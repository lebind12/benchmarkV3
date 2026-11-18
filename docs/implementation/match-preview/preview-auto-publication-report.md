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

## 6. AP-LIVE 실제 실행 결과 (2026-11-19)

계획서 AP-LIVE에 따라 서버를 현재 코드로 재시작하고 기존 수집 API를 **1회** 실행했다.
결과는 **부분 성공**이다. 승인 없이 생성·게시되는 경로는 실제로 동작했지만, 한 경기의
부상·매체 섹션이 **모델 시도 상한** 때문에 비었다.

### 6-1. 반영과 사전 확인

- 서버 재기동: 38000 PID **41543**(02:05 기동), 38003 PID **44805**(02:07 기동).
  두 프로세스 모두 제품 `7a3804a` 이후에 시작했으므로 현재 코드·설정으로 돈다.
  `WORKER_SCHEDULER_ENABLED=false`, `HOME_PREVIEW_ENABLED=false` 유지.
- 38003 자격: 기존 수집 자격(`API_FOOTBALL_KEY` 존재)과 모델 자격
  (`vertex`/`gemini-3.5-flash`/`global`, `PREVIEW_MODEL_LIVE_ENABLED=1`) 전달 확인.
  선수 3표 `postgres` INSERT=**true**(CE-ACL 유지).
- 5173은 이 워크트리 `frontend`의 Vite(프록시 → 38000/38003)임을 확인했다.
  8000·5174·5175·5176과 다른 워크트리는 건드리지 않았다.
- 사전: 진행 중 수집 0건, 승인 7건(최대 approved_at 2026-11-17T21:52:31Z), 두 경기 NS,
  계획 `can_collect=true`, 기간 **2026-11-19T00:00:00+09:00 ~ 2026-11-21T15:00:00+00:00**
  (실제 날짜 2026-11-19 기준으로 새로 계산된 값).
- **승인 readiness를 선행조건으로 요구하지 않았다.** 승인 행 삭제·신규 승인 POST·
  별도 bundle 생성 POST·재생성·undo는 **0회**다.

### 6-2. 요청 (1회)

- 2026-11-18T17:15:13Z(2026-11-19 02:15 KST) `POST /api/v1/admin/management/runs/preview-test`
  **1회**, HTTP 200. 수집 실행ID **`10a80162-cc37-4b78-b8a0-0bc2322ef4b4`**.
- 요청: `target_ids=[13]`, `preview_fixture_ids=[1557474,1557470]`,
  `generate_after_collection=true`, 기간은 위 계획 값 그대로.

### 6-3. 수집 (성공)

`status=succeeded`, stage `수집 결과 확인`, 종료 2026-11-18T17:21:14Z.
대상 item 처리 단위 `saved=55/55`, `failed=0`. `home_preview.state=finished`,
`failed=[]`.

주의(지시 4항): **55는 처리 단위 수이지 fixture 저장 수가 아니다.** 실제 저장 경기는
`collection_evidence` 기준으로 별도 확인해야 하며, 이번에는 그 값을 인용하지 않는다.

### 6-4. 자동 생성 (두 run 모두 succeeded)

| 경기 | 생성 run ID | 상태 | 품질 |
|---|---|---|---|
| 1557474 | **`4471fc0a-83f0-4e60-bef0-2b9819544ccf`** | succeeded | ready |
| 1557470 | **`2bacdc1f-3371-41dd-b16f-ffda4c3f2244`** | succeeded | ready |

### 6-5. 5섹션 상태 (핵심: 1557474는 2섹션이 비었다)

**1557474 / `4471fc0a`**

| 섹션 | 결과 ID | 품질 | 본문 | 사유 |
|---|---|---|---|---|
| players | `9a7e98fc-3691-4d5e-b636-39aacc2669fb` | ready | 402자 | — |
| odds | `82aab273-233a-45bd-9587-cfbe798a4c6f` | ready | 294자 | — |
| ai_forecast | `76433948-ef78-45f4-85aa-f88c6efb5b76` | ready | 433자 | — |
| availability | `e25eb4cb-…` | **insufficient** | **0** | `논리 호출 section_availability의 시도 상한(3회)에 도달했습니다.` |
| outlook | `c1efae45-…` | **insufficient** | **0** | `수집 기사에서 확인된 외부 매체 전망이 없어 …` |

**1557470 / `2bacdc1f`**: players `f586d8eb`·availability `9beae161`·outlook `3a8546fc`·
odds `0480346b`·forecast `4246dc36` **다섯 섹션 모두 ready**.

### 6-6. 원인 — Vertex 429가 시도 상한을 소진 (승인과 무관)

`preview_attempts`(읽기 전용)를 보면 **429 rate_limited**가 반복됐다.

| 논리 호출 | 시도 결과 |
|---|---|
| discovery_outlook | 429 → 429 → **200 ok** |
| discovery_people | 429 → **200 ok** |
| section_players | 429 → **200 ok** |
| section_ai_forecast | **200 ok** |
| **section_availability** | 429 → 429 → 429 (**상한 소진**) |
| **section_outlook** | 429 → 429 → 429 (**상한 소진**) |

