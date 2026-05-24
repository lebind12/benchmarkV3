---
feature_id: fixture-detail
title: 매치 디테일 페이지 — 헤더 + 3패널 구조 (Sofascore 참조)
created: 2026-05-14
priority: MVP
status: requirements-only
---

## 1. 개요

특정 경기의 상세 정보를 표시하는 페이지 (`/fixtures/{external_id}`). 메인 / 경기 리스트 / 팀 페이지 등에서 카드 클릭 시 진입. **DB 만** 사용 (라이브 API 호출 X).

## 2. 사용자

- 주 role: **public (비로그인 가능)**
- 부가: USER / STREAMER / ADMIN — 모두 동일

## 3. 사용자 흐름

1. 메인 / 경기 리스트 / 팀 페이지 등에서 경기 카드 클릭
2. 매치 디테일 페이지 로드
3. 상단 헤더 (스코어 + 골 이력)
4. 좌측 = 시간 순 events 타임라인 (아이콘 + hover 디테일)
5. 중앙 = 포메이션 (default) / 서브탭 전환 (H2H / 스탯 / 리그 랭킹)
6. 우측 = 양 팀 라인업 (선수 명단)

## 4. 페이지 / URL

- URL: `/fixtures/{external_id}`
- `external_id` = API-Football fixture.id (DB 의 fixture.external_id)
- 방송용 페이지 여부: **no**

## 5. Layout

### 5.1 viewport 분할 (높이)

```
┌────────────────────────────────────────────────────────────────┐
│  상단 탭 (h: 56px, 전역)                                       │
├────────────────────────────────────────────────────────────────┤
│  매치 헤더 (25vh)                                              │
│    [home logo]  3 - 1  [away logo]                             │
│    league.name_ko · round · FT · venue · referee · kickoff_at  │
│    골 이력 (모두 표시): Salah 23' / Saka 45'+2 / Son 67' ...   │
├────────────┬──────────────────────────────┬────────────────────┤
│  좌측 25%  │       중앙 50%               │   우측 25%         │
│            │                              │  ┌──────────────┐  │
│  events    │  서브탭 (상단): [포메이션]    │  │  홈 라인업   │  │
│  타임라인  │  [H2H] [스탯] [리그 랭킹]    │  │   (h: 50%)   │  │
│  (위→아래) │                              │  │              │  │
│            │  default 콘텐츠 (포메이션):  │  ├──────────────┤  │
│  좌: 홈    │  좌: 홈 4-3-3 도형           │  │              │  │
│  우: 어웨이│  우: 어웨이 4-2-3-1 도형     │  │  어웨이 라인업│  │
│            │                              │  │   (h: 50%)   │  │
│  아이콘 +  │                              │  │              │  │
│  hover     │                              │  └──────────────┘  │
│  tooltip   │                              │                    │
└────────────┴──────────────────────────────┴────────────────────┘
```

(footer 없음. 각 패널 내부 hidden 스크롤)

## 5.2 매치 헤더 (25vh) — **league 동적 테마 적용**

페이지 root 에 `data-league="<매치의 league.slug>"` 속성 부여 → ui-standards §3.2 의 CSS variable swap 으로 자동 적용 (헤더 배경 subtle gradient, 서브탭 active, 골 아이콘, 강조 등).

표시 항목:
- 양 팀 logo + name_ko (영문 fallback)
- 스코어: `{home_score} - {away_score}` (예: `3 - 1`)
- 매치 메타: `league.name_ko · round (예: '32라운드') · status_long (예: 'FT') · venue.name · referee · kickoff_at (KST)`
- **골 이력 모두 표시**: `Salah 23' / Saka 45'+2 / Son 67' / De Bruyne 89'` 같은 인라인 형식. 다득점 매치도 스크롤 없이 (작은 폰트 + 줄바꿈 허용)
- 헤더 배경: 매치 league 의 primary 색 subtle gradient 또는 좌측 보더 (절제 원칙)

상태별:
- NS (예정): 스코어 자리 = `vs`. 골 이력 = "kickoff 19:00 KST" (D-N 카운트다운 X)
- 1H/HT/2H/ET (라이브) — 사용자 화면에선 일반 사용자에게 라이브 갱신 안 보장. **DB 마지막 sync 값 그대로 표시**. 6h 지연 가능
- FT/AET/PEN (종료): 모두 표시

## 5.3 좌측 25% — events 타임라인

- 위→아래 시간 순 (1' → 90'+추가시간)
- 좌측 컬럼 = 홈 events, 우측 컬럼 = 어웨이 events (패널 내부 2 컬럼)
- 각 event 는 **작은 아이콘만** (골 ⚽ / 옐로 카드 🟨 / 레드 🟥 / 교체 🔄)
- hover 시 tooltip 으로 상세 (선수 이름 + 시간 + 추가 정보)
- 패널 내부 hidden 스크롤 (90 분 + 추가시간 + 연장 + 승부차기까지 모두)

## 5.4 중앙 50% — 서브탭 + 콘텐츠

상단에 서브탭 (가로 탭): `포메이션 (default) | H2H | 경기 스탯 | 리그 랭킹`

### default — 포메이션
- 좌측 절반: 홈 팀 포메이션 도형 (4-3-3 등). 각 선수 위치 + 이름 (name_ko)
- 우측 절반: 어웨이 팀 포메이션
- 데이터 출처: `fixture_detail.lineups`

