import boto3
import json
import time
import os
from decimal import Decimal
from boto3.dynamodb.conditions import Key

# RESOURCES
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('IPReputationTable')

# CONFIG
ADMIN_SECRET = os.environ.get('ADMIN_SECRET', 'my-super-secret-password')

# HELPER: Fixes "Object of type Decimal is not JSON serializable" error
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj)
        return super(DecimalEncoder, self).default(obj)

def lambda_handler(event, context):
    headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'OPTIONS,POST,GET',
        'Access-Control-Allow-Headers': 'Content-Type,X-Admin-Secret'
    }

    try:
        # 1. SECURITY CHECK (The Guard)
        # We check for a header "X-Admin-Secret"
        request_headers = event.get('headers') or {}
        # Handle case-insensitive headers (APIGW sometimes lowercases them)
        client_secret = request_headers.get('X-Admin-Secret') or request_headers.get('x-admin-secret')
        
        if event['httpMethod'] != 'OPTIONS' and client_secret != ADMIN_SECRET:
            print(f"Unauthorized access attempt. Token provided: {client_secret}")
            return {
                'statusCode': 401,
                'headers': headers,
                'body': json.dumps({'error': 'Unauthorized. Missing or invalid X-Admin-Secret header.'})
            }

        if event['httpMethod'] == 'OPTIONS':
            return {'statusCode': 200, 'headers': headers, 'body': ''}

        # 2. GET /admin -> List Users
        if event['httpMethod'] == 'GET':
            # Scan returns everything. 
            response = table.scan()
            items = response.get('Items', [])
            # Sort by violation count (highest first) to make it useful
            items.sort(key=lambda x: x.get('violation_count', 0), reverse=True)
            
            return {
                'statusCode': 200,
                'headers': headers,
                'body': json.dumps(items, cls=DecimalEncoder)
            }

        # 3. POST /admin -> Action
        if event['httpMethod'] == 'POST':
            body = json.loads(event.get('body', '{}'))
            ip = body.get('ip')
            action = body.get('action')

            if not ip or not action:
                return {'statusCode': 400, 'headers': headers, 'body': json.dumps({'error': 'Missing IP or Action'})}

            if action == 'ban':
                expiry = int(time.time()) + 86400 # 24h
                table.update_item(
                    Key={'ip_address': ip},
                    UpdateExpression="SET is_banned = :t, ban_expiry = :e, violation_count = :max",
                    ExpressionAttributeValues={
                        ':t': True,
                        ':e': expiry,
                        ':max': 999 # Max it out so they look "bad" in the UI
                    }
                )
                msg = f"User {ip} has been BANNED."

            elif action == 'unban':
                table.update_item(
                    Key={'ip_address': ip},
                    UpdateExpression="SET is_banned = :f, violation_count = :zero",
                    ExpressionAttributeValues={
                        ':f': False,
                        ':zero': 0
                    }
                )
                msg = f"User {ip} has been UNBANNED."
            
            else:
                return {'statusCode': 400, 'headers': headers, 'body': json.dumps({'error': 'Invalid action'})}

            return {
                'statusCode': 200,
                'headers': headers,
                'body': json.dumps({'message': msg, 'ip': ip, 'status': action})
            }

    except Exception as e:
        print(f"Server Error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({'error': str(e)})
        }