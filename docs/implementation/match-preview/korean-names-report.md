# 팀·선수 표시 이름 한국어화 (DB 값 사용) — 구현 보고

작성: 2026-11-11 KST. 담당: DeepSeek 구현 워커(MP-names, `task_0c827d5b31a1`).
실제 모델: `deepseek-ai/deepseek-v4.1-flash-1017` (hive, dsh-tui 프로필, Max).

## 1. 요구사항

사용자 요구: **팀·선수 표시 이름은 기존 DB의 한국어 이름 값을 쓴다.** 대상은 경기 목록,
홈/원정 제목, 주목 선수 선택 표시, 그리고 본문 문장 안의 언급까지다. 모델이 만든 영어
표기나 AI 번역·음차를 표시 값으로 쓰지 않는다.

## 2. 결론 (먼저 읽을 것)

| 구분 | 상태 |
|---|---|
| 해석기(resolver) 구현 | 완료. `app/preview/localized_names.py` |
| 집중 검사 | 완료. 21건 통과(`tests/preview/test_localized_names.py`) |
| 이름 읽기 권한 | 완료. 새 역할 `preview_dev_names_ro`(열 단위 SELECT만) |
| 실제 DB 값 확인 | 완료. 읽기 전용·범위 한정(fixture 1557474 관련 4개 팀/선수 + 로스터 66행) |
| **공유 렌더러 연결(UI에 한국어가 실제로 나가는 것)** | **미완료.** MP10/root 소유 공유 파일이라 이 워커는 수정하지 않았다 |
| 저장된 과거 본문/승인/원문 변경 | 없음(변경 금지) |

즉 **해석기는 준비됐지만, 화면에 한국어가 나오는 것은 아직 아니다.** 연결 절차는 §7에
그대로 적었다.

## 3. 실제 DB 스키마 (추측 아님)

기존 운영(Supabase) DB를 읽기 전용으로 직접 확인했다(PostgreSQL 17.6).

| 표 | 확인한 열 |
|---|---|
| `public.team` | `id`(PK, DB 내부), `external_id`(UNIQUE, API-Football 팀 ID), `name`(영어), `slug`, `code`, `country`, `founded`, `is_national`, `logo_url`, `venue_id`, `created_at`, `updated_at` |
| `public.team_translation` | `team_id`(PK/FK), `name_ko`, `short_name_ko`, `updated_at`, `version`, `human_modified`, `editor_id` |
| `public.player` | `id`(PK), `external_id`(UNIQUE, API-Football 선수 ID), `name`(표시 영어명), `firstname`, `lastname`, `age`, `birth_*`, `nationality`, `height_cm`, `weight_kg`, `injured`, `photo_url`, `current_team_id`, `slug`, `created_at`, `updated_at` |
| `public.player_translation` | `player_id`(PK/FK), `name_ko`, `short_name_ko`, `updated_at`, `version`, `human_modified`, `editor_id` |

- 한국어는 **별도 번역 표**에 있다. `team`/`player` 본체에 한국어 열은 없다. 별칭
  (alias/alternate name) 표는 `public`에 **없다**. 대신 `short_name_ko`가 사실상의 짧은
  표기다.
- 한국어 보유율: `team_translation` 1250/1250행 값 있음, `player_translation` 11761/12353행.
  **592명은 한국어 값이 실제로 없다** → 지어내지 않고 원래 이름 유지 + 사유 기록.
- 네 표 모두 RLS 비활성, 정책 없음.
- **ID 공간이 두 개다.** `public.fixture.home_team_id/away_team_id`는 `public.team.id`
  (내부 키)를 가리킨다(예: 맨시티 13, 풀럼 4). 반면 `FixtureIdentity`에 값을 넣는 경로가
  둘로 갈린다. 저장 자료 경로(`sources/fixtures.py`, `data.py`, `store.py`)는 내부 키를,
  `sources/api_football.py`의 `FixtureRecord.identity()`는 API 팀 ID를 넣는다. 실제
  `preview_dev.preview_runs` 행은 내부 키(13/4)를 쓰고 있었다. 그래서 해석기는 ID 공간을
  **명시적으로** 받고, 없으면 이름으로 대신 찾지 않는다.

