import boto3
import json
import time
from decimal import Decimal

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('IPReputationTable')

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj)
        return super(DecimalEncoder, self).default(obj)

def lambda_handler(event, context):
    print("Received event:", json.dumps(event))
    
    headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'OPTIONS,POST,GET'
    }
    
    method = event.get('httpMethod')
    
    try:
        if method == 'GET':
            response = table.scan()
            items = response.get('Items', [])
            
            return {
                'statusCode': 200,
                'headers': headers,
                'body': json.dumps(items, cls=DecimalEncoder)
            }

        if method == 'POST':
            body = json.loads(event.get('body', '{}'))
            ip = body.get('ip')
            action = body.get('action')
            
            if not ip or not action:
                return {
                    'statusCode': 400,
                    'headers': headers,
                    'body': json.dumps({'error': 'Missing ip or action'})
                }

            if action == 'ban':
                expiry = int(time.time()) + 86400
                table.update_item(
                    Key={'ip_address': ip},
                    UpdateExpression="SET is_banned = :t, ban_expiry = :e, violation_count = :zero",
                    ExpressionAttributeValues={
                        ':t': True,
                        ':e': expiry,
                        ':zero': 50
                    }
                )
                msg = f"Success: {ip} has been manually banned for 24h."

            elif action == 'unban':
                table.update_item(
                    Key={'ip_address': ip},
                    UpdateExpression="SET is_banned = :f, violation_count = :zero",
                    ExpressionAttributeValues={
                        ':f': False,
                        ':zero': 0
                    }
                )
                msg = f"Success: {ip} is now clean."
            
            else:
                return {
                    'statusCode': 400,
                    'headers': headers,
                    'body': 'Invalid action. Use "ban" or "unban".'
                }

            return {
                'statusCode': 200,
                'headers': headers,
                'body': json.dumps({'message': msg})
            }

        if method == 'OPTIONS':
            return {
                'statusCode': 200,
                'headers': headers,
                'body': ''
            }

    except Exception as e:
        print(f"Error: {e}")
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({'error': str(e)})
        }
