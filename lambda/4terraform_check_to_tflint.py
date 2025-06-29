import boto3
import datetime

def lambda_handler(event, context):
    s3 = boto3.client('s3')

    s3_info = event['Records'][0]['s3']
    bucket = s3_info['bucket']['name']
    object_key = s3_info['object']['key']

    parts = object_key.split('/')
    if len(parts) < 4:
        raise ValueError("object_key 형식 오류: {USER_NAME}/{SERVICE_NAME}/{now_str}/{file_name} 형태여야 함")

    USER_NAME = parts[0] 
    SERVICE_NAME = parts[1]
    TIME = parts[2]
    FILE_NAME = parts[3]
    prefix = f"{USER_NAME}/{SERVICE_NAME}/{TIME}"
    artifact_bucket = "terraform-artifacts-bucket-12"

    retry_count = event.get("retry_count", 0)  # 없으면 0 반환
    print(f"retry_count: {retry_count}")

    CODEBUILD_PROJECT = "infra-terraform-invalidation"
    codebuild = boto3.client('codebuild')

    response = codebuild.start_build(
        projectName=CODEBUILD_PROJECT,
        environmentVariablesOverride=[
            {'name': 'S3_BUCKET', 'value': bucket, 'type': 'PLAINTEXT'},
            {'name': 'S3_PREFIX', 'value': prefix, 'type': 'PLAINTEXT'}
        ],
        sourceTypeOverride='S3',
        sourceLocationOverride=f'{bucket}/{prefix}/',
        artifactsOverride={
            "type": "S3",
            "location": f"{artifact_bucket}",  # 여기에 아티팩트 버킷명
            "path": f"{prefix}", # 원하는 아티팩트 prefix
            "packaging": "NONE",
            "name": ""   # 빈 문자열이면 파일명은 buildspec.yml artifacts.files 설정대로 됨
        }
    )

    return {
        "Records": [
            {
                "s3": {
                    "bucket": { "name": f"{artifact_bucket}" },
                    "object": { "key": f"{prefix}/{CODEBUILD_PROJECT}/error.log" }
                }
            },
            {
                "s3": {
                    "bucket": { "name": f"{artifact_bucket}" },
                    "object": { "key": f"{prefix}/{CODEBUILD_PROJECT}/{FILE_NAME}" }
                }
            }
        ],
        "retry_count": retry_count
    }

