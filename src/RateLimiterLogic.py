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
        
        # 2. CHECK BAN STATUS (The Prison Check)
        # We must check this first!
        try:
            user_record = reputation_table.get_item(Key={'ip_address': ip}).get('Item', {})
            if user_record.get('is_banned'):
                # Check if ban is still active
                if int(time.time()) < int(user_record.get('ban_expiry', 0)):
                    print(f"🚫 BANNED USER BLOCKED: {ip}")
                    return {
                        'statusCode': 403,
                        'body': json.dumps({'error': 'Access Denied', 'message': 'You are banned.'})
                    }
        except Exception as e:
            print(f"Ban Check Error: {e}")

        # 3. FETCH GLOBAL CONFIG (The Shield Logic)
        try:
            config_item = config_table.get_item(Key={'config_key': 'global'})['Item']
            mode = config_item.get('mode', 'normal')
            difficulty = int(config_item.get('difficulty', 4))
            cpu_threshold = int(config_item.get('cpu_threshold', 80))
        except Exception:
            mode = 'normal'
            difficulty = 4
            cpu_threshold = 80

        # 4. SHIELD MODE (Proof of Work)
        if mode == 'shield':
            solution = headers.get('x-puzzle-solution', '') or headers.get('X-Puzzle-Solution', '')
            raw_string = f"{ip}{solution}"
            hashed = hashlib.sha256(raw_string.encode()).hexdigest()
            prefix = "0" * difficulty
            
            if not hashed.startswith(prefix):
                # REPORT ACTIVITY (So they show up in Dashboard)
                update_dashboard(ip, is_violation=False) 
                
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

        # 5. HEALTH CHECK (Adaptive Throttling)
        current_limit = 5 
        try:
            health_resp = requests.get(f"{TARGET_IP}/health", timeout=0.5)
            server_data = health_resp.json()
            server_cpu = server_data.get('cpu', 0)
            
            if server_cpu > cpu_threshold:
                print(f"⚠️ HIGH LOAD ({server_cpu}%). Throttling.")
                current_limit = 2 
        except Exception as e:
            print(f"Health Check Warning: {e}")
            current_limit = 2

        # 6. ATOMIC RATE LIMITING
        now = int(time.time())
        window_key = f"{ip}-{int(now // 10) * 10}"
        
        rate_resp = rate_table.update_item(
            Key={'client_id': window_key},
            UpdateExpression="ADD request_count :inc SET expires_at = :exp",
            ExpressionAttributeValues={':inc': 1, ':exp': now + 60},
            ReturnValues="UPDATED_NEW"
        )
        count = int(rate_resp['Attributes']['request_count'])

        if count > current_limit:
            # REPORT VIOLATION to Dashboard
            update_dashboard(ip, is_violation=True)
            return {
                'statusCode': 429,
                'body': json.dumps({'error': 'Too Many Requests', 'limit': current_limit})
            }

        # 7. SUCCESS - REPORT & FORWARD
        # We only report to dashboard periodically or on first hit to save DB writes
        # But for this Demo, we update "last_seen" so they appear instantly
        if count == 1:
            update_dashboard(ip, is_violation=False)

        backend_resp = requests.get(TARGET_IP, timeout=2)
        return {
            'statusCode': backend_resp.status_code,
            'body': backend_resp.text
        }

    except Exception as e:
        print(f"CRITICAL ERROR: {str(e)}")
        return {'statusCode': 500, 'body': json.dumps(str(e))}

def update_dashboard(ip, is_violation=False):
    """Helper to ensure user appears in Admin Dashboard"""
    try:
        expr = "SET last_seen = :t"
        vals = {':t': int(time.time())}
        
        if is_violation:
            expr += ", violation_count = if_not_exists(violation_count, :z) + :inc"
            vals[':inc'] = 1
            vals[':z'] = 0
            
        reputation_table.update_item(
            Key={'ip_address': ip},
            UpdateExpression=expr,
            ExpressionAttributeValues=vals
        )
    except Exception as e:
        print(f"Dashboard Update Failed: {e}")