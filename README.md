# FirstFolio AI Service

FirstFolio의 금융 문서 검색과 금융교육 콘텐츠 생성을 담당하는 FastAPI 기반 AI 서버입니다.

## 프로젝트 개요

AI 서버는 신뢰할 수 있는 금융 문서를 검색하고, 검색된 근거를 기반으로 금융교육 콘텐츠를 생성합니다.

Frontend와 직접 통신하지 않으며, Spring Legacy 메인 서버가 AI 요청과 응답을 중계합니다.

```text
Frontend
   ↓
Spring Legacy Backend
   ↓ 내부 REST API
FastAPI AI Server
   ↓ 구조화된 JSON
Spring Legacy Backend
   ↓
Frontend
```

## 담당 범위

### 현재 범위 

- 금융 문서 등록 및 전처리
- 문서 유형에 따른 청킹
- BM25·벡터 기반 하이브리드 검색
- 소단원 개념 문제 생성
- 대단원 시나리오 문제 생성
- 일일 퀘스트용 문제 생성
- 금융 뉴스 요약 및 주간 금융 레터 생성
- 생성 결과의 형식·근거 검증
- 검색 및 생성 품질 평가
- Spring 서버와 내부 REST API 통신

### 향후 확장 범위

- 포트폴리오 분석 근거 검색
- 포트폴리오 기반 AI 피드백 문장 생성
- 사용자 학습·오답 데이터를 반영한 개인화 콘텐츠 생성

### 담당하지 않는 범위

- 사용자 인증 및 권한 관리
- 사용자·포트폴리오·학습 이력 관리
- 퀴즈 정답 처리 및 점수 계산
- 리더보드 및 보상 관리
- 생성 콘텐츠의 최종 저장 및 사용자 제공
- Frontend와의 직접 통신

위 기능은 Spring Legacy 메인 서버가 담당합니다.

## 기술 스택

- Python 3.12
- FastAPI
- LangChain
- OpenAI API
- Kiwi 형태소 분석
- BM25 Retriever
- FAISS
- MySQL
- Amazon S3
- Docker
- Pytest
- Ruff
- GitHub Actions

## RAG 처리 흐름

### 색인 파이프라인

```text
금융 문서 등록
→ 원문 저장
→ 문서 유형 확인
→ 전처리 및 청킹
→ 청크 본문·메타데이터 저장
→ Kiwi 기반 토큰화
→ BM25 검색 객체 생성
→ OpenAI 임베딩 생성
→ FAISS 벡터 인덱스 생성
→ 인덱스 저장 및 작업 결과 기록
```

### 검색·생성 파이프라인

```text
Spring 서버 요청
→ 요청 데이터 검증
→ 문서 유형·카테고리 필터링
→ 질문 형태소 분석 및 임베딩
→ BM25·FAISS 하이브리드 검색
→ 상위 근거 청크 선별
→ 기능별 프롬프트 구성
→ LLM 호출
→ JSON 형식 및 근거 검증
→ Spring 서버에 결과 반환
```

## 데이터 저장 위치

| 저장 위치 | 저장 데이터 |
|---|---|
| MySQL | 문서 정보, 청크 본문, 메타데이터, 색인 작업 및 요청 로그 |
| Amazon S3 | 원본 문서와 FAISS 인덱스 백업 |
| FAISS 파일 | 청크 임베딩 벡터와 청크 식별자 |
| AI 서버 메모리 | 실행 중인 BM25 검색 객체 |
| 메인 서버 MySQL | 검증 완료된 퀴즈, 시나리오, 일일 퀘스트, 금융 레터 |

AI 서버가 생성한 콘텐츠는 구조화된 JSON으로 Spring 서버에 전달하며, 최종 서비스 데이터는 메인 서버의 MySQL에 저장합니다.

MySQL 청크, BM25 결과와 FAISS 결과는 공통 `chunk_key`로 연결합니다.

## 프로젝트 구조

```text
firstfolio-ai/
├── app/
│   ├── api/                    # FastAPI 라우터
│   ├── application/
│   │   └── chunkers/
│   │       └── paragraph.py    # 일반 텍스트 문단 청커
│   ├── core/                   # 환경설정
│   ├── domain/
│   │   ├── chunk.py            # 문서 청크 도메인 모델
│   │   └── document.py         # 원문 문서 도메인 모델
│   ├── infrastructure/
│   │   └── document_loaders/
│   │       └── text.py         # 일반 텍스트 문서 로더
│   └── main.py                 # FastAPI 실행 진입점
├── tests/
│   ├── api/
│   │   └── test_health.py
│   ├── application/
│   │   └── chunkers/
│   │       └── test_paragraph.py
│   └── infrastructure/
│       └── document_loaders/
│           └── test_text.py
├── .github/
│   └── workflows/
│       └── ci.yml
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
└── README.md
```

