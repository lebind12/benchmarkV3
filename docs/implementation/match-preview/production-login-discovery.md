# 운영 DB 연결·기존 로그인 구조 발견 기록 (2026-11-10 갱신)

작성: 2026-11-10 KST. 수행자: DeepSeek 구현 워커. 진행 문서(`Plans.md`)는 수정하지 않았다.
이전 판본의 "연결 정보가 없다"는 결론은 **틀렸다**. 연결 소스는 Koyeb 배포 설정이었다.

## 1. 정정: 연결 소스는 Koyeb 배포 환경이었다

이전 조사는 로컬 파일·프로세스 환경만 확인하고 "운영 접속 정보 없음"으로 결론냈다.
실제 연결 소스는 이미 인증된 Koyeb CLI에 있었다.

| 확인 | 명령 | 결과 |
|---|---|---|
| 앱 상태 | `koyeb apps list -o json` | `benchmark-v3` = `HEALTHY` |
| 서비스 | `koyeb services list -a benchmark-v3 -o json` | `api` = `HEALTHY`, id `5178062c-…-e96df3d672cb` |
| 활성 배포 | 위 JSON의 `active_deployment_id` | `6b6fbe4f-92eb-4cbe-9a09-68e1e9082287` |
| 배포 정의 | `koyeb deployments get <id> -o json` | `definition.env`에 14개 항목 |
| 비밀값 참조 | 같은 JSON의 `env[].secret` | `DATABASE_URL`, `JWT_SECRET_KEY`, `UPSTASH_*` 등은 secret 참조 |
| 비밀값 원문 | `koyeb secrets reveal DATABASE_URL -o json` | 0600 임시 파일로만 받아 메모리에서 파싱 |

배포 env 구성(키 이름만): `API_FOOTBALL_KEY`(secret), `APP_REVISION`(plain),
`CORS_ALLOW_ORIGINS`, `DATABASE_URL`(secret), `GOOGLE_APPLICATION_CREDENTIALS_JSON`(secret),
`GOOGLE_CLOUD_LOCATION`, `GOOGLE_CLOUD_PROJECT`, `JWT_SECRET_KEY`(secret→`BENCHMARK_AUTH_JWT_SECRET`),
`OPENAI_API_KEY`(secret), `UPSTASH_REDIS_KEY_PREFIX`, `UPSTASH_REDIS_REST_TOKEN`(secret),
`UPSTASH_REDIS_REST_URL`(secret), `VERTEX_AI_MODEL`, `WORKER_SCHEDULER_ENABLED`.

부수 확인: `koyeb deployments get deployment6b6f…`처럼 접두사를 붙인 인자는 거부된다.
CLI가 요구하는 것은 전체 UUID 또는 8자 short ID다.

`APP_REVISION` 값은 SHA가 아니라 `home-re…` 형태의 33자 문자열이었다. 배포가
`5f354e3` 리비전 그대로라고 단정하지 않는다.

### Supabase CLI (교차 확인)

`supabase projects list -o json` → `benchmark-v3`, `ACTIVE/HEALTHY`, ref `<project-ref>`
(값은 저장소에 적지 않는다; Koyeb `DATABASE_URL`의 사용자명 접미사와 동일하다).
Koyeb의 `DATABASE_URL`도 같은 프로젝트를 가리킨다(파싱한 host/db 기준).

## 2. 확인한 실제 DB 대상 (읽기 전용, 비밀값 미출력)

파싱해 메모리에서만 사용한 접속 정보의 **비밀 아닌 부분**:

| 항목 | 값 |
|---|---|
| 엔드포인트 유형 | Supabase pooler (session/pooler 호스트) |
| 호스트 | `aws-1-ap-northeast-1.pooler.supabase.com` |
| 포트 | `5432` |
| 데이터베이스 | `postgres` |
| 접속 롤 | `postgres.<project-ref>` (관리자 성격, `CREATEROLE`/`CREATEDB`, `SUPERUSER` 아님) |
| 서버 버전 | PostgreSQL 17.6 |

