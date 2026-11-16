> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `main` 워크트리의 `docs/spec/endpoints/phase-1-followup-l2.md`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# Phase 1 Follow-up L2 — `transfer` / `injury` / `news_article` 3 테이블 추가

본 문서는 BE 워크플로 spec 산출물이며, **additive DB migration** 의 요구사항 mirror 다.
정본은 `docs/spec/db-schema.md` §3.14, §3.15, §3.16.

> ⚠️ **불변 원칙**
> - 본 task 는 위 3 테이블 + 인덱스/UNIQUE 추가하는 **단일 마이그레이션 (0003)** 만 생성
> - 기존 마이그레이션 `0001_initial_schema.py`, `0002_league_is_active.py` **절대 수정 금지**
> - 컬럼/인덱스/제약 정본과 1:1 일치. 추가/누락/변경 금지
> - `h2h_fixture` (§3.17) 는 본 task 범위 외 — 별도 task 에서 처리

## 1. 범위

| 항목 | 변경 |
|---|---|
| 모델 | `app/models/` 에 `Transfer`, `Injury`, `NewsArticle` 추가 |
| 마이그레이션 | 신규 `alembic/versions/0003_transfer_injury_news.py` |
| 테이블 | `transfer`, `injury`, `news_article` |

본 task 의 be-dev 영역: `app/models/`, `alembic/versions/0003_*.py`. be-test 는 `app/` / `alembic/` 미수정.

## 2. 마이그레이션 메타데이터

| 항목 | 값 |
|---|---|
| `revision` | `0003_transfer_injury_news` |
| `down_revision` | `"0002_league_is_active"` |
| `branch_labels` | `None` |
| `depends_on` | `None` |

## 3. 테이블 정본

### 3.1 `transfer` (정본 §3.14)

```sql
CREATE TABLE transfer (
    id            bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    player_id     bigint      NOT NULL REFERENCES player(id)  ON DELETE CASCADE,
    transfer_date date        NOT NULL,
    type          text,
    from_team_id  bigint      REFERENCES team(id) ON DELETE SET NULL,
    to_team_id    bigint      REFERENCES team(id) ON DELETE SET NULL,
    raw_data      jsonb,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT transfer_uniq UNIQUE (player_id, transfer_date, from_team_id, to_team_id)
);
CREATE INDEX transfer_player_idx    ON transfer (player_id);
CREATE INDEX transfer_date_idx      ON transfer (transfer_date DESC);
CREATE INDEX transfer_to_team_idx   ON transfer (to_team_id);
CREATE INDEX transfer_from_team_idx ON transfer (from_team_id);
```

**NULL FK 처리**: `from_team_id` / `to_team_id` 둘 다 nullable. Free transfer (debut) 또는 retire 시 한쪽 NULL. UNIQUE 제약은 4-tuple 이지만 Postgres 의 기본 UNIQUE 동작으로 (player, date, NULL, X) 와 (player, date, NULL, X) 는 충돌 안 함 (NULL 은 distinct 로 취급). 운영상 같은 player 의 같은 date + 같은 from/to NULL row 가 중복 INSERT 가능. 본 task 는 정본 그대로 유지 (post-MVP 정책 결정).

### 3.2 `injury` (정본 §3.15)

```sql
CREATE TABLE injury (
    id           bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    player_id    bigint      NOT NULL REFERENCES player(id)  ON DELETE CASCADE,
    fixture_id   bigint      REFERENCES fixture(id) ON DELETE SET NULL,
    team_id      bigint      NOT NULL REFERENCES team(id)    ON DELETE CASCADE,
    league_id    bigint      NOT NULL REFERENCES league(id)  ON DELETE CASCADE,
    season_year  integer     NOT NULL,
    type         text,
    reason       text,
    raw_data     jsonb,
    reported_at  timestamptz,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT injury_uniq UNIQUE (player_id, fixture_id, league_id, season_year)
);
CREATE INDEX injury_player_idx      ON injury (player_id);
CREATE INDEX injury_team_season_idx ON injury (team_id, season_year);
CREATE INDEX injury_fixture_idx     ON injury (fixture_id) WHERE fixture_id IS NOT NULL;
```

**NULL fixture_id 처리**: 시즌 전체 부상 (특정 경기 무관) 인 경우 NULL. 동일 (player, NULL, league, season) 중복 INSERT 는 Postgres UNIQUE NULL distinct 동작으로 허용됨 (정본 그대로). partial index `injury_fixture_idx WHERE fixture_id IS NOT NULL` 로 fixture 별 조회 최적화.

### 3.3 `news_article` (정본 §3.16)

```sql
CREATE TABLE news_article (
    id               bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source           text        NOT NULL,
    source_url       text        NOT NULL UNIQUE,
    original_title   text        NOT NULL,
    original_summary text,
    published_at     timestamptz NOT NULL,
    image_url        text,
    title_ko         text,
    summary_ko       text,
    translated_at    timestamptz,
    tags             jsonb,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX news_article_published_idx ON news_article (published_at DESC);
CREATE INDEX news_article_pending_idx   ON news_article (created_at DESC) WHERE title_ko IS NULL;
CREATE INDEX news_article_tags_gin      ON news_article USING gin (tags);
```

**참고**: entity FK 없음. `tags` JSONB 는 `{teams: [external_id, ...], players: [external_id, ...]}` 형태. GIN 인덱스로 `tags @> ...` 조회 최적화.

## 4. ON DELETE 정책

| FROM → TO | ON DELETE |
|---|---|
| `transfer.player_id → player.id` | CASCADE |
| `transfer.from_team_id → team.id` | SET NULL |
| `transfer.to_team_id → team.id` | SET NULL |
| `injury.player_id → player.id` | CASCADE |
| `injury.team_id → team.id` | CASCADE |
| `injury.league_id → league.id` | CASCADE |
| `injury.fixture_id → fixture.id` | SET NULL |
| `news_article` | (FK 없음) |

## 5. upgrade() / downgrade() 요약

### upgrade()
1. `op.create_table("transfer", ...)` + 4 인덱스
2. `op.create_table("injury", ...)` + 2 일반 인덱스 + 1 partial 인덱스 (`WHERE fixture_id IS NOT NULL`)
3. `op.create_table("news_article", ...)` + 2 일반 인덱스 + 1 partial 인덱스 (`WHERE title_ko IS NULL`) + 1 GIN 인덱스 (`USING gin (tags)`)

### downgrade()
생성 역순:
1. `news_article` 인덱스 + 테이블 drop
2. `injury` 인덱스 + 테이블 drop
3. `transfer` 인덱스 + 테이블 drop

## 6. 모델 변경 (be-dev 영역)

`app/models/` 에 `Transfer`, `Injury`, `NewsArticle` 클래스 추가 + `app/models/__init__.py` 의 export 갱신. SQLAlchemy 2.x Mapped 스타일.

`jsonb` → `JSONB`, `timestamptz` → `DateTime(timezone=True)`, 부분 인덱스는 `Index(..., postgresql_where=...)`, GIN 인덱스는 `Index(..., postgresql_using="gin")` 사용.

## 7. 테이블 개수

- 0001 적용 후: 13 테이블
- 0002 적용 후: 13 테이블 (`league.is_active` 컬럼 추가, 테이블 수 동일)
- **0003 적용 후: 16 테이블** (+ transfer, injury, news_article)

## 8. 변경 기록

| 날짜 | 변경 |
|---|---|
| 2026-05-14 | spec 작성 (be-test, L2). db-schema.md §3.14/§3.15/§3.16 mirror |
