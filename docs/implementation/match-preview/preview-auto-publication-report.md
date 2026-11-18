# 프리뷰 자동 게시와 번역 검수 분리 (AP-IMPL)

작성 2026-11-19. 실행 주체: DeepSeek 구현 워커(task_4444a86d4f8d / ctx_e62acc95a43a).
세션 모델 `deepseek-ai/deepseek-v4.1-flash-1017`, provider `hive`, 추론 강도 `high`.
하위 워커 0, root `Plans.md` 편집 0. 설계·배정서:
`docs/superpowers/plans/2026-11-18-preview-auto-publication.md`.

## 결론

사용자 확정(승인/미승인은 **AI 한글 번역·선수 연결의 검수 상태**이며 프리뷰 게시 허가가
아니다)에 따라, **게시와 생성의 워크플로우 승인 의존을 제거**했다. 승인 행을 새로 만들거나
자동 승인하는 경로는 만들지 않았고, 남겨야 하는 정상성 보호(failed/cancelled/mock/빈본문/
정본 불일치)는 그대로 유지했다. 후보 PENDING 즉시 사용과 DB 한글명 우선도 유지했다.

## 1. 착수 확인

- HEAD `23253fe904f34fcee635edf9491af5bb550b7c02`, branch `lebind12/preview-api-migration`.
- 미커밋 변경은 root가 수정한 `docs/implementation/match-preview/collection-home-e2e-report.md`
  1건뿐이었다. 그 파일은 **건드리지 않았고 커밋에도 포함하지 않았다**(아래 EDITING STOPPED).

## 2. 변경 (제품)

### 2-1. 수집 후 자동 생성의 승인 게이트 제거

`app/services/home_preview_collection.py`

- `run_collection_generation`에서 생성 **직전** 승인 판정 블록을 제거했다. 이전에는
  `bundle_admission_state` 결과가 `ready`가 아니면 후보를 `approval_not_ready` /
  `approval_query_failed`로 건너뛰고 모델을 부르지 않았다.
- 더 이상 쓰이지 않는 `_admission()` 헬퍼를 삭제했다(24줄).
- `admission` 인자는 **호환용으로만** 남기고 게이트로 쓰지 않는다는 주석을 달았다.
  기존 호출부(테스트 포함)가 넘겨도 생성이 막히지 않는다.
- 모듈 docstring의 승인 경계 설명을 새 정책으로 고쳤다.

### 2-2. 홈 문서·추천의 승인 의존 제거

`app/services/home_preview_document.py`

- `_displayable`: 승인 버전 일치·승인 근거 일치 두 갈래 판정을 제거하고, **본문 있음 +
  mock 아님 + workflow_id/버전 존재**만 본다. 승인 인자는 호환용으로 남기고 쓰지 않는다.
- `_chosen_rows`, `select_document`: 승인 인자를 선택 사항으로 바꾸고 기본값을 `None`으로
  두었다. 워크플로우당 한 행·구성본 우선 규칙은 그대로다.
- `_load_selection_context`: 승인 표를 **읽지 않는다**. 따라서 승인 조회 장애가 홈 조회
  실패로 번지지 않는다(수용 기준 1의 홈 쪽 대응).
- `_read_approvals`: "게시 판정에 쓰지 않는 진단·표시용"으로 docstring을 정정했다.

`app/services/home_preview.py`

- `recommendations`에서 승인 표 조회와 `SQLAlchemyError → PreviewDocumentUnavailable`
  변환을 제거했다. 승인 조회 실패가 추천 조회 실패로 승격되지 않는다.

`app/preview/pipeline.py`

- `admission_state`의 docstring·`note`를 "검수 현황 요약이며 게시·생성의 허가 판정이
  아니다"로 정정했다. **판정 로직 자체는 손대지 않았다**(legacy API 전면 개편 제외 지시).

### 2-3. 관리자 프리뷰 탭 문구 정리

- `PreviewApprovalPanel.vue`: 헤더 안내를 "승인은 번역·선수 연결 **검수 표시**이며 프리뷰
  생성·홈 공개는 승인과 무관"으로 고쳤다. 승인 성공 문구도 "검수 승인이 기록됐습니다
  (홈 게시는 승인과 무관)"로 바꿨다.
- `PreviewPanel.vue`: `no_approved_version` 안내를 승인 부재가 아니라 **표시 가능한 저장
  본문 없음(정본 확인·필수 섹션 조건 미충족)** 으로 고쳤다. 응답 코드 값은 그대로 두어
  기존 클라이언트 호환을 유지했다.
- 게시 승인 버튼을 새로 만들지 않았고, 본문/저장/홈 비교·진단 표시는 그대로 유지했다.
  `/admin/runs`는 사용하지 않았다.

### 2-4. 손대지 않은 것

- `app/api/v1/preview_admin.py`: bundle 경로(`/bundle-runs`)에는 애초에 admission 게이트가
  없어(`grep` 결과 `AdmissionRefused`/`admission` 참조 0건) 수정이 필요 없었다. legacy
  `/runs`의 admission 파라미터·거부는 계획서의 "legacy 전면 개편 제외"에 따라 그대로 뒀다.
