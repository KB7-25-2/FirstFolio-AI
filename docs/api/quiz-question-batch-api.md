# AI–Spring 퀴즈 배치 전달 API

## 1. 문서 목적

이 문서는 AI 서버가 생성과 자동 검증을 완료한 퀴즈를 Spring Legacy
메인 서버에 배치로 전달하기 위한 내부 REST API 계약을 정의한다.

- AI 서버: 정기 퀴즈 생성, 근거 연결, 자동 검증과 전달
- Spring 서버: 요청 검증, 단원 연결, 메인 DB 저장과 검수 상태 관리
- Frontend: 이 API를 직접 호출하지 않음

Spring 구현 코드는 별도의 `ai` 또는 `internal` 최상위 패키지를 만들지
않고 `org.firstfolio.quiz` 도메인에 둔다.

## 2. API 개요

| 항목 | 내용 |
| --- | --- |
| 메서드 | `POST` |
| API 명세 표기 | `/internal/quiz-questions/batches` |
| 실제 호출 경로 | `/api/internal/quiz-questions/batches` |
| Content-Type | `application/json` |
| 호출 주체 | AI 서버 |
| 수신 주체 | Spring Legacy 서버 |
| 요청당 항목 수 | 최소 1건, 최대 100건 |
| 성공 항목 최초 상태 | `REVIEW` |

### 2.1 경로 표기 규칙

팀 API 명세에서는 공통 접두사 `/api`를 생략하고
`/internal/quiz-questions/batches`로 표기한다. 클라이언트가 실제로 호출할 때는
`/api`를 포함한 `/api/internal/quiz-questions/batches`를 사용한다.

## 3. 인증과 요청 헤더

| 헤더 | 현재 필수 | 운영 연동 시 필수 | 설명 |
| --- | --- | --- | --- |
| `Content-Type: application/json` | Y | Y | JSON 요청 본문 |
| `X-Internal-API-Key` | N | Y | AI–Spring 서버 간 내부 인증 키 |

계약 문서화, 로컬 Mock, Postman과 통합 테스트 단계에서는 인증을
적용하지 않는다. 운영 연동 단계에서 `X-Internal-API-Key`를 필수로
적용한다. 인증을 적용하기 전에는 이 API를 외부에 배포하지 않는다.

## 4. 요청 구조

### 4.1 최상위 필드

| 필드 | 타입 | 필수 | 규칙 |
| --- | --- | --- | --- |
| `batch_id` | UUID 문자열 | Y | AI가 배치당 하나를 생성 |
| `items` | array | Y | 1~100개의 항목 |

### 4.2 `items` 항목

| 필드 | 타입 | 필수 | 규칙 |
| --- | --- | --- | --- |
| `item_id` | UUID 문자열 | Y | 항목별 식별자. 한 요청 내 중복 금지 |
| `quiz` | object | Y | 자동 검증을 통과한 퀴즈 |

### 4.3 `quiz` 필드

| 필드 | 타입 | 필수 | 규칙 |
| --- | --- | --- | --- |
| `usage_type` | string | Y | `SUB_CHAPTER`, `MAIN_CHAPTER` |
| `question_type` | string | Y | `TRUE_FALSE`, `SINGLE_CHOICE`, `SCENARIO` |
| `prompt` | string | Y | 빈 값이 아닌 질문 문장 |
| `scenario_json` | object \| null | Y | `SCENARIO`이면 객체, 나머지는 `null` |
| `options` | array | Y | 문제 유형에 맞는 선택지 |
| `correct_answer` | object | Y | 정답 `option_id` |
| `explanation` | string | Y | 빈 값이 아닌 정답 해설 |
| `difficulty` | string | Y | `EASY`, `MEDIUM`, `HARD` |
| `source_refs` | array | Y | 하나 이상의 근거 출처 |

AI 내부 결과의 `validation`, `execution`, 입력·출력 토큰 수와 처리 시간은
Spring에 전달하지 않는다. AI 내부 `quiz.citations`도 전송 필드로 그대로
사용하지 않고, 출처 메타데이터가 포함된 `source_refs`로 전달한다.

### 4.4 `scenario_json` 필드

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `character` | string | Y | 가상 인물과 상황 |
| `financial_context` | string | Y | 금융 환경과 판단 맥락 |
| `constraints` | string[] | Y | 판단에 필요한 제약 조건 |

### 4.5 `options` 항목

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `option_id` | string | Y | OX는 `O`/`X`, 나머지는 `1`~`4` |
| `text` | string | Y | OX는 `O`/`X`, 나머지는 선택지 문구 |

### 4.6 `correct_answer` 필드

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `option_id` | string | Y | `options`에 존재하는 하나의 `option_id` |

### 4.7 `source_refs` 항목

