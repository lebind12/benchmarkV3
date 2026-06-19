# BroadcastProgram View Revision Scope

작성일: 2026-06-11

관련 문서:
- `docs/features/broadcast-match-program.md`
- `docs/features/broadcast-match-program.spec.md`
- `docs/features/broadcast-match-program.devplan.md`
- `docs/spec/broadcast-program-bottom-info-design.md`

## 1. 배경

클라이언트 피드백:

- 경기 이벤트 관련 알림은 제거
- 캐러셀 제거
- 라인업 상시표시
- 라인업은 번호, 이름 순
- 번호에는 축구공 또는 티셔츠 모양 SVG 사용
- 경기 스탯은 단축키로 전환
- 단축키 방식이 별로면 라인업 화면에 마우스 버튼 추가

추가 기획 결정:

- 라인업은 최초 선발 XI 를 기준으로 시작하되, 경기 중 교체 이벤트가 들어오면 현재 출전 선수 11명에 반영한다.
- 단축키는 `Ctrl+Z`, `Ctrl+X`, `Ctrl+C`, `Ctrl+V`, `Ctrl+B` 순으로 하단 view 를 전환한다. 스탯 view 단축키는 같은 키를 다시 누르면 라인업 view 로 돌아온다.

이번 변경은 기존 `BroadcastProgramApp` 의 하단 정보 캐러셀 중심 구조를 라인업 상시표시 중심 구조로 바꾸는 작업이다. 경기 영상 영역을 가리지 않는다는 기존 방송 프로그램 원칙은 유지한다.

## 2. 변경 목표

기존 화면에서 자동으로 순환되던 이벤트/스탯/배너 카드를 제거하고, 방송 중 항상 읽히는 라인업 패널을 고정 표시한다.

목표 상태:

- 좌측 상단 경기 영상 영역은 계속 UI overlay 없이 유지한다.
- 좌측 하단 정보 영역은 캐러셀이 아니라 라인업 기본 화면으로 사용한다.
- 경기 이벤트 알림, 이벤트 splash, 이벤트 카드, 이벤트 삽입 큐는 화면에서 제거한다.
- 경기 스탯은 상시 자동 노출하지 않고 사용자가 단축키로 일시 전환한다.
- 단축키 조작성이 낮으면 라인업 영역 안에 최소한의 마우스 전환 버튼을 둔다.

## 3. 범위 요약

| 영역 | 현재 | 변경 |
|---|---|---|
| 하단 정보 영역 | 자동 vertical carousel | 고정 라인업 패널 |
| 이벤트 알림 | 골/카드/교체/VAR 알림 및 splash 카드 | 제거 |
| 이벤트 큐 | 새 이벤트를 현재 카드 다음 위치에 삽입 | 제거 |
| 스탯 노출 | 캐러셀 항목으로 자동 순환 | 단축키로 라인업/스탯 화면 전환 |
| 라인업 | 데이터 생성은 있으나 주요 화면 아님 | 기본 상시 화면, 교체 이벤트 반영 |
| 선수 표기 | 카드 종류별로 상이 | 번호 아이콘 + 이름 순으로 통일 |
| 조작 | 데모 키보드 일부 존재 | `Ctrl+Z/X/C/V/B` view 전환으로 정리 |

## 4. 유지할 것

- 페이지와 entry:
  - `frontend/broadcast-program.html`
  - `frontend/src/broadcastProgram.ts`
  - `frontend/src/BroadcastProgramApp.vue`
- 기본 1920x1080 방송 레이아웃
- 좌측 경기 영상, 우측 크로마키 채팅/캐릭터 영역 구조
- 우측 크로마키 배경 `#00B140`
- 경기 영상 영역 내부 UI overlay 금지
- API-Football live mode 및 10초 polling 정책
- 팀명/선수명 한글 fallback 처리
- 라인업, 스탯 데이터 fetch 자체
- 월드컵 테마의 큰 방향

## 5. 제거할 것

### 5.1 화면 기능

- 하단 정보 캐러셀 자동 순환
- 배너 카드
- 이미지 배너 카드
- 이벤트 splash 카드
- 이벤트 상세 카드
- 신규 이벤트 알림 삽입 연출
- 골/자책골/카드/교체/VAR 이벤트 전용 화면 알림
- `CAROUSEL_INTERVAL_MS` 기반 타이머 UX

### 5.2 코드 후보

구현 시 제거 또는 축소 검토 대상:

- `InfoCard` 의 이벤트/배너/캐러셀 중심 필드
- `EventInfoCard`, `EventSplashCard`, `EventDisplayCard`, `CarouselInfoCard`
- `carouselQueue`, `carouselCards`, `activeCardIndex`
- `insertEventCardsAfterCurrent`
- `syncLiveEventCards`
- `createEventDisplayCards`
- `createEventSplashCard`
- 캐러셀 transition handler
- 이벤트 splash 이미지 import
- 하단 캐러셀 전용 CSS

주의: API-Football 이벤트 fetch 자체를 바로 제거할지는 별도 판단한다. 화면 알림은 제거하되, 향후 타임라인이나 로그에 쓸 가능성이 있으면 데이터 수집 함수는 남길 수 있다. 단 이번 화면에는 렌더하지 않는다.

## 6. 새 기본 화면: Lineup Panel

