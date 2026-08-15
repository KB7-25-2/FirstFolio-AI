# AI–Spring 퀴즈 생성 대상 조회·배치 전달 API

## 1. 문서 목적

이 문서는 AI 서버가 Spring Legacy 메인 서버에서 퀴즈 생성 대상을 조회하고,
생성·자동 검증을 완료한 퀴즈를 배치로 전달하기 위한 내부 REST API 계약을
정의한다.

- AI 서버: 생성 대상 조회, RAG 검색, 퀴즈 생성·검증과 배치 전달
- Spring 서버: 서비스 대상 단원 제공, 요청 재검증, 메인 DB에 `REVIEW` 상태로 저장
- 관리자(FE 관리자 페이지): 배치 일괄 승인 또는 개별 승인으로 `PUBLISHED` 전환
- Frontend: 두 내부 API를 직접 호출하지 않음

관리자 승인 화면과 승인 API는 FE–Spring 내부 기능이며 이 문서가 정의하는
AI–Spring 계약에 포함하지 않는다. 다만 배치 저장 직후 상태가 `REVIEW`이고
관리자 승인 후 `PUBLISHED`로 전환된다는 상태 모델은 이 계약에 포함한다.

MVP 최초 배치는 AI 서버에서 수동으로 시작한다. Spring 서버가 AI 서버에
퀴즈 생성을 요청하는 API는 만들지 않는다.

## 2. 전체 호출 흐름

```text
AI 최초 배치 수동 실행
→ GET /api/internal/quiz-generation-targets
→ 서비스 대상 전체 대·소단원과 실제 DB ID 확인
→ 단원별 RAG 검색·퀴즈 생성·자동 검증
→ 조회한 단원 ID를 퀴즈 배치 항목에 연결
→ POST /api/internal/quiz-questions/batches
→ Spring 재검증·`REVIEW` 저장
→ 관리자 배치 일괄 승인 또는 개별 승인
→ `PUBLISHED` 전환, 랜덤 출제 대상 포함
```

생성 대상은 사용자가 선택한 개인 커리큘럼이 아니다. 현재 서비스 대상으로
활성화된 전체 대단원·소단원이다. 따라서 사용자별 커리큘럼 선택과 무관하게
각 단원의 문제 풀을 미리 준비한다.

## 3. 공통 인증

두 API는 기존 Spring 내부 호출 인증을 사용한다.

```http
X-Internal-Token: {INTERNAL_CALL_TOKEN}
```

- 환경변수 이름: `INTERNAL_CALL_TOKEN`
- 헤더 이름: `X-Internal-Token`
- 토큰이 없거나 일치하지 않으면 `403 INTERNAL_CALL_REQUIRED`
- 인증을 적용하지 않은 상태로 외부에 노출하지 않음

성공 응답은 Spring 공통 형식인 `{"data": ...}`로 감싸고, 오류 응답은
`{"error": {...}}` 형식을 사용한다.

---

## 4. 퀴즈 생성 대상 조회 API

### 4.1 개요

| 항목 | 내용 |
| --- | --- |
| 메서드 | `GET` |
| API 명세 표기 | `/internal/quiz-generation-targets` |
| 실제 호출 경로 | `/api/internal/quiz-generation-targets` |
| 호출 주체 | AI 서버 |
| 요청 본문 | 없음 |

AI는 퀴즈를 생성하기 전에 이 API를 호출한다. 응답의 단원 이름은 RAG 검색과
생성 주제로 사용하고, 단원 ID는 AI 배치 코드가 생성 결과에 연결한다. LLM이
단원 ID를 생성하거나 추측하지 않는다.

### 4.2 성공 응답

```json
{
  "data": {
    "main_chapters": [
      {
        "main_chapter_id": 2,
        "title": "예·적금",
        "chapter_type": "ASSET",
        "sub_chapters": [
          {
            "sub_chapter_id": 17,
            "main_chapter_id": 2,
            "title": "예금과 적금의 차이"
          },
          {
            "sub_chapter_id": 18,
            "main_chapter_id": 2,
            "title": "금리 이해하기"
          }
        ]
      }
    ]
  }
}
```

