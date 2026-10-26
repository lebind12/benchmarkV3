# 관리 목업 — 개발 방향

정본: [spec](streamer-management-mock.spec.md). 이번 작업은 로컬 평가용 FE이며 backend 수정·commit/push/merge는 없다.

## 파일·컴포넌트

```text
frontend/src/views/AdminMockView.vue              # shell, URL 탭, 공통 상태/안내
frontend/src/components/admin-mock/
  TargetsPanel.vue                              # 목록·선택·편집/추가
  ExecutionPanel.vue                            # 선택/확인·현재 작업·취소
  HistoryPanel.vue                              # 필터·목록·상세
  TranslationsPanel.vue                         # 4종·검색·편집·충돌·이력
  MockDialog.vue                                # 필요 시 공통 modal/포커스 처리
frontend/src/lib/api/managementMock.ts           # 타입과 전용 namespace fetch
frontend/src/mocks/management/
  data.ts                                       # 샘플 생성·타입/시드 (handler만 import)
  state.ts                                      # storage·모의 진행·변경 규칙
  handlers.ts                                   # MSW REST handlers
  browser.ts                                    # 평가 경로 전용 초기화
```

파일 분해는 구현량에 맞춰 합칠 수 있으나 view에서 sample JSON을 직접 import하지 않는다. 기존 shadcn 계열 `components/ui/button/Button.vue`를 버튼에 활용할 수 있다. repo에 없는 Table/Dialog/Tabs 패키지를 새 설치하지 않고 semantic HTML·기존 CSS와 작은 공통 dialog를 사용한다. 기존 site header/테마 유지.

## 라우팅과 mock 초기화

- `import.meta.env.DEV || import.meta.env.VITE_USE_MOCK === 'true'`일 때만 `/admin/mock` route와 개발용 header 링크를 등록한다. 기존 `/admin` guard·component는 그대로 유지한다.
- view 진입 시 `ensureManagementMock()`을 await한 뒤에만 샘플 fetch를 시작한다. 초기화 실패 화면도 같은 view에서 표시해 빈 라우트가 되지 않게 하고 실제 API로 fallback하지 않는다.
- 기본 VITE_USE_MOCK=false에서는 관리 전용 MSW handler만 활성화한다. 일반 홈/다른 관리 API를 가로채지 않는다. 이미 global mock=true로 worker가 시작된 환경은 기존 worker에 관리 전용 handler를 추가해 중복 worker 충돌을 막는다.
- 탭 변경은 router query를 사용하고 reload 시 복원. 직접 진입/다른 탭에서 헤더 클릭 모두 동작해야 한다.

## 상태와 저장

- Pinia 또는 composable은 `tab, loading/error, targets/catalog, selectedTargetIds, activeRun, historyFilter/detail, translationFilter/editor/history/conflict, toast/scenario`를 분리한다. 루트 앱의 기존 auth store 값은 건드리지 않는다.
- MSW 상태 key는 `benchmark:management-mock:v1` 등 전용 namespace. schema version과 기본값을 검증하고 깨진 값은 안전한 샘플로 복구한다. storage 불가 시 복원 한계를 안내한다.
- 5개 기본 리그 중심 6~8개 target, 6개 이상 종료 이력(성공/부분 실패/취소/중단), 4종 각 2~4개 번역 샘플을 둔다. 숫자 요약은 dataset에서 계산. 날짜는 현재 기준 최근 7일로 생성해 fixture가 곧 만료되지 않게 한다.
- 모의 작업은 started_at과 deterministic unit progress를 사용. GET 시 경과 시간으로 진척을 계산/저장해 reload 후 복원한다. cancelled/interrupted는 추가 진행하지 않는다. 완료/실패에 target별 저장/실패/미처리 수와 로그를 남긴다.
- 상태 제안: `queued|running|cancel_requested|succeeded|partial_failed|failed|cancelled|interrupted`. 진행률과 성공률을 혼동하지 않는다.

## MSW 요청 목록

모든 path의 prefix는 `/api/_mock/management`. 전용 fetch client는 기존 `apiUrl`/`VITE_BACKEND_URL`을 사용하지 않고 같은 origin의 이 상대 path로만 요청한다. 실제 backend URL로 목업 쓰기가 나가면 안 된다. `getJson/requestJson`으로 에러 `{code,message,current?}`를 처리하며 HTTP 409/422/503을 구분한다.

