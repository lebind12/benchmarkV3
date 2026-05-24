# GET__api_v1_home_transfers Test Plan

대상 spec: `docs/spec/endpoints/GET__api_v1_home_transfers.md`

## 1. 분류

| 분류 | 파일 | 의존성 | 마커 |
|---|---|---|---|
| 단위 | `tests/unit/test_home_transfers.py` | service mock, DB 없음 | `unit` |
| 통합 | `tests/integration/test_home_transfers.py` | 격리 schema Postgres + alembic | `integration` |

## 2. 단위 테스트

| ID | 케이스 | 검증 | 코드 경로 |
|---|---|---|---|
| HT-U-01 | 정상 응답 | public GET, FE transfer shape 반환 | route/serializer |
| HT-U-02 | `fee:null` 허용 | fee null 도 200 | serializer |
| HT-U-03 | 빈 결과 | `items:[]` 도 200 | empty branch |

## 3. 통합 테스트

| ID | 케이스 | 검증 | 코드 경로 |
|---|---|---|---|
| HT-I-01 | 최근 이적 5건 | transfer_date desc + id desc + limit | SQL order/limit |
| HT-I-02 | target league scope | active 5리그 관련 team/player row 만 포함 | league/team_season filter |
| HT-I-03 | unresolved team 제외 | from/to team null row 제외 | FE shape guard |

## 4. Red 기대

`app.services.home` 과 `/api/v1/home/transfers` route 가 아직 없으므로 단위 테스트는 실패해야 한다.

## 5. Coverage Mapping

라우터 정상/빈 branch 와 service 의 relation filter, resolved-team guard, fee mapping 을 커버한다.
