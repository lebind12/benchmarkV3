# 관리 프리뷰 탭 섹션 워크플로우 승인 통합 구현 보고서 (`TPA-IMPL`)

## 1. 구현 요약

관리 프리뷰 탭(`/admin?tab=preview`)에서 저장된 프리뷰 본문 및 홈 반영 상태와 같은 화면에 섹션 워크플로우 버전 승인 UI를 직접 배치하고, 깨진 `/admin/runs` 별도 페이지 진입과 활성 이동 링크를 관리 프리뷰 탭으로 일원화했다.

### 변경 및 추가 파일
- [PreviewApprovalPanel.vue](file:///Users/woolee/orca/workspaces/benchmark/preview-api-migration/frontend/src/components/management/PreviewApprovalPanel.vue):
  - 저장된 프리뷰 본문(`preview-body`) 바로 아래에 섹션 워크플로우 승인 패널(`data-testid="preview-approval"`)을 추가했다.
  - 별도 대상 드롭다운 없이 단일 섹션 선택 목록(`preview-approval-item-${workflowId}`)을 통해 현재 표시 중인 섹션 결과와 승인 대상 `(workflow_id, run_id, section_result_id)`를 1:1로 바인딩한다.
  - 구성본(`composition.items`)이 다른 실행(`run_id`)의 섹션 결과를 고른 경우, `openRunId`가 아닌 해당 결과 행의 원래 `run_id`를 바인딩해 승인 요청에 전달한다.
  - 각 섹션의 한국어 `display_name`, 현재 승인 상태(`state`/`label`/`active_approval.workflow_version`), 검토 메모(`note`), 워크플로우 버전 단위 승인 안내(경기별 승인이 아님), 명시적 승인 버튼(`이 섹션 버전 승인`)을 제공한다.
  - `mock`, `storage_mismatch`, 빈 본문/`unavailable`, `approvable !== true`, `detail_error`/`sections_error`/`compositionError`/`composed_error`, 미확정 결과 행, 비ADMIN 권한(`!canApproveRole`)에서는 승인을 차단하고 사유(`preview-approval-blocked-reason`)를 표시하며, 임의 최신 행으로 대체하지 않는다.
  - 중복 클릭 방지(`approving` 잠금), API 실패 시 메모 보존 및 자동 재시도 금지, `openRunId`/`fixtureId`/`selectedWorkflowId` 전환 시 순번 가드(`contextSeq`)로 늦은 승인 응답 폐기를 구현했다.
- [PreviewPanel.vue](file:///Users/woolee/orca/workspaces/benchmark/preview-api-migration/frontend/src/components/management/PreviewPanel.vue):
  - `PreviewApprovalPanel`을 마운트하고 승인 성공 시 `@approved` 핸들러(`refreshAfterApproval`)에서 `previewRunsApi.detail(runId)`(미비 시 `previewRunsApi.approvals()` 폴백)와 `refreshHomeReflection(fixtureId, kickoffAt)`(GET 전용)을 함께 갱신한다.
  - 중첩된 진단 `<RunInspector>`에 `hide-approval`을 전달해 탭 내부에 승인 UI가 2중으로 뜨지 않게 했다.
  - 상단 `preview-open-runs` 링크를 `/admin/runs`에서 `/admin?tab=preview`(& `previewRun`) 및 인탭 실행 이력 토글(`실행 이력 보기`)로 전환했다.
- [RunInspector.vue](file:///Users/woolee/orca/workspaces/benchmark/preview-api-migration/frontend/src/features/match-preview/RunInspector.vue):
  - 선택적 prop `hideApproval?: boolean`(기본값 `false`)을 추가하고 `v-if="!hideApproval"`로 `data-testid="inspector-approval"` 섹션을 조건부 숨김 처리했다(단독 사용·기존 계약 호환 유지).
- [router/index.ts](file:///Users/woolee/orca/workspaces/benchmark/preview-api-migration/frontend/src/router/index.ts):
  - `/admin/runs`(`name: 'preview-runs'`) 진입 시 `requireAdminPreviewRoute` 가드를 먼저 통과한 뒤 `PreviewRunsView`를 렌더링하지 않고 `/admin?tab=preview`로 리다이렉트하며, `run` 쿼리가 있으면 `previewRun`으로 치환해 전달한다.
- 활성 `/admin/runs` 이동 링크 전환:
  - [SectionRunView.vue](file:///Users/woolee/orca/workspaces/benchmark/preview-api-migration/frontend/src/features/match-preview/SectionRunView.vue) (`openInspector` → `{ name: 'admin', query: { tab: 'preview', previewRun } }`)
  - [BundleGenerationPanel.vue](file:///Users/woolee/orca/workspaces/benchmark/preview-api-migration/frontend/src/features/match-preview/BundleGenerationPanel.vue) (`/admin?tab=preview`, `/admin?tab=preview&previewRun=...`)
  - [MatchPreviewRoute.vue](file:///Users/woolee/orca/workspaces/benchmark/preview-api-migration/frontend/src/features/match-preview/MatchPreviewRoute.vue) (`inspectorHref` → `/admin?tab=preview&previewRun=...`)
  - [AdminMetricsRoute.vue](file:///Users/woolee/orca/workspaces/benchmark/preview-api-migration/frontend/src/features/match-preview/AdminMetricsRoute.vue) (`openRun` → `{ name: 'admin', query: { tab: 'preview', previewRun, from: 'metrics', ...filters } }`)
- 직접 테스트 파일:
  - [PreviewApprovalPanel.test.ts](file:///Users/woolee/orca/workspaces/benchmark/preview-api-migration/frontend/src/components/management/PreviewApprovalPanel.test.ts) (신규 4건)
  - [PreviewPanel.test.ts](file:///Users/woolee/orca/workspaces/benchmark/preview-api-migration/frontend/src/components/management/PreviewPanel.test.ts) (baseline `readerPreview` mock 누락 보완 2건 + 승인 연동/중복 차단 통합 테스트 1건 추가)
  - [AdminPreviewRouting.test.ts](file:///Users/woolee/orca/workspaces/benchmark/preview-api-migration/frontend/src/features/match-preview/AdminPreviewRouting.test.ts) (`/admin/runs?run=run-123` 리다이렉트·인증 가드 및 `RunInspector hideApproval` 직접 검증 추가)
  - [AdminMetricsRoute.test.ts](file:///Users/woolee/orca/workspaces/benchmark/preview-api-migration/frontend/src/features/match-preview/AdminMetricsRoute.test.ts) (`tab=preview&previewRun=...` 쿼리 전환 검증)

## 2. 추가·수정 테스트 목적 및 실패 시 사용자 영향

1. `PreviewApprovalPanel.test.ts` — `binds single selected section to displayed result and submits once with note`:
   - 단일 섹션 선택으로 한국어 이름·워크플로우 범위·메모를 표시하고 선택 결과의 ID로 정확히 1회 승인해야 한다. 실패 시 관리자가 어떤 버전을 승인하는지 모르거나 다른 결과 ID로 잘못 승인할 수 있다.
2. `PreviewApprovalPanel.test.ts` — `uses cross-run owner run_id from composition and blocks if exact row is missing`:
   - 구성본이 다른 실행의 결과를 골랐다면 그 결과의 원래 `run_id`로 승인해야 하고 누락 시 대체 승인하지 않아야 한다. 실패 시 재생성·구성본 실행에서 다른 run의 섹션이 잘못된 `run_id`로 실패하거나 엉뚱한 행으로 승인된다.
3. `PreviewApprovalPanel.test.ts` — `disables approval with explicit reason on mock, storage_mismatch, empty, detail/composition errors, and non-admin`:
   - `mock`·`storage_mismatch`·빈 본문·미확정 행·조회 오류·비ADMIN 상태에서는 승인을 막고 이유를 알려야 한다. 실패 시 검증되지 않은 모의/불일치/오류 결과가 운영 기본 프리뷰 버전으로 잘못 승인된다.
4. `PreviewApprovalPanel.test.ts` — `prevents double-submit, preserves failure without retry, and discards stale response on selection switch`:
   - 중복 클릭·실패 유지(자동 재시도 금지)·실행/섹션 전환 중 늦게 온 승인 응답 폐기가 동작해야 한다. 실패 시 중복 승인 POST가 나가거나 다른 섹션/실행 화면에 이전 승인 완료 배너가 잘못 뜬다.
5. `PreviewPanel.test.ts` — `승인 성공 후 detail·홈 반영 GET을 함께 갱신하고 중첩 RunInspector 승인은 숨긴다`:
   - 프리뷰 탭에서 바로 승인 시 `detail`/홈 반영 GET이 함께 갱신되고 `RunInspector` 승인은 숨겨져야 한다. 실패 시 승인 직후 홈 반영 여부를 알 수 없거나 한 화면에 승인 UI가 두 번 떠 다른 버전을 누를 수 있다.
6. `AdminPreviewRouting.test.ts` — `/admin/runs?run=run-123` 리다이렉트 검사:
   - 기존 `/admin/runs` 직접 진입은 깨진 별도 화면 대신 관리 프리뷰 탭(`/admin?tab=preview&previewRun=...`)으로 리다이렉트되어야 한다. 실패 시 사용자가 기존 URL 또는 북마크로 진입하면 승인 UI가 없는 분리 화면에 갇힌다.
7. `AdminPreviewRouting.test.ts` — `hides inspector-approval only when RunInspector receives hideApproval=true`:
   - `PreviewPanel` 내부에 중첩된 `RunInspector`는 `hideApproval=true`일 때 자체 승인 UI를 숨기고 단독 실행에서는 유지해야 한다. 실패 시 프리뷰 탭의 진단 아코디언을 열었을 때 승인 UI가 2중으로 렌더링된다.

## 3. 검증 실행 결과

### TypeScript 및 직접 Vitest 스위트
실행 명령:
```sh
cd frontend && npx vue-tsc -p tsconfig.app.json --noEmit && npx vitest run src/components/management/PreviewPanel.test.ts src/components/management/PreviewApprovalPanel.test.ts src/features/match-preview/AdminPreviewRouting.test.ts src/features/match-preview/AdminMetricsRoute.test.ts src/features/match-preview/SectionRunView.test.ts
```
결과 (`exit code 0`, 전체 통과):
- `vue-tsc -p tsconfig.app.json --noEmit`: 0 errors
- `src/components/management/PreviewPanel.test.ts`: 30 passed
- `src/components/management/PreviewApprovalPanel.test.ts`: 4 passed
- `src/features/match-preview/AdminPreviewRouting.test.ts`: 4 passed
- `src/features/match-preview/AdminMetricsRoute.test.ts`: 2 passed
- `src/features/match-preview/SectionRunView.test.ts`: 7 passed
- 합계: 5 files passed, 47 tests passed

### 참고(기존 baseline 실패, 미수정)
- `src/features/match-preview/RunInspector.test.ts` (10 failed): `authenticatedFetch`가 `accessToken === null`일 때 `/api/v1/auth/refresh`를 호출하지만 해당 기존 테스트의 `fetchMock`에 `/auth/refresh` 응답이 없어 네트워크 오류(`서버에 연결하지 못했습니다`)로 실패하는 기존 baseline 실패이며 본 작업에서 수정하지 않았다. 대신 `RunInspector`의 `hideApproval` 분기는 `AdminPreviewRouting.test.ts`에서 `setAccessToken('admin-token')`과 함께 직접 검증했다.
- `src/views/AdminLoginView.test.ts` (8 passed, 1 failed — `reports a server error with its own message`): 기존 baseline 실패로 본 작업 범위 밖이다.

### 실시간 서버(`http://localhost:5173`) 및 스크롤 구조 확인
- Orca 브라우저 탭에서 `http://localhost:5173/admin/runs?run=00d34c23-a1d6-43d0-b8e2-fe9962184f3b`를 연 결과, 미인증 세션에서 `/auth/login?next=/admin/runs?run=00d34c23-a1d6-43d0-b8e2-fe9962184f3b`로 정상 리다이렉트되어 ADMIN 인증 경계와 쿼리 보존이 동작함을 확인했다(임시 탭은 확인 후 종료).
- CSS/레이아웃 점검(`frontend/src/styles/global.css`, `frontend/src/styles/management.css`): `body { overflow: hidden; }` 아래 `.management-page { height: calc(100vh - var(--header-height)); overflow-y: auto; }`가 단일 스크롤 컨테이너로 동작하며, `PreviewPanel.vue`와 `PreviewApprovalPanel.vue`에는 내부 높이를 자르는 고정 `height`/`overflow: hidden`이 없다.

## 4. 미실행 및 범위 제외 항목

- **실제 로그인 ADMIN 세션에서 `http://localhost:5173/admin?tab=preview&previewRun=00d34c23-a1d6-43d0-b8e2-fe9962184f3b` 화면 실측 및 스크롤 도달 확인**: Orca 기본 브라우저 프로필에 활성 ADMIN 세션이 없고 토큰·비밀번호 추출이 금지되어 미실행 상태다(코디네이터/사용자 환경의 로그인 세션에서 GET 확인 필요).
- **실제 `POST /api/v1/admin/preview/sections/{workflow_id}/approvals` 호출**: 사용자/코디네이터 지시에 따라 라이브 승인 쓰기는 실행하지 않았다.
- **레거시 뷰 일괄 삭제(`PreviewRunsView.vue`, `SectionRunView.vue` 등), 백엔드 코드·DB·`Plans.md` 수정**: 제외 범위에 따라 변경하지 않았다.
