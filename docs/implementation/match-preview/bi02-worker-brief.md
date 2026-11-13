# BI-02 — 경기별 생성 서비스·모듈별 재시도·저장

사용자가 2026-11-12 통합 계획을 확인하고 병렬 실행을 지시했다. 실제 DeepSeek 구현 작업이다. /Users/woolee/benchmark에서 AGENTS.md, Plans.md, 새 spec/plan(2026-11-12-benchmark-preview-integration)을 읽고 BI-02를 수행한다. 실제 DeepSeek flash-1017 Max는 root가 TUI 확인하며 시작 ACK에 기록한다. 프로필/비밀값을 덤프하거나 모델을 바꾸지 않는다.

## 병렬 경계

당신은 B다. A가 원래 benchmark 앱/인증/DB를 복구하고 root가 frontend를 직접 작성한다. 논리 구현은 병렬로 시작하고 import/앱 연결 검사는 A의 계약 준비 후 한다.

- **B 소유:** app/api/v1/preview_admin.py, app/services/match_preview.py 신규, app/preview/retry.py·provider.py·bundle_pipeline.py·store.py·section_preview.py·discovery.py·contracts.py·version_manifest.py·modules/bundle_sections.py, tests/preview/test_retry_budget.py·test_provider.py·test_bundle_sections.py·test_bundle_pipeline.py·test_bundle_integration.py, scripts/preview_bundle_live_once.py(호출자가 제품 정책을 다시 제한하지 않도록 필요한 부분만; 실행 금지).
- A 소유 수정 금지: main/core/db/auth/원본서비스·모델·worker·API, preview/config.py·db.py·access.py·models.py·send_ledger.py·pipeline.py·sections.py·sources/**·localized_names.py, requirements/런처/test conftest. send_ledger 변경이 실제 필요하면 root에 정확한 변경 요구를 보고하고 소유권 인계 전 편집하지 않는다.
- frontend/**, out/**, Plans.md는 root 소유. 프롬프트 내용 일반 개선·새 설계·배포/서버전환 없음. 범위 밖 파일이 필요하면 root로 한 번 요청한다.
- 중단된 AC-01의 부분 변경이 남아 있다. old 보고를 완료 증거로 쓰지 말고 diff를 보존하며 실제로 이어받는다. 전체 git checkout/reset·stage/commit 금지.

## A가 제공할 고정 경계

A는 먼저 app.preview.config.get_settings()/PreviewSettings, app.preview.db.get_db()/get_session_factory()/Base/SCHEMA, app.preview.access.PreviewPrincipal(user_id,email,role)/require_preview_admin()를 만든다. B는 자기 소유 파일의 app.db/app.core.config 및 preview_admin의 auth import를 직접 이 경로로 바꾼다. 가짜 session id나 기존 principal 조립은 하지 않는다. A가 준비했다고 root에 알리면 통합 검사한다.

## 결과 및 API 계약

- app/services/match_preview.py의 generate_match_preview(*, fixture_id:int, actor_id:int|None, trigger:'admin'|'collection') → 기존 BundlePipelineOutcome. 외부 fixture번호를 readonly reader로 해석하고 기존 LangGraph run_bundle_pipeline을 한 번 호출. 엔진 재작성·다른 서버 HTTP프록시 없음. 현재 구현 대상은 관리자 경로이며 collection 자동활성화는 후속이다. 시스템 호출 때문에 가짜 ADMIN id를 만들지 않는다.
- GET /api/v1/admin/preview/fixtures/{fixture_id}: 기존 FixtureCandidate 단건 객체. 번호 없음404·읽기불가503·모델0회.
- POST /api/v1/admin/preview/bundle-runs: {fixture_id,mode:'live'}만으로 저장된 경기 동일성 해석. 이전 전체식별자 입력이 충돌하면422, 현재 BundlePreviewRunResponse/run_id 유지.
- GET /runs/{id}/preview, section-results, information-bundle, run detail은 DB만 조회.
- section-runs/composition도 원래 benchmark 인증과 동일 preview 저장 연결 사용. 같은 경기의 선택 버전으로만 조합, 최종 AI에 새 검색/출처 검증 없음.

## 핵심 제한 및 결과 의미

1경기 1생성 실행의 **각 논리 AI 모듈 최초 포함 최대3회**다. 다른 경기/이전시험집합 prior 차감·독립전체8회 한도를 제거한다. 여섯 모듈*3=18은 집계 설명일 뿐 공용 여유 배분 정책 아님. 정상 성공 모듈은 재전송하지 않는다. 같은 run 복구는 장부를 읽고 기존 sends를 유지하며 retry를 새 run id로 초기화하지 않는다. 과거장부·trial label 기록은 보존하되 현재 정책으로 사용하지 않는다.

429/503/timeout, finishReason MAX_TOKENS, JSON parse failure는 같은 모듈3회 안에서 처리한다. 인증/설정 오류 또는 글의 길이·내용 부족·선택 자료 없음은 자동 반복하지 않는다. SDK/그래프/모듈 각각에 중복 retry를 달지 않는다. 모델동시2·요청당300초·출력40000·배당0모델 유지. 전역1800초가 모듈3회를 잘라내는 경로는 새 실행의 독립 중단 기준으로 쓰지 않는다. HTTP홉은 model attempts와 분리.

부분 본문/오류원문/장부를 저장한다. 기존 quality/complete는 진단으로 남길 수 있으나 본문 숨김/전체콘텐츠 실패/자동재생성 기준으로 쓰지 않는다. 기술 실행/저장오류는 정확히 보고한다. 성공평가는 사용자. 기존 기사본문→검색AI요약→DB, 강조prompt, 워크플로우 승인/버전, 구성본·재생성 기능은 유지. 새 품질 평가 엔진이나 기사검증을 만들지 않는다.

## 수용 기준·검증

기존 해당5개 검사 파일을 직접 수정한 경계만 보완:
- 여섯 모듈 각각3회 필요해도 다른모듈/전체8이 막지 않음, 각4번째transport0, 다른fixture첫호출허용, 동일run복구계수보존.
- 429→절단/JSON오류→정상 응답으로 실제3회,401/설정오류반복0, 짧은 파싱가능본문품질재호출0.
- 외부번호 조회/식별자충돌/partial저장후GET/구구성본호환. GET모델0·preview_dev밖쓰기0.

검사 명령은 계획의 tests/preview 5파일 중 직접 영향 범위. DB는 합성 또는 명시된 loopback *_test만. 실제모델·스크래핑·productionwrite·새 유료 smoke·전체suite 금지. 보유 credential/저장결과는 읽기만 가능, 비밀값 출력 금지. 기존서버 유지. A import이관 중 발생한 연결실패는 A소유파일 우회수정하지 말고 root에 계약을 확인한다.

시작 ACK로 기존부분변경/의도/API계약을 확인하고, 완료 후 변경파일·실제검사명령/결과·버전·미해결·EDITING STOPPED를 보고한다. no sub-workers. 공통 Plans.md 편집 금지.
