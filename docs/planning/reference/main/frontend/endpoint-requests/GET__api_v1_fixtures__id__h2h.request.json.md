> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `main` 워크트리의 `frontend/endpoint-requests/GET__api_v1_fixtures__id__h2h.request.json`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# GET__api_v1_fixtures__id__h2h.request.json

선언형 API/사전 계약의 기획 참고본입니다. 실행 파일이나 테스트 결과가 아닙니다.

```json
{
  "endpoint_id": "GET__api_v1_fixtures__id__h2h",
  "method": "GET",
  "path": "/api/v1/fixtures/{external_id}/h2h",
  "from_feature": "fixture-detail",
  "fe_mockup_ref": "frontend/src/mocks/data/fixture-detail/h2h.{external_id}.json",
  "handler_ref": "frontend/src/lib/api/fixtureDetail.ts (getH2H)",
  "spec_excerpt": "두 팀의 H2H 직전 5경기 리스트. kickoff_at desc, status_short=FT 만. 양 팀 슬롯 무관(home/away 가 뒤집힌 경기도 포함).",
  "auth": "public",
  "request_path_params": [{"name": "external_id", "type": "int"}],
  "request_query_params": [{"name": "limit", "type": "int", "default": 5, "max": 10}],
  "response_shape": {
    "h2h": [
      {
        "external_id": "int",
        "league": {"external_id":"int","slug":"string","name_ko":"string|null"},
        "kickoff_at": "ISO8601 UTC",
        "home": {"external_id":"int","slug":"string","name_ko":"string|null"},
        "away": {"external_id":"int","slug":"string","name_ko":"string|null"},
        "goals_home": "int",
        "goals_away": "int"
      }
    ]
  },
  "scenarios_used": ["normal", "empty"],
  "scenario_behavior": {
    "normal": "200 with up to limit FT fixtures sorted desc (e.g., 1000001 → 5 EPL classics)",
    "empty": "200 { h2h: [] } if 두 팀 간 직전 경기 없음"
  },
  "data_source": "h2h_fixture 테이블 (functional pair index 활용)",
  "notes_for_be": [
    "h2h_fixture 의 functional index (LEAST(home,away), GREATEST(home,away), kickoff_at DESC) 활용",
    "현재 fixture 의 home/away 추출 → 두 팀 매칭",
    "현재 fixture 자체는 제외",
    "league.name_ko fallback 영문 처리는 FE"
  ]
}
```
