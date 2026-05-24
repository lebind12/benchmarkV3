# Current Tasklist

갱신일: 2026-05-24

이 문서는 `Plans.md` 와 `.codex/state` 를 대조해 만든 현재 실행용 태스크리스트다. 장기 계획의 정본은 `Plans.md` 이고, workflow 상태의 정본은 `.codex/state/{feature-flow,endpoint-flow}/` 이다.

## 현재 진행 요약

| 영역 | 현재 상태 | 근거 |
|---|---|---|
| Codex harness migration | `.codex/agents`, `.codex/schemas`, `.codex/state`, `scripts/*-flow.sh` 존재. `validate-all` PASS | `.codex/`, `scripts/harness-flow.mjs` |
| FE mock: main-home | Mock lifecycle 완료, BE 대기 | `.codex/state/feature-flow/main-home.json` = `FE_DONE_AWAITING_BE` |
| FE mock: fixture-detail | Mock lifecycle 완료, BE 대기 | `.codex/state/feature-flow/fixture-detail.json` = `FE_DONE_AWAITING_BE` |
| FE mock: broadcast-match-overlay | Mock lifecycle 완료, BE 대기 | `.codex/state/feature-flow/broadcast-match-overlay.json` = `FE_DONE_AWAITING_BE` |
| BE foundation | DB schema / league active / transfer-injury-news / h2h / translation-filler 완료 | endpoint-flow foundation states = `MERGED` |
| BE FE-follow endpoints | home 7개 + fixture-detail 6개가 `SPEC_REVIEW`; broadcast overlay는 `FE_REQUESTED` | `.codex/state/endpoint-flow/GET__*.json` |
| Local unit probe | home endpoint unit 29/29 PASS, fixture-detail endpoint unit 22/22 PASS, worker/admin unit 22/22 PASS | 2026-05-24 로컬 실행 |
| Harness unit probe | harness-flow unit 7/7 PASS | 2026-05-24 로컬 실행 |
| Frontend integration | 미시작 | BE endpoint `MERGED` 이후 시작 가능 |
| Infra secrets / CI | 미완료 | `.github/` 없음, `Plans.md` 0.1~0.3 / 7.5~7.9 / 10.7~10.10 |

## 바로 할 일

| Priority | Task | 내용 | DoD | Depends | Owner |
|---|---|---|---|---|---|
| P0 | T0.1 | 기록/상태 정리 커밋 | `Plans.md`, `docs/tasks/current-tasklist.md`, `.codex` state가 현재 진행과 일치하고 커밋됨 | - | team-lead |
| P0 | T0.2 | 하네스 검증 재확인 | `scripts/feature-flow.sh validate-all` + `scripts/endpoint-flow.sh validate-all` 통과 | T0.1 | team-lead |
| P0 | T1.1 | 13개 일반/디테일 endpoint spec review | home 7개 + fixture-detail 6개가 `SPEC_APPROVED` 로 전이 | T0.2 | be-reviewer |
| P0 | T1.2 | broadcast overlay endpoint lifecycle 시작 | `GET__api_v1_broadcast_fixtures__id__overlay` spec/test 작성 후 `SPEC_REVIEW` | T0.2 | be-test |
| P1 | T2.1 | 13개 일반/디테일 endpoint integration test 실행 | 관련 integration test PASS 로그 기록 | T1.1 | be-test |
| P1 | T2.2 | 13개 일반/디테일 endpoint implementation review + merge gate | 구현 endpoint 가 `MERGED` 상태, review artifact 기록 | T2.1 | be-reviewer |
| P1 | T2.3 | broadcast overlay GET 구현 | STREAMER 권한, API-Football + cache, 10초 polling 정책 테스트 통과 | T1.2 | be-dev |
| P1 | T3.1 | FE integration lifecycle 시작 | `main-home`, `fixture-detail` integration state 전이 | T2.2 | team-lead |
| P1 | T3.2 | FE mock fetch 를 실 API + zod 검증으로 교체 | mock 제거/토글 정리, L3 test 추가 | T3.1 | fe-dev |
| P1 | T3.3 | FE integration review / L3 / L4 | integration feature state `DONE` | T3.2 | fe-reviewer |

## FE-Requested Endpoint Queue

