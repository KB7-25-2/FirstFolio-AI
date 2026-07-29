# FirstFolio AI Service

FirstFolio의 금융교육 콘텐츠 생성과 RAG 기반 금융정보 검색을 담당하는 AI 서버입니다.

## 1. 담당 범위

- 금융 문서 수집 및 전처리
- 문서 유형별 청킹
- BM25·벡터 기반 하이브리드 검색
- 금융교육 문제 및 시나리오 생성
- 뉴스 요약 및 주간 금융 레터 생성
- 포트폴리오 분석 근거 검색 및 피드백 생성
- 생성 결과 검증과 품질 평가
- Spring 서버와 내부 REST API 통신

사용자와 프론트엔드는 AI 서버를 직접 호출하지 않습니다.

```text
Frontend
   ↓
Spring Legacy Backend
   ↓
FastAPI AI Server
   ↓
Spring Legacy Backend
   ↓
Frontend
```

AI 서버는 사용자, 포트폴리오, 학습 이력 등의 서비스 데이터를 직접 관리하지 않습니다. Spring 서버로부터 필요한 데이터를 전달받고 구조화된 JSON 결과를 반환합니다.

## 2. 기술 스택

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
- GitHub Actions

## 3. RAG 처리 흐름

### 색인 파이프라인

```text
금융 문서 등록
→ 원문 저장
→ 문서 유형 확인
→ 전처리 및 청킹
→ 청크 메타데이터 저장
→ BM25 색인 생성
→ 임베딩 생성
→ FAISS 벡터 색인 저장
```

### 생성 파이프라인

```text
Spring 서버 요청
→ 요청 데이터 검증
→ 검색 범위 필터링
→ BM25·FAISS 하이브리드 검색
→ 관련 청크 선별
→ 프롬프트 구성
→ LLM 호출
→ 결과 형식 및 근거 검증
→ 구조화된 JSON 반환
```

## 4. 저장 데이터

| 저장 위치 | 주요 데이터 |
|---|---|
| MySQL | 문서 정보, 청크 본문, 메타데이터, 작업 상태, 요청 로그 |
| S3 | 원본 문서, FAISS 인덱스 백업, 생성 결과 백업 |
| AI 서버 메모리 | 실행 중인 BM25 검색 객체 |
| FAISS 파일 | 청크 임베딩 벡터와 청크 식별자 |

MySQL의 `chunk_key`를 공통 식별자로 사용하여 BM25 검색 결과, FAISS 검색 결과와 원본 청크를 연결합니다.

## 5. 프로젝트 구조

```text
firstfolio-ai/
├── app/
│   ├── api/                 # FastAPI 요청·응답 계층
│   ├── application/         # 기능별 서비스와 유스케이스
│   ├── domain/              # 문서, 청크, 검색 결과 도메인
│   ├── infrastructure/      # OpenAI, MySQL, S3, FAISS 연동
│   ├── pipelines/
│   │   ├── indexing/        # 문서 전처리·청킹·색인
│   │   ├── retrieval/       # BM25·벡터·하이브리드 검색
│   │   └── generation/      # 문제·레터·피드백 생성
│   ├── prompts/             # 기능별 프롬프트
│   ├── evaluation/          # 검색 및 생성 품질 평가
│   ├── core/                # 환경설정, 예외, 로깅
│   └── main.py
├── tests/
├── scripts/
├── data/
│   ├── raw/
│   └── vector_store/
├── docs/
├── .github/
│   └── workflows/
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── AGENTS.md
├── PROJECT_SPEC.md
└── README.md
```

## 6. 로컬 실행

### 환경 변수 설정

```bash
cp .env.example .env
```

`.env`에 실제 환경 변수 값을 입력합니다.

```dotenv
OPENAI_API_KEY=
DATABASE_URL=
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_REGION=
S3_BUCKET_NAME=
SPRING_API_BASE_URL=
INTERNAL_API_KEY=
```

`.env` 파일은 Git에 커밋하지 않습니다.

### Docker 실행

```bash
docker compose up -d --build
```

### 실행 상태 확인

```bash
docker compose ps
docker compose logs -f
```

### 서버 종료

```bash
docker compose down
```

## 7. API 통신 원칙

