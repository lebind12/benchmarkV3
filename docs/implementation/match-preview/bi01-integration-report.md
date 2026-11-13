# BI-01 인계 보고 — 원래 benchmark 앱·인증·DB 통합

작성: 2026-11-12 KST. 담당: DeepSeek 구현 워커 A (Orca term_aa6f203c).
Task `task_f226b3be2155` / Dispatch `ctx_a74d583b9de1`.

실제 모델: `deepseek-ai/deepseek-v4.1-flash-1017` (DSH Orca worker). 프로필·비밀 설정은
조회·변경하지 않았다. 모델을 바꾸지 않았다.

범위 ACK: 이 문서의 "A 소유" 파일만 편집했다. B 전용 파일(`app/api/v1/preview_admin.py`,
`app/services/match_preview.py`, `app/preview/{retry,provider,bundle_pipeline,store,
section_preview,discovery,contracts,version_manifest}.py`,
`modules/bundle_sections.py`, B 테스트, `scripts/preview_bundle_live_once.py`)과
`frontend/**`·`out/**`·`Plans.md`는 수정하지 않았다. 커밋하지 않았다. 모델 호출·
외부 수집·운영 쓰기·새 마이그레이션·새 grant·배포·기존 서버 재시작은 하지 않았다.

---

## 1. 결과 요약

원래 benchmark 앱(인증·관리·홈·수집 조회)과 프리뷰 기능이 **하나의 FastAPI 앱**
(`app.main:app`)에 있다. 원래 라우터와 프리뷰 라우터가 같은 프로세스에 있고, 인증은
원래 JWT 하나이며, DB는 목적별로 분리된다.

- 원래 benchmark 라우터: `/health`, `/api/v1/auth/*`, `/api/v1/home/*`,
  `/api/v1/admin*`, `/api/v1/fixtures*`, `/api/v1/broadcast*`, `/api/v1/*`(general).
- 프리뷰 라우터: `/api/v1/admin/preview/*` (30개 경로).
- total OpenAPI paths: **90** (실측).

원래 로그인은 기존 계정으로 동작하되 로컬 프로필에서 **기존 계정 행과 원격 세션
저장소에 쓰지 않는다**. 개발 세션만 `preview_dev.preview_admin_sessions`에 남는다.
preview 생성은 ADMIN만 가능하다. 일반 기존 관리 권한(`manager_user` = STREAMER/ADMIN)은
원래대로 보존된다.

---

## 2. 먼저 제공한 계약 (B가 import하는 경로)

| 모듈 | 계약 |
|---|---|
| `app/preview/config.py` | `get_settings() -> PreviewSettings`. `Settings`는 같은 클래스의 호환 alias(별도 singleton 아님). `PREVIEW_*` 접두어·`.env` 로딩·필드 집합 유지. 원본 `app.core.config`와 singleton 비공유. |
| `app/preview/db.py` | `get_db()`, `get_session_factory()`, `get_engine()`, `Base`, `SCHEMA='preview_dev'`, `reset_engine()`. `search_path=preview_dev` 고정. 원본 `app.db`의 `SessionLocal`/`get_db_session`/public `Base`와 완전히 별개 객체. |
| `app/preview/access.py` | `PreviewPrincipal(user_id, email, role)`, `require_preview_admin()`. 원본 `app.core.sessions.current_user`(JWT) 결과에 `role == 'ADMIN'` 요구. 비인증 401(+`WWW-Authenticate: Bearer`), 비ADMIN 403 `admin role required`. `session_id`/`expires_at` 같은 미확인 값을 채우지 않는다. |

이 계약은 구현 초반에 root에 두 번(status 메시지) 보고했다. B는 이후 실제로
`app.preview.{config,db,access}`를 import하도록 자기 파일을 바꿨다(내가 B 파일을
고치지 않았다).

---

## 3. 변경 파일

### 3.1 새로 만든 파일 (A 소유)

| 파일 | 내용 |
|---|---|
| `app/preview/config.py` | 프리뷰 전용 설정 이름공간(위 계약). |
| `app/preview/db.py` | 프리뷰 개발 저장소 엔진/세션(Base, SCHEMA). |
| `app/preview/access.py` | 원본 JWT 기반 ADMIN 경계. |
| `app/auth/benchmark_sessions.py` | 로컬 세션 adapter. `issue_session(user)`/`rotate_session(token)`/`revoke_session(token)` — 원본 `app.core.sessions`와 **같은 인자·반환 계약**, 같은 JWT 클레임. 저장만 `preview_dev`이고 회전은 조건부 UPDATE 1회로 원자적. |
| `scripts/run_benchmark_dev.sh` | 통합 앱 로컬 런처(`uvicorn app.main:app`). 0600 자격 파일을 프로세스 환경으로만 전달, 값 미출력. scheduler off·자동 migration 없음·자동 시작 없음. |
| `tests/unit/test_benchmark_preview_runtime.py` | 직접 검사 ① (라우터·세션 bind·스키마). |
| `tests/unit/test_benchmark_preview_auth.py` | 직접 검사 ② (로그인 계약·refresh·/me·권한·무변경). |

