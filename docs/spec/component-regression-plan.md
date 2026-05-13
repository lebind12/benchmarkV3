# Component Regression Plan

3 axes 의 회귀 검증 매트릭스. 본 문서는 검증 정책 SSOT이며, 신규 컴포넌트 추가 시 본 표에 row 를 추가하고 spec 을 갱신한다.

상위:
- UI 기준: `@docs/spec/ui-standards.md`
- 컬러: `@docs/spec/league-palette.md`
- FE 워크플로: `@docs/spec/fe-workflow.md`

## 1. Axes

| Axis | 대상 | Tool |
|---|---|---|
| **Size** | viewport 별 dimension / grid 비율 / 고정 px (header 56, MatchHeader 25vh) | Playwright `getBoundingClientRect` × 1280/1440/1920 |
| **Functionality** | 상호작용 (click, select, route sync, store mutation, toggle) | Playwright user-facing 시나리오 |
| **Theme** | 라이트/다크 토글, `[data-league]` swap, computed style 변화 | Playwright probe element + computed style |

순수 로직 (datetime / formations / league-colors / store action) 은 vitest 가 담당. E2E 는 viewable / theme-sensitive / layout-critical 영역만.

## 2. 컴포넌트 매트릭스

표기: ✅ 이미 cover / 🆕 본 plan 에서 추가 / — 해당 없음 (leaf 로직, vitest 가 충분)

### 2.1 common

| 컴포넌트 | Size | Functionality | Theme |
|---|---|---|---|
| AppHeader | 🆕 56px height, app-container 내부 nav | 🆕 nav 클릭 → route 이동, theme 토글 persist | ✅ (theme-league.spec.ts) |
| EmptyState | — | ✅ (vitest) | — |
| ErrorState | — | ✅ (vitest, FixtureCard) | — |
| PanelScroll | — | ✅ (vitest) | — |
| SkeletonCard | — | ✅ (간접: home/fixture 로딩 상태) | — |

### 2.2 home

| 컴포넌트 | Size | Functionality | Theme |
|---|---|---|---|
| HomeView | 🆕 grid 25/50/25, height calc(100vh-56) | ✅ (main-home.spec.ts) | — (per-fixture 카드에서) |
| LeftPanel | 🆕 logo 30% + cube 70% | ✅ S01 | — |
| CubeCarousel | 🆕 면 정사각, dot count = 4 | ✅ S11/12/13/14 (회전/일시정지/dot 클릭) | — |
| CenterPanel | 🆕 filter bar 고정 + 카드 list overflow | 🆕 FixtureFilters 클릭 → store.filter | — |
| FixtureFilters | — | 🆕 league/period 클릭 → activeFilter 갱신 | — |
| FixtureCard | — | ✅ (vitest) | 🆕 per-fixture [data-league] 적용 |
| RightPanel | 🆕 standings + top-players 비율 50/50 | ✅ | — |
| StandingsBlock | — | 🆕 league select → 갱신, 5리그 covered | 🆕 [data-league] 루트에 적용 |
| TopPlayersBlock | — | 🆕 league + metric select → 갱신 | 🆕 [data-league] 루트에 적용 |
| Cube faces (4종) | — | ✅ (S25 등 시나리오에서 컨텐츠 확인) | — |

### 2.3 fixture-detail

| 컴포넌트 | Size | Functionality | Theme |
|---|---|---|---|
| FixtureDetailView | 🆕 MatchHeader 25vh + ThreePanel 75vh, grid 25/50/25 | ✅ (fixture-detail.spec.ts) | ✅ root data-league |
| MatchHeader | 🆕 25vh 고정 | ✅ (vitest 5 + e2e) | ✅ border-left 라이트/다크 |
| EventsTimeline | — | ✅ (vitest 3) | — |
| GoalHistoryInline | — | ✅ (vitest) | — |
| LineupRow / LineupsRight / LineupPanel | — | ✅ F37/F38 bench toggle | — |
| FormationHalf / FormationTab | — | ✅ F18/F19/F20 tab sync, vitest | — |
| CenterTabs | — | ✅ F19/F20 URL ?tab= sync | — |
| StatBarRow / StatsTab | — | ✅ (vitest 2) | — |
| H2HTab / StandingsTab | — | (lazy load, S20 잠재 회귀) | — |

## 3. 신규 spec 파일

- `frontend/e2e/component-size.spec.ts` — Size axis 의 🆕 항목들
- `frontend/e2e/component-functionality.spec.ts` — Functionality 의 🆕 항목들
- `frontend/e2e/theme-league.spec.ts` (확장) — Theme 의 🆕 항목 (per-card / per-block data-league)

## 4. 실행 기준

- 모든 spec 은 mock 모드 (`VITE_USE_MOCK=true`) 에서 통과해야 함
- 회귀 비교 viewport: **1280×720, 1440×900, 1920×1080**
- 다크/라이트 둘 다 통과
- 통과 기준: 전체 e2e ≥ 60 case (현재 44 + 신규 ~16-20)

## 5. 본 문서의 위치

- 본 plan 은 `docs/spec/` 의 SSOT 일부. 신규 컴포넌트 / viewport / 테마 정책 변경 시 row 갱신.
- fe-reviewer 는 PR 단계에서 새 컴포넌트가 매트릭스에 추가됐는지 확인.
