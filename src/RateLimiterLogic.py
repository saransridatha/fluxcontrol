import boto3
import json
import time
import os
import urllib.request
import urllib.error
from datetime import datetime

# --- RESOURCES ---
# We initialize these outside the handler for better performance (Connection Reuse)
dynamodb = boto3.resource('dynamodb')
rate_table = dynamodb.Table(os.environ.get('TABLE_NAME', 'RateLimitTable'))
reputation_table = dynamodb.Table('IPReputationTable') 

# --- CONFIGURATION ---
LIMIT = 5            # 5 requests per window
WINDOW = 10          # 10s window
MAX_VIOLATIONS = 50  # 50 blocks allowed per day
BAN_DURATION = 86400 # 24 Hours in seconds (1 Day)
# Default to localhost if not set, but you MUST set this in Lambda Env Vars
TARGET_API_URL = os.environ.get('TARGET_API_URL', 'http://127.0.0.1:8000/')

def lambda_handler(event, context):
    print("STEP 1: Lambda Started. Parsing Event...")
    
    try:
        # 1. Get User Identity (IP)
        # Handle cases where sourceIp might be missing (local testing)
        if 'requestContext' in event and 'identity' in event['requestContext']:
            user_ip = event['requestContext']['identity']['sourceIp']
        else:
            user_ip = "127.0.0.1" # Fallback for testing
            
        current_time = int(time.time())
        today_str = datetime.utcnow().strftime('%Y-%m-%d')

        print(f"User IP: {user_ip} | Target: {TARGET_API_URL}")

        # --- PHASE 1: PRISON CHECK (The 24h Ban) ---
        print("STEP 2: Checking Reputation Table...")
        try:
            rep_response = reputation_table.get_item(Key={'ip_address': user_ip})
            if 'Item' in rep_response:
                rep = rep_response['Item']
                
                # Check if banned
                if rep.get('is_banned') and current_time < int(rep.get('ban_expiry', 0)):
                    print(f"BLOCKED: User {user_ip} is BANNED until {rep.get('ban_expiry')}")
                    return {
                        'statusCode': 403,
                        'body': json.dumps({'error': 'You are banned for 24 hours due to excessive abuse.'})
                    }
        except Exception as e:
            # If DB fails, we fail open (allow request) or log error
            print(f"STEP 2 ERROR: Failed to read Reputation Table: {e}")
            # We proceed to rate limit check even if this fails

        # --- PHASE 2: RATE LIMIT CHECK (The 10s Window) ---
        print("STEP 3: Checking Rate Limit (Atomic Counter)...")
        
        # Calculate Window ID (e.g., 12:00:00, 12:00:10)
        window_id = int(current_time // WINDOW) * WINDOW
        key = f"{user_ip}-{window_id}"
        
        try:
            # Atomic Increment
            response = rate_table.update_item(
                Key={'client_id': key},
                UpdateExpression="ADD request_count :inc SET expires_at = :exp",
                ExpressionAttributeValues={
                    ':inc': 1, 
                    ':exp': current_time + 60 # TTL
                },
                ReturnValues="UPDATED_NEW"
            )
            # DynamoDB returns Decimal, convert to int
            current_count = int(response['Attributes']['request_count'])
            print(f"Count for {key}: {current_count}")
            
        except Exception as e:
            print(f"STEP 3 ERROR: Rate Limit DB Failed: {e}")
            return {'statusCode': 500, 'body': 'Internal Database Error'}

        # --- PHASE 3: JUDGMENT ---
        if current_count > LIMIT:
            print(f"VIOLATION: User {user_ip} exceeded limit ({current_count}/{LIMIT})")
            
            # Record this strike on their permanent record
            record_violation(user_ip, today_str, current_time)
            
            return {
                'statusCode': 429,
                'body': json.dumps({
                    'error': 'Too Many Requests', 
                    'message': 'Slow down! Rate limit exceeded.'
                })
            }
        
        # --- PHASE 4: FORWARD REQUEST ---
        print("STEP 4: Forwarding request to EC2 Backend...")
        return forward_request()

    except Exception as e:
        print(f"CRITICAL SYSTEM ERROR: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps(f"Internal Gateway Error: {str(e)}")
        }

def record_violation(ip, today, now):
    """Increments violation count. If > MAX_VIOLATIONS, Bans user."""
    try:
        print(f"RECORDING VIOLATION for {ip}...")
        
        # 1. Atomic Increment of violation count
        resp = reputation_table.update_item(
            Key={'ip_address': ip},
            UpdateExpression="SET violation_count = if_not_exists(violation_count, :zero) + :inc, last_violation_date = :today",
            ExpressionAttributeValues={
                ':inc': 1, 
                ':zero': 0,
                ':today': today
            },
            ReturnValues="UPDATED_NEW"
        )
        
        new_count = int(resp['Attributes']['violation_count'])
        print(f"Total Violations for {ip}: {new_count}")
        
        # 2. Check for Ban Threshold
        if new_count > MAX_VIOLATIONS:
            print(f"BAN HAMMER: Banning {ip} for 24 hours.")
            reputation_table.update_item(
                Key={'ip_address': ip},
                UpdateExpression="SET is_banned = :true, ban_expiry = :expiry, violation_count = :zero",
                ExpressionAttributeValues={
                    ':true': True,
                    ':expiry': now + BAN_DURATION,
                    ':zero': 0 # Optional: reset count so they start fresh after ban
                }
            )
    except Exception as e:
        print(f"Failed to record violation: {e}")

def forward_request():
    """Helper function to call the real API"""
    try:
        # Create Request
        req = urllib.request.Request(TARGET_API_URL)
        
        # Open Connection (This is where TIMEOUTS usually happen)
        # Set a short timeout (e.g. 5s) so Lambda doesn't hang forever
        with urllib.request.urlopen(req, timeout=5) as response:
            data = response.read().decode('utf-8')
            status = response.getcode()
            print(f"STEP 4 SUCCESS: Got {status} from backend.")
            
            return {
                'statusCode': status,
                'body': data,
                'headers': {'Content-Type': 'application/json'}
            }
            
    except urllib.error.HTTPError as e:
        # The backend returned a 4xx or 5xx error (e.g. 404 Not Found)
        print(f"STEP 4 BACKEND ERROR: {e.code}")
        return {
            'statusCode': e.code, 
            'body': e.read().decode('utf-8')
        }
        
    except urllib.error.URLError as e:
        # Connection Refused / Timeout / DNS Failure
        print(f"STEP 4 CONNECTION FAILED: {e.reason}")
        return {
            'statusCode': 502, 
            'body': json.dumps({
                'error': 'Bad Gateway', 
                'details': f"Could not connect to backend: {str(e.reason)}"
            })
        }
        
    except Exception as e:
        print(f"STEP 4 UNKNOWN ERROR: {e}")
        return {'statusCode': 500, 'body': str(e)}