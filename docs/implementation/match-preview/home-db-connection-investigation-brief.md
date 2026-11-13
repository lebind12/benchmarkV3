# HOME-DB-01 서버 DB 연결 읽기 전용 조사

사용자 요청: 홈 추천 503의 원인이 서버 DB 연결/권한인지, 실제로 어떻게 연결되는지 확인한다. 설정·권한 수정은 아직 요청하지 않았다. 추천 경기와 독자 프리뷰는 비로그인 공개이며 생성·재생성만 ADMIN이다.

역할: DeepSeek 조사 워커. 실제 `deepseek-ai/deepseek-v4.1-flash-1017`과 기존 Max 설정을 확인하고 시작한다. 모델 교체·하위 워커 없음. 루트는 소스 요청 경로를 별도로 조사한다.

## 범위

- 제품/테스트/설정/비밀파일/Plans.md 편집 없음. 보고서 `docs/implementation/match-preview/home-db-connection-investigation.md` 하나만 작성 가능.
- 실제 프로세스: 마지막 확인 로컬8000 PID66697, `scripts/run_benchmark_dev.sh`로 시작한 `app.main:app`, Orca terminal `term_c31916c2-591f-43b0-bcd1-801b30806912`. PID/cwd/명령을 확인하고 프로세스를 재시작하거나 attach/debug하지 않는다. 기존 서버 환경을 읽을 수 있다면 메모리 안에서 필요한 값만 비교하고 원문을 절대 출력하지 않는다. 정확한 환경을 확인할 수 없으면 소스/설정에서 재구성한 값과 런타임 관측을 명확히 구분한다.
- 런처는 외부0600 preview-dev.env/model-live.env를 로드하고 DATABASE_URL을 BENCHMARK_READ_DATABASE_URL 또는 PREVIEW_FIXTURES_DATABASE_URL로 설정한다. app.db는 홈/일반 조회, get_auth_db_session은 identity 연결, app.preview.db는 preview_dev 저장 연결이다.
- 기존 보고서 `bi01-integration-report.md` §6에서 fixture 역할의 team_translation/league_translation/league_sync_target SELECT 부족과 public.home_preview_publication/version 부재가 보고됐으나 그대로 재인용하지 말고 현재 대상의 제한된 SELECT로 확인한다.

## 필요한 근거만 수집

최신 우선 질문(16:19): 사용자는 연결/권한 수정 전에 **프리뷰 생성 결과의 현재 저장 권한**부터 확인하라고 했다. 현재 서버 PREVIEW_DATABASE_URL과 PREVIEW_DEV_DATABASE_URL 동일성, app.preview.db/store/send_ledger의 해당 연결 사용, preview_dev 실행·섹션결과·원문아티팩트·전송장부·구성본 저장에 필요한 SELECT/INSERT/UPDATE 및 해당 시퀀스 USAGE를 권한 메타데이터로 확인한다. sequence를 사용하지 않는 UUID 테이블은 해당 없음으로 구분한다. public 기존 영역 쓰기 권한 부재도 boolean으로 확인한다. 실제 쓰기/쓰기 탐침/모델 호출은 하지 않는다. 이 확인을 같은 보고서에 포함하고, 수정 작업은 별도 대기 중이다.

1. 실제/설정상 DATABASE_URL이 어떤 키에서 선택됐는지 확인한다. BENCHMARK_READ_DATABASE_URL 존재 여부, fixture 연결과 동일 여부, 원래 repo .env의 기본 DB 대상과 동일 여부를 값 없이 보고한다. 전체 DSN·호스트·프로젝트 식별자·비밀번호·계정행·토큰을 출력/보고서에 넣지 않는다. URL 마스킹보다 동일/상이 boolean을 우선한다.
2. 일반조회/fixture/identity/names/stats/preview_dev 연결이 같은 host·port·database 대상인지, 어떤 역할 범위를 가지는지 표로 보고한다. 역할은 이미 코드에 공개된 논리 이름으로 설명해도 충분하다. 같은 DB와 다른 역할을 구별한다.
3. 기존 좁은 역할로 연결해서 메타데이터 SELECT만으로 필요한 표의 존재와 SELECT 권한 확인: public.fixture/team/league/team_translation/league_translation/league_sync_target/home_preview_publication/home_preview_version. identity는 app_user SELECT 및 쓰기 권한 boolean만, 개발 저장은 preview_dev.preview_runs 존재/읽기만 확인한다. 표가 없다는 것과 권한 때문에 조회가 거부되는 것을 구분하고 다른 스키마에 같은 두 home 표가 있는지도 메타데이터만 확인한다. 운영 데이터 행 내용은 불필요하다.
4. 설정을 같은 방식으로 읽는 기존 홈 recommendations 함수의 현재 첫 실패가 무엇인지, 가능하면 명시적 READ ONLY 트랜잭션의 기존 함수 1회로 확인한다. SQLSTATE와 실패 표 이름만 보고하고 SQL 파라미터/URL 포함 traceback은 출력하지 않는다. 새 검증 파일/범용 점검 도구는 만들지 않는다. SQL을 직접 쓰는 경우에도 SELECT 및 읽기 전용 트랜잭션 제어만 허용한다.
5. 결론은 연결 대상 오류 / 읽기 역할 선택 오류 또는 권한 부족 / 기존 홈 저장 계약의 표 부재를 구별한다. 'DB가 망가짐' 또는 '권한만 바꾸면 전부 해결'로 단정하지 않는다. 수정 후보를 가장 작은 범위로 제안하되 실행하지 않는다.

## 금지 및 종료

DB DML/DDL/GRANT/REVOKE/마이그레이션/쓰기 탐침/관리자 역할을 이용한 앱 우회 0. provision/status 스크립트는 쓰기 탐침을 포함할 수 있으므로 실행하지 않는다. pytest/vitest/build/실모델/외부 스크래핑/사용자 로그인/서버변경/commit/stage 0. 계정 정보와 비밀값 출력 0.

자료가 충분하면 한 번 보고하고 종료한다. 추가 문제 탐색·반복 검사·연결 유지 없음. worker_done에 정확한 근거, 새 사실, 미확인 한계, 유일 보고서 경로를 적는다. 옛 Dispatch 메일을 구현 지시로 실행하지 않는다. lifecycle 거부면 status 한 번만 보내고 종료한다.
