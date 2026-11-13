# HOME-DB-R 단일 연결 변경 한정 검토

작성: DeepSeek flash-1017 독립 검토 워커(읽기 전용 1회). 사용자 설정 Max 유지.
범위는 `home-db-review-brief.md`의 다섯 경계와 `home-db-final-runtime-brief.md`의 후속 범위뿐이다.
제품·테스트·Plans·비밀파일 편집 0. 모델 호출·DB 접속/쓰기·HTTP 요청·pytest/전체 suite·서버 재시작 0.
작성 파일은 이 보고서 하나다.

실행한 확인은 정적 읽기, `git diff/show`, 소스 문자열 검사, 자격 파일의 **키 이름·mode·값 동일성 boolean 비교**(값 미출력),
import 가능성 확인(`app.main`/`app.db`/`app.core.config`), 설정 객체 속성 존재 확인뿐이다.

## 0. 판정 요약

| # | 경계 | 판정 | 근거 위치 |
|---|---|---|---|
| 1 | 원래 `DATABASE_URL` 하나가 조회·인증·preview reader/writer의 단일 자격 증명 | 통과 | `app/core/config.py:56-59,209-232`, `app/db.py:76-116`, `app/preview/config.py:86-122`, `app/preview/db.py:46-57` |
| 2 | 옛 PREVIEW DSN 우회 소멸 | 통과(런처 기준) | `scripts/run_benchmark_dev.sh:87-92`, `app/preview/config.py:12-17`, `app/preview/sources/player_stats.py:408-436` |
| 3 | launcher가 원래 값을 덮어쓰지 않음 + 미설정 실패 | 통과 | `scripts/run_benchmark_dev.sh:37-46,67-72,89-92` |
| 4 | local auth/JWT·ADMIN·공개 GET 계약 보존 | 통과 | `app/api/v1/auth.py:96-124,146-177`, `app/preview/access.py:41-51`, `app/api/v1/home_preview.py:17-32` |
| 5 | 기존 public 자료 무변경·`preview_dev` 명시 저장·서로 다른 Base | 통과 | `app/preview/models.py:48,54-403`, `app/auth/models.py:38-39`, `app/models/base.py`, `app/preview/db.py:38-40` |
| 6 | 구현자 보고 USER 로그인 200 실패 = ADMIN 생성 경로 회귀인가 | **회귀 아님**(테스트 기대 불일치) | 아래 3절 |
| 7 | 24/67 검사의 현재 수용 기준 관련성 | 24는 무관, 67은 근거 없음 | 아래 4절 |
| 8 | runtime 후속 최소 권한 범위 | 범위는 기존 `preview_dev` 표+USAGE로 한정 타당(시퀀스 불필요) | 아래 5절 |
| 9 | 비밀값 출력·추적 파일 유입 | 통과 | 아래 6절 |

**차단 항목 0건.** 현재 코드는 원래 `DATABASE_URL` 하나로 통합 backend·인증·preview caller를 연결하며,
이 검토 시점 소스에서 서버 재시작을 막는 필수 경로 결함은 확인되지 않았다. 남은 실행 조건은 두 가지다:
(a) `preview_dev` 저장 쓰기는 5절 권한 부여 전까지 실패하고, (b) **public 홈 조회의 SELECT 권한**
(`league_sync_target`·`team_translation`·`league_translation`)이 원래 계정에 없으면 `home/recommendations`가 42501로 503이 된다.
홈 publication 표 부재는 별도 작업(18:23~18:29 `app/services/home_preview.py` 변경)으로 이제 **미제공으로 흡수**되지만,
그 변경은 이 검토의 검토 대상(HOME-DB-02 소유 파일)이 아니므로 판정하지 않는다.