| 필드 | 타입 | 필수 | Nullable | 설명 |
| --- | --- | --- | --- | --- |
| `document_id` | integer | Y | N | AI 문서 식별자 |
| `chunk_key` | string | Y | N | 근거 청크 식별자 |
| `title` | string | Y | N | 문서 제목 |
| `heading` | string \| null | Y | Y | 청크의 구조적 제목과 Spring 단원 매핑 기준 |
| `source_url` | string \| null | Y | Y | 원문 URL |
| `published_at` | ISO 8601 date-time \| null | Y | Y | 원문 발행 시각 |
| `evidence_text` | string | Y | N | 정답과 해설의 근거 부분 |

`reference_at`은 현재 교과서 MVP 계약에서 제외한다. 뉴스·법령·시장 자료의
기준 시점은 해당 콘텐츠를 연동할 때 별도로 확정한다.

## 5. 문제 유형별 규칙

| 문제 유형 | `usage_type` | 선택지 ID·문구 | `scenario_json` |
| --- | --- | --- | --- |
| `TRUE_FALSE` | `SUB_CHAPTER` | `O`, `X` | `null` |
| `SINGLE_CHOICE` | `SUB_CHAPTER` | `1`, `2`, `3`, `4` | `null` |
| `SCENARIO` | `MAIN_CHAPTER` | `1`, `2`, `3`, `4` | 필수 객체 |

`MULTIPLE_CHOICE`는 BE ERD가 수용할 수 있는 유형이지만 이 API 계약에서는
지원하지 않는다.

## 6. 요청 JSON 예제

아래 예제는 세 가지 지원 유형을 한 배치에 함께 전달한다.

```json
{
  "batch_id": "6ae92192-73dc-4e2e-b7af-4f81f5ab84fe",
  "items": [
    {
      "item_id": "c33132f0-350f-4d2b-85a6-44f147d0de30",
      "quiz": {
        "usage_type": "SUB_CHAPTER",
        "question_type": "TRUE_FALSE",
        "prompt": "요구불 예금은 예금자가 원할 때 입출금할 수 있다.",
        "scenario_json": null,
        "options": [
          {"option_id": "O", "text": "O"},
          {"option_id": "X", "text": "X"}
        ],
        "correct_answer": {"option_id": "O"},
        "explanation": "요구불 예금은 수시로 입출금이 자유로운 예금이다.",
        "difficulty": "EASY",
        "source_refs": [
          {
            "document_id": 47,
            "chunk_key": "47:189",
            "title": "금융 교과서",
            "heading": "저축 상품의 종류와 특징",
            "source_url": null,
            "published_at": null,
            "evidence_text": "요구불 예금이란 수시로 하는 입출금이 자유롭다."
          }
        ]
      }
    },
    {
      "item_id": "6fbbb556-754d-4033-af8c-8b3b0f1821d4",
      "quiz": {
        "usage_type": "SUB_CHAPTER",
        "question_type": "SINGLE_CHOICE",
        "prompt": "정기 예금에 대한 설명으로 올바른 것은?",
        "scenario_json": null,
        "options": [
          {"option_id": "1", "text": "정한 기간 동안 돈을 맡기는 저축성 예금이다."},
          {"option_id": "2", "text": "언제나 자유롭게 입출금하는 것이 목적이다."},
          {"option_id": "3", "text": "원금 손실을 전제로 한 투자 상품이다."},
          {"option_id": "4", "text": "예치 기간을 약정하지 않는다."}
        ],
        "correct_answer": {"option_id": "1"},
        "explanation": "정기 예금은 일정한 액수를 정해진 기간 동안 맡기는 저축성 예금이다.",
        "difficulty": "MEDIUM",
        "source_refs": [
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
      }
    },
    {
      "item_id": "1b06beb3-35a1-45ec-984a-2ff55f04ac35",
      "quiz": {
        "usage_type": "MAIN_CHAPTER",
        "question_type": "SCENARIO",
        "prompt": "민지의 목적에 가장 잘 맞는 저축 방법은?",
        "scenario_json": {
          "character": "고등학생 민지는 모아 둔 돈을 안전하게 관리하고 싶다.",
          "financial_context": "지금 가진 돈을 한 번에 맡길 수 있다.",
          "constraints": [
            "약정 기간 동안 돈을 사용할 계획이 없다.",
            "원금 손실을 피하고 싶다."
          ]
        },
        "options": [
          {"option_id": "1", "text": "정기 예금에 맡긴다."},
          {"option_id": "2", "text": "주식을 단기 매매한다."},
          {"option_id": "3", "text": "원금 손실 위험이 큰 파생상품에 투자한다."},
          {"option_id": "4", "text": "당장 사용할 수 있도록 모두 현금으로 보관한다."}
        ],
        "correct_answer": {"option_id": "1"},
        "explanation": "약정 기간 동안 사용할 계획이 없고 원금 손실을 피하려는 목적에는 정기 예금이 적합하다.",
        "difficulty": "HARD",
        "source_refs": [
          {
            "document_id": 47,
            "chunk_key": "47:190",
            "title": "금융 교과서",
            "heading": "저축 상품의 종류와 특징",
            "source_url": null,
            "published_at": null,
            "evidence_text": "정기 예금은 일정한 액수의 돈을 은행에 맡겨 두고 정하는 기간 동안 인출하지 않겠다고 은행과 약속하는 형식의 예금이다."
          },
          {
            "document_id": 47,
            "chunk_key": "47:188",
            "title": "금융 교과서",
            "heading": "저축 상품과 투자 상품",
            "source_url": null,
            "published_at": null,
            "evidence_text": "저축 상품은 돈을 맡긴 은행이 망하지 않는 한 원금이 보장된다."
          }
        ]
      }
    }
  ]
}
```

