# HOME-DB-02 마지막 실행 준비 결과 (기동 전 단계)

작성: DeepSeek 구현 워커. 배정서 `home-db-final-runtime-brief.md` 범위만 수행했다.
제품 코드·테스트·Plans.md·public 구조/데이터·역할/소유권은 변경하지 않았다.
비밀값·접속 식별자는 어떤 출력·로그·이 보고서에도 넣지 않았다.

## 1. 기동용 자격 파일의 단일 `DATABASE_URL`

| 확인 항목 | 결과 |
|---|---|
| 파일 | `~/.config/match-preview/preview-dev.env` |
| 기존 `DATABASE_URL` 항목 | **없음**(0건) → 이번에 1건 추가 |
| 현재 `DATABASE_URL` 항목 수 | **정확히 1건** |
| 값 출처 | 기존 Koyeb `benchmark-v3` / 서비스 `api` / 배포 `6b6fbe4f`의 `DATABASE_URL` secret(env 키 `DATABASE_URL` → secret `DATABASE_URL`) |
| 파일 값 == secret 값 | **동일(True)** |
| 파일 mode | **600** (작성 후 재확인) |
| 기존 키 보존 | `PREVIEW_IDENTITY_DATABASE_URL`, `PREVIEW_DEV_DATABASE_URL`, `PREVIEW_FIXTURES_DATABASE_URL`, `PREVIEW_NAMES_DATABASE_URL`, `PREVIEW_STATS_DATABASE_URL`, `PREVIEW_ALLOW_NONLOCAL_DB`, `PREVIEW_ALLOW_NONLOCAL_IDENTITY_DB`, `JWT_SECRET_KEY` **전부 유지** |
| 옛 PREVIEW DSN에 값 복제 | **없음** (다른 키에 값을 넣지 않았다) |
| `model-live.env` | **무변경**(mtime 유지) |

## 2. 단일 연결 동일성 (값 비출력)

| 비교 | 결과 |
|---|---|
| `DATABASE_URL` 대상 vs `PREVIEW_DEV_DATABASE_URL` 대상 | host **동일**, port **동일**, database **동일** |
| 두 DSN의 역할(사용자명) | **다름**(원래 계정 vs 개발 저장 역할) |
| 앱 설정 해석 | `configured_database_url()` → None 아님, 자리표시자 아님 |
| 정규화 | `postgresql+psycopg://`로 정규화됨(`normalize_database_url`) |
| 런처 dry-run | 필수 변수 3종(`DATABASE_URL`/`PREVIEW_ALLOW_NONLOCAL_DB`/`JWT_SECRET_KEY`) 충족, 옛 DSN unset 동작 확인, `sh -n` 문법 통과 |
| 런처가 값을 덮어쓰는가 | **아니오**(`${DATABASE_URL:?...}`로 원문 그대로 사용) |

앱 엔진 실제 확인(쓰기 없음, `BEGIN READ ONLY`):

- `app.db.make_engine()` → 연결 성공, `current_user`·`current_database()` 해석, `public.fixture` SELECT 가능.
- `app.preview.db` 엔진 → `preview_dev.preview_runs`, `preview_dev.preview_write_audit` SELECT 가능.
- 두 엔진의 접속 대상(host/port/db) **동일**.

## 3. 기존 `preview_dev` 저장 권한 (메타데이터만)

대상 스키마: `preview_dev` (실행 전 재확인). 부여 대상: 원래 계정(`DATABASE_URL`의 사용자).
부여 실행 연결: 기존 소유자 연결(`PREVIEW_DEV_DATABASE_URL`, 역할 `preview_dev_app`).
개발 역할/superuser: `rolsuper=false`, `rolcreaterole=false`. 새 역할 생성 **없음**.

### 권한 전후

| 항목 | 변경 전 | 변경 후 |
|---|---|---|
| `preview_dev` 테이블 수 | 16 | 16 |
| SELECT/INSERT/UPDATE/DELETE **전부** 보유 | **2** | **16** |
| 하나라도 부족한 테이블 | **14** | **0** |
| `preview_dev` 스키마 USAGE / CREATE | True / True | True / True (변경 없음) |
| `preview_dev` 시퀀스 수 | **0** | **0** (적용 대상 없음) |

부족했던 14개 테이블(전부 `preview_dev_app` 소유, 원래 계정은 SELECT만 보유):
`checkpoint_blobs`, `checkpoint_migrations`, `checkpoint_writes`, `checkpoints`,
`preview_artifacts`, `preview_attempts`, `preview_module_executions`,
`preview_pipeline_runs`, `preview_results`, `preview_runs`, `preview_section_approvals`,
`preview_section_results`, `preview_source_snapshots`, `preview_write_audit`.

부여하지 않은 2개: `schema_migrations`, `preview_admin_sessions` — 원래 계정이 **이미 소유자**라
권한 전에 이미 4종 전부 보유(중복 부여 불필요).

### 실행한 변경

- `GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE preview_dev.<14개> TO <원래 계정>` **1회**.
- 실행 전 대상 스키마·역할 존재·canlogin 재확인, 실행 후 같은 메타데이터로 차이 보고.
- `ALTER DEFAULT PRIVILEGES`/전역 GRANT/소유권 이전/`REVOKE` **없음**.
- `preview_dev` 기본 권한(`pg_default_acl`) 행 **0** → 향후 테이블 자동 권한 없음.
- 소유자는 여전히 `preview_dev_app`이 14개 테이블 소유(소유권 이전 없음).

## 4. `public` 권한 무변경

| 항목 | 변경 전 | 변경 후 |
|---|---|---|
| public 테이블 SELECT/INSERT/UPDATE/DELETE/전체 | 28 / 28 / 28 / 28 / 28 | **28 / 28 / 28 / 28 / 28** |
| public 테이블 쓰기(INSERT/UPDATE/DELETE) | 있다 | 있다 (이번 작업이 만든 것 아님) |

요청하신 대로 public 권한은 **한 건도 바꾸지 않았다**(부여 SQL이 `preview_dev` 테이블만 대상).

참고 사실(변경 없음): 원래 계정은 `public.league_sync_target`, `team_translation`,
`league_translation` SELECT를 이미 보유한다. `public.home_preview_publication`/`version`은
여전히 **대상 DB에 존재하지 않는다**(`to_regclass` NULL). 표 생성·자동 발행 **없음**.

## 5. 하지 않은 것

데이터 행 쓰기, 실제 로그인, 모델 호출, 자료 수집, **서버 재시작**, pytest/전체 suite/벤치마크,
마이그레이션, 새 역할·역할 멤버십·소유권 이전, public 구조/데이터 변경, 비밀값 출력.
8000 리스너는 기동 전과 동일한 PID66697 그대로다(재시작은 root 담당).

## 6. 실행 명령 종류와 변경 범위 요약

1. `koyeb secrets reveal DATABASE_URL` (표준출력 비노출, 임시 파일 즉시 삭제)
2. `psycopg` 메타데이터 조회 4회 (모두 `BEGIN READ ONLY`)
3. `GRANT ... ON TABLE preview_dev.<14개> TO <원래 계정>` 1회(커밋)
4. 자격 파일 1건 추가(백업 파일 삭제, mode 600 유지)
5. 앱 엔진 읽기 전용 연결 확인 1회

변경된 저장소 제품 파일: **없음**. 변경된 외부 상태: 자격 파일 1개, DB 권한 14개 테이블.