하단 정보 영역의 기본 view 는 `lineup` 이다.

### 6.1 표시 구조

권장 구조:

```text
┌──────────────────────────────────────────────────────────────┐
│ HOME TEAM / FORMATION                    AWAY TEAM / FORMATION│
├──────────────────────────────┬───────────────────────────────┤
│  [shirt] 1  선수명            │  [shirt] 1  선수명             │
│  [shirt] 4  선수명            │  [shirt] 2  선수명             │
│  [ball]  7  선수명            │  [shirt] 9  선수명             │
│  ...                          │  ...                           │
└──────────────────────────────┴───────────────────────────────┘
```

표기 규칙:

- 홈/원정 2열 병렬 표시
- 각 선수 행은 `번호 아이콘`, `번호`, `이름` 순
- 이름은 한글 번역명이 있으면 한글, 없으면 원문 fallback
- 최초 데이터는 선발 XI 를 기준으로 표시한다.
- 경기 중 교체 이벤트가 들어오면 현재 출전 11명으로 갱신한다.
- 교체 명단 전체를 별도 목록으로 상시 노출하지는 않는다.
- 포메이션은 팀 헤더에 표시한다.

### 6.2 2팀 11인 표시 가능성

기존 P1 레이아웃 기준 하단 정보 영역 크기:

- 전체 기준: `1920 x 1080`
- 좌측 영역: `78% width`, 약 `1498px`
- 하단 영역: `22% height`, 약 `238px`

홈/원정 2열에 각 팀 11명을 세로 단일 리스트로 넣을 경우:

- 팀 헤더와 상단 장식 영역을 제외하면 선수 목록에 쓸 수 있는 높이는 약 `185-205px` 정도다.
- 11명을 모두 넣으려면 선수 1행당 약 `16.8-18.6px` 안에 들어가야 한다.
- 기술적으로는 가능하지만, 방송 캡처 가독성 기준으로는 글자가 작고 행간이 답답해질 가능성이 높다.

따라서 1차 권장 배치는 `홈/원정 2팀 병렬`은 유지하되, 각 팀 내부를 `6명 + 5명`의 미니 2열로 나누는 방식이다.

```text
┌──────────────────────────────────────────────────────────────┐
│ HOME TEAM / 4-2-3-1                 AWAY TEAM / 4-3-3         │
├──────────────────────────────┬───────────────────────────────┤
│ [shirt] 1  이름  [shirt] 6 이름 │ [shirt] 1  이름  [shirt] 6 이름 │
│ [shirt] 2  이름  [shirt] 7 이름 │ [shirt] 2  이름  [shirt] 7 이름 │
│ [shirt] 3  이름  [shirt] 8 이름 │ [shirt] 3  이름  [shirt] 8 이름 │
│ [shirt] 4  이름  [shirt] 9 이름 │ [shirt] 4  이름  [shirt] 9 이름 │
│ [shirt] 5  이름  [shirt]10 이름 │ [shirt] 5  이름  [shirt]10 이름 │
│                 [shirt]11 이름 │                 [shirt]11 이름 │
└──────────────────────────────┴───────────────────────────────┘
```

이 방식이면 선수 행 높이를 약 `28-32px` 로 확보할 수 있어, 번호 아이콘과 한글 이름을 방송용으로 읽히게 만들 가능성이 높다.

### 6.3 번호 아이콘

요구사항 후보:

- 축구공 SVG
- 티셔츠 SVG

1차 추천:

- 선발 선수 기본 아이콘은 티셔츠 SVG
- 골키퍼 또는 특정 강조 상태가 필요할 때만 변형을 고려
- 축구공 SVG 는 득점자 표시처럼 의미가 강하므로, 이벤트 알림을 제거하는 이번 범위에서는 기본 번호 아이콘으로는 티셔츠가 더 명확하다.

아이콘 구현 원칙:

- 기존 코드 기반 SVG 또는 `frontend/src/assets/broadcast/` 아래 수동 SVG 사용
- 공식 로고/팀 엠블럼이 아니므로 임의 제작 가능
- 크로마키 유사 색상 사용 금지
- 번호와 아이콘은 고정폭으로 잡아 이름 정렬이 흔들리지 않게 한다.

## 7. 보조 화면: Stats View

경기 스탯은 기본 화면이 아니라 전환 view 로 둔다.

### 7.1 단축키

권장 키:

| 키 | 동작 |
|---|---|
| `Ctrl+Z` | 라인업 view, 현재 출전 11명 |
| `Ctrl+X` | 공격 스탯 view |
| `Ctrl+C` | 찬스 스탯 view |
| `Ctrl+V` | 경기 운영 스탯 view |
| `Ctrl+B` | 징계/수비 스탯 view |
| `Esc` | 라인업 view 로 복귀 |

토글 규칙:

- 현재 라인업 view 에서 `Ctrl+X/C/V/B` 를 누르면 해당 stats view 로 전환한다.
- 현재 stats view 에서 같은 단축키를 다시 누르면 라인업 view 로 복귀한다.
- 현재 stats view 에서 다른 stats 단축키를 누르면 해당 stats view 로 바로 전환한다.
- `Ctrl+Z` 와 `Esc` 는 언제나 라인업 view 로 복귀한다.

스탯 view 제안:

| View | 단축키 | 포함 지표 | 이유 |
|---|---|---|---|
| Lineup | `Ctrl+Z` | 현재 출전 11명, 포메이션, 교체 반영 | 기본 화면 |
| Attack | `Ctrl+X` | 점유율, 전체 슈팅, 유효 슈팅 | 가장 자주 쓰는 경기 흐름 요약 |
| Chance | `Ctrl+C` | 코너킥, 오프사이드, 박스 안 슈팅 또는 기대 위협 후보 | 공격 기회 성격의 묶음 |
| Control | `Ctrl+V` | 패스 성공률, 총 패스, 최근 흐름 후보 | 경기 장악/운영 설명용 |
| Discipline | `Ctrl+B` | 파울, 옐로카드, 레드카드 | 카드/거친 경기 흐름 설명용 |

API-Football live statistics 에서 일부 지표가 없을 수 있으므로, 각 view 는 지표별 fallback 을 둔다.

Fallback 우선순위:

- Chance view: `Corner Kicks`, `Offsides`, `Shots insidebox`, 없으면 `Total Shots`
- Control view: `Passes %`, `Total passes`, `Passes accurate`, 없으면 `Ball Possession`
- Discipline view: `Fouls`, `Yellow Cards`, `Red Cards`, 없으면 카드 지표만 표시

운영 원칙:

- 방송 송출 중 실수 입력 가능성을 줄이기 위해 단축키 수를 최소화한다.
- input/select/textarea 등 포커스 가능한 요소가 생기면 키 입력을 무시한다.
- 기본 view 는 항상 `lineup` 이다.
- 같은 stats 단축키를 다시 누르면 `lineup` 으로 돌아오는 토글 동작을 기본으로 한다.
- `Ctrl+C`, `Ctrl+V` 는 브라우저 기본 복사/붙여넣기와 충돌할 수 있다. 페이지에 입력 필드가 없고 방송 송출 전용 화면이라는 전제에서는 사용 가능하지만, 향후 제어 패널 input 이 생기면 단축키 충돌 방지 처리가 필요하다.

### 7.2 마우스 버튼 fallback

단축키 UX 가 별로면 하단 라인업 패널 내부 우상단에 작은 segmented control 을 추가한다.

버튼 후보:

- `LINEUP`
- `STATS`

조건:

- 영상 영역 안에는 버튼을 두지 않는다.
- 버튼은 크로마키 영역에 두지 않는다.
- 방송 캡처에 거슬리지 않게 작게 둔다.
- 구현 1차에서는 단축키를 우선하고, 버튼은 query param 또는 후속 작업으로 열어둘 수 있다.

## 8. 데이터 의존성

신규 백엔드 endpoint 는 필요하지 않다.

현재 live mode 의 데이터 중 계속 필요한 것:

- fixture summary: 팀, 스코어, 상태
- lineups: 팀별 formation, startXI, 선수 번호, 선수명, grid/pos
- statistics: 점유율, 슈팅, 유효슈팅, 코너킥, 파울, 카드 등
- events: 교체 이벤트를 현재 출전 11명에 반영하기 위한 데이터
- translations: 팀/선수 한글명

화면에서 더 이상 필요하지 않은 것:

- events 기반 alert card
- event splash asset
- 신규 이벤트 삽입 순서 관리

이벤트 데이터 처리 원칙:

- 골/카드/VAR 등은 하단 알림으로 렌더하지 않는다.
- 교체 이벤트만 라인업 상태 갱신에 사용한다.
- 교체 이벤트 수신 시 out player 의 기존 라인업 slot 에서 `OUT -> IN -> 하이라이트 선수` 순서의 애니메이션을 실행한다.
- 애니메이션이 slot 을 덮고 있는 중간 시점에 out player 를 현재 출전 목록에서 제거하고 in player 를 같은 팀 목록에 넣는다.
- 포지션/정렬 위치가 불명확하면 out player 의 기존 표시 위치를 in player 가 승계한다.
- 교체로 들어온 선수는 교체 적용 후에도 `IN` 라벨과 행 하이라이트를 유지한다. 단 이벤트 알림 카드처럼 별도 팝업화하지 않는다.

단, API 호출 비용과 응답 latency 를 줄이려면 live snapshot 생성 함수에서 전체 이벤트 fetch 를 유지하되 화면 변환 단계에서 substitution 만 사용하는 방식으로 시작하고, 필요 시 이벤트 종류 필터링 최적화를 후속 검토한다.

## 9. 테스트 범위

### 9.1 Unit

`frontend/tests/unit/BroadcastProgramApp.spec.ts` 수정 후보:

- 기본 렌더 시 lineup view 가 표시된다.
- 캐러셀 track/card/testid 가 표시되지 않는다.
- 이벤트 splash/event alert 가 표시되지 않는다.
- 선수 행이 번호, 이름 순으로 렌더된다.
- 선수 번호 아이콘이 렌더된다.
- 교체 이벤트가 들어오면 해당 선수 slot 에 `OUT -> IN` 애니메이션이 표시되고, 애니메이션 중간에 현재 출전 11명 목록이 갱신된다.
- `Ctrl+X`, `Ctrl+C`, `Ctrl+V`, `Ctrl+B` 입력 시 각 stats view 로 전환된다.
- 같은 stats 단축키를 다시 누르면 lineup view 로 복귀한다.
- `Ctrl+Z` 또는 `Esc` 입력 시 lineup view 로 복귀한다.
- lineups 데이터가 비어 있으면 안정적인 empty state 를 표시한다.