### 4.3 응답 필드

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `main_chapters` | array | Y | 현재 서비스 대상 대단원 목록 |
| `main_chapter_id` | integer | Y | BE 대단원 PK |
| `title` | string | Y | 대단원 이름 및 AI 생성 주제 |
| `chapter_type` | string | Y | BE 대단원 유형 |
| `sub_chapters` | array | Y | 해당 대단원의 서비스 대상 소단원 목록 |
| `sub_chapter_id` | integer | Y | BE 소단원 PK |
| `sub_chapters[].main_chapter_id` | integer | Y | 소단원이 속한 BE 대단원 PK |
| `sub_chapters[].title` | string | Y | 소단원 이름 및 AI 생성 주제 |

### 4.4 조회 정책

- 현재 서비스 대상으로 활성화된 대단원만 반환한다.
- 반환 대단원 아래의 활성 소단원만 반환한다.
- 사용자 ID, 개인 커리큘럼, 학습 진도와 오답 이력은 조회하지 않는다.
- 대단원과 소단원의 부모·자식 관계를 응답 구조로 고정한다.
- AI는 한 번의 수동 배치 실행 동안 조회 결과를 생성 대상 목록으로 사용한다.
- 조회 이후 단원 상태가 바뀔 수 있으므로 Spring은 배치 수신 시 다시 검증한다.

### 4.5 오류

| HTTP | 오류 코드 | 의미 |
| --- | --- | --- |
| `403` | `INTERNAL_CALL_REQUIRED` | 내부 토큰 누락·불일치 또는 서버 토큰 미설정 |
| `500` | `INTERNAL_ERROR` | 생성 대상 조회 중 예상하지 못한 서버 오류 |

---

## 5. 퀴즈 배치 전달 API

### 5.1 개요

| 항목 | 내용 |
| --- | --- |
| 메서드 | `POST` |
| API 명세 표기 | `/internal/quiz-questions/batches` |
| 실제 호출 경로 | `/api/internal/quiz-questions/batches` |
| Content-Type | `application/json` |
| 호출 주체 | AI 서버 |
| 요청당 항목 수 | 최소 1건, 최대 100건 |
| 성공 문항 최초 상태 | `REVIEW` |

`PUBLISHED` 전환은 이 API의 응답 범위가 아니다. 관리자가 FE 관리자 페이지에서
배치 단위 일괄 승인 또는 항목별 개별 승인을 하면 Spring이 별도 절차로
`PUBLISHED`로 전환한다. 랜덤 출제 조회는 `PUBLISHED` 상태만 대상으로 한다.

### 5.2 최상위 요청

| 필드 | 타입 | 필수 | 규칙 |
| --- | --- | --- | --- |
| `batch_id` | UUID 문자열 | Y | AI가 논리 배치당 하나 생성 |
| `items` | array | Y | 1~100개의 항목 |

### 5.3 배치 항목

| 필드 | 타입 | 필수 | 규칙 |
| --- | --- | --- | --- |
| `item_id` | UUID 문자열 | Y | 한 요청 내 중복 금지 |
| `quiz` | object | Y | 자동 검증을 통과한 퀴즈 |

### 5.4 `quiz` 필드

| 필드 | 타입 | 필수 | 규칙 |
| --- | --- | --- | --- |
| `usage_type` | string | Y | `SUB_CHAPTER`, `MAIN_CHAPTER` |
| `main_chapter_id` | integer | Y | 대상 조회 API에서 받은 대단원 ID |
| `sub_chapter_id` | integer \| null | Y | 소단원 문제는 ID, 대단원 문제는 `null` |
| `question_type` | string | Y | `TRUE_FALSE`, `SINGLE_CHOICE`, `SCENARIO` |
| `difficulty` | string | Y | `EASY`, `MEDIUM`, `HARD` |
| `prompt` | string | Y | 빈 값이 아닌 질문 문장 |
| `scenario_json` | object \| null | Y | `SCENARIO`만 BE 시나리오 객체 |
| `options_json` | array | Y | BE 선택지 배열 |
| `correct_answer_json` | object | Y | BE 단일 정답 객체 |
| `explanation` | string | Y | 빈 값이 아닌 정답 해설 |
| `source_refs_json` | null | N | MVP에서는 생략하거나 `null` 사용 |

