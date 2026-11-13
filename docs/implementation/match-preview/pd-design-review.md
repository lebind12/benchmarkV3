# PD-R — 프리뷰 디자인 4항목 **한정 독립 검토**

작성: 2026-11-12 KST. 담당: DeepSeek 독립 검토 워커(PD-R). 실제 모델 `deepseek-ai/deepseek-v4.1-flash-1017`(dsh-tui, Max 유지).
범위: 계획서 `2026-11-12-preview-design-adjustments.md` + `pd-design-report.md` + `body.css`/`MatchPreviewBody.vue`/`MatchPreviewBody.test.ts`의 현 상태만. 제품·테스트 편집 0, 브라우저·DB·HTTP·모델·서버 0.

## 판정 요약

| 요구 | 판정 | 근거 |
|---|---|---|
| 1. AI 본문 6 : 점수 4 + 우측 안쪽 여백 | **충족** | `.mpv-analysis`가 `minmax(0,6fr)/minmax(0,4fr)`·`align-items:stretch`·`padding-inline-end:var(--mpv-space-6)`(`body.css:149-156`). 좁은 화면에서 `padding-inline-end:0`으로 되돌림(`:611`). `mpv-prediction__score`는 문서에 1개뿐(복제 없음) |
| 2·3. 주목/부상 팀 헤더 로고가 같은 높이 테마 패널 | **충족(표시 조건부)** | 두 섹션이 같은 `.mpv-team__head`(로고 36px + `min-height:52px` + 테두리/배경/radius, `:280-298`), 토큰 `--mpv-panel-bg`/`--mpv-panel-line`은 밝은·어두운 테마에 모두 정의(`tokens.css:42-43,133-134`, `html.dark` `:109-110`). 새 색·장식 없음. 선수 사진 카드 `.mpv-entry`는 그대로(`:317-330`) |
| 4. 하단 매체·배당 공통 패널 + 자식 stretch | **충족** | `.mpv-evidence`가 자체 배경·테두리·여백 + `align-items:stretch`, 자식 `.mpv-evidence > .mpv-panel`은 `height:100%`·패널 스타일 해제(`:439-457`). 한쪽만 있으면 `.mpv-evidence--single`이 1열(`MatchPreviewBody.vue:421-423`) → 빈 열 없음 |
| 5. 좁은 화면 순서·넘침 없음 | **충족** | `@media (max-width:1020px)`에서 `.mpv-analysis`·`.mpv-evidence`가 1열(`:596-610`), 문서 순서가 본문→점수, 매체→배당. 자식 `height:auto`. 고정 높이·`max-height`·`line-clamp` 0(파일 전체 확인). `min-width:0`/`overflow-wrap`이 그리드 자식에 적용됨 |
| 본문·점수·사진·배당 보존 | **충족** | 마크업 변경은 로고 깨짐 키 분리뿐(`teamPhotoKey`, `MatchPreviewBody.vue:95-96,234-285`). 배당 셀·문장·사진 렌더 로직 무변경. 새 검사 1건이 두 로고 렌더 + 한쪽 `error`가 다른 쪽을 지우지 않음을 고정(`test.ts:284-353`) |

## 이번에 실제로 잡힌 결함(구현자가 검토 중 수정함)

- **CSS 리셋이 패널 여백을 덮고 있었다.** 파일 상단 리셋 `.mpv p { margin:0; padding:0 }`(특이도 0,1,1)가 `.mpv-team__head`(0,1,0)의 `padding`을 이겨 **computed padding 0**이 됐다. 22:57 갱신본이 선택자를 `.mpv .mpv-team__head`(0,2,0)로 올려 해결했고, 같은 이유로 `.mpv .mpv-entry__name`도 올라가 있다(`body.css:287,359`). 주석에 원인과 "리셋은 건드리지 않는다"는 판단이 남아 있다 → **요구 2·3의 실제 위반이었고 지금은 해소**.

## 참고(비차단, 이번 변경이 만든 것이 아님)

