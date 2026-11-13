# PF-REUSE 프론트 연결 — 재생성 패널의 저장 묶음·다른 섹션 보존

작성: 2026-11-12 KST. 담당: DeepSeek 구현 워커(Orca `dsh-tui`, 실제 모델
`deepseek-ai/deepseek-v4.1-flash-1017`, 사용자 설정 추론 강도 Max 유지).

## 1. 사용자가 본 결함과 원인

실제 관리자 run `d96fe824-bc38-4402-bb2c-9f16fdee4b3b`에서 섹션 재생성 → `section_odds` →
`저장된 정보 원문 재사용` 라디오가 **"이 실행에는 재사용할 정보 원문 묶음이 없습니다"** 로 비활성.
그러나 같은 실행의 `GET /runs/{id}/information-bundle`은 `availability.available=true`,
`bundle.bundle_id=bundle-524b60b9eb084a06`을 준다.

**원인(코드, 결정적)**: `PreviewPanel.vue`가 `SectionRegenerationPanel`에 `bundleId` prop을
**넘기지 않았다**. 패널은 `bundleId`가 비면 `reuseAvailable=false`로 재사용 모드를 막는다
(`SectionRegenerationPanel.vue`의 `reuseAvailable`/`regen-reuse-blocked`). `regenerated`
이벤트도 연결되지 않아 새 run을 열 방법이 화면에 없었다. 즉 서버·저장 자료 문제가 아니라
**부모의 연결 누락**이다.

## 2. 수정 (4파일, 모두 기존 파일)

| 파일 | 변경 |
|---|---|
| `frontend/src/components/management/PreviewPanel.vue` | ① 재생성 영역을 **사용자가 펼 때만** 기존 `previewRunsApi.informationBundle(runId)`를 호출해 `parseInformationBundle`로 `bundleId`를 얻고 패널에 전달 ② `@regenerated`를 받아 **새 run 열기 버튼** 제공 ③ 화면이 표시 중인 다른 섹션 버전의 결과 ID를 `selectedResultIds`로 전달 ④ `section_odds`에서만 모델 호출 문구 정정 ⑤ run 전환·초기화 시 묶음 상태·재생성 결과 초기화 |
| `frontend/src/features/match-preview/SectionRegenerationPanel.vue` | `selectedResultIds` prop 추가(기본 `[]`), 요청에 `selected_result_ids` 포함(자기 결과는 제외), 배당 섹션의 재사용·재생성 문구를 0회 모델로 표시 |
| `frontend/src/components/management/PreviewPanel.test.ts` | 대표 검사 4건 추가 + 재생성 패널 대역(stub)이 받은 props를 노출하도록 확장 |
| `frontend/src/features/match-preview/SectionRegenerationPanel.test.ts` | 대표 검사 2건 추가(선택 ID 보존·배당 문구) |

`frontend/src/features/match-preview/types.ts`는 **이번 라운드에서 손대지 않았다**(mtime 20:58,
직전 라운드 값 그대로). `SectionRegenerationRequest`에 `selected_result_ids`가 이미 있었으므로
타입 변경이 필요 없었다.

### 2-1. 수용 기준 대응

| 수용 기준 | 구현 |
|---|---|
| 1. 패널을 열면 기존 API로 저장 묶음 조회 → 정확한 bundleId 전달 | `toggleRegeneration` → `loadBundleForRegeneration` → `informationBundle` → `parseInformationBundle(...).bundleId` → `:bundle-id` |
| 1-a. 조회 실패를 "없음"으로 숨기지 않고 차단 | 실패 시 `bundleStatus='error'`, `preview-regeneration-bundle-error`에 서버 사유 표시, `bundleId=null`이라 재사용 라디오 비활성 |
| 1-b. run 변경에 낡은 응답이 붙지 않음 | `bundleSequence` 순번 + `openRunId.value !== runId` 확인, run 열기/생성 시 상태 초기화 |
| 1-c. 자동 생성 금지 | 접힌 상태에서 요청 0회(검사로 확인). 재생성 성공 후에도 **자동으로 run을 열지 않는다** |
| 2. 선택 섹션 1건만 재생성, base·bundle·live·reuse 보존 | 기존 payload 유지(`mode:'live'`, `source_mode:'reuse'`, `bundle_id`, `base_run_id`, `base_result_id`) + `selected_result_ids` 추가 |
| 2-a. 다른 섹션 결과를 selected_result_ids로 전달 | `otherSectionResultIds`(화면 표시 버전과 같은 버전의 저장 행) → 패널 → 요청 |
| 2-b. 원래 저장 run/구성본 덮어쓰기 금지, 마지막 AI 재호출 금지 | 새 run에만 POST(기존 경로 그대로). 마지막 AI를 부르는 동작은 추가하지 않았다 |
| 3. 성공 run을 바로 확인 가능 | `@regenerated` → `preview-regeneration-result` + `재생성된 실행 열기` → 기존 `openStoredRun` |
| 3-a. 모델0/배당0 사실 오해 문구 최소 정정 | `section_odds`에서만 "모델 호출 없이(0회)" 문구. 다른 섹션 문구는 그대로 |
| 4. 대표 검사 + 신규 타입오류 0 | 아래 §3 |

