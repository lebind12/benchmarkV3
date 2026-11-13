# HOME-DB-01 서버 DB 연결 읽기 전용 조사 결과

작성: DeepSeek 조사 워커 (읽기 전용). 범위는 `home-db-connection-investigation-brief.md`만 따른다.
제품·테스트·설정·권한·Plans.md 변경 없음. 이 보고서 외 파일은 쓰지 않았다.

## 0. 실행 조건 확인

- 실제 선택된 모델은 세션 기록의 `model/selection` 이벤트로 확인했다:
  provider `hive`, model `deepseek-ai/deepseek-v4.1-flash-1017`, reasoningEffort `max`.
  이 세션은 TUI 정적 프로필 기본값(`deepseek-official` / `low`)이 아니라
  hive 라우트의 `max`로 실행됐다(세션 이벤트가 우선).
- 서버 프로세스: 마지막 확인 PID와 동일한 PID 66697, cwd `/Users/woolee/benchmark`,
  명령 `.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`.
  재시작·attach·debug 없음. 런타임 환경은 해당 프로세스의 환경 블록을 **메모리에서만**
  읽어 필요 값 비교에 쓰고 원문(DSN·호스트·역할 원명·비밀번호)은 출력하지 않았다.

## 1. DATABASE_URL 선택 경로 (값 없이 boolean으로)

| 확인 항목 | 결과 |
|---|---|
| 서버 프로세스에 `BENCHMARK_READ_DATABASE_URL` 존재 | **없음** |
| 그래서 런처 fallback `PREVIEW_FIXTURES_DATABASE_URL`가 선택됨 | **예** |
| 런타임 `DATABASE_URL` == `PREVIEW_FIXTURES_DATABASE_URL` | **동일(True)** |
| 저장소 `.env` 파일 존재 | **없음** (있는 것은 `.env.example`) |
| 따라서 `app/core/config.py`의 placeholder 기본값이 런타임에 쓰임 | **아니오** |
| 런처가 0600 자격 파일 2개(`preview-dev.env`, `model-live.env`)를 로드 | **예** |
| 원래 repo 기본 DB 대상과 런타임 대상이 같은 로컬 DB | **아니오** (로컬 대체 없음) |

결론: 실제 `DATABASE_URL`은 **fixture 읽기 역할 DSN**이며, `PREVIEW_FIXTURES_DATABASE_URL`과
바이트 단위로 같다. `run_benchmark_dev.sh:69`의 우선순위대로 동작했다.

## 2. 연결 대상과 역할 (동일 DB·서로 다른 역할)

여섯 DSN은 모두 **host·port·database가 동일**하다(단일 원격 대상, 풀러 호스트, 포트 5432).
서로 다른 것은 **역할**뿐이다. 논리 역할명은 이미 저장소 문서/스크립트에 공개된 이름이다.

| env 키 | 사용 지점 | 논리 역할 | 같은 DB 대상 | 역할 성격 |
|---|---|---|---|---|
| `DATABASE_URL` | `app.db.get_db_session()` 홈/일반 조회 | `preview_dev_fixture_ro` | 예 | public 테이블 단위 SELECT 일부 |
| `PREVIEW_FIXTURES_DATABASE_URL` | 동일 DSN(위와 같은 값) | `preview_dev_fixture_ro` | 예 | 동일 |
| `PREVIEW_IDENTITY_DATABASE_URL` | `make_auth_engine()` 계정 조회 | `preview_dev_identity_ro` | 예 | `public.app_user` SELECT만 |
| `PREVIEW_NAMES_DATABASE_URL` | `app/preview/localized_names.py` | `preview_dev_names_ro` | 예 | 열 단위 SELECT만 |
| `PREVIEW_STATS_DATABASE_URL` | 선수 통계 reader | `preview_dev_stats_ro` | 예 | 열 단위 SELECT만 |
| `PREVIEW_DATABASE_URL` | `app.preview.db` 개발 저장 | `preview_dev_app` | 예 | `preview_dev` 스키마 전용 |

