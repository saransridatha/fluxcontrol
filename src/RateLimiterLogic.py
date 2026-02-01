import boto3
import json
import time
import os
import hashlib
import requests
from botocore.exceptions import ClientError

# --- RESOURCES ---
# Hardcoded region to be safe
dynamodb = boto3.resource('dynamodb', region_name='ap-northeast-1')
rate_table = dynamodb.Table('RateLimitTable')
config_table = dynamodb.Table('FluxConfig')
reputation_table = dynamodb.Table('IPReputationTable')

# --- CONFIG (HARDCODED FOR SAFETY) ---
TARGET_IP = "http://172.31.34.253:8000"

def lambda_handler(event, context):
    print(f"DEBUG: Lambda Started. Target: {TARGET_IP}")
    
    try:
        # 1. PARSE REQUEST
        request_context = event.get('requestContext', {})
        ip = request_context.get('identity', {}).get('sourceIp', '0.0.0.0')
        print(f"DEBUG: Processing IP: {ip}")

        # 2. CHECK BAN STATUS
        try:
            user_record = reputation_table.get_item(Key={'ip_address': ip}).get('Item', {})
            if user_record.get('is_banned'):
                if int(time.time()) < int(user_record.get('ban_expiry', 0)):
                    print(f"🚫 BLOCKED BANNED USER: {ip}")
                    return response(403, {'error': 'Access Denied', 'message': 'You are banned.'})
        except Exception as e:
            print(f"DEBUG: Ban Check Failed: {e}")

        # 3. FETCH CONFIG
        try:
            config_item = config_table.get_item(Key={'config_key': 'global'})['Item']
            mode = config_item.get('mode', 'normal')
            difficulty = int(config_item.get('difficulty', 4))
            cpu_threshold = int(config_item.get('cpu_threshold', 80))
            print(f"DEBUG: Config Loaded. Mode: {mode}")
        except Exception:
            print("DEBUG: Config missing, using defaults.")
            mode = 'normal'
            difficulty = 4
            cpu_threshold = 80

        # 4. SHIELD MODE
        if mode == 'shield':
            headers = event.get('headers') or {}
            solution = headers.get('x-puzzle-solution', '') or headers.get('X-Puzzle-Solution', '')
            raw_string = f"{ip}{solution}"
            hashed = hashlib.sha256(raw_string.encode()).hexdigest()
            prefix = "0" * difficulty
            
            if not hashed.startswith(prefix):
                print(f"🛡️ SHIELD BLOCK: {ip}")
                # Log to dashboard
                update_dashboard(ip, is_violation=False)
                return response(401, {
                    'error': 'Shield Active. Solve Puzzle.', 
                    'challenge': ip, 
                    'difficulty': difficulty
                })

        # 5. HEALTH CHECK & LIMIT
        current_limit = 5
        try:
            # Short timeout to prevent hanging
            health_resp = requests.get(f"{TARGET_IP}/health", timeout=0.5)
            server_cpu = health_resp.json().get('cpu', 0)
            print(f"DEBUG: Server CPU: {server_cpu}%")
            
            if server_cpu > cpu_threshold:
                print("⚠️ HIGH LOAD. Throttling.")
                current_limit = 2
        except Exception as e:
            print(f"DEBUG: Health Check Skipped: {e}")
            current_limit = 2

        # 6. ATOMIC COUNTER
        now = int(time.time())
        window_key = f"{ip}-{int(now // 10) * 10}"
        
        rate_resp = rate_table.update_item(
            Key={'client_id': window_key},
            UpdateExpression="ADD request_count :inc SET expires_at = :exp",
            ExpressionAttributeValues={':inc': 1, ':exp': now + 60},
            ReturnValues="UPDATED_NEW"
        )
        count = int(rate_resp['Attributes']['request_count'])
        print(f"DEBUG: Count {count}/{current_limit}")

        if count > current_limit:
            print("DEBUG: Rate Limit Exceeded")
            update_dashboard(ip, is_violation=True)
            return response(429, {'error': 'Too Many Requests', 'limit': current_limit})

        # 7. SUCCESS FORWARD
        if count == 1:
            update_dashboard(ip, is_violation=False)

        print("DEBUG: Forwarding to Backend...")
        backend_resp = requests.get(TARGET_IP, timeout=2)
        print(f"DEBUG: Backend Response: {backend_resp.status_code}")
        
        return {
            'statusCode': backend_resp.status_code,
            'body': backend_resp.text,
            'headers': {'Content-Type': 'application/json'}
        }

    except Exception as e:
        print(f"CRITICAL EXCEPTION: {str(e)}")
        # Return a valid JSON error so API Gateway doesn't explode
        return response(500, {'error': 'Internal Logic Error', 'details': str(e)})

def response(code, body_dict):
    """Helper to ensure API Gateway always gets the format it wants"""
    return {
        'statusCode': code,
        'body': json.dumps(body_dict),
        'headers': {'Content-Type': 'application/json'}
    }

def update_dashboard(ip, is_violation=False):
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
        print(f"DEBUG: Dashboard Updated for {ip}")
    except Exception as e:
        print(f"DEBUG: Dashboard Update Failed: {e}")