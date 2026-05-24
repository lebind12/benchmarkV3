# Broadcast API-Football Fixture Samples

작성일: 2026-05-14 KST

API-Football 을 직접 호출해 방송 화면 확인용 fixture id 를 확보했다. 조회 기준은 2025 시즌 5개 리그, 월드컵은 2026 시즌이다. 다만 화면 구성 확인에는 lineups/events/statistics 가 채워진 완료 경기가 필요하므로, 현재 시즌에 완료 경기가 없으면 이전 완료 시즌으로 fallback 한다.

## 1. 화면 구성용 Fixture

완료 경기가 있으면 방송 화면의 lineups/events/statistics 데이터가 더 잘 채워지므로 `last=1` 결과를 우선 사용한다. 아직 진행/완료 경기가 없는 월드컵 2026은 화면 구성 확인용으로 2022 시즌 결승 fixture를 사용한다.

| 대회 | league id | season | fixture id | 기준 | 일시(KST) | 상태 | 경기 |
|---|---:|---:|---:|---|---|---|---|
| Premier League | 39 | 2025 | 1379275 | last=1 | 2026-05-14 04:00 | FT | Manchester City 3-0 Crystal Palace |
| UEFA Champions League | 2 | 2025 | 1540844 | last=1 | 2026-05-07 04:00 | FT | Bayern Munchen 1-1 Paris Saint Germain |
| UEFA Europa League | 3 | 2025 | 1540873 | last=1 | 2026-05-08 04:00 | FT | Aston Villa 4-0 Nottingham Forest |
| Carabao Cup | 48 | 2025 | 1518728 | last=1 | 2026-03-23 01:30 | FT | Arsenal 0-2 Manchester City |
| FA Cup | 45 | 2025 | 1539715 | last=1 | 2026-04-26 23:00 | FT | Chelsea 1-0 Leeds |
| FIFA World Cup | 1 | 2022 | 979139 | previous completed season | 2022-12-19 00:00 | PEN | Argentina 3-3 France |

## 2. 다음 경기 Fixture

5개 기존 리그 중 Carabao Cup 은 현재 `next=1` 결과가 없다.

| 대회 | league id | season | fixture id | 일시(KST) | 상태 | 경기 |
|---|---:|---:|---:|---|---|---|
| Premier League | 39 | 2025 | 1379330 | 2026-05-16 04:00 | NS | Aston Villa vs Liverpool |
| UEFA Champions League | 2 | 2025 | 1544371 | 2026-05-31 01:00 | NS | Paris Saint Germain vs Arsenal |
| UEFA Europa League | 3 | 2025 | 1544596 | 2026-05-21 04:00 | NS | SC Freiburg vs Aston Villa |
| FA Cup | 45 | 2025 | 1542889 | 2026-05-16 23:00 | NS | Chelsea vs Manchester City |
| FIFA World Cup 2026 | 1 | 2026 | 1489369 | 2026-06-12 04:00 | NS | Mexico vs South Africa |

## 3. 이전 시즌 Fallback

| 대회 | league id | fallback season | fixture id | 일시(KST) | 상태 | 경기 |
|---|---:|---:|---:|---|---|---|
| FIFA World Cup | 1 | 2022 | 979139 | 2022-12-19 00:00 | PEN | Argentina 3-3 France |
| Carabao Cup | 48 | 2024 | 1351039 | 2025-03-17 01:30 | FT | Liverpool 1-2 Newcastle |

검증:

| fixture id | events | lineups | statistics |
|---:|---:|---:|---:|
| 979139 | 35 | 2 | 2 |
| 1518728 | 11 | 2 | 2 |
| 1351039 | 15 | 2 | 2 |

## 4. 방송 화면 URL

Live mode env:

```bash
VITE_BROADCAST_USE_API_FOOTBALL=true
VITE_USE_MOCK=false
```

오버레이:

| 대회 | URL |
|---|---|
| Premier League | `/broadcast.html?fixtureId=1379275&league=premier-league&revision=material` |
| UEFA Champions League | `/broadcast.html?fixtureId=1540844&league=champions-league&revision=material` |
| UEFA Europa League | `/broadcast.html?fixtureId=1540873&league=europa-league&revision=material` |
| Carabao Cup | `/broadcast.html?fixtureId=1518728&league=carabao-cup&revision=material` |
| FA Cup | `/broadcast.html?fixtureId=1539715&league=fa-cup&revision=material` |
| FIFA World Cup | `/broadcast.html?fixtureId=979139&league=world-cup-2026&revision=material` |

중계화면 포함 페이지:

| 대회 | URL |
|---|---|
| Premier League | `/broadcast-program.html?fixtureId=1379275&league=premier-league` |
| UEFA Champions League | `/broadcast-program.html?fixtureId=1540844&league=champions-league` |
| UEFA Europa League | `/broadcast-program.html?fixtureId=1540873&league=europa-league` |
| Carabao Cup | `/broadcast-program.html?fixtureId=1518728&league=carabao-cup` |
| FA Cup | `/broadcast-program.html?fixtureId=1539715&league=fa-cup` |
| FIFA World Cup | `/broadcast-program.html?fixtureId=979139&league=world-cup-2026` |
