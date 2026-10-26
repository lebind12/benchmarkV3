# 스트리머 관리 화면 → 실제 API 계약 (2026-10-25)

평가한 네 탭 UI와 피드백을 실제 `/admin`에 연결한다. `/admin/mock`은 개발 평가용으로 유지한다. 배포·운영 서비스 재시작은 수행하지 않는다. 초기 로컬 검증 후 사용자의 기존 DB 연결 제보에 따라 기존 연결 Supabase에는 검증한 0017을 적용했다.

## 인증

- 기존 signup/login의 user 응답을 유지하고 login에 access JWT + HttpOnly refresh cookie를 추가한다. GET `/api/v1/auth/me`, POST `/refresh`, POST `/logout`.
- access HS256/issuer/audience/expiry 검증, DB 현재 사용자/활성/역할 확인. refresh는 Upstash 환경 prefix 아래 해시 식별자만 저장하고 원자적 rotation, 재사용/만료 거절. 비설정 환경은 fail closed.
- 아래 전체 `/api/v1/admin/management` 및 기존 `/api/v1/admin/*`는 STREAMER/ADMIN만 허용. 익명401/USER403. 브라우저 저장 역할은 권한 근거가 아니다.

## FE 요구 API

| Method/path (management 아래) | 요청 | 응답 |
|---|---|---|
| GET /catalog | query,id | items(외부리그ID/이름/국가/최신 실제 두 시즌/순위 지원), updated_at,total |
| POST /catalog/refresh | 없음 | updated_at,api_count,synced_count,catalog_count; 동시 실행409 |
| GET /targets | 없음 | items(평가 MockTarget shape), persistence_available=true |
| POST /targets | league_id(외부ID),season,is_active,include_details/players/standings,fixture_limit | target; 같은리그시즌 upsert |
| PATCH /targets/{id} | 변경 필드; fixture_limit=null 해제 | target |
| DELETE /targets/{id} | 없음 | removed; 설정만 제외, 데이터 삭제 안함 |
| GET /runs | 최근7일 | active,items; 재접속 복원 |
| GET /runs/{id} | 없음 | 단건; 실패로그/전체실행 원인 집계 포함 |
| POST /runs | target_ids(1~20),mode(initial/refresh),parent_run_id | run; 중복409; 최초 전체시즌/갱신3일+예정 |
| POST /runs/{id}/cancel | 없음 | cancel_requested → cancelled; 저장된 단위 유지 |
| GET /translations | query,type,status(translated/untranslated),page | items,total,page,page_size,missing_count |
| PATCH /translations/{type}/{id} | name_ko,short_name_ko,expected_version | 변경행; 충돌409 current, 임의id404 |
| GET /translations/{type}/{id}/history | 없음 | 수정자/시각/before/after/version |

run: id,mode,status,created_at,started_at,finished_at,cancel_requested_at,actor,parent_run_id,items,logs,progress,stage,log_statistics/log_counts. 대상 결과 수는 처리 단위 기준으로 표시하며 실제 저장 row수와 구분한다. logs `{at,message,code,level,target_id,stage,attempt,max_attempts}`. 통계는 tail truncate 전에 누적하고 total/retained/dropped를 함께 전달한다. 기존 과거 원문은 보존하며 분류 불가능한 원인을 추측하지 않는다.

## DB/워커 규칙

- 네 번역 테이블 version/human_modified/editor 추가, append-only 이력. CAS + 트랜잭션. DB trigger가 보호된 이름/NULL을 자동 작업 및 기존 import에서 보존한다.
- 관리 실행 DB snapshot/heartbeat/cancel 플래그. 실행 중 단일 advisory lock을 수동·스케줄 모두 공유한다. 프로세스 종료 시 stale heartbeat/락 상태로 interrupted 표시. 이력7일, 진행작업 보존.
- 대상은 카탈로그 current와 직전 실제 개최 시즌으로 제한한다. league.is_active는 유효 활성 대상 존재와 일치시킨다. 설정 제외/비활성은 데이터 삭제가 아니다.
- 기존 runner/rate limiter/upsert 재사용. 취소는 API 요청 전/DB 저장 단위 사이에서 검사, 현재 트랜잭션 rollback, 이미 commit한 데이터 유지. 안전하게 재실행한다. 동시호출6/최대3회지수백오프 유지. 반복 요청은 중복실행을 막는다.
- 실제 API-Football payload 모델은 새로 만들지 않고 기존 검증된 catalog/runner/mappers를 재사용한다.

