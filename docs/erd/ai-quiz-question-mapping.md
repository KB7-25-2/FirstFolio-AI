# AI 퀴즈 JSON–BE ERD 매핑과 영향 검토

## 1. 문서 목적

이 문서는 AI 서버가 전달한 퀴즈 JSON을 Spring Legacy 서버가 BE
`quiz_questions` 테이블에 저장할 때의 필드 매핑과 기존 ERD 영향을 정의한다.

API 요청·응답, 검증과 오류 정책은
[`AI–Spring 퀴즈 생성 대상 조회·배치 전달 API`](../api/quiz-question-batch-api.md)를
따른다.

## 2. 저장 원칙

- AI는 Spring에서 현재 서비스 대상인 전체 대·소단원을 먼저 조회한다.
- AI는 조회한 `main_chapter_id`, `sub_chapter_id`를 퀴즈에 직접 연결한다.
- 자동 검증을 통과한 퀴즈만 Spring에 전달한다.
- Spring은 JSON 구조, 문제 유형, 단원 존재와 부모·자식 관계를 다시 검증한다.
- 유효한 퀴즈는 문항 버전 하나당 `quiz_questions` 한 행으로 저장한다.
- 최초 상태는 `REVIEW`이며 `published_at`은 `NULL`이다.
- 관리자가 FE 관리자 페이지에서 배치 일괄 승인 또는 개별 승인을 하면 Spring이
  해당 문항을 `PUBLISHED`로 전환하고 승인 시각을 `published_at`에 저장한다.
- 랜덤 출제 조회는 `PUBLISHED` 상태만 대상으로 한다.
- MVP에서는 AI 문항도 `source_refs_json=NULL`로 저장한다.
- AI 서버는 BE 메인 DB를 직접 수정하지 않는다.
- AI 내부 검증·실행 정보는 BE 퀴즈 원본에 저장하지 않는다.

## 3. AI 요청–`quiz_questions` 매핑

### 3.1 AI가 전달하는 필드

| AI 요청 필드 | AI JSON 타입 | BE 컬럼 | BE 타입 | 매핑 방식 |
| --- | --- | --- | --- | --- |
| `quiz.usage_type` | string | `usage_type` | `VARCHAR(30)` | 검증 후 그대로 저장 |
| `quiz.main_chapter_id` | integer | `main_chapter_id` | `BIGINT` | 존재·활성 상태 검증 후 저장 |
| `quiz.sub_chapter_id` | integer 또는 null | `sub_chapter_id` | `BIGINT` | 부모 관계 검증 후 저장 |
| `quiz.question_type` | string | `question_type` | `VARCHAR(30)` | 검증 후 그대로 저장 |
| `quiz.difficulty` | string | `difficulty` | `VARCHAR(20)` | 검증 후 그대로 저장 |
| `quiz.prompt` | string | `prompt` | `TEXT` | 그대로 저장 |
| `quiz.scenario_json` | object 또는 null | `scenario_json` | `JSON` | BE 시나리오 구조로 저장 |
| `quiz.options_json` | array | `options_json` | `JSON` | BE 선택지 구조로 저장 |
| `quiz.correct_answer_json` | object | `correct_answer_json` | `JSON` | BE 정답 구조로 저장 |
| `quiz.explanation` | string | `explanation` | `TEXT` | 그대로 저장 |
| `quiz.source_refs_json` | null 또는 생략 | `source_refs_json` | `JSON` | MVP에서는 SQL `NULL` 저장 |

AI 내부 `option_id`, `text`는 Spring 전송 전에 각각 `key`, `label`로
변환한다. Spring은 배치 계약에서 AI 내부 형식을 받지 않는다.
AI 내부 citation과 검색 문서 메타데이터도 MVP 배치 요청에 포함하지 않는다.

### 3.2 문제 범위

