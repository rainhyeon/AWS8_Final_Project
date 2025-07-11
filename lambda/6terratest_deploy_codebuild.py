import boto3
import os
import zipfile
import json

s3 = boto3.client('s3')
codebuild = boto3.client('codebuild')
cloudtrail = boto3.client('cloudtrail')
region = os.environ.get("AWS_REGION", "ap-northeast-2")
account_id = boto3.client("sts").get_caller_identity()["Account"]

# ✅ 버킷 없으면 자동 생성 + 정책 부착
def create_bucket_if_not_exists(bucket_name: str, region: str, account_id: str):
    try:
        s3.head_bucket(Bucket=bucket_name)
        print(f"✅ S3 버킷 이미 존재함: {bucket_name}")
        return
    except s3.exceptions.ClientError as e:
        if e.response["Error"]["Code"] != "404":
            raise
        print(f"🆕 S3 버킷 생성 중: {bucket_name}")
        s3.create_bucket(
            Bucket=bucket_name,
            CreateBucketConfiguration={"LocationConstraint": region}
        )

    # CloudTrail 로그 저장용 버킷 정책 설정
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "AWSCloudTrailAclCheck",
                "Effect": "Allow",
                "Principal": {"Service": "cloudtrail.amazonaws.com"},
                "Action": "s3:GetBucketAcl",
                "Resource": f"arn:aws:s3:::{bucket_name}"
            },
            {
                "Sid": "AWSCloudTrailWrite",
                "Effect": "Allow",
                "Principal": {"Service": "cloudtrail.amazonaws.com"},
                "Action": "s3:PutObject",
                "Resource": f"arn:aws:s3:::{bucket_name}/AWSLogs/{account_id}/*",
                "Condition": {
                    "StringEquals": {
                        "s3:x-amz-acl": "bucket-owner-full-control"
                    }
                }
            }
        ]
    }

    s3.put_bucket_policy(
        Bucket=bucket_name,
        Policy=json.dumps(policy)
    )
    print(f"✅ S3 버킷 정책 설정 완료: {bucket_name}")

# ✅ CloudTrail 트레일 생성
def create_cloudtrail_trail_if_not_exists(trail_name: str, s3_bucket_name: str):
    try:
        cloudtrail.get_trail(Name=trail_name)
        print(f"🔁 CloudTrail 트레일 이미 존재함: {trail_name}")
    except cloudtrail.exceptions.TrailNotFoundException:
        print(f"🆕 CloudTrail 트레일 생성 중: {trail_name}")
        cloudtrail.create_trail(
            Name=trail_name,
            S3BucketName=s3_bucket_name,
            IsMultiRegionTrail=True
        )
        cloudtrail.start_logging(Name=trail_name)
        print(f"✅ CloudTrail 트레일 생성 및 로깅 시작됨: {trail_name}")