### 9.2 E2E

`frontend/e2e/broadcast-program.spec.ts` 수정 후보:

- 1920x1080 에서 좌측 영상 영역과 하단 라인업 영역이 겹치지 않는다.
- 우측 채팅/캐릭터 크로마키 영역은 유지된다.
- 경기 영상 영역 내부에 UI overlay 가 없다.
- 라인업 기본 화면이 캡처 기준으로 가독성 있게 표시된다.
- 교체 이벤트가 발생하면 라인업 내부 slot 에서만 애니메이션이 실행되고, 별도 이벤트 알림은 표시되지 않는다.
- `Ctrl+Z/X/C/V/B` 단축키로 하단 view 전환이 가능하다.

## 10. 구현 순서 제안

1. `BroadcastProgramApp.vue` 에서 화면 state 를 `lineup | stats` 로 단순화한다.
2. 하단 캐러셀 렌더링을 `ProgramBottomLineup` 성격의 고정 패널로 교체한다.
3. 이벤트 splash/alert 렌더링과 관련 asset import 를 제거한다.
4. lineups snapshot 데이터를 하단 패널용 view model 로 정리한다.
5. 선수 행을 번호 아이콘, 번호, 이름 순으로 렌더한다.
6. 교체 이벤트를 현재 출전 11명 view model 에 반영한다.
7. `Ctrl+Z`, `Ctrl+X`, `Ctrl+C`, `Ctrl+V`, `Ctrl+B`, `Esc` 단축키를 추가한다.
8. stats view 는 기존 스탯 카드/그래프 자산 중 필요한 부분만 재사용한다.
9. unit/e2e 테스트를 새 UX 기준으로 갱신한다.
10. Playwright screenshot 으로 1920x1080 방송 레이아웃을 확인한다.

## 11. Phase 구현 계획

### Phase 0. 현행 구조 정리

목표: 캐러셀/이벤트 알림 중심 코드와 새 라인업 중심 구조의 경계를 확정한다.

작업:

- `BroadcastProgramApp.vue` 의 현재 state, computed, timer, keyboard handler 목록 정리
- lineups/statistics/events snapshot 이 어디서 만들어지고 어떤 shape 로 내려오는지 확인
- 제거 대상 import, type, computed, CSS 범위 표시
- 기존 테스트 중 유지할 항목과 폐기할 항목 분류

DoD:

- 캐러셀 제거 시 함께 제거할 코드 목록이 확정된다.
- lineups, statistics, substitution events 를 새 view model 로 만들 수 있는 데이터 경로가 확인된다.

Phase 0 결과:

상태: 완료

확인 파일:

- `frontend/src/BroadcastProgramApp.vue`
- `frontend/src/lib/api/apiFootballLive.ts`
- `frontend/tests/unit/BroadcastProgramApp.spec.ts`
- `frontend/e2e/broadcast-program.spec.ts`

현행 데이터 경로:

| 데이터 | 생성 위치 | 현재 shape | 새 구현 활용 |
|---|---|---|---|
| fixture summary | `apiFootballLive.ts` `normalizeSnapshot` | `fixtureId`, `home`, `away`, `score`, `clock`, `status` | 유지 |
| lineups | `normalizeLineups` | team별 `players`, `shape`, `substituteNumbers` | 현재 출전 11명 view model 의 시작점 |
| statistics | `normalizeStatistics` | `label`, `home`, `away`, `homePct`, `awayPct` | 4개 stats view 의 원천 |
| events | `normalizeEvents` | goal/card/var/substitution 등 정규화 이벤트 | substitution 만 라인업 갱신에 사용 |
| translations | `applyBroadcastTranslations` | team/player/league 한글명 적용 | 유지 |

새 기획에 이미 충분한 데이터:

- `ApiFootballBroadcastLineup.players` 는 선발 XI 를 최대 11명까지 제공한다.
- `ApiFootballBroadcastLineup.substituteNumbers` 는 교체 투입 선수 번호 lookup 에 사용할 수 있다.
- `ApiFootballBroadcastEvent` 는 substitution 에 대해 `playerId/outPlayer/outPlayerNumber`, `assistId/inPlayer/inPlayerNumber` 를 제공한다.
- tick refresh 에서 lineups 는 유지되고 events/statistics/player ratings 는 갱신된다. 따라서 교체 반영은 화면 view model 에서 events 를 lineups 위에 적용하는 방식이 적합하다.

주의할 데이터 제약:

- `normalizeStatistics` 는 현재 `Ball Possession`, `Total Shots`, `Shots on Goal`, `Corner Kicks`, `Passes %`, `Yellow Cards`, `Red Cards`, `Fouls`, `Offsides` 만 한글 label 로 정규화한다.
- 기획의 `Shots insidebox`, `Total passes`, `Passes accurate` 는 아직 `statTypeMap` 에 없다. Phase 4 에서 필요하면 `apiFootballLive.ts` 의 stat label mapping 을 확장해야 한다.
- 교체 이벤트에서 in player 는 API-Football assist 필드를 사용한다. 현재 normalize 로직도 `assist` 를 in player 로 매핑하고 있으므로 이 전제를 유지한다.