프로젝트 초기에는 필요한 폴더부터 구성하고, 기능이 추가될 때 해당 책임에 맞는 모듈을 확장합니다.

## 의존성 관리

### requirements.txt

AI 서버 실행에 필요한 패키지를 관리합니다.

```txt
fastapi
uvicorn
pydantic-settings
```

### requirements-dev.txt

개발, 테스트 및 코드 검사에만 필요한 패키지를 관리합니다.

```txt
pytest
httpx2
ruff
```

두 파일 모두 GitHub에서 버전 관리합니다.

- 운영 환경: `requirements.txt` 설치
- 개발 환경 및 CI: 두 파일 모두 설치

## 환경 변수 설정

환경 변수 예시 파일을 복사합니다.

```bash
cp .env.example .env
```

`.env`에 실제 값을 입력합니다.

```dotenv
APP_ENV=local
APP_PORT=8000

OPENAI_API_KEY=

DATABASE_URL=

AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_REGION=ap-northeast-2
S3_BUCKET_NAME=

SPRING_API_BASE_URL=
INTERNAL_API_KEY=
```

`.env` 파일과 실제 API 키는 GitHub에 커밋하지 않습니다.

## 로컬 실행

### Docker 실행

```bash
docker compose up -d --build
```

### 실행 상태 확인

```bash
docker compose ps
```

### 로그 확인

```bash
docker compose logs -f ai-api
```

### 서버 종료

```bash
docker compose down
```

## 테스트

### 전체 테스트 실행

```bash
docker compose exec ai-api python -m pytest
```

### 코드 검사

```bash
docker compose exec ai-api ruff check .
```

### 코드 형식 검사

```bash
docker compose exec ai-api ruff format --check .
```

### 코드 형식 자동 수정

```bash
docker compose exec ai-api ruff format .
```

## 테스트 범위

### 현재 테스트

- FastAPI `/health` 요청·응답
- UTF-8 텍스트 문서 로드
- 존재하지 않는 문서 경로 처리
- 디렉터리 경로 입력 처리
- 지원하지 않는 문서 확장자 처리
- 내용이 없는 문서 처리
- 일반 텍스트의 문단 단위 분리
- 문단 순서와 원문 메타데이터 보존
- 빈 문단 제외와 문단 내부 줄바꿈 보존

### 향후 테스트 범위

- 문서 전처리
- 문서 유형별 청킹
- Kiwi 토큰화
- BM25 검색
- FAISS 벡터 검색
- 하이브리드 검색
- 프롬프트 입력 구성
- LLM 출력 JSON 검증
- 검색 청크와 답변 근거 일치 여부
- FastAPI 요청·응답 형식
- Spring 서버 연동 계약
- 외부 API 실패 및 타임아웃
- 검색 결과가 부족한 경우의 대체 처리

CI에서는 실제 OpenAI, MySQL 및 S3를 호출하지 않고 Mock 또는 테스트 데이터를 사용합니다.

## CI

GitHub Actions를 이용해 Pull Request와 주요 브랜치의 코드 품질을 자동으로 검사합니다.

```text
코드 Push 또는 Pull Request
→ Python 3.12 설치
→ 실행·개발 의존성 설치
→ Ruff 코드 검사
→ Ruff 형식 검사
→ Pytest 실행
→ Docker 이미지 빌드 확인
```

CI는 다음 경우 실행됩니다.

- Pull Request 생성 또는 수정
- `dev` 브랜치 Push
- `main` 브랜치 Push

CI 성공은 배포 완료를 의미하지 않습니다. 현재 CI는 코드가 병합 가능한 상태인지 검사하는 역할만 담당합니다.

실제 배포 자동화는 운영 인프라가 확정된 후 별도 CD 단계로 추가합니다.

## 브랜치 전략

| 브랜치 | 용도 |
|---|---|
| `main` | 최종 배포가 가능한 안정 버전 |
| `dev` | 다음 버전을 위한 기능 통합 |
| `feat/{기능명}` | 신규 기능 개발 |
| `fix/{오류명}` | 버그 수정 |
| `docs/{문서명}` | 문서 작업 |

새로운 작업은 원칙적으로 `dev`에서 브랜치를 생성합니다.

```bash
git switch dev
git pull origin dev
git switch -c feat/document-indexing
```

하나의 메인 이슈는 하나의 브랜치에서만 작업합니다.

## Issue 규칙

작업을 시작하기 전에 GitHub Issue를 먼저 등록합니다.

Issue에는 다음 내용을 작성합니다.

```markdown
**작업명:** feat: 금융 문서 색인 기능 구현

## 작업 배경
금융 문서를 RAG 검색에 사용하기 위한 색인 파이프라인이 필요합니다.

## 작업 내용 및 현황
- [ ] 문서 로더 구현
- [ ] 문서 전처리 구현
- [ ] 청킹 구현
- [ ] BM25 색인 구현
- [ ] FAISS 색인 구현
- [ ] 테스트 작성

## 참고 사항
관련 설계 문서와 API 계약을 첨부합니다.
```

