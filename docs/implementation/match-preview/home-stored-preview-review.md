# 홈 최신 저장 프리뷰 독립 검토 (HP-REVIEW)

작성: DeepSeek 검토 워커(읽기 전용), 2026-11-13 01:49 KST.
대상: `app/services/home_preview_document.py`, `app/api/v1/home_preview.py`, `frontend/src/lib/api/homePreviewDocument.ts`, `frontend/src/lib/api/homePreview.ts`, `frontend/src/components/home-preview/HomeRecommendedSection.vue`, `frontend/src/styles/home-preview.css` 및 대응 직접 검사.
입력: `2026-11-13-home-stored-preview.md`, `2026-11-13-home-stored-preview-acceptance.md`, `2026-11-13-home-stored-preview-design.md`, `home-stored-preview-report.md`, `home-stored-preview-browser-evidence.md`.

throughput checkpoint: n/a, read-only investigation

## 목표와 이번 검토의 최소 기대

사용자 목표는 홈에서 고른 추천 경기의 **최신 저장 프리뷰 문서**를 별도 조작 없이 보고, 문서가 없으면 기존 6시간 안내를 구간에 맞게 보는 것이다. 이 검토는 그 연결이 요구한 다섯 경계를 지키는지, 구현 보고의 실행 근거가 실제로 재현되는지 대조한다. 쓰기·생성·승인 변경 없이 읽기만 했고, 제품·검사·도구 코드는 한 줄도 고치지 않았다.

## 실행 모델과 스킬 읽기 근거

- 모델: 이 세션은 `deepseek-ai/deepseek-v4.1-flash-1017`로 실행됐다. 프로필 `~/.dsh/profiles/desktop/cordis.patch.yml`의 `agent-default-model`이 `provider: hive`, `model: deepseek-ai/deepseek-v4.1-flash-1017`임을 직접 확인했다. 추론 강도는 그 프로필 파일에 값이 없어 세션 기본 설정을 그대로 따랐다(추정하지 않는다).
- 스킬: `/Users/woolee/benchmark/.agents/skills/poteto-mode/SKILL.md` 전문(162줄)을 작업 전에 읽었다. 이번 작업은 결과가 인용 있는 답인 읽기 전용 검토이므로 Investigation 플레이북을 적용했다.
- 원칙 leaf: `principle-prove-it-works/SKILL.md`, `principle-test-behavior-not-implementation/SKILL.md`를 직접 읽었다. 선언만 하고 leaf를 읽지 않은 원칙은 근거로 쓰지 않았다.

## 핵심 판정

**조건부 수용, 지적 2건은 수정 확인됨.** 조정자가 수용한 구현 선택(새 `/document`가 홈의 단일 소스, 기존 prematch는 잔존)은 실제 코드와 일치한다. 요구한 다섯 경계 중 넷은 코드와 재현 실행으로 확인됐다. 이 검토에서 **현재 요구 위반 1건**을 합성 입력으로 재현하고 **지연 응답 검사 근거 누락 1건**을 지적했으며, 두 건 모두 이후 구현 워커가 같은 파일에서 고쳤고 이 검토자가 현재 코드로 재확인했다(아래 "수정 확인"). 구현 보고의 수치(13/26/vue-tsc 8)는 전부 재현됐고, 미확인 승인 기록은 조정자의 실제 조회로 해소됐다. 기존 e2e 두 파일은 옛 prematch DOM을 단언해 새 홈과 맞지 않으며, 이는 제품 회귀가 아니라 과거 계약 단언 교체다(실행하지 않고 정적 대조).

| 구분 | 건수 | 성격 |
|---|---|---|
| 현재 요구 위반 (합성 재현) → 수정 확인 | 1 | 구성본이 고른 행이 공개 불가일 때 다른 버전으로 대체. 현재는 대체하지 않음 |
| 근거 누락 (수용 기준 배정 검사) → 수정 확인 | 1 | 경기 전환 지연 응답 대표 사례. 검사 1건 추가됨 |
| 기존 e2e 계약 갱신 필요 (미실행, 정적 대조) | 2 파일 | `home-preview-live.spec.ts`·`home-preview-l3.spec.ts`가 옛 prematch DOM 단언. 제품 회귀 아님 |
| 참고 개선 | 5 | 공개 화이트리스트 키, replay 경계, reveal 첫 프레임, 요청별 엔진 생성, 실행 조회 상한 |
| 참고 후속 (범위 외) | 2 | 옛 preview 메타데이터 연결 분리, `getHomePreview` 잔존 |

## 수정 확인 (2026-11-13 01:53~58 재검토)

지적 1·2만 확인했고 다른 경계를 다시 심사하지 않았다.

**지적 1 — 구성본 대체.** `_chosen_rows`(`app/services/home_preview_document.py:117-160`)가 `claimed` 집합을 새로 두고, 구성본이 지목한 워크플로우는 공개 불가여도 아래 채우기 대상에서 제외한다. docstring도 "공개 불가여도 `claimed`에 남겨 채우기 대상에서 제외한다"로 실제 코드와 맞춰졌다. 재현 결과가 바뀌었다.

