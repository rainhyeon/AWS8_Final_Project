#[Authority 2] 최소 권한 추출
import boto3
import os
import json
import csv
import io
import requests
import urllib.request

s3 = boto3.client("s3")
sts = boto3.client("sts")


def lambda_handler(event, context):
    print("입력 이벤트:", json.dumps(event, indent=2, ensure_ascii=False))
    # Step Functions → body가 문자열일 수도, dict일 수도, 아예 없을 수도 있음
    if "body" in event:
        if isinstance(event["body"], str):
            event = json.loads(event["body"])
        elif isinstance(event["body"], dict):
            event = event["body"]

    # 여기부터는 event가 JSON 객체라고 확정
    if "user_id" not in event:
        raise ValueError("❌ user_id가 포함된 이벤트가 아닙니다")
    
    if "service_name" not in event:
        raise ValueError("❌ service_name 포함된 이벤트가 아닙니다")

    user_id = event["user_id"]
    project_id = event["project_id"]
    token = event["token"]
    step_id = event["step_id"]
    service_name = event["service_name"]
    s3_path = event["athena_output_path"]
    year = event["query_date"]["year"]
    month = event["query_date"]["month"]
    day = event["query_date"]["day"]
    account_id = os.environ.get("ACCOUNT_ID", sts.get_caller_identity()["Account"])

    bucket, prefix = extract_bucket_and_prefix(s3_path)

    search_prefix = prefix.rstrip("/") + "/query-temp/"
    athena_files  = list_athena_results(bucket, search_prefix)
    if not athena_files:
        raise Exception("Athena 결과 파일을 찾을 수 없습니다.")

    actions = set()
    for key in athena_files:
        content = read_csv_from_s3(bucket, key)
        for row in content:
            src = row.get("event_source")
            name = row.get("event_name")
            if src and name:
                service = src.split(".")[0]
                actions.add(f"{service}:{name}")

    MANDATORY_ACTIONS = {
        "ec2:CreateTags", 
        "cloudwatch:PutDashboard", 
        "ec2:DescribeInstanceStatus", 
        "secretsmanager:GetSecretValue", 
        "redshift-serverless:ListWorkgroups", 
        "redshift-serverless:ListNamespaces",
        "docdb-elastic:ListClusters",
        "redshift:DescribeClusters",
        "elasticloadbalancing:AddTags",
        "rds:AddTagsToResource",
        "acm:AddTagsToCertificate",
        "iam:TagRole",
        "iam:TagInstanceProfile",
        "iam:PassRole",
        "elasticloadbalancing:DescribeTargetHealth",
        "ec2:CreateNetworkInterface",
        "ec2:DeleteNetworkInterface",
        "ec2:DescribeAvailabilityZones",
        "ec2:DescribeDhcpOptions",
        "ec2:DescribeInternetGateways",
        "ec2:DescribeNetworkInterfaces",
        "ec2:DescribeSecurityGroups",
        "ec2:DescribeSubnets",
        "ec2:DescribeVpcs",
        "ec2:ModifyNetworkInterfaceAttribute",
        "dms:*",
        "iam:CreateRole",
        "iam:PutRolePolicy",
        "iam:AttachRolePolicy"
    }
    raw_actions = actions.copy()  # 원본 유지
    actions.update(MANDATORY_ACTIONS)

    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": sorted(list(actions)),
                "Resource": "*"
            }
        ]
    }
    
    
    # policy 내용 s3에 저장
    s3.put_object(
        Bucket=user_id,
        Key=f"{service_name}/infra/output/policy/iam_policy.json",
        Body=json.dumps(policy, indent=2)
    )

    print("terraform 코드 & 최소 권한 추출 완료")

    
    # ------ Slack webhook url 받아오는 backend API 호출 ---------
    url = f"https://back.liftify.org/api/projects/{project_id}/slack/"
    headers = {
        "Authorization": f"Bearer {token}"
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        webhook_url = data.get("slack_webhook_url")
        print(f"슬랙 Webhook URL: {webhook_url}")
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] 요청 실패: {e}")
        return {
           "project_id": project_id,
            "statusCode": 500,
            "message": "Slack webhook URL 요청 실패"
        }
    except ValueError as e:
        print(f"[ERROR] 응답값 이상: {e}")
        return {
            "project_id": project_id,
            "statusCode": 500,
            "message": "Slack webhook URL 응답값 이상"
        }
    except Exception as e:
        print(f"[ERROR] 알 수 없는 에러: {e}")
        return {
            "project_id": project_id,
            "statusCode": 500,
            "message": "Slack webhook URL 알 수 없는 에러"
        }

    if not webhook_url:
        print("슬랙 Webhook URL 조회 실패")
        return {
            "project_id": project_id,
            "statusCode": 500,
            "message": "Slack webhook URL 조회 실패"
        }

    # --- Slack 알림 전송 ---
    msg = {
        "text": f":white_check_mark: *Terraform 코드와 IAM Role 최소 권한 추출 완료!* \nLiftify의 프로젝트에서 확인해주세요."
    }
    try:
        req = urllib.request.Request(
            webhook_url,
            data=json.dumps(msg).encode("utf-8"),
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req) as response:
            _ = response.read()
        print("Slack 메시지 전송 성공")
    except Exception as e:
        print(f"[ERROR] Slack 메시지 전송 실패: {e}")


    
    # ------------백엔드에 terraform 코드 & 최소 권한 추출 완료 API 전송 ------------
    try:
        # 정상 처리
        data = {
            "project_id": project_id,
            "phase": "infra",
            "status": "SUCCEEDED",
            "error_message": None,
            "step_id": step_id    
        }
        url = f"https://back.liftify.org/api/projects/{project_id}/step-function-result/"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        response = requests.post(url, json=data, headers=headers)
        response.raise_for_status()  # 요청 자체가 실패했을 때 예외 발생시킴
        print("SUCCESS: 백엔드 terraform 코드 & 최소 권한 전송")
    except Exception as e:
        # 에러 발생 시
        error_data = {
            "project_id": project_id,
            "phase": "infra",
            "status": "FAILED",
            "error_message": str(e),
            "step_id": step_id
        }
        url = f"https://back.liftify.org/api/projects/{project_id}/step-function-result/"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        # 에러 내용 전송
        requests.post(url, json=error_data, headers=headers)
        print("백엔드 terraform 코드 & 최소 권한 전송 실패:", e)
        return {
            "statusCode": e,
            "message": "백엔드 terraform 코드 & 최소 권한 전송 실패"
        }

    



# --- 🔧 Helper Functions ---
def extract_bucket_and_prefix(s3_uri):
    assert s3_uri.startswith("s3://")
    parts = s3_uri.replace("s3://", "").split("/", 1)
    bucket = parts[0]
    prefix = parts[1] + "/" if len(parts) > 1 else ""
    return bucket, prefix

def list_athena_results(bucket, prefix):
    response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
    return [
        obj["Key"]
        for obj in response.get("Contents", [])
        if obj["Key"].endswith(".csv")
    ]

def read_csv_from_s3(bucket, key):
    obj = s3.get_object(Bucket=bucket, Key=key)
    body = obj["Body"].read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(body))
    return list(reader)
