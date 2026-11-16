> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `main` 워크트리의 `frontend/endpoint-requests/GET__api_v1_fixtures__id__events.request.json`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# GET__api_v1_fixtures__id__events.request.json

선언형 API/사전 계약의 기획 참고본입니다. 실행 파일이나 테스트 결과가 아닙니다.

```json
{
  "endpoint_id": "GET__api_v1_fixtures__id__events",
  "method": "GET",
  "path": "/api/v1/fixtures/{external_id}/events",
  "from_feature": "fixture-detail",
  "fe_mockup_ref": "frontend/src/mocks/data/fixture-detail/events.{external_id}.json",
  "handler_ref": "frontend/src/lib/api/fixtureDetail.ts (getEvents)",
  "spec_excerpt": "EventsTimeline 컴포넌트. 시간순(분/추가시간) 정렬된 이벤트 (goal/card/sub/var). 좌(home)/우(away) 정렬 결정은 team_external_id 매칭으로 FE 가 처리.",
  "auth": "public",
  "request_path_params": [{"name": "external_id", "type": "int"}],
  "response_shape": {
    "events": [
      {
        "minute": "int",
        "extra": "int|null",
        "team_external_id": "int",
        "type": "goal|yellow|red|sub|var",
        "player": {"external_id":"int","slug":"string","name":"string","name_ko":"string|null","photo_url":"string|null"},
        "assist": {"external_id":"int","slug":"string","name":"string","name_ko":"string|null"} ,
        "detail": "string|null"
      }
    ]
  },
  "scenarios_used": ["normal", "empty"],
  "scenario_behavior": {
    "normal": "200 timeline events (e.g., 1000001 with 4 goals + cards)",
    "empty": "200 { events: [] } (NS / pre-match)"
  },
  "data_source": "fixture_detail.events JSONB",
  "notes_for_be": [
    "fixture_detail.events 에서 minute/extra/team/type/player 추출",
    "API-Football 'events' 응답 구조를 정규화 (Goal/Card/subst/Var)",
    "assist/detail 은 nullable"
  ]
}
```