```text
수정 전: 선택 ["a2"](미승인) → chosen rows = ["a1"], body = "승인 본문"
수정 후: 선택 ["a2"](미승인) → chosen = None (섹션 제외, 문서 없음)
        선택 ["a1"](승인)   → chosen rows = ["a1"], body = "관리자가 고른 본문"
```

정상 선택은 그대로 유지되므로 과잉 수정이 아니다. 회귀 검사 `test_unpublishable_composition_choice_is_dropped_not_replaced`(위치 `tests/unit/test_home_preview_document.py:104`)가 두 방향을 함께 고정한다. 부작용으로, 승인되지 않은 선택만 있는 실행은 `status=none`이 되지만 같은 실행의 승인된 다른 섹션은 여전히 채워지므로 문서 전체가 사라지지는 않는다.

**지적 2 — 지연 응답 검사.** `HomeRecommendedSection.test.ts:200`에 `keeps the newly selected fixture body when the previous response arrives late`가 추가됐다. 첫 경기 응답 promise를 붙잡아 두고 둘째 경기로 전환한 뒤 늦게 resolve해, 본문이 둘째 경기 것으로 남고 `data-fixture-id`가 `90002`인지 확인한다. 실제 사용자가 관찰하는 값만 단언하므로 구현 세부에 고정되지 않았다(`principle-test-behavior-not-implementation`). 컴포넌트의 순번·fixture 일치 가드(`:74`)는 그대로다.

**재실행 근거.** backend `tests/unit/test_home_preview_document.py` → **14 passed**(13 + 신규 1). frontend 직접 4파일 → **27 passed**(26 + 신규 1). 두 수치 모두 이 수정 확인 시점의 현재 코드 기준이다.

**검사가 실제로 결함을 잡는지 확인.** 새 검사가 구현을 그대로 반복하는 빈 검사가 아님을 두 방향으로 확인했다(파일 편집 없이 프로세스 안에서만 옛 동작을 흉내 냄).

```text
현재 코드               → 선택 a2(미승인) 결과 None
옛 _chosen_rows로 교체  → 같은 입력에서 "승인 본문" (지적했던 그 결함)
_displayable을 느슨하게 → 대체 후보가 "미승인" 본문으로 바뀜
```

즉 새 검사는 지적 1의 정확한 동작을 고정하고 있고, 승인 조건을 무력화하는 변경도 잡는다. 검토 세션은 이 확인을 위해 제품 파일을 수정하지 않았다. 옛 동작은 메모리 안의 함수 교체로만 재현하고 원복했다.



## 경계별 대조

### 1. 해당 외부 경기의 최신 문서 저장시각

통과. `_read_runs`가 `PreviewRun.fixture_id == external_id`로 실행을 모은다. 이 열은 `FixtureIdentity.fixture_id`(API-Football 외부 경기 ID, `app/preview/contracts.py:260`)에서 온다. 최신 기준은 `_saved_at`이 고른 섹션 행의 `created_at` 최댓값이며 요청 시각이나 킥오프가 아니다(`home_preview_document.py:159-178`). 동률은 `(saved_at, run_id)` 키로 결정되고 입력 순서를 바꿔도 같은 실행이 선택됐다(직접 실행 확인).

### 2. 구성본의 정확한 선택 결과(타 실행 포함)

**검토 시점 위반 1건, 수정 확인.** 타 실행 선택은 정상 동작한다. 저장 구성본의 결과 ID를 `get_section_result_any_run`으로 읽어 자기 실행 밖 행까지 합치고, 그 본문이 실제 공개 응답에 들어가는 것을 세션 스텁으로 재현했다(players는 타 실행 행, forecast는 현재 실행 행). 문제는 선택 행이 공개 불가일 때였다. 당시 위치는 `_chosen_rows`이고, 선택 행이 미승인·본문 없음이면 `continue`로 건너뛴 뒤 두 번째 루프가 그 워크플로우를 **최신 공개 가능 행으로 채웠다**. 함수 docstring은 "그 섹션을 빼고 다음 버전을 대신 넣지 않는다"고 적었지만 코드는 대신 넣었다.

재현(합성 입력, `select_document` 공개 함수, 검토 시점 코드):

```text
승인: section_players → {v1}
행:  a1(v1, 승인, "승인 본문"), a2(v2, 미승인, "미승인 새 본문")
구성본 선택: ["a2"]
당시 결과: chosen rows = ["a1"], body = "승인 본문"
현재 결과: chosen = None (섹션 제외)
```

사용자 영향은 승인 기록이 아니라 관리자 조합과의 불일치다. 관리자가 구성본으로 저장한 버전 대신 그 실행의 다른 버전 본문이 홈에 나간다. 수용 기준 DOC-PRESENT의 "관리자에서 확인했던 동일 결과와 일치"와 설계 2항("섹션을 각자 최신으로 바꿔 관리자가 저장한 조합과 달라지게 하지 않는다")에 어긋난다. 승인되지 않은 본문이 공개되는 것은 아니며, 대체 후보도 `_displayable`을 통과한 행이므로 누출은 없었다.

