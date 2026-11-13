# BI-01 운영 계정 읽기 연결 보완

실제 DeepSeek flash-1017 Max 구현 세션만 사용한다. 하위워커/모델 변경 금지. 이 작업은 기존 로컬 benchmark 통합의 관측된 연결 누락만 고친다.

사용자 확정: **현재 운영 DB의 기존 계정·비밀번호 해시·권한 그대로** 로그인한다. 별도 계정 DB·계정 복제·테스트 계정 생성 금지. 같은 DB의 preview_dev에는 개발 로그인 세션/새 프리뷰만 쓴다. 로컬 JWT 서명키는 이미 별도 준비돼 있으므로 건드리지 않는다.

관측된 누락:

- scripts/run_benchmark_dev.sh는 DATABASE_URL을 BENCHMARK_READ_DATABASE_URL 또는 PREVIEW_FIXTURES_DATABASE_URL로 지정한다.
- app/api/v1/auth.py의 login/refresh DbSession과 app/core/sessions.py의 current_user가 app.db.get_db_session을 사용한다.
- PREVIEW_IDENTITY_DATABASE_URL이 export돼 있어도 위 세 caller가 운영 계정용 identity_ro로 연결되지는 않는다. A의 기존 "identity_ro app_user SELECT 충분" 증거는 역할 권한 증거일 뿐 현재 caller 연결 증거가 아니다.

소유 파일: app/db.py, app/api/v1/auth.py, app/core/sessions.py. 기존 app/auth/identity.py와 app/preview/config.py 계약은 우선 읽어 재사용하며 정말 호출 경계 변경이 필요하면 먼저 이유를 보고한다. 테스트는 기존 tests/unit/test_benchmark_preview_auth.py 및 test_benchmark_preview_runtime.py의 직접 영향 사례만. 다른 제품 파일·frontend·B 파일·런처·비밀 파일·Plans.md 변경 금지.

요구사항:

1. 로컬 프로필의 계정 조회(login/refresh/current_user → /me·ADMIN 판정)에 기존 PREVIEW_IDENTITY_DATABASE_URL의 좁은 읽기 전용 연결을 실제 주입한다. 경기/홈/일반 조회 DATABASE_URL은 그대로 둔다. 설정 누락/읽기 실패를 로그인 성공이나 다른 역할 우회로 처리하지 않는다.
2. 원래 운영 프로필은 기존 get_db_session/로그인/세션 동작을 유지한다. 로컬에서 기존 계정 행·비밀번호·활성·역할·last_login_at 갱신0, 원격 Upstash 쓰기0, signup403, Origin 검사 유지.
3. 로컬 서명키와 개발 세션 저장은 기존 구현 그대로. 계정 원장을 preview_dev로 복제하지 않는다. 새 grant/migration/관리자 DSN 사용 금지.
4. 개발 계정 연결과 기존 경기 연결의 DB 대상이 같은지 기존 설정을 값 출력 없이 비교한다. 실DB 검증이 필요하면 기존 역할로 public.app_user의 존재/조회 가능 여부만 읽고 계정 식별자·해시·내용은 출력하지 않는다. 사용자 비밀번호로 로그인하지 않는다.

검증 범위·종료:

- 기존 두 직접 검사 파일만 필요 부분 갱신 후 1회. 핵심: 실제 local auth dependency가 identity 연결을 선택하며 fixture 연결은 계정 조회에 사용되지 않는 대표 사례, 기존 auth 응답/권한/무변경 보존. 동일 DB fixture에서 순차 실행하고 기존 loopback *_test 안전가드 유지. 운영 DB에 pytest/DDL/fixture 초기화 절대 금지.
- 모델/외부 HTTP/수집0, 서버 변경0, 전체 preview suite0, 새로운 검증 스크립트0, 커밋0. 기존 이름/이미지와 생성·재시도는 범위 밖.
- 독립 검토 R(task_9966b18acd43)이 기존 통합 경계를 검토 중이다. 바뀐 3파일과 해시·이전/이후 caller를 정확히 인계해 원 지적 범위 확인에 쓰게 한다. 검토 보고서는 수정하지 않는다.
- 완료 보고 1회 + EDITING STOPPED. 완료 등록이 거부되면 status 1회만 남기고 메일/완료 재시도 루프를 만들지 않는다.
