# 홈 프리뷰 디자인 목업 결과 (HM-01)

작성: DeepSeek 구현 워커 · 모델 `deepseek-ai/deepseek-v4.1-flash-1017` (DSH 프로필 `dsh-tui`) · 서브워커 0
범위: 디자인 목업만. 제품 홈·관리자 라우터 이식, backend/schema/API 변경 없음. 커밋·푸시·배포 0.

## v3: 홈 패널에 목업 본문 임베드

사용자 지시("홈화면의 패널에 현재 목업 내용을 그대로 넣읍시다. 맨시티대 풀럼")에 따라, 별도 mock 경로가 아니라 **루트 홈 `/`** 의 추천 대진·선택 프리뷰 패널이 맨체스터 시티 대 풀럼 1557474를 보여주고 그 패널 안에 v2 본문을 그대로 렌더한다.

| 항목 | 처리 |
|---|---|
| 본문 재사용 | v2 본문을 `src/components/home-preview/MatchPreviewBody.vue`로 분리. `variant="standalone"`(mock 경로)와 `variant="embedded"`(홈 패널)가 같은 `mock/match-city-fulham.json` 하나를 읽는다 |
| 홈 대진 일치 | `mocks/handlers/home-preview.ts`의 recommendations 응답을 실제 mock fixture(1557474, 팀 외부 50·36, 2026-11-21T12:30Z) 한 건으로 교체. 이전처럼 아스널–리버풀 샘플에 맨시티 프리뷰를 붙이지 않는다 |
| 패널 분기 | `HomeRecommendedSection.vue`는 `isMockFixture`(fixture 1557474)일 때만 `<MatchPreviewBody variant="embedded" />`를 쓰고, 원래 본문·빈 상태·생성 안내는 그대로 보존한다(다른 경기에서는 예전 동작) |
| 중복 방지 | embedded 변형은 자체 head를 그리지 않는다. 패널의 "경기 전 프리뷰" 제목 1개 유지, 중첩 `main` 0, 중첩 스크롤 컨테이너 0 |
| 스크롤 | `body` 전체 스크롤 규칙을 `html:has(main.mm-page)` / `body:has(main.mm-page)`로 한정해 **standalone 경로에서만** 적용. 홈은 원래 `main.home-page.panel-scroll` 단일 스크롤 유지 |
| 스타일 로딩 | 스타일시트 import를 공유 컴포넌트로 옮겨 두 경로 모두 같은 레이아웃이 되게 했다(처음엔 홈에서 unstyled로 나왔고, 측정으로 발견해 수정) |

렌더 확인(1440/1280/375/다크, 모두 콘솔 에러 0):
- 홈 대진: 맨체스터 시티 vs 풀럼, 21:30 KST, 1 / 1
- 섹션 순서: AI 경기 전망 → 주목 선수 → 부상·결장 → 외부 매체 전망(+배당)
- 그리드: 데스크톱 전망 2/3–1/3(698/349), 팀 컬럼 524+524, 배당 3열 / 폰은 전부 단일 컬럼
- 팀 컬럼: 주목 선수·부상 모두 `맨체스터 시티(홈)` 왼쪽, `풀럼(원정)` 오른쪽
- 배당: `맨체스터 시티 승 -`, `무승부 -`, `풀럼 승 -` (가짜 숫자 없음)
- 사진: 홈 임베드에서 8/8 로드(선수 8장), 팀 배지 포함 문서 전체 10/10
- 금지 문구 스캔: 예측값입니다·실제 경기 결과·저장된·그대로 옮겼·판단과는 별개·목업입니다·API-Football 경기 ID·로컬 JSON·진단·재시도·가상·샘플 **모두 absent**
- 가로 overflow 없음(1440/1280/375 모두 `scrollWidth == innerWidth`)
- standalone `/mock/man-city-fulham` 계속 동작(1440에서 720/360 그리드, 사진 10/10)

`sloplint --render` 결과: **0 FAIL / 0 WARN**, REFLEX 1건은 원본 홈 자체 CSS(`.hp-versus > .hp-muted` 등 10px)에서 나온 것으로 이번 작업에서 건드리지 않은 원본 파일이다. NOTE 4건은 원본 홈의 kept-layout 성격(hero/fold/섹션 수)이다.