`BroadcastProgramApp.vue` 현행 구조:

| 범주 | 현재 항목 | 판단 |
|---|---|---|
| live 상태 | `liveStatus`, `liveError`, `refreshApiFootballLive` | 유지하되 snapshot 저장 방식으로 변경 |
| theme | `themes`, `theme`, `themeVars`, `isAdminAllowed` | 유지 |
| carousel state | `activeCardIndex`, `carouselTransitionEnabled`, `baseInfoCards`, `carouselQueue`, `previousEventCards` | 제거 |
| carousel timers | `CAROUSEL_INTERVAL_MS`, `carouselTimer`, transition handler | 제거 |
| event queue | `seenEventIds`, `pendingEventCards`, `syncLiveEventCards`, `flushPendingEventCards` | 제거. substitution 적용 로직으로 대체 |
| base card sync | `createProgramMatchFromSnapshot`, `syncCarouselFromLiveMatch`, `resetCarouselForFixture`, `syncBaseInfoCards` | 제거 또는 새 snapshot/view model sync 로 대체 |
| stat helpers | `pickStat`, `statMetric`, `compactMetrics` | 일부 재사용 가능 |
| animations | possession/player rating animation refs/functions/watch | stats view 에서 유지 여부 판단. 1차는 단순화 권장 |
| demo mode | `demoEvents=all`, `loadDemoEventQueue`, `createDemoBroadcastEvents`, `i/k` 키 | 제거 또는 새 fixture demo 로 대체 |
| event rendering | event splash/event card/substitution card branches | 제거 |

제거 우선순위 높은 코드:

- 이벤트 splash 이미지 import 6종
- `matchStatsIntroUrl`, `worldCupKickoffBannerUrl` 기반 배너 카드가 새 UX 에 불필요하면 제거
- `InfoCard` 의 캐러셀/이벤트 중심 필드
- `EventInfoCard`, `EventSplashCard`, `EventDisplayCard`, `CarouselInfoCard`
- `insertEventCardsAfterCurrent`, `sortEventCards`, `createEventDisplayCards`, `createEventSplashCard`
- `programEventType`, `eventSplashType`, `eventLeftValue`, `eventRightValue`
- `handleInfoTrackTransitionEnd`, `manualNextBanner`, `manualPreviousBanner`, `handleDemoKeyboard`
- `carouselCards`, `activeVisibleCard`, `activeVisibleCardKind`, `infoTrackStyle`
- template 의 `program-bottom-carousel`, `program-info-track`, `program-info-card`, event/card/banner 분기
- carousel/event 관련 CSS class

유지 또는 재사용 후보:

- `PossessionPieChart` 는 Attack stats view 에서 재사용 가능
- `pickStat` 은 stats view grouping 에 재사용 가능
- `topRatedPlayerFromSnapshot` 은 이번 1차 범위에는 필수 아님. player focus view 가 빠지므로 제거 가능성이 높다.
- `playerNumberLabel` 은 선수 번호 표시 helper 로 재사용 가능
- demo snapshot 은 lineups 11명 검증용으로 확장해 재사용 가능하나, 현재는 2-3명만 있어 테스트 fixture 로는 부족하다.

테스트 영향:

- `frontend/tests/unit/BroadcastProgramApp.spec.ts` 의 대부분은 기존 캐러셀/event splash 동작을 검증하므로 새 UX 기준으로 대폭 재작성 대상이다.
- 유지 가능한 테스트 관점은 `ADMIN role`, `data-league`, `feed surface`, `right chroma slots`, `scorebug/lower-third 없음`, API-Football fetch stub 이다.
- 폐기/교체 대상은 `data-carousel-interval-ms`, `data-event-insert-index`, `program-info-card`, clone card, 7초 rotation, `demoEvents=all`, `i/k` 키, event insertion assertions 이다.
- `frontend/e2e/broadcast-program.spec.ts` 도 `program-bottom-carousel`, clone card, event card ids 를 기준으로 하므로 새 `program-bottom-panel`, lineup/stats shortcut 기준으로 교체해야 한다.

Phase 1 진입 조건:

- 새 state 는 `activeBottomView: 'lineup' | 'attack' | 'chance' | 'control' | 'discipline'` 로 시작한다.
- live data 는 `ProgramMatch`/`InfoCard` 로 변환하지 말고 `ApiFootballBroadcastSnapshot` 또는 새 `ProgramSnapshotViewModel` 로 보관한다.
- 캐러셀 제거 전이라도 `data-active-bottom-view` 를 먼저 추가하면 테스트 전환이 쉽다.

### Phase 1. 하단 view state 도입

목표: 캐러셀 상태를 걷어내기 전에 새 하단 view 전환 상태를 먼저 만든다.

작업:

- 하단 view type 정의: `lineup | attack | chance | control | discipline`
- 기본값은 `lineup`
- `Ctrl+Z/X/C/V/B`, `Esc` keyboard handler 구현
- 같은 stats 단축키 재입력 시 `lineup` 으로 돌아오는 toggle 규칙 구현
- 입력 요소 포커스 시 단축키 무시 처리

DoD:

- 단축키만으로 하단 view state 가 기대대로 전환된다.
- 아직 UI가 임시여도 `data-active-bottom-view` 같은 테스트 가능한 상태가 존재한다.

Phase 1 결과:

상태: 완료

변경 파일:

- `frontend/src/BroadcastProgramApp.vue`
- `frontend/tests/unit/BroadcastProgramApp.spec.ts`

구현 내용:

- `BottomView` type 추가: `lineup | attack | chance | control | discipline`
- `activeBottomView` state 추가, 기본값 `lineup`
- `data-active-bottom-view` 를 `program-stage` 와 하단 영역에 추가
- `Ctrl+Z/X/C/V/B`, `Esc` keyboard handler 추가
- 같은 stats 단축키 재입력 시 `lineup` 으로 복귀하는 toggle 규칙 구현
- stats view 상태에서 다른 stats 단축키를 누르면 해당 view 로 직접 전환
- input/select/textarea/contenteditable 에서 발생한 단축키 입력은 무시

검증:

- `npm run test:unit -- BroadcastProgramApp.spec.ts`
- `npm run type-check`

### Phase 2. 라인업 view model 구현

목표: 선발 XI 와 교체 이벤트를 합쳐 현재 출전 11명 목록을 만든다.

작업:

- team별 선발 XI 기반 `currentLineup` 생성
- 선수 표시 필드 정리: `id`, `number`, `name`, `position`, `grid`, `isSubstitutedIn`
- substitution event 처리
  - out player 제거
  - in player 삽입
  - 위치 정보가 부족하면 out player 의 표시 slot 승계
- 홈/원정 각각 11명 유지 보장
- translation fallback 유지
- lineups empty state 정의

DoD:

- 교체 이벤트가 들어오면 화면 알림 없이 현재 출전 11명 목록만 갱신된다.
- 선수명은 한글 translation 우선, 없으면 원문 fallback 으로 표시된다.
- 교체 명단 전체는 상시 렌더하지 않는다.

Phase 2 결과:

상태: 완료

구현 내용:

- `ApiFootballBroadcastSnapshot` 을 직접 보관하는 `liveSnapshot` state 로 전환
- 선발 XI 기반 `currentLineups` view model 추가
- substitution event 를 각 팀 라인업에 적용
- out player 의 slot 을 in player 가 승계
- 교체 투입 선수는 `isSubstitutedIn` 으로 표시 가능하게 구성
- 교체 명단 전체 상시 렌더링은 제외

### Phase 3. 하단 라인업 패널 렌더링

목표: 캐러셀 대신 방송 가독성 기준의 라인업 패널을 기본 화면으로 만든다.

작업:

- `bottom-info-carousel` 성격의 DOM 을 `bottom-program-panel` 또는 동등한 고정 패널로 교체
- 홈/원정 2팀 병렬 구조 렌더링
- 각 팀 내부는 1차로 `6+5` 미니 2열 배치 적용
- 선수 행 표기: 티셔츠 SVG 아이콘, 번호, 이름 순
- 포메이션/팀명 header 표시
- 교체 투입 선수의 짧은 강조 스타일 후보 적용
- 기존 캐러셀 transition/timer DOM 제거

DoD:

- 1920x1080 에서 양팀 현재 출전 11명이 모두 보인다.
- 선수 행이 번호 아이콘, 번호, 이름 순으로 안정적으로 정렬된다.
- 경기 영상 영역에는 UI overlay 가 없다.
- 우측 크로마키 영역은 기존처럼 유지된다.

Phase 3 결과:

상태: 완료

구현 내용:

- 하단 DOM 을 `program-bottom-panel` 기반 고정 패널로 교체
- 기본 view 를 `program-lineup-view` 로 구성
- 홈/원정 2팀 병렬 표시
- 각 팀 내부는 `6+5` 미니 2열 배치
- 선수 행은 티셔츠 SVG, 번호, 이름 순으로 렌더
- 교체 투입 선수는 `IN` 라벨과 강조 border 로 표시
- 경기 영상 영역과 우측 크로마키 영역은 유지

### Phase 4. 스탯 view 구현

목표: 단축키로 전환되는 4개 스탯 화면을 만든다.

작업:

- stats view 공통 패널 레이아웃 생성
- `Ctrl+X`: Attack, 점유율/전체 슈팅/유효 슈팅
- `Ctrl+C`: Chance, 코너킥/오프사이드/박스 안 슈팅 fallback
- `Ctrl+V`: Control, 패스 성공률/총 패스/정확한 패스 fallback
- `Ctrl+B`: Discipline, 파울/옐로카드/레드카드
- missing stat fallback UI 처리
- 같은 단축키 재입력 시 lineup 복귀 시각 상태 확인

DoD:

- 4개 stats view 가 모두 단축키로 전환된다.
- 같은 단축키를 다시 누르면 lineup view 로 돌아온다.
- 없는 지표가 있어도 빈 화면이나 런타임 오류가 발생하지 않는다.

Phase 4 결과:

상태: 완료

구현 내용:

