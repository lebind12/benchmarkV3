# GET__api_v1_home_hot_players Test Plan

대상 spec: `docs/spec/endpoints/GET__api_v1_home_hot_players.md`

## 1. 분류

| 분류 | 파일 | 의존성 | 마커 |
|---|---|---|---|
| 단위 | `tests/unit/test_home_hot_players.py` | service mock, DB 없음 | `unit` |
| 통합 | `tests/integration/test_home_hot_players.py` | 격리 schema Postgres + alembic | `integration` |

## 2. 단위 테스트

| ID | 케이스 | 검증 | 코드 경로 |
|---|---|---|---|
| HHP-U-01 | 정상 응답 | public GET, service payload 그대로 반환 | route |
| HHP-U-02 | score invariant | 응답의 `score == goals + assists` | serializer contract |
| HHP-U-03 | 빈 결과 | `items:[]` 도 200 | empty branch |

## 3. 통합 테스트

| ID | 케이스 | 검증 | 코드 경로 |
|---|---|---|---|
| HHP-I-01 | 5리그 current season 합산 | 여러 리그 stat seed 후 score desc top 5 | SQL join/order/limit |
| HHP-I-02 | inactive/zero score 제외 | inactive league 와 score 0 row 제외 | league filter |

## 4. Red 기대

`app.services.home` 과 route 가 아직 없으므로 단위 테스트는 실패해야 한다.

## 5. Coverage Mapping

라우터 정상/빈 branch 와 service 의 current-season filter, score 계산, top 5 limit 을 커버한다.