역할 확인 근거: 각 DSN의 사용자명이 위 논리 이름과 정확히 일치함을 boolean으로 대조했다.
`PREVIEW_DATABASE_URL`은 `PREVIEW_DEV_DATABASE_URL`로부터 주입된 값과 동일하다.

런타임 플래그(비밀이 아닌 값만): `LOCAL_DEV_AUTH_ENABLED=true`,
`PREVIEW_ALLOW_NONLOCAL_DB=1`, `PREVIEW_ALLOW_NONLOCAL_IDENTITY_DB=1`,
`HOME_PREVIEW_ENABLED=false`, `WORKER_SCHEDULER_ENABLED=false`.
즉 원격 대상 동의 플래그가 켜져 있고, 홈 프리뷰 생성·수집은 이 프로세스에서 꺼져 있다.

## 3. 메타데이터 SELECT만으로 확인한 표 존재·권한

모든 접속은 `BEGIN READ ONLY` 트랜잭션에서 `information_schema`/`pg_catalog` 조회 또는
`SELECT ... LIMIT 0`만 실행했다. 운영 행 내용은 읽지 않았다.

### fixture 역할 (`DATABASE_URL`, 홈 조회가 실제로 쓰는 연결)

| 표 | 존재 | SELECT |
|---|---|---|
| `public.fixture` | 있음 | **가능** |
| `public.team` | 있음 | **가능** |
| `public.league` | 있음 | **가능** |
| `public.injury` | 있음 | 가능 |
| `public.standings` | 있음 | 가능 |
| `public.team_translation` | 있음 | **거부(42501)** |
| `public.league_translation` | 있음 | **거부(42501)** |
| `public.league_sync_target` | 있음 | **거부(42501)** |
| `public.home_preview_publication` | **없음** | — (`42P01`) |
| `public.home_preview_version` | **없음** | — (`42P01`) |

fixture 역할의 쓰기 권한은 INSERT/UPDATE/DELETE/TRUNCATE 모두 **false**다.

### 그 밖의 역할

- `identity`: `public.app_user` SELECT **가능**, 쓰기 **불가**. 다른 public 표 권한 없음.
- `names`: `team(id, external_id, name)`, `team_translation(team_id, name_ko, short_name_ko)`,
  `player`·`player_translation`·`coach` 계열의 **열 단위** SELECT만 보유.
  **`league_translation`·`league`·`league_sync_target` 권한 없음** → 홈 조회 대체 역할로 부적합.
- `stats`: `public.player_season_stat` 열 단위 SELECT만 보유.
- `preview_dev_app`: `preview_dev.*` 16개 표 SELECT/쓰기 가능, **`public` 계열 권한 전무**
  (`public.fixture`·`public.app_user` SELECT도 false). 개발 쓰기 격리는 의도대로 동작한다.

### home 표 부재의 성격

`home_preview_publication`, `home_preview_version`(및 snapshot/attempt)은
**권한 거부가 아니라 대상 DB에 존재하지 않는다**(`to_regclass` → NULL,
`pg_class` 검색 결과 0건, `preview_dev`·`public` 등 어떤 스키마에도 없음).
DDL은 `git HEAD`의 `supabase/migrations/20261024235328_home_preview_storage.sql`과
`alembic/versions/0018_home_preview_storage.py`에 있으나 **현재 작업 트리에서는 삭제 상태**이고
대상 DB에는 적용되지 않았다.

## 4. 현재 홈 recommendations의 첫 실패

`app.services.home_preview.recommendations()`를 **명시적 READ ONLY 트랜잭션에서 1회** 실행했다.
설정은 서버와 같은 방식(자격 파일 로드 → `DATABASE_URL` fallback 규칙)으로 읽었다.

- 첫 실패: `home_preview.active_pairs()` → `select ... from league_sync_target`
  - **SQLSTATE 42501**, 실패 표 **`public.league_sync_target`**