호스트가 pooler이므로 새로 만든 롤은 사용자명에 테넌트 접미사(`.<project-ref>`)가
필요하다. 이 사실은 `scripts/preview_dev_provision.py`가 반영한다.

## 3. 실제 스키마 (현재 값, 이력 아님)

`public` 스키마의 테이블 28개 중 계정·경기 관련 핵심은 다음과 같다.

`app_user` 컬럼(현재 DB에서 직접 조회):

| 컬럼 | 타입 | NULL | 기본값 |
|---|---|---|---|
| `id` | bigint identity ALWAYS | NO | - |
| `email` | text | NO | - |
| `password_hash` | text | NO | - |
| `role` | text | NO | `'USER'::text` |
| `nickname` | text | YES | - |
| `is_active` | boolean | NO | `true` |
| `email_verified` | boolean | NO | `false` |
| `last_login_at` | timestamptz | YES | - |
| `created_at` | timestamptz | NO | `now()` |
| `updated_at` | timestamptz | NO | `now()` |

제약: `app_user_role_check CHECK (role = ANY (ARRAY['USER','STREAMER','ADMIN']))`,
`app_user_pkey`, `app_user_email_key`(unique), 인덱스 `app_user_role_idx`.

행 수준 사실(**값 미조회, 집계만**): 총 8행, 활성 8, `ADMIN` 5, `USER` 3, `last_login_at`
보유 6. `password_hash`는 8건 모두 `pbkdf2_sha256$260000$…` 형식이며 salt 16바이트,
digest 32바이트로 정상 파싱된다. 이메일은 모두 소문자다.

경기 자료(참고 규모, `pg_stat_user_tables` 근사): `fixture` 약 3,256행, `team` 약 1,250행,
`league` 8행.

## 4. 과거 기록과 현재 사실의 차이

| 항목 | 과거 구현(`5f354e3^`) | 현재 DB·현재 앱 |
|---|---|---|
| 계정 테이블 | `app_user` | `app_user` (동일) |
| 해시 | `pbkdf2_sha256$260000$…` | 동일 형식 확인 |
| 역할 표기 | 대문자 `ADMIN`/`STREAMER` | CHECK도 대문자, 동일 |
| 세션 | JWT(HS256) + Upstash refresh | 이번 구현은 DB 세션(해시 토큰)으로 대체 |
| 로그인 시 기존 행 갱신 | `last_login_at` UPDATE | **갱신하지 않는다**(정책상 무변경) |

즉 이전 보고서의 "운영 계정으로는 로그인이 성립하지 않는다"는 판단은 **현재 기준으로
틀렸다**. 차이는 해시 형식이 아니라 이 앱이 그 형식을 검증하지 못했던 구현 공백이었고,
이번에 `app/auth/passwords.py`가 그 형식을 직접 검증한다.

## 5. 같은 DB, 다른 스키마 (권한으로 분리)

사용자 승인 범위대로 **기존 데이터 읽기**와 **개발 쓰기**를 접속 롤로 나눴다.

| 롤 | 용도 | 권한 | 금지 확인 |
|---|---|---|---|
| `preview_dev_identity_ro` | 기존 계정 읽기 | `public` USAGE + `public.app_user` SELECT만 | `app_user` UPDATE/INSERT/DELETE 거부, `public.fixture`·`management_run`·`auth.users` SELECT 거부, `preview_dev` 접근 거부 |
| `preview_dev_app` | 개발 세션 쓰기 | `preview_dev` USAGE/CREATE + 그 스키마 테이블 DML | `public.app_user` SELECT/UPDATE/INSERT 거부, `public` CREATE 거부, `public.fixture` SELECT 거부 |

권한은 실제로 거부되는지까지 시도해 확인했다(성공 주장만 하지 않는다).

`preview_dev`에 만든 객체(신규, 기존 영역 무변경):