1. **같은 리셋 그림자가 남은 형제 규칙 3건**: `.mpv-prediction__score`(margin-block), `.mpv-media__text`(margin-top), `.mpv-odds__heading`(margin-bottom), `.mpv-media__head`는 모두 `<p>`에 걸린 **클래스 단독 선택자**라 리셋에 밀린다. 다만 이는 **목업 원본(`match-mock.css`)에도 동일**하고(`.mm-page p` 리셋 + `.mm-*` 단독 선택자), PD-F가 만든 회귀가 아니다. 요구 1·4의 성립(6:4·패널)에는 영향이 없고 값은 `gap`/`margin-top`(부모)으로 대체돼 화면이 깨지지 않는다. 후속 후보로만 적는다.
2. **주목 선수 로고의 팀 ID 누락(알려진 의존)** — *귀속 정정*: `section_structured._players`가 `team_external_id`를 내려주는 것은 **PD-B(backend)** 작업이며 frontend 편집은 0이다. 한편 `previewView.ts`의 22:53~23:07 변화는 **PD-F가 시도했다가 철회한 임시 매핑**(`verifiedTeamExternals`/`verified_team_externals`/`injuryRows`)과 철회 후 정리된 상태이지 PD-B의 편집이 아니다(현재 참조 0건 확인). 즉 frontend는 이름 별칭표가 없어도 `teamGroups`가 `row.team_external_id`로 좌우를 판정할 수 있게 됐지만, 그 값의 공급은 PD-B 소유이므로 이 검토는 수정 요구를 중복 제기하지 않는다.
3. `.mpv-evidence--single`은 `body.css`가 아니라 컴포넌트 `<style scoped>`에 있다(`MatchPreviewBody.vue:421`). 외곽 그리드는 `body.css`의 `.mpv-evidence`가 정의하므로 **1열 전환은 적용된다**(scoped 규칙도 같은 요소에 붙고, 클래스는 템플릿에서 직접 부여). 다만 패널 스타일이 두 파일에 나뉘어 있어 이후 수정 시 혼동 소지가 있다 — 참고.
4. `.mpv-team__head`가 `<p>`라 52px `min-height` 패널 안에 로고·팀명·홈/원정이 flex로 정렬된다. 의미상 `<p>` 유지 여부는 이번 요구와 무관.

## 근거 재사용

- 구현자 보고의 `MatchPreviewBody.test.ts` **9 passed**(기존 8 + 신규 1)와 typecheck 신규 오류 0·기존 8건 유지는 **재실행하지 않고** 검사 내용과 파일 존재로 대조했다. 현재 `it()` 9건 확인. 전체 suite·전체 빌드 반복 0.
- `previewView.ts`의 22:53~23:07 갱신은 **PD-F 임시 매핑 시도 후 철회**다(위 참고 2의 정정 참조). PD-B의 frontend 편집은 0이다. 그래서 이 검토는 1차 판정 시 그 파일을 PD-B 작업으로 오귀속했다가 정정했다.

## 남은 필수

1. **PD-UI(root) 실제 화면 확인 1회** — 6:4·패널 여백·stretch·좁은 폭·밝은/어두운 테마는 jsdom에서 검증되지 않는다. 이 검토도 브라우저를 열지 않았다.
2. 위 참고 1(리셋 그림자 4곳)은 **후속 후보**이며 이번 디자인 요구의 차단 사유가 아니다.

---

# PD-R-SCORE — 새 점수 요구(확대·정중앙·실제 팀명) **한정 확인**

추가 검토일: 2026-11-12 KST, 같은 세션(실제 `deepseek-ai/deepseek-v4.1-flash-1017`, Max 유지).
범위: `pd-design-report.md` §9 + `tokens.css` 점수 토큰 2개 + `body.css` prediction 정렬 + `previewView.ts` `leanLabel`/실제 팀명 + `MatchPreviewBody.test.ts` 신규 1건. 이전 4항목 전체 재검토 없음, 참고 확대 없음.

## 판정: **충족 (위반 없음)**

