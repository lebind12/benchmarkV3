# GET__api_v1_home_hot_players

## 1. Endpoint

| 항목 | 값 |
|---|---|
| Method | `GET` |
| Path | `/api/v1/home/hot-players` |
| Auth | public, JWT 불필요 |
| FE request | `frontend/endpoint-requests/GET__api_v1_home_hot_players.request.json` |
| Feature SSOT | `docs/features/main-home.spec.md` §3.3~§3.4, `docs/features/main-home.devplan.md` §6~§7 |

홈 좌측 큐브 2면 "핫 선수" 데이터. 일반 홈 endpoint 이므로 DB only 이며 라이브 API 호출, polling, 캐시 refresh 는 하지 않는다.

## 2. Query

없음.

## 3. Response

`200 OK`

```json
{
  "items": [
    {
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
      "goals": 22,
      "assists": 6,
      "score": 28
    }
  ]
}
```

빈 결과는 `200 OK { "items": [] }`.

## 4. Business Rules

1. 대상 리그는 main-home 초기 5리그 external_id `39, 2, 3, 48, 45` 중 `is_active = true` 인 row.
2. 시즌은 각 리그의 `league.current_season` 을 사용한다.
3. `player_season_stat` 에서 현재 시즌 row 를 모아 `score = COALESCE(goals, 0) + COALESCE(assists, 0)` 로 계산한다.
4. `score <= 0` row 는 제외한다.
5. 정렬은 `score DESC`, `goals DESC`, `assists DESC`, `player.name ASC`, `player.external_id ASC`.
6. 최대 5건을 반환한다. 5건 미만이어도 placeholder 를 채우지 않는다.
7. 팀은 stat row 의 `team_id`, 리그는 stat row 의 `league_id` 로 반환한다.
8. translation 값이 null 이어도 null 로 반환한다. FE 가 영문 fallback 을 수행한다.

## 5. DB Dependencies

- `league`, `league_translation`
- `player`, `player_translation`
- `team`, `team_translation`
- `player_season_stat`

## 6. Error Cases

| 케이스 | 응답 |
|---|---|
| DB 조회 실패 | `500` + 공통 error body |

## 7. Expected BE Surface For Tests

`app.services.home.list_home_hot_players(session, *, limit: int = 5) -> dict`

라우터는 위 service 를 호출해 같은 response shape 를 반환한다.