수정은 `_chosen_rows` 한 함수에서 이뤄졌다. 선택 ID가 있는 워크플로우를 `claimed` 집합에 먼저 기록하고 두 번째 루프에서 그 워크플로우를 채우지 않는다. 호출부는 바뀌지 않았다. 승인된 선택은 그대로 쓰이므로 과잉 수정이 아니다.

현재 승인 표가 비어 있어(`approved=[]`) 실제 홈에서는 발현되지 않는다. 그래서 조정자의 지금 실제 화면 작업을 막지 않는다.

### 3. 본문 없는 실행 건너뛰기

통과. 표시 가능한 행이 하나도 없는 실행은 후보에서 빠진다(`select_document:196-198`). 검사 `test_run_without_body_never_shadows_previous_document`가 이 동작을 고정하고, 직접 실행에서 통과했다.

### 4. 실제·승인된 버전만 공개

통과. `_displayable`이 본문 유무, `mode == "mock"` 제외, 워크플로우 버전의 활성 승인 포함을 차례로 확인한다(`:100-114`). 승인 표가 비면 어떤 문서도 `status=none / no_approved_version`으로 나간다. 조정자가 실제 조회로 확인한 `1557474 → none / no_approved_version`과 코드가 일치한다. 승인 POST나 DB 변경으로 우회한 흔적은 없다.

### 5. GET 무쓰기·외부 무호출·공개 화이트리스트

통과. 문서 경로(`app/services/home_preview_document.py`, `app/api/v1/home_preview.py`)에 `session.add/delete/flush/commit`이 없고 `requests/httpx/urllib/aiohttp` 호출도 없다. `_id_context`는 표시 이름 파사드를 통해 같은 DB를 읽기 전용으로 한 번 더 읽는다. 외부 HTTP 호출이 아니며 SELECT만 수행한다(`DbNameLookup._rows`).

공개 응답은 명시적으로 필드를 골라 만든다(`project_document:313-324`). `structured`는 `_public_row`가 화이트리스트로 줄이고 내부 기본키 `player_id`/`team_id`를 뺀다. 검사 `test_projection_drops_internal_primary_keys_from_structured_values`와 `test_projection_carries_reader_fields_and_no_internal_diagnostics`가 이 경계를 고정한다. 진단 문자열과 내부 실행 ID가 직렬화 결과에 없다는 것도 검사가 확인한다.

### 6. 프론트 공개 응답 경계와 본문 연결

통과. `homePreviewDocumentSchema`가 `status`를 `available|none`으로 좁히고, available은 섹션·저장시각·run_id를 요구하며 none은 섹션·시각·run을 금지한다. 경기 ID 교차도 막는다. `toStoredPreviewView`는 기존 `toMatchPreviewView`를 그대로 재사용해 두 번째 본문 규칙을 만들지 않았다. 내부 팀·리그 ID를 지어내지 않고 타입 경계에서만 맞춘다.

### 7. 첫 진입 자동 표시·경기 전환·오류 구분·없음 단일 안내

통과. `HomeRecommendedSection.vue:62-86`이 경기 선택이 정해지는 즉시 문서를 요청하고, 새 요청마다 앞 본문을 먼저 비운 뒤 순번(`documentId`)과 `fixture_id` 일치를 함께 확인해 늦은 응답을 버린다. 없음은 안내 컴포넌트 하나이고 다시 확인 버튼이 없으며, 오류만 별도 상태로 재확인을 제공한다. 조정자가 실제 홈에서 안내 1개·버튼 0개·본문 0개를 관측한 기록과 일치한다.

### 8. 없음 구간 문구와 6시간 경계

통과. `absence_notice`가 `past`(남은 시간 ≤ 0), `upcoming_overdue`(0 < 남은 ≤ 6h), `upcoming`(6h 초과)을 서버에서 한 값으로 정한다(`:327-358`). 고정 시각 검사가 6시간 정확·6시간 1초·1분·킥오프 정확·1시간 경과를 모두 덮는다(`tests/unit/test_home_preview_document.py:301-316`). 화면은 시계 비교를 다시 하지 않고 문구만 고른다. 수용 기준의 최소 해석(정확히 6시간은 문제 안내, 정확히 킥오프부터 past)과 같다.

세 state가 실제 서버 응답에서 모두 나왔다는 근거도 있다. `_fixture_display`가 `fixture.kickoff_at.isoformat()`을 `empty_document`의 `fixture`로 넘기고, `now`는 `utcnow()`이므로 이 값으로 세 분기가 실데이터에서 계산된다. 조정자의 실제 조회 세 건이 그 결과다. `upcoming`(1557474, 미래 6시간 초과), `past`(1557445, 과거), `upcoming`(1557470, 미래)이 모두 `empty_document` 경로로 나왔고 각 응답의 `absence.state`가 그 값과 일치한다. `upcoming_overdue`만 실제 사례가 없어 고정 시각 검사로만 확인됐다(수용 기준이 허용한 구분).

### 9. 섹션별 reveal과 되흐림 방지, 공통 디자인 보존

통과. `updateReveals`가 홈 컨테이너 안의 `.hp-stored-document .mpv-section`을 기존 대상에 더하고 `--reveal`은 최댓값으로 누적한다. 규칙은 `home-preview.css:230-232`에만 추가됐고 `MatchPreviewBody.vue`와 `body.css`는 변경 목록에 없다(직접 확인). reduced-motion에서는 즉시 선명하다.

