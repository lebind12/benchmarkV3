# MP-01 구현 보고: 최소 앱과 ADMIN 접근

**목표.** 관리자가 경기 프리뷰 도구를 쓰려면 먼저 로그인해서 실제 상태를 볼 수 있어야 한다.
이 작업은 그 첫 구간만 만든다. 관리자 로그인, 서버가 지키는 권한 경계, 그리고 저장된
실행이 없다는 사실을 그대로 보여주는 빈 실행 목록까지다. 기록·검사 화면은 MP-02 소유다.

**가장 작은 변경.** 사용자·역할·폐기 가능한 만료 세션 세 가지 데이터로 인증을 만들고,
서버의 `require_preview_admin` 하나로 모든 관리자 경로를 지킨다. 화면은 로그인과 빈
목록 두 개만 둔다.

## 실행 모델

| 항목 | 값 |
|---|---|
| 제공자 / 모델 | hive / `deepseek-ai/deepseek-v4.1-flash-1017` |
| 추론 강도 | max (유지) |
| 프로필 | dsh-tui |
| 작업 디렉터리 | `/Users/woolee/benchmark` |
| 착수 관측 시각 | 2026-11-10T16:09:03+09:00 |
| 커밋 시각 | 2026-11-10T16:24:34+09:00 |

관측 구간은 파일 타임스탬프와 명령 실행 시각으로만 적는다. 토큰 수로 시간을 추정하지
않았다.

| 구간 | 관측 시각 | 근거 |
|---|---|---|
| 문서·모델 확인, 도구 점검 | 16:09:03 ~ 16:11:12 | 착수 시각, `requirements.txt` 생성 시각 |
| 실패 테스트 작성·실패 관측 | 16:14:14 ~ 16:14:58 | 테스트 파일, `01-auth-tests-failing.txt` |
| 백엔드 구현 | 16:15:09 ~ 16:15:21 | `app/auth/service.py`, `app/main.py` |
| 프론트 구현 | ~16:21:03 | `AdminLoginView.vue`, `app.css` |
| 자체 검증 (백엔드·유닛·빌드·E2E) | 16:20:31 ~ 16:25:12 | `06-e2e.txt`, 최종 확인 시각 |
| 커밋 | 16:24:34 | `git log` |

구간이 겹치는 것은 프론트 구현과 검증을 번갈아 실행했기 때문이다. 이 수치로 다른
작업과의 속도를 비교하지 않는다.


위 값은 이 세션의 DSH 세션 기록(`model/selection`: provider `hive`, model
`deepseek-ai/deepseek-v4.1-flash-1017`, reasoningEffort `max`)에서 확인했다. 프롬프트에
적힌 값만으로 판단하지 않았다. 모델·설정은 변경하지 않았다.

## 로컬 환경

| 도구 | 확인 결과 |
|---|---|
| Python | 3.11.4 (`.venv`) |
| Node / npm | 22.19.0 / 11.11.0 |
| PostgreSQL | Docker `postgres:17-alpine`, 컨테이너 `match-preview-pg-mp01`, `127.0.0.1:55432` |

호스트에 `psql`·`pg_ctl`이 없고 Docker는 동작 중이어서, 격리된 로컬 컨테이너로
PostgreSQL을 준비했다. SQLite로 대체하지 않았다. 개발 DB(`preview_mp01_dev`)와 테스트
DB(`preview_mp01_test`)를 분리했고, 테스트는 매 테스트마다 `public` 스키마를 새로 만든다.
`PREVIEW_DATABASE_URL`이 루프백이 아니면 앱·마이그레이션·테스트가 거부한다.

## 데이터 형태

| 구조 | 내용 |
|---|---|
| `User` (`preview_users`) | id, email(unique), password_hash(argon2), role(`admin`/`user`/`streamer`), is_active, created_at |
| `AdminSession` (`preview_admin_sessions`) | id, user_id(FK, cascade), token_hash(SHA-256, unique), created_at, expires_at, revoked_at |
| `AdminPrincipal` | user_id, email, role, session_id, expires_at. 비밀번호·토큰·설정은 담지 않는다 |

