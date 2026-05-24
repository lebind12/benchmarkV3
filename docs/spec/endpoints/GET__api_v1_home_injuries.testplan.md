# GET__api_v1_home_injuries Test Plan

대상 spec: `docs/spec/endpoints/GET__api_v1_home_injuries.md`

## 1. 분류

| 분류 | 파일 | 의존성 | 마커 |
|---|---|---|---|
| 단위 | `tests/unit/test_home_injuries.py` | service mock, DB 없음 | `unit` |
| 통합 | `tests/integration/test_home_injuries.py` | 격리 schema Postgres + alembic | `integration` |

## 2. 단위 테스트

| ID | 케이스 | 검증 | 코드 경로 |
|---|---|---|---|
| HI-U-01 | 정상 응답 | public GET, FE injury shape 반환 | route/serializer |
| HI-U-02 | `expected_return:null` 허용 | null 도 200 | serializer |
| HI-U-03 | 빈 결과 | `items:[]` 도 200 | empty branch |

## 3. 통합 테스트

| ID | 케이스 | 검증 | 코드 경로 |
|---|---|---|---|
| HI-I-01 | current-season injury | active league current season row 반환 | SQL join/filter |
| HI-I-02 | reported_at order | 최신 reported_at 순서와 날짜 직렬화 | order/serializer |
| HI-I-03 | raw expected_return | raw_data 의 expected_return 을 응답 field 로 매핑 | raw_data mapping |

## 4. Red 기대

`app.services.home` 과 `/api/v1/home/injuries` route 가 아직 없으므로 단위 테스트는 실패해야 한다.

## 5. Coverage Mapping

라우터 정상/빈 branch 와 service 의 current-season filter, injury_type fallback, expected_return mapping 을 커버한다.
