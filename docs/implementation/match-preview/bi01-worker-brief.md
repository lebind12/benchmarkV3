# BI-01 — 원래 benchmark 앱·인증·DB 통합

사용자가 2026-11-12 새 통합 계획을 확인하고 병렬 실행을 지시했다. 실제 DeepSeek 구현 작업이다. 작업트리는 /Users/woolee/benchmark. 읽을 문서: AGENTS.md, Plans.md, docs/superpowers/specs/2026-11-12-benchmark-preview-integration.md, docs/superpowers/plans/2026-11-12-benchmark-preview-integration.md의 BI-01. 구현 시작 시 실제 모델과 범위를 ACK하라. DeepSeek flash-1017 Max는 root가 TUI에서 확인했다. 프로필/비밀 설정을 덤프하거나 모델을 바꾸지 않는다.

## 결과

원래 benchmark main/auth/management/home를 로컬에서 사용할 수 있게 복구·병합하고, 현재 app/preview 기능을 같은 앱의 router/service로 붙인다. 기존 계정/경기는 읽기 전용, preview 쓰기와 로컬 refresh 상태는 preview_dev만. 운영 API 프록시나 별도 preview 앱을 최종 결과로 삼지 않는다.

## 병렬 파일 소유권 — 이 목록이 일반 계획보다 우선

당신은 A다. B가 동시에 생성 모듈을 작업하고 root가 frontend를 직접 작업한다.

- A 소유: app/main.py, app/core/**, app/db.py, app/auth/**, 기존 원본 app/models/**·app/services/**·app/workers/**·app/schemas/**와 원본 API 복구(아래 B 예외 제외), app/preview/config.py·db.py·access.py 신규, app/preview/models.py·send_ledger.py·pipeline.py·sections.py·sources/**·localized_names.py의 설정/DB import 이관, app/api/v1/preview_metrics.py, requirements.txt/pyproject.toml(있을 때), scripts/run_benchmark_dev.sh, scripts/run_preview_dev.sh, tests/conftest.py와 tests/preview/conftest.py(있을 때)의 연결 이관, tests/unit/test_benchmark_preview_runtime.py·test_benchmark_preview_auth.py, 관련 기존 인증 테스트의 직접 영향 부분.
- **B 전용, 수정 금지:** app/api/v1/preview_admin.py, app/services/match_preview.py, app/preview/retry.py·provider.py·bundle_pipeline.py·store.py·section_preview.py·discovery.py·contracts.py·version_manifest.py·modules/bundle_sections.py, tests/preview/test_retry_budget.py·test_provider.py·test_bundle_sections.py·test_bundle_pipeline.py·test_bundle_integration.py, scripts/preview_bundle_live_once.py.
- frontend/**·out/**·Plans.md는 root 소유. 코드 일반개선, 새 migration/권한 grant, 배포, 기존 서버 재시작은 하지 않는다. 실행 파일/DB가 준비되면 root가 전환한다.
- A가 복구하는 원본 app/services 디렉터리에 B 신규 match_preview.py가 생기면 보존한다. 디렉터리 덮어쓰기/reset 금지. 중단된 AC-01은 Held 상태이고 assignment는 abandoned로 fence됐다. 그 변경을 버리지 않는다.

## 먼저 제공할 계약

가장 먼저 현재 preview 전용 설정과 DB 구현을 전용 파일로 보존해 B가 import할 경로를 만든 뒤 root에 알려라. 이후 원본 app/core/config.py·app/db.py를 복구한다.

- app.preview.config: get_settings()와 PreviewSettings. 기존 Settings 명칭을 쓰는 이관 caller에는 호환 alias를 둘 수 있다. PREVIEW_* 환경 키와 저장 schema 보존.
- app.preview.db: get_db(), get_session_factory(), get_engine(), Base, SCHEMA('preview_dev'). 현재 쓰기 연결 역할 유지.
- app.preview.access: PreviewPrincipal(user_id, email, role), require_preview_admin(). 원본 JWT current_user에서 ADMIN만 허용. 가짜 session_id/expiry를 채우지 말 것. B는 preview_admin.py의 이 import를 직접 바꾼다.
- B 소유 파일의 app.db/app.core.config import는 B가 바꾼다. A는 import 변경 목록을 root에게 전달하고 B 파일을 건드리지 않는다.

## 구현 경계

원본 조사 기준은 c4d7d32다. 작업트리 전체를 원본으로 되돌리지 말고 필요한 원본 파일을 열람·비교해 복구한다. 새 프리뷰 모델의 Base와 원본 모델 Base를 합치지 않는다. root frontend는 원래 JWT 로그인·관리 API 계약을 사용한다.

원본 로그인은 public.app_user.last_login_at 갱신과 Upstash refresh 쓰기가 있으므로 로컬 프로필에서 둘 다 방지한다. 기존 PBKDF2/원본 JWT·refresh-cookie·/me 계약은 유지하고 개발 세션만 기존 preview_dev.preview_admin_sessions에 기록하는 작은 adapter를 사용한다. 로컬 서명키/쿠키·Origin은 운영과 분리하되 Origin 검사를 끄지 않는다. ADMIN 외 preview 생성403, 일반 기존 관리 권한은 보존한다. 계정/role/비밀번호/기존 테이블/운영세션 쓰기 금지. 기존 narrow DSN에 필요한 읽기 권한이 없으면 정확한 대상·권한만 보고하고 관리자 DSN/새 grant로 우회하지 않는다.

새 런처는 0600 파일의 비밀값을 프로세스에만 전달하며 출력하지 않는다. 원래 benchmark 앱을 uvicorn app.main:app으로 띄울 준비, scheduler off·자동 migration off. 자동 시작하거나8000/5173/5174를 변경하지 않는다. root가 최종 전환한다. 운영배포 설정은 바꾸지 않는다.

## 수용 기준과 검증

1. 같은 FastAPI 앱에 /health, 원래 management/home 추천, preview 라우터가 있고 auth 중복 없음.
2. public 모델과 preview 모델이 각각 올바른 bind/schema를 사용한다.
3. 기존 로그인 응답 형태·refresh·/me, ADMIN/비ADMIN 경계, 기존 계정과 원격 세션 쓰기0을 합성 검사로 증명.
4. 설정·기동 명령과 원래 관리자 읽기에 필요한 권한을 정리. 비밀값은 보고 금지.

계획의 두 직접 검사 파일과 필요한 기존 연결 검사만 실행. 운영 DB에서 pytest/초기화/create_all 금지. no model calls/no external collection/no production writes/no commits. 실제 기존 데이터는 읽기만 가능. 예외 시험은 합성 입력/루프백 테스트DB로 한다. B 변경 중 import 일시 오류는 당신 파일로 우회하지 말고 계약 checkpoint 뒤 재확인한다. 전체 suite/새 일반 테스트 도구 금지.

완료 보고: 실제 모델, 변경 파일/복구 목록, 정확한 명령과 결과, 연결 계약, 남은 읽기 권한/설정, EDITING STOPPED. 공통 Plans.md를 수정하지 말고 root에 보고한다. 하위 워커를 만들지 않는다.
