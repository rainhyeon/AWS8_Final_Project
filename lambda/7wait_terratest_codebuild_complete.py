import boto3, json, os

s3 = boto3.client("s3")
stepfunctions = boto3.client("stepfunctions")

def lambda_handler(event, context):
    print("📥 입력 이벤트:", json.dumps(event, indent=2, ensure_ascii=False))

    # Case 1: EventBridge에서 직접 들어온 경우
    if "detail" in event:
        detail = event["detail"]
        build_id = detail["build-id"].split(":")[-1]
        logs_link = detail.get("logs", {}).get("deepLink", "")
    else:
        # Case 2: Step Function이 전달한 간단한 구조
        build_id = event["BuildId"]
        logs_link = event.get("logs_url", "")

    # S3에서 TaskToken 복원
    token_store_bucket = os.environ["TOKEN_S3_BUCKET"]
    token_key = f"task-token-store/terraform-terratest-codebuild:{build_id}.json"

    print("📌 추출된 build_id:", build_id)
    print("📌 추출된 bucket:", token_store_bucket)
    print("📌 조회할 S3 Key:", token_key)

    obj = s3.get_object(Bucket=token_store_bucket, Key=token_key)
    content = json.loads(obj["Body"].read())
    task_token = content["task_token"]
    original_input = content.get("input", {})

    build_status = event["detail"].get("build-status")
    if build_status not in ["SUCCEEDED"]:
        print("아직 빌드가 끝난 상태가 아님, 콜백 안함")
        return
    
    stepfunctions.send_task_success(
        taskToken=task_token,
        output=json.dumps({
            "build_id": build_id,
            "build_status": build_status,
            **original_input
        })
    )

    return {"message": "✅ Step Function 성공 처리 완료"}