## 보고 주장 대조

| 보고 주장 | 대조 결과 |
|---|---|
| backend 직접 검사 13 passed | 재현. 13 passed (0.21s) |
| frontend 직접 4파일 26 passed | 재현. 7+4+10+5 = 26 passed |
| vue-tsc 신규 0, 기존 8건 | 재현. 8건 모두 `PreviewPanel.test.ts`(6), `BundleGenerationPanel.test.ts`(1), `preview.ts`(1). 세 파일 모두 HEAD에 없는 작업트리 산출물이며 이번 변경 파일이 아니다 |
| `publication.spec.ts` 2건은 기존 환경 실패 | 재현. 두 검사 모두 `TypeError: resolve is not a function`. 파일도 무변경 |
| 합산 47건 표기 정정 | 정정 내용이 타당하다. 서로 다른 실행 수를 더한 값임을 스스로 밝혔다 |
| 홈 소비자가 옛 preview 메타데이터를 읽지 않는다 | 사실이다. `HomeRecommendedSection.vue`에 `items[].preview`를 읽는 코드가 없고, 추천을 쓰는 다른 홈 소비자도 없다 |
| 승인 기록을 조회하지 못했다 | 구현자 환경 한정 사실. 조정자의 실제 approvals GET(`approved=[]`)과 실제 `/document` 응답이 이 미확인을 해소했다 |

## 지적 목록

### 요구 위반 — 수정 확인됨

1. `app/services/home_preview_document.py:117-160` `_chosen_rows`. [검토 시점] 구성본이 고른 행이 공개 불가면 같은 워크플로우의 다른 버전이 대신 공개됐다. 영향은 관리자 저장 조합과 홈 본문의 불일치이며 미승인 본문 누출은 아니었다. [현재] `claimed` 집합으로 선택 워크플로우를 채우기 대상에서 제외해 대체가 사라졌고, docstring도 코드와 맞춰졌다. 회귀 검사 `test_unpublishable_composition_choice_is_dropped_not_replaced`가 추가됐고, 이 검사가 결함을 실제로 잡는 것을 mutation 확인으로 검증했다(위 "수정 확인").

### 근거 누락 — 수정 확인됨

2. 경기 전환 지연 응답 대표 사례. [검토 시점] `acceptance.md` SELECT 행은 "응답 지연 대표 사례는 단위 검사"로 정했는데, 추천 항목이 1건뿐이라 전환 자체를 만들지 못했고 순번·fixture 가드를 고정하는 검사가 없었다. [현재] `HomeRecommendedSection.test.ts:200`에 두 경기 추천·붙잡아 둔 첫 응답·늦은 resolve 사례가 추가됐다. 사용자 관찰 값(남은 본문, `data-fixture-id`)만 단언한다.

### 참고 개선 (차단 아님)

3. `home_preview_document.py:263-265` 미디어 화이트리스트 키 불일치. 백엔드 `_media`는 `predictedScore`·`publishedAt`(camelCase)를 만들지만 공개 화이트리스트는 `predicted_score`·`published_at`(snake)만 남긴다. 직접 실행으로 두 값이 응답에서 빠지는 것을 확인했다. 홈 `MatchPreviewBody`는 이 두 필드를 그리지 않으므로 현재 사용자 표시 영향은 없다. 관리자 `SectionStructuredView`는 원본 payload를 읽어 영향이 없다.
4. `home_preview_document.py:60` 모의 제외 상수가 `mock` 하나다. `RunMode.REPLAY`(저장 응답 재생)는 승인되면 공개될 수 있다. 승인 모듈도 mock만 거부하므로 이는 기존 승인 정책의 경계이고 이번 변경이 만든 문제가 아니다. "모의·시험 제외" 요구를 replay까지 볼지는 조정자 판단 대상이다.
5. `home-preview.css:230`과 `HomeRecommendedSection.vue:120-133` reveal 첫 프레임. CSS 기본값이 `var(--reveal, 1)`이라 본문이 붙은 직후 한 프레임은 선명하게 그려진 뒤 흐림에서 다시 밝아질 수 있다. 실화면 SCROLL 확인 때 이 깜빡임을 함께 보면 된다. 최소 수정은 래퍼 규칙에 `--reveal: 0` 기본값을 두는 한 줄이다.
6. `home_preview_document.py:516-524` 요청마다 표시 이름용 엔진을 새로 만든다. `open_display_names`가 `DbNameLookup.from_url`로 엔진을 만들고 요청 끝에 `dispose`하므로 공개 GET마다 연결을 새로 연다. 현재 수용 기준 위반은 아니고 비용 항목이다.
7. `home_preview_document.py:406-414` 실행 조회 상한 50. 한 경기에 본문 없는 실행이 50건 넘게 쌓이면 그 뒤의 이전 승인 문서를 놓친다. 현재 데이터 규모에서는 발생하지 않는다.

### 참고 후속 (이번 범위 밖)

