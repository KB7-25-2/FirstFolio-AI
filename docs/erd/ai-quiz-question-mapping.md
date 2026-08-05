# AI 퀴즈 JSON–BE ERD 매핑과 영향 검토

## 1. 문서 목적

이 문서는 AI 서버가 전달한 퀴즈 JSON을 Spring Legacy 서버가 BE
`quiz_questions` 테이블에 저장할 때의 필드 매핑과 기존 ERD 영향을 정의한다.

상세한 요청·응답과 오류 처리는
[`AI–Spring 퀴즈 배치 전달 API`](../api/quiz-question-batch-api.md)를 따른다.

## 2. 저장 원칙

- 자동 검증을 통과한 AI 퀴즈만 Spring에 전달한다.
- Spring은 API 스키마, 문제 유형 규칙과 단원 매핑을 다시 검증한다.
- 유효한 퀴즈는 `quiz_questions`에 문항 버전 하나당 한 행으로 저장한다.
- 최초 저장 상태는 `REVIEW`이며 즉시 게시하지 않는다.
- AI 서버는 BE 메인 DB를 직접 수정하지 않는다.
- AI의 생성 실행 정보와 검증 상태는 BE 퀴즈 원본에 저장하지 않는다.

## 3. AI 요청–`quiz_questions` 컬럼 매핑

### 3.1 AI가 전달하는 퀴즈 필드

| AI 요청 필드 | AI JSON 타입 | BE 컬럼 | BE 타입 | 매핑 방식 | 비고 |
| --- | --- | --- | --- | --- | --- |
| `quiz.usage_type` | string | `usage_type` | `VARCHAR(30)` | 그대로 저장 | 이 API는 `SUB_CHAPTER`, `MAIN_CHAPTER`만 허용 |
| `quiz.question_type` | string | `question_type` | `VARCHAR(30)` | 그대로 저장 | `TRUE_FALSE`, `SINGLE_CHOICE`, `SCENARIO`만 허용 |
| `quiz.prompt` | string | `prompt` | `TEXT` | 그대로 저장 | 시나리오와 분리된 질문 문장 |
| `quiz.scenario_json` | object 또는 null | `scenario_json` | `JSON` | JSON 객체 또는 SQL `NULL` | `SCENARIO`일 때만 객체 필수 |
| `quiz.options` | array | `options_json` | `JSON` | 배열 그대로 JSON 저장 | 해당 API에서는 필수 |
| `quiz.correct_answer` | object | `correct_answer_json` | `JSON` | 객체 그대로 JSON 저장 | 선택지에 존재하는 단일 `option_id` |
| `quiz.explanation` | string | `explanation` | `TEXT` | 그대로 저장 | 빈 값 금지 |
| `quiz.difficulty` | string | `difficulty` | `VARCHAR(20)` | 그대로 저장 | `EASY`, `MEDIUM`, `HARD` |
| `quiz.source_refs` | array | `source_refs_json` | `JSON` | 배열 그대로 JSON 저장 | 하나 이상이어야 함 |

### 3.2 JSON 컬럼 저장 예제

#### `options` → `options_json`

```json
[
  {"option_id": "1", "text": "정기 예금에 맡긴다."},
  {"option_id": "2", "text": "주식을 단기 매매한다."},
  {"option_id": "3", "text": "파생상품에 투자한다."},
  {"option_id": "4", "text": "모두 현금으로 보관한다."}
]
```

#### `correct_answer` → `correct_answer_json`

```json
{"option_id": "1"}
```

#### `scenario_json` → `scenario_json`

```json
{
  "character": "고등학생 민지는 모아 둔 돈을 안전하게 관리하고 싶다.",
  "financial_context": "지금 가진 돈을 한 번에 맡길 수 있다.",
  "constraints": [
    "약정 기간 동안 돈을 사용할 계획이 없다.",
    "원금 손실을 피하고 싶다."
  ]
}
```

`TRUE_FALSE`와 `SINGLE_CHOICE`는 `scenario_json` 컬럼에 SQL `NULL`을 저장한다.

## 4. `source_refs_json` 저장 구조

### 4.1 저장 예제

AI 요청의 `source_refs` 배열을 `source_refs_json` 컬럼에 그대로 저장한다.