### 3.2 수정한 파일 (A 소유)

- `app/main.py` — 원래 benchmark 라우터 전체 + 프리뷰 라우터를 한 앱에 등록. `/health`
  는 원래 계약(`{"status":"ok"}`). 검증 오류 스크러버 설치. `create_app()`은 같은 앱을
  돌려주는 팩토리(기존 검사 호환).
- `app/core/config.py` — 원본 복구 후 `local_dev_auth_enabled`(기본 `False`) 추가.
  운영 배포는 이 플래그를 설정하지 않으므로 원래 동작 그대로다.
- `app/db.py` — 원본 복구 + 로컬 프로필에서 `default_transaction_read_only=on` 강제
  (기존 영역 쓰기를 DB가 거부). `describe_target()`은 비밀값 없이 대상 요약만 준다.
- `app/api/v1/auth.py` — 원본 login/refresh/me/logout/signup 계약 유지. 로컬 프로필에서만
  ① `last_login_at` 미갱신(`touch_last_login=False`) ② 세션 저장을 `benchmark_sessions`로
  ③ signup 403. **Origin 검사는 그대로 유지**(끄지 않았다).
- `app/services/auth.py` — `login_user(..., touch_last_login: bool = True)`. 기본값은 원래
  동작(운영 경로 무변경).
- `app/auth/models.py`, `app/auth/service.py` — import를 `app.preview.{db,config}`로 이관.
  `app/auth/service.py`는 이제 앱에서 쓰이지 않는 이전 프리뷰 전용 세션 서비스다(삭제하지
  않고 보존 — 롤백·비교용. 아래 6절 참고).
- `app/preview/models.py`, `sections.py`, `pipeline.py`, `send_ledger.py`,
  `sources/player_stats.py` — 설정/DB import를 `app.preview.{config,db}`로 이관(A 소유
  이관 목록).
- `app/api/v1/preview_metrics.py` — `app.preview.access`/`app.preview.db`로 이관.
- `app/workers/preview.py` — `app.preview.{config,db}`로 이관.
- `requirements.txt`, `pyproject.toml` — 원래 benchmark 의존성(`PyJWT`, `jsonschema`,
  `apscheduler`, `requests`, `openai`, `google-auth`)과 프리뷰 의존성을 한 목록으로 병합.
  pytest marker 등록.
- `scripts/run_preview_dev.sh` — 통합 후에도 같은 `app.main:app`을 띄우는 경로임을 표시하고
  새 런처를 정식 경로로 안내. 실행 포트 기본값은 그대로 8000.
- `tests/preview/conftest.py` — 테스트 환경을 conftest import 시점에 설정(모듈 수준 엔진이
  placeholder URL을 붙잡지 않게), `BearerTestClient`(원래 프론트와 같은 Bearer 사용),
  스키마 DDL `lock_timeout`.
- `tests/preview/test_admin_access.py`(재작성), `test_production_auth.py`(재작성),
  `test_inspection_api.py`, `test_metrics.py`, `test_presentation.py` — 인증 계약이
  쿠키 세션 → 원래 JWT로 바뀐 직접 영향 부분만 갱신.

### 3.3 복구한 원본 파일 (c4d7d32 기준)

- `app/main.py`, `app/core/{config,security,sessions,worker_scheduler}.py`, `app/db.py`,
  `app/api/v1/auth.py`, `app/services/auth.py` — c4d7d32에서 복구한 뒤 위 병합을 얹었다.
- 삭제 상태였던 원본 `app/models/**`(18), `app/services/**`(33), `app/workers/**`,
  `app/schemas/**`, 원본 API(`app/api/home.py`, `app/api/fixture_detail.py`,
  `app/api/v1/{admin,broadcast,general,home,home_preview,management,fixture_detail_analytics}.py`)
  등 **98개 파일**을 파일 단위로 복구했다. 디렉터리 덮어쓰기·reset은 하지 않았고, B가
  그 사이 만든 신규 파일(`match_preview.py`, `bundle_pipeline.py` 등)은 그대로 보존됐다.

`app/services/**`에 B 신규 `match_preview.py`가 있는 상태를 확인했고 보존했다.

---

## 4. 실행한 명령과 결과

모든 검사는 루프백 전용 테스트 DB에서만 실행했다. 운영 DB에 pytest·초기화·create_all을
실행하지 않았다. 실제 기존 데이터는 읽기만 했다(권한 introspection).

