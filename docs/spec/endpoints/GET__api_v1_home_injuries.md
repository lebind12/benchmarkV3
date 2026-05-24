# GET__api_v1_home_injuries

## 1. Endpoint

| 항목 | 값 |
|---|---|
| Method | `GET` |
| Path | `/api/v1/home/injuries` |
| Auth | public, JWT 불필요 |
| FE request | `frontend/endpoint-requests/GET__api_v1_home_injuries.request.json` |
| Feature SSOT | `docs/features/main-home.spec.md` §3.3~§3.4, `docs/features/main-home.devplan.md` §6~§7 |

홈 좌측 큐브 4면 "부상" 데이터. `daily-sync` 가 적재한 DB row 만 읽는다.

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
        "external_id": 3001,
        "slug": "rodri",
        "name_ko": "로드리",
        "name": "Rodri",
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
      "injury_type": "햄스트링",
      "expected_return": "2026-06-01",
      "reported_at": "2026-05-12"
    }
  ]
}
```

빈 결과는 `200 OK { "items": [] }`.

## 4. Business Rules

1. main-home 5리그 external_id `39, 2, 3, 48, 45` 중 active/current-season injury row 만 반환한다.
2. 시즌은 `league.current_season` 과 `injury.season_year` 가 일치해야 한다.
3. 정렬은 `reported_at DESC NULLS LAST`, `updated_at DESC`, `id DESC`.
4. 최대 5건을 반환한다.
5. `injury_type` 은 `injury.type`, `injury.reason`, `raw_data.type`, `raw_data.reason` 순으로 선택하고 모두 없으면 `"미상"` 을 반환한다.
6. `expected_return` 은 `raw_data.expected_return` 또는 `raw_data.return_date` 가 `YYYY-MM-DD` 일 때 반환하고, 없거나 형식이 다르면 null.
7. `reported_at` 은 날짜 문자열 `YYYY-MM-DD` 로 반환한다. DB 값이 null 이면 `updated_at` 날짜를 사용한다.
8. `player.team` 은 `injury.team_id`, `player.league` 는 `injury.league_id` 를 기준으로 반환한다.
9. translation 값이 null 이어도 null 로 반환한다. FE 가 영문 fallback 을 수행한다.

## 5. DB Dependencies

- `injury`
- `player`, `player_translation`
- `team`, `team_translation`
- `league`, `league_translation`

## 6. Error Cases

| 케이스 | 응답 |
|---|---|
| DB 조회 실패 | `500` + 공통 error body |

## 7. Expected BE Surface For Tests

`app.services.home.list_home_injuries(session, *, limit: int = 5) -> dict`

라우터는 위 service 를 호출해 같은 response shape 를 반환한다.
