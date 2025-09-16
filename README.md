# AWS 기반 자동 마이그레이션 및 MSA 전환 프로젝트

## 프로젝트 개요
- 온프레미스 기반 서비스를 **AWS 환경으로 자동 마이그레이션** (3단계: Infra → DB → Application)  
- 고객 상황에 맞는 **MSA 구조 전환 방안 제시 및 설계 자동화**

### 아키텍처
<img width="1920" height="1080" alt="50" src="https://github.com/user-attachments/assets/a13a7610-a1ae-4208-b40b-20bcb3710945" />

---

## 🛠 기술 스택
<img width="837" height="454" alt="image" src="https://github.com/user-attachments/assets/8ef7f3a0-5278-44f6-8dc8-d402290784d5" />
<img width="852" height="462" alt="image" src="https://github.com/user-attachments/assets/b8d15a3c-104a-46a8-9a94-d2a5276d7634" />

---

# 👨‍💻 역할

## 사용한 기술 스택 및 사용 이유
<img width="1048" height="564" alt="image" src="https://github.com/user-attachments/assets/8b61f7d5-d4c0-4137-8143-6eb4757f2ad0" />

---

## 1. 인프라 마이그레이션 자동화 시스템 설계

### 🔹 인프라 마이그레이션 파이프라인
| 1. Terraform 코드 생성 | 2. 정적 분석 | 3. 동적 분석 | 4. 최종 배포 |
|-----------------------|--------------|--------------|--------------|
| <img width="1531" height="863" alt="Terraform 자동 생성" src="https://github.com/user-attachments/assets/bd6494b2-04dd-48d0-99ce-3d31e5078983" /> | <img width="1546" height="858" alt="정적 분석" src="https://github.com/user-attachments/assets/99ca99a4-5681-4597-b9e6-0787d2326ba7" /> | <img width="1535" height="851" alt="동적 분석" src="https://github.com/user-attachments/assets/8b54783b-54a4-4f8d-b463-f5a7e139b515" /> | <img width="1682" height="862" alt="최종 배포" src="https://github.com/user-attachments/assets/e9c66578-3f9a-4f58-be0d-2709e4cc40c8" /> |
| **Bedrock 기반 Terraform 코드 자동 생성 파이프라인 개발** | **TFLint, Terratest** 활용 IaC 정적 분석 | **Terratest** 기반 동적 분석 | 최종 배포 자동화 |

---

### 🔹 상세 기능 설명
| Terraform 코드 자동화 | 온프레미스 명세서 변환 | Step Functions 이벤트 오케스트레이션 | EventBridge + CodeBuild 상태 추적 | tfstate 무결성/잠금 관리 |
|----------------------|------------------------|--------------------------------------|-----------------------------------|--------------------------|
| <img width="1089" height="603" alt="Terraform 코드 자동화" src="https://github.com/user-attachments/assets/1f492405-1cc7-4b3b-9d24-022775c85e92" /> | <img width="1181" height="655" alt="온프레미스 명세서" src="https://github.com/user-attachments/assets/c4c0cc41-5532-4958-86df-df6ea2531e58" /> | <img width="874" height="785" alt="stepfunctions_graph (3)" src="https://github.com/user-attachments/assets/718d62f7-d1f3-4cc8-b70e-8bc788d61b8b" /> | <img width="1501" height="810" alt="Step Functions" src="https://github.com/user-attachments/assets/86a673f0-db65-4d85-bb8a-5699948940b2" /><br/><img width="1292" height="719" alt="오케스트레이션 상세" src="https://github.com/user-attachments/assets/9226d755-edd5-492b-a5c8-27da8c36e178" /> | <img width="1305" height="712" alt="상태 추적" src="https://github.com/user-attachments/assets/73f6705f-e1e1-445d-8414-914f6bc3ac5f" />  |

---

## 2. 보안

