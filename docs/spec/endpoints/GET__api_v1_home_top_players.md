# GET__api_v1_home_top_players

## 1. Endpoint

| 항목 | 값 |
|---|---|
| Method | `GET` |
| Path | `/api/v1/home/top-players` |
| Auth | public, JWT 불필요 |
| FE request | `frontend/endpoint-requests/GET__api_v1_home_top_players.request.json` |
| Feature SSOT | `docs/features/main-home.spec.md` §5.2, `docs/features/main-home.devplan.md` §6~§7 |

일반 홈 우측 하단 "리그별 선수 스탯" 블록의 데이터. 일반 페이지 정책에 따라 DB 만 사용하고 API-Football, OpenAI, Upstash 호출은 금지한다.

## 2. Query

| 이름 | 타입 | 필수 | 기본값 | 규칙 |
|---|---|---:|---|---|
| `league_id` | integer | no | `39` | API-Football league external_id |
| `metric` | enum | no | `goals` | `goals`, `assists`, `yellow_cards`, `red_cards` |

FastAPI validation 으로 타입/enum 오류는 `422` 를 반환한다.

## 3. Response

`200 OK`

```json
{
  "league": {
    "external_id": 39,
    "slug": "premier-league",
    "name_ko": "프리미어리그",
    "name": "Premier League"
  },
  "season": 2025,
  "metric": "goals",
  "rows": [
    {
      "rank": 1,
      "player": {
        "external_id": 1100,
        "slug": "erling-haaland",
        "name_ko": "엘링 홀란드",
        "name": "Erling Haaland",
        "photo_url": null,
        "team": {
          "external_id": 50,
          "slug": "manchester-city",
          "name_ko": "맨체스터 시티",
          "name": "Manchester City",
          "logo_url": null
        },
        "league": {
          "external_id": 39,
          "slug": "premier-league",
          "name_ko": "프리미어리그",
          "name": "Premier League"
        }
      },
      "metric_value": 22
    }
  ]
}
```

빈 결과도 `200 OK` 이며 `rows: []` 를 반환한다. 요청 리그 row 가 DB 에 없거나 active/current season 이 없으면 `league` 는 `null` 이 될 수 있다.

## 4. Business Rules

1. `league.external_id = league_id` 이고 `league.is_active = true` 인 리그만 조회한다.
2. 시즌은 `league.current_season` 을 사용한다. `current_season IS NULL` 이면 빈 결과를 반환한다.
3. `player_season_stat` 에서 `league_id`, `season_year`, 선택 metric 을 기준으로 조회한다.
4. 정렬은 `metric_value DESC`, 동률 시 `player.name ASC`, `player.external_id ASC`.
5. `rank` 는 응답 정렬 순서 기준 1부터 부여한다.
6. `metric_value` 는 null 을 0으로 취급하되, FE 랭킹 노이즈를 피하기 위해 0 이하 row 는 제외한다.
7. 팀은 stat row 의 `team_id` 를 기준으로 반환한다.
8. 한글명은 translation table 값을 그대로 반환하고, null fallback 은 FE 가 처리한다.
9. 최대 30 row 를 반환한다.

## 5. DB Dependencies

- `league`, `league_translation`
- `player`, `player_translation`
- `team`, `team_translation`
- `player_season_stat`

## 6. Error Cases

| 케이스 | 응답 |
|---|---|
| `metric` enum 오류 | `422` |
| `league_id` 타입 오류 | `422` |
| DB 조회 실패 | `500` + 공통 error body |

## 7. Expected BE Surface For Tests

`app.services.home.list_home_top_players(session, *, league_id: int = 39, metric: str = "goals", limit: int = 30) -> dict`

라우터는 위 service 를 호출해 같은 response shape 를 반환한다.