```json
[
  {
    "document_id": 47,
    "chunk_key": "47:190",
    "title": "금융 교과서",
    "heading": "저축 상품의 종류와 특징",
    "source_url": null,
    "published_at": null,
    "evidence_text": "정기 예금은 일정한 액수의 돈을 은행에 맡겨 두고 정하는 기간 동안 인출하지 않겠다고 은행과 약속하는 형식의 예금이다."
  }
]
```

### 4.2 하위 필드별 용도

| `source_refs_json` 필드 | 저장 값 | 용도 |
| --- | --- | --- |
| `document_id` | AI 문서의 숫자 ID | 원문 추적 |
| `chunk_key` | `{document_id}:{chunk_order}` 형식 식별자 | AI 청크·인덱스와 연결 |
| `title` | 문서 제목 | 검수 화면과 출처 표시 |
| `heading` | 구조적 제목 또는 `null` | Spring 단원 매핑과 출처 표시 |
| `source_url` | 원문 URL 또는 `null` | 원문 접근 |
| `published_at` | ISO 8601 발행 시각 또는 `null` | 출처 발행 시각 추적 |
| `evidence_text` | 근거 청크의 부분 문자열 | 정답·해설 근거 검수 |

`reference_at`은 현재 교과서 MVP 저장 구조에 포함하지 않는다. BE의
`source_refs_json`은 JSON 타입이므로 이 제외를 위한 ERD 변경은 필요하지 않다.
뉴스·법령·시장 자료를 연동할 때 기준 시점 계약을 별도로 확정한다.

## 5. Spring이 생성하거나 결정하는 필드

AI는 아래 필드를 요청에 포함하지 않는다.

| `quiz_questions` 컬럼 | 생성·결정 주체 | 최초 저장 값 | 설명 |
| --- | --- | --- | --- |
| `question_id` | MySQL | `AUTO_INCREMENT` | 특정 문항 버전 행의 PK |
| `question_key` | Spring | 새 UUID | 후속 버전을 묶는 논리 키 |
| `version_no` | Spring | `1` | AI가 전달한 최초 문항 버전 |
| `main_chapter_id` | Spring | 단원 매핑 결과 | 두 `usage_type` 모두 소속 대단원 저장 |
| `sub_chapter_id` | Spring | 단원 매핑 결과 또는 `NULL` | `SUB_CHAPTER`는 소단원, `MAIN_CHAPTER`는 `NULL` |
| `display_order` | Spring | `NULL` | 검수·배포 전에는 순서 미지정 |
| `status` | Spring | `REVIEW` | 관리자 검수 대기 |
| `created_by` | Spring 설정 | 로컬 관리자 테스트 계정 ID | 운영은 AI 배치 전용 시스템 사용자 ID로 교체 |
| `published_at` | Spring | `NULL` | 게시 전이므로 빈 값 |
| `created_at` | Spring | DB 저장 시각 | 최초 문항 생성 시각 |

### 5.1 `question_key`와 버전

- 이 API로 새로 받은 퀴즈는 Spring이 새 `question_key`를 생성한다.
- 최초 `version_no`는 `1`이다.
- 검수 후 문항 변경은 기존 BE 버전 정책에 따라 새 행을 생성한다.
- AI `batch_id`나 `item_id`를 `question_key`로 재사용하지 않는다.

### 5.2 `status=REVIEW` 정책

- AI 자동 검증 통과는 BE 게시 승인을 의미하지 않는다.
- 저장 직후 문항은 `REVIEW` 상태로 관리자 검수 대상이 된다.
- `published_at`과 `display_order`는 최초 저장 시 `NULL`이다.
- 검수·게시는 기존 BE 콘텐츠 관리 정책을 따르며 AI가 결정하지 않는다.

### 5.3 `created_by` 정책

- 로컬·Mock·통합 테스트는 기존 관리자 테스트 계정의 `user_id`를 Spring
  설정값으로 사용한다.
- 운영 연동 전 AI 배치 전용 시스템 사용자의 `user_id`로 설정을 교체한다.
- 이 계약 문서화 범위에서 `users` 행을 생성하거나 ERD를 변경하지 않는다.

## 6. 단원 연결 규칙

Spring은 AI가 BE 단원 ID를 직접 지정하도록 하지 않고 `usage_type`과
`source_refs.heading`으로 단원을 찾는다.