8. 옛 preview 메타데이터 연결. 추천 응답의 `items[].preview`는 여전히 옛 publication 저장소를 보고, `homeRecommendationsSchema`의 `superRefine`이 그 값을 계속 검증한다. 홈 컴포넌트는 읽지 않으므로 사용자 표시 영향은 없지만, 옛 메타데이터가 계약을 위반하면 추천 응답 전체가 실패해 홈이 "추천 경기를 불러오지 못했습니다"가 될 수 있다. 실제 사용자 표시 영향이 확인되지 않았으므로 보고서가 제안한 대로 별도 후속으로 분리하는 것이 맞다.
9. `getHomePreview`(prematch 클라이언트)는 이제 홈에서 호출되지 않고 남아 있다. 계획이 "다른 용도 삭제는 범위 밖"으로 정했으므로 그대로 둔 판단이 타당하다.

## 기존 e2e 계약 영향 (정적 대조, 미실행)

`frontend/e2e/home-preview-live.spec.ts`(288줄, tracked, 변경 없음)는 `**/api/v1/home/**`를 가로채 `/prematch` 응답만 채운다. 새 홈은 `/recommendations`와 `/fixtures/{id}/document`만 호출하므로 이 파일에서 `/document` 요청은 마지막 분기 `{ items: [], rows: [] }`로 떨어진다. 그 값은 `homePreviewDocumentSchema`를 통과하지 못해 클라이언트가 예외를 던지고 화면은 조회 실패 상태가 된다. 그래서 문서 있음 단언(`.hp-lead`, `.hp-prediction`, `preview-sources`, `key-absence`, `player-watchpoint`, `all-injuries`, `#preview-odds`, `preview-generation-time`)이 모두 실패한다. 브라우저 실행은 금지 범위라 실행하지 않았고, 이 판정은 라우트 분기와 스키마 조건을 정적으로 대조한 것이다(추정이 아니라 코드 대조).

**실제 제품 회귀가 아니라 과거 계약 단언 교체다.** 홈 화면 자체는 정상 동작하며, 단언이 옛 prematch 기반 DOM을 가리키기 때문이다. 다만 그 안에 표시 내용의 실제 감소가 하나 섞여 있다.

- 이름만 바뀐 경우: `.hp-lead`·`.hp-prediction`·`#preview-odds`는 같은 정보가 `MatchPreviewBody`의 `mpv-lead`·`mpv-prediction`·`mpv-odds`로 렌더된다.
- 실제 표시 내용 감소: 옛 홈이 옛 prematch 응답에서 그리던 **최근 5경기 표(`.hp-form`)**, **출처·자료 시점 접기(`.hp-sources`)**, **주목 선수·부상 요약(`HomePlayerWatchpoints`·`HomeInjurySummary`)**, **자료 확인 현황(`data-gap-summary`)** 은 저장 문서에 대응 데이터가 없어 새 홈에 자리가 없다. 세 컴포넌트는 `HomePreviewMockView`와 `HomeSingleCallReviewView`에만 남아 있다(직접 확인). 이것은 새 연결의 결함이 아니라 조정자가 수용한 "저장 문서 단일 소스" 선택의 결과다. 수용 기준 DOC-PRESENT의 열거 항목(본문·예상 점수·선수/부상 사진·팀 로고·매체·배당)에는 이 셋이 없어 현재 요구 위반은 아니지만, 사용자가 이전 화면과 비교하면 최근 5경기 표와 출처 접기가 사라진 것을 보게 된다. 이 감소를 표시로 유지할지는 조정자 판단이다.

**최소 갱신 범위** (e2e 소유자는 구현 워커이며, 검토자는 실행하지 않았다).

- 라우트 mock의 `/prematch` 분기를 `/document`로 바꾸고 fixture별 문서 응답을 넣는다.
- 205줄 `homeRequests.every(path => ...'/prematch')`를 `/document` 기준으로 바꾼다.
- `.hp-lead`·`.hp-prediction`·`#preview-odds` 단언을 `mpv-*`로 옮긴다.
- 저장 문서에 없는 내용(최근 5경기·출처 접기·주목 선수·부상 요약·자료 확인 현황) 단언은 이 파일에서 빼거나 관리자·다른 화면 검사로 옮긴다.
- 147·166·217줄의 pending·layout 검사는 `/prematch` pending 응답을 전제하므로 `status: 'none'` + `absence` 응답으로 다시 쓴다.

`frontend/e2e/home-preview-l3.spec.ts`는 `HOME_PREVIEW_L3=1`일 때만 실행되고 실제 API를 쓰지만, 같은 `hp-lead`·`key-absence`·`preview-injuries`·`hp-form` 단언을 갖고 있어 같은 이유로 갱신 대상이다. `home-preview-mock.spec.ts`는 `/home/mock`(`HomePreviewMockView`)을 보므로 영향이 없다.

## 조정기록 실패와 제품 판정의 분리