## 4. 이름 읽기 권한 (새 역할, 범위 최소)

기존 역할은 `public.player`/`*_translation` SELECT가 없어서, 사용자 승인 범위(이름 읽기)
안에서 **새 역할**을 만들었다.

- 역할: `preview_dev_names_ro`, `LOGIN`, `NOSUPERUSER NOCREATEDB NOCREATEROLE
  NOREPLICATION NOBYPASSRLS NOINHERIT`
- 데이터베이스 `CONNECT`, `public` 스키마 `USAGE`만. `public` `CREATE` 없음,
  `preview_dev` 접근 없음.
- **열 단위 `SELECT`만**:
  - `public.team(id, external_id, name)`
  - `public.team_translation(team_id, name_ko, short_name_ko)`
  - `public.player(id, external_id, name, firstname, lastname, current_team_id)`
  - `public.player_translation(player_id, name_ko)`
- 주지 않은 것: 선수 통계(`player_season_stat`), 계정(`app_user`), 생년/국적/신체/사진/
  slug 같은 개인·부가 정보, 표 전체 권한, 쓰기 권한 전부.
- 기존 역할(`identity_ro`, `fixture_ro`, `app`) 권한 확대 없음. 기존 비밀번호 회전 없음.
  스키마·RLS·트리거 변경 없음.
- 검증: `information_schema.column_privileges`와 `has_*_privilege` introspection. 실제
  DML 탐침은 실행하지 않았다. 금지 열은 전부 DENY, 표 전체 권한은 전부 false였다.
- 비밀값: `~/.config/match-preview/preview-dev.env`(mode 600)에
  `PREVIEW_NAMES_DATABASE_URL` 키로만 저장. 값은 프롬프트·보고서·증거에 쓰지 않았다.
- 준비 스크립트: `scripts/preview_dev_names_ro_provision.py` (1회성, 앱 런타임 아님).
  재실행 시 기존 역할 비밀번호를 회전하지 않는다(`--issue-password`를 줘야 자기 역할만
  재발급).

## 5. 해석기 인터페이스

`app/preview/localized_names.py`가 내보내는 것:

```python
DbNameLookup.from_url(dsn)
  .load_teams(*, team_ids=None, external_ids=None)      # 범위 없으면 ValueError
  .load_players(*, team_ids=None, player_ids=None, external_ids=None)

load_name_index(lookup, *, team_ids=None, team_external_ids=None,
                include_rosters=True, player_ids=None) -> LocalizedNameIndex

DisplayNames(index)
  .resolve_team(value=None, *, team_id=None, external_id=None, id_space="internal")
  .fixture_label(*, home_team_id=None, away_team_id=None, id_space="internal",
                 home_name=None, away_name=None, fallback=None) -> str
  .resolve_player(name, *, team_hint=None, scope_team_ids=None,
                  player_id=None, external_id=None, id_space="internal",
                  id_is_hint=False) -> PlayerResolution
  .confirm_player(name, *, team_hint=None, scope_team_ids=None) -> PlayerResolution
  .watch_players(items, *, scope_team_ids=None) -> WatchPlayersResult
  .rewrite_body(text) -> str
  .unmapped -> tuple[UnmappedName]     # .to_dict() = {kind, original, reason, detail}
```

- `NameSource`: `db_korean` / `db_short_korean` / `original`.
- `NameReason`: `not_found` / `ambiguous` / `db_korean_missing` / `empty` / `conflict`.
- 반환 객체는 `display_name`(표시)과 `english_name`(원문)을 함께 둔다. 원문은 진단·추적용
  으로 남고 화면에는 `display_name`만 쓰면 된다.

## 6. 동작 규칙 (왜 이렇게 했는지)

1. **번역하지 않는다.** 표시 값은 `name_ko`/`short_name_ko`에 있는 문자열뿐이다. 없으면
   원래 표기를 유지하고 `db_korean_missing`/`not_found`를 남긴다.