### 6.1 `SUB_CHAPTER`

1. `source_refs.heading`을 BE 소단원명 비교 규칙에 맞게 정규화한다.
2. 정확히 하나의 `sub_chapters` 행과 일치하면 `sub_chapter_id`를 저장한다.
3. 일치한 소단원의 부모 `main_chapter_id`도 함께 저장한다.
4. 일치 항목이 없거나 둘 이상이면 `CHAPTER_MAPPING_FAILED`로 거절한다.

### 6.2 `MAIN_CHAPTER`

1. `source_refs.heading`을 BE 대단원명 비교 규칙에 맞게 정규화한다.
2. 정확히 하나의 `main_chapters` 행과 일치하면 `main_chapter_id`를 저장한다.
3. `sub_chapter_id`는 `NULL`로 저장한다.
4. 일치 항목이 없거나 둘 이상이면 `CHAPTER_MAPPING_FAILED`로 거절한다.

### 6.3 공통 금지 규칙

- 유사도 기반으로 단원을 추측하지 않는다.
- 단원 ID가 없는 상태로 문항을 저장하지 않는다.
- AI 요청에 `main_chapter_id`나 `sub_chapter_id`를 임의로 추가하지 않는다.
- 단원 매핑 품질은 AI JSONL과 BE 커리큘럼을 연결하는 통합 테스트에서 측정한다.

## 7. API 규칙과 ERD의 넓은 허용 범위

BE ERD는 관리자 등록, 레벨 테스트, 일일 퀴즈 등 다른 사용 목적도 수용하므로
일부 JSON 컬럼과 연결 컬럼에 `NULL`을 허용한다. AI 배치 수신 API는 이보다
엄격하게 검증한다.

| BE ERD 허용 범위 | AI 배치 수신 API 규칙 | ERD 변경 |
| --- | --- | --- |
| `difficulty`는 `NULL` 허용 | `difficulty` 필수 | 불필요 |
| `options_json`은 `NULL` 허용 | 세 지원 유형 모두 선택지 필수 | 불필요 |
| `source_refs_json`은 `NULL` 허용 | `source_refs` 하나 이상 필수 | 불필요 |
| `question_type`은 `MULTIPLE_CHOICE` 수용 | 해당 유형 전송 금지 | 불필요 |
| `usage_type`은 레벨·일일 퀴즈 용도 수용 | `SUB_CHAPTER`, `MAIN_CHAPTER`만 허용 | 불필요 |
| `scenario_json`은 `NULL` 허용 | `SCENARIO`일 때만 객체 필수 | 불필요 |

API DTO와 서비스 검증으로 이 규칙을 적용하며 기존 컬럼의 넓은 허용 범위를
바꾸지 않는다.

## 8. BE에 저장하지 않는 AI 필드

| AI 필드 | 저장 여부 | 사유 |
| --- | --- | --- |
| `batch_id` | 저장 안 함 | 전송 배치 추적용이며 현재 BE 영속화 범위에서 제외 |
| `item_id` | 저장 안 함 | 응답 항목 연결용이며 현재 BE 영속화 범위에서 제외 |
| `quiz.citations` | 별도 필드로 저장 안 함 | 같은 `chunk_key`의 `sources` 메타데이터와 결합해 `source_refs_json`으로 저장 |
| `validation` | 저장 안 함 | AI 내부 자동 검증 결과 |
| `execution` | 저장 안 함 | AI 생성 실행 정보 |
| `execution.model` | 저장 안 함 | AI 운영·로깅 정보 |
| `execution.input_tokens` | 저장 안 함 | AI 비용·로깅 정보 |
| `execution.output_tokens` | 저장 안 함 | AI 비용·로깅 정보 |
| `execution.elapsed_ms` | 저장 안 함 | AI 성능·로깅 정보 |

AI 내부 생성·검증·실행 정보는 AI 로그와 로컬 JSONL의 책임이다. BE의
서비스용 퀴즈 원본에 중복해 저장하지 않는다.

`quiz.citations` 자체는 폐기하지 않는다. citation의 `chunk_key`와 검증된
`evidence_text`를 기준으로 같은 `chunk_key`의 `sources` 메타데이터를 결합해
`source_refs_json` 항목을 만든다. 따라서 Spring에는 citation 배열과 source
배열을 각각 전달하지 않고, 두 정보를 합친 `source_refs`만 전달한다.