- 선수 처리·후보 저장 코드: 변경하지 않았다. 후보 PENDING 즉시 사용과 DB 한글명 우선이
  이미 그 경계에서 유지되고 있음을 확인만 했다(2-5 참조).

### 2-5. 후보 PENDING이 게시를 막지 않는지 확인

`_displayable`이 후보·미연결 상태를 보지 않으므로, AI 후보가 PENDING이거나 `player_id`가
미연결이어도 섹션 본문이 있으면 표시된다. 후보 생성·PENDING 저장 자체는 손대지 않았다.

## 3. 직접 검증

로컬 격리 DB `127.0.0.1:55432/preview_mp01_test`만 사용했다(`_dbguard`가 루프백·`*_test`
이름을 먼저 검사). 운영 URL 테스트·초기화 0회, 동시 pytest 없음.

| 명령 | 결과 |
|---|---|
| `pytest tests/unit/test_home_preview_collection.py -q` | **35 passed** |
| `pytest tests/unit/test_home_preview_document.py -q` | **19 passed** |
| `pytest tests/unit/test_preview_api_storage_migration.py -q` | **7 passed** |
| `pytest tests/unit/test_management_preview_test.py -q` | **27 passed** |
| `pytest ... 위 4개 파일(88건) + tests/unit/test_bundle_collection_admission.py(9건) -q`(합산 재확인) | **97 passed** = 88 + 9 |
| `pytest tests/preview/test_player_section_integration.py -q` | **9 passed** |
| `npx vitest run src/components/management/PreviewPanel.test.ts` | **31 passed** |
| `npx vitest run PreviewApprovalPanel.test.ts PreviewTestPanel.test.ts` | **26 passed, 2 failed(기준선과 동일)** |
| `npx vue-tsc -p tsconfig.app.json --noEmit` | **exit 0** |

새/수정 검사는 모두 수용 기준에 연결된 대표 사례다.

- `test_missing_approval_does_not_block_generation` (기준 1): 게이트 `not_ready`여도 두 경기
  생성이 정상 호출된다.
- `test_approval_query_failure_does_not_block_generation` (기준 1): 승인 조회 장애를 생성
  실패로 바꾸지 않는다.
- `test_mock_results_are_not_published_but_unapproved_live_results_are` (기준 2·4): 모의는
  계속 차단, 승인 없는 live는 게시.
- `test_read_document_publishes_a_live_run_with_no_approval_rows` (기준 2): 승인 행 0건에서도
  홈이 문서를 게시한다.
- `test_recommendations_and_document_agree_with_or_without_approval_rows` (기준 2): 두 표면이
  승인 유무와 무관하게 같은 run/섹션을 선택한다.
- `test_failed_run_never_replaces_the_previous_healthy_document` 등 기존 보호 검사는 그대로
  통과한다(기준 2의 정상성 보호 유지 확인).

### 기준선과 분리한 실패 2건

아래 2건은 **내 변경을 stash한 상태에서도 동일하게 실패**해 기존 기준선 문제로 분리했다.

- `PreviewApprovalPanel > binds single selected section ...` — `emit('approved')` 미발생.
- `PreviewTestPanel > 응답을 못 받은 요청의 재전송은 같은 request_id ...` — emit 없음.
- (백엔드) `tests/preview/test_pipeline.py::test_admin_preview_run_endpoint_requires_admin`
  — `pipeline.py` 수정을 stash해도 동일하게 실패. legacy 경로 검사이며 이번 범위 밖이다.

## 4. 미검증 / 남은 일

- **실제 수집·실모델·홈 반영은 확인하지 않았다.** 이번 단위는 서버 재기동 0회, 수집 POST 0회,
  실모델 호출 0회다. 승인 없는 실제 경기에서 생성·게시가 끝까지 되는지는 AP-LIVE에서
  확인해야 한다.
- 승인 행이 없는 상태의 실제 DB 실측(권한·게이트)은 격리 검사로만 대체했다. 운영 계정·승인
  행 삭제 실험은 하지 않았다.
- legacy `/runs` 경로의 admission 거부는 의도적으로 남겨 두었다. 이 경로를 쓰는 화면이
  있다면 별도 판단이 필요하다(현재 관리 탭은 bundle 경로를 쓴다).

## EDITING STOPPED

아래 11개 파일만 수정했고 그 외 변경은 없다. root가 수정한
`docs/implementation/match-preview/collection-home-e2e-report.md`는 **건드리지 않았고
커밋에 포함하지 않았다**(워크트리에 미커밋 상태로 남아 있다).

제품 4: `app/services/home_preview_collection.py`, `app/services/home_preview_document.py`,
`app/services/home_preview.py`, `app/preview/pipeline.py`
프론트 2: `frontend/src/components/management/PreviewApprovalPanel.vue`,
`frontend/src/components/management/PreviewPanel.vue`
검사 4: `tests/unit/test_home_preview_collection.py`, `tests/unit/test_home_preview_document.py`,
`tests/unit/test_preview_api_storage_migration.py`, `tests/unit/test_management_preview_test.py`
보고서 1: 이 문서(`docs/implementation/match-preview/preview-auto-publication-report.md`)