## v2 수정 (사용자 피드백 5건)

같은 DeepSeek 세션에서 `MatchMockView.vue`와 `match-mock.css`만 고쳤다. 제품 코드·라우터·JSON 스키마·DB는 그대로다.

| 사용자 요구 | 반영 |
|---|---|
| 큰 상단 킥오프 영역 제거 | hero·대진 카드·이동 버튼을 모두 삭제. 상단은 "경기 전 프리뷰" 제목 한 줄과 배지·팀명·리그·킥오프만 있는 compact 식별 줄로 교체 |
| 전망은 기존 홈 형식 | 원본 `HomeRecommendedSection`의 `hp-analysis-grid`(본문 + 우측 카드) 구조를 따라 본문 2/3 + AI 예상 스코어 1/3 |
| '예측값입니다' 등 면책 문장 제거 | "실제 경기 결과가 아닌…", "저장된 한 번의 생성 결과입니다", "생성된 문장을 그대로 옮겼습니다", "이 서비스의 판단과는 별개입니다", 목업 안내 박스, 바닥 문구까지 본문에서 전부 삭제 |
| 주목 선수를 부상처럼 팀별 좌우 | `byTeam()`이 외부 팀 ID로 묶어 홈(맨시티) 왼쪽·원정(풀럼) 오른쪽, 각 팀 2명을 세로 배치. 부상과 동일한 컬럼 폭·헤더·사진 규칙 공유 |
| 외부 전망 옆 배당 | `mm-evidence` 2단(매체 3곳 왼쪽 + 배당 오른쪽). 배당 값은 전부 `-` |

추가로 원본 홈의 밀도에 맞춰 섹션 간격을 32px 단위로 줄였다(이전 96/72px → 32px). 1440 전체 높이가 3149px에서 **1653px**로 줄었고, 모바일은 2613px다. 마케팅 hero·랜덤 테마·폰트 변경은 없다.

삭제 문구 검증: 렌더된 본문에서 `예측값입니다`, `실제 경기 결과`, `저장된`, `그대로 옮겼`, `판단과는 별개`, `목업입니다`, `API-Football 경기 ID`, `로컬 JSON` 모두 **absent**.

JSON의 `caveat`·`odds_note`는 파일에 남아 있으나 UI에서 참조하지 않아 화면에 나오지 않는다.

Hallmark는 `redesign: polish` + `kept layout`으로 기록했고, 원본 유지 레이아웃에 landing 규칙을 강제하지 않도록 6b·79·44c를 kept-layout 사유로 waive했다. sloplint 결과 `77`(섹션 수)과 `79`(첫 화면 아래 여백)는 waive 대상이 아닌 structural NOTE로 2건 출력되며, 원본 홈 밀도를 유지하라는 요구에 따른 의도된 결과다.

## 실행 URL

| 대상 | URL | 상태 |
|---|---|---|
| 원래 추천 홈 (격리 원본, c4d7d32) | http://127.0.0.1:5174/ | 200 |
| 새 디자인 목업 (단일 경기) | http://127.0.0.1:5174/mock/man-city-fulham | 200 |
| 기존 관리자 프론트 | http://127.0.0.1:5173/ | 200 (변경 없음) |
| 기존 백엔드 | http://127.0.0.1:8000/ | 200 (변경 없음) |

포트 5174가 비어 있어 그대로 사용했다. 두 화면은 같은 격리 copy의 같은 서버에서 뜬다. 원본만 보려면 `/`, 목업만 보려면 `/mock/man-city-fulham`.

## 원본 재현

- `git archive c4d7d32 frontend`로 296개 파일을 `out/home-preview-mock/original-frontend/`에 격리 export했다. 현재 worktree의 `frontend/`는 읽지도 쓰지도 않았다(20:29 이후 변경 파일 0개, `frontend/node_modules` 변경 0개).
- 의존성은 원본 `package-lock.json`으로 `npm ci` 격리 설치했다. 첫 설치는 세션 환경의 `NODE_ENV=production` 때문에 devDependencies(vite 포함)가 빠져 서버가 뜨지 않았고, `--include=dev`로 다시 설치해 해결했다.
- 원본 홈은 `/api/v1/home/recommendations`와 `/api/v1/home/fixtures/:id/prematch`를 부르는데, 이 저장소의 현재 backend에는 두 경로가 없다(openapi 33개 경로 확인, `/api/v1/home/*` 없음). 그래서 격리 copy 안에서만 두 가지를 추가했다.
  - `src/mocks/handlers/home-preview.ts`: 원본이 이미 갖고 있던 샘플 빌더(`buildMockRecommendations`, `buildMockPreview`, `buildMockResponse`)로 두 응답을 만든다.
  - `src/lib/api/homePreview.ts`의 `is_mock` 가드 한 줄 완화: 샘플 payload를 화면에 서빙하기 위해서다. **격리 copy에만 적용했고 제품 파일은 그대로다.**
