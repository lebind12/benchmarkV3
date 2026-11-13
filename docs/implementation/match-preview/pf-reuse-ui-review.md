# PF-REUSE 프론트 연결 — 독립 검토 (읽기 전용)

검토: 2026-11-12 KST. DeepSeek 검토 워커(Orca `dsh-tui`, 실제 모델
`deepseek-ai/deepseek-v4.1-flash-1017`, 추론 강도 Max 유지).
입력: `docs/implementation/match-preview/pf-reuse-ui-report.md`(구현자 EDITING STOPPED 인계).
검토 범위(4파일, 추가 편집 0):
`frontend/src/components/management/PreviewPanel.vue` + `PreviewPanel.test.ts`,
`frontend/src/features/match-preview/SectionRegenerationPanel.vue` + `SectionRegenerationPanel.test.ts`.
`lib/api/preview.ts`는 별도 후속 진행 중이라 **검토 제외**.

검토 시점 고지: 검토 중 `PreviewPanel.vue`(21:56)·`PreviewPanel.test.ts`(21:57)가 **다른 작업자에 의해**
갱신된 흔적이 있어(인계 시각 21:49 이후), 최종 확인은 22:0x 시점 파일 내용을 기준으로 다시 대조했다.
수용 기준에 해당하는 배선(`:bundle-id` 766행, `:selected-result-ids` 767행, `@regenerated` 771행,
bundleSequence 238/244/251행)과 테스트 수(PreviewPanel 21·Panel 10)는 그 시점에도 **동일**했다.
내가 편집한 파일은 이 보고서 하나뿐이다.

검토 방식: 소스 정독 + 보고서 주장 대조. `pytest`/`vitest`/`typecheck` **재실행 0**,
브라우저·서버·DB·HTTP·모델 **0**. 새 테스트·재현 스크립트 **작성 0**.

## 1. 차단 여부 — 프론트 수용기준 기준 차단 0, backend 소유 차단 후보 1(W-3)

수용 기준 4개 조건 모두 코드에서 **실제로 충족**됨을 확인했다(원 지시 기준 재현된 수용 위반 **0건**).

다만 root의 21:52 실제 화면 지적을 반영해 odds 문구를 다시 대조한 결과 **1건이 차단 후보**로 올라온다:
**W-3** — `section_odds` + `source_mode='refresh'`에서 backend가 `expected_model_calls=0`을 고정 반환해
`no_model_call=true`로 내려가지만, refresh는 조사 모델을 **실제 1회** 호출한다(아래 §3-1).
이 값이 화면의 모델 0회 문구 근거이므로 **프론트 4파일 범위 밖(backend) 수정**이 필요하다.

나머지 참고(R-1 문구 상충, W-1·W-2 문구 정확도)는 재사용 동작·데이터 정합성을 깨지 않는다.

## 2. 수용 기준별 확인 근거

| 수용 기준 | 확인한 코드 | 판정 |
|---|---|---|
| 패널을 **펼칠 때만** 기존 `informationBundle` 조회 → `parseInformationBundle` → `bundleId` 전달 | `toggleRegeneration`(263행, `@toggle`는 714행)이 `open`일 때만 `loadBundleForRegeneration` 호출, 접힘에서 `return`. `loadBundleForRegeneration`(240행)이 `previewRunsApi.informationBundle(runId)` → `parsed.bundleId` → `bundleId.value`. 템플릿 766행 `:bundle-id="bundleId"` | 충족 |
| 오류를 "묶음 없음"으로 숨기지 않음 | 252~256행: `!response.ok` → `bundleStatus='error'`, `bundleError=response.message`. 템플릿 752~760행이 `preview-regeneration-bundle-error`(757행)로 "묶음 없음이 아닙니다" + 사유 표시 | 충족 |
| 낡은 run 응답으로 잘못 재사용 금지 | 244행 `sequence = ++bundleSequence`, 251행 `disposed \|\| sequence !== bundleSequence \|\| openRunId.value !== runId` 이면 폐기. `openStoredRun`(369~373행)과 `clearResultState`(306~313행)가 `bundleLookupRunId/bundleStatus/bundleId/bundleError/regeneratedRunId` 초기화 | 충족 |
| 기존 `mode:'live'`/`base_run_id`/`base_result_id`/`source_mode:'reuse'`/`bundle_id` 보존 | `SectionRegenerationPanel.regenerate`(168~189행): `mode:'live'` 고정(172행), `base.run_id`/`base.section_result_id`(177~180행), `reuse`일 때만 `bundle_id`(181~183행) | 충족 |
| 화면이 보는 **다른 섹션 선택 버전 ID** 전달 | `otherSectionResultIds`(174~189행): `previewView.sections[].version`과 같은 `version`의 `storedSections` 행에서 `section_result_id`를 고르고, **재생성 대상 섹션은 제외**. 패널은 186~189행에서 자기 `base.section_result_id`를 한 번 더 제외하고 `selected_result_ids`로 전송 | 충족 |
| 성공 새 run 열기 버튼 | `@regenerated="onSectionRegenerated"`(771행) → `regeneratedRunId`, 템플릿 773~790행 버튼 `preview-regeneration-open`(783행) → `openRegeneratedRun` → 기존 `openStoredRun`. **자동 열기 없음** | 충족 |
| odds 모델 0 문구 | 부모 725~730행과 패널 296~298행이 `workflowId === 'section_odds'`에서만 "모델 호출 없이(0회)" 표시. 서버 `_SECTION_MODEL_CALLS['section_odds'] == 0`과 일치 | 충족 |
| 원 run/구성본 무변경, 자동 생성 0 | 부모는 `informationBundle`(GET)·`readerPreview`(GET)·`sectionResults`(GET)·`detail`(GET)만 호출. `runBundle`/`createMockDemo`/승인 호출 **없음**. 재생성은 패널 사용자 클릭에서만 `regenerateSection` 1회 | 충족 |

