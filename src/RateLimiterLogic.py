import boto3
import json
import time
import os
import urllib.request
import urllib.error
import logging
from datetime import datetime
from botocore.exceptions import ClientError

# --- LOGGING CONFIGURATION ---
# Sets up structured logging. In production, this allows you to search logs by "level" or "ip".
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# --- RESOURCES ---
# Initialized outside handler for "Execution Context Reuse" (Faster warm starts)
dynamodb = boto3.resource('dynamodb')
rate_table = dynamodb.Table(os.environ.get('TABLE_NAME', 'RateLimitTable'))
reputation_table = dynamodb.Table('IPReputationTable') 

# --- CONFIGURATION ---
LIMIT = int(os.environ.get('RATE_LIMIT', 5))
WINDOW = int(os.environ.get('WINDOW_SECONDS', 10))
MAX_VIOLATIONS = int(os.environ.get('MAX_VIOLATIONS', 50))
BAN_DURATION = 86400  # 24 Hours
TARGET_API_URL = os.environ.get('TARGET_API_URL', 'http://127.0.0.1:8000/')

def lambda_handler(event, context):
    """
    Main Entry Point.
    Uses Atomic Counters to enforce rate limits and forwards traffic if allowed.
    """
    try:
        # 1. PARSE & VALIDATE INPUT
        # Handle API Gateway "Proxy Integration" event structure
        request_context = event.get('requestContext', {})
        identity = request_context.get('identity', {})
        
        # Fallback to "Unknown" if testing locally or missing IP
        user_ip = identity.get('sourceIp', 'unknown-ip')
        
        current_time = int(time.time())
        today_str = datetime.utcnow().strftime('%Y-%m-%d')
        
        logger.info(json.dumps({
            "event": "request_received",
            "ip": user_ip,
            "target": TARGET_API_URL
        }))

        # --- PHASE 1: PRISON CHECK (The 24h Ban) ---
        if is_ip_banned(user_ip, current_time):
            logger.warning(json.dumps({"event": "access_denied", "reason": "banned", "ip": user_ip}))
            return {
                'statusCode': 403,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'Access Denied', 'message': 'You are temporarily banned due to excessive abuse.'})
            }

        # --- PHASE 2: RATE LIMIT CHECK (The 10s Window) ---
        # Calculate Window ID (Floors time to nearest 10s: 12:00:00, 12:00:10...)
        window_id = int(current_time // WINDOW) * WINDOW
        rate_key = f"{user_ip}-{window_id}"
        
        current_count = increment_request_count(rate_key, current_time)

        # --- PHASE 3: JUDGMENT ---
        if current_count > LIMIT:
            logger.warning(json.dumps({
                "event": "rate_limit_exceeded", 
                "ip": user_ip, 
                "count": current_count, 
                "limit": LIMIT
            }))
            
            # Async-like call to record violation (Keep it fast)
            record_violation(user_ip, today_str, current_time)
            
            return {
                'statusCode': 429,
                'headers': {'Content-Type': 'application/json', 'Retry-After': str(WINDOW)},
                'body': json.dumps({'error': 'Too Many Requests', 'message': 'Slow down.'})
            }
        
        # --- PHASE 4: FORWARD REQUEST ---
        logger.info(json.dumps({"event": "request_allowed", "ip": user_ip}))
        return forward_request()

    except Exception as e:
        logger.error(json.dumps({"event": "system_error", "error": str(e)}), exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({"error": "Internal Gateway Error", "requestId": context.aws_request_id})
        }

# -------------------------------------------------------------------------
# HELPER FUNCTIONS (Separated for Testability & Readability)
# -------------------------------------------------------------------------

def is_ip_banned(ip, now):
    """
    Checks the IPReputationTable for an active ban.
    A user is considered banned if the 'is_banned' flag is true and the current time is before the 'ban_expiry' timestamp.
    """
    try:
        response = reputation_table.get_item(Key={'ip_address': ip})
        if 'Item' in response:
            item = response['Item']
            # Check if 'is_banned' is True AND expiry time is in the future
            if item.get('is_banned') and now < int(item.get('ban_expiry', 0)):
                return True
        return False
    except ClientError as e:
        logger.error(f"DynamoDB Read Error (Reputation): {e}")
        return False # Fail Open (Allow traffic if DB breaks)

def increment_request_count(key, now):
    """Atomically increments the request counter for the current window."""
    try:
        response = rate_table.update_item(
            Key={'client_id': key},
            UpdateExpression="ADD request_count :inc SET expires_at = :exp",
            ExpressionAttributeValues={
                ':inc': 1, 
                ':exp': now + 60 # TTL: Auto-delete after 60s to save money
            },
            ReturnValues="UPDATED_NEW"
        )
        # Convert Decimal to int immediately
        return int(response['Attributes']['request_count'])
    except ClientError as e:
        logger.error(f"DynamoDB Write Error (RateLimit): {e}")
        raise e # Fail Closed (If we can't count, we should probably error out)

def record_violation(ip, today_str, now):
    """Increments violation count and applies Ban if threshold exceeded."""
    try:
        # 1. Atomic Increment
        resp = reputation_table.update_item(
            Key={'ip_address': ip},
            UpdateExpression="SET violation_count = if_not_exists(violation_count, :zero) + :inc, last_violation_date = :today",
            ExpressionAttributeValues={
                ':inc': 1, 
                ':zero': 0, 
                ':today': today_str
            },
            ReturnValues="UPDATED_NEW"
        )
        
        new_violation_count = int(resp['Attributes']['violation_count'])
        
        # 2. Ban Logic
        if new_violation_count > MAX_VIOLATIONS:
            logger.warning(f"BANNING IP: {ip} (Violations: {new_violation_count})")
            reputation_table.update_item(
                Key={'ip_address': ip},
                UpdateExpression="SET is_banned = :true, ban_expiry = :expiry, violation_count = :zero",
                ExpressionAttributeValues={
                    ':true': True,
                    ':expiry': now + BAN_DURATION,
                    ':zero': 0 # Reset count on ban
                }
            )
    except ClientError as e:
        logger.error(f"Failed to record violation for {ip}: {e}")

def forward_request():
    """Proxies the request to the backend with explicit timeouts."""
    try:
        req = urllib.request.Request(TARGET_API_URL)
        # Timeout is CRITICAL. Without it, Lambda hangs for 30s and you pay for it.
        # 3.05s is a standard 'wait slightly longer than 3s' timeout.
        with urllib.request.urlopen(req, timeout=3.05) as response:
            return {
                'statusCode': response.getcode(),
                'body': response.read().decode('utf-8'),
                'headers': {'Content-Type': 'application/json'}
            }
    except urllib.error.HTTPError as e:
        return {'statusCode': e.code, 'body': e.read().decode('utf-8')}
    except urllib.error.URLError as e:
        logger.error(f"Backend Unreachable: {e.reason}")
        return {'statusCode': 502, 'body': json.dumps({'error': 'Bad Gateway', 'message': 'Backend unavailable'})}
    except Exception as e:
        # Catches timeout errors (socket.timeout)
        logger.error(f"Backend Timeout/Error: {e}")
        return {'statusCode': 504, 'body': json.dumps({'error': 'Gateway Timeout', 'message': 'Backend took too long'})}