# GET__api_v1_home_transfers

## 1. Endpoint

| 항목 | 값 |
|---|---|
| Method | `GET` |
| Path | `/api/v1/home/transfers` |
| Auth | public, JWT 불필요 |
| FE request | `frontend/endpoint-requests/GET__api_v1_home_transfers.request.json` |
| Feature SSOT | `docs/features/main-home.spec.md` §3.3~§3.4, `docs/features/main-home.devplan.md` §6~§7 |

홈 좌측 큐브 3면 "이적" 데이터. `daily-sync` 가 적재한 DB row 만 읽는다.

## 2. Query

없음.

## 3. Response

`200 OK`

```json
{
  "items": [
    {
      "id": "1",
      "player": {
        "external_id": 2002,
        "slug": "florian-wirtz",
        "name_ko": "플로리안 비르츠",
        "name": "Florian Wirtz",
        "photo_url": null,
        "team": {
          "external_id": 40,
          "slug": "liverpool",
          "name_ko": "리버풀",
          "name": "Liverpool",
          "logo_url": null
        },
        "league": {
          "external_id": 39,
          "slug": "premier-league",
          "name_ko": "프리미어리그",
          "name": "Premier League"
        }
      },
      "from_team": {
        "external_id": 168,
        "slug": "leverkusen",
        "name_ko": "레버쿠젠",
        "short_name_ko": "레버쿠젠",
        "name": "Bayer Leverkusen",
        "logo_url": null
      },
      "to_team": {
        "external_id": 40,
        "slug": "liverpool",
        "name_ko": "리버풀",
        "short_name_ko": "리버풀",
        "name": "Liverpool",
        "logo_url": null
      },
      "transfer_date": "2026-05-08",
      "fee": "€120m"
    }
  ]
}
```

빈 결과는 `200 OK { "items": [] }`.

## 4. Business Rules

1. 최근 이적 최대 5건을 `transfer.transfer_date DESC`, `transfer.id DESC` 로 반환한다.
2. main-home 5리그 external_id `39, 2, 3, 48, 45` 중 active/current-season 팀과 관련된 row 만 반환한다.
3. 관련 판정은 `from_team_id` 또는 `to_team_id` 가 `team_season` 으로 active target league 의 `current_season` 에 연결되거나, player stat 이 active target league/current season 에 연결된 경우다.
4. FE shape 를 위해 `from_team_id` 와 `to_team_id` 가 모두 resolve 된 row 만 반환한다. 한쪽 팀이 null 이거나 삭제되어 null 이면 제외한다.
5. `fee` 는 `transfer.type` 원문 문자열을 그대로 매핑한다. 통화/단위 정규화는 MVP 외다.
6. `player.team` 은 현재 team (`player.current_team_id`) 이 있으면 우선 사용하고, 없으면 `to_team`, 그 다음 `from_team` 을 사용한다.
7. `player.league` 는 관련 판정에 사용한 active target league 를 반환한다. `to_team` 의 current-season league 를 우선한다.
8. translation 값이 null 이어도 null 로 반환한다. FE 가 영문 fallback 을 수행한다.

## 5. DB Dependencies

- `transfer`
- `player`, `player_translation`, `player_season_stat`
- `team`, `team_translation`, `team_season`
- `league`, `league_translation`

## 6. Error Cases

| 케이스 | 응답 |
|---|---|
| DB 조회 실패 | `500` + 공통 error body |

## 7. Expected BE Surface For Tests

`app.services.home.list_home_transfers(session, *, limit: int = 5) -> dict`

라우터는 위 service 를 호출해 같은 response shape 를 반환한다.