세션 토큰 원문은 응답 쿠키로 한 번만 나가고 DB에는 해시만 남는다. 쿠키는
`HttpOnly`, `SameSite=lax`, `path=/`이며 `PREVIEW_COOKIE_SECURE`로 HTTPS에서만 `Secure`가
붙는다.

## 권한 경계

| 상황 | 결과 |
|---|---|
| 쿠키 없음 / 잘못된 쿠키 | 401 `authentication required` |
| 만료 세션 / 폐기(로그아웃) 세션 | 401 |
| 비활성 계정(세션 보유) | 401 |
| 아이디·비밀번호 오류 | 401 `invalid credentials` (계정 존재 여부 비노출) |
| 인증됐지만 role이 USER | 403 `admin role required` |
| 인증됐지만 role이 STREAMER | 403 |
| 유효한 ADMIN | 통과 |

인증 실패(401)와 인증된 비ADMIN(403)을 구분해 유지했다. STREAMER는 ADMIN의 대체 권한이
아니다. UI 리다이렉트는 편의일 뿐이고 실제 판정은 서버의 `require_preview_admin`이 한다.

## 검증 결과

모든 명령은 저장소 루트에서 실행했다. 원문 출력은
`docs/implementation/match-preview/evidence/`에 있다.

| # | 명령 | 종료 코드 | 결과 |
|---|---|---|---|
| 1 | `.venv/bin/python -m pytest tests/preview/test_admin_access.py -q` | 0 | 23 passed |
| 2 | `npm --prefix frontend run test:unit -- src/views/AdminLoginView.test.ts` | 0 | 9 passed |
| 3 | `npm --prefix frontend run type-check` | 0 | 오류 없음 |
| 4 | `npm --prefix frontend run build` | 0 | 37 modules, 산출물 생성 |
| 5 | `npm --prefix frontend run test:e2e -- e2e/preview-access.spec.ts` | 0 | 3 passed |
| 6 | `sloplint ... --scope app` | 0 | 0 FAIL, 0 REFLEX, 0 WARN |

**실패 선행 증거.** 인증을 만들기 전 같은 테스트를 돌려 23건이 모두 실패하는 것을 먼저
확인했다(`01-auth-tests-failing.txt`). 첫 시도는 `app.main` 임포트 오류였으므로 그 결과를
증거로 쓰지 않고, 앱을 임포트 가능한 최소 상태로 만든 뒤 다시 돌려 **동작 실패**를
확인했다. 예를 들어 익명 요청은 보호 경로가 없어 `404 Not Found`였고 기대는 401이었다.
환경·임포트 실패를 기대 실패로 대신하지 않았다.

**백엔드 테스트가 검사하는 동작.** 익명 거부, 오답 401, 미존재 계정 401, ADMIN 로그인
응답에 비밀값 미포함, ADMIN 보호 경로 200, USER 403, STREAMER 403, 유효 세션 + 비ADMIN
403, 비활성 401, 만료 세션 401, 로그아웃 후 401, 탈취 쿠키 재전송 401, 세션 토큰 평문
미저장, 위조 쿠키 401, 쿠키 속성(HttpOnly·SameSite), 필수 필드 422, 잘못된 JSON 422,
세션 없는 로그아웃 204, 세션 조회 401, DB 포함 health 확인.

**프론트 테스트가 검사하는 동작.** 라벨·autocomplete·비밀번호 필드 타입, 인증 실패 단일
문구와 비밀번호 초기화, 비ADMIN 문구, 네트워크 실패 문구, 서버 오류 문구, 요청 중 버튼
비활성, 로그인 성공 후 이동, 자격 증명이 URL이 아닌 POST 본문으로만 전송, 빈 제출 시
로컬 차단과 첫 빈 필드 포커스.