## 7. Spring 검증과 단원 매핑

Spring은 요청을 DB에 저장하기 전에 최대 100건 전체를 먼저 검증한다.

1. 배치 구조, 건수, UUID와 `item_id` 중복을 검증한다.
2. 항목별 퀴즈 필드와 문제 유형 규칙을 검증한다.
3. `usage_type`과 `source_refs.heading`을 정규화해 단원을 찾는다.
4. 정확히 하나의 단원과 일치할 때만 저장 대상으로 분류한다.
5. 일치 항목이 없거나 둘 이상이면 `CHAPTER_MAPPING_FAILED`로 거절한다.

유사도로 단원을 추측하거나, 단원 ID를 찾지 못한 문항을 단원 없이 저장하지
않는다. 실제 매핑 품질은 기존 AI JSONL과 BE 커리큘럼을 연결하는 통합
테스트 단계에서 검증한다.

## 8. 저장과 트랜잭션 정책

1. 검증 또는 단원 매핑에 실패한 항목은 `REJECTED`로 분류한다.
2. 유효한 항목만 하나의 DB 트랜잭션으로 저장한다.
3. 저장에 성공한 항목은 `ACCEPTED`로 응답한다.
4. 유효한 항목의 DB 저장 자체가 실패하면 저장 대상 전체를 롤백하고 `500`을
   반환한다.
5. 모든 항목이 거절되어도 요청 구조 자체가 유효하면 `200`을 반환한다.
6. AI 서버는 이 API의 실패 항목을 자동으로 재전송하지 않는다.

Spring이 성공 항목을 저장할 때 다음 값을 생성하거나 결정한다.

| 항목 | 저장 정책 |
| --- | --- |
| `question_id` | MySQL `AUTO_INCREMENT` |
| `question_key` | Spring이 생성한 UUID |
| `version_no` | `1` |
| `status` | `REVIEW` |
| `main_chapter_id` | 단원 매핑 결과 |
| `sub_chapter_id` | 단원 매핑 결과. `MAIN_CHAPTER`는 `NULL` |
| `created_by` | 현재는 관리자 테스트 계정 ID, 운영은 AI 배치 전용 시스템 사용자 ID |
| `created_at` | Spring DB 저장 시각 |
| `published_at` | 최초 저장 시 `NULL` |
| `display_order` | 최초 저장 시 `NULL` |

AI 요청에는 이 필드를 포함하지 않는다.

## 9. 응답

### 9.1 HTTP 상태

| 상태 | 의미 |
| --- | --- |
| `200 OK` | 전체 성공, 부분 성공 또는 전체 항목 거절 |
| `400 Bad Request` | 배치 최상위 요청 구조 오류 |
| `401 Unauthorized` | 운영 인증 적용 후 내부 API 키 오류 또는 누락 |
| `500 Internal Server Error` | 유효한 저장 대상의 DB 트랜잭션 실패 |

### 9.2 전체 성공 예제

```json
{
  "batch_id": "6ae92192-73dc-4e2e-b7af-4f81f5ab84fe",
  "total": 2,
  "accepted": 2,
  "rejected": 0,
  "items": [
    {
      "item_id": "c33132f0-350f-4d2b-85a6-44f147d0de30",
      "result": "ACCEPTED",
      "question_id": 1001,
      "status": "REVIEW"
    },
    {
      "item_id": "6fbbb556-754d-4033-af8c-8b3b0f1821d4",
      "result": "ACCEPTED",
      "question_id": 1002,
      "status": "REVIEW"
    }
  ]
}
```

### 9.3 부분 성공 예제