| `usage_type` | 허용 유형 | `main_chapter_id` | `sub_chapter_id` |
| --- | --- | --- | --- |
| `SUB_CHAPTER` | `TRUE_FALSE`, `SINGLE_CHOICE` | 필수 | 필수 |
| `MAIN_CHAPTER` | `SCENARIO` | 필수 | `null` |

Spring은 소단원이 요청한 대단원에 실제로 속하는지 검증한다. 관계가 다르면
해당 항목을 `INVALID_CHAPTER_SCOPE`로 거절한다.

## 4. JSON 컬럼 매핑

### 4.1 `options_json`

```json
[
  {"key": "1", "label": "정기 예금에 맡긴다."},
  {"key": "2", "label": "주식을 단기 매매한다."},
  {"key": "3", "label": "파생상품에 투자한다."},
  {"key": "4", "label": "모두 현금으로 보관한다."}
]
```

선택지의 `description`은 선택적이며 없으면 생략하거나 `null`을 사용한다.

### 4.2 `correct_answer_json`

```json
{"key": "1"}
```

정답 키는 `options_json`에 정확히 하나 존재해야 한다.

### 4.3 `scenario_json`

```json
{
  "title": "금융상품 선택",
  "narrative": "민서는 조건에 맞는 금융상품을 고르려고 한다.",
  "persona": {
    "name": "민서",
    "age": "18세",
    "job": "고등학생"
  },
  "requirements": {
    "assets": "저축 자금 100만 원",
    "risk": "원금 손실을 피하고 싶음",
    "goal": "6개월 뒤 학업 비용 마련"
  },
  "market": {
    "title": "시장 정보",
    "reference_at": "2026-08-10T00:00:00Z",
    "bullets": ["검증된 시장 정보"]
  },
  "constraints": ["약정 기간 동안 자금을 사용하지 않는다."],
  "paper_title": "선택 보고서"
}
```

`TRUE_FALSE`, `SINGLE_CHOICE`는 `scenario_json` 컬럼에 SQL `NULL`을
저장한다.

## 5. `source_refs_json` MVP 정책

| 구분 | MVP 저장 값 | 설명 |
| --- | --- | --- |
| HUMAN 문항 | SQL `NULL` | 기존 정책 유지 |
| AI 커리큘럼 문항 | SQL `NULL` | 출처 조립과 노출을 배치 저장 조건으로 사용하지 않음 |
| 향후 AI 뉴스 문항 | 미정 | 뉴스 도메인 정의 후 구조와 노출 정책 확정 |

컬럼은 삭제하지 않는다. 일일 퀘스트와 뉴스 도메인에서 향후 사용할 수 있고,
삭제할 경우 도메인, MyBatis 매핑, 스냅샷과 응답까지 불필요하게 변경되기 때문이다.

현재 DB의 `chk_quiz_questions_source_refs`는 AI 문항에 비어 있지 않은 배열을
요구한다. 별도 Flyway 마이그레이션에서 다음 정책으로 완화해야 한다.

```text
HUMAN → source_refs_json IS NULL
AI    → source_refs_json IS NULL 또는 비어 있지 않은 JSON 배열
```

공통 퀴즈 JSON Schema도 AI 문항의 `source_refs_json`에 `null`을 허용한다.
이번 MVP에서는 출처 배열 내부의 새 구조를 정의하지 않는다.

## 6. Spring이 생성하거나 결정하는 필드

AI는 아래 값을 요청에 포함하지 않는다.

| `quiz_questions` 컬럼 | 생성·결정 주체 | 최초 저장 값 | 설명 |
| --- | --- | --- | --- |
| `question_id` | MySQL | `AUTO_INCREMENT` | 특정 문항 버전 행의 PK |
| `question_key` | Spring | 새 고유 키 | 후속 버전을 묶는 논리 키 |
| `version_no` | Spring | `1` | 최초 AI 문항 버전 |
| `generation_type` | Spring | `AI` | 내부 배치 요청이므로 고정 |
| `display_order` | Spring | `NULL` | 문제 풀 랜덤 출제 대상 |
| `status` | Spring | `REVIEW` | 관리자 승인 전까지 출제 대상 아님 |
| `created_by` | Spring 설정 | AI 배치 시스템 사용자 ID | 운영 설정값 사용 |
| `source_refs_json` | Spring | `NULL` | MVP 출처 미사용 |
| `published_at` | Spring | `NULL` | 관리자 승인 시각에 채워짐 |
| `created_at` | Spring | DB 저장 시각 | 최초 버전 생성 시각 |