> **스냅샷 주의.** 이 검토 중 다른 에이전트가 같은 워크트리를 계속 수정했다(`app/services/home_preview.py` 18:29, `.pytest_cache` 18:33,
> `tests/unit/test_benchmark_preview_runtime.py` 18:27). 아래 판정은 **17:17~17:33에 저장된 HOME-DB-02 핵심 파일**
> (`app/core/config.py`, `app/db.py`, `app/preview/config.py`, `app/preview/db.py`, `scripts/run_benchmark_dev.sh`, `app/auth/*`)
> 을 기준으로 하고, 다른 소유 영역의 변경은 인용 시 시각을 함께 적었다.

## 1. 단일 자격 증명과 옛 DSN 우회

- 기준값은 `app/core/config.py:56-59`의 `database_url` 하나이고, 미설정은 자리표시자(`:17-20`)로 표현해
  `configured_database_url()`이 `None`을 돌려준다(`:209-218`). `resolved_database_url()`은 대체 없이 `MissingDatabaseUrl`로 멈춘다(`:221-232`).
- 프리뷰 축 `PreviewSettings`는 DB 주소를 **필드로 복제하지 않고 property로만** 노출한다
  (`app/preview/config.py:63-64,86-122`). `database_url`·`identity_database_url`·`fixtures_database_url`·
  `names_database_url`·`stats_database_url`·`resolved_identity_database_url`이 모두 같은 두 함수를 호출한다.
  `env_prefix="PREVIEW_"`(`:57`)는 유지되지만 `database_url` 필드가 없어 옛 `PREVIEW_*` 키가 값을 바꾸지 못한다.
- caller 매핑(모두 같은 값):
  - 일반/홈 조회: `app/db.py:76-88` → `create_engine(normalize_database_url(url))`
  - 인증/`/me`/ADMIN 판정: `app/db.py:96-116`, `:171-180` (`get_auth_db_session`은 `get_db_session`과 같은 세션을 돌려줌)
  - preview 저장: `app/preview/db.py:46-57` → `resolved_database_url()`
  - preview 이름/통계 조회: `app/preview/sections.py:1148-1155`, `app/preview/sources/player_stats.py:408-436`
  - 계정 원장 조회기: `app/auth/identity.py:152-173` (`build_read_only_engine`은 이름만 유지, 강제 읽기 전용 옵션 없음)
- 강제 읽기 전용 흔적: `app/db.py`에 `READ_ONLY_CONNECT_ARGS`/`default_transaction_read_only`가 없다(검색 결과 0).
  남은 `read_only` 문자열은 표시용(`app/db.py:206`, `app/api/v1/preview_metrics.py:116`)이다.
- 옛 DSN 우회: 런처가 여섯 키와 `BENCHMARK_READ_DATABASE_URL`을 `unset`한다(`scripts/run_benchmark_dev.sh:87-92`).
  앱 코드에서 옛 키를 **환경으로 읽는 곳은 없다**. 남은 문자열은 `app/preview/config.py:12-17`의 설명 주석과
  `app/preview/sources/player_stats.py:60`의 표시용 라벨 상수(권한 없음 사유에 이름만 남김)뿐이다.
- `preview_dev` 저장이 `search_path`에 의존하지 않는다(중요). 모델 11개 표가 metadata상 모두 `preview_dev.*`이고
  (`app/preview/models.py:48`의 `_TABLE_ARGS` + 각 모델 `__table_args__`), 원시 SQL도 스키마를 생략한 preview 표 참조가 0건이다.
  따라서 HOME-DB-01이 관측한 "풀러가 `-c` 옵션을 서버에 전달하지 않는다"는 사실이 있더라도 **저장 위치는 여전히 `preview_dev`로 확정**된다.
  `connect_args`의 `search_path`(`app/preview/db.py:55`)는 보조 장치다.
- 자격 파일 실측(값 비출력): `~/.config/match-preview/preview-dev.env` mode `600`, `DATABASE_URL` **1건**,
  옛 다섯 키는 각각 `DATABASE_URL`과 **다른 값**(동일성 False)이며 **host/port/database는 모두 동일**(True).
  즉 원래 계정과 옛 전용 역할들이 같은 DB 대상을 보고 있고, 앱은 그중 원래 값만 소비한다.

## 2. launcher·미설정 실패·인증/공개 GET 계약

