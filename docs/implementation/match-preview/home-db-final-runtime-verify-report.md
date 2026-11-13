# HOME-DB-02 마지막 실행 준비 검증 결과 (기동 전, 후속 확인)

작성: DeepSeek 구현 워커(재배정). 배정서 `home-db-final-runtime-brief.md` 범위만 수행했다.
제품 파일·테스트·Plans.md 편집 0. 데이터 행 쓰기·실제 로그인·모델 호출·자료 수집·서버 재시작·pytest 0.
비밀값·접속 식별자(호스트·계정·DB명·비밀번호)는 어떤 출력·로그·이 문서에도 넣지 않았다.

이 dispatch의 변경은 **이 보고서 파일 하나**다. DB 권한 변경 0건(아래 3절: 부족 항목이 없어 부여 불필요).

## 1. 기동용 자격 파일의 단일 `DATABASE_URL`

| 확인 항목 | 결과 | 근거 |
|---|---|---|
| 파일 | `~/.config/match-preview/preview-dev.env` | `stat` |
| mode | **600** | `stat -f '%Lp'` |
| `DATABASE_URL` 항목 수 | **1건**(중복 0) | 파싱 후 키별 개수 집계 |
| 파일 값 출처 | Koyeb org secret `DATABASE_URL` (id `f71d940c`) | `koyeb secrets reveal DATABASE_URL` |
| 배포 바인딩 | `benchmark-v3` / `api` / 배포 `6b6fbe4f`(HEALTHY) env 키 `DATABASE_URL` → `secret: DATABASE_URL`, `scopes: region:tyo` | `koyeb deployments get 6b6fbe4f -o json` |
| 파일 값 == secret 값 | **동일(True)** | 0600 임시 파일로만 받아 메모리 비교, 즉시 삭제 |
| 값 형식 | `postgresql://` 스킴 1개, host·port(5432)·db·역할 네 요소 모두 존재(`urlsplit` 파싱) | `urlsplit` |
| 인용부호 | 작은따옴표로 감싼 1줄, 내부 공백·`$`·백틱 0 | 바이트 검사 |
| 런처가 읽는가 | `sh`로 source 시 스킴 `postgresql`·길이 114로 정상 로드 | 별도 셸에서 source 후 스킴·길이만 출력 |
| 기존 키 보존 | 10개 키 전부 유지: `PREVIEW_IDENTITY_DATABASE_URL`, `PREVIEW_DEV_DATABASE_URL`, `PREVIEW_FIXTURES_DATABASE_URL`, `PREVIEW_NAMES_DATABASE_URL`, `PREVIEW_STATS_DATABASE_URL`, `PREVIEW_ALLOW_NONLOCAL_DB`, `PREVIEW_ALLOW_NONLOCAL_IDENTITY_DB`, `JWT_SECRET_KEY`, `API_FOOTBALL_KEY`, `DATABASE_URL` | 키 이름 목록 |
| 옛 PREVIEW DSN 값 복제 | **없음**. 다섯 DSN 모두 `DATABASE_URL`과 값 동일성 False, 역할 False, **대상(host/port/db) True** | 값 비출력 비교 |
| `model-live.env` | 무변경(mtime `Nov 10 21:17`) | `stat` |

결론: 원래 연결 자격 증명은 **가용**하다. 파일에 원래 값 1건이 이미 있었고, 배포가 바인딩하는 같은 secret과 일치하므로
이번에 값을 새로 만들거나 복제할 필요가 없었다.

## 2. 단일 연결 해석 (값 비출력)

| 확인 항목 | 결과 |
|---|---|
| `configured_database_url()` | None 아님 |
| `resolved_database_url()` | 정상 반환, `postgresql+psycopg://` 정규화 |
| `PreviewSettings`의 여섯 property(`database_url`, `identity_database_url`, `resolved_identity_database_url`, `fixtures_database_url`, `names_database_url`, `stats_database_url`) | 여섯 값 모두 핵심 원문과 **raw 동일(True)**, 정규화 후 동일, 대상(host/port/db/역할) 동일 |
| `app.db.engine` (홈·일반 조회) | 대상 == 핵심값 |
| `app.preview.db.get_engine()` (preview_dev 저장) | 대상 == 핵심값 |
| 런처 | `sh -n` 통과, `${DATABASE_URL:?...}` 요구만 하고 값 생성·대체 없음, `PREVIEW_ALLOW_NONLOCAL_DB`·`JWT_SECRET_KEY` 요구 충족 |
| 옛 키 제거 | 런처가 옛 PREVIEW 5종 + `BENCHMARK_READ_DATABASE_URL`을 `unset` |

앱 엔진 읽기 전용 확인(모두 `BEGIN READ ONLY`):

- `app.db.SessionLocal` → 원래 계정으로 연결, `public`의 `league_sync_target`·`team_translation`·`league_translation`
  존재·SELECT 권한 True, `league_sync_target` `LIMIT 0` 읽기 성공.
- `app.preview.db.get_engine()` → `preview_dev` 기본 테이블 16개 조회, `preview_dev.preview_runs`에서 `count(*)`=28 조회 성공(행 내용 미조회).
- `public.home_preview_publication` / `home_preview_version` → **여전히 부재**(`to_regclass` NULL). 표 생성·자동 발행 없음.

