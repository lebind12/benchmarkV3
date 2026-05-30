# benchmark

축구 정보 사이트 + 방송용 페이지. FastAPI + Supabase + Upstash. 도메인 SSOT 는 [`CLAUDE.md`](./CLAUDE.md), 작업 정본은 [`Plans.md`](./Plans.md).

## 로컬 실행

```bash
pip install -e '.[dev]' && uvicorn app.main:app --reload
```

## 프론트엔드 라우트 운영 상태

`ui-review` 후보 화면은 원본 사용자 라우트로 승격되어 운영 URL에서 바로 사용한다.

- `/` → `frontend/src/views/ui-review/UiReviewHomeView.vue`
- `/fixtures` → `frontend/src/views/ui-review/UiReviewFixturesView.vue`
- `/fixtures/:externalId` → `frontend/src/views/ui-review/UiReviewFixturePreviewView.vue`
- `/teams` → `frontend/src/views/ui-review/UiReviewTeamsView.vue`
- `/players` → `frontend/src/views/ui-review/UiReviewPlayersView.vue`
- `/stats` → `frontend/src/views/ui-review/UiReviewStatsView.vue`
- `/news` → `frontend/src/views/ui-review/UiReviewNewsView.vue`

`/ui-review/*` 라우트는 회귀 확인과 비교 확인용으로 유지한다. 아직 별도 후보 구현이 없는 `/standings`, `/teams/:slug`, `/players/:slug`, `/admin`은 기존 원본 화면을 계속 사용한다.