### H2H
- 양 팀 직접 대결 최근 5 경기 (DB `h2h_fixture` 테이블)
- 시간 순 / 결과 (W/D/L 색상 표시)
- 5경기 모두 viewport 안에 표시

### 경기 스탯
- 양 팀 비교 bar 차트:
  - 점유율 (%)
  - 슛 (총 / 유효)
  - 패스 (총 / 정확도)
  - 코너킥
  - 파울 / 옐로 / 레드
  - 오프사이드
- 데이터 출처: `fixture_detail.statistics`
- 상태가 NS / 라이브 (정착 안 됨) 면 일부 비어 있음

### 리그 랭킹
- 매치의 `league_id` 의 standings 표시
- 양 팀 row 강조 (highlight background)
- UCL/UEL 매치면 해당 그룹 또는 토너먼트 진출 표 (standings.group_name 활용)

## 5.5 우측 25% — 양 팀 라인업

상단 50% (홈) / 하단 50% (어웨이) 분할.

각 영역:
- 선발 11명: 선수 이름 (name_ko) + 등번호 + 위치 (포메이션 좌표 또는 텍스트)
- 벤치 (확장 가능): 패널 내부 hidden 스크롤
- 데이터 출처: `fixture_detail.lineups`
- 선수 카드 클릭 시 `/players/{slug}` 이동

NS 상태: "라인업 미정 (kickoff 1시간 전 발표)" placeholder

## 6. 인터랙션

| 영역 | 동작 |
|---|---|
| 매치 헤더 | 정적. 클릭 액션 없음 |
| 좌측 타임라인 | 아이콘 hover → tooltip 상세 (선수 / 시간 / event 종류) |
| 중앙 서브탭 | 클릭 시 콘텐츠 swap (포메이션 ↔ H2H ↔ 스탯 ↔ 리그 랭킹) |
| 중앙 포메이션 카드 | 선수 카드 클릭 시 `/players/{slug}` |
| 중앙 H2H row | 클릭 시 그 매치의 `/fixtures/{external_id}` 로 이동 |
| 중앙 리그 랭킹 row | 클릭 시 팀 페이지 `/teams/{slug}` |
| 우측 라인업 카드 | 선수 클릭 시 `/players/{slug}` |
| 상단 글로벌 탭 | 일반 페이지 이동 |

라이브 갱신 / 자동 polling 없음.

## 7. 비기능

| 항목 | 값 |
|---|---|
| 데이터 신선도 | 6h (AGENTS.md §6 정책) |
| 폴링 | 없음 |
| 접근성 | 키보드 탐색, hover tooltip 의 키보드 활성화 |
| 성능 | LCP < 1.5s, 번들 회귀 < 10% |
| 반응형 | 1920×1080 최적 / 1366×768 최소 |
| 스크롤 | 페이지 X, 각 패널 내부 hidden 스크롤만 |
| footer | 없음 |

## 8. 디자인 참조

- UI 기준: `@docs/spec/ui-standards.md` (§3.2 동적 league 테마 적용 규칙 포함)
- 색상 팔레트: `@docs/spec/league-palette.md` (5리그 토큰 정의)
- 페이지 root 에 `data-league="<slug>"` 부여 — CSS variable swap 으로 헤더/서브탭/강조 모두 league 색상 자동 적용
- 참조: **Sofascore**, fotmob
- shadcn-vue Tabs 컴포넌트 (서브탭)

## 9. MVP 여부 / 우선순위

- MVP 포함: **yes**
- 우선순위: **2** (홈 다음으로 중요)

## 10. FE 팀이 결정해도 되는 것

- 포메이션 도형 구현 (CSS / SVG)
- events 아이콘 / tooltip 디자인
- 서브탭 콘텐츠 layout 디테일
- 라인업 카드 형식
- 컴포넌트 분해

## 11. FE 팀이 결정해서는 안 되는 것 (메인 확인 필요)

- URL 규칙 (`/fixtures/{external_id}`)
- 매치 헤더 / 좌중우 패널 분할 비율 (25/50/25)
- 서브탭 항목 (포메이션 / H2H / 스탯 / 리그 랭킹)
- 좌측 타임라인의 표시 방식 (아이콘 + hover)
- 라이브 갱신 추가 (정책 위반)
- league 동적 테마 미적용 (해당 매치의 리그 색상 반영 필수)

## 12. 미확정 / 메모

- 포메이션 도형 시각화 디테일 (4-3-3 좌표 등) — fe-planner 결정
- 골 이력 표시 한계 — 다득점(8골+) 시 줄바꿈 + 작은 폰트 vs 가로 스크롤. fe-planner 결정 (스크롤 정책 위반 안 됨)
- 라이브 매치 진행 중 사용자가 디테일 페이지 보면 6h stale 가능 — 의도된 정책 (라이브 정보 = 방송용 페이지)
- 라인업의 평점 (rating) 표시 여부 — player_season_stat 의 평균이 아닌 매치별 평점은 API-Football 의 `fixture_detail.lineups` 에 포함 가능 (확인 필요)
- 매치 미발견 (`external_id` 가 DB 에 없음) 시 404 페이지 또는 placeholder