- launcher는 `DATABASE_URL="${DATABASE_URL:?...}"`(`:69`)로 **값을 만들지 않고 요구만** 한다.
  `PREVIEW_ALLOW_NONLOCAL_DB`도 명시 요구(`:72`), `JWT_SECRET_KEY` 요구(`:76`), 자격 파일 mode 검사(`:42-46`, 모델 파일 `:56-60`),
  `WORKER_SCHEDULER_ENABLED`/`HOME_PREVIEW_ENABLED` 기본 false(`:83-85`), 자동 migration 없음(`:31`)이 그대로다.
  모델 자격 파일에는 `DATABASE_URL` 키가 없어(키 이름 확인) 원래 값을 덮어쓸 경로가 없다.
- 미설정 실패: 엔진은 만들되 `creator=_refuse`로 **모든 연결 시도**가 `MissingDatabaseUrl`이 된다(`app/db.py:50-84`).
  `_account_session`이 이를 잡아 503으로 드러낸다(`:142-168`). 런처가 미설정 시 기동을 거부하므로 실서버 경로에서는 먼저 실패한다.
- local auth/JWT: 로컬 프로필은 refresh 상태만 `preview_dev.preview_admin_sessions`에 남기고 계정 행을 갱신하지 않는다
  (`app/api/v1/auth.py:99-124`, `app/services/auth.py:85-110`, `app/auth/benchmark_sessions.py:1-26`). JWT 클레임·응답 모양은 그대로다.
- ADMIN: 모든 preview 관리 엔드포인트에 `require_preview_admin`이 붙어 있음을 정적으로 전수 확인했다
  (`app/api/v1/preview_admin.py`, AST 전수 확인 32개 라우터 전부 `require_preview_admin` 보유·누락 0; `app/api/v1/preview_metrics.py:69`; 판정은 `app/preview/access.py:41-51`의 JWT+역할).
- 공개 GET: `/api/v1/home/recommendations`·`/fixtures/{id}/prematch`에 `Depends(get_db_session)`만 있고 인증 의존성이 없다
  (`app/api/v1/home_preview.py:14-32`). 저장소 오류는 `SQLAlchemyError`/`ValueError` → 503 계약 유지.

## 3. USER 로그인 200 보고의 귀속 (전체 검사 재실행 없음)

- 실패 지점은 `tests/preview/test_pipeline.py:426-436`이며, 기대값은 "비ADMIN은 **로그인 단계에서** 403"이다.
- 현재 로그인은 원래 benchmark 인증이다: 자격 증명이 맞는 USER면 **200 + 토큰**을 주고(`app/api/v1/auth.py:96-124`,
  `app/services/auth.py:85-110`는 역할을 보지 않는다), ADMIN 요구는 preview 진입점에서 판정한다(`app/preview/access.py:41-51`).
  같은 계약을 새 검사가 이미 고정하고 있다: `tests/unit/test_benchmark_preview_auth.py:525-542`("STREAMER도 USER도 401이 아니라 403").
- 즉 **ADMIN 생성 경로는 회귀가 아니다.** 생성·재생성 엔드포인트는 `require_preview_admin`으로 401/403을 그대로 내고,
  USER 200은 "일반 사용자 로그인"이라는 원래 인증 계약의 정상 동작이다. 실패는 통합 이후 갱신되지 않은 **테스트 기대**다.
- 이 판정은 소스 경계 비교이며 pytest를 실행하지 않았다.

## 4. 구현자 보고 24/67 검사의 관련성

- "24"는 저장소에서 `docs/implementation/match-preview/evidence/23-mp02-frontend.txt:13`의 frontend `24 passed`(2026-11-10, vitest 3파일)와 일치한다.
  이는 **프론트 단위검사** 결과로 DB 단일 연결 수용 기준과 무관하다.