2. **ID가 우선, 이름은 보조.** ID가 오면 그 공간에서만 찾는다. 신뢰 ID(기본값,
   `id_is_hint=False`)가 없으면 이름으로 대신 찾지 않고 미해결로 돌려준다(다른 공간의 같은
   숫자를 다른 팀으로 읽는 사고 방지).
   예외: **검증되지 않은 참조**는 `id_is_hint=True`로 넘긴다. 모델이 응답에 적은
   `player_ref`가 이 경우다. 그 숫자가 우리 DB에 없으면 ID를 버리고 이름 표기로 다시
   확인한다. 모델이 숫자를 잘못 적었다고 확실한 한국어 이름을 포기하지 않기 위해서다.
   반대로 **ID와 이름이 서로 다른 선수를 가리키면** `conflict`로 돌려주고 어느 쪽도
   임의로 고르지 않는다(다른 사람 이름을 붙이는 것이 가장 나쁜 결과다).
3. **애매하면 안 고른다.** 같은 등급 후보가 여럿이면 `ambiguous`로 돌려주고 원래 이름을
   유지한다. 예: 성만 같은 두 선수.
4. **매칭은 결정적 규칙만.** 정규화(대소문자·발음기호·HTML 엔티티·머리글자 마침표) 후
   ① DB `name` 일치 ② 이름+성 전체 ③ 이름+성 낱말 ④ 머리글자+성 ⑤ 성 단독 순으로 센
   등급을 쓴다. 유사도·임베딩·모델·외부 API를 쓰지 않는다. 실제 payload가 `Erling
   Haaland`인데 DB `name`이 `E. Haaland`여도 ④로 확정된다.
5. **본문 치환은 안전하게.** 정렬된 정규식(긴 표기 우선), 라틴 문자·숫자 기준 낱말 경계,
   URL 구간 제외, 한 번만 훑기(치환 결과 재처리 없음 → 멱등), 반복 언급 모두 처리.
   한국어 조사가 붙은 `Manchester City와`도 같은 이름으로 본다.
6. **확인된 표기만 바꾼다(추측 치환 금지).** 치환 대상은 (a) DB에 저장된 표기
   (`A. Iwobi`, `Rodrigo Muniz`, `Manchester City`)와 (b) 이 실행에서
   `resolve_player`/`watch_players`/`confirm_player`로 확정한 모델 표기다. 본문에만 있고
   아무 단계에서도 확인하지 않은 이름은 원문을 유지한다. 실제 사례: 모델이 `Alex Iwobi`라고
   썼지만 확정 전에는 `A. Iwobi`만 DB 표기라 바뀌지 않는다. 그래서 렌더러는 **화면에 낼
   선수를 먼저 확인한 뒤** 본문을 치환해야 한다(§7-5).
7. **성 단독 표기(`Iwobi`)는 치환 표기로 등록하지 않는다.** 등록하면 `Alex Iwobi`가
   `Alex 알렉산더 츄카 이워비`로 깨진다(실제 저장 본문으로 확인된 결함). 성 단독 해석은
   `resolve_player`가 범위·유일성 검사를 거쳐 처리한다. 마찬가지로 선수의 `short_name_ko`
   도 치환 표기로 등록하지 않는다(한국어 이름에 붙으면 없는 이름이 합성된다).
   팀 약칭(`맨시티`)은 인명 접두와 충돌하지 않아 등록한다.
8. **범위 한정 읽기.** 필터 없는 조회는 `ValueError`로 거부한다. fixture 1557474 확인 시
   실제로 읽은 것은 팀 2행 + 그 로스터 66행뿐이다.
9. **실패는 조용히 원문 유지.** DSN이 없거나 읽기가 실패하면 해석을 건너뛰고 지금처럼
   원문을 쓴다. 실행을 실패시키지 않는다.

## 7. 공유 렌더러 연결 절차 (아직 하지 않음)

공유 파일(`config.py`, `presentation.py`, `sections.py`, `form.py`, `contracts.py`)은 MP10/
root 소유라 이 워커는 수정하지 않았다. 연결은 다음 순서면 된다.

