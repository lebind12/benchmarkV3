> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `main` 워크트리의 `frontend/endpoint-requests/GET__api_v1_home_top_players.request.json`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# GET__api_v1_home_top_players.request.json

선언형 API/사전 계약의 기획 참고본입니다. 실행 파일이나 테스트 결과가 아닙니다.

```json
{
  "endpoint_id": "GET__api_v1_home_top_players",
  "method": "GET",
  "path": "/api/v1/home/top-players",
  "from_feature": "main-home",
  "fe_mockup_ref": "frontend/src/mocks/data/home/top_players.json",
  "handler_ref": "frontend/src/mocks/handlers/home.ts",
  "spec_excerpt": "우측 하단 50% — 리그별 선수 스탯. 지표 = goals/assists/yellow_cards/red_cards. 행 = rank · player.name_ko · 팀 배지 · 수치. 클릭 시 /players/{player_slug}. (spec §5.2)",
  "auth": "public",
  "request_query_params": [
    { "name": "league_id", "type": "number", "optional": true, "default": "39", "description": "리그 external_id" },
    { "name": "metric", "type": "'goals'|'assists'|'yellow_cards'|'red_cards'", "optional": true, "default": "goals", "description": "스탯 지표" }
  ],
  "response_shape": {
    "league": {
      "external_id": "number",
      "slug": "string",
      "name_ko": "string|null",
      "name": "string"
    },
    "season": "number (예: 2025)",
    "metric": "'goals'|'assists'|'yellow_cards'|'red_cards'",
    "rows": [
      {
        "rank": "number",
        "player": {
          "external_id": "number",
          "slug": "string",
          "name_ko": "string|null",
          "name": "string",
          "photo_url": "string|null",
          "team": {
            "external_id": "number",
            "slug": "string",
            "name_ko": "string|null",
            "name": "string",
            "logo_url": "string|null"
          },
          "league": "(LeagueRef)"
        },
        "metric_value": "number"
      }
    ]
  },
  "response_example_path": "frontend/src/mocks/data/home/top_players.json",
  "scenarios_used": ["normal", "empty", "error"],
  "scenario_behavior": {
    "empty": "200 { league: <ref|null>, season: <year>, metric, rows: [] }",
    "error": "500",
    "normal": "rank asc, 최대 ~30행"
  },
  "data_source": "player + 시즌 stats. metric 별 집계. 현재 시즌, 지정 리그.",
  "notes_for_be": [
    "metric 값은 정수. 없는 row 는 rows:[] 로 반환.",
    "league 가 null 가능 (rows:[] 일 때) — FE 가 처리."
  ]
}
```