AI 내부의 `citations`, `validation`, `execution`, 모델명, 토큰 수와 처리 시간은
Spring에 전달하지 않는다.

## 6. 문제 유형별 규칙

| 문제 유형 | `usage_type` | `main_chapter_id` | `sub_chapter_id` | `scenario_json` |
| --- | --- | --- | --- | --- |
| `TRUE_FALSE` | `SUB_CHAPTER` | 필수 | 필수 | `null` |
| `SINGLE_CHOICE` | `SUB_CHAPTER` | 필수 | 필수 | `null` |
| `SCENARIO` | `MAIN_CHAPTER` | 필수 | `null` | 필수 객체 |

`MULTIPLE_CHOICE`, `DAILY_GENERAL`, `DAILY_NEWS`는 이 배치 계약에서
지원하지 않는다.

### 6.1 선택지와 정답

선택지는 BE 스키마의 `key`, `label`, 선택적 `description`을 사용한다.

```json
{
  "key": "1",
  "label": "정기 예금에 맡긴다.",
  "description": null
}
```

- `TRUE_FALSE`: 정확히 `O`, `X` 두 선택지
- `SINGLE_CHOICE`, `SCENARIO`: `1`~`4` 네 선택지
- `description`: 없으면 생략하거나 `null`

정답은 선택지에 존재하는 하나의 키다.

```json
{
  "key": "1"
}
```

### 6.2 `scenario_json`

`SCENARIO`는 현재 BE 퀴즈 JSON Schema의 시나리오 구조를 사용한다.

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

## 7. MVP 출처 정책

- `source_refs_json` 컬럼은 향후 뉴스 도메인과 운영 추적 확장을 위해 유지한다.
- 이번 커리큘럼 퀴즈 배치에서는 출처를 조립하거나 사용자에게 노출하지 않는다.
- AI와 HUMAN 문항 모두 `source_refs_json=null`을 허용한다.
- AI는 배치 항목에서 `source_refs_json`을 생략하거나 `null`로 전달할 수 있다.
- Spring은 출처 누락을 문항 거절 사유로 사용하지 않는다.
- RAG가 여러 문서를 사용했더라도 MVP 저장을 위해 임의의 대표 출처를 만들지 않는다.
- 뉴스 도메인이 정의되면 출처 필드와 사용자 노출 정책을 별도 계약으로 확정한다.

현재 BE DB CHECK 제약은 AI 문항에 비어 있지 않은 출처 배열을 요구하므로,
별도 Flyway 마이그레이션에서 AI 문항도 `NULL`을 허용하도록 완화해야 한다.
공통 퀴즈 JSON Schema와 fixture도 같은 nullable 정책으로 변경한다.

## 8. 전체 요청 예제

```json
{
  "batch_id": "6ae92192-73dc-4e2e-b7af-4f81f5ab84fe",
  "items": [
    {
      "item_id": "c33132f0-350f-4d2b-85a6-44f147d0de30",
      "quiz": {
        "usage_type": "SUB_CHAPTER",
        "main_chapter_id": 2,
        "sub_chapter_id": 17,
        "question_type": "TRUE_FALSE",
        "difficulty": "EASY",
        "prompt": "정기 예금은 약정 기간 동안 돈을 맡기는 금융상품이다.",
        "scenario_json": null,
        "options_json": [
          {"key": "O", "label": "O"},
          {"key": "X", "label": "X"}
        ],
        "correct_answer_json": {"key": "O"},
        "explanation": "정기 예금은 일정 기간 돈을 맡기는 저축성 예금이다."
      }
    },
    {
      "item_id": "1b06beb3-35a1-45ec-984a-2ff55f04ac35",
      "quiz": {
        "usage_type": "MAIN_CHAPTER",
        "main_chapter_id": 2,
        "sub_chapter_id": null,
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
        "source_refs_json": null
      }
    }
  ]
}
```

## 9. Spring 검증 정책

Spring은 저장 전에 최대 100건 전체를 분류한다.

