---
feature_id: main-home
title: 메인 페이지 (홈) — 3패널 dashboard 형식
created: 2026-05-13
priority: MVP
status: requirements-only
---

## 1. 개요

축구 정보 사이트의 홈 페이지 (`/`). 5리그(EPL/UCL/UEL/카라바오/FA) 의 경기·순위·스탯·뉴스를 **단일 viewport 안에 dashboard 형식** 으로 종합 표시. 메인은 간략 요약, 상세는 상단 탭의 각 페이지에서.

## 2. 사용자

- 주 role: **public (비로그인 가능)**
- 부가 role: USER / STREAMER / ADMIN — 모두 동일 메인. 인증별 분기는 MVP 외 (우상단 "로그인"/"프로필" 토글만)

## 3. 사용자 흐름

1. 도메인 진입(`/`) → 메인 페이지 로드
2. 좌측 큐브에서 뉴스/핫선수/이적/부상 (10초 회전) 훑기
3. 중앙에서 오늘 경기 확인, 리그/기간 필터로 다른 경기 검색
4. 우측에서 리그 팀 순위 + 선수 스탯 훑기 (패널 내부 hidden 스크롤)
5. 각 카드/항목 클릭 시 해당 상세 페이지로 이동

## 4. 페이지 / URL

- URL: `/`
- 방송용 페이지 여부: **no** (방송용은 별도 entry `/broadcast/...`)
- 상단 탭에서 다른 페이지로 이동 가능. 상단 탭 목록은 §5.1 참조

## 5. 표시 데이터 / 콘텐츠

### 5.1 상단 탭 (height 56px)

| 라벨 | path | 영역 |
|---|---|---|
| 홈 | `/` | 본 페이지 |
| 경기 | `/fixtures` | 일정 / 결과, 월/주/일 필터, 리그 필터 |
| 순위 | `/standings` | 5리그 standings 상세 |
| 팀 | `/teams` | 팀 목록 + 개별 페이지 |
| 선수 | `/players` | 선수 목록 + 개별 페이지 |
| 스탯 | `/stats` | 핫 선수 / 이적 / 부상 / topscorer / topassist 등 |
| (스트리머) 방송 | `/broadcast` | STREAMER role 만 |

(커뮤니티 / 데이터센터 / 광고 / 마이페이지 등은 MVP 외)

### 5.2 좌측 25% — 로고 + 3D 큐브

```
┌─────────────────┐
│  로고 (30%)     │  사이트 로고 (브랜드)
├─────────────────┤
│                 │
│  3D 큐브 (70%)  │  4면 회전 (10초 자동, hover 정지)
│                 │  하단: dot 인디케이터 (4 dots, 라벨 표시)
│  ● ○ ○ ○        │
└─────────────────┘
```

큐브 4면 (각 5건):

| 면 | 라벨 | 데이터 | 카드 클릭 시 |
|---|---|---|---|
| 1 | News | `news_article` (EPL 팀 키워드 매칭, title_ko 채워진 것만) 최신 5건 — title_ko / summary_ko / 출처 | 원문 URL 외부 link |
| 2 | Hot 선수 | `player_season_stat` 의 5리그 통합 top 5 — 골 + 어시스트 종합 점수 | `/stats` 탭 |
| 3 | Transfer | `transfer` 최근 5건 — 선수 / from→to / 날짜 | `/stats` 탭 |
| 4 | Injury | `injury` — 곧 시작 경기 영향 부상자 5건 | `/stats` 탭 |

### 5.3 중앙 50% — 오늘의 경기 + 필터

```
┌───────────────────────────────────────────┐
│ [전체] [EPL] [UCL] [UEL] [카라바오] [FA]  │  리그 필터 (탭)
│ [월] [주] [일]                             │  기간 필터
├───────────────────────────────────────────┤
│  경기 카드 1                                │
│  홈팀 logo + 이름 | 시각 / 스코어 | 어웨이 │
│  status (SCHED / LIVE / FT)                │
├───────────────────────────────────────────┤
│  경기 카드 2                                │
│  ...                                       │
└───────────────────────────────────────────┘
```

- 기본 필터: 리그 = "전체", 기간 = "일" (오늘)
- 경기 카드 클릭 시 `/fixtures/{external_id}` 상세 페이지
- 카드 표시 항목: home_team.logo + name_ko, away_team.logo + name_ko, kickoff_at (한국시간), status_short, goals_home/goals_away (종료 후), league.name_ko
- 패널 내부 스크롤 hidden (콘텐츠 길어지면 스크롤바 안 보이게)

### 5.4 우측 25% — 순위 + 스탯 (각 50% 높이)