## 3. 기존 `preview_dev` 권한 (이번 dispatch 재측정)

측정 방법: 원래 계정으로 접속해 `pg_class`·`has_table_privilege`·`has_schema_privilege`·`pg_default_acl` 메타데이터만 조회.

| 항목 | 직전 세션 측정(참고) | **이번 재측정** |
|---|---|---|
| `preview_dev` 기본 테이블 수 | 16 | **16** |
| SELECT/INSERT/UPDATE/DELETE 전부 true | 2 → 16 | **16** |
| 하나라도 부족한 테이블 | 14 → 0 | **0** (부족 대상 없음) |
| 스키마 USAGE / CREATE | True / True | **True / True** |
| `preview_dev` 시퀀스 | 0 | **0** (부여 대상 없음) |
| `pg_default_acl`(preview_dev) 행 | 0 | **0** (향후 자동 권한 없음) |

전체 권한 보유 16개: `checkpoint_blobs`, `checkpoint_migrations`, `checkpoint_writes`, `checkpoints`,
`preview_admin_sessions`, `preview_artifacts`, `preview_attempts`, `preview_module_executions`,
`preview_pipeline_runs`, `preview_results`, `preview_runs`, `preview_section_approvals`,
`preview_section_results`, `preview_source_snapshots`, `preview_write_audit`, `schema_migrations`.

소유권과 부여를 구분했다. 원래 계정 소유 2개(`preview_admin_sessions`, `schema_migrations`)는 ACL에 소유자로 표기되고,
나머지 14개는 **`preview_dev_app` 소유**이며 원래 계정은 **명시 GRANT의 수혜자**로 ACL에 이름이 있다(미부여 0건).
소유권 이전·새 역할·전역 권한·`ALTER DEFAULT PRIVILEGES` 없음.

이번 dispatch가 실행한 권한 변경은 **0건**이다. 부족한 테이블이 없어 brief 2항의 "부족한 테이블에만 부여" 조건이 발생하지 않았다.

## 4. `public` 무변경

| 항목 | 결과 |
|---|---|
| public 기본 테이블 수 | 28 |
| 원래 계정 SELECT/INSERT/UPDATE/DELETE 보유 수 | 28 / 28 / 28 / 28 |
| 이번 dispatch의 public 구조·데이터·권한 변경 | **0건**(DDL·GRANT·REVOKE 실행 없음) |

`public`의 기존 쓰기 권한은 이번 작업이 만든 것이 아니며 그대로 두었다(brief 2항 "public 권한은 바꾸지 않는다").

## 5. 실행한 명령 종류와 변경 범위

1. `koyeb deployments get 6b6fbe4f -o json` — 배포 env 메타데이터(키 이름·secret 바인딩 이름)만 확인.
2. `koyeb secrets reveal DATABASE_URL` — 출력을 0600 임시 파일로만 받아 파일 값과 **동일성 비교**, 즉시 삭제(표준출력 미노출).
3. `psycopg` 메타데이터 조회 — 모두 `BEGIN READ ONLY`, 행 내용 미조회.
4. 앱 엔진 경유 읽기 전용 조회 2회(`app.db`, `app.preview.db`), 모두 `BEGIN READ ONLY`.
5. `sh -n scripts/run_benchmark_dev.sh`, `sh` source 스킴 확인, `stat`·`lsof`·`ps` 상태 확인.

변경된 외부 상태: **없음**. 변경된 저장소 파일: 이 보고서 1개.

## 6. 현재 상태와 남은 일

- 백엔드: `uvicorn app.main:app` 프로세스 **없음**(마지막 확인 PID4177 종료 상태). 8000 포트는 다른 프로젝트 컨테이너
  `second-brain-api-1`이 IPv6 `*:8000`으로 점유 중이다. 바인딩 시험에서 `127.0.0.1:8000`은 **가능**, `0.0.0.0:8000`은
  `EADDRINUSE`였다. 런처는 `--host 127.0.0.1 --port 8000`으로 기동하므로 **충돌하지 않는다**(직전 PID4177 기동과 같은 조건).
- 프론트: 5173 `node` PID67430 유지.
- 남은 일은 **root의 서버 기동과 실제 GET 확인** 하나다. 자격 증명·권한·단일 연결 해석은 이번 확인 범위에서 갖춰졌다.
- 미확인: 기동 후 실제 `home/recommendations` 200 여부(공개 홈 publication 표 부재는 별도 사실로 남긴다), 실제 로그인·생성 경로.

## 7. 같은 워크트리의 동시 작업 (내 변경 아님)

확인 중 `tests/preview/test_bundle_review_fixes.py`(미추적)가 `01:59:03`에 갱신됐다. 이 워커는 그 파일을 읽거나 쓰지 않았고
pytest도 실행하지 않았다(실행 중인 pytest 프로세스 0 확인). 다른 세션의 동시 편집으로 보이며, 이번 배정 범위 밖이라 조사하지 않았다.
`app/`·`scripts/`·`tests/` 중 이 세션 시작(01:45) 이후 변경된 파일은 그 한 건뿐이다.
