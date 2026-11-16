> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `main` 워크트리의 `docs/spec/endpoints/GET__api_v1_home_news.testplan.md`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# GET__api_v1_home_news Test Plan

대상 spec: `docs/spec/endpoints/GET__api_v1_home_news.md`

## 1. 분류

| 분류 | 파일 | 의존성 | 마커 |
|---|---|---|---|
| 단위 | `tests/unit/test_home_news.py` | service mock, DB 없음 | `unit` |
| 통합 | `tests/integration/test_home_news.py` | 격리 schema Postgres + alembic | `integration` |

## 2. 단위 테스트

| ID | 케이스 | 검증 | 코드 경로 |
|---|---|---|---|
| HN-U-01 | 정상 응답 | public GET, 최신 뉴스 shape 반환 | route/serializer |
| HN-U-02 | `title_ko` null | null 값도 200 으로 통과 | fallback contract |
| HN-U-03 | 빈 결과 | `items:[]` 도 200 | empty branch |

## 3. 통합 테스트

| ID | 케이스 | 검증 | 코드 경로 |
|---|---|---|---|
| HN-I-01 | 최신 5건 | 6개 seed 후 `published_at DESC`, limit 5 | SQL order/limit |
| HN-I-02 | column mapping | source_url/image_url/original_title 이 FE field 로 매핑 | serializer |

## 4. Red 기대

`app.services.home` 과 `/api/v1/home/news` route 가 아직 없으므로 단위 테스트는 실패해야 한다.

## 5. Coverage Mapping

라우터 정상/빈 branch 와 service 의 news_article order/limit/mapping 을 커버한다.