## 9. 저장 결과 예시

다음은 `SCENARIO` 항목 하나가 단원 매핑과 저장에 성공했을 때의 논리적 저장
결과다. 실제 SQL 문이 아니며 ID와 시각은 예시다.

```json
{
  "question_id": 1001,
  "question_key": "2bbfd223-c913-4d84-ac47-2052565be12f",
  "version_no": 1,
  "usage_type": "MAIN_CHAPTER",
  "main_chapter_id": 10,
  "sub_chapter_id": null,
  "display_order": null,
  "question_type": "SCENARIO",
  "difficulty": "HARD",
  "prompt": "민지의 목적에 가장 잘 맞는 저축 방법은?",
  "scenario_json": {
    "character": "고등학생 민지는 모아 둔 돈을 안전하게 관리하고 싶다.",
    "financial_context": "지금 가진 돈을 한 번에 맡길 수 있다.",
    "constraints": ["약정 기간 동안 돈을 사용할 계획이 없다."]
  },
  "options_json": [
    {"option_id": "1", "text": "정기 예금에 맡긴다."},
    {"option_id": "2", "text": "주식을 단기 매매한다."},
    {"option_id": "3", "text": "파생상품에 투자한다."},
    {"option_id": "4", "text": "모두 현금으로 보관한다."}
  ],
  "correct_answer_json": {"option_id": "1"},
  "explanation": "사용 계획이 없고 원금 손실을 피하려는 목적에는 정기 예금이 적합하다.",
  "source_refs_json": [
    {
      "document_id": 47,
      "chunk_key": "47:190",
      "title": "금융 교과서",
      "heading": "저축 상품의 종류와 특징",
      "source_url": null,
      "published_at": null,
      "evidence_text": "정기 예금은 일정한 액수의 돈을 은행에 맡겨 두는 예금이다."
    }
  ],
  "status": "REVIEW",
  "created_by": 1,
  "published_at": null,
  "created_at": "2026-08-05T10:30:00+09:00"
}
```

## 10. ERD 영향 검토

| 검토 항목 | 결과 | 근거 |
| --- | --- | --- |
| 신규 테이블 | 없음 | 기존 `quiz_questions`에 퀴즈 원본과 출처 저장 가능 |
| 신규 컬럼 | 없음 | 요청 필드를 기존 일반 컬럼과 JSON 컬럼에 모두 매핑 가능 |
| 기존 컬럼 변경 | 없음 | API 검증으로 ERD의 넓은 널 허용 범위와 차이를 처리 |
| 신규 FK | 없음 | 기존 `main_chapter_id`, `sub_chapter_id`, `created_by` 관계 사용 |
| 기존 관계 변경 | 없음 | 단원·사용자 연결 방식 유지 |
| 유일 제약 변경 | 없음 | 기존 `UNIQUE (question_key, version_no)` 사용 |
| AI 전용 퀴즈 테이블 | 없음 | 메인 퀴즈 원본을 AI DB에 중복 저장하지 않음 |

따라서 이 API 계약을 적용하기 위한 BE ERD 변경은 없다.

## 11. 알려진 제한과 후속 검증

| 발견한 문제 | 영향 | 확인 단계 | 작업 전 논의 |
| --- | --- | --- | --- |
| `batch_id`, `item_id` 미저장 | 동일 배치 재전송 시 중복 저장 가능 | MVP 운영 결과로 idempotency 필요성 검토 | 필요 |
| `heading`과 BE 단원명의 표기 차이 | 정상 문항의 단원 매핑 실패 가능 | AI JSONL·BE 커리큘럼 통합 테스트 | 필요 |
| 단원 매핑 실패 반복 | AI 문서 구조 제목만으로 안정적 연결이 어려울 수 있음 | 통합 테스트 후 AI 청크와 BE 단원 ID 연결 방식 검토 | 필요 |
| 운영용 `created_by` 시스템 사용자 미준비 | 로컬 관리자 계정을 운영에서 재사용할 위험 | 운영 연동 전 설정값 교체 | 필요 |
| 뉴스·법령·시장 자료의 기준 시점 계약 부재 | 최신성이 중요한 문항의 추적 정보 부족 | 해당 문서 유형 연동 전 | 필요 |
