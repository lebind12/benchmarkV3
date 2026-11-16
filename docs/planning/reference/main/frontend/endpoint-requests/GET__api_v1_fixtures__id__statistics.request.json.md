> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `main` 워크트리의 `frontend/endpoint-requests/GET__api_v1_fixtures__id__statistics.request.json`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# GET__api_v1_fixtures__id__statistics.request.json

선언형 API/사전 계약의 기획 참고본입니다. 실행 파일이나 테스트 결과가 아닙니다.

```json
{
  "endpoint_id": "GET__api_v1_fixtures__id__statistics",
  "method": "GET",
  "path": "/api/v1/fixtures/{external_id}/statistics",
  "from_feature": "fixture-detail",
  "fe_mockup_ref": "frontend/src/mocks/data/fixture-detail/statistics.{external_id}.json",
  "handler_ref": "frontend/src/lib/api/fixtureDetail.ts (getStatistics)",
  "spec_excerpt": "StatBarRow 컴포넌트. 양 팀 경기 통계 (점유율, 슛, 유효슛, 코너, 파울, 카드 등). 좌(home)/우(away) bar chart.",
  "auth": "public",
  "request_path_params": [{"name": "external_id", "type": "int"}],
  "response_shape": {
    "home": {
      "possession_pct": "float|null",
      "shots_total": "int",
      "shots_on": "int",
      "corners": "int",
      "fouls": "int",
      "yellow_cards": "int",
      "red_cards": "int",
      "offsides": "int",
      "passes_total": "int|null",
      "passes_accurate_pct": "float|null"
    },
    "away": "same shape"
  },
  "scenarios_used": ["normal", "empty"],
  "scenario_behavior": {
    "normal": "200 with full stats (e.g., 1000001 FT)",
    "empty": "200 with all int=0, possession_pct/passes_*=null (NS)"
  },
  "data_source": "fixture_detail.statistics JSONB",
  "notes_for_be": [
    "API-Football 'statistics' 응답의 Ball Possession, Total Shots 등 KEY 정규화",
    "possession_pct: '52%' 같은 문자열을 float 52.0 으로 변환",
    "FT 가 아니면 통계 부족 가능 → 누락 항목 0 또는 null"
  ]
}
```
