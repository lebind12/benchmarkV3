> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `main` 워크트리의 `frontend/endpoint-requests/GET__api_v1_home_injuries.request.json`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# GET__api_v1_home_injuries.request.json

선언형 API/사전 계약의 기획 참고본입니다. 실행 파일이나 테스트 결과가 아닙니다.

```json
{
  "endpoint_id": "GET__api_v1_home_injuries",
  "method": "GET",
  "path": "/api/v1/home/injuries",
  "from_feature": "main-home",
  "fe_mockup_ref": "frontend/src/mocks/data/home/injuries.json",
  "handler_ref": "frontend/src/mocks/handlers/home.ts",
  "spec_excerpt": "큐브 4면(부상): 선수 사진 + name_ko + 팀 배지 + 부상 종류 + 복귀 예상(있을 때). 클릭 시 /stats 부상 섹션. 빈 상태: '현재 보고된 부상자가 없습니다'. (spec §3.3)",
  "auth": "public",
  "request_query_params": [],
  "response_shape": {
    "items": [
      {
        "id": "string",
        "player": {
          "external_id": "number",
          "slug": "string",
          "name_ko": "string|null",
          "name": "string",
          "photo_url": "string|null",
          "team": "TeamRef",
          "league": "LeagueRef"
        },
        "injury_type": "string (한글, 예: '햄스트링')",
        "expected_return": "YYYY-MM-DD|null",
        "reported_at": "YYYY-MM-DD"
      }
    ]
  },
  "response_example_path": "frontend/src/mocks/data/home/injuries.json",
  "scenarios_used": ["normal", "empty", "error"],
  "scenario_behavior": {
    "empty": "200 { items: [] }",
    "error": "500",
    "normal": "현재 진행 중인 부상 최대 5건. reported_at desc. 5리그 소속 선수만"
  },
  "data_source": "injury 테이블 (daily-sync 적재).",
  "notes_for_be": [
    "injury_type 은 가능하면 한글. 자동번역 미적용 시 영문 가능 — FE 는 그대로 표기.",
    "expected_return 이 null 이면 FE 는 '복귀 미정' 표기 (생략 가능)."
  ]
}
```