## 3. 참고 (차단 아님, 이번 검토에서 고치지 않음)

**R-1. 묶음 조회 실패 시 같은 화면에 상충하는 두 문구가 함께 보인다.**
부모는 752~760행에서 "읽지 못했습니다(묶음 없음이 아닙니다)"를 띄우지만, `SectionRegenerationPanel`은
`v-if="selectedSectionId"`(762행)로 **그대로 마운트**되고 `bundleId=null`이므로 패널 내부 300행(`reuseAvailable`은 92행에서 `Boolean(props.bundleId)`)의
`regen-reuse-blocked`가 "이 실행에는 재사용할 정보 원문 묶음이 없습니다"를 동시에 보여준다.
즉 구현자가 명시한 "조회 실패를 묶음 없음으로 숨기지 않는다"는 **부모 수준에서는 지켜지지만**,
패널 문구는 여전히 "묶음 없음"이라고 단정한다. 재사용 버튼은 비활성이라 **잘못된 재사용은 발생하지 않는다**
(동작 결함 아님). 실패 시 패널에 "조회 실패"를 구분해 전달하거나 패널을 숨기는 것이 후속 후보.

### 3-1. odds 문구 3건 (root 21:52 실제 화면 지적 반영, 재검토 시점 22:1x)

root가 21:52 실제 화면에서 저장묶음 연결·재생성 버튼 활성을 확인했고(추가 생성 0), 그 화면의
배당 문구가 backend 동작과 어긋남을 지적했다. 검토 시점(22:1x) 파일을 다시 대조한 결과,
**당시 문구는 이미 다른 작업자에 의해 갱신되어 있었고**, 갱신된 문구 기준으로 3건을 판정한다.

**W-1 (수용기준 위반 → 이미 해소됨).** 지적 당시 재사용 문구는
"배당은 모델 호출 없이(0회) **저장된 채택 배당 줄만 다시 옮깁니다**"였다.
backend `run_section_regeneration`(2392~2403행)은 `has_remaining_slots`면 `_provider_odds_for`로
**API-Football `/odds`를 1회 조회**한다. 즉 "저장값만 변환"은 사실과 달랐다 — root 지적이 정확했다.
현재 파일(314~318행)은 "저장된 정보 원문을 재사용하고, 남는 자리가 있으면 **배당 API를 1회
보완합니다. 모델 호출은 0회입니다.**"로 바뀌어 **모델 0회와 새 배당 조회 가능을 구분**한다.
→ 판정: **해소**. 다만 이 갱신은 인계(21:49) 이후 시각(22:11)에 이뤄졌으므로 **인계 보고서의 문구와
현재 파일이 다르다**(보고서 §2-1의 "저장된 채택 배당 줄만" 서술은 현재 코드와 불일치).

**W-2 (신규 확인, 차단 아님 / 문구 정확도).** 현재 배당 **새 수집(refresh)** 문구(96~104행)는
"배당 섹션은 모델을 부르지 않습니다(모델 0회)"라고 단정한다. 그러나 refresh는
`regeneration_discovery_group('section_odds')` → `outlook` 조사 그룹을 실행하고
(`bundle_pipeline` 2253~2281행), `discovery.discover_candidates`가 `request_model`을 **1회** 부른다
(`discovery.py` 789·809행). 즉 **배당 reuse는 모델 0회가 맞지만 refresh는 모델 1회**다.
근거: `regeneration_logical_call_ids('section_odds', source_mode='refresh')` → `('discovery_outlook',)`.