### 2-2. 서버 계약과의 대조(변경 없음, 읽기만)

- `GET /runs/{id}/information-bundle`은 저장 행만 읽는다. 이 조회를 재생성 영역을 펼 때만
  호출하므로 조회만으로 모델·외부 호출이 생기지 않는다.
- `selected_result_ids`는 서버가 **각 결과를 자기 실행에서 찾아** 경기·섹션을 검증하고,
  통과한 항목만 구성본으로 복사한다. 다시 만든 섹션만 새 결과로 교체된다
  (`app/preview/bundle_pipeline.py`의 `resolve_selected_results` / 구성본 복사부).
  그래서 다른 섹션 본문이 유지되고 기존 실행·구성본은 덮어쓰지 않는다(새 run 소유).
- `section_odds`의 기대 모델 호출 수는 `preview_admin._SECTION_MODEL_CALLS`에서 **0**이다.
  같은 맵에서 다른 섹션은 1이므로, 배당에만 0회 문구를 적용했다.

## 3. 검사 명령과 실제 결과

```
cd frontend && npx vitest run \
  src/components/management/PreviewPanel.test.ts \
  src/features/match-preview/SectionRegenerationPanel.test.ts
→ Test Files 2 passed (2) / Tests 31 passed (31)
   (PreviewPanel 21 = 기존 17 + 신규 4, SectionRegenerationPanel 10 = 기존 8 + 신규 2)

cd frontend && npx vue-tsc -p tsconfig.app.json --noEmit
→ exit 2, 오류 8건 — 모두 기존(§4). PreviewPanel.vue·SectionRegenerationPanel.vue 오류 0
```

추가한 대표 검사와 수용 기준:

| 검사 | 수용 기준 | 실패하면 사용자에게 생기는 일 |
|---|---|---|
| 재생성 영역을 열 때 `informationBundle('run-1557474-a')` 1회 호출, 패널이 `bundle-524b60b9eb084a06`을 받는다 (접힌 상태 요청 0회) | 1 | 묶음이 있는데도 재사용이 계속 비활성 |
| 조회 503 → `preview-regeneration-bundle-error`에 사유 표시, `bundleId` 비움 | 1-a | 조회 실패가 "묶음 없음"으로 위장된다 |
| 다른 run 열기 → 이전 run의 늦은 응답이 새 run에 붙지 않음 | 1-b | 이전 run 묶음으로 재생성해 다른 자료를 쓴다 |
| 다른 섹션 표시 버전만 `selected_result_ids`로 전달(자기 섹션 제외), 성공 후 열기 버튼으로 `openStoredRun` 호출 | 2-a·3 | 재생성 후 다른 섹션 본문이 달라지고 새 결과를 확인할 수 없다 |
| 재사용 요청이 `base_run_id`/`base_result_id`/`bundle_id`/`mode:'live'`/`source_mode:'reuse'` 보존 | 2 | 비교 기준·묶음이 빠져 다른 조건으로 생성된다 |
| `section_odds`에서 "모델 호출 없이(0회)" 문구, 다른 섹션 문구는 미표시 | 3-a | 배당 재생성이 모델을 부른 것으로 오해된다 |

