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

### 운영 흐름과 개발 순서

위 색인·검색 흐름은 최종 운영 구조입니다. 현재는 메모리
청크 저장소를 단위 테스트와 개발 대역으로 유지하면서, MySQL 문서·청크
저장소와 S3 원문 저장소를 연결한 상태입니다.

확정된 개발 순서는 다음과 같습니다.

```text
임베딩 인터페이스와 테스트 대역
→ OpenAI 임베딩 어댑터
→ FAISS 벡터 색인·검색
→ BM25·FAISS 하이브리드 검색
→ 기본 검색 품질 평가
→ AI MySQL 문서·청크 저장 완료
→ S3 원문 저장 완료
→ MySQL 전체 청크 기반 BM25·FAISS 재색인 완료
→ FAISS 인덱스 S3 백업·복구 완료
→ 근거 기반 퀴즈 생성 MVP
→ JSON·정답·해설·출처 검증
→ Spring 내부 API 연동
→ 문서 유형별 청킹 확장
```

`InMemoryChunkRepository`는 단위 테스트와 개발 대역으로 유지하고,
`MySQLChunkRepository`는 운영 데이터 영속화와 BM25·FAISS 재색인에
사용합니다. 두 구현은 같은 `ChunkRepository` 계약을 사용합니다.
문서 유형별 청킹은 퀴즈 생성 MVP 결과에서 검색 오류가 확인된 문서부터
독립 전략으로 확장합니다. 현재는 기존 문단 청킹을 유지합니다.

## 데이터 저장 위치

| 저장 위치 | 저장 데이터 |
|---|---|
| MySQL | 문서 정보, 청크 본문과 메타데이터 |
| Amazon S3 | 원본 문서와 FAISS 인덱스 백업 |
| FAISS 파일 | 청크 임베딩 벡터와 청크 식별자 |
| AI 서버 메모리 | 실행 중인 BM25 검색 객체 |
| 메인 서버 MySQL | 검증 완료된 퀴즈, 시나리오, 일일 퀘스트, 금융 레터 |

AI 서버가 생성한 콘텐츠는 구조화된 JSON으로 Spring 서버에 전달하며, 최종 서비스 데이터는 메인 서버의 MySQL에 저장합니다.

MySQL 청크, BM25 결과와 FAISS 결과는 공통 `chunk_key`로 연결합니다.

현재 구현에서는 MySQL의 숫자 `document_id`로 원문과 청크를 연결하고,
청크 식별자는 `{document_id}:{chunk_order}` 형식으로 생성합니다.
`ChunkRepository` 인터페이스를 통해 메모리와 MySQL 구현체를 교체할 수
있습니다. 메모리 저장소는 서버 종료 시 사라지며, MySQL 저장소는
문서 메타데이터와 청크를 영속화합니다.

`TextDocumentRegistrationPipeline` 문서 등록은 S3 업로드, Version ID
기반 원문 재조회, 청킹, MySQL 문서·청크 저장을 순서대로
실행합니다. 문서 갱신 시 같은 `document_id`와 S3 객체 키를
유지하면서 새 Version ID와 청크를 하나의 MySQL 트랜잭션으로
교체합니다. DB 처리가 실패하면 기존 Version ID와 청크를
유지합니다.

문서 등록·교체와 BM25·FAISS 재색인은 분리됩니다. 문서 저장이
정상 완료된 후에만 기존 인덱스를 무효화하고, 저장 중 오류가
발생하면 기존 인덱스를 유지합니다. 여러 문서를 저장한 뒤
MySQL 전체 청크로 `rebuild_index()`를 한 번 실행할 수 있습니다.

임베딩은 애플리케이션의 `EmbeddingClient` 인터페이스를 통해 사용합니다.
자동 테스트에서는 LangChain의 결정적 테스트 대역을 사용하고, 실제 실행에서는
`OpenAIEmbeddingClient`가 `text-embedding-3-small` 모델을 호출합니다.
임베딩 모델명은 `EMBEDDING_MODEL` 환경변수로 관리합니다.