- 결과: 원본 추천 홈이 추천 경기 캐러셀·대진·프리뷰·주목선수·부상·최근 5경기·외부 전망·배당까지 원래 배치 그대로 렌더된다(캡처 참조). 원본 데이터는 원본이 가진 샘플(아스널-리버풀 등)이고, 맨시티-풀럼 실데이터는 목업 경로에만 있다.

## 목업 데이터

- `out/home-preview-mock/mock/match-city-fulham.json` 한 파일. 값은 `docs/implementation/match-preview/evidence/ps05-live/reader-preview-9c079eea.json`(outlook v2)과 같은 실행의 live 증거, 그리고 `evidence/r4-information-bundle/source-bundle.json`(경기 정체성)에서만 옮겼다.
- 필드: `fixture`(경기 ID 1557474, 킥오프 2026-11-21T12:30Z, 팀 외부 ID 50/36) · `ai_forecast`(본문·lean·score 2-0·reasoning 2줄) · `players` 4명(팀별 2명, 선정 이유 각각 별도 필드) · `injuries` 4명(상태 원문 유지: 결장(확정 표기) 1, 출전 불확실 3) · `external_forecasts` 3곳(Forebet·FootyPulse·WinDrawWin, 본문 그대로) · `odds: null`.
- 배당은 원본 증거에 값이 없어 영역을 만들지 않았다. 화면 본문 밖 목업 안내 박스에만 "배당 영역을 넣지 않았습니다"와 사유를 적었다.
- AI 2-0은 "AI 예상 스코어 · 실제 경기 결과가 아닌 AI 예측값입니다"로만 표기하고, 실제 스코어처럼 쓰지 않았다.
- 수집/검증/재시도/진단 문구는 본문에서 뺐다. 선수·부상·매체 문장은 증거 원문 그대로다.
- 이 JSON은 최종 API 계약이 아니라 목업용 초안이다(`_meta.contract_status`에 명시).

## 이미지

- 팀 배지: `https://media.api-sports.io/football/teams/{50,36}.png` (DB 내부 13/4 아님, 외부 ID 사용)
- 선수 사진: `https://media.api-sports.io/football/players/{external_id}.png` — 1100 홀란드, 156477 셰르키, 389315 킹, 278133 보브, 19281 세메뇨, 67971 게히, 19025 케어니
- 실 렌더 GET 결과 v2에서도 **10/10 로드**(`evidence-photos-v2.json`): 배지 2장 + 선수 8장, 모두 150x150 원본이 지정 박스에 들어갔다. 실패 시 같은 선수 이름 텍스트로만 대체하도록 코드에 fallback을 두었고, 실제로는 발동하지 않았다.

## Hallmark

- `--fast` 스파이크로 진행. 원본 `global.css`·`leagues.css` 토큰(Pretendard, light/dark, header 56px, EPL 색)을 그대로 쓰고 테마를 갈아엎지 않았다.
- 스탬프·critique·waiver는 `src/styles/match-mock.css` 첫 줄부터 선언. waive 3건: 1(Pretendard를 브랜드 display로 유지), 65(프로젝트 중성지·Pretendard 유지, 크림 paper/세리프 도입 안 함), 74(EPL 리그 토큰이 프로젝트 자체 팔레트).
- 토큰은 `src/styles/match-mock/tokens.css`의 `:root`/`html.dark`에만 있고, CSS 본문에는 색 리터럴이 없다. focus-visible, `prefers-reduced-motion`, `overflow-x: clip`, `minmax(0,1fr)` 이미지 그리드, 4px 스케일 유지.
- `sloplint --render` v2 최종: **0 FAIL, 0 WARN, 2 NOTE**(3 files + 1 URL). NOTE 2건은 섹션 수(77)와 첫 화면 아래 여백(79)으로, kept-layout 사유다. 렌더 티어가 실제로 5장을 찍었다(v2: 1440-full 1440x1653, 375 2613).
- 빌드 로그: `out/home-preview-mock/.hallmark/log.json`.

