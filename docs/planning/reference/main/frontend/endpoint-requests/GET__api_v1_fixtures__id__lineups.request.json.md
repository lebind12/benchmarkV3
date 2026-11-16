> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `main` 워크트리의 `frontend/endpoint-requests/GET__api_v1_fixtures__id__lineups.request.json`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# GET__api_v1_fixtures__id__lineups.request.json

선언형 API/사전 계약의 기획 참고본입니다. 실행 파일이나 테스트 결과가 아닙니다.

```json
{
  "endpoint_id": "GET__api_v1_fixtures__id__lineups",
  "method": "GET",
  "path": "/api/v1/fixtures/{external_id}/lineups",
  "from_feature": "fixture-detail",
  "fe_mockup_ref": "frontend/src/mocks/data/fixture-detail/lineups.{external_id}.json",
  "handler_ref": "frontend/src/lib/api/fixtureDetail.ts (getLineups)",
  "spec_excerpt": "FormationHalf 컴포넌트 (홈/원정 반쪽). 포메이션 문자열(e.g., '4-3-3') + 선발 11명 (grid_row/grid_col 위치) + 후보 7명 + 코치. 11+bench 토글로 후보 표시 (F37/F38).",
  "auth": "public",
  "request_path_params": [{"name": "external_id", "type": "int"}],
  "response_shape": {
    "home": {
      "formation": "string (e.g., '4-3-3')",
      "starting": [{"player":{"external_id":"int","slug":"string","name":"string","name_ko":"string|null","photo_url":"string|null"},"position":"GK|DF|MF|FW","grid_row":"int 1-4","grid_col":"int 1-5","shirt_number":"int|null"}],
      "bench": [{"player":{"external_id":"int","slug":"string","name":"string","name_ko":"string|null"}}],
      "coach": {"name":"string","name_ko":"string|null"}
    },
    "away": "same shape as home"
  },
  "scenarios_used": ["normal", "empty"],
  "scenario_behavior": {
    "normal": "200 with full lineups (e.g., 1000001 4-3-3 vs 4-2-3-1)",
    "empty": "200 with starting=[], bench=[] (NS pre-match e.g., 1000002)"
  },
  "data_source": "fixture_detail.lineups JSONB",
  "notes_for_be": [
    "API-Football 'lineups' 응답의 formation/startXI/substitutes/coach 정규화",
    "grid 좌표는 formation 문자열에서 계산 가능 (4-3-3 → 4 DF / 3 MF / 3 FW + 1 GK)",
    "선수 name_ko 는 player_translation 조인"
  ]
}
```