FAISS 벡터 검색은 임베딩 벡터를 정규화한 뒤 내적 검색을 사용해 코사인
유사도를 계산합니다. FAISS 인덱스에는 청크 본문을 넣지 않고 벡터와 위치를
저장하며, 별도 JSON 파일의 `chunk_key` 목록으로 청크 저장소와 연결합니다.
인덱스와 키 매핑은 로컬 파일로 저장하고 다시 로드할 수 있습니다.

FAISS 인덱스와 매핑 파일은 S3에 각각 업로드하고 두 객체의 Version ID를
하나의 백업 참조값으로 반환합니다. 복구 시 정확한 두 버전을 내려받아
검색 파이프라인에
로드하므로 전체 청크를 다시 임베딩하지 않고 검색을 재개할 수 있습니다.
서버 시작 시 자동 복구 연결은 운영 배포 구성이 확정된 뒤 추가합니다.

하이브리드 검색은 BM25와 FAISS의 원점수 범위가 서로 다르므로 원점수를
직접 더하지 않습니다. 각 검색 결과의 순위를 기준으로 `가중치 / 순위` 점수를
계산하고, 같은 `chunk_key`가 양쪽에 있으면 점수를 합산합니다. 기본 가중치는
BM25 `0.7`, FAISS `0.3`이며 환경변수로 조정합니다.

## 프로젝트 구조