- "67"에 해당하는 산출물(로그·요약)을 저장소에서 찾지 못했다. 이 보고서는 그 수치를 근거로 채택하지 않는다.
- `.pytest_cache`는 **다른 프로세스가 pytest를 실행하며 계속 갱신**했다(lastfailed 18:30:25, nodeids 18:33:50; 이 검토는 pytest를 실행하지 않았다).
  최종 스냅샷(45건)을 현재 소스와 대조하면:
  - 이름이 현재 파일에 없거나 파일 단위 항목: **9건**(`test_outlook_module.py` 파일 항목 1 + 옛 이름 8:
    `test_benchmark_preview_auth` 3, `test_bundle_integration` 2, `test_pipeline`/`test_bundle_runtime`/`test_bundle_sections` 각 1).
  - `tests/preview/test_db_target.py`: **18건**. `Settings(database_url=...).assert_local_database()`를 호출하는데
    `app.core.config.Settings`에 그 메서드가 이제 없다(`AttributeError` 확인). 7절-2의 가드 이동/누락과 같은 원인이다.
  - `tests/preview/test_outlook_module.py`: **15건**. `test_outlook_module.py`와 `app/preview/modules/outlook.py`는 모두 HEAD 그대로이고
    `git status`상 이번 변경에서 수정되지 않았다. 이번 단일 연결 변경 소유가 아니다.
  - `tests/preview/test_pipeline.py`: **1건**(`test_admin_preview_run_endpoint_requires_admin`, 3절).
  - `test_bundle_integration`/`test_bundle_pipeline`: 각 1건(미추적 신규 파일, 이번 변경 소유 밖).
  - `tests/unit/test_benchmark_preview_runtime.py`: 이번 스냅샷에는 **없다**(18:10 스냅샷에서는 2건이 있었다). 그 2건은
    `preview_db.get_engine()`/`describe_target()`을 `DATABASE_URL` 없이 호출해 `MissingDatabaseUrl`로 실패하는 환경 의존 실패였고
    (비연결 확인), 해당 파일은 18:27에 다른 에이전트가 수정했다. 두 스냅샷 모두에서 이 파일의 실패는 **단일 연결 코드의 기능 회귀 증거가 아니다**.
  재실행하지 않았으므로 위 항목의 실제 실패 문구는 보지 않았고, 원인 귀속은 소스 대조에 한정한다.
  다만 `test_db_target` 18건은 `AttributeError`를 코드로 재현해 원인을 확인했다.
- **전체 suite 추가 실행은 범위 이탈로 기록**한다(재실행·일반 수리 확대 없음).
- **전체 suite 추가 실행은 범위 이탈로 기록**한다(재실행·일반 수리 확대 없음).

## 5. runtime 후속 최소 권한 범위 (실행은 구현자)

- 대상은 기존 `preview_dev` 표와 스키마 USAGE로 한정하는 것이 타당하다. 원래 계정은 public 전체 권한을 이미 갖고 있으므로
  public 쪽 신규 GRANT·소유권 이전·`ALTER DEFAULT PRIVILEGES`가 필요 없다(계획 `:5`, 최종 브리프 `:10`).
- 시퀀스 권한은 **불필요**하다: `app/preview/models.py`·`app/auth/models.py`의 PK는 모두 UUID/문자 기반이고
  `Identity(`·`Sequence(` 사용처가 0이다. 브리프의 "시퀀스" 항목은 실제로 대상 없음으로 보고하면 된다.
- 모델 기준 `preview_dev` 표는 11개(`preview_runs`, `preview_module_executions`, `preview_attempts`, `preview_source_snapshots`,
  `preview_results`, `preview_artifacts`, `preview_write_audit`, `preview_section_approvals`, `preview_section_results`,
  `preview_pipeline_runs`, `preview_admin_sessions`). HOME-DB-01의 16개와 차이는 migrations 이력 표와 checkpoint 표로 보이며,
  실제 개수·부족 대상은 구현자가 메타데이터로 전후 비교해야 한다(이 검토는 DB를 열지 않았다).
- 스키마 CREATE까지 열지는 것은 이번 범위가 아니다(새 표 생성은 승인 대상 아님). checkpoint `setup()`처럼 표를 새로 만드는 경로는
  별도 판단으로 남긴다.