```json
{
  "batch_id": "6ae92192-73dc-4e2e-b7af-4f81f5ab84fe",
  "total": 2,
  "accepted": 1,
  "rejected": 1,
  "items": [
    {
      "item_id": "c33132f0-350f-4d2b-85a6-44f147d0de30",
      "result": "ACCEPTED",
      "question_id": 1001,
      "status": "REVIEW"
    },
    {
      "item_id": "6fbbb556-754d-4033-af8c-8b3b0f1821d4",
      "result": "REJECTED",
      "error_code": "CHAPTER_MAPPING_FAILED",
      "error_message": "출처 제목과 일치하는 단원을 하나로 확정할 수 없습니다."
    }
  ]
}
```

### 9.4 `400 Bad Request` 예제

```json
{
  "error_code": "INVALID_BATCH_REQUEST",
  "error_message": "items는 1건 이상이어야 하며 각 item_id는 중복될 수 없습니다."
}
```

항목이 100건을 초과한 경우는 `BATCH_SIZE_EXCEEDED`를 사용한다.

### 9.5 `500 Internal Server Error` 예제

```json
{
  "error_code": "INTERNAL_SERVER_ERROR",
  "error_message": "퀴즈 배치를 저장하지 못했습니다."
}
```

이 응답을 반환하기 전에 저장 대상 전체를 롤백한다.

### 9.6 `401 Unauthorized` 예제

```json
{
  "error_code": "UNAUTHORIZED",
  "error_message": "내부 API 인증에 실패했습니다."
}
```

## 10. 오류 코드

### 10.1 배치 전체 오류

| 오류 코드 | HTTP | 의미 |
| --- | --- | --- |
| `INVALID_BATCH_REQUEST` | 400 | 최상위 구조, UUID, 필수 필드 또는 중복 `item_id` 오류 |
| `BATCH_SIZE_EXCEEDED` | 400 | `items`가 100건 초과 |
| `UNAUTHORIZED` | 401 | 운영 연동에서 내부 API 키 오류 또는 누락 |
| `INTERNAL_SERVER_ERROR` | 500 | DB 트랜잭션 또는 예상하지 못한 서버 오류 |

### 10.2 항목별 오류

| 오류 코드 | 의미 |
| --- | --- |
| `INVALID_QUIZ_PAYLOAD` | 퀴즈 JSON 구조 또는 필수 필드 오류 |
| `INVALID_USAGE_TYPE` | 지원하지 않는 `usage_type` 또는 문제 유형과의 불일치 |
| `INVALID_QUESTION_TYPE` | 지원하지 않는 `question_type` |
| `INVALID_DIFFICULTY` | 난이도 누락 또는 지원하지 않는 값 |
| `INVALID_OPTIONS` | 선택지 개수, ID, 문구 또는 중복 오류 |
| `INVALID_CORRECT_ANSWER` | 정답이 선택지에 없거나 단일 정답 규칙 위반 |
| `INVALID_SCENARIO` | 시나리오 필수·금지 규칙 또는 내부 필드 오류 |
| `SOURCE_REQUIRED` | 근거 출처 누락 또는 빈 배열 |
| `CHAPTER_MAPPING_FAILED` | 정규화한 제목과 일치하는 단원이 없거나 둘 이상 |

DB 저장 실패는 항목별 `QUIZ_SAVE_FAILED`로 반환하지 않는다. 저장 대상
전체를 롤백한 뒤 `INTERNAL_SERVER_ERROR`로 반환한다.

## 11. 알려진 제한사항

- `batch_id`와 `item_id`는 BE DB에 저장하지 않는다.
- 같은 배치를 다시 전송하면 동일한 퀴즈가 중복 저장될 수 있다.
- 자동 재전송과 idempotency 저장 구조는 현재 범위에 포함하지 않는다.
- `source_refs.heading`과 BE 단원명의 표기 차이로 매핑이 실패할 수 있다.
- 뉴스·법령·시장 자료의 기준 시점 필드는 후속 계약에서 확정한다.
- 이 계약으로 BE ERD의 테이블, 컬럼, 제약과 관계를 변경하지 않는다.

## 12. 후속 검증 항목

| 발견한 문제 | 영향 | 확인 단계 | 작업 전 논의 |
| --- | --- | --- | --- |
| 단원명 표기 차이로 매핑 실패 가능 | 정상 퀴즈가 `REJECTED`로 처리될 수 있음 | AI JSONL과 BE 커리큘럼 통합 테스트 | 필요 |
| 운영 인증 미적용 상태의 내부 API 노출 위험 | 미인증 요청으로 퀴즈가 저장될 수 있음 | 운영 연동과 배포 | 필요 |
| 동일 배치 재전송 시 중복 저장 가능 | 검수 대기 문항이 중복 생성될 수 있음 | MVP 운영 결과 검토 후 idempotency 개선 판단 | 필요 |
| 뉴스·법령·시장 자료의 기준 시점 계약 부재 | 최신성이 중요한 문항의 추적 정보가 부족할 수 있음 | 해당 문서 유형 연동 전 | 필요 |