`main_chapter_id`, `sub_chapter_id`는 AI 요청으로 받되 Spring이 존재·활성 상태와
부모 관계를 검증한 뒤 저장한다.

## 7. 단원 연결 규칙

### 7.1 생성 전

1. AI가 `GET /api/internal/quiz-generation-targets`를 호출한다.
2. 응답의 단원 이름으로 RAG 검색과 퀴즈 생성을 수행한다.
3. 응답의 단원 ID는 LLM 출력에 맡기지 않고 AI 배치 코드가 연결한다.

### 7.2 저장 전

1. Spring이 `main_chapter_id`의 존재와 서비스 대상 여부를 확인한다.
2. `SUB_CHAPTER`이면 `sub_chapter_id` 존재와 부모 대단원 관계를 확인한다.
3. `MAIN_CHAPTER`이면 `sub_chapter_id`가 `null`인지 확인한다.
4. 문제 유형과 사용 범위가 맞을 때만 저장 대상으로 분류한다.

### 7.3 금지 규칙

- 출처나 문서 제목으로 BE 단원 ID를 결정하지 않는다.
- 유사도 기반으로 단원을 추측하거나 보정하지 않는다.
- 존재하지 않거나 비활성인 단원 ID로 문항을 저장하지 않는다.
- 부모 대단원이 다른 소단원 ID를 요청 값 그대로 저장하지 않는다.

## 8. ERD의 허용 범위와 배치 API 규칙

BE ERD는 관리자 등록, 레벨 테스트와 일일 퀘스트도 수용하므로 배치 API보다
넓은 값을 허용할 수 있다. AI 배치 수신 API는 DTO와 서비스 검증으로 더 엄격한
규칙을 적용한다.

| BE ERD 허용 범위 | AI 배치 API 규칙 | ERD 변경 |
| --- | --- | --- |
| `difficulty`는 `NULL` 허용 | 필수 | 불필요 |
| `options_json`은 넓은 JSON 허용 | 지원 유형별 개수·키 검증 | 불필요 |
| AI의 `source_refs_json`은 비어 있지 않은 배열 필수 | MVP에서는 `NULL` 허용 | CHECK 제약 변경 필요 |
| 여러 `usage_type` 수용 | `SUB_CHAPTER`, `MAIN_CHAPTER`만 허용 | 불필요 |
| `scenario_json`은 `NULL` 허용 | `SCENARIO`만 필수 객체 | 불필요 |

테이블과 컬럼은 추가·삭제하지 않는다. DB CHECK 제약과 공통 JSON Schema,
fixture 및 검증 테스트만 AI nullable 정책에 맞게 변경한다.

## 9. BE에 저장하지 않는 AI 필드

| AI 필드 | 저장 여부 | 사유 |
| --- | --- | --- |
| `batch_id` | 저장 안 함 | MVP 전송 배치 추적용 |
| `item_id` | 저장 안 함 | 응답 항목 연결용 |
| `quiz.citations` | 저장 안 함 | MVP에서는 출처를 BE 저장 조건으로 사용하지 않음 |
| `validation` | 저장 안 함 | AI 내부 자동 검증 결과 |
| `execution` | 저장 안 함 | AI 실행·성능 정보 |
| 모델명·토큰 수·처리 시간 | 저장 안 함 | AI 운영 로그의 책임 |