## 6. 비밀값

- 자격 파일 값은 출력하지 않았다. 비교는 mode·키 개수·동일성 boolean·host/port/database 동일성만 사용했다.
- 추적 파일(`git ls-files`) 전수 검사에서 자격 파일의 사용자명·비밀번호·원문 DSN·host 토큰 포함 파일 **0건**.
  워크트리 전체(벤더·캐시 제외) 검사에서 유일한 hit는 `docs/implementation/match-preview/production-login-discovery.md`이며,
  포함된 것은 **pooler 호스트 이름**뿐이고 비밀번호·사용자명은 포함하지 않는다(기존 문서, 이번 변경과 무관).
- 새로 쓰인 코드·런처·보고서에는 DSN/비밀번호가 없다. 런처는 값을 `export`만 하고 출력하지 않는다(`:94-99`).

## 7. 후속 참고 (차단 아님 — 이번 변경이 만든 부수 손상 포함)

아래 1·2는 기존 결함이 아니라 **이번 변경 기간에 새로 생긴 손상**이다(가드 API가 `app.core.config`에서 `app.preview.config`로 옮겨졌고,
`app/db.py`가 경로 확인을 호출하지 않는다). 둘 다 재시작·조회·생성 같은 필수 경로에는 걸리지 않으므로 이번 수용을 막지 않는다.
다만 둘 다 저장소의 기존 계약을 깬 상태이므로, 다음 수정 단위에서 최소 범위로 정리할 것을 권고한다.

1. **`alembic/env.py`가 현재 import 단계에서 깨진다**(이번 변경의 부수 손상). `alembic/env.py:17`의 `from app.db import Base`는
   `ImportError`(확인: `from app.db import Base FAILED: cannot import name 'Base'`)이고, `:29`의 `settings.assert_local_database()`도
   더 이상 `app.core.config.Settings`에 없다(확인: `AttributeError`). 서버 기동·조회 경로는 alembic을 쓰지 않고(런처 `:31`),
   `scripts/preview_dev_migrate.py`도 alembic `env.py`를 호출하지 않는다(마이그레이션 모듈을 직접 import). 그래서 필수 경로 영향은 없다.
   최소 수정: `from app.models.base import Base`로 바꾸고 대상 확인은 `app.preview.config`의 `assert_local_database()`를 쓴다.
2. **일반 연결(`app/db.py make_engine`)이 경로 확정 가드를 호출하지 않고, docstring과 어긋난다.** `app/db.py:13-14`는 "연결 대상 확인은
   `app.preview.config` 계약을 그대로 쓴다"고 적었지만 `make_engine()`(`:76-84`)은 그 검사를 하지 않는다(실제 호출은 auth 엔진 `:109`와
   preview 저장 엔진 `app/preview/db.py:47`에만 있다). HEAD에서는 `app/db.py`가 `preview_dev` 저장 전용이고 `_build()`가
   `assert_local_database()`를 먼저 불렀으므로, **이번 변경이 그 모듈의 역할을 일반 조회/인증 연결로 넓히면서 가드를 옮기지 않은 결과**다.
   결과적으로 URL 밖에서 목적지를 바꾸는 형태(`?host=`, 다중 host, 비Postgres 스킴)를 일반 조회 연결에서 연결 전에 거부하지 않는다.
   현재 런처 값은 목적지가 확정 가능한 단일 URL이고(쿼리 키 0, 단일 host, 비루프백 동의 플래그 설정됨) 실제 접속은 DB 권한이 결정하므로
   필수 경로 동작에는 영향이 없지만, 보호가 한 겹 줄었다. `tests/preview/test_db_target.py:98-163`이 이 계약을 고정하고 있어
   그 18건이 실패 상태다(4절). 최소 수정: `make_engine()`에서 `get_preview_settings().assert_local_database()`를 먼저 부르고,
   해당 테스트의 `Settings(...)`도 `app.preview.config.PreviewSettings`로 맞춘다.