| 요구 | 판정 | 근거 |
|---|---|---|
| 점수를 더 크게 | 충족 | `--mpv-text-score: clamp(64px, 9vw, 112px)`, 구분자 `--mpv-text-score-sep: clamp(32px, 5vw, 56px)`(`tokens.css:64-65`). 이전 상한 72px 이하에서 상향, 좁은 폭은 `vw`로 축소 |
| 패널 가로·세로 정중앙 | 충족 | `.mpv-prediction`에 `place-content:center`·`justify-items:center`·`text-align:center`(`body.css:221-232`), 점수 줄도 `justify-content:center`·`max-width:100%`(`:240-250`). 그리드 `place-content`로 세로도 중앙 |
| 실제 팀명 우세 | 충족 | `leanLabel`이 무승부는 그대로, 홈/원정은 확인된 팀명으로 `${name} 우세`(`previewView.ts:433-443`), 렌더는 `forecast.lean_label`(`MatchPreviewBody.vue:214`) |
| 6:4·모바일 기존 유지 | 충족 | `body.css:152` `minmax(0,6fr)/minmax(0,4fr)`, `:613` `@media (max-width:1020px)` 1열 — 이번에 손대지 않음 |
| ID 추측 없이 이미 검증된 fixture ID와 **정확히 같은 행**의 저장 팀명만 | 충족 | `teamNamesByExternalId`가 `(team, team_external_id)` 쌍만 받아 **ID 키**로 모으고, 같은 ID에 다른 이름이 오면 `null`로 확정 보류(`:403-424`). 대체는 fixture 이름이 fallback(`홈팀`/`원정팀`)일 때만(`:729-738`). ID 생성·유사도 매칭·새 매핑 없음 |

## 대표 검사 대조(재실행 0)

`MatchPreviewBody.test.ts` 현재 `it()` **10건**(기존 9 + 신규 1). 신규 1건(`:353-424`)이 두 경우를 함께 고정한다 — 외부 ID 50 행의 `맨체스터 시티` → `맨체스터 시티 우세`, 그 행이 없으면 `홈팀 우세` 유지. 즉 "이름 보완"과 "추측 금지"를 동시에 잡는다. 보고의 10 passed·변경 파일 타입 오류 0은 위 내용 대조로 재사용했고 새 vitest/typecheck는 실행하지 않았다.

## 참고(비차단)

1. **`leanLabel` 구현이 세 곳에 따로 있다**: `previewView.ts`(이번 경로)와 `MatchPreview.vue:77`, `SectionStructuredView.vue:52`는 여전히 `홈팀 우세`/`원정팀 우세`를 쓴다. 이번 요구는 관리 화면의 저장 프리뷰(`MatchPreviewBody`) 경로이므로 범위상 맞지만, 두 옛 화면은 문구가 다르다. 통합은 요구되지 않았다.
2. `.mpv-prediction__score`의 `margin-block`은 상단 `.mpv p` 리셋에 밀리는 **기존** 항목(§참고 1)이지만, 세로 중앙은 부모 `place-content:center`와 `gap`이 만들므로 이번 요구 성립에 영향이 없다.
3. 실제 크기·중앙 정렬·좁은 폭에서의 축소는 CSS이므로 jsdom 미검증 — root 실제 화면 확인 대상이다.

## 남은 필수

1. **root 실제 화면 확인 1회**(점수 크기·중앙 정렬·좁은 폭·실제 팀명 문구). 이 검토는 브라우저·서버·DB·HTTP·모델을 열지 않았다.
2. 그 밖에 이번 요구의 미수정 항목·차단 사유는 없다.

READ-ONLY CONFIRMED — 제품·테스트 파일을 수정하지 않았다.
EDITING STOPPED

## PD-R-SQUARE — 5조건 판정(충족, 회귀 없음)
1. **8:2** 충족 — `.mpv-analysis` `minmax(0,8fr)/minmax(0,2fr)`(`body.css:154`), 6fr/4fr 잔존 0.
2. **정사각형** 충족 — `.mpv-prediction` `aspect-ratio:1/1` + `container-type:inline-size`(`:236-237`). root 실측 938.391/234.609 = 3.9998배, 패널 234.609×234.609가 이와 일치.
3. **본문 따라 늘지 않음** 충족 — `align-items: stretch→start`(`:156`), `min-height:0`(`:239`). `stretch`는 `.mpv-evidence`(`:486`)에만 남아 하단 패널 요구 그대로.
4. **중앙 유지** 충족 — `place-content:center`·`justify-items:center`·`text-align:center`(`:232-242`) 유지, 실제 팀명 `lean_label` 렌더도 무변경(§PD-R-SCORE).
5. **≤1020px 세로 + 정사각형** 충족 — 1열·문서순서(본문→점수) 유지, `aspect-ratio` 그대로 + `width:min(100%,340px)`(`:651-660`). CSS 중괄호 균형 0.
보고서 §10의 319/206/340px 넘침 검산은 **산술 추정**이며 화면 실측 근거가 아니다(실측은 root의 1667/1100/390 확인 담당, 1100·390 진행 중). 새 검사·빌드·브라우저·제품편집 0.
