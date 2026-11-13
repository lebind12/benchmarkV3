# BI-01~03 통합 경계 독립 검토 — 읽기 전용 1회

당신은 구현 A/B/C와 별도인 DeepSeek 검토자다. 실제 모델은 deepseek-ai/deepseek-v4.1-flash-1017, 기존 Max 설정 유지. 시작 시 실제 모델을 확인하고 ACK한다. 모델이 다르면 검토를 시작하지 말고 보고한다. 프로필/비밀값 덤프·모델 변경·하위워커 금지.

Orca의 직접 감독 worker-start로 시작한다. 이전 작업의 외부 터미널 재사용이 아니다. 종료 전에 현재 Dispatch 메일만 한 번 읽고 보고한다. 완료 후 오래된 알림/메일을 반복 탐색하지 않는다. 다른 Dispatch의 메일은 이 작업 지시가 아니다.

## 목적과 검토 기준

원래 benchmark 앱+원래 서비스 관리 화면에 기존 preview LangGraph 생성기를 통합하는 BI-01~03 구현의 현재 수용 기준만 독립 확인한다. Plans.md, docs/superpowers/specs/2026-11-12-benchmark-preview-integration.md, 동명 plans 문서의 Review Focus와 BI-01~03을 먼저 읽는다. 사용자 직접 생성/콘텐츠 평가, 후속 홈 공개/수집 자동화는 이번 검토에서 실행하거나 설계하지 않는다.

A/B/C는 worker_done을 보고했다. A 인계 docs/implementation/match-preview/bi01-integration-report.md, B는 배정된5파일96passed 및 기록 transport 저장 증거를 보고했다. C는 타입체크 및 PreviewPanel12/MatchPreview8 통과를 보고했다. 이 통과를 그대로 결론으로 삼지 말고 아래 연결 경계를 소스/존재하는 증거와 대조한다. 테스트 개수 목표 없음.

## 읽기 범위와 초점

1. **원래 앱·로컬 인증·개발 저장 경계**: app/main.py, app/db.py, app/core/config.py 및 sessions.py, app/api/v1/auth.py, app/services/auth.py, app/auth/benchmark_sessions.py, app/preview/config.py/db.py/access.py/models.py, scripts/run_benchmark_dev.sh. 한 FastAPI 앱/원래 JWT+ADMIN/기존 계정 무변경/원격 세션 무쓰기/preview_dev만 신규 쓰기/로컬 런처 안전 기본값이 실제 호출 경로에 연결되는지. 설정 분리 이름만 만들고 실제 caller가 옛 경로를 쓰는 문제 확인. 기존 전체98복구파일을 새로 전부 리뷰하지 않는다.
2. **경기 한 번·논리 모듈별 최초 포함3회**: app/services/match_preview.py, preview_admin.py, retry/provider/bundle_pipeline/discovery/modules/bundle_sections, send_ledger 읽기. 전체8·타경기/trial 누적 차감·전체1800기한이 실제 경로를 다시 제한하지 않는지. 동일 run 복구 장부 보존, 새 run으로 내부 재시도 초기화 금지, 429/503/timeout/MAX_TOKENS/JSON 오류 한 루프, 401/설정/짧지만 유효한 본문 자동 재호출 금지. 정상 성공모듈 재전송0. 재생성 refresh/reuse도 실제 참여 logical_call_ids와 파생 예산이 일치하는지. 모델40000/동시2/배당0 유지.
3. **저장·조회·부분 본문·구성본**: GET은 DB만 읽기, 섹션 부족/quality 때문에 받은 본문을 숨기지 않음, 같은 경기 선택 결과만 최종 AI로 연결, 원문·이전 버전 보존. 관리자 실행 시험은 승인 자동생성이 아니며 프롬프트/워크플로우 버전 기록 보존. 새 품질 평가기 필요 없음.
4. **원래 관리 UI의 실연결**: frontend/src/views/ManagementView.vue, components/management/PreviewPanel.vue, lib/api/preview.ts/previewView.ts/http.ts/base.ts/session.ts, components/home-preview/MatchPreviewBody.vue 및 재사용 features/match-preview 컴포넌트에서 실제 호출되는 경계만. ADMIN 탭/원래4탭 유지, 경기번호 확인→명시 POST1→같은 run GET, 입력 변경/늦은응답/더블클릭·GET 새로고침 무호출, 부분 본문 보존. fixture/section 버전이 다른 결과를 잘못 섞지 않음. 저장 API 실패를 자료 없음으로 바꾸지 않음. 이름 강조는 strong/text만. UI 내부 진단을 본문에 섞지 않음. 섹션 재생성/구성본 버튼이 실제 백엔드 계약을 만족하는지.
5. **검증 경계와 증거**: tests/unit/test_benchmark_preview_runtime.py/test_benchmark_preview_auth.py, tests/preview/conftest.py/_dbguard.py 및 B 지정5파일·frontend PreviewPanel.test.ts를 읽는다. 현재 목표를 검사하는지, 단언 약화/가짜 writer로 실제 전달을 우회하는지, destructive fixture 전에 실제 loopback *_test 제한이 있는지. 별도 새 테스트/재현 스크립트 작성 금지.

## 이미 알려진 미완료 — 중복 발견이나 일반 확장 금지

- 5173/8000은 아직 이전 실행 프로세스이며 새 코드 브라우저·로그인 연결 검증 전이다. 서버를 시작/재시작하지 않는다. 로그인 비밀값을 요청하거나 사용하지 않는다.
- 사진·팀 로고 nullable 필드가 아직 API에 없다. 기존 names lookup에는 external_id가 있으나 structured 변환/프론트는 현재 null이다. root가 별도 최소 연결 작업으로 남겼다. 내부 player_id를 사진 외부ID로 가정하거나 고정 fixture mapping 요구 금지.
- 원래 home/management 일부 읽기 권한 부족, 원래 home_preview_publication/version 표 부재는 A 보고에 있다. 계정/preview 경로의 실제 blocker인지 구분하되 새 grant/public migration/권한 우회/추가 제품 설계 금지.
- A/B가 같은 테스트DB를 초기화하며 잠금 충돌했다. A는 preview_bi01_test, B는 preview_mp01_test에서 최종 검사 완료 보고. 이번 검토는 DB를 연결하거나 pytest를 다시 돌리지 않는다.
- 미사용 옛 auth/service/tokens, 광범위 주석/스타일 개선은 후속 참고로만. 원래 다른 테스트의 무관한 실패를 현재 단위 blocker로 확대하지 않는다.

## 허용 작업·종료

제품/테스트/설정/스크립트 편집0, HTTP0, DB연결/쓰기0, 모델/생성0, pytest/vitest/build0. 읽기 전용 소스 대조와 기존 증거 읽기만 수행한다. 필요하면 네트워크·DB·파일쓰기가 없는 기존 순수함수를 호출할 수 있지만 재현 코드를 파일로 만들지 않는다. 증명이 부족하면 한계로 적고 가상의 입력/환경으로 범위를 늘리지 않는다.

유일한 작성 파일: docs/implementation/match-preview/bi-integration-review.md. 검토 시각·해시·정확한 파일/함수, 재현 가능한 호출 경로, 사용자 영향과 가장 작은 수정 범위를 기록한다. 판정은 현재 수용 실패(차단), 현재 결함(비차단), 참고 개선을 구분한다. 신규 지적이 없으면 명시적으로 없다고 보고. 독립 검토1회 후 종료, 수정 확인은 나중에 지적 항목만 한다. 보고 후 EDITING STOPPED. Plans.md는 root 소유.