3. 문서 드리프트(동작 영향 없음): `app/core/sessions.py:5`, `app/api/v1/auth.py:5`가 아직 "좁은 읽기 전용 `PREVIEW_IDENTITY_DATABASE_URL`"을
   설명하고, `app/preview/models.py:5`는 `app/db.py`가 `search_path`를 고정한다고 적었다(이제 고정은 `app/preview/db.py:55`).
   `.env.example:5,9`도 옛 두 DSN 이름을 안내한다.
4. `scripts/run_preview_dev.sh`는 여전히 옛 DSN을 `PREVIEW_DATABASE_URL`/`PREVIEW_IDENTITY_DATABASE_URL`로 매핑하고 `DATABASE_URL`을
   설정하지 않는다. 스스로 "통합 증거로 쓰지 않는다"고 밝힌 비교용 경로라 필수 경로는 아니지만, 이 스크립트로 띄우면 원래 연결이
   없어 실패한다(경로 폐기 또는 `DATABASE_URL` 요구로 정리 필요).
5. `MissingDatabaseUrl`은 `RuntimeError`라 `app/api/v1/home_preview.py:19-32`의 `except`에 걸리지 않는다. 런처가 미설정 기동을
   막으므로 실경로 노출은 없으나, 앱을 우회 기동하면 공개 GET이 503이 아니라 500이 된다.
6. `app/auth/service.py`(구 관리자 세션 판정)는 현재 어떤 라우터도 import하지 않는다(검색 결과 0). 실제 경계는 `app/preview/access.py`다.
   죽은 중복 모듈이라 동작 영향은 없으나, 같은 이름의 `require_preview_admin`이 둘 존재해 혼동을 부른다.
7. **홈 추천이 남은 실패 조건**(이번 검토 범위 밖의 동시 변경과 함께 판단해야 한다): `app/services/home_preview.recommendations()`는
   `active_pairs()`→`public.league_sync_target`, `names()`→`public.team_translation`, `league_names`→`public.league_translation`을
   조건 없이 읽는다(`app/services/home_preview.py:114-152,333-335`). 이 세 표의 SELECT가 원래 계정에 없으면 42501이 그대로 올라가 503이다.
   반면 publication/version 표 부재는 18:23~18:29 변경으로 세션 SAVEPOINT + 42P01 대상 확인을 거쳐 "미제공"으로 흡수된다
   (`:50-92,199-202`). 즉 **재시작 후 홈 GET 성공 여부는 (a) 원래 계정의 public SELECT 권한과 (b) 5절 preview_dev 쓰기 권한에 달려 있고,
   publication 표 부재만으로는 더 이상 503이 아니다.** 두 조건 모두 구현자 후속(권한 확인·부여)과 실제 GET 확인으로 판정해야 한다.
   이 항목은 소스 경계 판독이며, 해당 변경의 정확성은 별도 검토 대상이다.

## 8. 미확인(이 검토에서 열지 않은 것)

- 실제 DB 권한·표 존재·표 개수의 재확인(구현자 후속 영역). HOME-DB-01/02 보고를 그대로 인용했다.
- 실제 로그인·HTTP GET·재시작 후 동작. 모델·DB·HTTP·pytest 실행은 배정상 금지다.
- pytest 45건 실패의 재현과 원인 확정(4절). 이번 변경과 무관한 영역은 판정하지 않았다.

## 9. 후속 확인: tests/unit 25 passed / 2 failed 보고 경계 판정 (2026-11-14 02:00)

조정자 요청 범위는 "보고된 runtime 2건 실패가 현재 단일 연결 수용에 영향을 주는지, 기존 검토 경계 안에서만 판정"이다.
DB 접속·pytest 재실행·서버 조작은 하지 않았다(조정자 지시). 확인은 정적 읽기와, 같은 식을 소켓 없이 실행하는 오프라인 대조뿐이다.

- `tests/unit`에는 `conftest.py`가 없다(`tests/preview/conftest.py`만 있고 그 디렉터리 하위에만 적용된다).
  그래서 이 묶음은 `DATABASE_URL`을 프로세스 환경에서만 받는다. 이 셸에는 `DATABASE_URL`이 없고 `.env`도 없다(값 미출력 확인).
