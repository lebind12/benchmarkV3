> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `main` 워크트리의 `frontend/endpoint-requests/GET__api_v1_fixtures__id__league_standings.request.json`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# GET__api_v1_fixtures__id__league_standings.request.json

선언형 API/사전 계약의 기획 참고본입니다. 실행 파일이나 테스트 결과가 아닙니다.

```json
{
  "endpoint_id": "GET__api_v1_fixtures__id__league_standings",
  "method": "GET",
  "path": "/api/v1/fixtures/{external_id}/league-standings",
  "from_feature": "fixture-detail",
  "fe_mockup_ref": "frontend/src/mocks/data/fixture-detail/league-standings.{external_id}.json",
  "handler_ref": "frontend/src/lib/api/fixtureDetail.ts (getLeagueStandings)",
  "spec_excerpt": "해당 fixture 가 속한 league 의 현재 시즌 순위표. 양 팀 row 만 하이라이트. 그룹 스테이지 컵대회는 그룹 단위 standings.",
  "auth": "public",
  "request_path_params": [{"name": "external_id", "type": "int"}],
  "response_shape": {
    "league": {"external_id":"int","slug":"string","name_ko":"string|null"},
    "season": "int",
    "format": "table|groups",
    "groups": [
      {
        "name": "string|null (A,B,... or null for 단일 table)",
        "rows": [
          {"rank":"int","team":{"external_id":"int","slug":"string","name_ko":"string|null","logo_url":"string|null"},"points":"int","played":"int","win":"int","draw":"int","loss":"int","goals_for":"int","goals_against":"int","goal_diff":"int","form":"string|null (e.g., 'WWDLW')"}
        ]
      }
    ]
  },
  "scenarios_used": ["normal_epl_table", "normal_ucl_groups", "empty"],
  "scenario_behavior": {
    "normal_epl_table": "200 with format=table, single group, 20 rows (e.g., 1000001 EPL)",
    "normal_ucl_groups": "200 with format=groups, 8 groups × 4 rows (e.g., 1000007 UCL group stage)",
    "empty": "200 with groups=[] (시즌 시작 전)"
  },
  "data_source": "standings 테이블 + team_translation",
  "notes_for_be": [
    "standings 테이블의 league_external_id + season + (선택)group_name 으로 필터",
    "form 컬럼이 있으면 사용, 없으면 null",
    "team_translation 조인으로 name_ko",
    "컵대회: standings.group_name 으로 그룹 분리. EPL/EFL 등 단일 table: format='table', groups[0].name=null"
  ]
}
```