## 검증

먼저 권한/토큰·CAS/보호·NULL/시즌·최초/갱신·취소·재접속·실패/통계·카탈로그에 대한 단위 및 격리 Postgres 테스트. 이후 실제 FastAPI→Postgres→응답과 Vue→FastAPI 흐름을 확인한다. 외부 API/유료 번역은 고정 fixture로 대체하고 이를 실제외부연동 검증과 구분한다. no commit/push/merge/deploy; 로컬 검증 결과를 Plans.md에 기록한다.

## 구현 결과 (로컬, 2026-10-25)

- 실제 `/admin`과 평가용 `/admin/mock`이 공통 `ManagementView`/네 패널을 사용하며 API를 주입한다. 실제 화면은 MSW나 localStorage 작업 데이터를 사용하지 않는다.
- `app/api/v1/management.py`, `app/services/management.py`, `app/services/management_runs.py`에 계약을 구현했다. 기존 admin CRUD/카탈로그 및 daily-sync 적재 코드를 재사용했다. 기존 수동 daily-sync 실행도 새 영속 실행으로 연결하며 기본 대상 fallback으로 활성 설정을 우회하지 못하게 했다.
- 신규 `management_run`, `translation_audit`, target initial_status/last_sync, 네 번역 테이블 version/human_modified/editor_id. 새 운영 테이블은 RLS를 활성화하고 backend DB 연결을 통해서만 제공한다.
- Supabase CLI가 생성한 `supabase/migrations/20261024212510_streamer_management.sql`을 DDL 정본으로 사용하고 Alembic `0017_streamer_management`가 같은 SQL을 실행한다. **기존 연결 Supabase DB에 0016→0017 적용 및 head 확인을 완료했다.** 기존 환경은 0016 기준선 확인 후 둘 중 한 경로로만 적용해야 한다. `supabase db push`를 기존 Alembic DB에 무작정 적용하지 않는다. downgrade는 신규 테이블/메타데이터를 제거하므로 명시적인 별도 롤백 작업에서만 사용한다.
- 처리 수는 API/적재 단계 단위, 저장 수는 commit된 upsert 행 처리 수다(서로 다른 단위이며 중복 upsert 포함). 범위 확인 전 취소는 수를 모르는 상태로 표시하고 재실행할 수 있다.
- 실행 목록은 최근 7일/최대 100개 요약과 전체 실행 원인 카운터를 전달한다. 완료 작업의 원문 로그는 단건 API에서 조회한다. 활성 작업은 2초 간격으로 확인한다. 원문은 최근 1,000줄, 전체 카운터는 자르기 전에 누적한다.
- 성공한 수집 대상의 리그에 한정해 최신 두 실제 개최 시즌 밖의 fixture/순위/선수 시즌 통계/팀 시즌/감독 시즌/부상 자료를 정리한다. 원본 entity와 번역은 공유 참조를 보존한다. 대상 설정 제외 자체는 자료를 삭제하지 않는다.
- 앱 스케줄러는 기존 daily-sync 00/06/12/18 KST 정책을 유지한다. translation-filler는 기존 CLI/등록 코드를 유지하고 queue·UPDATE 및 DB trigger에서 사람 수정 보호를 추가했다. 다른 워커의 자동 등록이나 운영 실행 설정은 이번에 변경하지 않았다.

