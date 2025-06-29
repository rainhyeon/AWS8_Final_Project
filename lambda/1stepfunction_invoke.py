import boto3
import json

def lambda_handler(event, context):
    sfn = boto3.client("stepfunctions")
    state_machine_arn = "arn:aws:states:ap-northeast-2:798172178824:stateMachine:Intra3Steps"

    # S3 이벤트에서 버킷 이름과 오브젝트 키만 추출
    records = []
    for record in event['Records']:
        bucket_name = record['s3']['bucket']['name']
        object_key = record['s3']['object']['key']
        records.append({
            "s3": {
                "bucket": {"name": bucket_name},
                "object": {"key": object_key}
            }
        })
        
    # Step Functions 실행 input으로 전달
    slim_event = {"Records": records,
                    "project_id": 1,
                    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzUxMTgzMzUyLCJpYXQiOjE3NTExODE1NTIsImp0aSI6IjczOWI4MDIxMDdhYTQxNTQ5ZjY4ZWI1YTRiOTE1NGEwIiwidXNlcl9pZCI6MX0.l2jmta5Q1H87CWZF3IknXis92Ggvv26A0Rv4m6ZSXYo"}

    response = sfn.start_execution(
        stateMachineArn=state_machine_arn,
        input=json.dumps(slim_event)
    )
    return {
        "message": "Step Functions started successfully",
        "executionArn": response['executionArn'],
        "input": slim_event
    }