Orca 자동후속 등록이 timeout과 식별자 불일치로 실패한 것은 **전달 기록의 문제**이지 제품 판정이 아니다. 산출물은 저장돼 있고, 이 보고서는 저장소 상태만 근거로 판정했다. Orca 메타데이터 수정은 하지 않았다. 구현자의 `EDITING STOPPED` 보고와 첫 인계 시점의 파일 상태는 어긋나지 않았다. 이후 01:53에 지적 1·2를 고치는 같은 소유자의 수정이 있었고, 이 검토자가 그 두 항목만 다시 확인했다(위 "수정 확인"). 그 수정이 다른 경계를 건드리지 않았는지는 이 검토 범위에서 다시 심사하지 않았다.

## 남은 실제 확인 (승인 조건과 분리)

현재 승인 표가 비어 있어 아래 항목은 실제 홈에서 열리지 않는다. 조정자의 실제 화면 작업을 막는 차단 원인은 승인 기록 부재이고, 구현 오류가 아니다.

- 문서 있음 표시와 DOC-PRESENT 일치(본문·점수·사진·로고·매체·배당이 관리자 저장본과 같은지).
- 문서 있음 → 없음 → 있음 전환과 전환 중 앞 본문 잔존 여부. 지연 응답 부분은 이제 단위 검사가 고정하지만, 실제 화면에서도 한 번 보는 편이 좋다.
- 섹션별 스크롤 흐림→선명과 되흐림 없음, reveal 첫 프레임 깜빡임(참고 5).
- 8:2 배치, 정사각 점수 패널, 중앙 정렬, 좁은 폭·테마 유지.

## 실행·재사용 근거

| 구분 | 명령 | 결과 |
|---|---|---|
| 실행 (1차 검토) | `.venv/bin/python -m pytest tests/unit/test_home_preview_document.py -q` | 13 passed |
| 실행 (1차 검토) | `npm run test:unit -- tests/unit/home-preview/storedDocument.spec.ts src/components/home-preview/HomeRecommendedSection.test.ts src/components/home-preview/MatchPreviewBody.test.ts tests/unit/home-preview/recommendations.spec.ts` | 26 passed (4 files) |
| 실행 (수정 확인) | 같은 backend 명령, 01:53 코드 기준 | **14 passed** |
| 실행 (수정 확인) | 같은 frontend 4파일 명령, 01:53 코드 기준 | **27 passed** (4 files) |
| 실행 | `npx vue-tsc -b --pretty false` | 8 errors, 모두 변경 밖 파일 |
| 실행 (증거 대조 1회) | `npm run test:unit -- tests/unit/home-preview/publication.spec.ts` | 2 failed / 11 passed, 보고된 `resolve` 오류 재현 |
| 실행 (모듈 직접 확인) | `select_document`/`_public_row`/`read_document` 합성 입력 호출 | 구성본 대체(수정 전) → 미대체(수정 후), 화이트리스트 키, 타 실행 선택, 동률 결정 확인 |
| 실행 (mutation 확인) | 현재 코드 vs 옛 `_chosen_rows`·느슨한 `_displayable` 메모리 교체 | 새 검사가 지적 1의 결함과 승인 조건 무력화를 모두 잡는 것을 확인, 원복 |
| 재사용 | 구현 보고의 backend·frontend·vue-tsc 수치 | 위 표로 재현됐으므로 재실행 범위를 넓히지 않았다 |
| 제외 | 전체 회귀, 전체 빌드, stash 비교, 브라우저, 서버 재시작, 승인 POST, DB 쓰기 | 금지 범위이며 실제 화면은 조정자 담당이다 |
| 미재현 | "전체 검사 68 failed / 345 passed" | 금지 범위라 실행하지 않았다. 보고서가 인용한 `publication.spec` 실패만 독립 재현됐다 |

## 적용한 원칙과 달라진 판단

- **Prove It Works.** 구현 보고의 수치를 인용으로 끝내지 않고 직접 다시 실행했다. 13·26·8이 모두 맞았고, `publication.spec` 실패도 재현됐다. 그래서 "근거가 틀렸다"는 지적을 만들지 않았다.
- **Test Behavior, Not Implementation.** 경계 판정에서 내부 함수 호출 모양이 아니라 홈이 실제로 받는 응답과 화면 분기를 기준으로 봤다. 그래서 `toStoredPreviewView`가 기존 투영을 재사용한 점을 결함이 아니라 재사용으로 기록했다.
- **Laziness Protocol.** 지적마다 최소 수정 범위를 한 함수·한 줄 단위로 적고, 범위를 넓히는 제안(옛 메타데이터 연결 통합 등)은 후속으로 분리했다.

## 검토 종료

독립 검토 1회는 1차 판정에서 끝냈고, 이후 추가된 것은 지시받은 수정 확인과 e2e 계약 분류뿐이다. 같은 검사를 다시 돌리거나 범위를 넓히지 않는다. 지적 1·2는 같은 소유자가 고쳤고 이 검토자가 현재 코드로 재확인했으므로, 조정자가 남은 결정을 하면 된다. 판단이 필요한 항목은 셋이다. 기존 e2e 두 파일 갱신을 누구에게 언제 배정할지, 최근 5경기 표·출처 접기 같은 옛 표시가 저장 문서에 없다는 감소를 받아들일지, 그리고 참고 개선 5건 중 공개 화이트리스트 키 불일치(3번)를 이번에 고칠지다. 승인 기록 부재로 열리지 않는 문서 있음 실화면은 승인 조건이 풀린 뒤 조정자가 확인할 항목으로 남는다.