B가 같은 테스트 DB(`preview_mp01_test`)로 자기 검사를 동시에 돌리고 있어 스키마 DDL이
서로를 막았다(내가 만든 문제가 아니라 공유 DB 경합). 그래서 내 검사는 **분리된 루프백
테스트 DB** `preview_bi01_test`로 실행했다(생성만, 로컬 55432 인스턴스).

```sh
# 직접 검사 ① — 라우터·세션 bind·스키마
.venv/bin/python -m pytest tests/unit/test_benchmark_preview_runtime.py -q
#   7 passed

# 직접 검사 ② — 로그인/refresh/me 계약, ADMIN 경계, 기존행·원격세션 쓰기 0
PREVIEW_TEST_DATABASE_URL=postgresql+psycopg://preview:preview_local_dev@127.0.0.1:55432/preview_bi01_test \
  .venv/bin/python -m pytest tests/unit/test_benchmark_preview_auth.py -q
#   10 passed

# 두 직접 검사 함께 (2회 반복, 동일 결과)
#   17 passed  (각 회)

# 영향받은 기존 인증·연결 검사
PREVIEW_TEST_DATABASE_URL=...preview_bi01_test \
  .venv/bin/python -m pytest tests/preview/test_admin_access.py \
      tests/preview/test_production_auth.py tests/preview/test_auth_input_redaction.py -q
#   39 passed

PREVIEW_TEST_DATABASE_URL=...preview_bi01_test \
  .venv/bin/python -m pytest tests/preview/test_inspection_api.py tests/preview/test_metrics.py \
      tests/preview/test_presentation.py tests/preview/test_section_approvals.py \
      tests/preview/test_run_store.py tests/preview/test_retention.py -q
#   66 passed
```

기동 확인(포트 8099, 기존 8000/5173/5174는 건드리지 않았다):

```sh
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8099
curl -s http://127.0.0.1:8099/health            # {"status":"ok"}
curl -s http://127.0.0.1:8099/openapi.json      # paths: 90
curl -s -o /dev/null -w "%{http_code}" \
  http://127.0.0.1:8099/api/v1/admin/preview/runs   # 401 (비인증)
```

B 소유 모듈이 새 계약으로 정상 import되는 것도 확인했다:
`app.services.match_preview`(=`generate_match_preview` 존재), `app.api.v1.preview_admin`.

---

## 5. 연결 계약 (root·BI-02·BI-03이 쓰는 것)

- 앱: `uvicorn app.main:app` 하나. `/health` = `{"status":"ok"}`.
- 인증: `POST /api/v1/auth/login` → `{"user": {id,email,role,nickname,is_active},
  "access_token","token_type":"bearer","expires_in":900}` + `benchmark_refresh` HttpOnly 쿠키.
  `GET /api/v1/auth/me`(Bearer), `POST /api/v1/auth/refresh`(쿠키 회전), `POST /api/v1/auth/logout`.
  Origin 검사 유지(`cors_allow_origins`).
- 프리뷰 관리: 모든 `/api/v1/admin/preview/*`가 `require_preview_admin`을 통과해야 한다
  (`Authorization: Bearer`). ADMIN 외 403, 비인증 401.
- 설정: 원래 앱은 `app.core.config.get_settings()`, 프리뷰는 `app.preview.config.get_settings()`.
  두 singleton은 분리돼 있다.
- 저장: 원래 모델 → `app.db`(public), 프리뷰 모델 → `app.preview.db`(`preview_dev`).
  두 `Base`는 합치지 않았다(검사로 단언).
- 로컬 프로필: `LOCAL_DEV_AUTH_ENABLED=true`일 때만 ① 기존 계정 행 무변경 ② 원격 세션
  저장소 미사용 ③ signup 403 ④ 원래 DB 연결 읽기 전용. 기본값 `False` = 운영 원래 동작.
- 기동 명령: `scripts/run_benchmark_dev.sh`(통합, 정식) / `scripts/run_preview_dev.sh`(비교용).

---

## 6. 남은 문제 — 읽기 권한 부족 (root가 결정해야 함)

기존 좁은 DSN으로 **원래 관리자·홈 읽기에 필요한 권한이 부족**하다. 관리자 DSN으로
우회하지 않았다. 정확한 대상만 적는다(`has_table_privilege` 읽기 전용 introspection +
`SELECT` 1회로 확인).

### 6.1 인증(로그인/`/me`/refresh) — **권한 충분**

`PREVIEW_IDENTITY_DATABASE_URL`(`preview_dev_identity_ro`)는 `public.app_user` SELECT만
있고, 로그인 경로가 필요로 하는 것은 그 하나다. **추가 grant 없이 동작한다.**

