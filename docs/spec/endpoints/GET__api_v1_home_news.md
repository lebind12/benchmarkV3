# GET__api_v1_home_news

## 1. Endpoint

| 항목 | 값 |
|---|---|
| Method | `GET` |
| Path | `/api/v1/home/news` |
| Auth | public, JWT 불필요 |
| FE request | `frontend/endpoint-requests/GET__api_v1_home_news.request.json` |
| Feature SSOT | `docs/features/main-home.spec.md` §3.3~§3.4, `docs/features/main-home.devplan.md` §6~§7 |

홈 좌측 큐브 1면 "뉴스" 데이터. `news-fetcher` 가 적재한 `news_article` DB row 만 소비한다.

## 2. Query

없음.

## 3. Response

`200 OK`

```json
{
  "items": [
    {
      "id": "1",
      "title_ko": "리버풀, 막판 동점골로 무승부",
      "title": "Liverpool snatch late equalizer",
      "summary_ko": "리버풀이 후반 추가시간 동점골로 1-1 무승부를 거뒀다.",
      "source": "bbc.com",
      "url": "https://example.com/news/1",
      "thumbnail_url": null,
      "published_at": "2026-05-14T08:00:00Z"
    }
  ]
}
```

빈 결과는 `200 OK { "items": [] }`.

## 4. Business Rules

1. `news_article` 에 저장된 row 를 `published_at DESC`, `id DESC` 로 정렬한다.
2. 최대 5건을 반환한다. 5건 미만이어도 placeholder 를 채우지 않는다.
3. `id` 는 DB id 를 문자열로 직렬화한다.
4. `title` 은 `news_article.original_title`, `summary_ko` 는 `news_article.summary_ko`.
5. `url` 은 `news_article.source_url`, `thumbnail_url` 은 `news_article.image_url`.
6. `title_ko` 가 null 이어도 그대로 반환한다. FE 가 원문 title fallback 을 수행한다.
7. EPL 키워드 필터링은 `news-fetcher` 책임이며 endpoint 는 외부 RSS 를 호출하지 않는다.

## 5. DB Dependencies

- `news_article`

## 6. Error Cases

| 케이스 | 응답 |
|---|---|
| DB 조회 실패 | `500` + 공통 error body |

## 7. Expected BE Surface For Tests

`app.services.home.list_home_news(session, *, limit: int = 5) -> dict`

라우터는 위 service 를 호출해 같은 response shape 를 반환한다.
