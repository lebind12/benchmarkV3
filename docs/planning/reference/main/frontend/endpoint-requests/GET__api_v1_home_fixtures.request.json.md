> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `main` 워크트리의 `frontend/endpoint-requests/GET__api_v1_home_fixtures.request.json`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# GET__api_v1_home_fixtures.request.json

선언형 API/사전 계약의 기획 참고본입니다. 실행 파일이나 테스트 결과가 아닙니다.

```json
{
  "endpoint_id": "GET__api_v1_home_fixtures",
  "method": "GET",
  "path": "/api/v1/home/fixtures",
  "from_feature": "main-home",
  "fe_mockup_ref": "frontend/src/mocks/data/home/fixtures.json",
  "handler_ref": "frontend/src/mocks/handlers/home.ts",
  "spec_excerpt": "중앙 패널: 오늘/이번주/이번달 경기 리스트. 리그 필터 (전체 또는 5리그 중 하나) + 기간 필터 (day/week/month). 카드 = 리그 배지 + 홈/어웨이 + kickoff_at(NS) 또는 score(FT/AET/PEN) + status badge. 클릭 시 /fixtures/{external_id}. (spec §4)",
  "auth": "public",
  "request_query_params": [
    { "name": "league_id", "type": "number", "optional": true, "description": "external_id (39|2|3|48|45). 생략 = 전체" },
    { "name": "period", "type": "'day'|'week'|'month'", "optional": true, "default": "day", "description": "KST 기준. day=오늘(0시~다음0시), week=이번주(월~일), month=이번달" },
    { "name": "date", "type": "string YYYY-MM-DD (KST)", "optional": true, "default": "오늘 KST", "description": "특정 날짜의 fixture 만 반환. 생략 시 period 기준. 함께 오면 date 우선 + period 는 보조 정렬." }
  ],
  "response_shape": {
    "items": [
      {
        "external_id": "number (fixture external_id)",
        "league": {
          "external_id": "number",
          "slug": "string",
          "name_ko": "string|null",
          "short_name_ko": "string|null",
          "name": "string"
        },
        "home": {
          "external_id": "number",
          "slug": "string",
          "name_ko": "string|null",
          "short_name_ko": "string|null",
          "name": "string",
          "logo_url": "string|null"
        },
        "away": "(same shape as home)",
        "kickoff_at": "ISO8601 datetime UTC",
        "status_short": "'NS'|'FT'|'AET'|'PEN'|'PST'|'CANC'|'LIVE 등 API-Football status_short 그대로'",
        "goals_home": "number|null",
        "goals_away": "number|null"
      }
    ],
    "filters_applied": {
      "period": "'day'|'week'|'month'",
      "league_id": "number|undefined"
    }
  },
  "response_example_path": "frontend/src/mocks/data/home/fixtures.json",
  "scenarios_used": ["normal", "empty", "error"],
  "scenario_behavior": {
    "empty": "200 { items: [], filters_applied: {...} }",
    "error": "500",
    "normal": "필터 조건에 맞는 경기 리스트. kickoff_at asc 정렬 권장(시간순)."
  },
  "data_source": "fixture 테이블 (daily-sync 적재). 시즌 = current season 한정 (spec §8).",
  "notes_for_be": [
    "filters_applied 는 응답에 반드시 echo 해야 함 (FE 가 필터 동기화 검증).",
    "period 경계는 KST(Asia/Seoul) 기준 계산: day = 오늘 00:00 KST ~ 다음날 00:00 KST.",
    "라이브 매치도 DB stale 6h 정책상 status_short LIVE 그대로 가능 — FE 는 시각/스코어 표시 정책으로 처리.",
    "league_id 는 external_id (39/2/3/48/45)."
  ]
}
```
