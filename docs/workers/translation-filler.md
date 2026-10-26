---
worker_id: translation-filler
title: 매칭 테이블 한글 자동 번역 워커
created: 2026-05-13
priority: MVP
status: requirements-only
---

## 1. 목적

2026-10-24 갱신: 직접 번역 검수·수정은 인증된 STREAMER / ADMIN의 공통 관리 범위다. 사람 수정·의도적 NULL은 이후 filler/import가 덮어쓰지 못하도록 버전·보호 상태와 경쟁 검증을 추가한다. 현재 구현은 비NULL 컬럼 COALESCE 보존만 제공한다. 실제 큐는 팀·선수·감독이며 리그 자동 음역은 제외되어 있다. 아래 NULL 큐에 신규 검수 보호 조건을 추가하는 것은 후속 구현이다. 상세는 [plan.md](../../plan.md), [결정 기록](../decisions/2026-10-24-streamer-management-and-ax.md)을 따른다.

daily-sync가 새 entity (team/player/coach) 발견 시 만들어 둔 `name_ko IS NULL OR short_name_ko IS NULL` row를 OpenAI gpt-3.5-turbo로 음역하여 한글 표기를 채운다. 시드 CSV (player 6,422 row)와 일관된 표기를 유지하기 위해 같은 모델 + few-shot 패턴을 사용한다.

## 2. 스케줄

- 종류: polling
- 주기: **1분 간격**
- 시작 조건: 사이클 시작 시 큐(NULL row) 가 비어 있으면 **즉시 종료** (그 사이클은 호출 없음)
- 종료 조건: 큐 비거나 배치 상한 도달 또는 fatal 에러

## 3. 트리거 / 입력

### 큐 정의
3개 매칭 테이블에서 한글 누락 row:

```sql
-- coach
SELECT 'coach' AS entity_type, ct.coach_id AS id, c.name, '' AS context_a, NULL AS context_b
FROM coach_translation ct
JOIN coach c ON c.id = ct.coach_id
WHERE ct.name_ko IS NULL OR ct.short_name_ko IS NULL

UNION ALL

-- team
SELECT 'team', tt.team_id, t.name, t.country, t.code
FROM team_translation tt
JOIN team t ON t.id = tt.team_id
WHERE tt.name_ko IS NULL OR tt.short_name_ko IS NULL

UNION ALL

-- player
SELECT 'player', pt.player_id, p.name, p.nationality, p.firstname || ' ' || p.lastname
FROM player_translation pt
JOIN player p ON p.id = pt.player_id
WHERE pt.name_ko IS NULL OR pt.short_name_ko IS NULL;
```

### 외부 자원
- OpenAI API (`gpt-3.5-turbo`)
- 시드 CSV `_Player__202605131748.csv` (few-shot 예시 원본, player 한정)

## 4. 처리 단계

```
[사이클 시작]
   ↓
Step 1. 큐 조회 (3 매칭 테이블 UNION ALL)
   ↓
Step 2. 큐 비면 → 즉시 종료
   ↓
Step 3. entity_type 별 그룹화 (coach / team / player 별 처리)
   ↓
Step 4. 배치 상한 적용 (최대 N row / 사이클)
   ↓
Step 5. 각 row 별 OpenAI 호출 (few-shot)
   ↓
Step 6. 응답 파싱 (JSON 강제, 실패 시 row skip)
   ↓
Step 7. 매칭 테이블 UPDATE
   ↓
[사이클 종료]
```

### Step 5 상세 — OpenAI 호출 패턴

#### Few-shot 예시 추출
- **league**: 자동번역 큐에서 제외. 리그 한글표기는 STREAMER / ADMIN의 직접 검수·수정 대상으로 제공한다.
- **coach**: 원문 이름을 기반으로 처리하며 한글 이름/짧은 이름 누락값만 채운다.
- **team**: 사용자가 작성한 team_translation 시드 CSV 에서 동일 country 의 5~10건 무작위
- **player**: 시드 CSV `_Player__202605131748.csv` 에서 동일 nationality 의 5~10건 무작위

#### 프롬프트 구조 (player 예시)

