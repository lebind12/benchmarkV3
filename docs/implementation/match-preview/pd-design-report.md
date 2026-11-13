# PD-F 프리뷰 디자인 4항목 구현 보고

작성: 2026-11-12 KST. 담당: DeepSeek 구현 워커(Orca `dsh-tui`, 실제 모델
`deepseek-ai/deepseek-v4.1-flash-1017`, 사용자 설정 추론 강도 Max 유지).
근거 계획: `docs/superpowers/plans/2026-11-12-preview-design-adjustments.md`.

## 1. 변경 파일

| 파일 | 변경 |
|---|---|
| `frontend/src/styles/match-preview/body.css` | AI 전망/점수 **6:4** + 우측 안쪽 여백, 팀 로고 **테마 패널**, 매체·배당 **공통 외곽 패널**(자식 stretch), 좁은 화면 세로 순서 |
| `frontend/src/components/home-preview/MatchPreviewBody.vue` | 팀 로고 **깨짐 상태 키를 섹션별로 분리**(`teamPhotoKey`). 로고/사진 URL·문장·배당 셀 로직 변경 없음 |
| `frontend/src/components/home-preview/MatchPreviewBody.test.ts` | 팀 로고 대표 검사 1건 추가(아래 §4) |

`previewView.ts`는 **조사만 하고 수정하지 않았다**. `tokens.css`도 수정하지 않았다(기존 패널 토큰으로
충분). 호출 안내 3파일(`PreviewPanel.vue`, `SectionRegenerationPanel.vue`, `SectionRegenerationPanel.test.ts`)은
mtime 22:21~22:23으로 이번 작업(22:33 시작) 이전 상태 그대로이며 **편집 0**이다.

## 2. 네 항목별 구현

| 항목 | 요구 | 구현 |
|---|---|---|
| 1 | AI 전망 60% / 예상 스코어 40%, 같은 블록, 우측 안쪽 여백 | `.mpv-analysis`를 `6fr/4fr`로 바꾸고 `padding-inline-end` 추가, `align-items: stretch`. 점수·근거는 복제하지 않음 |
| 2 | 주목 선수 팀 제목에도 실제 로고 | 아래 §3 참고 — **마크업은 이미 있고**, 로고가 안 나오던 원인 2가지를 분리 확인 |
| 3 | 두 선수 섹션 로고를 같은 높이 작은 패널에 | `.mpv-team__head`에 `--mpv-panel-bg`/`--mpv-panel-line`/`--mpv-radius-m`로 패널 + `min-height: 52px`. 새 색·장식 없이 기존 테마 변수만 사용(밝은/어두운 테마 자동). 선수 사진 카드(`.mpv-entry`)는 그대로 |
| 4 | 매체·배당 공통 외곽 패널 + 부모 높이 stretch | `.mpv-evidence`에 패널 배경·테두리·안쪽 여백, `align-items: stretch`, 자식 `.mpv-panel`은 `height: 100%` + 패널 스타일 해제. 한쪽만 있으면 기존 `.mpv-evidence--single`이 한 열로 펴서 **빈 열 없음** |
| 5 | 좁은 화면 세로, 고정 높이 금지 | `max-width: 1020px`에서 두 그리드를 1열로. 문서 순서가 곧 읽기 순서(본문→점수, 매체→배당). 자식 `height: auto`로 되돌리고 고정 높이 없음 |

## 3. 팀 로고(항목 2) — 원인 분리

로고 마크업은 이미 있었고(`.mpv-team__head > img`), 안 나오는 이유는 **두 가지 서로 다른 원인**이었다.

### 3-1. 고친 것 — 두 섹션이 깨짐 상태를 공유했다 (내 소유 범위)

`photoOk`/`markBroken` 키가 열 번호만(`team-0`/`team-1`)이라 주목 선수와 부상·결장이 같은 키를 썼다.
그래서 **한 섹션에서 로고가 한 번 깨지면 다른 섹션 로고까지 함께 사라졌다**. 실측:

```
수정 전: IMGS_BEFORE=2  →  한 img에 error  →  IMGS_AFTER=0   (두 섹션 모두 사라짐)
수정 후: IMGS_BEFORE=2  →  한 img에 error  →  IMGS_AFTER=1   (나머지 섹션 로고 유지)
```

`teamPhotoKey(section, column)`로 섹션 이름을 키에 붙여 서로 영향을 주지 않게 했다.

### 3-2. 남은 것 — 주목 선수 행에는 팀 외부 ID가 없다 (backend 계약, 범위 밖)