- Frontend는 AI 서버를 직접 호출하지 않습니다.
- AI 서버는 Spring 서버의 내부 요청만 처리합니다.
- 요청과 응답은 JSON 형식을 사용합니다.
- 서버 간 인증용 내부 API 키를 사용합니다.
- 모든 요청에 `request_id` 또는 `trace_id`를 포함합니다.
- 타임아웃, 실패 상태, 재시도 가능 여부를 명시적으로 반환합니다.
- API 계약이 변경되면 Spring 담당자와 먼저 협의합니다.

## 8. 브랜치 전략

| 브랜치 | 용도 |
|---|---|
| `main` | 배포 가능한 안정 버전 |
| `dev` | 기능 통합 브랜치 |
| `feat/{기능명}` | 신규 기능 개발 |
| `fix/{오류명}` | 오류 수정 |
| `docs/{문서명}` | 문서 작업 |

새 작업 브랜치는 원칙적으로 `dev`에서 생성합니다.

```bash
git switch dev
git pull origin dev
git switch -c feat/hybrid-search
```

하나의 메인 이슈는 하나의 브랜치에서만 작업합니다.

## 9. 커밋 메시지

```text
[타입]: [작업 내용] #[이슈번호]
```

예시:

```text
feat: 금융 문서 청킹 파이프라인 구현 #12
fix: FAISS 인덱스 로드 오류 수정 #15
docs: AI 서버 실행 방법 추가 #18
ref: 하이브리드 검색 로직 분리 #22
test: 검색 결과 평가 테스트 추가 #25
chore: Docker 실행 환경 구성 #30
```

팀 컨벤션에 따라 리팩터링 타입은 `ref`를 사용합니다.

## 10. 작업 절차

1. GitHub Issue를 등록합니다.
2. `dev`에서 작업 브랜치를 생성합니다.
3. 기능을 구현하고 테스트합니다.
4. 컨벤션에 맞춰 커밋합니다.
5. 원격 저장소에 브랜치를 푸시합니다.
6. `dev`를 대상으로 Pull Request를 생성합니다.
7. 최소 한 명의 리뷰와 승인을 받습니다.
8. 충돌과 CI 결과를 확인한 후 일반 Merge를 진행합니다.

`main`과 `dev` 브랜치에 직접 커밋하거나 직접 병합하지 않습니다.

## 11. Pull Request 확인 사항

- 로컬 환경에서 정상적으로 실행되는가?
- 관련 테스트가 통과하는가?
- `dev` 기준 충돌이 없는가?
- Spring 연동 API가 변경되었다면 공유했는가?
- DB나 JSON 계약 변경 사항을 문서화했는가?
- 환경 변수나 API 키가 포함되지 않았는가?
- 최소 한 명의 승인을 받았는가?

## 12. 테스트

```bash
docker compose exec ai-api pytest
```

주요 테스트 대상:

- 문서 전처리 및 청킹
- 문서 유형별 청킹 전략
- BM25 검색
- FAISS 벡터 검색
- 하이브리드 검색
- 프롬프트 입력 형식
- LLM 출력 JSON 검증
- 근거 청크 일치 여부
- Spring 연동 API 요청·응답
- 외부 API 실패 및 타임아웃

## 13. 보안 원칙

다음 정보는 저장소에 커밋하지 않습니다.

- OpenAI API 키
- 데이터베이스 계정
- AWS 인증 정보
- 내부 서버 인증 키
- 사용자 개인정보
- 실제 운영 환경 설정 파일

협업에 필요한 환경 변수 이름만 `.env.example`로 관리합니다.

포트폴리오 분석 요청에는 사용자 이름, 이메일, 전화번호, 계좌번호와 같은 직접 식별 정보를 포함하지 않습니다. AI 서버에는 분석에 필요한 자산 유형, 금액 또는 비율과 같은 최소 정보만 전달합니다.

## 14. 문서 기준

- `PROJECT_SPEC.md`: 제품 범위와 공식 요구사항
- `AGENTS.md`: AI 개발 규칙과 작업 제약
- `README.md`: 실행 방법과 협업 규칙
- `docs/`: AI API 계약, RAG 설계 및 평가 기준

문서 내용이 충돌하면 공식 팀 문서와 `PROJECT_SPEC.md`를 우선합니다.