| Endpoint id | Method | Path | Feature | State |
|---|---|---|---|---|
| `GET__api_v1_home_fixtures` | GET | `/api/v1/home/fixtures` | main-home | `SPEC_REVIEW` |
| `GET__api_v1_home_standings` | GET | `/api/v1/home/standings` | main-home | `SPEC_REVIEW` |
| `GET__api_v1_home_top_players` | GET | `/api/v1/home/top-players` | main-home | `SPEC_REVIEW` |
| `GET__api_v1_home_hot_players` | GET | `/api/v1/home/hot-players` | main-home | `SPEC_REVIEW` |
| `GET__api_v1_home_news` | GET | `/api/v1/home/news` | main-home | `SPEC_REVIEW` |
| `GET__api_v1_home_transfers` | GET | `/api/v1/home/transfers` | main-home | `SPEC_REVIEW` |
| `GET__api_v1_home_injuries` | GET | `/api/v1/home/injuries` | main-home | `SPEC_REVIEW` |
| `GET__api_v1_fixtures__id` | GET | `/api/v1/fixtures/{external_id}` | fixture-detail | `SPEC_REVIEW` |
| `GET__api_v1_fixtures__id__events` | GET | `/api/v1/fixtures/{external_id}/events` | fixture-detail | `SPEC_REVIEW` |
| `GET__api_v1_fixtures__id__lineups` | GET | `/api/v1/fixtures/{external_id}/lineups` | fixture-detail | `SPEC_REVIEW` |
| `GET__api_v1_fixtures__id__h2h` | GET | `/api/v1/fixtures/{external_id}/h2h` | fixture-detail | `SPEC_REVIEW` |
| `GET__api_v1_fixtures__id__statistics` | GET | `/api/v1/fixtures/{external_id}/statistics` | fixture-detail | `SPEC_REVIEW` |
| `GET__api_v1_fixtures__id__league_standings` | GET | `/api/v1/fixtures/{external_id}/league-standings` | fixture-detail | `SPEC_REVIEW` |
| `GET__api_v1_broadcast_fixtures__id__overlay` | GET | `/api/v1/broadcast/fixtures/{external_id}/overlay` | broadcast-match-overlay | `FE_REQUESTED` |

## 현재 주의점

- `.codex/state` 는 official workflow 상태만 나타낸다. 현재 작업트리에 home/fixture-detail endpoint 구현이 있고 unit probe는 green이지만, 아직 spec approval / integration / implementation review / merge gate가 끝난 것은 아니다.
- `GET /api/v1/broadcast/fixtures/{external_id}/overlay` 는 아직 실제 라우트가 없다. 현재 [app/api/v1/broadcast.py](/Users/woolee/benchmark/app/api/v1/broadcast.py:31)는 `POST /api/v1/broadcast/translations` 만 제공한다.
- `.github/` 디렉터리가 없어 CI/GH Actions 계열 작업은 모두 남아 있다.
- 대량 source/frontend/assets 변경은 이번 P0 기록 커밋과 분리한다.

## Backlog

| Priority | Plans task | 내용 | Blocker / dependency |
|---|---|---|---|
| P1 | 0.1~0.3 | Supabase/Koyeb/Upstash env 및 GH Secrets 마무리 | 배포/통합 테스트 안정화 전 필요 |
| P1 | 2.1~2.5 | league/team/player translation seed import 결과 검증 | seed 파일과 import script는 존재하므로 DB row count/중복/결측 검증으로 범위 조정 |
| P1 | 4.1, 4.3~4.8 | daily-sync 통합 검증/운영 dry-run | unit green 이후 실제 DB/API-Football 경로 검증 필요 |
| P1 | 5.5.1~5.5.3 | news-fetcher 통합 검증/스케줄 등록 | unit green 이후 RSS fetch/store dry-run 필요 |
| P1 | 5.6.1~5.6.3 | news-translator 통합 검증/스케줄 등록 | unit green 이후 mock/real OpenAI 운영 정책 검증 필요 |
| P2 | 1.8 | Supabase RLS 정책 결정 | 인증/권한 phase 전에 결정 필요 |
| P2 | 3.1~3.5 | 인증/JWT/refresh/role endpoint | 방송용 STREAMER/ADMIN 기능 전 필요 |
| P2 | 7.5~7.9, 10.7~10.10 | GH Actions / reviewer automation / Vercel preview | PR 자동화와 integration L3 안정화 |
| P2 | 9.3~9.11 | FE infra 나머지 상태 확정 | 일부 구현되어 있어 `Plans.md` 검증 후 상태 갱신 필요 |
| P3 | 11.1~11.5 | feature catalog, sitemap, 이후 page-led feature 반복 | main-home/fixture-detail integration 후 진행 |
