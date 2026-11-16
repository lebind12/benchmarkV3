> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `main` 워크트리의 `frontend/endpoint-requests/GET__api_v1_home_transfers.request.json`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# GET__api_v1_home_transfers.request.json

선언형 API/사전 계약의 기획 참고본입니다. 실행 파일이나 테스트 결과가 아닙니다.

```json
{
  "endpoint_id": "GET__api_v1_home_transfers",
  "method": "GET",
  "path": "/api/v1/home/transfers",
  "from_feature": "main-home",
  "fe_mockup_ref": "frontend/src/mocks/data/home/transfers.json",
  "handler_ref": "frontend/src/mocks/handlers/home.ts",
  "spec_excerpt": "큐브 3면(이적): 선수 사진 + name_ko + 'from team → to team' + 날짜(YYYY-MM-DD). 클릭 시 /stats 이적 섹션. 빈 상태: '최근 이적 정보가 없습니다'. (spec §3.3)",
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
        "from_team": {
          "external_id": "number",
          "slug": "string",
          "name_ko": "string|null",
          "short_name_ko": "string|null",
          "name": "string",
          "logo_url": "string|null"
        },
        "to_team": "(same shape as from_team)",
        "transfer_date": "YYYY-MM-DD",
        "fee": "string|null (예: '€103m')"
      }
    ]
  },
  "response_example_path": "frontend/src/mocks/data/home/transfers.json",
  "scenarios_used": ["normal", "empty", "error"],
  "scenario_behavior": {
    "empty": "200 { items: [] }",
    "error": "500",
    "normal": "최근 이적 최대 5건. transfer_date desc. 5리그 관련 (to_team 또는 from_team 이 5리그 소속이거나 player.league 가 5리그)"
  },
  "data_source": "transfer 테이블 (daily-sync 적재).",
  "notes_for_be": [
    "fee 는 원본 문자열 그대로(통화/단위 포함). 정규화는 MVP 외.",
    "from_team / to_team 모두 외부팀(다른 리그)일 수 있음 — short_name_ko 가 있으면 함께 반환."
  ]
}
```