### 6.2 `/api/v1/home/recommendations` — 부족

`PREVIEW_FIXTURES_DATABASE_URL`(`preview_dev_fixture_ro`)에 없는 것:

| 대상 | 상태 |
|---|---|
| `public.team_translation` | 표 있음 · SELECT 없음 |
| `public.league_translation` | 표 있음 · SELECT 없음 |
| `public.league_sync_target` | 표 있음 · SELECT 없음 |
| `public.home_preview_publication` | **표가 DB에 없음** |
| `public.home_preview_version` | **표가 DB에 없음** |

`fixture`·`team`·`league`는 이미 읽을 수 있다. 즉 추천 목록은 번역 이름과 sync target,
그리고 홈 프리뷰 발행 표가 없어 현재 DSN으로는 완성되지 않는다.

### 6.3 `/api/v1/home/*` 나머지 — 부족

같은 DSN에 없는 것: `news_article`, `player`, `player_translation`,
`player_season_stat`, `team_season`, `transfer`.
(`fixture`,`team`,`league`,`injury`,`standings`는 있음.)

### 6.4 `/api/v1/admin/management/*` — 부족

같은 DSN에 없는 것: `api_football_league_catalog`, `coach`, `coach_translation`,
`management_run`, `team_coach`, `translation_audit`, `worker_sync_log`.

### 6.5 판단이 필요한 지점

- 위 표들은 **읽기 전용 grant**만 있으면 된다. 쓰기 권한은 필요 없다.
- `home_preview_*` 4개 표는 실제 DB에 존재하지 않는다. 원래 앱 모델은 `public` 스키마에
  선언돼 있으므로, 이 표를 만들려면 **새 마이그레이션**(이번 범위 밖, root 결정 필요)이
  필요하다. 만들지 않고 홈 recommendations를 완성할 수는 없다.
- `team_translation`/`league_translation`/`player_translation`은 **열 단위**로 이미
  `preview_dev_names_ro`에 SELECT가 있다(이름 열만). 원래 앱은 `LeagueTranslation`/
  `TeamTranslation`/`PlayerTranslation` 모델 전체를 select하므로 표 단위 SELECT가 필요하다.
  좁은 역할을 유지하려면 표 단위 grant를 주지 말고, 표시 이름 조회를
  `PREVIEW_NAMES_DATABASE_URL` 경로로 바꾸는 별도 작업이 후속 후보다(이번 범위 밖).

이 6.2~6.4 때문에 "원래 관리자·홈 읽기"는 **코드·앱 연결은 완료, 실데이터 조회는 권한
대기** 상태다. 숨기지 않고 그대로 보고한다.

---

## 7. 남은 위험·주의

1. **B 동시 실행**: B가 같은 로컬 테스트 DB(`preview_mp01_test`)로 검사를 돌리면 스키마
   DDL이 서로 막힌다. 내 검사는 분리 DB로 돌렸다. 통합 검증 시 한쪽만 돌리거나 DB를
   나눠야 한다.
2. `app/auth/service.py`·`app/auth/tokens.py`는 이제 앱에서 import되지 않는 이전 프리뷰
   전용 세션 코드다. 삭제하지 않고 보존했다(롤백 비교용). 정리 여부는 root 결정.
3. `app/core/validation.py`의 스크러버를 통합 앱에 설치했다(로그인 비밀번호가 422 응답에
   되돌아가지 않게). 원래 앱에는 없던 것이지만 기존 검사가 요구하는 보호다.
4. 프론트는 root 소유다. 5173이 통합 백엔드를 보도록 바꾸는 것, MSW 기본 off, 원래
   라우트 복구는 root 작업이다. 서버 전환도 root가 한다(자동 시작하지 않았다).
5. 로컬 55432에 내 검사용 DB `preview_bi01_test`를 만들었다(로컬 인스턴스, 운영 아님).
   필요 없으면 지워도 된다.
6. 운영 DB에 새 grant·마이그레이션·배포는 하지 않았다.

---

## 8. 사용자가 직접 할 다음 단계 (root 전환 후)

1. root가 `scripts/run_benchmark_dev.sh`로 8000을 통합 앱으로 전환(기존 프로세스 소유 확인).
2. root가 5173을 원래 benchmark 프론트 + 로컬 8000으로 연결.
3. 6.2~6.4의 읽기 권한을 **root 판단으로** 부여(읽기 전용). `home_preview_*` 표 생성 여부도
   root 결정.
4. 사용자가 브라우저에서 기존 계정으로 로그인 → 관리·홈 조회 확인 → `/admin?tab=preview`에서
   경기 번호로 생성(생성 버튼은 사용자 직접).

EDITING STOPPED.