```
당신은 축구 선수 영문 이름을 한국 축구 중계/기사에서 통용되는 한글 표기로
음역하는 번역가입니다. 응답은 JSON 만 출력하세요.

예시:
{"eng": "Bukayo Saka", "nationality": "England", "name_ko": "부카요 사카", "short_name_ko": "사카"}
{"eng": "S. Sherring", "nationality": "England", "name_ko": "셰링", "short_name_ko": "셰링"}
{"eng": "Sadio Mané", "nationality": "Senegal", "name_ko": "사디오 마네", "short_name_ko": "마네"}
... (시드 CSV 에서 5~10건)

입력:
{"eng": "{player_name}", "nationality": "{nationality}"}

출력 (JSON):
```

#### 모델 / 파라미터
- `model = "gpt-3.5-turbo"`
- `temperature = 0` (일관성)
- `max_tokens = 100` (짧은 응답)
- `response_format = {"type": "json_object"}` (강제)

#### 응답 파싱
- JSON 파싱 성공 + `name_ko` `short_name_ko` 둘 다 존재 → UPDATE
- 파싱 실패 또는 누락 → 해당 row skip (NULL 유지, 다음 사이클 재시도)

## 5. 출력 / 부수 효과

### 갱신 테이블
| 테이블 | 동작 |
|---|---|
| `league_translation` | `name_ko` / `short_name_ko` UPDATE (선택적, league 처리 시) |
| `team_translation` | `name_ko` / `short_name_ko` UPDATE |
| `player_translation` | `name_ko` / `short_name_ko` UPDATE |

### 외부 부수 효과
- OpenAI API 호출 (소비)

## 6. 멱등성 / 재시도

### 멱등성
- 큐 조건이 `name_ko IS NULL` → 채워진 row 는 다음 사이클에서 제외
- 같은 사이클이 두 번 실행돼도 OpenAI 호출은 NULL row 에만
- 변경 데이터 반영 안 함 (의도) — 한 번 채워진 한글은 본 워커가 절대 덮어쓰지 않음

### 재시도 정책
- OpenAI 호출 실패: 지수 백오프 3회 (1s / 2s / 4s)
- 그 이상 실패는 해당 row NULL 유지 → 다음 사이클 (1분 후) 재시도
- 같은 row 가 N 사이클 연속 실패하면? → 운영자 알림 (임계치 결정 필요)

## 7. 분산 락

- **사용 안 함** (AGENTS.md §4 단일 인스턴스 전제)

## 8. 동시성 / 외부 API 제약

| 항목 | 값 |
|---|---|
| OpenAI rate limit (gpt-3.5-turbo) | 분당 수천 req (Tier 기준), 본 워커에 충분 |
| 동시 호출 semaphore | **결정 필요** (권장 5) |
| 한 사이클 배치 상한 | **결정 필요** (권장 50 row) |
| 큐 평균 크기 | 0~5 row (평시), 50~200 (시즌 시작 시) |

평시엔 큐가 거의 비어 즉시 종료. 시즌 시작 직후 일시적으로 많아짐.

## 9. 오류 처리

| 분류 | 처리 |
|---|---|
| OpenAI 5xx / timeout | 지수 백오프 3회. 그래도 실패면 row skip |
| OpenAI 4xx (인증/quota) | 사이클 abort + 운영자 알림 |
| JSON 파싱 실패 | row skip (NULL 유지) |
| 응답에 name_ko/short_name_ko 누락 | row skip (NULL 유지) |
| DB UPDATE 실패 | 해당 row skip, 다음 사이클 재시도 |
| DB 접속 불가 | 사이클 abort + 운영자 알림 |

## 10. 모니터링 / 로깅

매 사이클 종료 시 stdout 로깅:
- `cycle_started_at`, `duration_seconds`
- `queue_size_at_start`
- `processed_count`, `succeeded_count`, `failed_count`
- `openai_calls`, `openai_errors`
- `cost_estimate_usd` (대략. 호출 수 × 단가)

알람 조건:
- OpenAI 4xx (인증/quota) 발생
- DB 접속 불가
- 같은 row 가 N 사이클 연속 실패 (**N 결정 필요, 권장 10**)
- 큐 크기 비정상 (예: 1000+)

알람 채널: MVP 단계 → stdout 로깅만

## 11. 의존성

### DB 테이블 (읽기)
- 3개 매칭 테이블 (`*_translation`)
- 3개 entity 테이블 (`league`, `team`, `player`) — JOIN 용

### DB 테이블 (쓰기)
- 3개 매칭 테이블 (UPDATE)

### 외부 API
- OpenAI API (`gpt-3.5-turbo`)