- `attack`, `chance`, `control`, `discipline` stats view 추가
- `Ctrl+X/C/V/B` 전환과 같은 키 재입력 시 lineup 복귀 유지
- `Ctrl+Z`, `Esc` lineup 복귀 유지
- 각 stats view 는 `ApiFootballBroadcastStat` 기반 metric 카드로 렌더
- missing stat 은 빈 상태로 처리
- stats view 등장/퇴장 transition 추가
- stats view 진입 시 수치와 그래프가 `0` 에서 현재 값으로 증가
- 지표 성격별 그래프 타입 분리
  - 모든 그래프는 좌측 홈, 우측 어웨이 기준으로 배치
  - 모든 그래프는 홈/어웨이 팀 엠블럼을 표시하고, 로고가 없을 때만 팀 코드 fallback
  - `점유율`: Chart.js 기반 홈/어웨이 분리형 파이 그래프. 시작점은 12시이며 홈은 좌측 방향, 어웨이는 우측 방향으로 증가
  - `패스성공률`: 홈/어웨이 대결 막대그래프
  - 슈팅/코너킥/오프사이드/파울: 홈/어웨이 세로 막대그래프
  - 카드 지표: 징계 카운터형 막대그래프
  - 단일 막대 점유 차트는 사용하지 않음

현 구현의 지표 범위:

- Attack: `점유율`, `전체슈팅`, `유효슈팅`
- Chance: `코너킥`, `오프사이드`, fallback 성격의 `전체슈팅`
- Control: `패스성공률`, fallback 성격의 `점유율`
- Discipline: `파울`, `옐로카드`, `레드카드`

### Phase 5. 캐러셀/이벤트 알림 제거

목표: 새 UX 에 필요 없는 캐러셀, 이벤트 알림, splash asset 의 실제 의존성을 제거한다.

작업:

- 이벤트 splash 이미지 import 제거
- `InfoCard`, `EventInfoCard`, `EventSplashCard`, `CarouselInfoCard` 등 불필요 type 제거
- `carouselQueue`, timer, transition handler 제거
- 이벤트 알림 렌더링 분기 제거
- 캐러셀 전용 CSS 제거 또는 새 패널 CSS 로 대체
- events 데이터는 substitution 처리에 필요한 최소 경로만 유지

DoD:

- 화면에 이벤트 alert/splash/card 가 렌더되지 않는다.
- 캐러셀 timer 가 더 이상 동작하지 않는다.
- 이벤트 데이터는 교체 반영 외 렌더링에 사용되지 않는다.

Phase 5 결과:

상태: 완료

구현 내용:

- 이벤트 splash asset import 제거
- `InfoCard`, event card, carousel card 중심 구조 제거
- carousel queue, timer, transition handler 제거
- demoEvents 전용 `i/k` 키보드 조작 제거
- 이벤트 alert/splash/card 렌더링 제거
- events 데이터는 substitution 기반 라인업 갱신에만 사용
- 대상 unit test 를 새 UX 기준으로 갱신

검증:

- `npm run type-check`
- `npm run test:unit -- BroadcastProgramApp.spec.ts`

### Phase 6. 테스트 갱신

목표: 새 기획 기준으로 unit/e2e 검증을 재작성한다.

작업:

- `frontend/tests/unit/BroadcastProgramApp.spec.ts`
  - 기본 lineup 렌더
  - 양팀 11명 표시
  - 교체 이벤트 반영
  - 단축키 전환/toggle
  - 이벤트 alert 미렌더
  - empty state
- `frontend/e2e/broadcast-program.spec.ts`
  - 1920x1080 layout smoke
  - feed overlay 없음
  - right chroma 유지
  - lineup 가독성
  - stats shortcut 전환

DoD:

- 관련 unit 테스트가 통과한다.
- e2e smoke 가 새 화면 구조를 기준으로 통과한다.

Phase 6 결과:

상태: 완료

변경 파일:

- `frontend/tests/unit/BroadcastProgramApp.spec.ts`
- `frontend/e2e/broadcast-program.spec.ts`

구현 내용:

- unit test 를 라인업/스탯 패널 기준으로 갱신
- e2e test 를 `program-bottom-panel`, `program-lineup-view`, `program-stats-view` 기준으로 갱신
- e2e 에 API-Football/translation route mock 추가
- 1920x1080 레이아웃 비율 검증 유지
- 캐러셀/event splash/card 미렌더 검증 추가
- `Ctrl+X/C/V/B`, `Esc` 단축키 전환 검증 추가
- fixture route bridge 검증을 새 하단 패널 기준으로 갱신

검증:

- `npm run type-check`
- `npm run test:unit -- BroadcastProgramApp.spec.ts`
- `npm run test:e2e -- broadcast-program.spec.ts`

### Phase 7. 방송 화면 시각 검증

목표: 실제 방송 캡처 기준으로 2열 라인업과 스탯 view 가 읽히는지 확인한다.

작업:

- dev server 실행
- Playwright 또는 Browser 로 `broadcast-program.html` 1920x1080 캡처
- lineup view 캡처
- 4개 stats view 캡처
- 긴 선수명, 번호 없음, lineups 없음 케이스 확인
- 크로마키 색상 침범 여부 확인

DoD:

- 1920x1080 캡처에서 양팀 라인업이 잘리지 않는다.
- 텍스트 겹침이 없다.
- 영상 영역과 하단 패널이 겹치지 않는다.
- `#00B140` 은 우측 크로마키 영역에만 사용된다.

Phase 7 결과:

상태: 완료