1. 최상위 구조, 건수, UUID와 `item_id` 중복을 검증한다.
2. 문제 유형별 필수 필드와 BE JSON 구조를 검증한다.
3. 대단원과 소단원의 존재 여부를 검증한다.
4. 소단원이 요청한 대단원에 실제로 속하는지 확인한다.
5. 단원이 현재 서비스 대상인지 다시 확인한다.
6. `usage_type`과 `question_type` 조합을 확인한다.
7. 선택지 키와 정답 키가 일치하는지 확인한다.

검증 실패 항목은 `REJECTED`로 분류하고 다른 정상 항목의 저장을 막지 않는다.
단원명이 비슷하다는 이유로 ID를 보정하거나 다른 단원으로 추측하지 않는다.

## 10. 저장과 트랜잭션 정책

1. 검증에 실패한 항목은 DB에 저장하지 않는다.
2. 유효한 항목만 하나의 DB 트랜잭션으로 저장한다.
3. 저장 성공 항목은 `ACCEPTED`로 응답한다.
4. 유효 항목 저장 중 DB 오류가 나면 저장 대상 전체를 롤백하고 `500`을 반환한다.
5. 모든 항목이 거절되어도 최상위 요청이 유효하면 `200`을 반환한다.
6. AI 서버의 자동 재전송은 MVP 범위에서 제외한다.

Spring이 성공 항목에 적용하는 값은 다음과 같다.

| 항목 | 저장 정책 |
| --- | --- |
| `question_id` | MySQL `AUTO_INCREMENT` |
| `question_key` | Spring이 생성한 새 고유 키 |
| `version_no` | `1` |
| `generation_type` | `AI` |
| `main_chapter_id` | 요청 ID 검증 후 저장 |
| `sub_chapter_id` | 요청 ID 검증 후 저장. 대단원 문제는 `NULL` |
| `display_order` | `NULL` |
| `source_refs_json` | `NULL` |
| `created_by` | AI 배치 전용 시스템 사용자 ID |
| `created_at` | Spring DB 저장 시각 |
| `status` | `REVIEW` |
| `published_at` | `NULL` |

AI 요청에는 위 자동 결정 필드를 포함하지 않는다. `status`가 `PUBLISHED`로
바뀌고 `published_at`이 채워지는 시점은 관리자 승인 이후이며 이 배치 API의
응답에는 반영되지 않는다.

## 11. 응답

### 11.1 전체 성공

```json
{
  "data": {
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
        "item_id": "1b06beb3-35a1-45ec-984a-2ff55f04ac35",
        "result": "ACCEPTED",
        "question_id": 1002,
        "status": "REVIEW"
      }
    ]
  }
}
```

### 11.2 부분 성공

```json
{
  "data": {
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
        "error_code": "INVALID_CHAPTER_SCOPE",
        "error_message": "요청한 소단원이 해당 대단원에 속하지 않습니다."
      }
    ]
  }
}
```

### 11.3 전체 항목 거절

```json
{
  "data": {
    "batch_id": "6ae92192-73dc-4e2e-b7af-4f81f5ab84fe",
    "total": 1,
    "accepted": 0,
    "rejected": 1,
    "items": [
      {
        "item_id": "6fbbb556-754d-4033-af8c-8b3b0f1821d4",
        "result": "REJECTED",
        "error_code": "CHAPTER_NOT_FOUND",
        "error_message": "요청한 단원을 찾을 수 없습니다."
      }
    ]
  }
}
```

### 11.4 최상위 요청 오류

```json
{
  "error": {
    "code": "INVALID_BATCH_REQUEST",
    "message": "items는 1건 이상이어야 하며 item_id는 중복될 수 없습니다.",
    "request_id": "req-01J5FOLIO8N2X"
  }
}
```

### 11.5 인증 실패

```json
{
  "error": {
    "code": "INTERNAL_CALL_REQUIRED",
    "message": "허용된 내부 호출이 아닙니다.",
    "request_id": "req-01J5FOLIO8N2X"
  }
}
```

### 11.6 HTTP 상태

| HTTP | 의미 |
| --- | --- |
| `200 OK` | 전체 성공, 부분 성공 또는 유효한 요청의 전체 항목 거절 |
| `400 Bad Request` | 최상위 요청 구조, UUID, 중복 또는 요청 건수 오류 |
| `403 Forbidden` | 내부 호출 인증 실패 |
| `500 Internal Server Error` | 유효 항목 DB 저장 실패 또는 예상하지 못한 서버 오류 |

