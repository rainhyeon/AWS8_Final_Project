import boto3
import json
import re

def lambda_handler(event, context):
    s3 = boto3.client('s3')
    bedrock = boto3.client('bedrock-runtime', region_name='ap-northeast-2')

    s3_info = event['Records'][0]['s3']
    bucket = s3_info['bucket']['name']
    object_key = s3_info['object']['key']

    parts = object_key.split('/')
    if len(parts) < 5:
        raise ValueError("object_key 형식 오류: {bucket_name}/{SERVICE_NAME}/{DATE}/terraform-validation/{file_name} 형태여야 함")

    parsed_bucket = parts[0]
    SERVICE_NAME = parts[1]
    DATE = parts[2]
    FOLDER_NAME = parts[3]

    full_key = f"{parsed_bucket}/{SERVICE_NAME}/{DATE}/{FOLDER_NAME}"
    error_log_key = f"{full_key}/error.log"
    retry_count = event.get("retry_count", 0)

    try:
        response = s3.get_object(Bucket=bucket, Key=error_log_key)
        error_log = response['Body'].read().decode('utf-8')

        if "error" not in error_log.lower():
            print("✅ error.log에 에러 없음. 수정 없이 그대로 저장합니다.")

            # 원본 terraform.tf 경로 (소스)
            source_key = f"{full_key}/terraform.tf"

            # terraform.tf 파일 가져오기
            response = s3.get_object(Bucket=bucket, Key=source_key)
            content = response['Body'].read()

            return {
                "Records": [
                    {
                        "s3": {
                            "bucket": { "name": bucket },
                            "object": { "key": source_key }
                        }
                    }
                ],
                "error_present": False,
                "retry_count": retry_count
            }

    except s3.exceptions.NoSuchKey:
        print("❌ error.log가 존재하지 않음.")
        return {
            "error": "error.log not found",
            "error_present": True,
            "retry_count": retry_count
        }

    except Exception as e:
        print(f"예외 발생: {str(e)}")
        return {
            "error": str(e),
            "error_present": True,
            "retry_count": retry_count
        }

    print("⚠️ error.log에 에러 발견. .tf 파일들 분석 시작")
    tf_contents = ""

    tf_files = s3.list_objects_v2(Bucket=bucket, Prefix=full_key)
    for obj in tf_files.get('Contents', []):
        key = obj['Key']
        if key.endswith('.tf'):
            file_data = s3.get_object(Bucket=bucket, Key=key)
            content = file_data['Body'].read().decode('utf-8')
            tf_contents += f"# File: {key}\n{content}\n\n"

    # Claude 프롬프트
    prompt = f"""
        You are an expert in Terraform and infrastructure as code debugging.

        You are given two inputs:
        1. An error log from a Terraform validate/plan command.
        2. The current Terraform `.tf` code that caused this error.

        --- error.log ---
        {error_log}

        --- .tf files ---
        {tf_contents}

        Your task:

        - Analyze the error messages in `error.log`.
        - Identify exactly what is wrong in the Terraform code.
        - Fix all problems in the `.tf` code.
        For example, workarounds in the following situations:
            - Declaring any undeclared resources or variables if mentioned.
            - Adding missing dependencies (e.g., `depends_on`, missing route tables, missing listeners, etc.)
            - Correcting any invalid references or arguments.
            - Fixing cyclic dependencies by splitting security group rules if needed.

        Important output format:
        - Output only the corrected, complete Terraform code.
        - Do not include any explanation, heading, or text such as “Here is the corrected code”.

        If multiple `.tf` files are referenced, combine them into a single Terraform code block.
        No comment/comment/reasoning.
        """


    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 8182,
        "top_k": 250,
        "stop_sequences": [],
        "temperature": 0,
        "top_p": 0,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt
                    }
                ]
            }
        ]
    }

    response = bedrock.invoke_model(
        modelId="apac.anthropic.claude-sonnet-4-20250514-v1:0",
        contentType="application/json",
        accept="application/json",
        body=json.dumps(body)
    )

    response_body = json.loads(response['body'].read())
    fixed_code = response_body["content"][0]["text"]
    fixed_code = re.sub(r"```[a-z]*\n|\n```", "", fixed_code).strip()

    # 저장 경로 및 파일명
    output_key = f"{parsed_bucket}/{SERVICE_NAME}/{DATE}/terraform.tf"

    s3.put_object(
        Bucket="s3-terraform-12",
        Key=output_key,
        Body=fixed_code.encode('utf-8')
    )

    return {
        "Records": [
            {
                "s3": {
                    "bucket": { "name": "s3-terraform-12" },
                    "object": { "key": output_key }
                }
            }
        ],
        "error_present": True,
        "retry_count": retry_count + 1
    }