- `preview_dev.preview_admin_sessions` — 세션 id/사용자 id/이메일/토큰 해시/만료/폐기 시각
- `preview_dev.preview_admin_sessions`의 인덱스 `ix_preview_admin_sessions_user_id`
- `preview_dev.schema_migrations` — 적용 기록 1행(`0001_preview_dev_admin_sessions`)

`user_id`는 기존 `app_user.id`(bigint)를 가리키되 **FK를 걸지 않았다**. 기존 테이블에
제약을 추가하지 않는다는 경계 때문이다.

수행하지 않은 것: `DROP SCHEMA`, `TRUNCATE`, 기존 스키마 재생성, `create_all`/`drop_all`
(기존 스키마 대상), 운영 서비스 재배포·재시작, Koyeb env 변경, 비밀값 로테이션,
구 앱 마이그레이션 실행. 기존 서비스 롤(`anon`/`authenticated`/`service_role` 등)과
`postgres` 롤 권한도 바꾸지 않았다.

## 6. 구현한 로그인 경로

1. 브라우저 `http://127.0.0.1:5173/admin/login` → Vite 프록시 → 로컬 백엔드 `:8000`
2. 백엔드가 **읽기 전용** 연결로 `public.app_user`를 이메일로 조회(대소문자 무시)
3. `pbkdf2_sha256` 검증 → 활성 여부 → `role == 'ADMIN'` 판정(아니면 403)
4. 세션 행은 `preview_dev.preview_admin_sessions`에만 insert(토큰은 SHA-256 해시만)
5. 쿠키는 HttpOnly `preview_admin_session`. 보호 경로는 매 요청마다 기존 계정의
   **현재** 역할·활성 상태를 다시 읽어 판정한다
6. 로그아웃은 개발 세션 `revoked_at`만 채우고 쿠키를 지운다

기존 행 무변경은 테스트로 고정했다: 로그인·보호 경로 접근 전후 `app_user` 행의
`password_hash/role/is_active/last_login_at/updated_at`가 동일하다.

## 7. 확인한 증거

| 검사 | 명령 | 결과 |
|---|---|---|
| 백엔드 테스트 | `.venv/bin/python -m pytest tests/preview -q` | `104 passed` |
| 프론트 타입 | `npm run type-check` | 오류 없음 |
| 프론트 단위 | `npm run test:unit` | 16 passed |
| 프론트 빌드 | `npm run build` | 성공 |
| 브라우저 렌더 | Chromium으로 `/admin/login` | 제목·이메일 입력·password 타입·콘솔 오류 0 |
| UI→API 경로 | 폼 제출(합성 오답) | 401 + 한국어 오류 문구, 쿠키 미설정 |
| 헬스 | `GET /api/v1/health` | `{"status":"ok","database":"ok","identity":"ok"}` |
| 기존 계정 읽기 | 앱의 `IdentityReader`로 실제 DB | `count_rows() = 8`, 미존재 조회는 `None` |

## 8. 아직 확인하지 않은 것 (성공으로 주장하지 않는다)

- **실제 계정으로 로그인 성공**: 사용자가 직접 입력해야 한다. 워커는 어떤 계정의
  비밀번호도 요청·표시·추측하지 않았다.
- 로그인 세션의 장기 동작, 만료 후 재로그인(서버 시계 기준 TTL만 구현·단위 검증).
- 운영 서비스가 이 코드를 쓰는지: 아니다. 운영은 기존 배포 그대로이고, 이 앱은
  로컬에서만 돈다.
- Upstash/JWT 기반 기존 세션과의 상호 호환: 이번 범위가 아니다(별도 세션 저장).

## 9. 남은 필수 확인 (사용자 몫)

1. `http://127.0.0.1:5173/admin/login`에서 본인 ADMIN 계정으로 로그인
2. `/admin/runs` 진입과 이메일 표시 확인, 로그아웃 후 재접근이 401/로그인 화면인지 확인
3. 이 결과로 MP-01 로그인 단계 승인 여부 판단

MP-02는 이 승인 전에 시작하지 않는다.
