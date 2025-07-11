#[Authority 1] CloudTrail 로그가 저장된 S3 버킷에서 Athena Query를 통해 필요한 요소들만 추출해서 다시 S3로 저장
import boto3
import json
import os
import time

ATHENA_DATABASE = os.environ.get("ATHENA_DATABASE", "default")
ATHENA_TABLE = os.environ.get("ATHENA_TABLE", "cloudtrail_logs")
ACCOUNT_ID = os.environ.get("ACCOUNT_ID", "798172178824")

athena = boto3.client("athena")

def lambda_handler(event, context):
    print("📥 입력 이벤트:", json.dumps(event, indent=2, ensure_ascii=False))

    # ✅ Step Function으로부터 직접 전달되는 구조 대응
    if "body" in event:
        event = json.loads(event["body"])  # API Gateway나 첫 람다 결과를 string으로 받을 경우 파싱

    user_id = event["user_id"]
    project_id = event["project_id"]
    service_name = event["service_name"]
    step_id = event["step_id"]
    token = event["token"]
    log_bucket = event["log_bucket"]
    log_prefix = event["log_prefix"]  # 예: AWSLogs/798172178824/CloudTrail
    year = event["query_date"]["year"]
    month = event["query_date"]["month"]
    day = event["query_date"]["day"]

    regions = ['ap-northeast-2', 'us-east-1']
    result_path = f"s3://{log_bucket}/athena-results/{year}/{month}/{day}/"

    # ✅ 1. 파티션 추가
    for region in regions:
        location = f"s3://{log_bucket}/{log_prefix}/{region}/{year}/{month}/{day}/"
        partition_query = f"""
        ALTER TABLE {ATHENA_TABLE}
        ADD IF NOT EXISTS PARTITION (
          region='{region}',
          year='{year}',
          month='{month}',
          day='{day}'
        )
        LOCATION '{location}'
        """
        execute_athena_query(partition_query, result_path)
        print(f"✅ 파티션 추가 완료 for region: {region}")

    # ✅ 2. SELECT DISTINCT 쿼리
    query = f"""
    SELECT DISTINCT
      json_extract_scalar(rec, '$.eventSource') AS event_source,
      json_extract_scalar(rec, '$.eventName') AS event_name
    FROM {ATHENA_TABLE}
    CROSS JOIN UNNEST(CAST(json_extract(line, '$.Records') AS ARRAY<JSON>)) AS t(rec)
    WHERE year = '{year}'
      AND month = '{month}'
      AND day = '{day}'
      AND region IN ('ap-northeast-2', 'us-east-1')
      AND (
        json_extract_scalar(rec, '$.userIdentity.arn') LIKE 'arn:aws:sts::{ACCOUNT_ID}:assumed-role/terraform-terratest-codebuild-role%'
        OR json_extract_scalar(rec, '$.userAgent') LIKE '%Terraform%'
      )
    """
    execute_athena_query(query, result_path)
    print("✅ Athena SELECT DISTINCT 쿼리 완료:", result_path)

    return {
        "statusCode": 200,
        "project_id": project_id,
        "user_id": user_id,
        "step_id": step_id,
        "token": token,
        "log_bucket": log_bucket,
        "log_prefix": log_prefix,
        "service_name": service_name,
        "athena_output_path": result_path,
        "query_date": {
            "year": year,
            "month": month,
            "day": day
        }
    }

def execute_athena_query(query, output_path):
    response = athena.start_query_execution(
        QueryString=query,
        QueryExecutionContext={'Database': ATHENA_DATABASE},
        ResultConfiguration={'OutputLocation': f"{output_path}query-temp/"},
        WorkGroup='primary'
    )
    execution_id = response['QueryExecutionId']

    # 쿼리 완료까지 대기
    while True:
        result = athena.get_query_execution(QueryExecutionId=execution_id)
        state = result['QueryExecution']['Status']['State']
        if state in ['SUCCEEDED', 'FAILED', 'CANCELLED']:
            break
        time.sleep(2)

    if state != 'SUCCEEDED':
        raise Exception(f"Athena 쿼리 실패: {state}")
