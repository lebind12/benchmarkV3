> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `main` 워크트리의 `frontend/endpoint-requests/GET__api_v1_home_standings.request.json`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# GET__api_v1_home_standings.request.json

선언형 API/사전 계약의 기획 참고본입니다. 실행 파일이나 테스트 결과가 아닙니다.

```json
{
  "endpoint_id": "GET__api_v1_home_standings",
  "method": "GET",
  "path": "/api/v1/home/standings",
  "from_feature": "main-home",
  "fe_mockup_ref": "frontend/src/mocks/data/home/standings.json",
  "handler_ref": "frontend/src/mocks/handlers/home.ts",
  "spec_excerpt": "우측 상단 50% — 리그별 팀 순위. 드롭다운 = 5리그 (컵대회는 standings 없으면 빈). 행 = rank · team.short_name_ko · points · W-D-L. 클릭 시 /teams/{team_slug}. (spec §5.1)",
  "auth": "public",
  "request_query_params": [
    { "name": "league_id", "type": "number", "optional": true, "default": "39", "description": "리그 external_id. 기본 EPL(39). 5리그(39|2|3|48|45) 중 하나" }
  ],
  "response_shape": {
    "league": {
      "external_id": "number",
      "slug": "string",
      "name_ko": "string|null",
      "short_name_ko": "string|null",
      "name": "string"
    },
    "season": "number (예: 2025)",
    "rows": [
      {
        "rank": "number",
        "team": {
          "external_id": "number",
          "slug": "string",
          "name_ko": "string|null",
          "short_name_ko": "string|null",
          "name": "string",
          "logo_url": "string|null"
        },
        "points": "number",
        "played": "number",
        "win": "number",
        "draw": "number",
        "loss": "number",
        "goals_for": "number",
        "goals_against": "number"
      }
    ]
  },
  "response_example_path": "frontend/src/mocks/data/home/standings.json",
  "scenarios_used": ["normal", "empty", "error"],
  "scenario_behavior": {
    "empty": "200 { league: <ref>, season: <year>, rows: [] } — 컵대회(카라바오/FA) 또는 시즌 미시작",
    "error": "500",
    "normal": "rank asc 정렬"
  },
  "data_source": "standing 테이블 (daily-sync 적재). 현재 시즌(current season).",
  "notes_for_be": [
    "컵 대회(48, 45)는 standings 없을 수 있음 → rows:[] 반환 (FE 가 'standings 없음' 카피 표시).",
    "league.short_name_ko 가 있어야 우측 패널 헤더에 사용. FE 가 영문 fallback."
  ]
}
```
