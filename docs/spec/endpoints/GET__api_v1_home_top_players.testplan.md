# GET__api_v1_home_top_players Test Plan

대상 spec: `docs/spec/endpoints/GET__api_v1_home_top_players.md`

## 1. 분류

| 분류 | 파일 | 의존성 | 마커 |
|---|---|---|---|
| 단위 | `tests/unit/test_home_top_players.py` | service mock, DB 없음 | `unit` |
| 통합 | `tests/integration/test_home_top_players.py` | 격리 schema Postgres + alembic | `integration` |

외부 API-Football/OpenAI/Upstash 호출은 모든 테스트에서 금지한다.

## 2. 단위 테스트

| ID | 케이스 | 검증 | 코드 경로 |
|---|---|---|---|
| HTP-U-01 | 기본 요청 | public GET, `league_id=39`, `metric=goals` 기본값으로 service 호출 | route, query default |
| HTP-U-02 | 쿼리 override | `league_id=2&metric=assists` 가 service 에 전달 | route, query parsing |
| HTP-U-03 | 빈 결과 | `league:null`, `rows:[]` 도 200 으로 직렬화 | serializer |
| HTP-U-04 | invalid metric | `metric=saves` 는 422, service 미호출 | validation |

## 3. 통합 테스트

| ID | 케이스 | 검증 | 코드 경로 |
|---|---|---|---|
| HTP-I-01 | seeded goals ranking | 격리 schema 에 league/team/player/stat seed 후 metric desc + rank | SQL join/order |
| HTP-I-02 | zero metric excluded | 0점 row 는 제외되어 빈 rows 가능 | metric filter |

## 4. Red 기대

현 시점 app 은 `/health` 만 노출하고 `app.services.home` 이 없으므로 단위 테스트는 ImportError/404 로 실패해야 한다.

## 5. Coverage Mapping

라우터 validation/default + service query/order/empty branch 를 모두 커버한다. 예상 구현 파일 `app/api/home.py`, `app/services/home.py`, `app/schemas/home.py` 기준 80% 이상을 목표로 한다.
