
import boto3
import json
import os


def lambda_handler(event, context):
    s3 = boto3.client('s3')
    bedrock = boto3.client('bedrock-runtime', region_name='ap-northeast-2')
    sfn = boto3.client('stepfunctions')

    if "Records" in event and isinstance(event["Records"], list):
        s3_info = event["Records"][0]["s3"]
    elif "Records" in event and isinstance(event["Records"], dict):
        s3_info = event["Records"]["s3"]
    else:
        raise Exception("❌ event 구조가 예상과 다릅니다")

    bucket = s3_info['bucket']['name']
    object_key = s3_info['object']['key']

    parts = object_key.split("/")
    USER_NAME, SERVICE_NAME, DATE, *_ = parts

    error_count = event.get('error_count', 0)

    STATIC_CODEBUILD_NAME = "infra-terraform-invalidation"
    DYNAMIC_CODEBUILD_NAME = "terraform-terratest-codebuild"

    static_base_prefix = f"{USER_NAME}/{SERVICE_NAME}/{DATE}/{STATIC_CODEBUILD_NAME}/"
    dynamic_base_prefix = f"{USER_NAME}/{SERVICE_NAME}/{DATE}/{DYNAMIC_CODEBUILD_NAME}/"

    tf_key = static_base_prefix + "terraform.tf"
    terratest_key = dynamic_base_prefix + "terratest-output.txt"

    print(f"terraform 코드: {tf_key}")
    print(f"teratest 결과물: {terratest_key}")

    terratest_obj = s3.get_object(Bucket=bucket, Key=terratest_key)
    terratest_content = terratest_obj['Body'].read().decode('utf-8')

    final_tf_key = f"{SERVICE_NAME}/infra/output/terraform.tf"
    tf_obj = s3.get_object(Bucket=bucket, Key=tf_key)
    tf_content = tf_obj['Body'].read().decode('utf-8')

    terratest_content_lower = terratest_content.lower()
    if "error" in terratest_content_lower:
        error_lines = [
            line for line in terratest_content_lower.splitlines() if "error" in line
        ]
        error_present = any(("go-multierror" not in line) for line in error_lines)
    else:
        error_present = False

    if not error_present:
        s3.put_object(Bucket=USER_NAME, Key=final_tf_key, Body=tf_content.encode('utf-8'))

        return {
            "Records": [
                {
                    "s3": {
                        "bucket": {"name": bucket},
                        "object": {"key": tf_key}
                    }
                }
            ],
            "status": "success",
            "error_present": False,
            "error_count": error_count,
            "message": "테라폼 테스트가 성공적으로 완료되었습니다.",
            "user_id": USER_NAME,
            "service_name": SERVICE_NAME,
            "log_bucket": f"cloudtrail-logs-{USER_NAME}",
            "log_prefix": f"AWSLogs/{os.environ.get('ACCOUNT_ID', '798172178824')}/CloudTrail",
            "query_date": {
                "year": DATE[:4],
                "month": DATE[4:6],
                "day": DATE[6:8]
            }
        }

    prompt = f"""
You are a professional Terraform architect
Below are the Terraform test results (error) and the Terraform code.
Analyze the error and print out a new terraform code that fixes all problems.

--- Terra test output.txt ---
{terratest_content}

--- terraform.tf ---
{tf_content}

- Output each file in this format:
- Split each logical component into separate `.tf` blocks (e.g., `vpc.tf`, `subnet.tf`, `security_groups.tf`, `alb.tf`, `ec2.tf`, `iam.tf`, `outputs.tf`)
- Use only Terraform native syntax, no comments or explanations
- Code must be directly executable with `terraform apply`
- Output each file in this format:

// Filename: terraform.tf
```
<Terraform code block>
```
Only include code blocks for .tf files.
"""

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 8184,
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

    result = json.loads(response['body'].read())
    new_tf_code = result["content"][0]["text"].strip()

    import re
    new_tf_code = re.findall(
        r"// Filename: (.+?\.tf)\n```(?:hcl)?\n([\s\S]*?)```", new_tf_code
    )

    combined_code = ""
    for filename, code in new_tf_code:
        combined_code += f"// Filename: {filename.strip()}\n{code.strip()}\n\n"

    s3.put_object(Bucket=bucket, Key=tf_key, Body=combined_code.encode('utf-8'))

    sfn.start_execution(
        stateMachineArn="arn:aws:states:ap-northeast-2:798172178824:stateMachine:GenerateIAMPolicyStepFunction",
        input=json.dumps({
            "user_id": USER_NAME,
            "log_bucket": f"cloudtrail-logs-{USER_NAME}",
            "log_prefix": f"AWSLogs/{os.environ.get('ACCOUNT_ID', '798172178824')}/CloudTrail",
            "query_date": {
                "year": DATE[:4],
                "month": DATE[4:6],
                "day": DATE[6:8]
            }
        })
    )

    return {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": bucket},
                    "object": {"key": tf_key}
                }
            }
        ],
        "status": "error_fixed",
        "error_present": True,
        "error_count": error_count + 1,
        "message": "에러가 감지되어 terraform.tf를 수정하여 저장함.",
        "terraform_key": tf_key,
        "user_id": USER_NAME,
        "service_name": SERVICE_NAME,
        "log_bucket": f"cloudtrail-logs-{USER_NAME}",
        "log_prefix": f"AWSLogs/{os.environ.get('ACCOUNT_ID', '798172178824')}/CloudTrail",
        "query_date": {
            "year": DATE[:4],
            "month": DATE[4:6],
            "day": DATE[6:8]
        }
    }