**W-3 (backend 표시 결함, 화면 문구의 신뢰 근거를 흔든다).** 위와 같은 이유로 odds+refresh에서
backend는 `expected_model_calls=(0 if section_odds else 1)`(2547행) 때문에 여전히 **0**을 돌려주고,
`preview_admin` 899행이 `no_model_call = expected_model_calls == 0` → **true**로 내려준다.
`external_calls`는 `budget.model_used`(2546행)이므로 실제 1이 찍힌다. 화면은 `no_model_call=true`를
먼저 보므로(W-2 문구와 결합) **모델을 1회 불렀는데 "모델 0회"로 표시**된다.
→ 판정: **backend 소유 결함**(프론트 문구만으로 고칠 수 없음). 이번 검토 범위(frontend 4파일) 밖이며,
`bundle_pipeline`의 `expected_model_calls`를 refresh에서 실제 참여 모듈 수로 계산하도록 고치는 것이
최소 해결 범위다. **root 판단 필요** — 사용자가 배당 "재생성"으로 실제 모델 호출·과금이 발생하는지에
직결되므로 차단 후보로 올린다.

**R-3 (유지).** 부모 머리 문구는 배당에서 제공자 배당 읽기 가능성을 함께 알리도록 갱신되어 있다
(718~730행, "남는 자리가 있으면 배당 API를 1회 보완 … 실제 제공자 전송 수는 이 화면에서 확인하지
않습니다"). 사실과 일치하나, **W-3이 해소되기 전에는 reuse에만 맞는 서술**이다(refresh는 모델 1회).

## 4. 보고서 주장 대조 (재실행 없이 파일로 확인)

| 구현자 주장 | 파일 사실 | 판정 |
|---|---|---|
| 대표 31검사(PreviewPanel 21 + Panel 10) | `PreviewPanel.test.ts` `it(` **21**개, `SectionRegenerationPanel.test.ts` **10**개 | 일치 |
| 신규 컴포넌트 타입 오류 0 | 두 `.vue`에서 새 prop(`bundleId`/`selectedResultIds`)은 `withDefaults`(56행)에 선언, emit 타입(59~63행)에 `SectionRunResponse` 사용. 새 대입에서 타입 위반 없음 | 일치 |
| 기존 8오류(`PreviewPanel.test.ts` 6, `BundleGenerationPanel.test.ts` 1, `preview.ts` 1) | `SectionStructuredProjection`(types.ts 432행)에 `available` 필드 **없음** → 테스트 리터럴의 `available: true`가 초과 속성. `preview.ts` 16행 `previewRequest`는 import만 있고 사용 없음 | 일치(기존) |
| `types.ts` 이번 라운드 미수정 | `SectionRegenerationRequest`에 `selected_result_ids`가 이미 정의됨(types.ts 721행 주석) | 일치 |
| 회귀 감지력(전달 제거 시 4 실패) | `:bundle-id`/`:selected-result-ids`/payload 줄이 실제로 존재하며, 이를 지우면 새 검사 4건이 깨지는 구성 | 일치 |

보고서와 코드 사이에 **모순은 발견되지 않았다**.

## 5. 결론

- **프론트 4파일 수용 기준: 차단 0건.** 펼칠 때만 조회·오류 구분·낡은 run 방지·payload 보존·
  선택 ID 전달·새 run 열기·배당 reuse 모델 0회 문구를 코드가 충족한다.
- **차단 후보 1건(W-3)**: `section_odds`+`refresh`에서 backend `expected_model_calls`가 0으로
  고정되어 `no_model_call=true`가 내려오지만 조사 모델이 실제 1회 호출된다. 화면이 그 값을 그대로
  믿으므로 **backend(`bundle_pipeline`) 수정**이 최소 해결이며, 이번 검토 범위 밖이다.
- 참고(R-1 문구 상충, W-1 해소, W-2 refresh 문구)는 **후속 후보**이며 reuse 연결을 막지 않는다.
- 구현자 보고의 31검사·타입오류 8건 근거는 파일 사실과 일치하므로 **검사 재실행 없이** 그 근거를 인용했다.
- 이 검토에서 제품·테스트·설정 파일을 **수정하지 않았다**(읽기 전용).

EDITING STOPPED