**회귀 확인(검사가 실제 결함을 잡는지)**: `:bundle-id`/`:selected-result-ids` 전달과
`selected_result_ids` payload 줄을 일시 제거하고 재실행하면 위 4건이 실패(`4 failed | 27 passed`),
되돌리면 31 passed. 즉 새 검사는 이번 결함을 직접 잡는다.

## 4. 기존 타입 오류 8건 (확대 수정 금지, 그대로 둠)

```
src/components/management/PreviewPanel.test.ts(508,757,770,824,856,919)
  TS2353 'available' does not exist in type 'SectionStructuredProjection'   ← 6
src/features/match-preview/BundleGenerationPanel.test.ts(57) TS2339   ← 1
src/lib/api/preview.ts(16,10) TS6133 'previewRequest' 미사용            ← 1
```

직전 라운드에서 보고한 것과 동일하며 이번 변경으로 늘거나 줄지 않았다(8 → 8).
`npm run type-check`(파일 0개 검사)는 근거로 쓰지 않았다.

## 5. 남은 일

- **실제 화면 확인은 root 담당**이다. 이번 검사는 고정 입력 + jsdom이며 브라우저를 열지 않았다.
- root가 이미 기존 API로 배당 재생성을 1회 실행해 `493ef4a9-0e14-4436-8a97-d6de7ce034a7`
  (succeeded/ready/모델 0/`49923b1c`)를 확인했다. 이번 변경은 그 경로를 **화면에서 다시 쓸 수
  있게** 연결한 것이며 **추가 생성을 하지 않았다**(모델·서버·DB·HTTP 호출 0).
- 배당 실제 값 공급과 부상 이름/사진의 저장 payload 반영은 이번 범위 밖이다(각각 PF-B·재생성 판단).
- `PreviewPanel.test.ts`의 기존 타입 오류 6건은 소유 밖이라 고치지 않았다(§4).

## 6. 실행하지 않은 것

전체 빌드·전체 suite·브라우저·모델·DB·서버 제어·실제 HTTP·마이그레이션·커밋 0.
다른 워커나 하위 워커를 만들지 않았다. 임시로 만든 파일은 `/tmp`에만 두었고 저장소에 남기지 않았다.

## 7. 표시 문구 최소 정정 (독립 검토 R-1·R-2·R-3)

독립 검토([pf-reuse-ui-review.md](pf-reuse-ui-review.md))는 차단 0으로 판정하면서, 추가한 문구가
실제 동작과 다른 3건을 참고로 남겼다. 그 3건만 **표시 문구**로 고쳤다. 새 상태·prop·게이트·
로직 리팩터링·API·서버·DB·HTTP·새 테스트는 없다.

| 지적 | 기존 문구 | 정정 |
|---|---|---|
| R-2·R-3 배당 재사용 | "모델 호출 없이(0회) 저장된 채택 배당 줄만 다시 옮깁니다" — 제공자 배당 GET 1회를 0회로 읽히게 함 | "저장된 정보 원문을 재사용하고, 남는 자리가 있으면 **배당 API를 1회 보완**합니다. 모델 호출은 0회입니다" (부모·패널 동일 사실) |
| 배당 새 수집 | 일반 문구 "새 수집은 외부 HTTP 요청과 모델 호출을 새로 발생시킵니다"가 배당에도 노출 | 기존 `workflowId` 분기(`modelFreeSection`)만 써서 배당은 "정보 수집 HTTP와 배당 API 조회를 새로 발생시킵니다. 배당 섹션은 모델을 부르지 않습니다(모델 0회)" |
| 배당 결과 문구 | `no_model_call` 응답에서 `외부 호출 0회`를 그대로 표시 → 제공자 GET 0회 증거가 아님 | 배당은 "모델 호출 없이 처리됐습니다(모델 0회). 배당 조회는 이 응답과 별도로 발생할 수 있으며, 실제 제공자 전송 수는 이 화면에서 확인하지 않습니다" — **숫자를 만들지 않는다**(API 새 필드 없음) |
| R-1 묶음 없음 단정 | "이 실행에는 재사용할 정보 원문 묶음이 없습니다" — 부모의 조회 실패 문구와 상충 | "재사용할 정보 원문 묶음을 **확인하지 못했습니다**" (미확인 표현). 부모의 구체 사유 표시는 그대로 |

