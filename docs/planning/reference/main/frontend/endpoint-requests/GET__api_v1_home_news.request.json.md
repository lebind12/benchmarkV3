> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `main` 워크트리의 `frontend/endpoint-requests/GET__api_v1_home_news.request.json`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# GET__api_v1_home_news.request.json

선언형 API/사전 계약의 기획 참고본입니다. 실행 파일이나 테스트 결과가 아닙니다.

```json
{
  "endpoint_id": "GET__api_v1_home_news",
  "method": "GET",
  "path": "/api/v1/home/news",
  "from_feature": "main-home",
  "fe_mockup_ref": "frontend/src/mocks/data/home/news.json",
  "handler_ref": "frontend/src/mocks/handlers/home.ts",
  "spec_excerpt": "큐브 1면(뉴스): 썸네일(없으면 placeholder) + title_ko (2줄 ellipsis) + 출처 도메인 + 게시 시각(상대시간). 클릭 시 새 탭 외부 link. 빈 상태: '오늘 EPL 관련 뉴스가 없습니다'. 5건이 안 나오면 placeholder 채우지 않고 있는 만큼만 표시. 6시간마다 갱신 안내. (spec §3.3, §3.4, §10)",
  "auth": "public",
  "request_query_params": [],
  "response_shape": {
    "items": [
      {
        "id": "string",
        "title_ko": "string|null",
        "title": "string",
        "summary_ko": "string|null",
        "source": "string (도메인)",
        "url": "string (절대 URL)",
        "thumbnail_url": "string|null",
        "published_at": "ISO8601 datetime UTC"
      }
    ]
  },
  "response_example": {
    "items": [
      {
        "id": "n1",
        "title_ko": "리버풀, 막판 동점골로 무승부",
        "title": "Liverpool snatch late equalizer",
        "summary_ko": "리버풀이 후반 추가시간 동점골로 1-1 무승부를 거뒀다.",
        "source": "bbc.com",
        "url": "https://example.com/news/1",
        "thumbnail_url": null,
        "published_at": "2026-05-14T08:00:00Z"
      }
    ]
  },
  "scenarios_used": ["normal", "empty", "error"],
  "scenario_behavior": {
    "empty": "200 { items: [] }",
    "error": "500 { error: 'mock error' }",
    "normal": "최대 5건. 최신순(published_at desc). EPL 키워드 필터 (news-fetcher 가 적재)"
  },
  "data_source": "news_article 테이블 (news-fetcher 적재). DB only, 신선도 1h",
  "notes_for_be": [
    "news-fetcher 워커가 적재하는 news_article 테이블 소비 (CLAUDE.md §4).",
    "FE 는 정확히 최신 5건을 기대하지만, 부족하면 있는 만큼 반환 — 빈 placeholder 채우지 말 것.",
    "title_ko NULL fallback 은 FE 가 처리(title 사용)."
  ]
}
```