- 이어지는 `names()`는 위 실패로 트랜잭션이 abort되어 별도 평가되지 않았고,
  각 표를 따로 조회한 결과는 아래와 같다.
  - `league_sync_target`: 42501
  - `team_translation`: 42501
  - `league_translation`: 42501
  - `league`: 정상
  - `team`: 정상
  - `home_preview_publication`: 42P01 (존재하지 않음)
  - `home_preview_version`: 42P01 (존재하지 않음)
- 실제 서비스도 같은 결과로 응답한다: `GET /api/v1/home/recommendations` → **503**
  (`home_preview_storage_unavailable`).

부가 관측(중요): 이 풀러 대상에서는 접속 옵션 `-c default_transaction_read_only=on`이
**서버에 전달되지 않는다**(같은 방식으로 보낸 `statement_timeout`도 무시됨).
즉 `app/db.py`의 `READ_ONLY_CONNECT_ARGS`는 이 경로에서 **실효 차단이 아니며**,
실제 쓰기 차단은 오로지 **역할 권한**이 담당한다. 이는 brief의 "플래그만 켜서는 안 된다"는
경고와 일치하며, 현재 fixture 역할은 실제로 쓰기 권한이 없어 위험은 없다.

## 5. 결론 (세 원인을 구분)

1. **연결 대상 오류: 아님.** `DATABASE_URL`은 의도된 원격 DB의 fixture 읽기 역할로 올바르게
   선택됐다(`BENCHMARK_READ_DATABASE_URL` 미설정 → fixtures fallback). 로컬 placeholder로
   새지 않았다.
2. **읽기 역할 선택 오류 / 권한 부족: 맞음, 그러나 단독 원인은 아님.**
   홈 조회는 `league_sync_target`·`team_translation`·`league_translation`에 대해 42501로
   막힌다. 앞의 둘은 홈 recommendations 경로가 직접 쓰는 표다.
3. **기존 홈 저장 계약의 표 부재: 맞음.** `home_preview_publication`/`version`은 권한이 아니라
   **대상 DB에 아예 없다**. 2와 3은 독립 문제다.

따라서 "DB가 망가졌다"거나 "권한만 바꾸면 전부 해결된다"고 단정할 수 없다. 권한을 넓혀도
표가 없으므로 `read_preview` / publications 경로는 여전히 42P01로 실패한다.

## 6. 수정 후보 (가장 작은 범위, 실행하지 않음)

제안일 뿐 실행하지 않았다. 우선순위 순.

1. **권한 후보(가장 작음):** fixture 역할에 `public.league_sync_target` 테이블 SELECT를
   추가한다. 이 한 건으로 `active_pairs`의 42501이 풀린다. 이어서 `team_translation`,
   `league_translation`의 **필요 열 단위** SELECT(`team_id/league_id`, `name_ko`)를 추가하면
   `names()`와 `league_names` 조회가 통과한다. `public` 전체 GRANT나 관리자 역할 사용은
   제안하지 않는다.
2. **표 부재 후보(별건):** `home_preview_*` 4개 표를 **`preview_dev` 스키마**에 두고
   모델 `__tablename__`/`schema` 매핑과 조회 계약을 맞추는 방향. 현재 DDL은 스키마 미지정
   `public` 대상이며 작업 트리에서 삭제 상태이므로, 그대로 적용하면 "기존 public 영역 구조
   변경"이 되어 AGENTS.md의 개발 DB 기준(기존 영역 무변경)과 충돌한다. 표 생성 위치를
   `preview_dev`로 확정하는 결정이 먼저 필요하다.
3. **순서 제안:** 1은 즉시 검증 가능한 최소 변경이지만, 2가 없으면 recommendations 전체가
   여전히 실패한다. 그러므로 1과 2를 같은 승인 단위로 묶거나, 2의 스키마 확정을 먼저
   결정한 뒤 1을 적용하는 편이 재작업이 적다.