| Method / path | 역할·응답 후보 |
|---|---|
| GET `/catalog?query=` | `{items:[{id,name,name_ko,country,seasons,coverage}]}` |
| POST `/catalog/refresh` | `{updated_at,api_count,synced_count,catalog_count}`, 확인/진행/검색 재조회, 실제 외부 호출 없음 |
| GET `/targets` | `{items:Target[]}` |
| POST `/targets` | 같은 league+season upsert, 허용 시즌/옵션·제한 검증 |
| PATCH `/targets/:id` | 옵션·is_active·fixture_limit(null 포함) 갱신 |
| DELETE `/targets/:id` | 설정 제외, 수집 데이터 보존 설명 |
| GET `/runs` | `{active:Run|null,items:Run[]}` 및 경과 시간 진행 |
| GET `/runs/:id` | target 결과·로그 포함 run 단건 |
| POST `/runs` | `{target_ids,mode,parent_run_id?,scenario?}` → run, active 중복 409 |
| POST `/runs/:id/cancel` | 취소 요청 후 완료 결과, 기존 저장 값 유지 |
| GET `/translations` | 유형/이름/상태 필터 또는 FE 필터용 전체 결과 |
| PATCH `/translations/:type/:id` | `{name_ko,short_name_ko,expected_version}` → 갱신/409 current |
| GET `/translations/:type/:id/history` | before/after·editor·시각·version 이력 |
| POST `/scenario` | 빈/오류/충돌/부분 실패/중단의 샘플 재현 |
| POST `/reset` | 관리 mock key만 기본값으로 복원 |

모의 API는 기존 실제 `/api/v1/admin/*`를 대신 호출하지 않는다. backend 후보는 기존 대상 CRUD/실행·로그 경로 확장과 신규 cancel/retry/translations이며 최종 shape는 사용자 평가 후 확정한다. 이번에 endpoint-flow를 init하지 않는다.

## 중요 UI 규칙

- 대상 선택은 탭 간 유지. 추가와 편집은 같은 폼을 사용하고 리그/시즌·지원 영역 설명을 표시한다.
- 실행/제외는 `window.confirm` 대신 명시적 dialog로 영향과 결과를 평가할 수 있게 한다. 실패 재실행은 실패 target 선택 상태로 이동 후 확인한다.
- 번역 충돌은 current와 draft 별도 상태. 최신값 적용은 version만 조용히 갈아끼워 자동 overwrite하지 말고 사용자의 비교/재검토 동작을 요구한다.
- 보관 7일은 terminal run에만 적용. active run은 이력 prune과 별도이며 번역 변경 이력에 7일 규칙을 붙이지 않는다.
- 세로 높이/overflow는 기존 global body hidden과 호환되도록 화면 root에서 관리한다. panel/action은 모바일에서도 접근 가능해야 한다.

## 진행과 결과 보고

로컬 코드·테스트를 먼저 완성하고 `IMPL_PUSHED`나 `MERGED`로 상태를 과장하지 않는다. user 평가 전 BE 구현·실 API 연동·운영 적용·push를 시작하지 않는다. 검증 증거는 unit/E2E/type/build와 실제 screenshot/viewport 확인으로 남긴다.

사용자 dev server가 5173에서 실행 중이므로 kill/재시작하지 않는다. Playwright는 전용 5186 포트 config로 검증하며, 평가 경로가 기존 5173의 VITE_USE_MOCK=false 환경에서도 작동하는지 확인한다.

## 2026-10-25 변경

`CatalogPanel.vue`는 조회/최신화/시즌 선택을 담당하고 `TargetsPanel`로 선택한 리그/시즌을 전달한다. `RunLogs.vue`와 `logPresentation.ts`는 로그 수준/원인 필터, 한국어 설명, 원문 확인과 원인 집계를 담당한다. 과거 샘플 실행은 기존 로컬 데이터 보존 후 코드가 있는 실패 로그 fixture만 보충한다.

BE 후속 응답 초안: 로그 `{at,code,level,message,target_id,stage,attempt,max_attempts}`. 실제 기존 `{ts,message}`에는 수준/원인 코드가 없으므로 필드 정규화 및 알려진 과거 문구의 제한적 대응이 필요하다. 문자열의 임의 키워드만으로 구체 원인을 확정하지 않는다. `worker_runs.MAX_LOG_LINES=1000`이므로 운영 통계는 잘린 로그 tail만으로 전체 집계하지 않는다. 실행 중 누적한 원인별 카운터를 종료 결과에 저장하고 `total/retained/dropped` 및 통계 범위를 전달하는 방향으로 BE 평가 후 확정한다. 현재 목업은 전체 샘플 이벤트의 클라이언트 집계이며 실제 서버 통계 구현이 아니다.
