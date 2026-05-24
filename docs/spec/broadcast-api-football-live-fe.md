# Broadcast API-Football Live FE Handler

작성일: 2026-05-14

## 1. 결정

방송용 오버레이(`/broadcast.html`)와 중계화면 포함 페이지(`/broadcast-program.html`)는 라이브 데이터에 한해 FE 에서 API-Football 을 직접 호출한다.

현재 사용자 결정:
- 이 두 방송용 화면은 FastAPI 백엔드 endpoint 를 사용하지 않는다.
- `/api/v1/...` 경로를 호출하지 않는다.
- 일반 사용자 페이지의 DB-only / 6h stale 정책은 그대로 유지한다.

## 2. 구현 위치

| 파일 | 역할 |
|---|---|
| `frontend/src/lib/api/apiFootballLive.ts` | API-Football 직접 호출, 응답 정규화 |
| `frontend/src/BroadcastApp.vue` | 크로마키 방송 오버레이에 live snapshot 적용 |
| `frontend/src/BroadcastProgramApp.vue` | 중계화면 포함 페이지 하단 캐러셀에 live snapshot 적용 |
| `frontend/tests/unit/lib/apiFootballLive.spec.ts` | FastAPI 를 거치지 않는 직접 호출 회귀 테스트 |

## 3. 환경 변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `VITE_BROADCAST_USE_API_FOOTBALL` | unset | `true` 일 때 방송용 live 직접 호출 활성화 |
| `VITE_USE_MOCK` | `true` | `false` 이고 API key 가 있으면 live 직접 호출 활성화 |
| `VITE_API_FOOTBALL_KEY` | unset | API-Football `x-apisports-key` 헤더 값 |
| `API_FOOTBALL_KEY` / `APIKEY` | unset | 사용자 로컬 `.env` 직접 접근용 fallback. Vite `envPrefix` 로 방송용 FE 번들에 노출됨 |
| `VITE_API_FOOTBALL_BASE_URL` | `https://v3.football.api-sports.io` | API-Football v3 base URL |
| `API_FOOTBALL_HOST` | unset | `VITE_API_FOOTBALL_BASE_URL` 이 없을 때 host fallback |
| `VITE_API_FOOTBALL_POLL_MS` | `10000` | 방송 페이지 live polling 주기 |

## 4. 호출 API

`fixture` query 가 있으면 해당 fixture 를 조회한다. 없으면 첫 live fixture 를 가져온다.

| API-Football endpoint | 사용 데이터 |
|---|---|
| `GET /fixtures?id={fixture_id}` | fixture status, score, team, venue |
| `GET /fixtures?live=all` | fixture query 가 없을 때 첫 live fixture 선택 |
| `GET /fixtures/events?fixture={fixture_id}` | goal, card, substitution, VAR 등 이벤트 |
| `GET /fixtures/lineups?fixture={fixture_id}` | formation, starting XI, player grid |
| `GET /fixtures/statistics?fixture={fixture_id}` | possession, shots, corners, passes, fouls, offsides |

## 5. 화면 동작

- `VITE_BROADCAST_USE_API_FOOTBALL=true` 또는 `VITE_USE_MOCK=false` + key 존재 시 live mode 로 전환한다.
- live mode 가 아니면 기존 mock 데이터를 유지한다.
- live 요청 실패 시 화면은 마지막 데이터 또는 mock 데이터를 유지하고 console 에 오류만 기록한다.
- 국가/팀 배지는 hardcoded flag URL 을 쓰지 않고 `/fixtures?id=...` 응답의 `teams.home.logo`, `teams.away.logo` 를 사용한다.
- API logo 값이 없으면 임의 국기 이미지로 대체하지 않고 팀 코드 텍스트 배지로 fallback 한다.
- 중계화면 하단 캐러셀은 기존 7초 vertical infinite carousel 규칙을 유지한다.
- 새 이벤트는 현재 카드 바로 다음 위치(index `1`)에 삽입되도록 정규화된 이벤트 큐를 구성한다.

## 6. 보안/운영 주의

이 결정은 사용자 요청에 따라 FastAPI 를 사용하지 않는 FE 직접 호출이다. 따라서 `VITE_API_FOOTBALL_KEY`, `API_FOOTBALL_KEY`, `APIKEY` 는 브라우저 번들/네트워크에서 노출될 수 있다. 운영 배포에서 키 보호가 필요하면 FastAPI 가 아닌 별도 edge/proxy 정책을 새 결정으로 분리해야 한다.

## 7. 참고

- API-Football v3 documentation: `https://www.api-football.com/documentation-v3`
- API-Football beginner guide: `https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide`

## 8. Fixture Samples

방송 화면 확인용 fixture id 는 `docs/spec/broadcast-api-football-fixture-samples.md` 에 보관한다.