## e2e 갱신 최종 확인 (2026-11-13 02:15, 읽기 전용)

`frontend/e2e/home-preview-live.spec.ts` 한 파일(277+/158-)만 확인했다. 다시 실행하지 않았고 14/5·27 근거를 재사용했다.

확인한 리비전은 `sha256 60f8a9ab…dcf8`, mtime 11-13 02:04:51이다. 이 리비전에는 173줄의 팀 로고 단언(`.mpv-team__head img`의 `src` = `TEAM_LOGO`)이 포함돼 있다. 조정자가 02:05에 추가했다고 안내한 그 행이며, 이 검토가 읽은 파일이 이미 그 상태였으므로 판정은 최종 리비전에 대한 것이다. 이후 파일은 바뀌지 않았다.

**계약 준수.** 합성 응답이 새 `/document` 스키마를 그대로 따른다. `status`·`reason`·`absence`·`saved_at`·`run_id`·`sections[]`를 모두 채우고, 없음 응답은 `sections: []`·`saved_at: null`·`run_id: null`로 계약상 필수 조건을 만족한다. `/prematch` mock은 전부 `/document`로 바뀌었고 `homeRequests.some(path => path.endsWith('/prematch'))`를 `false`로 단언해 옛 경로 회귀를 잡는다. 옛 선택자(`.hp-lead`·`hp-form`·`hp-prediction`·`key-absence`·`player-watchpoint`·`all-injuries`·`#preview-odds`·`is_mock`·`generation_due_at`)는 실행 코드에서 사라졌다.

**의미 있는 검사.** 첫 진입 자동 표시(`match-preview-body`가 클릭 없이 보임), 저장 시각, 카드 4종(예상 점수·매체·배당 3칸·선수 사진), 팀 로고, `--reveal` 스타일 설정, 경기 전환 시 배당 라벨이 선택 팀을 따름, 지연 응답 무덮음, 계약 위반 응답→오류 상태, 503→오류+다시 확인, 없음 단일 안내(버튼0), 6시간 이내 미생성 문구, 1440/390 단일 스크롤 소유자, 방송 권한 4역할을 각각 단언한다. `test.skip`·`fixme`·`only`·무조건 성공은 파일에 없고(직접 grep), 이전 버전에도 없었다. 실패를 숨긴 흔적은 없다.

**DOC-PRESENT 필수 항목 중 부상 카드는 단언되지 않는다.** HP-FIX 표는 "부상 내용 — `section_availability` 구조 값 `디아스`"라고 적었지만, `디아스`는 합성 fixture(79줄)에만 있고 `expect`는 없다(74개 expect 전수 확인). 부상 데이터를 넣어두고 그려지는지 보지 않는 상태다. 사용자 영향은 저장 문서의 부상 카드가 홈에서 깨지거나 비어도 e2e가 통과한다는 것이다. 다만 이 항목은 카드 렌더링 자체가 `MatchPreviewBody` 소관이고 그 컴포넌트는 이번에 수정되지 않았으므로 **현재 변경이 만든 직접 요구 위반은 아니다**. 최소 보완은 첫 테스트에 `body.locator('.mpv-entry__name')`에 `디아스`가 있는지 한 줄 추가하는 것이다. 새 검사 항목을 만들지 말라는 지시가 있으므로 차단 항목이 아니라 이 절의 기록으로만 남긴다.

**명령 판정 분리.** 저장소 기본 명령은 실패가 맞다. `playwright-core/browsers.json`이 `chromium-headless-shell` 1223을 요구하는데 캐시에는 1254·1217만 있어 `Executable doesn't exist`가 된다(직접 확인). 설치된 1254로만 지정한 임시 설정 실행의 **14 passed (7.9s)**는 구현 세션 `74f0dacf` 기록에서 확인했고, 그 설정은 `/tmp`에 있었고 지금 없으며 저장소 `playwright.config.ts`는 이번 작업에서 변경되지 않았다(mtime 11-12 03:17, 이전 다른 작업의 변경). 따라서 **14 pass는 임시 설정 조건의 근거이고 기본 명령 성공이 아니다.** e2e가 실행하는 대상은 합성 응답이며 실제 승인 문서 화면 성공을 뜻하지 않는다.

**검사 수.** 이전 15 → 현재 14. 구성은 이렇게 바뀌었다. 단일 검사 5 → 6(옛 `real home loads…`는 `synthetic stored document…`로 다시 쓰였고, 옛 `key absences…`의 배당 추종 단언은 그 첫 검사로 합쳐졌고, 옛 `pending preview`는 생성 예정 UI 제거로 사라졌으며, `contract-violating`·`document read error`·`absent document`·`six hour window` 4건이 늘었다). 스크롤 소유자 행렬은 4 → 2(옛 `ready`/`pending` 두 상태 중 `pending`이 없어져 viewport당 1건), 빈 홈 2 → 2, 방송 권한 4 → 4. 그래서 단일 +1, 스크롤 -2로 합계 -1이다. 요구가 비지 않았고 skip으로 대체된 검사는 없다.

