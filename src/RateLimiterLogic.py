import boto3
import json
import time
import os
import hashlib
import requests
from botocore.exceptions import ClientError

# --- CONFIG ---
TARGET_IP = os.environ.get('TARGET_IP') 
DYNAMO_REGION = 'ap-northeast-1'

# --- RESOURCES ---
dynamodb = boto3.resource('dynamodb', region_name=DYNAMO_REGION)
rate_table = dynamodb.Table('RateLimitTable')
config_table = dynamodb.Table('FluxConfig')
reputation_table = dynamodb.Table('IPReputationTable')

def lambda_handler(event, context):
    try:
        # 1. PARSE REQUEST
        request_context = event.get('requestContext', {})
        ip = request_context.get('identity', {}).get('sourceIp', '0.0.0.0')
        headers = event.get('headers') or {}
        
        # 2. FETCH GLOBAL CONFIG (The "Shield" Logic)
        try:
            config_item = config_table.get_item(Key={'config_key': 'global'})['Item']
            mode = config_item.get('mode', 'normal')
            difficulty = int(config_item.get('difficulty', 4))
            cpu_threshold = int(config_item.get('cpu_threshold', 80))
        except Exception:
            # Fallback if config is missing
            mode = 'normal'
            difficulty = 4
            cpu_threshold = 80

        # 3. SHIELD MODE (Proof of Work Check)
        if mode == 'shield':
            solution = headers.get('x-puzzle-solution', '') or headers.get('X-Puzzle-Solution', '')
            
            # Validation: SHA256(IP + Solution) must start with "0000..."
            raw_string = f"{ip}{solution}"
            hashed = hashlib.sha256(raw_string.encode()).hexdigest()
            prefix = "0" * difficulty
            
            if not hashed.startswith(prefix):
                print(f"🛡️ SHIELD BLOCK: {ip} failed puzzle.")
                return {
                    'statusCode': 401,
                    'headers': {'Content-Type': 'application/json'},
                    'body': json.dumps({
                        'error': 'Shield Active. Solve Puzzle.',
                        'challenge': ip, 
                        'difficulty': difficulty
                    })
                }

        # 4. HEALTH CHECK (Adaptive Throttling)
        current_limit = 5 # Default limit
        try:
            # Query the EC2 Private IP for health
            # timeout=0.5s is critical so we don't hang if EC2 is dead
            health_resp = requests.get(f"{TARGET_IP}/health", timeout=0.5)
            server_data = health_resp.json()
            server_cpu = server_data.get('cpu', 0)
            
            if server_cpu > cpu_threshold:
                print(f"⚠️ HIGH LOAD ({server_cpu}%). Throttling aggressively.")
                current_limit = 2 # Squeeze traffic to save the server
        except Exception as e:
            print(f"Health Check Warning: {e}")
            # If backend is unresponsive, we throttle to protect it
            current_limit = 2

        # 5. ATOMIC RATE LIMITING
        now = int(time.time())
        window_key = f"{ip}-{int(now // 10) * 10}" # 10s Window
        
        rate_resp = rate_table.update_item(
            Key={'client_id': window_key},
            UpdateExpression="ADD request_count :inc SET expires_at = :exp",
            ExpressionAttributeValues={':inc': 1, ':exp': now + 60},
            ReturnValues="UPDATED_NEW"
        )
        count = int(rate_resp['Attributes']['request_count'])

        if count > current_limit:
            return {
                'statusCode': 429,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'Too Many Requests', 'limit': current_limit})
            }

        # 6. FORWARD TO BACKEND
        # We proxy the call to the Private IP
        backend_resp = requests.get(TARGET_IP, timeout=2)
        return {
            'statusCode': backend_resp.status_code,
            'body': backend_resp.text
        }

    except Exception as e:
        print(f"CRITICAL ERROR: {str(e)}")
        return {'statusCode': 500, 'body': json.dumps(str(e))}