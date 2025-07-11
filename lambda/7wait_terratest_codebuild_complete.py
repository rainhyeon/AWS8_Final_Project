import boto3    # AWS 리소스(서비스)를 제어하기 위한 AWS 공식 Python 라이브러리
import json     # JSON 데이터 처리를 위한 파이썬 표준 라이브러리
import os       # 환경변수 및 파일 경로 작업용 파이썬 표준 라이브러리

# S3와 Step Functions에 접근할 수 있는 boto3 클라이언트 객체 생성
s3 = boto3.client("s3")
stepfunctions = boto3.client("stepfunctions")

def lambda_handler(event, context):
    # 함수가 호출될 때 넘어오는 이벤트 내용을 로그로 출력 (트러블슈팅에 매우 중요!)
    print("📥 입력 이벤트:", json.dumps(event, indent=2, ensure_ascii=False))

    # EventBridge(빌드 상태 변경 알림)로부터 호출된 경우: event에 "detail" 키가 있음
    if "detail" in event:
        detail = event["detail"]
        # CodeBuild 빌드 작업의 고유 ID 추출 (앞에 prefix가 있을 수 있으므로 맨 뒤값 사용)
        build_id = detail["build-id"].split(":")[-1]
        # 빌드의 상태값 추출 ("SUCCEEDED", "FAILED", "STOPPED" 등)
        build_status = detail.get("build-status")
        # CodeBuild의 빌드 로그(CloudWatch Log 링크)
        logs_link = detail.get("logs", {}).get("deepLink", "")
    else:
        # Step Function이 단순하게 콜백하는 경우 (디버깅 등): 별도 키로 접근
        build_id = event.get("BuildId") or event.get("build_id")
        build_status = event.get("build_status")
        logs_link = event.get("logs_url", "")

    # Step Function의 TaskToken을 저장한 S3 버킷명 (환경변수로 세팅되어야 함)
    token_store_bucket = os.environ["TOKEN_S3_BUCKET"]
    # S3에서 TaskToken을 저장한 파일의 경로 (빌드 ID 기반)
    token_key = f"task-token-store/terraform-terratest-codebuild:{build_id}.json"

    print("📌 추출된 build_id:", build_id)
    print("📌 추출된 bucket:", token_store_bucket)
    print("📌 조회할 S3 Key:", token_key)

    # (1) S3에서 해당 TaskToken 파일을 다운로드하여, 파일 내용을 파싱(복원)
    obj = s3.get_object(Bucket=token_store_bucket, Key=token_key)
    content = json.loads(obj["Body"].read())
    # Step Function에서 사용할 TaskToken (이 값이 있어야 콜백 가능!)
    task_token = content["task_token"]
    # Step Function의 원본 입력(Records, retry_count 등, 재시도 로직에 필요)
    # Step Function의 원본 입력(Records, retry_count 등, 재시도 로직에 필요)
    original_input = content.get("input", {})

    print("📦 원본 input:", original_input)

    # 각 항목을 개별 변수로 추출
    retry_count = original_input.get("RetryCount", 0)
    project_id = original_input.get("project_id")
    step_id = original_input.get("step_id")
    token = original_input.get("token")
    records = original_input.get("Records")

    # 확인용 로그
    print("RetryCount:", retry_count)
    print("project_id:", project_id)
    print("step_id:", step_id)
    print("token:", token)
    print("Records:", json.dumps(records, indent=2))

    # (2) 빌드가 아직 진행 중인 상태라면 아무 작업도 하지 않고 종료
    if build_status not in ["SUCCEEDED", "STOPPED", "FAILED"]:
        print("아직 빌드가 끝난 상태가 아님, 콜백 안함")
        return

    # (3) Step Function으로 반환할 payload 구성
    output_payload = {
        "build_id": build_id,
        "build_status": build_status,
        "logs_url": logs_link,
        **original_input,  # ✅ 원본 그대로 펼침 (RetryCount 포함됨)
        "RetryCount": retry_count,
        "project_id": project_id,
        "step_id": step_id,
        "token": token,
        "Records": records
    }


    # (4) Step Function에 콜백!
    #  - 성공/실패 구분 없이 모두 send_task_success로 보냄
    #    (분기 처리는 Step Function의 Choice 상태에서 수행)
    if build_status == "SUCCEEDED":
        # 빌드가 정상적으로 완료된 경우
        stepfunctions.send_task_success(
            taskToken=task_token,
            output=json.dumps(output_payload)
        )
        print("✅ Step Function 성공 처리 완료")
    else:
        # 빌드가 실패(FAILED) 또는 중단(STOPPED)된 경우
        # 여기서도 일단 send_task_success로 보내야 Step Function에서 재시도 분기가 가능함
        stepfunctions.send_task_success(
            taskToken=task_token,
            output=json.dumps(output_payload)
        )
        print("⚠️ Step Function 실패/중단 처리 완료")

    # 함수 결과 리턴 (로그 목적)
    return {
        "message": "✅ Step Function 콜백 처리 완료",
        "build_id": build_id,
        "build_status": build_status,
        **original_input,
        "RetryCount": retry_count,
        "project_id": project_id,
        "step_id": step_id,
        "token": token,
        "Records": Records
    }