## 커밋 메시지 규칙

```text
[타입]: [작업 내용] #[이슈번호]
```

| 타입 | 용도 | 예시 |
|---|---|---|
| `feat` | 새로운 기능 | `feat: 금융 문서 청킹 구현 #12` |
| `fix` | 버그 수정 | `fix: FAISS 인덱스 로드 오류 수정 #15` |
| `docs` | 문서 작성 | `docs: AI API 계약 추가 #18` |
| `style` | 코드 형식 변경 | `style: Ruff 기준 코드 정리 #20` |
| `ref` | 리팩터링 | `ref: 검색 서비스 책임 분리 #22` |
| `test` | 테스트 추가·수정 | `test: 하이브리드 검색 테스트 추가 #25` |
| `chore` | 설정 및 빌드 작업 | `chore: Docker 실행 환경 구성 #30` |

작업 완료 시 현재 변경사항에 적합한 커밋 메시지를 확인한 후 커밋합니다.

## Pull Request 규칙

- `main`과 `dev` 브랜치에 직접 병합하지 않습니다.
- 기능 브랜치에서 `dev`를 대상으로 PR을 생성합니다.
- 최소 한 명 이상의 리뷰와 승인을 받습니다.
- Rebase 사용을 지양하고 일반 Merge를 사용합니다.
- CI 검사를 통과한 코드만 병합합니다.
- API, JSON 형식 또는 DB 구조가 변경되면 관련 팀에 공유합니다.

### PR 체크리스트

- [ ] 로컬 환경에서 정상적으로 실행되는가?
- [ ] 자동 테스트가 통과하는가?
- [ ] Ruff 검사와 형식 검사를 통과하는가?
- [ ] Docker 이미지가 정상적으로 빌드되는가?
- [ ] `dev` 기준 충돌이 없는가?
- [ ] API 및 JSON 계약 변경 사항을 공유했는가?
- [ ] 환경 변수와 비밀 정보가 포함되지 않았는가?
- [ ] 최소 한 명 이상의 승인을 받았는가?

## 서버 간 통신 원칙

- Frontend는 AI 서버를 직접 호출하지 않습니다.
- AI 서버는 Spring 서버의 내부 요청만 처리합니다.
- 요청과 응답은 JSON 형식을 사용합니다.
- 서버 간 인증을 위한 내부 API 키를 사용합니다.
- 하나의 요청 흐름을 추적할 수 있도록 `request_id` 또는 `trace_id`를 전달합니다.
- 타임아웃, 실패 상태와 재시도 가능 여부를 명시적으로 반환합니다.
- API 계약을 변경하기 전에 Spring 담당자와 협의합니다.
- AI 서버는 메인 DB를 임의로 수정하지 않습니다.

## 보안 원칙

다음 정보는 GitHub에 커밋하지 않습니다.

- OpenAI API 키
- 데이터베이스 계정 및 비밀번호
- AWS 인증 정보
- 서버 간 인증 키
- 사용자 개인정보
- 실제 운영 환경 설정 파일
- 테스트 과정에서 생성된 민감한 데이터

협업에 필요한 환경 변수 이름만 `.env.example`에 작성합니다.

포트폴리오 분석 요청에는 사용자 이름, 이메일, 전화번호, 계좌번호와 같은 직접 식별 정보를 포함하지 않습니다. AI 서버에는 분석에 필요한 자산 유형, 금액, 비율과 같은 최소 정보만 전달합니다.

## 초기 품질 목표

- 준비된 평가 질문에서 정답 근거가 검색 상위 5개 안에 포함되는 비율 측정
- 초기 검색 목표: `Recall@5 80% 이상`
- 생성 결과가 지정된 JSON 형식을 만족하는지 검사
- 답변의 출처 청크가 실제 검색 결과와 일치하는지 검사
- 검색 근거가 부족하면 임의로 생성하지 않고 실패 상태 반환
- 개별 생성 실패가 전체 배치 작업을 중단시키지 않도록 처리
- 실패한 생성 항목만 제한적으로 재시도

## 현재 상태

FastAPI 기본 서버, Docker 개발 환경, 환경 변수, Pytest, Ruff, GitHub Actions CI, 일반 텍스트 문서 로더와 기본 문단 기반 청킹을 완료했습니다.

초기 구축 순서:

```text
FastAPI 기본 서버 완료
→ Docker 개발 환경 완료
→ 환경 변수 설정 완료
→ 자동 테스트 완료
→ Ruff 설정 완료
→ GitHub Actions CI 구성 완료
→ 일반 텍스트 문서 로더 완료
→ 기본 문단 기반 청킹 완료
→ BM25 검색
→ FAISS 검색
→ 하이브리드 검색
→ 콘텐츠 생성
→ 품질 평가
→ Spring 서버 연동
```