- **최소 권한 기반 IAM Role 인증 체계 설계**
- **Terraform Cloud 환경변수 관리**를 통한 AWS Credential 및 DB 민감정보 안전 관리
- **AWS Secret Manager + IAM Role 연계**를 통한 GitHub 인증 자동화 파이프라인 구축  

<img width="1488" height="778" alt="보안 아키텍처" src="https://github.com/user-attachments/assets/967f1e10-bcfb-450f-a1ee-d0be2414be7c" />

---

---

## 📈 성과
- 전체 이관 소요시간 **62% 단축**
<img width="863" height="474" alt="image" src="https://github.com/user-attachments/assets/dd1e062e-7974-4f74-8651-65dc3b428912" />
- Terraform 코드 정확도 **98% 향상**
- Jenkins Credential 기반 **민감 정보 보호**
- Bedrock 모델별 **정확도·요구사항 충실도 분석** → Claude Sonnet 4 최종 선정
<img width="1509" height="828" alt="image" src="https://github.com/user-attachments/assets/c1cd6ee1-bb91-4b84-89f2-edd58bdf7ab1" />
- **Lambda 권한 오류 진단 및 정책 보완**
- Step Functions + CodeBuild 연계를 위한 **TaskToken S3 저장 방식 설계**

---

### 📽️ 시연 영상

- **Infra 단계**  
[![Infra 단계](http://img.youtube.com/vi/u5mxL9T5f1E/0.jpg)](https://youtu.be/u5mxL9T5f1E)

- **DB 단계**  
[![DB 단계](http://img.youtube.com/vi/DnJUB3bH_rc/0.jpg)](https://youtu.be/DnJUB3bH_rc)

- **App 단계**  
[![App 단계](http://img.youtube.com/vi/DSZxG3gsO7Q/0.jpg)](https://youtu.be/DSZxG3gsO7Q)

- **Final Report**  
[![Final Report](http://img.youtube.com/vi/4Bj82-InGO4/0.jpg)](https://youtu.be/4Bj82-InGO4)


---

## 📂 GitHub Repository
- **Terraform 코드** → [🔗 Repo Link](https://github.com/rainhyeon/TerraCloudTest)  
- **Lambda & Step Functions** → [🔗 Repo Link](https://github.com/rainhyeon/AWS8_Final_Project)  

---

## 📑 자료
- **PDF 문서**
[![PDF 바로보기](https://img.shields.io/badge/PDF-Open-red?logo=adobeacrobatreader)](https://drive.google.com/file/d/1xP2rMU9oImp3Ymgez3LvGyK-lAJBVwYS/view?usp=sharing)

---

## 📊 워크 플로우

### stepfunction/6. 5steps
<img width="874" height="785" alt="stepfunctions_graph (3)" src="https://github.com/user-attachments/assets/718d62f7-d1f3-4cc8-b70e-8bc788d61b8b" />

### stepfuction/5ReportAndAlarmCompleteInfra.json
<img width="564" height="564" alt="stepfunctions_graph (4)" src="https://github.com/user-attachments/assets/11bdb3ef-79b0-488d-b1f5-16eead8f760b" />

### stepfuction/4GetLeastPrivilegeThroughAthena.json
<img width="264" height="315" alt="stepfunctions_graph (5)" src="https://github.com/user-attachments/assets/a4ca86ea-2436-48c6-a870-ad597524be55" />

### stepfuction/3 infra-terratest-stepfunction.json
<img width="918" height="605" alt="stepfunctions_graph (6)" src="https://github.com/user-attachments/assets/cf9bc700-6ace-4cca-89b3-e479f2501635" />

### stepfunction/2infra-tflint-validate-stepfunction.json
<img width="264" height="399" alt="stepfunctions_graph (7)" src="https://github.com/user-attachments/assets/5ca3db1e-0763-4add-8481-42d96793d111" />

### stepfunction/1 infra-terraform-generator-stepfunction.json
<img width="275" height="315" alt="stepfunctions_graph (8)" src="https://github.com/user-attachments/assets/29b2ea0c-1e41-43b5-a37c-4066e21980b8" />