**판정.** e2e 갱신은 수용한다. 현재 변경이 만든 직접 요구 위반은 없다. 남는 것은 위 부상 단언 한 줄과, 저장소 기본 브라우저 버전 불일치라는 환경 제한이다. 전자는 기록만 하고 후자는 조정자가 필요 시 별도로 정리할 항목이다.

이 확인에서 제품·검사·도구·임시 설정 코드를 편집하지 않았고 백그라운드 작업도 시작하지 않았다.

## 실제 조회 근거와 e2e 계약 영향 (2026-11-14 01:55 KST 추가)

root가 전달한 두 사실(실제 document GET 결과, 기존 e2e 옛 계약 우려)을 현재 트리와 대조한 최소 기록이다. 코드 편집·브라우저 실행·검사 실행은 없었다. 스킬 `poteto-mode/SKILL.md` 해시 `70faeea6…b936`은 미변경이라 기존 읽기를 재사용했다.

### e2e 우려는 현재 파일에 해당하지 않는다 (정정)

전달된 "`home-preview-live.spec.ts`가 옛 `/prematch` mock과 `hp-lead`·`preview-sources`·`data-gap-summary`를 가정해 새 `/document` 단일소스와 맞지 않는다"는 서술은 **현재 파일 상태와 다르다.** 이 파일은 이미 HP-FIX에서 현재 계약으로 다시 쓰였다(보고서 231행, mtime 11-13 02:04, `sha256 60f8a9ab…dcf8`).

- `/prematch` **mock 분기는 남아 있지 않다.** `grep` 결과 `prematch` 문자열은 헤더 주석 1건과 "호출하지 않는다"를 확인하는 두 단언뿐이다. diff에서도 `/prematch` fulfull 분기 5곳이 제거됐다.
- 옛 선택자 `preview-sources`·`data-gap-summary`는 **부재 단언**(`toHaveCount(0)`, 189-190행)으로만 남아 있다. 이는 옛 UI가 홈에서 사라졌다는 **새 요구를 고정하는 단언**이며, 옛 계약을 가정한 것이 아니다. `.hp-lead`는 헤더 주석에만 언급된다.
- 라우트 mock은 `**/api/v1/home/**`에서 `/recommendations`와 `/document`만 응답하고, 325행이 `homeRequests.some(path => path.endsWith('/prematch'))`를 `false`로 단언한다.

따라서 이 파일에 **추가로 갱신할 범위는 없다.** 분류상 이것은 **이미 완료된 과거 계약 단언 교체**이고, 새 홈 연결이 만든 제품 회귀가 아니다.

### 실제 옛 계약이 남은 파일

`frontend/e2e/home-preview-l3.spec.ts`는 여전히 `page.on('request')`에서 `/prematch`를 수집하고 `.hp-lead` 존재를 단언하며 `http://127.0.0.1:8017/.../prematch`를 직접 호출한다. 다만 첫 줄이 `test.skip(process.env.HOME_PREVIEW_L3 !== '1', ...)`로 격리 DB·8017 전용 opt-in이고, Plans.md 27행이 이미 현재 완료 조건에서 제외해 과거 계약 후속으로 남겼다. 이 검토에서도 편집·실행 대상으로 추가하지 않는다.

### 실제 GET 결과는 코드 동작과 일치한다

root가 관측한 세 응답은 현재 코드의 사유 분기와 일치하며 **코드 실패가 아니다.**

| 경기 | 관측 | 코드 근거 |
|---|---|---|
| 1557474 맨시티 | `none/no_approved_version/upcoming` | `_read_runs`가 실행을 찾았고 본문 있는 실행이 있으나 승인 버전이 없어 `_reason_key`가 `no_approved_version`(`home_preview_document.py:275-282`) |
| 1557445 과거 | `none/no_stored_run/past` | 실행 0건 → `no_stored_run`(`:276`, `:626-627`), 시각 분기 `past`(`:413`) |
| 1557470 미래 첼시 | `none/no_stored_run/upcoming` | 실행 0건, 6시간 초과 → `upcoming`(`:415-417`) |

`no_approved_version`은 승인 정책이 작동한 결과다. root가 함께 관측한 `approvals approved=[]`·전 `active/pinned=null`이 그 원인이며, 승인 없이 저장 본문을 노출하지 않는 현재 계약과 모순되지 않는다. 맨시티 문서가 이전에 표시됐다면 승인 행 상태가 그 사이 바뀐 것이므로, 그것이 개발 스키마 초기화인지 승인 비활성인지는 root가 확인할 사실이다. 이 검토는 코드 결함으로 단정하지 않는다.

저장 구성본 `493ef4a9`의 5섹션이 GET으로 확인됐는데도 본문/reveal 실표시가 미완인 것은 **승인 POST 0건의 결과**이며, 합성 브라우저 성공으로 대체하지 않는다. 실제 본문 표시 검증은 승인 상태가 정해진 뒤 root 몫으로 남는다.

### 판정

새 홈 연결이 만든 직접 회귀는 확인되지 않았다. e2e는 이미 현재 계약이고, 남은 옛 계약 파일은 skip-gated 격리 검사로 기존 결정대로 후속이다. 편집 0건, 백그라운드 0건.