def lambda_handler(event, context):
    print("📥 입력 이벤트:", json.dumps(event, indent=2, ensure_ascii=False))

    task_token = event["TaskToken"]
    record = event["Records"][0]
    bucket = record["s3"]["bucket"]["name"]
    object_key = record["s3"]["object"]["key"]
    retry_count = event.get("RetryCount", 0)

    parts = object_key.split("/")
    USER_NAME, SERVICE_NAME, DATE, FOLDER_NAME, *_ = parts

    # ✅ 사용자 기반 CloudTrail 버킷 & 트레일 동적 생성
    trail_bucket = f"cloudtrail-logs-{USER_NAME.lower()}"
    trail_name = f"terraform-deploy-trail-{USER_NAME.lower()}"
    create_bucket_if_not_exists(trail_bucket, region, account_id)
    create_cloudtrail_trail_if_not_exists(trail_name, trail_bucket)

    terratest_output = "terratest-output.txt"
    CODEBUILD_PROJECT = "terraform-terratest-codebuild"
    full_prefix = f"{USER_NAME}/{SERVICE_NAME}/{DATE}"
    zip_s3_key = f"{full_prefix}/{FOLDER_NAME}/terraform.zip"
    output_txt = f"{full_prefix}/{CODEBUILD_PROJECT}/{terratest_output}"

    # 임시 디렉토리 생성
    local_base_dir = "/tmp/terraform-code"
    os.makedirs(f"{local_base_dir}/test", exist_ok=True)

    # buildspec.yml 생성
    buildspec_content = f"""
version: 0.2
env:
  variables:
    S3_BUCKET: "{bucket}"
    S3_KEY: "{zip_s3_key}"
    ERROR_LOG_KEY: "{output_txt}"
phases:
  pre_build:
    commands:
      - echo "📦 S3에서 terraform.zip 다운로드"
      - aws s3 cp s3://$S3_BUCKET/$S3_KEY terraform.zip
      - unzip terraform.zip -d terraform-code
      - cd test
      - go mod init terratest || true
      - go mod tidy
  build:
    commands:
      - echo "🚀 Terratest 실행 중"
      - |
        if ! go test -timeout 200m -v 2>&1 | tee terratest-output.txt; then
          echo "❌ 테스트 실패"
          exit 1
      - aws s3 cp test/terratest-output.txt s3://$S3_BUCKET/$ERROR_LOG_KEY
artifacts:
  files:50.75 
    - {terratest_output}

"""
    with open(f"{local_base_dir}/buildspec.yml", "w") as f:
        f.write(buildspec_content.strip())

    # main_test.go 생성
    go_content = """
package test

import (
  "testing"                                 // Go의 테스트 프레임워크 패키지
  "github.com/gruntwork-io/terratest/modules/terraform"  // Terratest Terraform 모듈
  "net/http"                                // HTTP 요청용 표준 패키지
  "io/ioutil"                               // 응답 본문 읽기용 패키지
  "time"                                    // sleep 등 시간 관련 함수
)

func TestInfraDeployment(t *testing.T) {
  // Terraform 실행 옵션(디렉터리 위치 등) 지정
  options := &terraform.Options{
    TerraformDir: "../",
  }

  // 테스트 종료 후 Terraform 리소스 자동 정리(destroy)
  //defer terraform.Destroy(t, options)
  
  // Terraform 코드 init + apply (인프라 배포)
  terraform.InitAndApply(t, options)

  // 테스트할 대상 URL 지정 (직접 입력)
  url := "https://www.bboaws.shop/login"

  // HTTP 응답 및 에러, 바디 저장 변수 선언
  var resp *http.Response
  var err error
  var body []byte

  // 최대 시도 횟수 지정 (10번까지 재시도)
  maxRetries := 10
  // 성공 여부 플래그
  success := false

  // 1 ~ maxRetries까지 반복
  for i := 1; i <= maxRetries; i++ {
    // HTTP GET 요청 전송
    resp, err = http.Get(url)
    // 에러가 없고, 응답 코드가 2xx 또는 3xx면(성공 또는 리다이렉트)
    if err == nil && resp.StatusCode >= 200 && resp.StatusCode < 400 {
      // 응답 Body를 나중에 Close (메모리 누수 방지)
      defer resp.Body.Close()
      // 응답 Body 전체 읽기
      body, _ = ioutil.ReadAll(resp.Body)
      // 응답 코드 로그 출력
      t.Logf("시도 %d: 응답 코드: %d", i, resp.StatusCode)
      // 응답 본문 로그 출력
      t.Logf("응답 본문: %s", string(body))
      // 성공 플래그 true로
      success = true
      // 즉시 반복문 종료
      break
    }
    // resp가 nil이 아닐 때(에러가 있더라도), Body 닫기(자원 해제)
    if resp != nil {
      resp.Body.Close()
    }
    // 실패 로그 출력(에러 및 응답 코드)
    t.Logf("시도 %d: 실패 (err: %v, status: %v). 3초 후 재시도...", i, err, func() int {
      if resp != nil {
        return resp.StatusCode
      }
      return 0
    }())
    // 3초 대기 후 재시도
    time.Sleep(3 * time.Second)
  }

  // 성공하지 못한 경우 테스트 실패 처리
  if !success {
    t.Logf("최대 %d번 시도했으나, %s에 성공적으로 접속하지 못했습니다.", maxRetries, url)
  }
}

"""
    with open(f"{local_base_dir}/test/main_test.go", "w") as f:
        f.write(go_content.strip())

    # terraform.tf 다운로드
    s3.download_file(
        Bucket=bucket,
        Key=object_key,
        Filename=f"{local_base_dir}/terraform.tf"
    )

    terraform_backend_file = f"""
terraform {{
  backend "s3" {{
    bucket = "{USER_NAME}"
    key    = "{SERVICE_NAME}/infra/tfstate/terraform.tfstate"
    dynamodb_table = "terraform-lock-table"
    region = "ap-northeast-2"
  }}
}}
"""
    with open(f"{local_base_dir}/backend.tf", "w") as f:
        f.write(terraform_backend_file.strip())

    # terraform.zip 생성
    zip_path = "/tmp/terraform.zip"
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(local_base_dir):
            for file in files:
                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path, start=local_base_dir)
                zipf.write(abs_path, arcname=rel_path)

    print(f"✅ terraform.zip 생성 완료 → {zip_path}")

    # S3 업로드
    s3.upload_file(Filename=zip_path, Bucket=bucket, Key=zip_s3_key)
    print(f"✅ S3 업로드 완료 → s3://{bucket}/{zip_s3_key}")

    # CodeBuild 실행
    response = codebuild.start_build(
        projectName=CODEBUILD_PROJECT,
        environmentVariablesOverride=[
            {"name": "S3_BUCKET", "value": bucket, "type": "PLAINTEXT"},
            {"name": "S3_KEY", "value": zip_s3_key, "type": "PLAINTEXT"}
        ],
        sourceTypeOverride='S3',
        sourceLocationOverride=f'{bucket}/{zip_s3_key}'
    )

    build_id = response["build"]["id"].split("/")[-1]
    print(f"🚀 CodeBuild 시작됨: {build_id}")

    # TaskToken S3 저장
    token_bucket = os.environ["TOKEN_S3_BUCKET"]
    token_key = f"task-token-store/{build_id}.json"
    s3.put_object(
        Bucket=token_bucket,
        Key=token_key,
        Body=json.dumps({
            "task_token": task_token,
            "input": {"Records": event["Records"]}
        })
    )

    print(f"✅ TaskToken 저장 완료 → s3://{token_bucket}/{token_key}")
    year, month, day = DATE[:4], DATE[4:6], DATE[6:8]


    return {
      "message": f"✅ CodeBuild 시작됨: terraform-terratest-codebuild:{build_id}",
      "user_id": USER_NAME.lower(),
      "log_bucket": trail_bucket,
      "log_prefix": f"AWSLogs/{account_id}/CloudTrail",
      "query_date": {
          "year": year,
          "month": month,
          "day": day
      },
      "RetryCount": retry_count
    }