## 캡처

- v3 홈 임베드: `captures/home-embedded-v3/home-embedded-home-desktop.png`, `...-phone.png`, `home-embedded-dark-home-desktop.png`, 패널 전체 `home-panel-home-desktop-part.png`
- v2 목업: `captures/mock-5174-v2/mock-v2-home-desktop.png`, `...-phone.png`, `mock-v2-dark-home-desktop.png`
- v1 목업(보존): `captures/mock-5174/mock-city-fulham-home-desktop.png` 외 2장
- 원본 추천 홈: `captures/original-home-5174/original-recommended-home-home-desktop.png`, `...-phone.png`
- 새 목업: `captures/mock-5174/mock-city-fulham-home-desktop.png`(2880x6220), `...-phone.png`(780x8852), `...-dark-home-desktop.png`
- sloplint 렌더: `.hallmark/shots/`(1280x800, 1440x900, 1920x1080, 1440 full, 375)

## 검증

- `vue-tsc --noEmit -p tsconfig.app.json` 통과(exit 0). pytest/vitest/전체 빌드는 범위상 실행하지 않았다.
- 다크 모드·375px에서 가로 스크롤 없음(`docWidth` 1440/375, overflow-x clip), 콘솔 에러 0.
- 원본 라우트(`/`, `/home/mock`) 재확인: 정상 렌더, 셸 스타일 변경 영향 없음.

## 한계·남은 일

- 원본 화면은 제품 backend가 아니라 격리 copy의 MSW 샘플 응답으로 떴다. 실 API 응답 형태를 확인한 캡처는 아니다.
- 원본 copy에는 렌더 확인용으로만 두 가지 스파이크 수정(핸들러 추가, `is_mock` 가드 완화)이 들어 있다. 제품에는 반영되지 않았다.
- 최종 JSON 스키마 확정, 제품 홈/관리자 이식, 배당 데이터 소스 연결은 사용자가 이 목업 디자인을 확인한 뒤의 작업이다.
- 이 워커의 작업은 여기서 종료(EDITING STOPPED). 서버 5174는 사용자가 확인할 수 있도록 켜 둔 상태다.

## v4: 전망 근거 분리·인물별 패널·매체/배당 분리 패널

사용자 승인 디자인 정제. 같은 격리 목업 안에서만 수정했고, 실제 실행 세션 모델은 `deepseek-ai/deepseek-v4.1-flash-1017`(DSH 프로필 `dsh-tui`, 세션 `2fd7c24e-9b61-4df5-8558-a62d56511aeb`의 세션 로그 `"model"` 필드로 확인)이다.

수정 파일(소유 범위 내 3개): `src/components/home-preview/MatchPreviewBody.vue`, `src/styles/match-mock.css`, `src/styles/match-mock/tokens.css`.

| 요구 | 반영 |
|---|---|
| 전망 2/3 + 점수 1/3 유지 | `.mm-analysis` 그리드 유지(712px / 356px @1440) |
| 문장 단위 문단 분리, 문구 불변 | `forecast.paragraph`를 문장 경계로만 split해 문단 2개로 렌더. 단어·문장 재작성 0 |
| 근거를 별도 전망 근거 영역으로 | 점수 카드 아래에 있던 `reasoning` 2건을 좌측 본문 아래 **전망 근거** 블록으로 이동(번호·문장 그대로) |
| 점수 패널은 3요소만 | 패널 텍스트가 `AI 예상 스코어 2 : 0 홈 우세 예상` — 라벨·점수·lean만 남기고 근거 제거 |
| 이름·사진 확대 | 데스크톱 이름 21px(`clamp(18px,1.5vw,21px)`), 사진 112×128px. 780px 이하 88×104, 520px 이하 76×92 |
| 인물별 팀 틴트 패널 | 선수·부상 각 항목을 개별 패널로 감쌈. 홈(맨시티) sky tint `#eef6fc`, 원정(풀럼) neutral `#f6f5f2`, 다크 `#11202c` / `#171a1f`. 플랫 단색 + 1px 경계, 중첩 카드 없음 |
| 매체·배당 2개 패널 | 각각 `.mm-panel`로 감싼 별도 컨테이너(712px / 356px), 매체는 행 구분선 유지, 배당은 3열 값 그대로 `-` |
| 루트/standalone 동일 본문 | 동일 컴포넌트이므로 본문 텍스트가 완전 일치(헤드만 standalone 전용). parity 확인: `identical after removing standalone head: true` |