**E2E 검사.** `/admin/runs` 비인증 접근이 로그인으로 이동, 잘못된 비밀번호 오류 표시,
ADMIN 로그인 후 빈 실행 목록 표시, 로그아웃 후 보호 경로 재차단, 세션 쿠키 만료·삭제 시
로그인 복귀, 익명 API 401. 실제 백엔드와 실제 PostgreSQL을 쓰며 네트워크 모킹은 없다.
자격 증명은 `PREVIEW_E2E_ADMIN_PASSWORD` 환경변수로만 전달한다.

## 화면

Hallmark를 `--scope app`으로 적용했고 테마는 dealt 3개 중 Console(graphite)을 골랐다.
이유는 이 화면이 기록·감사 추적을 다루는 도구이고, 어두운 중성 바탕이 측정값과 사람이
쓴 문장을 같은 무게로 놓기 때문이다. 최종 CSS는 색·타이포 모두 `:root` 토큰을 거치고,
`transition: all`과 폭·높이 애니메이션이 없고, 모든 조작 요소에 `:focus-visible`이 있으며,
`prefers-reduced-motion` 대체가 있다. 표·폼·상태가 중심이고 히어로·통계 카드·가짜 수치는
없다.

네 가지 상태를 실제로 구현했다. 로딩은 표 모양 스켈레톤, 빈 상태는 "아직 실행 기록이
없습니다"와 오류가 아니라는 설명, 오류는 원인 문구와 다시 시도 버튼, 정상은 표다. 40rem
이하에서 여백과 바가 줄어든다.

스크린샷은 자격 증명 없이 실제 브라우저(Chromium)로 촬영했다. 모두 이번 세션에서
만든 것이다.

| 파일 | 내용 |
|---|---|
| `evidence/ui-01-login.png` | 로그인 화면 (1280x720) |
| `evidence/ui-02-runs-empty.png` | 로그인 후 빈 실행 목록 (1280x720) |
| `evidence/ui-03-login-error.png` | 잘못된 비밀번호 오류 상태 |
| `evidence/ui-04-login-mobile.png` | 로그인 화면 390px 너비 |
| `evidence/ui-05-runs-mobile.png` | 빈 실행 목록 390px 너비 |

빈 목록 화면의 실제 렌더링 텍스트는 다음과 같다(브라우저에서 읽은 값).

```
경기 프리뷰 관리자
admin@local.test
로그아웃
실행 목록
경기 프리뷰 생성 실행이 여기에 쌓입니다. 호출 기록과 조사 결과는 다음 단계에서 추가됩니다.
아직 실행 기록이 없습니다.
첫 실행을 만들면 이 목록에 나타납니다. 지금은 조회할 기록이 없다는 뜻이며, 오류가 아닙니다.
```

세션 이메일은 로그인한 관리자 본인 계정이고, 비밀번호나 토큰은 화면에 나오지 않는다.


## 파일

**계획 §3 MP-01 경로 (모두 새로 작성).**
`pyproject.toml`, `requirements.txt`, `.env.example`, `.gitignore`(제한 수정),
`app/main.py`, `app/db.py`, `app/core/config.py`, `app/auth/models.py`,
`app/auth/service.py`, `app/api/v1/auth.py`, `alembic.ini`, `alembic/env.py`,
`alembic/versions/0001_preview_access.py`, `frontend/package.json`,
`frontend/package-lock.json`, `frontend/index.html`, `frontend/tsconfig.json`,
`frontend/vite.config.ts`, `frontend/vitest.config.ts`, `frontend/playwright.config.ts`,
`frontend/src/main.ts`, `frontend/src/App.vue`, `frontend/src/router/index.ts`,
`frontend/src/lib/api/http.ts`, `frontend/src/views/AdminLoginView.vue`,
`scripts/preview_admin.py`, `tests/preview/conftest.py`, `tests/preview/test_admin_access.py`,
`frontend/src/views/AdminLoginView.test.ts`, `frontend/e2e/preview-access.spec.ts`.

