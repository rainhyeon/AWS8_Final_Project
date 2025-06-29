import boto3
import json

# Bedrock (Claude) + S3 클라이언트
bedrock = boto3.client("bedrock-runtime", region_name="ap-northeast-2")
s3 = boto3.client("s3")

def lambda_handler(event, context):
    # S3 업로드 정보 파싱 -> 
    bucket_name = event['Records'][0]['s3']['bucket']['name'] # terraform-artifacts-bucket-12
    object_key = event['Records'][0]['s3']['object']['key']   # 예시: "{사용자명}/{프로젝트명}/{날짜}/infra-terraform-invalidation/terraform.tf"

    # S3 경로 파싱
    parts = object_key.split('/')
    if len(parts) < 5:
        raise ValueError("object_key 형식 오류: {사용자명}/{프로젝트명}/{날짜}/infra-terraform-invalidation/terraform.tf")

    # SERVICE_NAME 추출
    USER_NAME = parts[0]         # {사용자명}
    SERVICE_NAME = parts[1]     # 프로젝트명
    DATE = parts[2]             # 날짜
        

    # === [1] S3 경로 정보 파라미터 받기 ===
    spec_bucket = bucket_name
    spec_key = object_key
    # s3://s3-terra-output-bucket/onprem-to-aws-input/shopping/20250621/20250621_aws_specification.md
    tf_bucket = "s3-terra-output-bucket"
    tf_key = f"{USER_NAME}/{SERVICE_NAME}/{DATE}/{DATE}_aws_specification.txt"

    # === [2] S3에서 파일 다운로드 및 텍스트 디코딩 ===
    on_premise_obj = s3.get_object(Bucket=spec_bucket, Key=spec_key)
    on_premise_spec = on_premise_obj["Body"].read().decode("utf-8")

    tf_code_obj = s3.get_object(Bucket=tf_bucket, Key=tf_key)
    terraform_code = tf_code_obj["Body"].read().decode("utf-8")

    # === [2] Claude에게 보낼 Markdown 기반 리포트 프롬프트 생성 ===
    prompt = f"""
결과는 꼭 한국어로 작성해줘
## 작업 내용
온프레미스 시스템 사양과 Terraform 코드를 기반으로, 임원 및 엔지니어를 위한 명확하고 전문적인 AWS Lift & Shift 마이그레이션 보고서를 작성하세요.

## 보고서 형식
전체 보고서는 Markdown으로 작성합니다.
적절한 경우, 제목(##, ###), 표, 불릿포인트를 활용하세요.

## 보고서 섹션
1. Executive Summary (요약)
2. Current On-Premise Architecture (현재 온프레미스 아키텍처)
3. AWS Mapping Plan (AWS 매핑 계획)
4. Migration Strategy: Lift & Shift (마이그레이션 전략: Lift & Shift)
5. Terraform Code Breakdown (Terraform 코드 상세 설명)

## 입력 예시

온프레미스 사양
{on_premise_spec}

Terraform 코드
{terraform_code}
"""

    # === [3] invoke_model 요청 구성 ===
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1024,
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

    try:
        # Claude 3 Haiku로 호출 (on-demand)
        response = bedrock.invoke_model(
            modelId="anthropic.claude-3-haiku-20240307-v1:0",
            contentType="application/json",
            accept="application/json",
            body=json.dumps(body)
        )

        result = json.loads(response["body"].read())
        markdown_output = result["content"][0]["text"]  # ✅ 여기 수정됨!

        # === [5] Markdown 형식으로 응답 반환 ===

        # 저장 경로 정의
        output_bucket = USER_NAME
        output_key = f"{SERVICE_NAME}/infra/output"
        report_key = "report/infra-report.md"
        terraform_key = "terraform.tf"


        # S3에 Markdown 파일 업로드
        s3.put_object(
            Bucket=output_bucket,
            Key=f"{output_key}/{report_key}",
            Body=markdown_output.encode("utf-8"),
            ContentType="text/markdown"
        )
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }

    return {
        "Terraform": [
            {
                "s3": {
                    "bucket": {
                    "name": output_bucket
                    },
                    "object": {
                    "key": f"{output_key}/{terraform_key}"
                    }
                }
            }
        ],
        "Report": [
            {
                "s3": {
                    "bucket": {
                    "name": output_bucket
                    },
                    "object": {
                    "key": f"{output_key}/{report_key}"
                    }
                }
            }
        ],
        "message": "report 생성 완료"
    }