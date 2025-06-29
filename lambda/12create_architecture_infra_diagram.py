import boto3
import json
import os

def stream_to_string(body):
    # S3 get_object().Body는 StreamingBody 타입이므로 read() 필요
    return body.read().decode("utf-8")

def lambda_handler(event, context):
    # 1. S3 정보 파싱
    record = event["Records"][0]
    bucket_name = record["s3"]["bucket"]["name"]
    object_key = record["s3"]["object"]["key"]

    project_id = event["project_id"]

    # ex: USER_NAME/SERVICE_NAME/...
    try:
        USER_NAME, SERVICE_NAME = object_key.split("/")[:2]
    except Exception as e:
        print("ERROR: Invalid object key format:", object_key)
        return { "status": "error", "message": "object key 파싱 오류" }

    # 2. S3에서 terraform 코드 읽기
    s3 = boto3.client("s3")
    try:
        res = s3.get_object(Bucket=bucket_name, Key=object_key)
        terraform_code = stream_to_string(res["Body"])
    except Exception as e:
        print("ERROR: Failed to read from S3:", e)
        return { "status": "error", "message": "S3 읽기 오류" }

    # 3. Claude 3 Sonnet 프롬프트 생성
    prompt = f"""
You are an AWS architecture diagram generator.

Your job is to analyze the Terraform code below and create a clear, hierarchical AWS architecture diagram using Mermaid ("graph TD").  
Follow these rules:

- Only extract and show AWS resources and relationships that are actually defined in the Terraform code (e.g. VPC, subnets, ALB, EC2, RDS, Bastion Host, Route53, etc).  
  Do NOT include any resource or connection that is not explicitly present in the code.
- Use nested subgraph blocks to visually group resources:
    - Top level: AWS Cloud (or Region)
    - Inside AWS Cloud: VPC
    - Inside VPC: subnets (public, web, DB, etc)
    - Place resources (NAT Gateway, ALB, EC2, Server, bastion, db, RDS, etc) inside the correct subnet group.
- If there are two or more subnets of the same type, group them together in a single large box rather than drawing each separately.
- If an ALB (Application Load Balancer) is exposed to the internet, place it at the public boundary and connect it to the public subnets that are attached to it.
- Show only the key network flows as arrows between the main resources (e.g. User/Route53 → IGW → ALB → ASG → EC2 → RDS). Do not include minor flows.
- No node should have more than one incoming or outgoing edge; each node must be connected to at most one other node on each side.
- Do not draw any edge (arrow) without both a source and a target node.
- Draw the diagram vertically (top to bottom), not horizontally.
- For each resource node, add the Terraform resource name after a colon (e.g. EC2: web, RDS: prod_db).
- Hide trivial resources (e.g. security groups, IAM, EIP, etc), unless architecturally essential.
- Output only the Mermaid diagram, starting with 'graph TD'. Do not include any explanation, comments, or code block markers.

Here is an example of the required style (do not copy, just use as a visual template):
graph TD
  Route53["route 53"] --> IGW["internet gateway"]
  IGW --> ALB["ALB"]

  %% 왼쪽 AZ
  subgraph AZ1["AZ A"]
    subgraph Public_Subnet1["public subnet"]
      NAT1["nat gateway"]
      Bastion1["bastion"]
    end
    subgraph Web_Subnet1["web subnet"]
      Web1["web server"]
    end
    subgraph DB_Subnet1["db subnet"]
      RDS1["rds"]
    end
    Public_Subnet1 --> Web_Subnet1
    Web_Subnet1 --> DB_Subnet1
  end

  %% 오른쪽 AZ
  subgraph AZ2["AZ B"]
    subgraph Public_Subnet2["public subnet"]
      NAT2["nat gateway"]
    end
    subgraph Web_Subnet2["web subnet"]
      Web2["web server"]
    end
    subgraph DB_Subnet2["db subnet"]
      RDS2["rds"]
    end
    Public_Subnet2 --> Web_Subnet2
    Web_Subnet2 --> DB_Subnet2
  end

  ALB --> Public_Subnet1
  ALB --> Public_Subnet2

Here is the Terraform code to analyze and visualize:

{terraform_code}

"""

    # 4. Claude 3 Sonnet 호출 (AWS Bedrock)
    bedrock = boto3.client(
        service_name="bedrock-runtime",
        region_name="ap-northeast-2"
    )
    model_id = "apac.anthropic.claude-3-sonnet-20240229-v1:0"

    native_request = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1024,
        "temperature": 0,   # 원하는 값
        "top_p": 0,         # 필요시
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt}
                ],
            }
        ],
    }
    try:
        response = bedrock.invoke_model(
            modelId=model_id,
            body=json.dumps(native_request),
            accept="application/json",
            contentType="application/json"
        )
        body = response["body"].read().decode("utf-8")
        resp_json = json.loads(body)
        # 결과는 output.message.content[0].text
        diagram_text = resp_json["content"][0]["text"]
    except Exception as e:
        print("ERROR: Can't invoke Bedrock:", e)
        return { "status": "error", "message": str(e) }

    # 5. Mermaid 다이어그램을 S3에 저장 (.mmd, text/markdown)
    output_key = f"{SERVICE_NAME}/infra/output/diagram/infra_diagram.mmd"
    try:
        s3.put_object(
            Bucket=USER_NAME,
            Key=output_key,
            Body=diagram_text.strip(),
            ContentType="text/markdown"
        )
    except Exception as e:
        print("ERROR: Failed to upload to S3:", e)
        return { "status": "error", "message": "S3 저장 오류" }

    return {
        "Diagram": [
            {
                "s3": {
                    "bucket": {"name": USER_NAME},
                    "object": {"key": output_key}
                }
            }
        ],
        "project_id": project_id,
        "status": "diagram 생성 success"
    }