## 7. 추가 확인: 프리뷰 저장 계정의 쓰기 권한 (권한 메타데이터만)

후속 지시("권한 수정 전에 프리뷰 생성 결과를 DB에 쓸 수 있는지 먼저 확인")에 따라
같은 보고서에 짧게 덧붙인다. 실제 INSERT/UPDATE/DELETE·GRANT·쓰기 탐침은 하지 않았고,
`BEGIN READ ONLY`에서 `has_table_privilege`/`has_schema_privilege`/`information_schema`만 읽었다.

| 확인 항목 | 결과 |
|---|---|
| 서버 `PREVIEW_DATABASE_URL` == `PREVIEW_DEV_DATABASE_URL` | **동일(True)** |
| 프리뷰 저장 연결의 사용 지점 | `app.preview.db`(`SCHEMA='preview_dev'`, `search_path` 고정) — `app/auth/service.py`, `benchmark_sessions.py`, `app/api/v1/preview_admin.py`, `preview_metrics.py`, `app/workers/preview.py`, `app/preview/models.py`, `pipeline.py`, `send_ledger.py`가 사용 |
| `preview_dev` 테이블 수 | 16 |
| 16개 전부 SELECT/INSERT/UPDATE/DELETE | **모두 True** |
| `preview_dev` 스키마 CREATE/USAGE | **True/True** |
| 시퀀스 USAGE | 해당 스키마에 시퀀스 0개(모든 PK가 identity 아님) → 미적용 사항 없음 |
| `public` 테이블 SELECT 가능 수 | **0** (public 쓰기 권한도 전무) |

즉 프리뷰 생성 결과(실행·섹션결과·아티팩트·모듈 실행·전송/감사 장부 등
`app/preview/models.py`의 10개 `preview_dev` 표 전부)는 **이미 저장 가능**하다.
막는 것은 읽기 쪽(`public` 홈 표 권한·표 부재)이며, 저장 계정 권한 부족이 아니다.

기존 public 영역 무변경 확인: 이 역할은 `preview_dev` 밖에서 아무 권한도 없어
"같은 계정에 public SELECT까지 합치기"를 하려면 GRANT가 필요하고, 그 변경은
이번 조사 범위(변경 0)를 벗어난다.

정정: 위 문단의 "원래 연결은 저장소에 존재하지 않는다"는 이전 판단은 **철회**한다.
repo `.env`가 없다는 것은 저장소에 기본값 파일이 없다는 사실일 뿐이고, 원래 연결은
저장소 밖 자격 파일에 존재한다(§8). 아래 §8이 최종 사실이며 §1~§7의 연결 판단보다 우선한다.

## 8. 최종 정정 기준 확인: 원래 DATABASE_URL의 출처·대상·현재 권한