`batch_id`, `item_id` 미저장으로 인해 같은 배치를 재전송하면 중복 저장될 수
있다. 자동 재시도와 영속 idempotency 구조는 MVP 이후 별도 검토한다.

## 10. 저장 결과 예시

```json
{
  "question_id": 1001,
  "question_key": "2bbfd223-c913-4d84-ac47-2052565be12f",
  "version_no": 1,
  "usage_type": "MAIN_CHAPTER",
  "main_chapter_id": 2,
  "sub_chapter_id": null,
  "display_order": null,
  "question_type": "SCENARIO",
  "difficulty": "HARD",
  "prompt": "민서의 목표에 가장 적절한 선택은 무엇인가요?",
  "scenario_json": {
    "title": "금융상품 선택",
    "narrative": "민서는 안전하게 학업 비용을 마련하려고 한다.",
    "persona": {"name": "민서", "age": "18세", "job": "고등학생"},
    "requirements": {
      "assets": "저축 자금 100만 원",
      "risk": "원금 손실을 피하고 싶음",
      "goal": "6개월 뒤 학업 비용 마련"
    },
    "market": {
      "title": "시장 정보",
      "reference_at": "2026-08-10T00:00:00Z",
      "bullets": ["검증된 시장 정보"]
    },
    "constraints": ["약정 기간 동안 자금을 사용하지 않는다."],
    "paper_title": "선택 보고서"
  },
  "options_json": [
    {"key": "1", "label": "정기 예금에 맡긴다."},
    {"key": "2", "label": "주식을 단기 매매한다."},
    {"key": "3", "label": "파생상품에 투자한다."},
    {"key": "4", "label": "모두 현금으로 보관한다."}
  ],
  "correct_answer_json": {"key": "1"},
  "explanation": "원금 손실을 피하면서 기간을 정해 맡기려는 목표에 적합하다.",
  "generation_type": "AI",
  "source_refs_json": null,
  "status": "REVIEW",
  "created_by": 1,
  "published_at": null,
  "created_at": "2026-08-13T01:30:00Z"
}
```

## 11. ERD 영향

| 검토 항목 | 결과 | 근거 |
| --- | --- | --- |
| 신규 테이블 | 없음 | 기존 `quiz_questions` 사용 |
| 신규 컬럼 | 없음 | 일반 컬럼과 기존 JSON 컬럼에 모두 저장 가능 |
| 기존 컬럼 타입 변경 | 없음 | `source_refs_json` JSON 타입 유지 |
| 기존 CHECK 제약 변경 | 필요 | AI 문항도 `source_refs_json=NULL` 허용 |
| 신규 FK | 없음 | 기존 단원·사용자 FK 사용 |
| 기존 관계 변경 | 없음 | ID 검증 방식만 명확하게 변경 |
| 유일 제약 변경 | 없음 | 기존 `(question_key, version_no)` 사용 |
| AI 전용 퀴즈 테이블 | 없음 | 최종 원본을 AI DB에 중복 저장하지 않음 |

따라서 테이블·컬럼·관계 변경은 없지만 CHECK 제약 변경을 위한 Flyway
마이그레이션은 필요하다. BE 공통 퀴즈 JSON Schema, fixture와 검증 테스트도
AI 출처 nullable 정책에 맞게 수정한다.

## 12. 제외 범위와 후속 작업

이번 계약 문서에는 다음을 포함하지 않는다.

- Spring API 실행 코드
- AI 송신 코드
- 일일 퀘스트 FE 연동
- `quest_date` 마이그레이션
- 랜덤 출제와 HUMAN fallback
- 배치 스케줄링과 자동 재시도
- 기존 AI 문항 `RETIRED`
- 관리자 승인 화면·승인 API 구현(FE–Spring 후속 작업)
- 뉴스 출처 구조와 사용자 노출 정책

후속 구현에서는 Spring과 AI가 이 문서의 동일한 정상·오류 JSON 예제로 계약
테스트를 작성해야 한다.