## 12. 오류 코드

### 12.1 배치 전체 오류

| 오류 코드 | HTTP | 의미 |
| --- | --- | --- |
| `INVALID_BATCH_REQUEST` | 400 | 최상위 구조, UUID, 필수 필드 또는 중복 `item_id` 오류 |
| `BATCH_SIZE_EXCEEDED` | 400 | `items`가 100건 초과 |
| `INTERNAL_CALL_REQUIRED` | 403 | 내부 토큰 누락·불일치 또는 서버 토큰 미설정 |
| `INTERNAL_ERROR` | 500 | DB 트랜잭션 또는 예상하지 못한 서버 오류 |

### 12.2 항목별 오류

| 오류 코드 | 의미 |
| --- | --- |
| `INVALID_QUIZ_PAYLOAD` | 퀴즈 JSON 구조 또는 필수 필드 오류 |
| `INVALID_USAGE_TYPE` | 지원하지 않는 `usage_type` 또는 유형 조합 오류 |
| `INVALID_QUESTION_TYPE` | 지원하지 않는 `question_type` |
| `INVALID_DIFFICULTY` | 난이도 누락 또는 지원하지 않는 값 |
| `INVALID_CHAPTER_SCOPE` | 단원 ID 조합 또는 부모·자식 관계 오류 |
| `CHAPTER_NOT_FOUND` | 요청한 대단원 또는 소단원이 존재하지 않음 |
| `CHAPTER_NOT_ACTIVE` | 요청한 단원이 현재 서비스 대상이 아님 |
| `INVALID_OPTIONS` | 선택지 개수, 키, 문구 또는 중복 오류 |
| `INVALID_CORRECT_ANSWER` | 정답 키가 선택지에 없거나 단일 정답 규칙 위반 |
| `INVALID_SCENARIO` | 시나리오 필수·금지 규칙 또는 내부 필드 오류 |

DB 저장 실패는 항목별 오류로 바꾸지 않는다. 저장 대상 전체를 롤백한 뒤
`INTERNAL_ERROR`로 반환한다.

## 13. 알려진 제한사항

- `batch_id`, `item_id`는 MVP에서 BE DB에 저장하지 않는다.
- 같은 배치를 다시 전송하면 동일 퀴즈가 중복 저장될 수 있다.
- 자동 재전송과 영속 idempotency 구조는 MVP 범위에 포함하지 않는다.
- 성공 항목은 `REVIEW` 상태로 저장되며, 관리자 승인 전까지 랜덤 출제 대상이 아니다.
- 관리자 승인 화면·승인 API 자체는 이 문서 범위 밖이며 FE–Spring 후속 작업이다.
- 기존 AI 문항의 `RETIRED` 처리와 주기적 교체는 포함하지 않는다.
- 스케줄링과 일일 퀘스트 문제 생성은 별도 작업으로 다룬다.
- 출처 구조와 사용자 노출 정책은 뉴스 도메인 정의 후 별도로 확정한다.

## 14. 후속 구현 이슈

1. Spring 생성 대상 조회 API 구현
2. Spring 배치 수신·`REVIEW` 저장 구현
3. Flyway로 AI 문항의 `source_refs_json=NULL` 허용 CHECK 제약 변경
4. Spring 공통 퀴즈 JSON Schema·fixture의 nullable 정책 반영
5. AI 배치 요청 변환·송신 구현
6. 전체 서비스 대상 단원의 최초 수동 생성 배치 구현
7. FE 관리자 페이지의 배치 일괄 승인·개별 승인 → `PUBLISHED` 전환 API 구현
8. 소단원·대단원 랜덤 출제(`PUBLISHED`만 대상)와 HUMAN fallback 구현
9. AI 생성부터 Spring 저장·관리자 승인·응시·채점까지 통합 검증

이번 문서 작업에는 위 실행 코드, 일일 퀘스트 연동, `quest_date` 마이그레이션,
스케줄링과 관리자 승인 화면·API 구현을 포함하지 않는다. 다만 배치 저장 최초
상태가 `REVIEW`이고 관리자 승인 후 `PUBLISHED`로 전환된다는 상태 모델은 이
계약에 포함한다.