**계획 밖에서 추가한 파일 (이유 포함).**

| 파일 | 이유 |
|---|---|
| `app/api/v1/preview_admin.py` | 빈 실행 목록을 돌려주는 보호 경로. 계획 §3에서 MP-02 소유로 적힌 경로지만, MP-01의 "로그인 → 보호된 빈 목록" 도달에 필요해 최소 라우트만 두었다. MP-02 담당자가 이 파일을 인계받아 확장한다. |
| `frontend/src/views/PreviewRunsView.vue` | 같은 이유로 만든 빈 목록 화면. 계획이 MP-02 경로(`features/match-preview/PreviewRunsView.vue`)로 예정한 화면이며, MP-01에서는 `views/`에 두고 인계한다. |
| `frontend/src/views/NotFoundView.vue` | 라우터 catch-all. 잘못된 주소가 빈 화면이 되지 않게 한다. |
| `frontend/src/styles/app.css` | 공통 토큰·컴포넌트 스타일. 계획의 "최소 공유 스타일" 항목이다. |
| `alembic/script.py.mako` | Alembic이 요구하는 리비전 템플릿. |
| `alembic/versions/` 디렉터리 | 마이그레이션 위치. |
| `app/__init__.py`, `app/api/__init__.py`, `app/api/v1/__init__.py`, `app/auth/__init__.py`, `app/core/__init__.py` | Python 패키지 초기화. 계획이 각 디렉터리 소유자에게 맡긴 항목이다. `alembic/`은 패키지가 아니라 스크립트 디렉터리이므로 초기화 파일을 두지 않았다. |

`.env.example`의 `preview_local_dev`는 위 Docker 컨테이너를 띄울 때 쓰는 일회용 로컬
DB 비밀번호다. 실제 관리자 로그인 자격 증명은 아니며, 어떤 환경의 실제 비밀값도
저장소에 넣지 않았다.

## 커밋

작업 전 저장소에는 847건의 미커밋 삭제·변경이 있었다. 그중 MP-01이 소유한 경로는
대부분 삭제 상태였고(` D`), 내가 그 경로에 새 파일을 만들면서 `M`으로 바뀌었다.
이번 커밋은 아래 경로만 명시적으로 골라 스테이징했다. 나머지 수백 건의 삭제는 그대로
남겨 두었다.

`.gitignore`는 커밋에서 제외했다. 이 파일은 작업 전부터 미커밋 수정 상태였고, 그 내용은
HEAD의 48줄 규칙을 지우고 3줄로 줄인 삭제였다. 내가 추가한 항목은 그 3줄 뒤에 붙어
작업 트리에는 반영되어 있지만, 이 파일을 스테이징하면 내 변경이 아닌 48줄 삭제가 함께
커밋된다. 그래서 파일은 작업 트리에 두고 커밋하지 않았다. 통합 소유자가 `.gitignore`를
별도로 정리할 때 함께 가져가면 된다.

| `docs/implementation/match-preview/MP-01-local-setup.md` | 재현 가능한 로컬 기동 절차. |
| `docs/implementation/match-preview/MP-01-report.md` | 이 보고서. |
| `docs/implementation/match-preview/evidence/*` | 명령 출력·스크린샷. |

**만들지 않은 것.** 회원가입, 회원 관리, 홈 자동화, 검색·모델 호출, 실행 추적 저장소,
지표, 배포, MP-02 이후 기능. `.venv/`, `frontend/node_modules/`, `frontend/dist`는
`.gitignore`에 넣었다.

## 인계

MP-02 담당자가 이어받을 지점은 다음과 같다.

- `app/auth/service.py`의 `require_preview_admin`이 모든 관리자 경로의 유일한 서버 경계다.
  새 관리자 라우터는 이 의존성을 붙이면 된다.