검증(필요 최소 범위만):
- `vue-tsc --noEmit` exit 0
- `sloplint --render` 1 batched: **0 FAIL / 0 WARN**, REFLEX 1건은 손대지 않은 원본 홈 CSS의 10px 텍스트, NOTE는 kept-layout 성격
- 수정 배치 1회 후 확인 1회: 새로 만든 `.mm-panel` 텍스트 색 미지정(WARN 41)과 3px 오프스케일(NOTE 24b)을 고쳐 재확인
- 1440/1280/375/다크: 콘솔 에러 0, 가로 overflow 0, 클리핑 0, 사진 8/8(배지 포함 10/10)
- 본문 보존 검증: forecast 문단·근거 2건·선수 선정 이유 4건·부상 상세/영향/상태 4건·매체 3곳 문장·발행사·외부 링크 3개 모두 원문 포함 확인
- 확인 중 발견·수정한 실제 결함: 원본 `.hp-page h3 { font-size: 16px }`가 임베드 안 선수 이름 h3를 다시 16px로 눌러, `.mm-body .mm-entry__name`으로 특이도를 올려 21px 유지

한계: 원본 홈 CSS의 10px 텍스트 REFLEX는 원본 파일이라 이번 범위에서 고치지 않았다. 격리 copy의 MSW 샘플 응답이므로 운영 홈 응답 재현은 아니다. JSON·문구·URL·부상 상태·서버는 그대로다.


## v4 캡처

- 루트: `captures/home-embedded-v4/v4-home-home-desktop.png`, `...-phone.png`, `v4-home-dark-home-desktop.png`, 패널 전체 `v4-panel-home-desktop-part.png`
- v3 캡처는 `captures/home-embedded-v3/`에 그대로 보존.

## v4b 정정: 인물 패널을 팀 틴트 그라데이션으로

v4 보고에서 패널 배경을 "flat solid tint"로 적었고 CSS에도 그라데이션이 없었다. 사용자는 그라데이션 패널을 명시 요청했으므로, 요청을 우선해 패널 배경만 정정했다. Hallmark의 그라데이션 기본값은 사용자의 명시 요청을 덮지 않는다.

변경 범위(2개 파일, 배경만):
- `src/styles/match-mock/tokens.css`: 그라데이션 끝점 토큰 추가. 라이트 홈 `#e2f0fa → #f8fcff`, 원정 `#efede7 → #fbfaf8`. 다크 홈 `#17293a → #0e1a24`, 원정 `#1d2127 → #12151a`. 기존 tint/edge 토큰은 그대로 두고 fallback으로 유지.
- `src/styles/match-mock.css`: `.mm-entry`의 `background` 한 줄을 `background-color` + `background-image: linear-gradient(135deg, from 0%, to 100%)`로 교체. `.mm-team--home` / `.mm-team--away`가 끝점 토큰을 넘긴다.

그대로 유지한 것: 크기(이름 21px, 사진 112×128, 폰 88×104 / 76×92), 그리드(2/3–1/3, 팀 컬럼 524+524), 여백, 데이터·문구·URL·부상 상태, 매체/배당 분리 패널, 단일 패널 스크롤.

