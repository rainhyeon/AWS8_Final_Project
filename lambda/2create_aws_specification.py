import boto3
import json
import re
import datetime
import pandas as pd
import io

def lambda_handler(event, context):
    s3 = boto3.client('s3')
    bedrock = boto3.client("bedrock-runtime", region_name="ap-northeast-2")

    # S3 업로드 정보 파싱
    bucket_name = event['Records'][0]['s3']['bucket']['name'] # {사용자명}
    object_key = event['Records'][0]['s3']['object']['key']   # 예시: "{프로젝트명}/infra/input/onprem.xlsx"
    projec_id = event['project_id']
    print(projec_id)

    # S3 경로 파싱
    parts = object_key.split('/')
    if len(parts) < 4:
        raise ValueError("object_key 형식 오류: {사용자명}/{프로젝트명}/infra/input/onprem.xlsx 형태여야 함")

    # SERVICE_NAME 추출
    SERVICE_NAME = parts[0]     # {프로젝트명}
    INFRA = parts[1]            # infra
    FLODER_NAME = parts[2]      # input
    FILE_NAME = parts[3]        # onprem.xlsx

    print("SERVICE_NAME:", SERVICE_NAME)
    print("FILE_NAME:", FILE_NAME)

    # S3에서 엑셀 바이너리로 읽기
    response = s3.get_object(Bucket=bucket_name, Key=object_key)
    binary_data = response['Body'].read()
    excel_io = io.BytesIO(binary_data)

    # pandas로 엑셀 파싱
    df = pd.read_excel(excel_io)

    # 엑셀의 내용을 문자열로 가공 (예시: csv 포맷)
    input_text = df.to_csv(index=False)

    # Claude에게 전달할 프롬프트
    prompt = f"""
You are an AWS Solution Architect and Infrastructure Modernization Specialist.
You are given a detailed on-premises infrastructure specification, including subnet roles, zones, server specs, NAT/firewall rules, and domain configuration.
Your task is to analyze this on-prem environment and produce a comprehensive AWS infrastructure migration specification document.
--- ON-PREMISES INPUT ---
{input_text}

### What to include in your output:
1. AWS Resource Summary Table
- List of AWS services required (e.g., VPC, Subnets, EC2, ALB, IGW, NAT Gateway, Route 53, ACM)
- Purpose of each service
- How it maps to on-prem components (subnet role, server zone)

2. Subnet and AZ Design Plan
- VPC CIDR and subnet breakdown (public/web/db):
- Set each subnet to two different az bands with reference to "서브넷 및 Zone/역할별 정보" Specific Information.
- public-1, public-2, web-1, web-2, db-1, db-2
- DB Subnet Path Table: Internet Access Inaccessible
- Which subnets will go to which AZs (e.g., ap-northeast-2a/c)  
- NAT gateway redundancy design  
- Route table structure for public/web/db

3. Server Mapping and Sizing Recommendation  
- EC2 instance type and RDS type per server (based on CPU/RAM/Disk)
- OS/AMI strategy
- Network interface placement and zone mapping

4. Security and Access Control Plan 
- Security group structure and flow: ALB → Web → DB
- Ingress rules and rationale
- Outbound in all security groups is allowed
- Match original firewall and ACL behavior on AWS

5. Domain, DNS, and Blue/Green (Weighted Routing) Plan
- The Route 53 hosted zone domain name must always be set to rainhyeon.store.
- Use AWS Route 53 for DNS management and ALB domain mapping.
- Clearly specify which application endpoints (e.g., `www`, `api` or root domain) will use Route 53 "weighted records" to enable canary or blue/green traffic shifts.
- For each such endpoint, describe:
    - How to define multiple DNS records (e.g., on-premises public IP, ALB) with "weight-based routing" (e.g., ALB weight 0, on-prem weight 255 for cutover start)
    - How to gradually shift user traffic from on-premises to AWS by adjusting Route53 weight values over time
    - That the ALB alias record should point to the ALB resource, and the on-premises A record should point to the provided "온프레미스 공인 IP" of {input_text}.
- Use of ACM certificate with DNS validation and wildcard SANs (e.g., `*.rainhyeon.store`)
- Use of ALB for HTTPS with ACM integration and validation dependencies

6. Domain and TLS (HTTPS) Plan
- Use of AWS Route 53 for DNS
- Use of ACM certificate with DNS validation
- Use of ALB for HTTPS with ACM integration and validation dependencies
- To protect the root domain with HTTPS,when ACM certificate is generated, domain_name is "DNS명", Specify subject_alternative_names in "wildcard" (ex. '*.rainhyon.store').

7. Benefits & Improvements Section  
- Explain how the AWS design improves scalability, availability, automation, and security
- Reference AWS best practices (e.g., multi-AZ NAT, SG rule separation, DNS-validated ACM)

8. Output Format  
- Structured, technical and easy-to-read document
- Use markdown headings, tables, and bullet points
- Do NOT include any Terraform code — this is an architecture planning document
- Audience: DevOps engineer, Cloud architect, or decision maker planning a migration

Your goal is to produce a production-quality infrastructure planning document for AWS migration.
"""

 # Bedrock API 요청 body (원하는 포맷)
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4096,
        "top_k": 250,
        "stop_sequences": [],
        "temperature": 0.3,
        "top_p": 0.3,
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

    # === [** 중요 **] inferenceProfileArn 사용 ===
    response = bedrock.invoke_model(
        modelId="anthropic.claude-3-haiku-20240307-v1:0",
        contentType="application/json",
        accept="application/json",
        body=json.dumps(body)
    )

    # Claude/Bedrock 응답 추출
    response_body = json.loads(response['body'].read().decode('utf-8'))
    aws_design_output = response_body['content'][0]['text']

    # 파일명(날짜+시간)
    now_str = datetime.datetime.now().strftime("%Y%m%d")
    file_name = f"{now_str}_aws_specification.txt"   # ✅ 규칙 적용

    # S3에 저장 (SERVICE_NAME 폴더 하위에)
    s3.put_object(
        Bucket='s3-terra-output-bucket',
        Key=f"{bucket_name}/{SERVICE_NAME}/{now_str}/{file_name}",            # ✅ 폴더 경로 포함
        Body=aws_design_output.encode('utf-8')
    )


    # Step Functions input용 반환값
    return {
        "Records": [
            {
                "s3": {
                    "bucket": {
                        "name": "s3-terra-output-bucket"
                    },
                    "object": {
                        "key": f"{bucket_name}/{SERVICE_NAME}/{now_str}/{file_name}"
                    }
                }
            }
        ]
    }