- `app/api/v1/preview_admin.py`의 `/api/v1/admin/preview/runs`가 자리표시 경로다. MP-02는
  이 응답을 실제 저장된 실행으로 바꾼다. 응답 봉투(`{"runs": [], "next_cursor": null}`)는
  그대로 유지하면 프론트 변경이 필요 없다.
- `tests/preview/conftest.py`의 `client`·`make_user`·`schema` 픽스처를 공통으로 쓴다.
  `make_user`는 구현 해시 함수가 아니라 argon2를 직접 쓰므로 인증 구현이 바뀌어도
  테스트가 함께 흔들리지 않는다.
- `frontend/src/lib/api/http.ts`의 `previewRequest`가 공통 전송 계층이다. 인증은 쿠키로만
  오가고 오류는 `ApiFailure`로 정규화된다.
- `frontend/src/views/PreviewRunsView.vue`는 계획상
  `frontend/src/features/match-preview/PreviewRunsView.vue`로 옮겨 확장한다.
- `alembic/versions/0001_preview_access.py`가 기준 리비전이다. MP-02는 여기에 이어
  `0002`를 만든다.

## 미해결·미검증

- **메일 발송, 비밀번호 재설정, 다중 관리자 관리**는 이 범위에 없다. 계정은
  `scripts/preview_admin.py`로만 만든다.
- **레이트 리밋·잠금 정책**은 두지 않았다. 로그인 시도 횟수 제한은 MP-01 요구가 아니었다.
- **세션 만료의 자동 정리**는 없다. 만료 행은 남고 판정에서 제외된다. 정리 작업은
  운영 단계에서 정한다.
- **운영 DB·클라우드 연결·배포는 미검증**이다. 이 작업은 격리된 로컬 PostgreSQL만
  확인했다.
- **`alembic.ini`에는 URL을 넣지 않았다.** `alembic/env.py`가 앱 설정에서 읽고 루프백
  검사를 적용한다. 이 때문에 `alembic` 명령은 `PREVIEW_DATABASE_URL` 환경변수를 필요로
  한다.
- **브라우저는 Chromium만 실제로 구동**했다. Safari·Firefox는 미검증이다.
- **개발자 비밀번호**는 저장소 밖 `/tmp/mp01_admin_pw.txt`(권한 600)에 있다. 저장소·로그·
  스크린샷에는 없다.

## 실행 중인 프로세스

| 대상 | 주소 | 소유 |
|---|---|---|
| 백엔드 (uvicorn) | http://127.0.0.1:8000 | `nohup .venv/bin/python -m uvicorn app.main:app` , 로그 `/tmp/mp01-backend.log` |
| 프론트 (vite) | http://127.0.0.1:5173 | `nohup npm run dev` (frontend), 로그 `/tmp/mp01-frontend.log` |
| PostgreSQL | 127.0.0.1:55432 | Docker 컨테이너 `match-preview-pg-mp01` |

세 프로세스 모두 이 작업자가 띄운 것이고 검사 가능한 상태로 남겨 둔다.

---

# 수정 패스 (검증 대기 피드백 반영)

앞의 내용은 처음 구현 시점의 기록이다. 아래는 검증 대기 상태에서 받은 지적을 고친
내용이다. 지적은 모두 재현해 확인한 뒤 고쳤고, 원래 증거 파일은 지우거나 덮어쓰지
않았다.

수정 시점 모델은 동일하다. DSH 세션 메타데이터의 `model/selection`은
provider `hive`, model `deepseek-ai/deepseek-v4.1-flash-1017`, reasoningEffort `max`이고
강도는 바꾸지 않았다.

## 수정 1. 테스트 준비 단계가 개발 DB를 지울 수 있었다

**문제.** `tests/preview/conftest.py`가 모든 테스트마다 `DROP SCHEMA public CASCADE`를
실행했다. 대상 검사는 호스트만 봤고, `PREVIEW_ALLOW_NONLOCAL_DB=1`이면 호스트 제한까지
열렸다. `PREVIEW_TEST_DATABASE_URL`을 개발 DB로 바꾸면 개발 데이터가 지워질 수 있었다.

