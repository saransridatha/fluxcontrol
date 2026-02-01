import boto3
import json
import time
import os
from decimal import Decimal

# RESOURCES
dynamodb = boto3.resource('dynamodb')
rep_table = dynamodb.Table('IPReputationTable')
config_table = dynamodb.Table('FluxConfig')
ADMIN_SECRET = os.environ.get('ADMIN_SECRET', 'FluxRulez2026!')

# HELPER
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
        # 1. SECURITY CHECK
        req_headers = event.get('headers') or {}
        client_secret = req_headers.get('X-Admin-Secret') or req_headers.get('x-admin-secret')
        
        if event['httpMethod'] != 'OPTIONS' and client_secret != ADMIN_SECRET:
            return {'statusCode': 401, 'headers': headers, 'body': json.dumps({'error': 'Unauthorized'})}

        if event['httpMethod'] == 'OPTIONS':
            return {'statusCode': 200, 'headers': headers, 'body': ''}

        # 2. GET (List Users)
        if event['httpMethod'] == 'GET':
            response = rep_table.scan()
            items = response.get('Items', [])
            items.sort(key=lambda x: x.get('violation_count', 0), reverse=True)
            return {'statusCode': 200, 'headers': headers, 'body': json.dumps(items, cls=DecimalEncoder)}

        # 3. POST (Actions)
        if event['httpMethod'] == 'POST':
            body = json.loads(event.get('body', '{}'))
            action = body.get('action')

            # ACTION: BAN
            if action == 'ban':
                ip = body.get('ip')
                expiry = int(time.time()) + 86400
                rep_table.update_item(
                    Key={'ip_address': ip},
                    UpdateExpression="SET is_banned = :t, ban_expiry = :e, violation_count = :max",
                    ExpressionAttributeValues={':t': True, ':e': expiry, ':max': 999}
                )
                msg = f"User {ip} BANNED."

            # ACTION: UNBAN
            elif action == 'unban':
                ip = body.get('ip')
                rep_table.update_item(
                    Key={'ip_address': ip},
                    UpdateExpression="SET is_banned = :f, violation_count = :zero",
                    ExpressionAttributeValues={':f': False, ':zero': 0}
                )
                msg = f"User {ip} UNBANNED."

            # ACTION: SEAMLESS (VIP)
            elif action == 'seamless':
                ip = body.get('ip')
                expiry = int(time.time()) + 86400
                rep_table.update_item(
                    Key={'ip_address': ip},
                    UpdateExpression="SET is_seamless = :t, seamless_expiry = :e, is_banned = :f, violation_count = :zero",
                    ExpressionAttributeValues={':t': True, ':e': expiry, ':f': False, ':zero': 0}
                )
                msg = f"User {ip} is in SEAMLESS MODE."
            
            # ACTION: CONFIG (Toggle Shield)
            elif action == 'config':
                mode = body.get('mode') # 'normal' or 'shield'
                config_table.put_item(Item={
                    'config_key': 'global',
                    'mode': mode,
                    'difficulty': 4,
                    'cpu_threshold': 80
                })
                msg = f"System Mode set to: {mode}"

            else:
                return {'statusCode': 400, 'headers': headers, 'body': json.dumps({'error': 'Invalid Action'})}

            return {'statusCode': 200, 'headers': headers, 'body': json.dumps({'message': msg})}

    except Exception as e:
        return {'statusCode': 500, 'headers': headers, 'body': json.dumps({'error': str(e)})}