인증 구현은 [PyJWT 공식 사용 문서](https://pyjwt.readthedocs.io/en/stable/usage.html)의 명시적 HS256/만료 검증 인터페이스를 사용한다. 서명 키나 환경 prefix가 없으면 인증을 우회하지 않고 실패한다.

실제 환경에 필요한 설정(이번에 배포 환경 값은 변경하지 않음; 로컬 .env만 설정): `JWT_SECRET_KEY`(충분한 길이의 랜덤 키, 32자 이상), `UPSTASH_REDIS_REST_URL/TOKEN`, `UPSTASH_REDIS_KEY_PREFIX=local:` 또는 `prod:`, `CORS_ALLOW_ORIGINS`(정확한 FE origin 목록). HTTPS의 `AUTH_COOKIE_SECURE=true`가 기본값이며 로컬 HTTP에서만 false를 사용한다. 서로 다른 site에 FE/API가 있으면 secure cookie와 `AUTH_COOKIE_SAMESITE=none`의 조합을 검토해야 한다.

## 로컬 화면

기존 계정/기존 Supabase: http://127.0.0.1:5173/admin

별도 fixture 검증 DB: http://127.0.0.1:5187/admin

테스트 전용 계정: `streamer@management.local` / `Bench1234`. USER 차단 확인용은 `user@management.local` / 동일 비밀번호다. 두 계정은 전용 로컬 테스트 DB에만 생성했다.

이 화면은 실제 Vue → FastAPI → PostgreSQL을 사용한다. API-Football과 Upstash만 명시적인 테스트 fixture로 대체하며 유료 외부 호출은 하지 않는다. MSW 관리 목업과 구분한다. FA Cup fixture는 재시도·실패 로그 확인을 위해 의도적으로 timeout을 반환한다.

재실행(별도 터미널):

```sh
# 먼저 전용 로컬 PostgreSQL(55439)에 0017까지 적용돼 있어야 한다.
.venv/bin/python -m tests.support.management_live_server
```

```sh
VITE_USE_MOCK=false VITE_BACKEND_URL=http://127.0.0.1:8016 npm --prefix frontend run dev -- --host 127.0.0.1 --port 5187 --strictPort
```

검증 서버는 127.0.0.1:55439 전용 DB만 허용하고, 실환경과 다른 refresh cookie 이름/prefix를 사용한다. 기존 5173 개발 서버와 다른 서비스는 재시작하지 않았다.

현재 로컬 개발 API는 Vite proxy를 통해 동일 origin으로 요청한다. CORS와 auth Origin 검사는 `allowed_web_origins`를 공유한다. 로컬 JWT 키/HTTP cookie/5173 origin은 `.env`에 설정했고 DB URL은 보존했다. 5187의 테스트 계정은 기존 Supabase에 생성하지 않았다.

## 선수·감독 조건 검색·로고 확장 (2026-10-25)

- GET `/translations/affiliation-filters?type=player|coach&league_id=`: 수집된 소속 관계의 `{leagues:[{id,name,name_en,logo_url}],teams:[...]}`. ID는 external ID이며 리그 선택 시 팀 후보를 좁힌다.
- GET `/translations`: `type=player|coach`에서 optional positive `league_id`/`team_id`를 기존 이름·상태·페이지 조건과 함께 적용한다. 페이지 처리 전 EXISTS로 필터/중복 제거하고, 다른 entity 종류와 조건을 조합하면 422를 반환한다.
- 기존 GET `/catalog`, `/targets` 항목에 nullable `logo_url`을 추가했다. 기존 DB의 리그 로고를 사용한다.
- 화면/관계 의미/실제 검증 결과는 [player-translation-filters.md](player-translation-filters.md)를 따른다. 스키마 변경은 없다.

## 카탈로그 추천 검색 확장 (2026-10-25)

GET `/catalog`에 country/type/group/page/page_size를 추가했다. 한국어 번역·검증된 기본명/별칭과 원문으로 검색하며 국가/종류/주요 대회 그룹을 SQL 페이지 처리 전에 적용한다. 기존 items/updated_at을 유지하며 matched total/catalog_total/page/page_size/countries와 항목별 country_label/type/aliases/featured를 제공한다. 상세 계약과 검증은 [catalog-discovery.md](catalog-discovery.md)를 따른다. 원본 country 식별자와 표시용 국가명을 구분한다. 추천을 위해 외부 API/AI를 호출하거나 DB 번역을 자동 수정하지 않는다.

국가 검색 후속: countries의 `{value,label}` 계약을 유지하고 한국어 표시명 우선 순서를 제공한다. FE에서 한국어·원문 검색 추천으로 국가를 선택한다. 대회 items도 실제 한국어 표시명이 있는 항목을 페이지 적용 전 우선하며 그 안에서 기존 별칭·주요 대회 순서를 유지한다. 자세한 검증은 catalog-discovery 문서의 후속 절을 따른다.

## 수집 로그 원문 분류 후속 (2026-10-25)

GET `/runs/{id}`의 logs에 optional analysis(code/title/action/category/category_label/level/stage/target/classified)를 제공한다. 기존 원문/code/level은 보존한다. 기존 WorkerSyncLog도 읽을 때 분석하며 `/runs` 요약에는 보관 로그 기반 log_statistics 및 log_statistics_scope=retained/log_unclassified_count를 제공한다. 신규 실행의 전체 누적 통계는 보존한다. 상세 계약/분석 근거/검증은 [sync-log-classification.md](sync-log-classification.md)를 따른다.