**수정.** `tests/preview/_dbguard.py`를 추가해 연결 전에 두 조건을 함께 검사한다.

- 호스트가 루프백이어야 한다. 테스트 경로는 `PREVIEW_ALLOW_NONLOCAL_DB`를 읽지 않으므로
  애플리케이션용 우회 플래그로 열리지 않는다.
- DB 이름이 `test_*` 또는 `*_test`여야 한다. `postgres`, `template0/1`, `preview_mp01_dev`
  같은 이름은 거부한다.

검사는 순수 문자열 판정이고 연결을 열지 않는다. `_environment` 세션 픽스처가 어떤
픽스처보다 먼저 이 검사를 호출하므로, 거부되면 엔진 생성 전에 실패한다.

**확인한 동작.** 개발 DB를 테스트 대상으로 지정하고 실행하면 25건이 픽스처 오류로
즉시 실패하고, 개발 DB의 `preview_users` 1행과 `alembic_version=0001_preview_access`가
그대로 남았다(`evidence/12-dev-db-untouched.txt`). 가드 자체는 DB에 붙지 않는 11개
테스트로 검사한다(`evidence/10-test-db-guard.txt`).

## 수정 2. 컨테이너가 0.0.0.0에 게시되어 있었다

**문제.** `-p 55432:5432` 때문에 `docker ps`가 `0.0.0.0:55432`와 `[::]:55432`를 보였다.
보고서는 격리된 루프백이라고 적었지만 실제 게시 범위가 달랐다.

**수정.** 데이터 볼륨을 유지한 채 컨테이너만 다시 만들었다. 순서는 `pg_dump` 백업 →
`docker stop`/`rm`(볼륨 유지) → 같은 볼륨을 `-v`로 붙이고 `-p 127.0.0.1:55432:5432`로
재생성이다. 볼륨은 지우지 않았다.

**확인한 동작.** `PortBindings`는 `{"5432/tcp":[{"HostIp":"127.0.0.1","HostPort":"55432"}]}`,
`docker ps`는 `127.0.0.1:55432->5432/tcp`만 보여준다. 호스트 리스너도
`TCP 127.0.0.1:55432` 하나다. 재생성 후에도 `preview_mp01`, `preview_mp01_dev`,
`preview_mp01_test` 세 DB와 개발 관리자 계정이 남아 있었고 로그인·보호 경로·로그아웃이
그대로 동작했다(`evidence/13-loopback-binding.txt`).

## 수정 3. 로그인 422 응답이 제출 본문을 되돌려줬다

**문제.** 루트가 `POST /api/v1/auth/login`에 비밀번호 객체를 보냈고, FastAPI 기본
422 응답이 `detail[].input`에 제출값을 그대로 담아 반환했다. email이 빠지고 password만
있을 때도 본문 전체가 `input`으로 돌아왔다.

**수정.** `app/core/validation.py`의 `install_validation_error_scrubber`를 앱에 등록해
검증 오류 항목을 `type`·`loc`·`msg`만 남기도록 바꿨다. `input`·`ctx`·`url`은 버린다.
로그인뿐 아니라 앱 전체 검증 오류에 적용된다.

**확인한 동작.** 수정 전후를 같은 합성 표식으로 비교했다. 수정 후 다섯 경우(객체
password, email 누락, password 누락, 잘못된 JSON, 배열 본문) 모두 제출값을 되돌려주지
않았다(`evidence/14-login-422-before.txt`, `evidence/15-login-422-after.txt`). 행동
테스트 10건이 같은 경계를 검사한다(`evidence/11-login-redaction.txt`). 표식은 테스트
전용 문자열이며 실제 자격 증명이 아니다.

## 수정 4. E2E 이름이 실제 검사 범위와 달랐다

