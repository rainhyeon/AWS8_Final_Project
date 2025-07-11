import boto3
import json
import re
import datetime
from botocore.config import Config

def lambda_handler(event, context):
    s3 = boto3.client('s3')
    bedrock_config = Config(
        read_timeout=120,  # 최대 120초까지 기다리게 설정
        connect_timeout=10,
        retries={"max_attempts": 3}
    )
    bedrock = boto3.client("bedrock-runtime", region_name="ap-northeast-2", config=bedrock_config)

    # S3 업로드 정보 파싱 (Step Functions에서 받은 인풋 그대로 사용)
    bucket_name = event['Records'][0]['s3']['bucket']['name']
    object_key = event['Records'][0]['s3']['object']['key']  
    # 예: 'onprem-to-aws-input/shoppingmall/20240605-130055_aws_specification.txt'

    # S3 경로 파싱
    parts = object_key.split('/')
    if len(parts) < 4:
        raise ValueError("object_key 형식 오류: {bucket_name}/{SERVICE_NAME}/{now_str}/{file_name} 형태여야 함")

    # (참고: 첫 번째 parts[0]는 원래 업로드에 사용한 bucket_name)
    parsed_bucket = parts[0]             # "onprem-to-aws-input"
    SERVICE_NAME = parts[1]              # "shoppingmall"
    FILE_NAME = parts[3]                 # "20240605-130055_aws_specification.txt"

    print("bucket_name (from event):", bucket_name)
    print("parsed_bucket (from key):", parsed_bucket)
    print("SERVICE_NAME:", SERVICE_NAME)
    print("FILE_NAME:", FILE_NAME)

    # S3에서 명세서 파일 읽기
    response = s3.get_object(Bucket=bucket_name, Key=object_key)
    input_text = response['Body'].read().decode('utf-8')

    default_dms_iam_role = """
resource "aws_iam_role" "dms_vpc_role" {
  name = "dms-vpc-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "dms.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = {
    Name = "dms-vpc-role"
  }
}

resource "aws_iam_policy" "dms_vpc_custom_policy" {
  name        = "dms-vpc-custom-policy"
  description = "Allow DMS to manage EC2 network interfaces"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ec2:Describe*",
          "ec2:CreateNetworkInterface",
          "ec2:DeleteNetworkInterface",
          "ec2:AttachNetworkInterface"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "dms_vpc_custom_attach" {
  role       = aws_iam_role.dms_vpc_role.name
  policy_arn = aws_iam_policy.dms_vpc_custom_policy.arn
}

resource "aws_iam_role" "dms_assessment_role" {
  name = "DMSAssessmentRole"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect    = "Allow",
      Principal = { Service = "dms.amazonaws.com" },
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_policy" "dms_assessment_policy" {
  name = "DMSAssessmentPolicy"

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = ["s3:*"],
        Resource = ["arn:aws:s3:::liftify-assessment-*", "arn:aws:s3:::liftify-assessment-*/*"]
      },
      {
        Effect = "Allow",
        Action = ["dms:*"],
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "attach" {
  role       = aws_iam_role.dms_assessment_role.name
  policy_arn = aws_iam_policy.dms_assessment_policy.arn
}
"""
    example_route53_record_code = """
resource "aws_route53_record" "Cafe_Management_www_onprem" {
  zone_id = aws_route53_zone.Cafe_Management_zone_1.zone_id
  name    = "www.${var.domain_name}"
  type    = "A"
  ttl     = 300
  records = ["34.22.91.176"]

  weighted_routing_policy {
    weight = 225
  }

  set_identifier = "www-onprem-weight-225"
}

resource "aws_route53_record" "Cafe_Management_www_alb" {
  zone_id = aws_route53_zone.Cafe_Management_zone_1.zone_id
  name    = "www.${var.domain_name}"
  type    = "A"

  alias {
    name                   = aws_lb.Cafe_Management_alb_1.dns_name
    zone_id                = aws_lb.Cafe_Management_alb_1.zone_id
    evaluate_target_health = true
  }

  weighted_routing_policy {
    weight = 0
  }

  set_identifier = "www-alb-weight-0"
}
"""

    # Claude 프롬프트(명세서를 Terraform 코드로 바꿔달라고 요청)
    prompt = f"""
You are a professional Terraform architect.

You are given a detailed AWS infrastructure specification.

Your task is to generate production-ready Terraform code using valid and recommended Terraform HCL syntax only.

Use AWS provider version = "~> 6.0" when generating the Terraform code.

--- AWS INFRASTRUCTURE SPECIFICATION ---
{input_text}
---------------------------------------

### Requirements:

1. Code Structure
- Split each logical component into separate `.tf` blocks (e.g., `variables.tf`, `vpc.tf`, `subnet.tf`, `security_groups.tf`, `alb.tf`, `ec2.tf`, `iam.tf`, `rds.tf`, `outputs.tf`)
- Use only Terraform native syntax, no comments or explanations
- Code must be directly executable with `terraform apply`
- Output each file in this format:

// Filename: terraform.tf
```
<Terraform code block>
```
Only output code blocks for .tf files. No extra explanation or text.

2. Required variables
Always create a file named variables.tf.
In variables.tf, you must include the following variables exactly as written below, with no changes:
- A variable named region with the the description "region" the default "ap-northeast-2".
- A variable named db_name with the description "DB name" the default "{SERVICE_NAME}_db".
- A variable named db_username with the description "master user" the default "admin".
- A variable named db_password with the description "master password" and with sensitive = true and the default "password".
- A variable named domain_name with the description "Domain name" and the default "bboaws.shop".

Do not modify the variable names, descriptions, or default values.
These variables must always be present in every variables.tf you generate.

3. Create TWO `aws_route53_record` resources with two columns in {input_text}:
- "서브도메인(record)": subdomain (e.g., www, api, test)
- "온프레미스 공인 IP": onprem_ip

For the domain "bboaws.shop", perform the following for each row in the table:
--- EXAMPLE ROUTE53 RECORD CODE START ---
{example_route53_record_code}
--- EXAMPLE ROUTE53 RECORD CODE START ---

For each value in the "record" column (call it "subdomain") and its matching "온프레미스 공인 IP" (call it "onprem_ip"):
- (a) Create a Route53 resource "A" record for the subdomain "subdomain.bboaws.shop" with:
    - `records = ["onprem_ip"]`
    - `weighted_routing_policy {{ weight = 225 }}`
    - `set_identifier = "subdomain-onprem-weight-225"`
    - `type = "A"`
    - `zone_id = aws_route53_zone.this.zone_id`
     - `ttl = 300`
- (b) Create a second "A" record for the same subdomain ("subdomain.bboaws.shop"), but as an alias to the ALB, with:
    - `alias name = aws_lb.this.dns_name, zone_id = aws_lb.this.zone_id, evaluate_target_health = true`
    - `weighted_routing_policy {{ weight = 0 }}`
    - `set_identifier = "subdomain-alb-weight-0"`
    - `type = "A"`
    - `zone_id = aws_route53_zone.this.zone_id`
This means: for every row, you must output exactly TWO aws_route53_record resources, one with an explicit records value and one with an alias block, both using the same subdomain.**
- Do not merge or collapse these resources into one. There must always be two Route53 records per subdomain.
- The hosted zone must always be created as a resource using the domain_name variable, never data lookup.
- "aws_route53_record" resource name must start with {SERVICE_NAME}.
- Update the `health_check` path of `aws_lb_target_group` to "health check 경로" based on the {input_text}.

4. Key Design Constraints
- Never import resources dynamically with data. create your own.
- Create a VPC with DNS support
- Design subnets by role (public, web/app, db), across two AZs
- When creating a public subnet, include:
- "map_public_ip_on_launch = true"
- "enable_resource_name_dns_a_record_on_launch = true"
- "depends_on = [aws_internet_gateway.this]"
- When creating a private subnet, include:
- "enable_resource_name_dns_a_record_on_launch = true"
- The db routing table does not route the natgateway.
- Assign NAT Gateways (1 per AZ) and associated Elastic IPs
- All created nat gateways are assigned to different subnets.
- Create an ALB with TLS termination using ACM and Route53 DNS validation.
- Do not generate dynamically with "aws_ami data".
- If it is linux in "OS and AMI Strategy", assign "ami-0c593c3690c32e925" to "ami-08943a151bd468f4e" directly to ami_id in the instance.
- All web server instances must use the same AMI.
- Never use the "user_data" or "user_data_base64" argument in any aws_instance resource for web servers.
- Attach proper IAM Role and Instance Profile for SSM access
- Define all security groups with inline ingress/egress blocks
- Please write the Terraform code in a way that avoids cycle (circular dependency) errors between aws_security_group.db, aws_security_group.web, and aws_security_group.alb.
- Ensure ALB listeners wait for ACM certificate validation
- Set up Route53 records for ACM validation and ALB access
- Use wildcard SANs for ACM (`*.example.com`)

5. RDS Timezone Configuration  
- If you generate an `aws_db_instance` resource, you must configure the timezone as `Asia/Seoul`.  
  - For MySQL, MariaDB, and PostgreSQL, set the timezone by attaching a `aws_db_parameter_group` with the appropriate timezone parameter.  
  - For SQL Server, set the `timezone` argument in the resource block directly.
- `Identifier` for `aws_db_instance` is set to {SERVICE_NAME}_db

6. Default IAM Code
In every generated Terraform code, always include the following IAM roles and policies exactly as written. Do not modify or skip.

--- DEFAULT IAM CODE START ---
{default_dms_iam_role}
--- DEFAULT IAM CODE END ---

7. Resource Naming Rules
- For every resource, set the Terraform local name and its tags["Name"] value to be identical, following the format: "{SERVICE_NAME}_resource_type".
- Never change domain name and {SERVICE_NAME}.

8. Output Rules
- Output one code block per file
- Use `for_each` where applicable (e.g., Route53 CNAME records)
- Avoid placeholders — use realistic values or derive them from input

Your goal is to produce complete, deployable Terraform code for the given infrastructure.

"""

    # Bedrock API 요청 body
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 9500,
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

    # Claude 3 Haiku로 호출 (on-demand)
    response = bedrock.invoke_model(
        modelId="apac.anthropic.claude-sonnet-4-20250514-v1:0",
        contentType="application/json",
        accept="application/json",
        body=json.dumps(body)
    )

    # Claude 응답 추출
    response_body = json.loads(response['body'].read().decode('utf-8'))
    output_text = response_body['content'][0]['text']

    print("===== Claude 응답 원문 =====")
    print(output_text)

    # 코드 블록 추출
    tf_blocks = re.findall(
    r"// Filename: (.+?\.tf)\n```(?:hcl)?\n([\s\S]*?)```", output_text
    )
    
    # 모든 코드 합치기 (코드 내용만)
    combined_code = ""
    for filename, code in tf_blocks:
        combined_code += f"// Filename: {filename.strip()}\n{code.strip()}\n\n"

    # 파일명(폴더/파일) 결정
    output_bucket = "s3-terraform-12"
    now_str = datetime.datetime.now().strftime("%Y%m%d")
    key = f"{parsed_bucket}/{SERVICE_NAME}/{now_str}/terraform.tf"   # ex) 20240605-140501/combined_output.tf

    # S3에 저장 (하나의 파일로)
    s3 = boto3.client('s3')
    s3.put_object(
        Bucket=output_bucket,
        Key=key,
        Body=combined_code.encode("utf-8")
        #Body=output_text.encode("utf-8")
    )

    # 2. buildspec.yml S3에서 읽어서 같이 저장!
    src_buildspec_key = "buildspec.yml"  # 원본 위치
    dst_buildspec_key = f"{parsed_bucket}/{SERVICE_NAME}/{now_str}/{src_buildspec_key}"  # .tf 파일과 같은 prefix로 저장

    buildspec_content = """
    version: 0.2

    phases:
        pre_build:
            commands:
            - echo "Copying tf files from s3://$S3_BUCKET/$S3_PREFIX"
            - aws s3 cp s3://$S3_BUCKET/$S3_PREFIX ./ --recursive --exclude "*" --include "*.tf"

        build:
            commands:
            - echo "---------- terraform init --------------" > error.log
            - terraform init >> error.log 2>&1 || true
            - echo "---------- terraform validate --------------" >> error.log
            - terraform validate >> error.log 2>&1 || true
            - echo "---------- tflint --------------" >> error.log
            - tflint >> error.log 2>&1 || true
            - echo "---------- terraform plan --------------" >> error.log
            - terraform plan -out=plan.out >> error.log 2>&1 || true
            - echo "========== error.log =========="
            - cat error.log

    artifacts:
        files:
            - error.log
            - "*.tf"
    """

    # ✅ S3에 저장
    s3.put_object(
        Bucket=output_bucket,
        Key=dst_buildspec_key,
        Body=buildspec_content.encode('utf-8'),
        ContentType='text/plain'
    )

    print(f"✅ buildspec.yml 파일 저장 완료 → s3://{output_bucket}/{key}")

    return {
        "Records": [
            {
                "s3": {
                    "bucket": {
                        "name": "s3-terraform-12"
                    },
                    "object": {
                        "key": f"{parsed_bucket}/{SERVICE_NAME}/{now_str}/terraform.tf"
                    }
                }
            },
            {
                "s3": {
                    "bucket": {
                        "name": "s3-terraform-12"
                    },
                    "object": {
                        "key": f"{parsed_bucket}/{SERVICE_NAME}/{now_str}/buildspec.yml"
                    }
                }
            }
        ]
    }
