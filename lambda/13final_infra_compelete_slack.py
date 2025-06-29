import os
import json
import urllib.request

def lambda_handler(event, context):
    webhook_url = os.environ['SLACK_WEBHOOK_URL']

    if isinstance(event, str):
        event = json.loads(event)
    # event가 list 형태일 때 분리
    if isinstance(event, list):
        report_part = event[0]
        diagram_part = event[1]
    else:
        report_part = event
        diagram_part = {}

    # Terraform
    terraform_record = report_part["Terraform"][0]
    terraform_bucket = terraform_record["s3"]["bucket"]["name"]
    terraform_key = terraform_record["s3"]["object"]["key"]

    # Report
    report_record = report_part["Report"][0]
    report_bucket = report_record["s3"]["bucket"]["name"]
    report_key = report_record["s3"]["object"]["key"]

    # Diagram
    diagram_record = diagram_part["Diagram"][0]
    diagram_bucket = diagram_record["s3"]["bucket"]["name"]
    diagram_key = diagram_record["s3"]["object"]["key"]
    
    # 👉 project_id는 diagram_part에서 추출해야 함!
    project_id = diagram_part["project_id"]
    #project_id = 1

    # 예시로 Terraform만 Slack 메시지 보냄 (필요에 따라 아래 부분 반복해서 사용)
    msg = {
        "text": f":report 생성 완료"
    }
    req = urllib.request.Request(
        webhook_url,
        data=json.dumps(msg).encode("utf-8"),
        headers={'Content-Type': 'application/json'}
    )
    try:
        with urllib.request.urlopen(req) as response:
            _ = response.read()
        print("Slack 메시지 전송 성공")
    except Exception as e:
        print("Slack 메시지 전송 실패:", e)
        error_message = e
    # 필요하면 Report, Diagram도 똑같이 아래처럼 추가로 메시지 전송
    # (코드 복사해서 report_bucket, report_key, ... 식으로 사용)

    # ---- 백엔드로 전달할 값-----
    import requests

    try:
        # 정상 처리
        data = {
            "project_id": project_id,
            "phase": "infra",
            "status": "SUCCEEDED",
            "error_message": None
        }
        url = f"https://back.liftify.org/api/projects/{project_id}/step-function-result/"
        headers = {"Content-Type": "application/json"}
        response = requests.post(url, json=data, headers=headers)
        response.raise_for_status()  # 요청 자체가 실패했을 때 예외 발생시킴
        print("백엔드 infra result 요청 성공")
    except Exception as e:
        # 에러 발생 시
        error_data = {
            "project_id": project_id,
            "phase": "infra",
            "status": "FAILED",
            "error_message": str(e)
        }
        url = f"https://back.liftify.org/api/projects/{project_id}/step-function-result/"
        headers = {"Content-Type": "application/json"}
        # 에러 내용 전송
        requests.post(url, json=error_data, headers=headers)
        print("백엔드 infra result 요청 실패:", e)
    return {
        "status": "SUCCESS"
    }
    