**문제.** `expired session` 케이스는 실제로는 쿠키만 지웠고, `non-admin accounts` 케이스는
익명 401만 확인했다. 이름이 서버 만료·역할 거부를 검증한 것처럼 읽혔다.

**수정.** 이름을 실제 검사 내용으로 바꾸고, 커버리지 범위를 주석과 Playwright
annotation에 명시했다. 익명 401이 USER/STREAMER 거부를 증명한다고 적지 않았다.

- `admin logs in through the form, sees the empty run list, and logs out`
- `a cleared session cookie sends the admin back to the login screen`
- `the app renders the server 403 for a non-admin role instead of an empty list`
  (응답은 스텁이며, MP-01에 계정 생성 UI가 없어 브라우저에서 실제 STREAMER 세션을 만들 수
  없다. 역할 거부 자체는 백엔드가 증명한다.)
- `anonymous requests to the protected endpoint are rejected by the server`

서버 판정은 백엔드 테스트가 맡는다. 이번에 `test_authenticated_streamer_with_valid_session_is_denied`
(유효 세션 + STREAMER → 403, 익명 401과 다른 경계)와
`test_session_expiry_is_enforced_from_the_clock_not_a_flag`를 추가했다.

## 수정 패스 검증

| 명령 | 종료 코드 | 결과 |
|---|---|---|
| `.venv/bin/python -m pytest tests/preview -q` | 0 | 46 passed |
| `.venv/bin/python -m pytest tests/preview/test_db_isolation.py -q` | 0 | 11 passed |
| `.venv/bin/python -m pytest tests/preview/test_auth_input_redaction.py -q` | 0 | 10 passed |
| `npm --prefix frontend run test:unit -- src/views/AdminLoginView.test.ts` | 0 | 9 passed |
| `npm --prefix frontend run type-check` | 0 | 오류 없음 |
| `npm --prefix frontend run build` | 0 | 산출물 생성 |
| `npm --prefix frontend run test:e2e -- e2e/preview-access.spec.ts` | 0 | 4 passed |

증거 파일은 `evidence/09`~`evidence/16`이다. 처음 구현의 `01`~`08`은 당시 상태 그대로
남겨 두었다. `08-local-db.txt`의 포트 표기는 수정 전 상태이므로 위 수정 2의 근거와 함께
읽어야 한다.

## 수정 패스에서 남은 것

- E2E의 403 케이스는 응답을 스텁한다. 브라우저에서 실제 STREAMER 세션을 만들려면 계정
  생성 경로가 필요한데, MP-01은 회원 관리 기능을 제공하지 않는다. 서버 판정은 백엔드
  테스트가 실제 세션으로 검사한다.
- 로그인 레이트 리밋, 세션 만료 행 정리, Safari·Firefox 검증은 여전히 범위 밖 또는
  미검증이다.
- 앱 설정의 `PREVIEW_ALLOW_NONLOCAL_DB`는 애플리케이션 기동 경로에 남아 있다. 테스트
  가드는 이 값을 무시하지만, 애플리케이션 쪽 우회 플래그 자체를 없애는 일은 이 작업의
  범위가 아니다.

## 수정 패스 중 발견해 바로잡은 것

작업 중 `tests/__init__.py`를 패키지 초기화용으로 새로 만들었다. 이 파일은 작업 전에
이미 삭제된 상태였고, 커밋 후 확인하니 미커밋 삭제 수가 809에서 808로 줄어 있었다.
의도하지 않게 남의 삭제 하나를 되살린 것이다. 파일을 다시 지워 809로 되돌렸고,
`tests.preview`는 네임스페이스 패키지로 임포트되므로 이 파일 없이 46개 테스트가
그대로 통과한다. 같은 이유로 `tests/preview/__init__.py`는 새 파일이지만, 이 경로는
MP-01이 소유한 테스트 디렉터리이고 가드 모듈을 명시적으로 임포트하기 위해 필요하다.