즉 부상·매체 섹션이 빠진 이유는 **게시 승인 부재가 아니라**, Vertex가 `Resource
exhausted`(429)를 세 번 연속 반환해 모듈별 시도 상한(3회)에 걸렸기 때문이다. 같은 시각
1557470은 다섯 섹션이 모두 성공했으므로 코드 경로 문제가 아니라 **공급자 레이트리밋**이다.

**정직하게 남기는 불일치(확정 아님):** availability는 저장 사유가 "시도 상한 도달"인데
outlook은 "매체 전망 없음"이다. 그런데 outlook의 시도도 3회 모두 429였다. 두 섹션의
사유 문구가 왜 다른지는 이번 관측만으로 확정하지 않는다(추가 조사는 범위 밖).

### 6-7. 홈 게시와 complete 의미

| 표면 | 결과 |
|---|---|
| `GET /api/v1/home/fixtures/1557474/document` | run `4471fc0a`, `complete=true`, **섹션 3개**(players·odds·ai_forecast) |
| `GET /api/v1/home/fixtures/1557470/document` | run `2bacdc1f`, `complete=true`, **섹션 5개** |
| `GET /api/v1/home/recommendations` | 1557474 `state=ready`, `served=current`, generated_at 2026-11-18T17:17:00Z |

**`complete=true`를 "5섹션 완료"로 읽으면 안 된다.** 완전성 판정은
`REQUIRED_READER_SECTIONS = ("section_players", "section_ai_forecast")` 두 섹션만 본다.
1557474는 그 둘이 ready라 `complete=true`이지만 availability·outlook 본문이 없어 홈에
렌더되지 않는다. **홈 제외 사유는 승인이 아니라 빈 본문(insufficient)** 이다.
이 부분 표시 정책은 기존 사양 그대로이며 이번에 바꾸지 않았다.

사용자 목표에 부상 정보가 포함되므로, **"승인 없이 게시 성공"과 "부상 정보 실제 표시"는
별개**로 본다. 1557474는 후자를 충족하지 못했다.

### 6-8. 정본·후보

| run | watch | injury | candidates |
|---|---|---|---|
| `4471fc0a`(1557474) | 1 | **0** | 0 |
| `2bacdc1f`(1557470) | 1 | 1 | 0 |

- 부상 표 0행은 availability 실패와 일치한다(부상 섹션 자체가 없으므로 저장할 것도 없다).
- 이번 두 run은 **새 번역 후보를 만들지 않았다**(0행). 기존 후보 12행은 모두
  `review_status=pending` 그대로이며, 그 PENDING 상태가 게시를 막지 않는 것은 앞선
  격리 검사 근거(`_displayable`이 후보 상태를 보지 않음)로 확인된다. 새 후보가 없었으므로
  "이번 실행에서 PENDING 후보가 실제 공개됐다"는 실측은 하지 못했다.
- 승인 행 7건·최대 approved_at **무변경**.

### 6-9. 화면 확인 상태

- 공개 홈 실화면은 root가 직접 확인했다(1557474 3섹션, 1557470 5섹션 렌더).
- 관리자 `/admin?tab=preview` 실화면은 **이 워커 세션에서 미확인**이다(로그인 상태를
  조작하지 않았다). 승인 패널 부재는 `PreviewPanel.test.ts`의 대표검사로만 확인했다.

### 6-10. 판정

**부분 성공.** 승인 없이 수집→자동 생성→정본 저장→홈 게시가 실제로 완료됐고(1557470은
5섹션 전부, 1557474는 3섹션), 승인 행은 생성·게시에 쓰이지 않았다. 다만 1557474의
부상·매체 섹션은 **공급자 429로 시도 상한을 소진**해 비었으며, 이는 승인 제거와 무관한
런타임 실패다. `complete=true`만으로 5섹션 완료를 주장하지 않는다.

### 6-11. 남은 제약 / 미검증

- 429 레이트리밋은 이번 단위에서 재시도·우회하지 않았다(추가 모델 호출 0회). 같은 실행을
  다시 돌리면 개선될 수 있으나 **재실행은 승인 범위 밖**이다.
- 관리자 프리뷰 탭 실화면 미확인(위 6-9).
- 후보가 새로 생기지 않아 "PENDING 후보가 실제 공개되는 장면"은 실측하지 못했다.
- outlook 사유 문구와 시도 기록의 불일치는 미확정으로 남긴다.

## EDITING STOPPED (AP-LIVE)

이번 단위에서 수정한 파일: `frontend/src/components/management/PreviewApprovalPanel.test.ts`
(옛 문구 단언 1줄, 커밋 `3e23207`)와 이 보고서. 제품 코드 수정 0건. root 미커밋
`collection-home-e2e-report.md` 보존(내 커밋에 0줄). 수집 POST 1회·실모델 호출은 위
attempts 기록 범위이며 추가 호출 0회. 승인 행 생성·삭제 0건, undo 0회, 서버는 38000/38003만
재기동해 유지 중이다.