바꾼 파일: `PreviewPanel.vue`·`SectionRegenerationPanel.vue`(**문구와 그 문구를 설명하는 주석만**),
`SectionRegenerationPanel.test.ts`(정확 문구를 단언하던 3줄). `PreviewPanel.test.ts`는 문구를
단언하지 않아 **수정하지 않았다**(그 파일의 `it(` 21건 그대로).

```
cd frontend && npx vitest run src/features/match-preview/SectionRegenerationPanel.test.ts
→ Test Files 1 passed (1) / Tests 10 passed (10)
```

지시대로 이 한 파일만 1회 실행했고, typecheck·전체 회귀는 재반복하지 않았다(문구 변경뿐).
`EDITING STOPPED` — 이 표시 정정 이후 추가 후보를 만들지 않는다.

## 8. 정정 2차 — 배당 refresh의 모델 0 전제 철회 (독립 검토 W-2/W-3)

지난 정정(§7)은 "배당은 어느 방식이든 모델 0회"라는 **잘못된 전제**를 깔고 있었다. 새 검토가
그 전제를 반증했다: 배당 **본문 작성**만 모델을 쓰지 않고, 새 수집(refresh)은
`regeneration_discovery_group('section_odds')` → `outlook` 조사 그룹을 실행하며
`discovery.discover_candidates`가 모델을 1회 호출한다(reuse는 조사하지 않으므로 모델 0회).
root의 실제 run `493ef4a9…`도 **reuse**여서 지난 문구가 그 실행에서는 유효했다.

backend 워커가 `run_section_regeneration`의 `expected_model_calls`를 실행 계획 길이로 고쳐
odds refresh 기대 1 / `no_model_call=false`, reuse 0 / true를 돌려주도록 수정 중이며 **호출 자체는
바꾸지 않는다**. 그래서 프론트는 응답 값을 따르게만 고쳤다.

| 항목 | 정정 |
|---|---|
| 배당 refresh 문구 | "배당 섹션은 모델을 부르지 않습니다(모델 0회)" 삭제. "새 수집은 **자료 검색 모델 호출**과 외부 API 조회(배당 포함)를 새로 발생시킵니다. 배당 본문 작성 자체는 모델을 쓰지 않지만, 조사 단계의 모델 호출은 발생합니다" |
| 배당 reuse 문구 | 유지: 저장된 정보 원문 재사용 + 필요 시 배당 API 1회 보완, **이 재사용 경로는** 모델 0회(방식 한정 표현으로 축소) |
| 결과 문구 | `section_id`로 모델 0을 단정하지 않고 **응답 `no_model_call`·실제 모델 전송 값**을 따른다. `external_calls`는 `budget.model_used`(모델 전송 수)이므로 "외부 호출"이 아니라 **"모델 전송 n회"**로 적고, 배당 API 전체 전송 수로 표현하지 않는다. 숫자는 응답 값만 쓰고 새로 추정하지 않는다 |
| 부모 힌트 | 사용자가 고른 동작을 알 수 없으므로 모델 0회를 단정하지 않고 reuse/refresh 두 경우를 함께 적는다(§2-2의 "배당은 모델을 안 부른다" 주석도 정정) |
| 내부 이름/주석 | `modelFreeSection` → `oddsSection`(이름이 '모델 안 부름'을 함의해 오해를 만들었다). 로직·prop·상태 변경 없음 |

**검사** — `SectionRegenerationPanel.test.ts` 한 파일만 1회 실행, 대표 2건으로 고정:

| 검사 | 확인 |
|---|---|
| odds **reuse** `no_model_call=true`, `external_calls=0` | "모델 호출 없이 처리됐습니다" + "모델 전송 0회" |
| odds **refresh** `no_model_call=false`, `external_calls=1` | 모델 0회 문구 **없음** + "모델 전송 1회" |

```
cd frontend && npx vitest run src/features/match-preview/SectionRegenerationPanel.test.ts
→ Test Files 1 passed (1) / Tests 13 passed (13)
```

`PreviewPanel.test.ts`는 문구를 단언하지 않아 수정하지 않았다. 새 prop·상태·설정·API·HTTP·
서버·DB·브라우저·모델 호출·전체 생성 없음. typecheck·전체 회귀는 재반복하지 않았다.
이 문제가 두 번째 확인이므로 추가 가정으로 확장하지 않는다.

`EDITING STOPPED`