### 선행 작업
- daily-sync 가 먼저 동작해서 NULL row 를 생성해 둔 상태여야 의미 있음
- 시드 CSV import 완료 (few-shot 예시 원본)

### 선행 워커
- daily-sync (NULL row 생성자)

## 12. 비기능

| 항목 | 값 |
|---|---|
| 사이클 시간 (평시, 큐 빔) | < 1초 (즉시 종료) |
| 사이클 시간 (큐 50 row) | ~10초 (semaphore 5, 평균 1초/call) |
| 사이클 당 OpenAI 호출 | 평시 0, 시즌 시작 시 0~50 |
| 일일 OpenAI 호출 | 평시 거의 0, 시즌 시작 직후 일시 수백 |
| 호출당 비용 | ~$0.001 미만 |
| 일일 OpenAI 비용 | 평시 < $0.01, 시즌 시작 시 일시 ~$1 이내 |
| 메모리 | 큐 크기 + 시드 예시 ≈ 수 MB |
| CPU | 매우 낮음 (I/O 바운드) |

## 13. 테스트 전략

### 단위 테스트
- 큐 조회 SQL 정확성 (NULL row 만 선택)
- few-shot 프롬프트 빌더 (entity_type 별 예시 선택, country/nationality 매칭)
- OpenAI 응답 파싱 (JSON 정상 / JSON 깨짐 / 필드 누락)
- height/weight 같은 unrelated 파싱 없음 (player_translation 은 이름만)

### 통합 테스트
- 격리 schema + mock OpenAI client
- 사이클 1회 실행: NULL row 입력 → 정상 응답 mock → UPDATE 확인
- 큐 비었을 때 즉시 종료 (OpenAI 호출 0)
- OpenAI 5xx mock → 재시도 3회 → 결국 row skip
- JSON 깨진 응답 mock → row skip (NULL 유지)
- 멱등성: 이미 채워진 row → 다음 사이클에서 무시

### 회귀 테스트
- 시드 CSV 의 표기와 본 워커 결과 표기의 일관성 (sample 비교)
- 같은 입력 2회 호출 → 동일 출력 (temperature=0)

## 14. BE 팀이 결정해도 되는 것

- 내부 함수 / 모듈 구조 (`app/workers/translation_filler/`)
- OpenAI 클라이언트 wrapping 구조
- few-shot 예시 선택 알고리즘 (random vs nationality-weighted 등)
- 단위 테스트 케이스 세부

## 15. BE 팀이 결정해서는 안 되는 것 (메인 확인 필요)

- 스케줄 주기 변경 (1분)
- 모델 변경 (gpt-3.5-turbo → 다른 모델)
- 음역 정책 변경 (web_search 도입 등 — AGENTS.md §11 의 향후 항목)
- 새 entity_type 추가
- DB 스키마 변경
- league를 자동번역 처리 대상에 정식 포함할지 (현재 제외)

## 16. 확정 운영 파라미터 / 미정

### 확정
| 항목 | 값 |
|---|---|
| 동시 OpenAI 호출 semaphore | **5** |
| 배치 상한 (한 사이클 처리할 row 수) | **50** |
| 연속 실패 row 알림 임계치 | **10 사이클** (= 10분 연속 실패) |
| league 대상 처리 | 본 워커 제외. STREAMER / ADMIN 공통 번역 검수에서 직접 수정. 관리 API/UI 구현, 로컬 연결 검증 |

### 미정 / 메모
| 항목 | 메모 |
|---|---|
| 알람 채널 | 미정 (MVP 단계 stdout 만) |
| 시드 외 few-shot 출처 | team_translation 시드 작성되면 team 처리 시 같이 활용 |
| 직접 번역 검수 | 이번 범위의 STREAMER / ADMIN 공통 관리. AI 의심 표기 추천은 별도 선택 후보 |

## 2026-10-25 보호 연결

queue는 `human_modified=false`만 선택하며 UPDATE에도 같은 조건을 적용한다. 네 번역 테이블 DB trigger는 모든 기존 import 경로에서도 사람이 수정한 이름/짧은 이름/의도적인 NULL을 보호한다. 새 관리 API는 version 충돌과 수정 전후 이력을 기록한다. 본 변경은 앱 scheduler에 filler를 자동 등록하거나 운영 OpenAI 호출을 시작하지 않는다. 기존 CLI/등록 함수와 실제 실행 설정은 구분한다.
