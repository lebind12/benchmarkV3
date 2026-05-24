---
worker_id: news-fetcher
title: ESPN Soccer RSS → DB 적재 워커
created: 2026-05-13
priority: MVP
status: requirements-only
---

## 1. 목적

ESPN Soccer RSS 에서 축구 기사를 수집해 `news_article` 테이블에 메타데이터 (제목 + 요약 + 원문 URL) 만 적재. 본문 직접 게재 X (저작권). 번역은 `news-translator` 워커가 짧은 한국어 제목/요약만 생성한다.

## 2. 스케줄

- 종류: cron / interval
- 주기: **1시간 간격**
- 시작 조건: 조건 없음 (매 실행)
- 종료 조건: 모든 RSS 소스 처리 완료 또는 fatal error

## 3. 트리거 / 입력

### RSS 소스
- ESPN Soccer: `https://www.espn.com/espn/rss/soccer/news`

### EPL 키워드 (DB 에서 동적 조회)
- DB 의 EPL 소속 team.name + team.code (예: 'Manchester United' + 'MUN')
- (선택, 3차 매칭) EPL 소속 player.name

## 4. 처리 단계

```
[사이클 시작]
   ↓
Step 1. ESPN Soccer RSS 소스 로드 (config 또는 DB)
   ↓
Step 2. 각 RSS HTTP GET + 파싱
   ↓
Step 3. 각 article 마다:
   3a. 이미 적재됐는지 확인 (source_url unique)
   3b. EPL 키워드 매칭 (title + summary 텍스트)
   3c. 매칭되면 tags JSONB 채움 (매칭된 team external_id 들)
   3d. INSERT ON CONFLICT (source_url) DO NOTHING
   ↓
[사이클 종료]
```

### Step 3 상세
- 키워드 매칭은 부분 문자열 (case-insensitive). 예: title 에 'Manchester United' 또는 'MUN' 등장 시 매치
- 매칭 결과는 `tags.teams = [external_id, ...]` 로 저장
- 매칭된 게 없으면 article skip (DB INSERT X)

## 5. 출력 / 부수 효과

| 테이블 | 동작 |
|---|---|
| `news_article` | INSERT ON CONFLICT (source_url) DO NOTHING. 신규 row 만, 한글 컬럼 NULL |

### 외부 부수 효과
- 없음 (RSS HTTP GET 만, OpenAI 호출 없음, 자체 DB write 만)

## 6. 멱등성 / 재시도

- `source_url` UNIQUE → 같은 기사 두 번 INSERT X
- HTTP 실패 시 지수 백오프 3회 (1s → 2s → 4s). 그래도 실패면 다음 사이클 (1시간 뒤) 재시도
- 부분 실패 (1 소스 실패) 시 다른 소스 진행

## 7. 분산 락

- **사용 안 함** (단일 인스턴스 전제)

## 8. 동시성 / 외부 API 제약

| 항목 | 값 |
|---|---|
| RSS 소스 동시 호출 | semaphore 1 |
| 한 사이클 RSS GET 수 | 1 |
| 일일 RSS GET 수 | 24 |

## 9. 오류 처리

| 분류 | 처리 |
|---|---|
| RSS HTTP 4xx/5xx | 지수 백오프 3회. 그래도 실패면 해당 소스 skip, 다음 사이클 |
| RSS XML 파싱 실패 | 해당 소스 skip, 로그 기록 |
| DB INSERT 실패 | 해당 article skip |
| DB 접속 불가 | 사이클 abort + 운영자 알림 |

## 10. 모니터링 / 로깅

매 사이클 종료 시:
- `cycle_started_at`, `duration_seconds`
- `sources_processed`, `sources_failed`
- `articles_fetched_total`, `articles_filtered_in` (EPL 매치), `articles_inserted` (new), `articles_skipped`
- 매칭 키워드 분포 (선택)

알람:
- 연속 3 사이클 실패
- 모든 소스 0 article (장애 의심)

## 11. 의존성

### DB 테이블 (읽기)
- `team` (EPL 소속 team 의 name, code 조회 — `WHERE league_id IN (EPL ids)`)
- (선택) `player` (3차 매칭)

### DB 테이블 (쓰기)
- `news_article`

### 외부
- ESPN Soccer RSS

### 선행 작업
- daily-sync 가 적재한 team 정보 (필터 키워드 기반)
- league.is_active = true 인 EPL row

### 후속 워커
- `news-translator` — title_ko 가 NULL 인 row 번역

## 12. 비기능

| 항목 | 값 |
|---|---|
| 사이클 시간 | 30초~1분 (RSS 응답 속도 의존) |
| 일일 신규 article | 30~50건 (예상) |
| 메모리 | 작음 (RSS 페이로드 수십 KB × 3) |
| CPU | I/O 바운드 |
| DB write | 30~50 INSERT / 일 |

## 13. 테스트 전략

### 단위 테스트
- RSS XML 파싱 (정상 / 형식 깨짐 / 빈 feed)
- EPL 키워드 매칭 (case-insensitive, 부분 문자열)
- tags JSONB 빌더 (매칭된 team external_id 집합)
- source_url 추출

### 통합 테스트
- 격리 schema + mock RSS server (고정 XML 응답)
- 사이클 1회 → DB 에 매칭 article INSERT, 비매칭 skip 확인
- 같은 mock 2회 → row count 동일 (멱등성)
- RSS 5xx mock → 재시도 후 skip

## 14. BE 팀이 결정해도 되는 것

- 내부 함수 / 모듈 구조 (`app/workers/news_fetcher/`)
- RSS 파서 라이브러리 선택 (feedparser, defusedxml 등)
- 키워드 매칭 알고리즘 (단순 string vs regex)
- 단위 테스트 케이스 세부

## 15. BE 팀이 결정해서는 안 되는 것 (메인 확인 필요)

- 스케줄 주기 변경 (1시간)
- RSS 소스 목록 변경 (ESPN-only 정책 변경)
- EPL 외 다른 리그 키워드 매칭 추가
- DB 스키마 변경
- 새 외부 데이터 의존성 추가 (NewsAPI 등)

## 16. 확정 운영 파라미터 / 미정

### 확정
| 항목 | 값 |
|---|---|
| 폴링 주기 | 1시간 |
| RSS 소스 | 1개 (ESPN Soccer) |
| 동시 호출 semaphore | 3 |
| 재시도 | 지수 백오프 3회 |
| 키워드 매칭 | team.name + team.code + player.name |
| 보관 기간 | 90일 (별도 cleanup task) |

### 미정 / 메모
- 알람 채널 (MVP stdout)
- RSS 소스 확장 시점
- 이미지 처리 (RSS enclosure) — MVP 미사용 또는 thumbnail 만