```
┌──────────────────────────┐
│  리그별 팀 순위 (50%)    │
│  [EPL] [UCL] [UEL] [...] │  리그 선택 (드롭다운 또는 탭)
│  1. 팀 A   pts  W-D-L    │
│  2. 팀 B   ...           │
│  ... (내부 hidden 스크롤)│
├──────────────────────────┤
│  리그별 선수 스탯 (50%)  │
│  [Goal] [Assist] [...]   │  지표 선택
│  [EPL] [UCL] [...]       │  리그 선택
│  1. 선수 A  골수         │
│  2. ...                  │
└──────────────────────────┘
```

- 상단 50%: standings 테이블의 rank / team.name_ko / points / W-D-L
- 하단 50%: player_season_stat 또는 `/topscorers` 결과의 player.name_ko / 지표값
- 둘 다 패널 내부 hidden 스크롤
- 항목 클릭 시 `/teams/{slug}` 또는 `/players/{slug}`

## 6. 인터랙션

| 영역 | 동작 |
|---|---|
| 큐브 | 자동 회전 10초. hover 시 정지. 하단 dot 클릭으로 직접 이동. 카드 클릭 시 §5.2 표대로 이동 |
| 중앙 리그 필터 | 클릭 시 fixture 리스트 재로드 |
| 중앙 기간 필터 | 월/주/일 토글, 재로드 |
| 중앙 경기 카드 | 클릭 시 fixture 상세 |
| 우측 순위 | 리그 탭/드롭다운 변경, 팀 클릭 시 팀 페이지 |
| 우측 스탯 | 지표 변경 (골/어시/카드 등), 리그 변경, 선수 클릭 시 선수 페이지 |
| 상단 탭 | 각 라벨 클릭 시 해당 페이지 |
| 우상단 토글 | 비로그인 시 "로그인" 버튼 → `/auth/login`, 로그인 시 "프로필" 메뉴 |

## 7. 비기능

| 항목 | 값 |
|---|---|
| 데이터 신선도 | 일반 6h (daily-sync), 뉴스 1h (news-fetcher), 라이브 데이터 메인 표시 X |
| 접근성 | 키보드 탐색, 큐브에 aria-live polite, 색 대비 WCAG AA |
| 성능 | LCP < 1.5s, 번들 회귀 < 10% (대비 main) |
| 반응형 | 1920×1080 최적 / 1440×900 fit / 1366×768 최소 동작 |
| 스크롤 | **페이지 자체 스크롤 X, footer 없음**. 우측 패널 + 중앙 패널 내부 hidden 스크롤만 |
| 자동 갱신 | 페이지 진입 시 1회 fetch. 백그라운드 polling 없음 (라이브 메인 X) |

## 8. 디자인 참조

- shadcn-vue 컴포넌트
- Dark / Light mode 토글
- 5리그 색상 팔레트 적용 (`docs/spec/league-palette.md` 별도 작성 예정)
- 참조: Sofascore, fotmob, blfil.com (구조 참조)
- 3D 큐브 구현: CSS `transform-style: preserve-3d` + `transform: rotateY(deg)`
- 인디케이터: 하단 dot (4개) + 라벨 (News / Hot / Transfer / Injury 한글)

## 9. MVP 여부 / 우선순위

- MVP 포함: **yes**
- 우선순위: **1** (홈, 최우선)

## 10. FE 팀이 결정해도 되는 것

- 큐브 구현 디테일 (transform / transition 값, easing)
- 컴포넌트 분해 (단일 vs 다층)
- Pinia store 모양
- 로딩 / 에러 / 빈 상태 표현
- 우측 패널 내부 hidden 스크롤 구현 (CSS `overflow-y: auto; scrollbar-width: none;` 등)
- 리그 필터 — 탭 vs 드롭다운
- 큐브 카드 디자인 (썸네일 / 색상 강조 / 등)

## 11. FE 팀이 결정해서는 안 되는 것 (메인 확인 필요)

- URL 규칙 변경 (`/`)
- 상단 탭 항목 추가/제거
- 방송용 페이지 여부 전환
- 새 외부 데이터 의존성 추가
- 좌측 큐브의 4 페이지 구성 (News/Hot/Transfer/Injury) 변경
- 우측 패널 콘텐츠 (팀 순위 + 선수 스탯) 변경
- 페이지 자체 스크롤 허용
- footer 추가
- 자동 회전 시간 변경 (10초)

## 12. 미확정 / 메모

- 인증 상태별 메인 분기 — MVP 외 (우상단 토글만)
- 빈 데이터 상태 (시즌 휴식기, 뉴스 부족 등) UI — fe-planner 결정
- 큐브 페이지 라벨 한글 표기 (News=뉴스 / Hot=핫 / Transfer=이적 / Injury=부상) — fe-planner 와 디자인 합의
- 5리그 색상 팔레트 별도 task — `docs/spec/league-palette.md` 작성 필요 (사용자 조사 자료)
- 우측 리그 선택 UX — 탭 vs 드롭다운 (fe-planner 결정)
- 라이브 데이터 미표시 정책 — 사용자가 "라이브 진행 중" 정보가 필요해지면 별도 페이지 (`/score` 등) 안내