`badgeOf`는 홈/원정이 **확인된** 묶음에만 로고를 붙인다(확인 안 되면 다른 팀 로고를 붙이지 않는다).
그 확인에 쓰는 `team_external_id`가 backend 구조화 투영에서 **부상 행에만** 있고 **주목 선수 행에는
없다**:

```
app/preview/section_structured.py _players(...)   → "team_external_id" 키 없음
app/preview/section_structured.py _injuries(...)  → "team_external_id" 키 있음
```

그래서 주목 선수는 이름 비교(경기 라벨·저장 `korean_labels` 별칭표)로만 좌우를 정한다. 실측으로
확인한 세 경우:

| 입력 | 주목 선수 side 판정 | 로고 |
|---|---|---|
| 라벨 한국어(`맨체스터 시티 vs 풀럼`) + 팀명 한국어 | 홈=0, 원정=1 | **그려짐** |
| 라벨 영어 + 팀명 한국어, 별칭표 있음 | 홈=0, 원정=1 | **그려짐** |
| 라벨 영어 + 팀명 한국어, 별칭표 없음 | 둘 다 `null` | 안 그려짐 |

즉 저장 run에 `korean_labels`(R4 payload)가 있으면 지금도 로고가 그려지고, 없으면 좌우를 확인하지
못해 **의도적으로** 붙이지 않는다(배열 순서로 홈/원정을 추측하지 않는 기존 규칙).

**최소 필요 범위(데이터 계약, 추측 구현 안 함)**: `_players`가 `_injuries`처럼
`team_external_id`를 내려주면 주목 선수도 ID로 확정된다. 이는 backend 소유이며 이번 지시에서
제외되어 **고치지 않았다**. 프론트에서 이름 추측으로 ID를 만들지 않았다.

## 4. 검사

```
cd frontend && npx vitest run src/components/home-preview/MatchPreviewBody.test.ts
→ Test Files 1 passed (1) / Tests 9 passed (9)   (기존 8 + 신규 1)

cd frontend && npx vue-tsc -p tsconfig.app.json --noEmit
→ 변경 파일(MatchPreviewBody.vue·previewView.ts) 관련 새 오류 0
   기존 8건은 확대 수정하지 않았다.
```

추가한 대표 검사 1건과 수용 기준:

| 검사 | 수용 기준 | 실패하면 사용자에게 생기는 일 |
|---|---|---|
| 두 선수 섹션이 팀 로고를 그리고, 한 로고의 `error`가 다른 섹션 로고를 지우지 않는다 | 항목 2·3의 로고 표시 | 주목 선수 카드에서 팀 로고를 보지 못한다(부상 섹션까지 함께 사라짐) |

디자인/CSS를 그대로 반복하는 새 검사는 만들지 않았다(계획의 PD-F 조건).

## 5. 보존 확인

본문 문장·선수 이름/이유·부상 요약·매체 문장·배당 3행·선수 사진·`**강조**`(strong 노드) 규칙은
변경하지 않았다. 기존 8검사(중복 표시·배당 사유·배당 값/관측 시각·구성본 카드 복구)가 그대로 통과한다.

## 6. 실제 화면 미확인 항목

CSS 배치(6:4, 패널, stretch, 좁은 화면 순서)는 **jsdom에서 검증되지 않는다**. 이 보고가 확인한 것은
"구조·클래스·내용이 그대로"이고, 시각 배치는 root의 실제 화면 확인(PD-UI, 기존 저장 run
`493ef4a9-0e14-4436-8a97-d6de7ce034a7`) 대상이다. 밝은/어두운 테마와 좁은 폭도 그때 확인해야 한다.
주목 선수 로고가 실제 화면에서 보일지는 그 run의 `korean_labels` 유무에 달려 있다(§3-2).

## 7. 실행하지 않은 것

DB·서버·브라우저·실제 HTTP·모델·재생성·전체 생성·`Plans.md` 편집 **0**. backend 수정 0,
새 데이터 계약/추측 구현 0, 전체 suite·전체 빌드 0, 커밋 0, 하위 워커 0.

## 8. 후속 — 실제 화면 computed style 충돌 1건 정정 (root 실측)

root가 22:52 실제 run `493ef4a9` desktop에서 `getComputedStyle`로 확인한 결과 **모든
`.mpv-team__head`의 `padding`이 `0px`** 였다. 원인은 이 파일 위쪽의 리셋
`.mpv p { margin: 0; padding: 0 }`(특이도 0,1,1)이 `.mpv-team__head`(0,1,0)보다 세서,
항목 3에서 요청받은 패널 안쪽 여백이 실제로는 적용되지 않은 것이다. 마크업상 `.mpv-team__head`는
`<p>`다.