캡처 산출물:

- `test-results/broadcast-program-phase7/lineup.png`
- `test-results/broadcast-program-phase7/attack.png`
- `test-results/broadcast-program-phase7/chance.png`
- `test-results/broadcast-program-phase7/control.png`
- `test-results/broadcast-program-phase7/discipline.png`
- `test-results/broadcast-program-phase7/report.json`

자동 점검 결과:

- stage: `1920 x 1080`
- feed: 약 `1497.59 x 842.39`
- bottom panel: 약 `1497.59 x 237.59`
- lineup panel: 22명 표시
- bottom panel 내부 overflow: `0`
- chroma slot 색상: `rgb(0, 177, 64)` 2개 영역
- 우측 크로마키 영역 밖 `#00B140` 사용: `0`

조정 사항:

- 두 자리 선수 번호에서 미세 overflow 가 감지되어 선수 번호 column 을 `2ch` 에서 `2.8ch` 로 확장했다.

검증:

- `npm run type-check`
- `npm run test:unit -- BroadcastProgramApp.spec.ts`
- `npm run test:e2e -- broadcast-program.spec.ts`

### 추가 반영. 라인업 교체 애니메이션

목표: 교체 이벤트가 들어왔을 때 라인업 값이 즉시 바뀌지 않고, 해당 선수 공간에서 `OUT -> IN -> 하이라이트 선수` 순서로 교체 결과를 반영한다.

구현 내용:

- substitution event 별 적용 상태와 애니메이션 상태를 분리
- 교체 이벤트 최초 수신 시 out player 의 기존 slot 을 찾아 애니메이션 queue 에 등록
- 애니메이션 초반에는 기존 선수가 slot 을 유지하고, `OUT` 패널이 위에서 내려와 slot 을 덮는다.
- `OUT` 패널이 덮은 상태에서 나가는 선수 정보가 우측에서 들어온다.
- `3.0s` 시점에 해당 substitution id 를 적용 목록에 추가하고 라인업 view model 을 갱신한다.
- 라인업 변경 이후에는 `IN` 패널이 아래에서 올라와 `OUT` 패널을 덮는다.
- `IN` 패널이 덮은 상태에서 들어오는 선수 정보가 좌측에서 들어온다.
- `OUT` 패널은 위로 빠지고, `IN` 패널은 아래로 빠진다.
- 총 시퀀스는 `8.0s` 로 두되, OUT/IN 패널의 진입 속도는 빠르게 유지하고 표시/대기 구간만 길게 둔다.
- `8.0s` 시점에 overlay 를 제거해 하이라이트된 투입 선수 행을 노출
- z-index 는 기본 라인업 콘텐츠 `1`, overlay container `20`, `OUT` 패널 `30`, `IN` 패널 `40` 으로 둔다.
- 동일 substitution id 는 polling 으로 다시 들어와도 재실행하지 않도록 timer/applied set 으로 중복 방지
- 컴포넌트 unmount 시 교체 애니메이션 timer 정리
- unit/e2e 테스트를 애니메이션 시작, 중간 반영, 종료 후 하이라이트 유지 상태로 갱신

검증:

- `npm run type-check`
- `npm run test:unit -- BroadcastProgramApp.spec.ts`
- `npm run test:e2e -- broadcast-program.spec.ts`

### Phase 8. 후속 선택지

목표: 1차 구현 후 사용성에 따라 추가할 수 있는 항목을 분리한다.

후속 후보:

- 하단 우상단 segmented control 추가
- stats view 자동 복귀 타이머
- 교체 투입 선수 하이라이트 세부 스타일 조정
- 단일 세로 리스트와 `6+5` 미니 2열 A/B 비교
- 실제 영상 소스 연동 정책 확정 후 program-config endpoint 검토

DoD:

- 1차 구현에 포함하지 않을 항목이 명확히 분리된다.
- 클라이언트 피드백을 받아도 core 구현을 흔들지 않고 후속 task 로 나눌 수 있다.

## 12. 미결정 사항

- 번호 아이콘을 축구공으로 할지 티셔츠로 할지 최종 선택
- 교체 투입 선수 행의 최종 스타일 강도
- 라인업을 팀별 단일 세로 리스트로 둘지, 팀 내부 `6+5` 미니 2열로 나눌지 여부
- 단축키만 둘지, 화면 버튼도 1차에 포함할지 여부
- stats view 전환 시 자동 복귀 타이머가 필요한지 여부

## 13. 1차 권장 결정

- 하단 기본 화면은 선발 XI 양팀 리스트로 고정한다.
- 교체 이벤트는 별도 알림 카드 없이 라인업 slot 내부 `OUT -> IN -> 하이라이트 선수` 흐름으로 반영하고, 투입 선수 하이라이트는 유지한다.
- 번호 아이콘은 티셔츠 SVG 로 시작한다.
- 교체 명단 전체 상시 노출은 제외한다.
- 라인업은 방송 가독성을 위해 팀 내부 `6+5` 미니 2열을 우선 검토한다.
- 조작은 단축키 우선으로 시작한다.
- 마우스 버튼은 단축키 사용성 확인 후 추가한다.
- 이벤트 데이터는 substitution 만 라인업 갱신에 사용하고, 나머지 이벤트 렌더링은 제거한다.
