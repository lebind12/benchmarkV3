---
worker_id: news-translator
title: news_article 한글 번역 워커
created: 2026-05-13
priority: MVP
status: requirements-only
---

## 1. 목적

`news-fetcher` 가 적재한 영문 외신 기사 메타데이터 (`news_article` 의 `title_ko IS NULL OR summary_ko IS NULL`) 를 읽어 한국어 제목과 짧은 요약을 생성한다. 원문 전문 재게시가 아니라 **요지 중심의 짧은 의역**만 저장한다.

`translation-filler` 와 구조 유사하지만 별도 워커 (프롬프트 다름 — 이름 음역 vs 문장 의역).

## 2. 스케줄

- 종류: polling
- 주기: **1분 간격**
- 시작 조건: 사이클 시작 시 큐 비어 있으면 즉시 종료
- 종료 조건: 큐 비거나 배치 상한 도달

## 3. 트리거 / 입력

### 큐 정의
```sql
SELECT id, source, original_title, original_summary
FROM news_article
WHERE title_ko IS NULL OR summary_ko IS NULL
ORDER BY published_at DESC
LIMIT 50;
```

### 외부 자원
- OpenAI API (`gpt-3.5-turbo`)

## 4. 처리 단계

```
[사이클 시작]
   ↓
Step 1. 큐 조회 (news_article 미번역 row)
   ↓
Step 2. 큐 비면 즉시 종료
   ↓
Step 3. 배치 상한 (50건) 적용
   ↓
Step 4. 각 row 별 OpenAI 호출 (짧은 의역)
   ↓
Step 5. 응답 파싱 (JSON 강제)
   ↓
Step 6. dry-run 이 아니면 UPDATE news_article SET title_ko, summary_ko, translated_at = now()
   ↓
[사이클 종료]
```

### Step 4 — OpenAI 프롬프트

```
당신은 영문 축구 뉴스를 한국어로 번역하는 번역가입니다.
다음 사항을 지킵니다:

1. 사실은 그대로, 어조는 한국 축구 매체 스타일 (자연스러운 의역 OK).
2. 선수/팀 이름은 한국 축구 중계 통용 표기 (예: Manchester United → 맨체스터 유나이티드)
3. 원문 전문을 재게시하지 말고, 제목 80자 이내 / 요약 1문장 160자 이내로 압축.
4. 응답은 JSON 만, 다른 텍스트 X.

입력:
{
  "original_title": "...",
  "original_summary": "..."
}

출력 (JSON):
{
  "title_ko": "...",
  "summary_ko": "...",
  "confidence": 0.0~1.0
}
```

### 모델 / 파라미터
- `model = "gpt-3.5-turbo"`
- `temperature = 0.3` (자연스러움 + 일관성 중간값)
- `max_tokens = 400`
- `response_format = {"type": "json_object"}`

## 5. 출력 / 부수 효과

| 테이블 | 동작 |
|---|---|
| `news_article` | dry-run 이 아니면 UPDATE title_ko, summary_ko, translated_at. 기존 값은 덮어쓰지 않음 |

### 외부 부수 효과
- OpenAI API 호출

## 6. 멱등성 / 재시도

- 큐 조건 `title_ko IS NULL OR summary_ko IS NULL` → 채워진 row 재처리 X
- 한 번 번역된 row 본 워커가 절대 덮어쓰지 않음
- 실패 시 다음 사이클 재시도

### 재시도 정책
- OpenAI 호출 실패: 지수 백오프 3회 (1s / 2s / 4s)
- 그래도 실패 시 해당 row skip, 다음 사이클 (1분 후)
- 연속 실패 N회 → 알림

## 7. 분산 락

- **사용 안 함** (단일 인스턴스 전제)

## 8. 동시성 / 외부 API 제약

| 항목 | 값 |
|---|---|
| 동시 OpenAI 호출 semaphore | **5** |
| 한 사이클 배치 상한 | **50** |
| 큐 평균 크기 | 0~5 (평시), 폴링 직후 30~50 (news-fetcher 사이클 직후) |

## 9. 오류 처리

| 분류 | 처리 |
|---|---|
| OpenAI 5xx / timeout | 지수 백오프 3회. 그래도 실패 → row skip |
| OpenAI 4xx (인증/quota) | 사이클 abort + 알림 |
| JSON 파싱 실패 | row skip |
| title_ko/summary_ko 누락 응답 | row skip |
| DB UPDATE 실패 | row skip |
| DB 접속 불가 | 사이클 abort + 알림 |

## 10. 모니터링 / 로깅

매 사이클:
- `cycle_started_at`, `duration_seconds`
- `queue_size_at_start`
- `processed_count`, `succeeded_count`, `failed_count`
- `openai_calls`, `openai_errors`
- `cost_estimate_usd` (호출 수 × 단가)

알람:
- OpenAI 4xx
- DB 접속 불가
- 연속 실패 row N 사이클 (**N 권장 10**)

## 11. 의존성

### DB 테이블 (읽기 / 쓰기)
- `news_article`

### 외부 API
- OpenAI (`gpt-3.5-turbo`)

### 선행 워커
- `news-fetcher` (NULL row 생성자)

## 12. 비기능

| 항목 | 값 |
|---|---|
| 사이클 시간 (큐 빔) | < 1초 |
| 사이클 시간 (큐 50건) | ~10초 (semaphore 5, 평균 1초/call) |
| 일일 OpenAI 호출 | 30~50 (news-fetcher 의 일일 신규 수 만큼) |
| 호출당 비용 | ~$0.001 (gpt-3.5-turbo, 평균 400 tokens) |
| 일일 OpenAI 비용 | < $0.05 = **월 < $1.50** |

## 13. 테스트 전략

### 단위 테스트
- 큐 조회 SQL (NULL row 만)
- 프롬프트 빌더 (input shape)
- OpenAI 응답 파싱 (정상 / JSON 깨짐 / 필드 누락)

### 통합 테스트
- 격리 schema + mock OpenAI
- 사이클 1회: NULL row 5건 입력 → 정상 응답 mock → UPDATE 확인
- 큐 비었을 때 즉시 종료
- 5xx mock → 재시도 후 row skip
- 멱등성: 채워진 row 재처리 X

## 14. BE 팀이 결정해도 되는 것

- 내부 모듈 구조 (`app/workers/news_translator/`)
- OpenAI 클라이언트 wrapping
- 프롬프트 미세 조정
- 단위 테스트 케이스

## 15. BE 팀이 결정해서는 안 되는 것 (메인 확인 필요)

- 스케줄 주기 (1분)
- 모델 변경 (gpt-3.5-turbo → 다른)
- 번역 정책 변경 (의역 → 직역 등)
- DB 스키마 변경

## 16. 확정 운영 파라미터 / 미정

### 확정
| 항목 | 값 |
|---|---|
| 모델 | gpt-3.5-turbo |
| temperature | 0.3 |
| 폴링 주기 | 1분 |
| 동시 호출 semaphore | 5 |
| 배치 상한 | 50 |
| 재시도 | 지수 백오프 3회 |
| 연속 실패 알림 임계 | 10 사이클 |

### 미정
- 알람 채널 (MVP stdout)
- 의역 품질 모니터링 (post-MVP, ADMIN 검수 시)
- 이미지 caption 번역 (현재 미사용)