```text
firstfolio-ai/
├── app/
│   ├── api/                    # FastAPI 라우터
│   ├── application/
│   │   ├── document_registration.py # S3·MySQL 문서 등록·교체
│   │   ├── quiz_generation.py # 검색·생성·근거검증 퀴즈 파이프라인
│   │   ├── quiz_prompts.py    # 퀴즈 생성·근거검증 프롬프트
│   │   ├── quiz_sources.py    # `chunk_key` 기반 출처 구성
│   │   ├── quiz_validation.py # 퀴즈 규칙·인용·중복 검증
│   │   ├── chunkers/
│   │   │   └── paragraph.py    # 일반 텍스트 문단 청커
│   │   ├── ports/
│   │   │   ├── chunk_repository.py # 청크 저장소 인터페이스
│   │   │   ├── embedding.py    # 임베딩 인터페이스
│   │   │   └── quiz_model.py   # 퀴즈 생성·근거검증 모델 인터페이스
│   │   └── search/
│   │       ├── bm25_pipeline.py # BM25 검색 통합 파이프라인
│   │       ├── evaluation.py    # 검색 품질 평가 지표·데이터 로더
│   │       ├── faiss_backup.py  # FAISS S3 백업·복구
│   │       ├── faiss_pipeline.py # FAISS 재색인·저장·복구 파이프라인
│   │       └── hybrid.py        # BM25·FAISS 하이브리드 검색
│   ├── core/
│   │   └── config.py           # 환경설정
│   ├── domain/
│   │   ├── chunk.py            # 문서 청크 도메인 모델
│   │   ├── document.py         # 원문 문서 도메인 모델
│   │   ├── quiz.py             # 퀴즈·출처·검증 JSON 모델
│   │   └── search.py           # 검색 결과 도메인 모델
│   ├── infrastructure/
│   │   ├── database.py          # MySQL 연결
│   │   ├── document_loaders/
│   │   │   └── text.py         # 일반 텍스트 문서 로더
│   │   ├── openai_embedding.py  # LangChain OpenAI 임베딩 어댑터
│   │   ├── openai_quiz.py       # `gpt-4o-mini` 구조화 퀴즈 어댑터
│   │   ├── repositories/
│   │   │   ├── in_memory_chunk.py # 메모리 청크 저장소
│   │   │   ├── mysql_chunk.py    # MySQL 청크 저장소
│   │   │   └── mysql_document.py # MySQL 문서 저장소
│   │   ├── search/
│   │   │   ├── bm25.py         # BM25 키워드 검색
│   │   │   └── faiss.py        # FAISS 벡터 색인·검색·파일 저장
│   │   ├── s3.py                # S3 원문 업로드·버전 조회
│   │   └── tokenizers/
│   │       └── kiwi.py         # Kiwi 한국어 토크나이저
│   ├── main.py                 # FastAPI 실행 진입점
│   └── quiz_mvp.py             # 퀴즈 생성 MVP CLI 진입점
├── db/init/
│   └── 001_create_document_tables.sql # AI 문서·청크 DDL
├── tests/
│   ├── api/
│   │   └── test_health.py
│   ├── application/
│   │   ├── test_embedding.py
│   │   ├── chunkers/
│   │   │   └── test_paragraph.py
│   │   └── search/
│   │       ├── test_bm25_pipeline.py
│   │       ├── test_evaluation.py
│   │       ├── test_faiss_backup.py
│   │       ├── test_faiss_pipeline.py
│   │       └── test_hybrid.py
│   ├── core/
│   │   └── test_config.py
│   └── infrastructure/
│       ├── test_openai_embedding.py
│       ├── document_loaders/
│       │   └── test_text.py
│       ├── repositories/
│       │   └── test_in_memory_chunk.py
│       ├── search/
│       │   ├── test_bm25.py
│       │   └── test_faiss.py
│       └── tokenizers/
│           └── test_kiwi.py
├── data/
│   └── local/                  # Git에서 제외하는 로컬 비공개 문서
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
kiwipiepy
rank-bm25
langchain-openai
numpy
faiss-cpu
mysql-connector-python
boto3
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
SEARCH_TOP_K=5
BM25_WEIGHT=0.7
FAISS_WEIGHT=0.3
EMBEDDING_MODEL=text-embedding-3-small

OPENAI_API_KEY=

DATABASE_URL=

MYSQL_HOST=mysql
MYSQL_PORT=3306
MYSQL_DATABASE=firstfolio_ai
MYSQL_USER=firstfolio_ai
MYSQL_PASSWORD=
MYSQL_ROOT_PASSWORD=

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

### 로컬 비공개 문서

개발 중 사용하는 비공개 원문은 다음 경로에 저장합니다.

```text
data/local/raw/
```

`data/local/`은 Git에서 제외하며 Docker 컨테이너의 `/app/data/local`에 읽기 전용으로 연결합니다. 실제 원문은 자동 테스트와 CI에서 사용하지 않습니다.

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

### 실제 OpenAI 임베딩 연결 확인

실제 API 연결 확인은 일반 Pytest와 CI에 포함하지 않고 개발자가 필요할 때만
수동으로 실행합니다. 다음 명령은 개인정보가 없는 문장 하나를 전송하고 벡터
차원만 출력합니다.

```bash
docker compose exec ai-api python -c '
from app.core.config import Settings
from app.infrastructure.openai_embedding import OpenAIEmbeddingClient

settings = Settings()
client = OpenAIEmbeddingClient(model=settings.embedding_model)
vector = client.embed_query("예금은 금융기관에 돈을 맡기는 금융상품이다.")