**수정(이 파일 1곳)**: 선택자를 `.mpv .mpv-team__head`(0,2,0)로 올려 리셋보다 강하게 만들었다.
리셋 규칙 자체는 건드리지 않았다(다른 본문 문단의 여백이 함께 바뀌는 것을 막기 위해). 같은 이유로
`min-height`·테두리·배경도 함께 유지된다. 주석에 이 충돌 이유를 남겼다.

부수 정정: 파일 머리 주석의 옛 "전망 2/3 + 점수 1/3" 서술을 현재 배치(본문 60% / 점수 40%,
매체·배당 공통 외곽 패널)로 사실에 맞게 고쳤다.

**되돌린 것(범위 축소)**: 주목 선수 로고의 `team_external_id` 부재를 프론트에서 저장 행
(`team`+`team_external_id` 쌍)으로 보완하는 시도를 **전부 되돌렸다**. 조정자가 그 연결은
PD-B(backend)에서 실제 ID로 처리 중이라고 확인했으므로, 프론트의 추측성 보완은 남기지 않는다.
`previewView.ts`는 이번 후속에서 **변경 0**(§1의 "조사만 함" 상태 그대로)이며 타입 오류도 0이다.

**검증**: `MatchPreviewBody.test.ts` 9 passed 유지, 변경 파일 타입 오류 0. CSS는 jsdom에서
computed padding을 검증하지 않는다(지시대로 새 CSS 미러 검사·전체 vitest·타입 반복 없음).
실제 `padding` 값과 화면은 root가 computed style·screenshot으로 확인한다.

### 8-1. 복구 확인 (지시 즉시 처리)

지시대로 **본인 후속 추가만** 제거된 상태를 확인했다. 별도 되돌림 편집은 필요 없었다 —
직전 턴에서 이미 철회를 마쳐 저장소에 다음 참조가 **0건**이다.

```
grep -rn "injuryRows|verifiedTeamExternals|verified_team_externals" src/   → 0건
grep -rn "injuryRows" . (node_modules/dist 제외)                            → 0건
npx vue-tsc -p tsconfig.app.json --noEmit | grep "previewView.ts|preview.ts"
  → previewView.ts 오류 0 (preview.ts 16행 미사용 import 1건은 기존 오류)
```

`PreviewPanel` render error의 원인이던 `injuryRows` 미정의 참조는 **남아 있지 않다**.
**기존 구성본 연결은 그대로 보존**했다(`withComposedRows`, `composed_sections`,
`loadComposedSections` 모두 유지). 기존 검사로 복구를 확인했다.

```
npx vitest run src/components/home-preview/MatchPreviewBody.test.ts                src/components/management/PreviewPanel.test.ts
→ Test Files 2 passed (2) / Tests 30 passed (30)
```

`body.css`의 team head padding reset 충돌 1건은 §8에서 이미 최소 수정된 상태다
(`.mpv .mpv-team__head`). 새 데이터 매핑·범용 검사는 추가하지 않았다. 실제 화면은 root가 확인한다.

EDITING STOPPED

## 9. PD-SCORE — 예상 점수 확대·정중앙·실제 팀명 우세 (새 사용자 요청)

요청: 예상 점수를 더 크게, 점수·라벨·우세 문구를 패널 **가로/세로 정중앙**의 컴팩트 그룹으로,
`홈팀/어웨이팀 우세` 대신 **실제 팀명**(예: `맨체스터 시티 우세`). 이전 CSS 패딩 수정과 임시맵
제거 인계는 그대로 보존했다.

| 항목 | 변경 |
|---|---|
| 점수 크기 | `tokens.css`의 `--mpv-text-score`를 `clamp(56px,7vw,76px)` → `clamp(64px,9vw,112px)`(기존 72px보다 충분히 큼), 구분자도 `clamp(32px,5vw,56px)`로. 좁은 폭은 vw로 줄어 넘치지 않음 |
| 정중앙 정렬 | `body.css` `.mpv-prediction`에 `place-content: center`·`justify-items: center`·`text-align: center`, 점수 줄 `justify-content: center`·`max-width: 100%` |
| 실제 팀명 우세 | `previewView.ts` `leanLabel`이 무승부는 그대로 두고, 홈/원정 우세는 **확인된 팀명**으로 표시 |

