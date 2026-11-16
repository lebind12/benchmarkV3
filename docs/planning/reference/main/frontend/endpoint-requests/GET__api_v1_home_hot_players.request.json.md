> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `main` 워크트리의 `frontend/endpoint-requests/GET__api_v1_home_hot_players.request.json`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# GET__api_v1_home_hot_players.request.json

선언형 API/사전 계약의 기획 참고본입니다. 실행 파일이나 테스트 결과가 아닙니다.

```json
{
  "endpoint_id": "GET__api_v1_home_hot_players",
  "method": "GET",
  "path": "/api/v1/home/hot-players",
  "from_feature": "main-home",
  "fe_mockup_ref": "frontend/src/mocks/data/home/hot.json",
  "handler_ref": "frontend/src/mocks/handlers/home.ts",
  "spec_excerpt": "큐브 2면(핫 선수): 선수 사진 + name_ko + 팀 배지 + 골+어시스트 합산점(score) + 리그 배지. 클릭 시 /players/{slug}. 빈 상태: '시즌 휴식 중입니다'. (spec §3.3)",
  "auth": "public",
  "request_query_params": [],
  "response_shape": {
    "items": [
      {
        "player": {
          "external_id": "number",
          "slug": "string",
          "name_ko": "string|null",
          "name": "string",
          "photo_url": "string|null",
          "team": {
            "external_id": "number",
            "slug": "string",
            "name_ko": "string|null",
            "name": "string",
            "logo_url": "string|null"
          },
          "league": {
            "external_id": "number",
            "slug": "string",
            "name_ko": "string|null",
            "name": "string"
          }
        },
        "goals": "number",
        "assists": "number",
        "score": "number (= goals + assists)"
      }
    ]
  },
  "response_example_path": "frontend/src/mocks/data/home/hot.json",
  "scenarios_used": ["normal", "empty", "error", "null-ko"],
  "scenario_behavior": {
    "empty": "200 { items: [] }",
    "error": "500",
    "null-ko": "모든 name_ko 를 null 로 (FE 의 영문 fallback 검증용 — 운영에서는 발생 시점에 따라 자연 발생)",
    "normal": "최대 5건. 현재 시즌 (current season) 전 리그 합산 score desc 정렬"
  },
  "data_source": "player + 시즌 stats 집계 (goals, assists). 현재 시즌, 5리그 한정 (CLAUDE.md §2)",
  "notes_for_be": [
    "리그 = 5개 활성 league 만 (is_active=true). 컵대회 포함.",
    "score = goals + assists 단순 합 (FE 가 표시).",
    "name_ko 가 NULL 이어도 반환 가능 — FE 가 영문 fallback."
  ]
}
```
