import boto3
import json
import time
import os
from decimal import Decimal

# RESOURCES
dynamodb = boto3.resource('dynamodb')
rep_table = dynamodb.Table('IPReputationTable')
config_table = dynamodb.Table('FluxConfig')

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
        'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'
    }

    try:
        # 1. HANDLE OPTIONS (CORS Preflight)
        if event['httpMethod'] == 'OPTIONS':
            return {'statusCode': 200, 'headers': headers, 'body': ''}

        # 2. GET (List Users) - NO AUTH CHECK
        if event['httpMethod'] == 'GET':
            try:
                response = rep_table.scan()
                items = response.get('Items', [])
                items.sort(key=lambda x: x.get('violation_count', 0), reverse=True)
                return {
                    'statusCode': 200, 
                    'headers': headers, 
                    'body': json.dumps(items, cls=DecimalEncoder)
                }
            except Exception as e:
                print(f"DB Error: {e}")
                return {'statusCode': 500, 'headers': headers, 'body': json.dumps({'error': str(e)})}

        # 3. POST (Actions) - NO AUTH CHECK
        if event['httpMethod'] == 'POST':
            body = json.loads(event.get('body', '{}'))
            action = body.get('action')
            msg = "Action completed"

            if action == 'ban':
                ip = body.get('ip')
                expiry = int(time.time()) + 86400
                rep_table.update_item(
                    Key={'ip_address': ip},
                    UpdateExpression="SET is_banned = :t, ban_expiry = :e, violation_count = :max",
                    ExpressionAttributeValues={':t': True, ':e': expiry, ':max': 999}
                )
                msg = f"User {ip} BANNED."

            elif action == 'unban':
                ip = body.get('ip')
                rep_table.update_item(
                    Key={'ip_address': ip},
                    UpdateExpression="SET is_banned = :f, violation_count = :zero",
                    ExpressionAttributeValues={':f': False, ':zero': 0}
                )
                msg = f"User {ip} UNBANNED."

            elif action == 'seamless':
                ip = body.get('ip')
                expiry = int(time.time()) + 86400
                rep_table.update_item(
                    Key={'ip_address': ip},
                    UpdateExpression="SET is_seamless = :t, seamless_expiry = :e, is_banned = :f, violation_count = :zero",
                    ExpressionAttributeValues={':t': True, ':e': expiry, ':f': False, ':zero': 0}
                )
                msg = f"User {ip} is in SEAMLESS MODE."
            
            elif action == 'config':
                mode = body.get('mode')
                config_table.put_item(Item={
                    'config_key': 'global',
                    'mode': mode,
                    'difficulty': 4,
                    'cpu_threshold': 80
                })
                msg = f"System Mode set to: {mode}"

            return {'statusCode': 200, 'headers': headers, 'body': json.dumps({'message': msg})}

    except Exception as e:
        return {'statusCode': 500, 'headers': headers, 'body': json.dumps({'error': str(e)})}