1. `app/core/config.py`에 `names_database_url: str | None = None` 추가(`PREVIEW_` 접두어로
   `PREVIEW_NAMES_DATABASE_URL`을 읽는다). fixture/identity DSN 재사용 금지(역할이 다르다).
2. 실행/요청 단위로 `lookup` 하나를 만들고 `load_name_index(lookup, team_ids=[홈, 원정])`로
   인덱스를 만든 뒤 `DisplayNames(index)`. 종료 시 `lookup.close()`.
3. `identity.home_team_id/away_team_id`는 저장 자료 경로에서 **내부 키**이므로
   `id_space="internal"`(기본값)을 쓴다. API 팀 ID를 넣는 경로만 `"external"`.
4. 경기 목록·홈/원정 제목: `fixture_label(...)` 대신 `names.fixture_label(...)`.
5. 주목 선수: `form.py`가 만든 목록을 `names.watch_players(items,
   scope_team_ids=[홈, 원정])`로 변환해 화면에는 `res.rows`를 쓴다. **원본 목록은 그대로
   보존**하고, `res.unmapped`는 관리자 진단에만 넣는다(독자 응답 금지).
   `watch_players`가 확정한 선수 표기는 자동으로 치환 표기에 등록되므로, 이 단계를 먼저
   하면 §6의 본문 치환에서 모델 표기까지 같은 값으로 바뀐다.
6. 본문 문장: `compose_reader_body` 결과와 `presentation.to_preview_document`의 표시
   문자열에 **표시 경계에서만** `names.rewrite_body(...)`를 적용한다. 저장 본문·원문
   응답은 절대 다시 쓰지 않는다.
7. 출처 구분: 표시 치환이라는 사실을 별도 필드/버전으로 남긴다. 과거 원문 본문을 승인된
   것처럼 덮어쓰지 않는다. AGENTS 기준상 같은 엔티티의 표시 정정만으로 새 의미 워크플로우
   승인을 요구하지는 않지만, 과거 승인 기록을 조용히 바꾸면 안 된다.
8. 실패 격리: 위 5~6단계는 try/except로 감싸 실패 시 기존 표기를 그대로 쓴다.

## 8. 실제 DB 확인 결과 (읽기 전용)

근거: `evidence/korean-names/02-real-db-check.json`

| 항목 | 값 |
|---|---|
| `fixture_label(home_team_id=13, away_team_id=4)` | `맨체스터 시티 vs 풀럼` |
| 주목 선수(영어 payload) | `Erling Haaland`→`엘링 홀란드`, `Alex Iwobi`→`알렉산더 츄카 이워비`, `Rodrigo Muniz`→`로드리고 무니즈` |
| 팀 표기 | `Manchester City`→`맨체스터 시티`, `Fulham`→`풀럼` |
| 미해결 | 0건 |
| 실제 저장 본문(868자, run `6e59041a…` 최신 v6) 치환 후 | 824자, 문단 6→6 유지, 남은 영어 이름 0건(Manchester City/Fulham/Erling Haaland/Alex Iwobi/Rodrigo Muniz 모두 false) |
| URL 보존 | `https://example.com/Manchester-City/Erling-Haaland` 그대로 |

치환 후 길이가 줄어든 것은 `Manchester City`(15자) → `맨체스터 시티`(7자)처럼 표기 길이가
줄었기 때문이다. 문단 수는 6→6으로 같고, 치환된 전문을 근거 JSON에 함께 저장했다.

## 9. 검사

- `tests/preview/test_localized_names.py` **21건 통과**. 근거:
  `evidence/korean-names/01-focused-tests.txt`
- 검사가 고정하는 동작: DB 한국어 값이 영어보다 우선(팀+주목 선수), ID 공간 혼용 시 확정
  거부, 동률 후보 미선택, 한국어 값 없음/미매칭 시 원문 유지+사유, URL·다른 고유명사·
  부분 문자열 보존, 반복 언급 안전, 확인한 표기만 치환, 성 단독 표기 미등록, 멱등성,
  무필터 조회 거부, 검증되지 않은 참조의 이름 폴백, ID·이름 충돌 시 미선택.
