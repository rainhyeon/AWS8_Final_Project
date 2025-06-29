import boto3
import os
import zipfile
from github import Github
from datetime import datetime
import json
import urllib.request
import requests
import shutil

def lambda_handler(event, context):
    # project_id
    project_id = event["project_id"]
    token = event["token"]

    # ------ Slack webhook url 받아오는 API 호출 ---------
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


    # ------ Github 정보, SSM 정보 받아오는 API 호출 ---------
    s3_info = event["Records"][0]["s3"]
    bucket = s3_info['bucket']['name']
    object_key = s3_info['object']['key']
    splits = object_key.split("/")
    USER_NAME = splits[0]
    SERVICE_NAME = splits[1]

    # --- 우리 계정 Secrets Manager에서 고객사 계정 접근용 키 가져오기 -------
    secret_name = f"{USER_NAME}_{SERVICE_NAME}_iam_user"    # Secret 이름
    region_name = "ap-northeast-2"

    try:
        my_sm = boto3.client('secretsmanager', region_name=region_name)
        secret = my_sm.get_secret_value(SecretId=secret_name)["SecretString"]
        secret_dict = json.loads(secret)
        access_key = secret_dict["access_key"]
        secret_key = secret_dict["secret_key"]
        print(f"고객사 계정용 access_key, secret_key 조회 성공")
    except Exception as e:
        print(f"[ERROR] 우리 계정 SecretsManager에서 고객사 access_key/secret_key 조회 실패: {e}")
        return {
            "project_id": project_id,
            "statusCode": 500,
            "message": "고객사 access_key/secret_key 조회 실패"
        }

    # --- 고객사 계정 Secrets Manager에서 github-token 값 가져오기 -------
    try:
        cust_sm = boto3.client(
            "secretsmanager",
            region_name=region_name,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )
        token_secret = cust_sm.get_secret_value(SecretId=f"{USER_NAME}_{SERVICE_NAME}_SM")["SecretString"]
        github_token = json.loads(token_secret)["github_token"]
        print("고객사 SecretsManager에서 github-token 조회 성공")
    except Exception as e:
        print(f"[ERROR] 고객사 계정의 SecretsManager에서 github-token 조회 실패: {e}")
        return {
            "project_id": project_id,
            "statusCode": 500,
            "message": "고객사 github-token 조회 실패"
        }

    # --- GitHub repo 정보 (repo명, branch명은 필요에 따라 event 등에서 받도록 수정 가능) ---
    # github_repo_name = "600gramSik/terraformTest" # 근식

    # 
    #github_repo_url = "https://github.com/rainhyeon/TerraCloudTest"
    #repo_path = github_repo_url.replace("https://github.com/", "")
    #print(repo_path)
    # branch = "main"
    
    # --- [1] GitHub repo 정보 받아오기 ---
    url = f"https://back.liftify.org/api/projects/git-info/{project_id}"
    headers = {
        "Authorization": f"Bearer {token}"
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        github_repo_url = data.get("repo_name")   # ex: "https://github.com/rainhyeon/TerraCloudTest"
        branch = data.get("branch_name", "main")  # 없으면 main 기본값
    except Exception as e:
        print(f"[ERROR] GitHub repo 정보 API 호출 실패: {e}")
        return {
            "project_id": project_id,
            "statusCode": 500,
            "message": "GitHub repo 정보 API 호출 실패"
        }

    print("받아온 github_repo_url:", github_repo_url)
    print("받아온 branch:", branch)

    # --- GitHub 연결 및 파일 업로드 ---
    try:
        g = Github(github_token)
        print(github_token)
        repo = g.get_repo(repo_path)
        # S3에서 파일 다운로드
        s3 = boto3.client("s3")
        local_tf_path = "/tmp/main.tf"
        s3.download_file(bucket, object_key, local_tf_path)

        extract_dir = "/tmp/tf-files"
        os.makedirs(extract_dir, exist_ok=True)
        shutil.copy(local_tf_path, os.path.join(extract_dir, "main.tf"))

        # GitHub에 파일 업로드 (존재하면 update, 없으면 create)
        for root, dirs, files in os.walk(extract_dir):
            for file in files:
                full_path = os.path.join(root, file)
                with open(full_path, "r") as f:
                    content = f.read()
                relative_path = os.path.relpath(full_path, extract_dir).replace("\\", "/")
                try:
                    existing_file = repo.get_contents(relative_path, ref=branch)
                    repo.update_file(
                        path=relative_path,
                        message=f"Update {relative_path} via Lambda at {datetime.utcnow().isoformat()}",
                        content=content,
                        sha=existing_file.sha,
                        branch=branch
                    )
                except Exception:
                    repo.create_file(
                        path=relative_path,
                        message=f"Create {relative_path} via Lambda at {datetime.utcnow().isoformat()}",
                        content=content,
                        branch=branch
                    )
        print("GitHub push 완료")
    except Exception as e:
        print(f"[ERROR] GitHub 업로드 실패: {e}")
        return {
            "project_id": project_id,
            "statusCode": 500,
            "message": "GitHub 업로드 실패"
        }

    # --- Slack 알림 전송 ---
    msg = {
        "text": f":white_check_mark: Github에 push 완료!\n*파일명*: `main.tf`\n<{github_repo_url} | Github에서 바로 가기>"
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

    return {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": bucket},
                    "object": {"key": object_key}
                }
            }
        ],
        "project_id": project_id,
        "statusCode": 200,
        "github_message": f"Terraform code pushed to GitHub repo {github_repo_url}",
        "slack_message": "Slack Alarm complete"
    }