print("모델:", settings.embedding_model)
print("벡터 차원:", len(vector))
print("연결 성공:", len(vector) == 1536)
'
```

이 명령을 실행할 때만 실제 API 비용이 발생합니다. API 키와 벡터 전체는
출력하지 않습니다.

### MySQL 통합 테스트

로컬 MySQL 컨테이너가 `healthy`인 상태에서만 실행합니다.
이 테스트의 S3 호출은 Mock으로 대체되므로 AWS 비용이 발생하지
않습니다.

```bash
docker compose exec -e RUN_MYSQL_INTEGRATION_TESTS=true ai-api python -m pytest
```

### 실제 S3·MySQL 문서 등록 검증

2026-08-02 `data/local/raw/financial_textbook.txt`를 실제 S3에
업로드하고 Version ID를 지정해 재조회한 뒤, 로컬 MySQL에
문서 1건과 청크 406건으로 저장되는 것을 확인했습니다.
검증 당시 `chunk_order`는 0~405, 고유 `chunk_key`는 406개였고
`s3_version_id`는 빈 값이 아니었습니다. 로컬 `document_id`는 47이었으며
환경별 AUTO_INCREMENT 상태에 따라 달라집니다.

문서 등록과 재색인을 분리했으므로 등록 직후 상태는
`pending`입니다. 실제 업로드는 S3 요청과 저장 사용량이
발생하므로 일반 Pytest와 CI에서는 실행하지 않습니다.

같은 날 Ruff 코드·형식 검사, MySQL 통합 테스트를 포함한
Pytest 164개, Docker 이미지 빌드를 모두 통과했습니다. 통합
테스트 임시 문서는 0건으로 정리되었고, 실제 교과서 406개
청크는 유지됐습니다.

### 실제 FAISS S3 백업·복구 검증

2026-08-02 결정적 테스트 임베딩으로 만든 작은 FAISS 인덱스와
`chunk_key` 매핑 파일을 실제 S3에 업로드했습니다. 두 객체의 Version ID로
다시 내려받아 복구 전후 검색 결과가 일치하는 것을 확인했습니다.

이 검증에서는 OpenAI API와 MySQL을 호출하지 않았습니다. 교과서 406개
청크의 실제 OpenAI 임베딩 인덱스 업로드는 아직 수행하지 않았습니다.

### 실제 퀴즈 생성 MVP 검증

2026-08-03 MySQL에 저장된 `financial_textbook.txt` 406개 청크와
BM25·FAISS 하이브리드 검색, `gpt-4o-mini`를 연결해 세 문제
유형의 실제 생성을 확인했습니다.

```bash
docker compose exec -T ai-api python -m app.quiz_mvp \
  --type true_false \
  --topic "요구불 예금의 특징"

docker compose exec -T ai-api python -m app.quiz_mvp \
  --type single_choice \
  --topic "예금의 특징"

docker compose exec -T ai-api python -m app.quiz_mvp \
  --type scenario \
  --topic "정기 예금 선택 상황"