사용자 최종 지시("새 계정/GRANT 없이 원래 `DATABASE_URL`과 그 기존 전체 권한을 그대로
재사용, 프리뷰도 같은 연결")에 대한 사실 확인만 담았다. 설정·제품·권한·서버 변경 **0**.
DB 접속은 전부 `BEGIN READ ONLY`에서 `pg_catalog`/`has_*_privilege` 메타데이터 조회만 했다.

### 8.1 원래 `DATABASE_URL`은 기존 backend 기본 연결이다

| 확인 항목 | 근거 | 결과 |
|---|---|---|
| 코드상 단일 기준 | `app/core/config.py`의 `resolved_database_url()`; `app/db.py`·`app/preview/db.py`·`app/preview/config.py`가 모두 이 함수를 호출 | **예** |
| 런처가 값을 덮어쓰는가 | `scripts/run_benchmark_dev.sh:69`가 `${DATABASE_URL:?...}`로 원문 그대로 사용, 옛 DSN 6종은 `unset` | **아니오(덮어쓰지 않음)** |
| 값 출처 | Koyeb 앱 `benchmark-v3` / 서비스 `api` / 활성 배포 `6b6fbe4f`의 env 엔트리 `DATABASE_URL`이 **secret 참조** | **원래 배포 연결과 동일 출처** |
| 자격 파일 값 == 그 secret | 둘 다 SHA-256 앞 12자리 `f14b615b1ae9`로 대조(값 비출력, 임시 파일 즉시 삭제) | **동일(True)** |
| 같은 배포의 실행 명령 | `uvicorn app.main:app --host 0.0.0.0 --port 8000` | 이 저장소 앱이 맞음 |
| repo `.env` | 현재 없음(`.gitignore` 대상, git 이력에 커밋된 적 없음) | 코드 기본값은 `PLACEHOLDER_DATABASE_URL`이며 연결에 쓰이지 않음 |

즉 원래 연결은 "저장소 파일 기본값"이 아니라 **외부 0600 자격 파일의 `DATABASE_URL`**이며,
그 값은 활성 배포의 `DATABASE_URL` secret과 같다. 이것이 기존 backend의 기본 연결이다.

### 8.2 새 전용 DSN들과 같은 DB 대상인가

| env 키 | 역할(사용자명) | 같은 DB 대상(host+port+db) | 비고 |
|---|---|---|---|
| `DATABASE_URL` (원래) | `postgres` | 기준 | 비밀번호 길이 16 |
| `PREVIEW_DEV_DATABASE_URL` | `preview_dev_app` | **동일(True)** | 개발 저장 역할 |
| `PREVIEW_FIXTURES_DATABASE_URL` | `preview_dev_fixture_ro` | **동일(True)** | 구 런타임 fallback |
| `PREVIEW_IDENTITY_DATABASE_URL` | `preview_dev_identity_ro` | **동일(True)** | 계정 조회 역할 |
| `PREVIEW_NAMES_DATABASE_URL` | `preview_dev_names_ro` | **동일(True)** | 이름 조회 역할 |
| `PREVIEW_STATS_DATABASE_URL` | `preview_dev_stats_ro` | **동일(True)** | 통계 조회 역할 |

여섯 DSN 모두 host(풀러, `*.supabase.com`)·port 5432·database `postgres`가 같고
**역할만 다르다**. 대조는 파싱 결과를 메모리에서 비교했고 원문은 출력하지 않았다.

사용자명은 Supabase 풀러 규칙대로 `<역할>.<프로젝트ref>` 형태다. 여섯 DSN의
프로젝트 ref가 **동일(1개)** 함을 SHA-256 앞 8자리로 대조했고, 접속 후 `current_user`는
각 DSN에서 `postgres` / `preview_dev_app` / `preview_dev_fixture_ro` /
`preview_dev_identity_ro` / `preview_dev_names_ro` / `preview_dev_stats_ro`로 해석됐다.
따라서 같은 DB·같은 프로젝트 안에서 역할만 분리된 상태다.

코드도 더 이상 전용 DSN을 읽지 않는다(`app/preview/config.py`의 호환 property 5종이
전부 `configured_database_url()` 하나를 돌려줌). 남은 `PREVIEW_IDENTITY_DATABASE_URL`
문구는 `app/core/sessions.py`·`app/api/v1/auth.py` **docstring 주석**뿐이며 실제 분기 코드가 아니다.

### 8.3 현재 writer 권한 (원래 계정 vs 개발 저장 역할)

`BEGIN READ ONLY`에서 `has_table_privilege`/`has_schema_privilege`/`has_sequence_privilege`만 조회.

| 항목 | 원래 `DATABASE_URL` 계정 | `PREVIEW_DEV_DATABASE_URL` 역할 |
|---|---|---|
| role 속성(super/createrole/createdb/canlogin) | `false / true / true / true` | `false / false / false / true` |
| `public` 테이블 수 | 28 | 28 |
| `public` SELECT/INSERT/UPDATE/DELETE 전부 보유 | **28 / 28** | **0 / 28** |
| `public` 표 소유자 본인 | **28** | 0 |
| `public` 스키마 USAGE / CREATE | **true / true** | true / **false** |
| `preview_dev` 테이블 수 | 16 | 16 |
| `preview_dev` 4종 전부 보유 | **16 / 16** | 16 / 16 |
| `preview_dev` 스키마 USAGE / CREATE | true / true | true / true |
| 시퀀스 19개 USAGE 누락 | **0** | 19 |

요약: **원래 계정은 이미 `public` 전체 읽기·쓰기와 `preview_dev` 16개 표 전체 권한을
모두 보유한다.** 쓰기 권한을 새로 만들 필요가 없다. 반대로 개발 저장 역할은 공개 영역
권한이 전혀 없어 "프리뷰도 같은 연결" 요구를 그 역할로는 만족할 수 없다.

### 8.4 현재 런타임 사실 (변경 없음)

- 이 조사 시점에 기준 런타임 PID 66697은 **이미 종료**되어 존재하지 않는다.
- 포트 8000 리스너는 다른 프로젝트 컨테이너 `second-brain-api-1`이며(`/openapi.json` 제목
  `Second Brain MCP`, `/api/v1/home/recommendations` → 404), benchmark backend가 아니다.
  이 컨테이너는 조사 대상이 아니므로 열지 않았다.
- 5173 프론트(`frontend`)는 살아 있고 프록시 대상은 `http://127.0.0.1:8000`이다.
  따라서 지금 상태로 프론트 경유 홈 조회는 benchmark 백엔드가 아니라 남의 앱에 붙는다.
- 앱 코드를 원래 연결로 **읽기 전용 1회** 실행한 결과: `home_preview.recommendations()`가
  **정상 동작**(`display_date 2026-11-21`, items 1, `as_of 2026-11-13T15:04:28Z`,
  `fallback_reason no_eligible_today`)했다. 이전 42501(league_sync_target 등)은 재현되지 않았다.

### 8.5 남은 실제 결함 (권한 아님)

- `home_preview_publication`/`version`/`snapshot`/`attempt` 표는 **어떤 스키마에도 없다**
  (`pg_class` 0건). 그래서 각 아이템의 `preview`가 `state: unavailable`로 나온다.
  이것은 권한 문제가 아니라 **저장 표 미생성**이며 표를 `public`에 만들면 기존 영역 구조
  변경이 되어 AGENTS.md 기준과 충돌한다. 표를 둘 스키마 확정이 먼저 필요하다.
- 이건 이번 조사 범위(사실 확인)를 벗어나므로 수정하지 않았다.

## 9. 미확인 한계

- `preview_dev.schema_migrations`의 실제 컬럼 구성을 읽지 못해(`version_num` 부재, 42703)
  개발 스키마 마이그레이션 이력의 정확한 최신 버전은 확인하지 않았다.
- 풀러가 세션 옵션을 무시하는 이유(transaction pooling 모드 여부)는 이 조사 범위에서
  더 파지 않았다. 관측 사실(옵션 미전달)만 기록한다.
- 표 부재가 "아직 적용 전"인지 "다른 스키마로 옮겨졌다가 삭제"인지는 git 이력만으로
  단정하지 않았다. 현재 작업 트리에서 관련 파일이 삭제 상태라는 사실만 확인했다.
- 원래 repo `.env`의 기본 DB 대상(로컬)과의 비교는 해당 파일이 없어 **실제 값 비교가 아니라
  부재 확인**으로 대체했다. 다만 §8에서 원래 연결의 실제 출처(외부 자격 파일 == 활성 배포
  secret)를 확인했으므로, 이 한계는 "저장소 파일 기본값이 없다"는 사실로 한정된다.
- 원래 계정의 `role` 속성 중 `rolcreaterole=true`, `rolcreatedb=true`는 사실 기록일 뿐이며
  이번 작업에서 역할·DB 생성은 하지 않았다.
- 프리뷰 저장 표(`home_preview_*`)의 대상 스키마 미정은 이 조사의 미확인이 아니라
  **사용자 결정이 필요한 열린 결정**이다.