**팀명 확인 규칙(추측 없음)**: ① fixture/candidate 이름이 실제 팀명이면 우선 사용(`홈팀`/`원정팀`
fallback 은 이름으로 쓰지 않음) ② fixture 외부 ID와 **정확히 일치하는** 구조화 행(선수·부상)의
`team`+`team_external_id` 쌍에서만 이름을 가져온다. 같은 ID에 다른 이름이 오면 확정하지 않고,
확인 불가면 팀명을 지어내지 않고 기존 중립 문구(`홈팀 우세`/`원정팀 우세`)를 유지한다.
부상 행으로 ID를 복원하거나 ID를 추측하는 새 맵은 만들지 않았다.

**검증** — 기존 직접 검사 1파일만:
```
cd frontend && npx vitest run src/components/home-preview/MatchPreviewBody.test.ts
→ Tests 10 passed (10)   # 기존 9 + 대표 1
```
대표 검사(실제 저장본 모양: 라벨 `fixture 1557474`, fixture 이름 fallback): 외부 ID 50 행의
`맨체스터 시티`로 `맨체스터 시티 우세`, 그 행이 없으면 `홈팀 우세` 유지. 이름 해석을 끄면 이
검사가 실패(`1 failed`)하므로 실제 결함을 잡는다. `vue-tsc -p tsconfig.app.json`에서 변경 파일
오류 0, 기존 8건은 그대로(확대 없음). CSS 미러 검사·타입 전체 반복 없음.

**미확인**: 실제 점수 크기·중앙 정렬·좁은 폭은 CSS이므로 jsdom에서 검증하지 않는다. 6:4와 모바일
세로 규칙은 손대지 않았다. root가 실제 화면에서 확인한다.

EDITING STOPPED

## 10. PD-SQUARE — 8:2 + 정사각형 점수 패널 (사용자 후속)

요청: "전망 점수 8:2 정도로, 점수는 너비와 높이가 똑같게". 계획의 PD-SQUARE 절이 현 수용 기준이며
앞선 6:4 요구를 대체한다.

**변경 파일: `body.css`만.** Vue/TS/API/backend/DB/서버/모델/HTTP/`Plans.md` 편집 0.
`tokens.css`의 점수 토큰(PD-SCORE, 112px 상한)은 그대로 재사용했다.

| 요구 | 구현 |
|---|---|
| 전망/점수 **8:2** | `.mpv-analysis` `grid-template-columns: minmax(0,8fr) minmax(0,2fr)` (6:4 규칙 대체) |
| 패널 **바깥 너비 = 높이** | `.mpv-prediction`에 `aspect-ratio: 1 / 1` + `container-type: inline-size` |
| 본문 높이를 따라 **세로로 늘어나지 않음** | `.mpv-analysis`의 `align-items`를 `stretch` → **`start`**로 바꿔, 높이를 내용이 아니라 `aspect-ratio`가 정하게 함 |
| 라벨·점수·우세팀 **가로/세로 중앙** 유지 | `place-content: center` + `justify-items: center` + `text-align: center` 유지 |
| 좁은 패널에서 **글자 잘림/넘침 0** | 점수·구분자에 `--mpv-text-score` 폴백 선언 후 `clamp(…, min(토큰, 38cqi/20cqi), …)`로 패널 폭 기준 축소. 우세팀 문구는 작은 크기 + `overflow-wrap: anywhere`(문구 유지, 삭제 없음) |
| 모바일 세로 순서 + 정사각형 유지 | `max-width: 1020px`에서 1열(본문 → 점수) 유지, `.mpv-prediction`은 `aspect-ratio` 그대로 + `width: min(100%, 340px)` |

**넘침 검산**(브라우저 없이 산술): 1667px → 패널 ≈319px·점수 ≈108px(두 자리 ≈119px < 285px 내부),
1100px → ≈206px·≈65px(≈72px < 172px), 390px → ≈340px·≈112px(≈123px < 306px). 세 폭 모두
패널 내부 폭 안에 들어온다.

**검증**: 순수 CSS 변경이므로 새 검사·vitest·typecheck·빌드 반복은 하지 않았다(지시대로).
CSS 중괄호 균형 확인, 6:4 규칙이 8:2로 대체됐고 `aspect-ratio`·모바일 규칙이 존재함을 파일로 확인.
기존 수정(팀 로고 특이도 패딩, 공통 외곽 패널, 도입 문장)은 그대로 보존됐다.

**미확인**: 실제 열 비율·정사각형·중앙 정렬·넘침은 렌더 결과이므로 jsdom으로 검증하지 않는다.
root가 1667px / 1100px / 390px 실제 화면에서 확인한다.

EDITING STOPPED