- 영향 경로 확인: `tests/preview/test_presentation.py`, `test_data.py` 30건 통과(공유 파일을
  수정하지 않았으므로 회귀 없음 확인용).
- 실행하지 않은 것: 전체 296/155/95 스위트, 프론트엔드 type/build/browser, 유료 API/모델
  호출. 공유 UI 코드를 아직 바꾸지 않아 필요 없다.

## 10. 실제로 없는 자료 (따로 보고)

- **한국어 값이 없는 선수 592명**(player_translation 12353 중 11761만 값 있음). 이 선수들이
  주목 선수로 뽑히면 영어 표기가 그대로 나가고 `db_korean_missing` 사유가 관리자 진단에
  남는다. 번역을 지어내지 않는다. 해결은 번역 데이터 보강이며 이 작업 범위가 아니다.
- 별칭(alternate name) 표가 없다. 그래서 `Rodri` 같은 통칭·애칭은 DB `name`/`firstname`/
  `lastname`으로 확정되지 않으면 미해결로 남는다(임의 매핑 금지).
- 선수 `short_name_ko`는 본문 치환에 쓰지 않는다(§6-6). 필요하면 별도 승인 범위에서
  "짧은 한국어 이름을 어디까지 한 사람 이름으로 볼지" 규칙을 먼저 정해야 한다.

## 11. 남은 일 / 인계

1. **공유 렌더러 연결**(§7): MP10 또는 root가 소유. 이 워커는 편집하지 않았다.
2. `PREVIEW_NAMES_DATABASE_URL` 키를 `Settings`에 추가하고 실행 스크립트 env 파일에 그대로
   두면 된다(이미 0600 파일에 있음).
3. 연결 후 실제 화면 확인(경기 목록·제목·주목 선수·본문)은 별도 검증 단계다. 연결 전에는
   **UI 한국어 표시가 완료됐다고 말할 수 없다.**
4. 이 역할/DSN은 이름 표시 전용이다. 다른 기능이 같은 권한을 필요로 하면 그때 별도로
   판단한다(기존 역할 확대로 처리하지 않는다).

## 11-1. R4(주목선수 모듈) 연결 확인

`app/preview/modules/players.py`(R4, `task_397ce4b7a79a`)가 이 해석기를 duck-typed로
호출한다. 실제 호출 형태를 코드에서 확인하고 동작을 검사했다.

- R4 호출: `resolver.resolve_player(name, team_hint=, scope_team_ids=, player_id=, id_space=)`
  → 시그니처 호환 확인.
- R4는 모델 응답의 `player_ref`를 그대로 `player_id`로 넘긴다. 그 값은 **검증되지 않은
  참조**다. 그래서 R4가 `id_is_hint=True`를 넘기도록 연결해야 한다. 넘기지 않으면 모델이
  숫자를 잘못 적었을 때 확실한 한국어 이름이 `not_found`로 막힌다(둘 다 검사로 고정했다).
- `player_ref`가 없는 경우(`None`)는 이름 매칭으로 정상 해석된다.
- R4가 `rewrite_body`로 이유 문장을 정리하는 경로도 같은 표기 규칙을 쓴다.
- 로스터를 넣지 않고 인덱스를 만들면 이름 매칭이 불가능하다. R4는 로스터를 받으므로
  `load_name_index(..., include_rosters=True)`(기본값)로 인덱스를 만들어야 한다.

## 12. 파일

| 경로 | 상태 |
|---|---|
| `app/preview/localized_names.py` | 신규(해석기) |
| `tests/preview/test_localized_names.py` | 신규(집중 검사 21건) |
| `scripts/preview_dev_names_ro_provision.py` | 신규(1회성 역할 준비) |
| `docs/implementation/match-preview/korean-names-report.md` | 이 보고서 |
| `docs/implementation/match-preview/evidence/korean-names/01-focused-tests.txt` | 검사 출력 |
| `docs/implementation/match-preview/evidence/korean-names/02-real-db-check.json` | 실제 DB 확인 결과 |

공유 파일 수정 0건. 스테이징/커밋 0건. 과거 DB 행 수정 0건. 실제 모델/API 호출 0건.