```

| 문제 유형 | `usage_type` | 출처 `chunk_key` | 입력 토큰 | 출력 토큰 | 결과 |
|---|---|---|---:|---:|---|
| `TRUE_FALSE` | `SUB_CHAPTER` | `47:287` | 9,751 | 303 | 통과 |
| `SINGLE_CHOICE` | `SUB_CHAPTER` | `47:189` | 9,661 | 374 | 통과 |
| `SCENARIO` | `MAIN_CHAPTER` | `47:195` | 7,849 | 551 | 통과 |

위 토큰 수는 각 유형을 한 번씩 실행한 개발 환경 표본이며 고정된
비용·성능 기준선이 아닙니다. 로컬 `document_id` 47과 `chunk_key`는
해당 검증 환경의 값으로, 데이터베이스에 따라 달라질 수 있습니다.

세 유형 모두 JSON 구조, 선택지, 단일 정답, 해설, Top 5 내
출처, 원문 근거 문장과 최종 근거검증을 통과했습니다.
근거가 부족하면 `grounding_not_supported`로 계속 차단하며,
실패 시 CLI에 검증 단계, `reason`, `unsupported_claims`를 출력합니다.

이 명령은 실제 OpenAI API 비용이 발생하므로 일반 Pytest와 CI에서는
실행하지 않습니다. 자동 테스트는 OpenAI 호출을 Mock으로 대체합니다.
최종 검증에서 Pytest 249개가 통과했고 7개가 스킵됐으며, Ruff
코드·형식 검사도 통과했습니다.

## 테스트 범위

### 현재 테스트

- FastAPI `/health` 요청·응답
- UTF-8 텍스트 문서 로드
- 존재하지 않는 문서 경로 처리
- 디렉터리 경로 입력 처리
- 지원하지 않는 문서 확장자 처리
- 내용이 없는 문서 처리
- 일반 텍스트의 문단 단위 분리
- 문단 순서, 문서 ID와 청크 식별자 보존
- 빈 문단 제외와 문단 내부 줄바꿈 보존
- 메모리 청크 저장·교체·식별자 순서 조회와 누락 식별자 오류 처리
- 검색 결과 개수의 기본값·환경 변수·유효성 검사
- Kiwi 기반 한국어 금융 문장 토큰화
- 영문 검색어 소문자 변환과 빈 검색어 처리
- BM25 관련 청크 순위와 상위 결과 개수 제한
- 무관한 검색어와 잘못된 BM25 입력 처리
- 텍스트 파일 로드, 청크 저장부터 BM25 검색까지의 통합 흐름
- 색인 생성 전 검색 요청 처리와 환경 설정 적용
- 여러 문서 등록 후 BM25 인덱스 일괄 재생성
- 같은 문서 재등록 시 이전 청크 제거와 다른 문서 청크 유지
- 문서 처리 실패 시 기존 BM25 인덱스 유지
- 빈 청크 저장소의 BM25 재생성 요청 처리
- 임베딩 모델 기본값과 환경변수 설정
- 결정적 임베딩 테스트 대역의 문서·검색어 벡터 생성
- OpenAI 임베딩 어댑터의 모델 설정과 요청 위임
- FAISS 코사인 유사도 기반 벡터 색인과 상위 결과 검색
- FAISS 벡터 차원·개수·빈 입력 오류 처리
- FAISS 인덱스와 `chunk_key` 매핑 저장·로드 및 불일치 처리
- BM25·FAISS 결과의 가중 순위 결합과 중복 청크 점수 합산
- 검색 가중치가 0인 검색기 호출 생략
- 하이브리드 검색 결과 개수 제한과 누락된 `chunk_key` 오류 처리
- 두 검색 결과가 모두 비어 있을 때 빈 결과 반환
- Recall@K·MRR 계산과 입력값 검증
- JSON 평가 질문·정답 청크 키 로드
- 동일한 평가 질문을 여러 검색 방식에 적용하고 지표 비교
- MySQL 연결 성공·실패와 비밀번호 비노출
- MySQL 문서·청크 저장, 조회, 교체와 트랜잭션 롤백
- S3 원문 업로드, Version ID 획득·재조회와 오류 처리
- FAISS 인덱스·매핑 파일 S3 백업과 Version ID 기반 복구
- 복구 전후 FAISS 검색 결과 일치 여부
- S3 원문 재조회·청킹·MySQL 문서·청크 저장 파이프라인
- 문서 교체 실패 시 기존 S3 Version ID와 MySQL 청크 유지
- MySQL 전체 청크 기반 BM25·FAISS 재색인과 하이브리드 검색
- 세 퀴즈 유형의 Pydantic JSON 구조와 선택지·단일 정답 규칙
- Top 5 검색 근거 프롬프트와 `chunk_key`·원문 부분 문자열 검증
- `gpt-4o-mini` 구조화 응답, 타임아웃·재시도와 토큰 사용량 추출
- 검색·생성 규칙·근거검증 실패 차단과 CLI 진단 JSON
- MySQL·BM25·FAISS·OpenAI를 연결한 퀴즈 생성 MVP 실행 흐름

### 향후 테스트 범위

- 문서 전처리
- 문서 유형별 청킹
- FastAPI 요청·응답 형식
- Spring 서버 연동 계약
- 외부 API 실패 및 타임아웃

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

### 검색 품질 1차 기준선

로컬 금융 교과서를 기본 문단 단위로 406개 청크로 나누고, 10개
평가 질문에 정답 `chunk_key`를 연결했습니다. 각 질문에서 상위 5개
결과의 Recall@5와 첫 정답 순위를 반영한 MRR을 계산했습니다.

| 검색 방식 | Recall@5 | MRR |
|---|---:|---:|
| BM25 | 1.0000 | 0.8533 |
| FAISS | 0.9500 | 0.8667 |
| 하이브리드 | 1.0000 | 0.8833 |

하이브리드 검색은 기본 가중치 BM25 `0.7`, FAISS `0.3`에서 목표
Recall@5 80% 이상을 만족하고 가장 높은 MRR을 기록했습니다. 현재
가중치는 유지합니다. 이 결과는 한 교과서와 기본 문단 청킹을 사용한
개발 기준선이며, 문서 유형별 청킹을 적용한 후 다시 평가합니다.

## 현재 상태

FastAPI 기본 서버, Docker 개발 환경, Pytest, Ruff, GitHub Actions CI,
일반 텍스트 로더·청킹, Kiwi·BM25·FAISS 하이브리드 검색과 기본
검색 품질 평가를 완료했습니다. Docker Compose MySQL 8.0, AI
문서·청크 DDL, MySQL 저장소, S3 Version ID 기반 원문 저장,
문서 등록·교체 트랜잭션, MySQL 청크 기반 재색인 연결과 FAISS
인덱스 S3 백업·복구, 근거 기반 퀴즈 생성 MVP와 세 문제
유형의 실제 OpenAI 검증도 완료했습니다.

현재 개발 진행 순서:

```text
FastAPI 기본 서버 완료
→ Docker 개발 환경 완료
→ 환경 변수 설정 완료
→ 자동 테스트 완료
→ Ruff 설정 완료
→ GitHub Actions CI 구성 완료
→ 일반 텍스트 문서 로더 완료
→ 기본 문단 기반 청킹 완료
→ Kiwi 기반 BM25 키워드 검색 파이프라인 완료
→ 문서·청크 식별자 및 청크 저장소 인터페이스 완료
→ 문서 등록·교체와 BM25 인덱스 재생성 분리 완료
→ 임베딩 인터페이스와 테스트 대역 완료
→ OpenAI 임베딩 어댑터 및 실제 연결 확인 완료
→ FAISS 벡터 색인·검색 및 파일 저장·로드 완료
→ BM25·FAISS 하이브리드 검색 완료
→ 기본 검색 품질 평가 완료
→ Docker Compose MySQL 8.0·영속 볼륨 완료
→ AI_DOCUMENTS·AI_DOCUMENT_CHUNKS DDL 완료
→ FastAPI·MySQL 연결 완료
→ MySQL 문서·청크 저장소·트랜잭션 완료
→ S3 원문 업로드·Version ID 재조회 완료
→ S3·MySQL 문서 등록·교체 파이프라인 완료
→ MySQL 전체 청크 기반 BM25·FAISS·하이브리드 검색 완료
→ `financial_textbook.txt` 실제 S3·MySQL 406개 청크 검증 완료
→ FAISS 인덱스 S3 백업·복구 완료
→ 근거 기반 퀴즈 생성 MVP 완료
→ JSON·정답·해설·출처 검증 완료
→ Spring 서버 연동
→ 문서 유형별 청킹 전략 확장
```

### main 브랜치 반영 시점

기능 브랜치는 항상 `dev`를 대상으로 병합하고, `main`에는 기능 하나가 끝날
때마다 반영하지 않습니다. 다음과 같이 실행·검증 가능한 마일스톤이 완성됐을
때 `dev`에서 `main`으로 PR을 생성합니다.

1. **검색 기반 1차 완성**: 기본 검색 품질 평가를 완료하고 BM25·FAISS·
   하이브리드 검색의 기준 결과와 설정값을 기록한 시점
2. **운영 저장 기반 완성**: AI MySQL, S3와 재색인·복구 흐름을 검증한 시점
3. **RAG 콘텐츠 생성 MVP 완성**: 근거 기반 퀴즈 생성과 품질 검수를 완료한 시점

기본 검색 품질 평가를 `dev`에 병합하고 전체 CI를 통과하면 검색 기반
1차 버전의 `dev → main` PR을 생성합니다.