- 두 실패는 모두 `MissingDatabaseUrl` 경로다. 같은 식을 오프라인으로 직접 실행해 확인했다(접속 없음).
  - `test_benchmark_and_preview_use_different_bases_and_engines`(`tests/unit/test_benchmark_preview_runtime.py:67-73`)의
    첫 단언이 `preview_db.get_engine()`을 부르고, 그 함수는 `_build()`에서 `assert_local_database()`를 거쳐
    `resolved_database_url()`을 먼저 통과한다(`app/preview/db.py:46-49`). URL이 없으면 `MissingDatabaseUrl`로 멈춘다.
  - `test_account_reader_always_uses_the_original_connection`(`:121-169`)는 `base.connection()`과 `describe_target()`을 부른다.
    각각 `DatabaseConnectionUnavailable`(503) 변환(`app/db.py:150-168`)과 `resolved_database_url()`(`app/db.py:199-209`)에 걸린다.
- 설정이 채워지면 단일 연결 계약 자체는 소스상 유지된다. 아래는 직접 실행한 결과다.
  - 루프백 URL, allow 플래그 없음: 1번 검사의 두 단언 모두 통과.
  - 비루프백 URL + `PREVIEW_ALLOW_NONLOCAL_DB=true`: 통과. 거부는 비루프백 URL에 동의 플래그가 없을 때만 생기고
    (`app/preview/config.py:138-148`), 그 거부는 정책이 요구하는 대상 검사다. 런처는 이 플래그를 명시 요구한다
    (`scripts/run_benchmark_dev.sh:72`). 즉 실패 조건은 검사 환경에 플래그·URL이 없다는 것이지 코드 회귀가 아니다.
- 2번 검사는 추가로 **도달 가능한 DB**를 요구한다(`base.connection()`이 실제 연결을 연다). `unit` marker의
  "no external services"(`pyproject.toml:52`)와 어긋나므로, 실 DB 없이 통과를 기대할 수 없다. 참고 사항이며 차단 아님이다.
- 보고된 25/2 수치는 실행 로그로 재구성되지 않고, 갖고 있는 자료로는 어느 판본이 실행됐는지 확정할 수 없다.
  산술적으로는 27건 중 2건 실패이므로 "auth 13 + runtime 14"가 들어맞지만, 그것을 뒷받침하는 관측이 없다.
  근거는 `.pytest_cache/v/cache/nodeids`가 실행마다 누적 합집합으로 갱신되어 디스크에 없는 옛 이름까지 남아 있다는 점이다
  (2026-11-14 01:51 갱신; `lastfailed`는 2026-11-13 05:53 스냅샷). 캐시는 현재 파일보다 **많은** 이름을 갖고 있다:
  runtime 14건 대 현재 12건, auth 16건 대 현재 13건. 빠진 이름 중 런타임 쪽 둘
  (`test_account_reader_keeps_the_original_connection_in_the_production_profile`,
  `test_only_the_known_preview_tables_may_degrade_to_unavailable`)은 옛 판본 이름이며 첫째는
  `docs/implementation/match-preview/bi-integration-review.md:58`이 인용한다. 그러나 캐시가 합집합이므로
  "실행 시점 auth는 13건이었다"를 캐시로 증명할 수 없다. 그래서 25·2를 수용 근거로 채택하지 않고,
  위에서 직접 대조한 실패 모드만 근거로 쓴다(4절의 "개수 수치 미채택"과 같은 기준).
- 판정은 **단일 연결 수용에 영향 없음**이다. 두 실패는 설정·DB 가용성이 없는 실행 환경의 산출물이고, 0절의 결론
  (단일 자격 증명·권한 경계 차단 0)과 8절의 미확인 항목을 바꾸지 않는다. 공개 추천의 42P01 처리와 HOME-LIST-01 수정은
  별도 범위이므로 이 판정에 넣지 않는다.
