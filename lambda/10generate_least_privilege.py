import boto3
import os
import json
import csv
import io

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

    MANDATORY_ACTIONS = {"ec2:CreateTags", "cloudwatch:PutDashboard", "ec2:DescribeInstanceStatus", "secretsmanager:GetSecretValue"}
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

    return {
        "statusCode": 200,
        "Records": [
            {
                "s3": {
                    "bucket": {
                        "name": "terraform-artifacts-bucket-12"
                    },
                    "object": {
                        "key": f"{user_id}/{service_name}/{year}{month}{day}/infra-terraform-invalidation/terraform.tf"
                    }
                }
            }
        ],
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({
            "user_id": user_id,
            "iam_policy": policy
        })
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
