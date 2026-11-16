> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `main` 워크트리의 `frontend/endpoint-requests/GET__api_v1_fixtures__id.request.json`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# GET__api_v1_fixtures__id.request.json

선언형 API/사전 계약의 기획 참고본입니다. 실행 파일이나 테스트 결과가 아닙니다.

```json
{
  "endpoint_id": "GET__api_v1_fixtures__id",
  "method": "GET",
  "path": "/api/v1/fixtures/{external_id}",
  "from_feature": "fixture-detail",
  "fe_mockup_ref": "frontend/src/mocks/data/fixture-detail/match.{external_id}.json",
  "handler_ref": "frontend/src/lib/api/fixtureDetail.ts (getMatch)",
  "spec_excerpt": "MatchHeader 영역의 메인 데이터. 25vh 헤더에 league name_ko + round + venue + kickoff_at(KST) + status_short/long + home/away team(name_ko) + score + goal_events 인라인 표시. status_short ∈ {NS,1H,HT,2H,ET,PEN,FT,AET,PST,CANC,SUSP}. (spec §2.1, §2.4, §4)",
  "auth": "public",
  "request_path_params": [{"name": "external_id", "type": "int", "desc": "API-Football fixture external_id"}],
  "response_shape": {
    "external_id": "int",
    "league": {"external_id": "int", "slug": "string", "name": "string", "name_ko": "string|null", "short_name_ko": "string|null", "logo_url": "string|null"},
    "round": "string|null",
    "status_short": "NS|1H|HT|2H|ET|PEN|FT|AET|PST|CANC|SUSP",
    "status_long": "string",
    "kickoff_at": "ISO8601 UTC",
    "venue": {"name": "string|null", "city": "string|null"},
    "referee": "string|null",
    "home": {"external_id":"int","slug":"string","name":"string","name_ko":"string|null","short_name_ko":"string|null","logo_url":"string|null"},
    "away": {"external_id":"int","slug":"string","name":"string","name_ko":"string|null","short_name_ko":"string|null","logo_url":"string|null"},
    "goals_home": "int|null",
    "goals_away": "int|null",
    "penalty_home": "int|null",
    "penalty_away": "int|null",
    "goal_events": [{"minute":"int","extra":"int|null","scorer":{"external_id":"int","slug":"string","name":"string","name_ko":"string|null","photo_url":"string|null"},"team_external_id":"int","type":"normal|penalty|own"}]
  },
  "scenarios_used": ["normal_FT", "NS_no_lineups", "404_not_found", "500_server_error"],
  "scenario_behavior": {
    "normal_FT": "200 with full payload + goal_events (e.g., 1000001 Liverpool 3-1 Arsenal)",
    "NS_no_lineups": "200 with goals_home=null, goals_away=null, goal_events=[] (e.g., 1000002)",
    "404_not_found": "404 → FE redirect to /not-found (e.g., 1000099)",
    "500_server_error": "500 → ErrorState (e.g., 1000098)"
  },
  "data_source": "fixture + fixture_detail tables (daily-sync 적재). league/team/player_translation 조인",
  "notes_for_be": [
    "league_external_id 기반 league_translation 조인 → name_ko/short_name_ko",
    "home/away_team_id 기반 team_translation 조인",
    "goal_events 는 fixture_detail.events JSONB 에서 type='Goal' 만 추출, 또는 별도 사전 추출 컬럼",
    "FT/PEN/AET 가 아니면 goals_home/away NULL",
    "데이터 신선도 6h (CLAUDE.md §6 일반 사용자 페이지)"
  ]
}
```