스코프 확인 1회(1440 라이트·다크, 375 라이트):
- 렌더된 배경이 실제 그라데이션: 라이트 홈 `linear-gradient(135deg, rgb(226,240,250) 0%, rgb(248,252,255) 100%)`, 원정 `rgb(239,237,231) → rgb(251,250,248)`; 다크 홈 `rgb(23,41,58) → rgb(14,26,36)`, 원정 `rgb(29,33,39) → rgb(18,21,26)`. 서로 다른 그라데이션 2종, 8개 패널 전부 적용.
- 가독성(텍스트 대 gradient 양 끝점 최소 대비): 라이트 7.32:1(보조 텍스트) / 15.15:1(본문), 다크 8.99:1 / 12.52:1. 모두 WCAG AA 이상.
- 레이아웃 불변: 이름 21px, 사진 112×128 유지, 가로 overflow 0, 콘솔 에러 0, 사진 10/10.
- 캡처: `captures/home-embedded-v4/v4b-fullbody-home-desktop.png`, `v4b-fullbody-dark-home-desktop.png` — standalone 본문 전체(전망 제목 y173, 전망 근거 y369, 점수 패널 y209, 첫 선수 패널 y567, 마지막 부상 패널 y1199, 매체/배당 패널 y1426, 페이지 높이 1834)를 담아 v4 캡처가 놓쳤던 전망·근거·매체/배당 영역을 포함한다.

타입체크·린트·테스트는 이 정정에서 다시 돌리지 않았다(요청대로 스코프 시각 확인 1회).

## v5: 합성 3행 배당 패널 (디자인 확인용)

사용자 승인 지시에 따라 격리 목업의 배당 패널을 최대 3개 북메이커 행으로 구현했다. 엔드포인트 결정은 **API-Football `/odds`**(`/predictions` 아님)이다. 외부 사이트 배당을 먼저 쓰고, 남는 자리를 API-Football Odds가 서로 다른 실제 북메이커로 채워 총 3개 고유 행을 만드는 구성이다. 이 목업은 디자인 확인용이므로 아래 값은 **명시적 합성 예시**다.

| 북메이커 | 맨체스터 시티 승 | 무승부 | 풀럼 승 | 채널 |
|---|---:|---:|---:|---|
| Bet365 | 1.35 | 5.20 | 8.00 | site |
| William Hill | 1.36 | 5.00 | 8.50 | site |
| Unibet | 1.34 | 5.25 | 8.20 | api_football_odds |

- 패널 제목은 **예시 배당**. 컬럼은 북메이커 / 맨체스터 시티 승 / 무승부 / 풀럼 승.
- 셋째 행(Unibet)에 작은 **API-Football Odds 보충** 표기를 달아 fallback 구성을 보여준다.
- JSON: `odds.synthetic: true`, `odds.label: "예시 배당"`, `market: 1x2_90min`, `format: decimal`, 행마다 `source_channel`(`site`/`api_football_odds`), `attribution`, `note`("합성 예시 배당. 실제 수집값·조회 시각 아님.").
- **추정 시각·실제 조회 주장 없음**: 패널 텍스트에 시각 문자열이나 "수집/조회" 문구가 없음을 확인(`textHasTime: false`).
- 실제 저장 생성 증거는 그대로다: `evidence/ps05-live/reader-preview-9c079eea.json`의 `section_odds-writer.odds == []`, `section_odds` 품질 `insufficient`. 이 v5 값은 그 증거를 바꾸지 않는다.

수정 파일: `out/home-preview-mock/mock/match-city-fulham.json`, `src/components/home-preview/MatchPreviewBody.vue`(타입·테이블), `src/styles/match-mock.css`(`.mm-odds` 테이블 스타일). 그 외 변경 없음.

검증:
- 타입이 바뀌었으므로 `vue-tsc --noEmit` 1회 → exit 0
- 1440 라이트/다크, 375 라이트에서 3행·4컬럼 렌더, 콘솔 에러 0, 가로 overflow 0
- 보존 확인: 인물 패널 8개 전부 그라데이션 유지, 이름 21px, 사진 112×128, 매체 3건, 전망 본문·전망 근거 유지, 사진 8/8
- 루트 `/`와 standalone `/mock/man-city-fulham` 동일 표 렌더
- 캡처: `captures/odds-3rows/odds-panel-home-desktop-part.png`(2176×728), `odds-panel-phone-home-phone-part.png`(636×1525) — 매체+배당 패널 영역

남은 한계: 이 배당은 합성 예시이며 실제 수집 파이프라인·계약 검증 결과가 아니다. 운영 API 연동/예측(predictions) 경로/환산/모델·HTTP·DB 호출은 이번 범위에 포함하지 않았다.

EDITING STOPPED