서버 재기동·실수집·실모델 0회. 승인 행 생성·삭제 0건. 계정·권한·마이그레이션 변경 0건.

## 5. 독립검토 R1 수용 보완 (2026-11-19)

독립검토 `/tmp/ap-review.md`가 지적한 R1(승인 버튼을 "번역·선수 연결 검수"로 오표기)을
**최소 수정**으로 처리했다. 지시대로 번역 관리 UI를 새로 만들거나 다른 페이지로 옮기지 않고,
활성 프리뷰 탭에서 패널 마운트를 제거하는 쪽을 택했다.

### 5-1. PreviewPanel에서 승인 패널 제거

`frontend/src/components/management/PreviewPanel.vue`

- `<PreviewApprovalPanel>` 마운트 삭제(활성 프리뷰 탭).
- 그 패널에서만 쓰던 것을 함께 정리: `PreviewApprovalPanel` import,
  `approvalsFallback`/`approvalRefreshWarning` 상태, 두 곳의 초기화, 승인 후
  detail·홈 재조회를 묶던 `refreshAfterApproval()` 핸들러, 미사용이 된
  `ApprovalsSummary` 타입 import.
- **유지**: 본문 표시(`MatchPreviewBody`), 진단(`preview-diagnostics`), 구성본 패널,
  저장 결과 조회, 홈 반영 새로 조회(`refreshHomeReflection`과 홈 문서 GET) 경로.
  `RunInspector`의 `hide-approval`도 그대로다.

### 5-2. 남은 승인 컴포넌트 문구를 사실로 정정

`PreviewApprovalPanel.vue`(다른 곳에서 쓰이더라도 오해가 없도록)

- 헤더: "이 승인은 **섹션 워크플로우 버전과 그 근거 결과 행을 기록**합니다. …
  **AI 한글 번역 상태나 선수 연결을 변경하지 않습니다**(번역 후보의 검수 상태와 선수
  식별자는 그대로입니다). 프리뷰 생성과 홈 공개도 이 기록과 무관합니다."
- 성공 문구: "… 워크플로우 버전 승인이 기록됐습니다. **번역 후보 검수 상태와 선수 연결은
  변경되지 않았습니다.**"
- 기존 승인 이력·API는 삭제하지 않았다(엔드포인트·테이블·감사 기록 그대로).

### 5-3. pipeline 설명을 실제 범위로 정정

`app/preview/pipeline.py` — **판정 로직·버전 계산·프롬프트 변경 0**이다.

- `admission_state`: docstring/`note`를 "**legacy 전체 프리뷰 경로**의 섹션 워크플로우 버전
  승인 현황"으로 고쳤다. 현재 수집 후 자동 생성·bundle 생성·홈 공개는 이 값과 무관하고,
  **legacy 전체 프리뷰 시작만** 이 판정으로 거부된다는 사실을 명시했다.
- `bundle_admission_state`: "승인이 없으면 자동 생성을 시작하지 않는다"는 **거짓 설명을
  삭제**하고, "이 값은 자동 생성을 막지 않는다(수집 후 생성·홈 공개는 승인과 무관)"로
  정정했다. 반환 값의 의미(섹션별 버전 승인 현황)는 그대로다.

### 5-4. 검사

| 명령 | 결과 |
|---|---|
| `npx vitest run src/components/management/PreviewPanel.test.ts` | **31 passed** |
| `npx vue-tsc -p tsconfig.app.json --noEmit` | **에러 0(exit 0)** |
| `pytest tests/unit/test_bundle_collection_admission.py tests/unit/test_home_preview_collection.py tests/unit/test_home_preview_document.py -q` | **63 passed** |

대표검사(이번 지적에 직접 연결):
- `활성 프리뷰 탭에는 섹션 워크플로우 승인 UI가 없고, 저장 본문·홈 비교는 그대로 보인다`
  — 승인 패널/버튼/컴포넌트 부재 + 본문·홈 비교 존재를 함께 단언한다.
- `승인 API를 호출하지 않고 저장 본문·구성본·홈 재조회 경로만 쓴다` — 승인 제출 UI가 없고
  진단·패널은 남아 있음을 확인한다.
- 기존 `승인 성공 후 detail·홈 반영 …` / `approvable 판정` 두 검사는 승인 UI 전제라
  위 두 검사로 대체했다(삭제가 아니라 대체).

### 5-5. 변경 파일

`frontend/src/components/management/PreviewPanel.vue`,
`frontend/src/components/management/PreviewApprovalPanel.vue`,
`app/preview/pipeline.py`, `frontend/src/components/management/PreviewPanel.test.ts`,
이 보고서. 그 외 변경 0. root 미커밋 문서는 건드리지 않았다.

## EDITING STOPPED (R1 보완)

승인 컴포넌트 자체의 기준선 실패 1건(`binds single selected section … emit`)은 이번에도
동일하게 남아 있으며 성공으로 표현하지 않는다. 서버 재기동·실수집·실모델·승인 변경·DB 쓰기
0회, root 문서·Plans 보존.
