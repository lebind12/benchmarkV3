# PD-B — 주목 선수 팀 로고 ID 연결

작성: 2026-11-12 KST. 담당: DeepSeek 구현 워커(Orca `dsh-tui`, 실제 모델
`deepseek-ai/deepseek-v4.1-flash-1017`, 추론 강도 Max 유지).
근거: `docs/implementation/match-preview/pd-design-report.md` §3-2(PD-F가 남긴 데이터 계약 누락).

## 1. 무엇이 빠져 있었나

사용자 디자인 요구 2번은 **주목 선수 카드에도 실제 팀 로고**다. 부상 카드는 `team_external_id`가
구조 값에 있어 ID로 좌우·로고가 확정되지만, 주목 선수 행에는 그 키가 **없었다**.

```
_players(...)   → "team_id"/"team_external_id" 키 없음   ← 이번에 고침
_injuries(...)  → "team_id"/"team_external_id" 키 있음
```

그래서 주목 선수는 팀 **이름 비교**(경기 라벨·`korean_labels` 별칭표)로만 좌우를 정했고,
별칭표가 없는 저장 run에서는 좌우가 `null`이 되어 로고가 그려지지 않았다(PD-F §3-2 실측).

## 2. 수정 (한 파일, 한 함수)

`app/preview/section_structured.py` `_players(...)`가 `_injuries(...)`와 **같은 계약**으로
검증된 nullable 팀 ID를 내려준다.

| 추가 키 | 값 | 확인 방법 |
|---|---|---|
| `team_id` | 내부 팀 ID 또는 `null` | ① 저장 payload의 `team_id`(내부 ID 그대로 보존) ② 없으면 저장된 팀 이름 → 기존 DB 해석기(`team_by_name`, **이 경기 두 팀 범위**) |
| `team_external_id` | 외부(API-Football) 팀 ID 또는 `null` | 위에서 확인된 `team_id`를 `id_context.team_external_id()`로 변환 |

지킨 제약:

- **내부/외부 ID를 섞지 않는다.** 저장된 `team_id`는 내부 키로만 쓰고, 외부 ID는 DB 해석기가
  확인해 준 값만 쓴다. 실측: 저장 payload에 외부값 50을 `team_id`로 잘못 담은 경우 내부 50은
  이 경기 팀이 아니므로 `team_external_id=null`이다(외부값을 내부로 승격하지 않는다).
- **배열 순서 추측 금지.** 순서는 쓰지 않는다(기존 `resolveSides` 규칙 유지).
- **모델 추측 금지.** 이름→ID 변환은 기존 DB 이름 해석기만 쓴다(같은 범위에서 유일 확인).
- 확인 실패는 `null`이다(값을 만들지 않는다).
- 기존 키(`player`/`reason`/`team`/`player_id`/`external_player_id`/`photo_url`)는 그대로.
- 저장 payload·기존 ID 해석기 로직·프런트 계약 **변경 없음**.

## 3. 실측 근거 (읽기 전용, 같은 두 run 한정)

`run_section_regeneration`으로 만든 `493ef4a9`의 players 결과는 **원 run `d96fe824` 저장 행**을 읽는다.
그 저장 payload에는 팀 표시 이름(한국어)만 있고 `team_id`가 없다.

| run | 저장된 주목 선수 | 저장 `team_id` | 투영 후 `team_id` / `team_external_id` |
|---|---|---|---|
| `d96fe824` | 엘링 홀란드(533) | 없음 | **13 / 50** (맨체스터 시티) |
| `d96fe824` | 필 포든(531) | 없음 | **13 / 50** |
| `d96fe824` | 로드리고 무니즈(138) | 없음 | **4 / 36** (풀럼) |
| `d96fe824` | 에밀 스미스 로우(122) | 없음 | **4 / 36** |

reader fixture의 내부/외부 팀 ID와 일치한다(`home 13/50`, `away 4/36`).
`493ef4a9` 자체는 배당만 다시 만든 실행이라 `section_players` 행이 없고, 화면은 구성본으로
원 run의 players 행을 읽는다(그 경로도 같은 함수·같은 해석기다).

**확인 실패 대표**: 팀 이름이 DB 범위에 없거나 팀 표기가 아예 없으면 `team_id`/`team_external_id`
모두 `null`이다(실측).

## 4. 프런트 계약 — 추가 요청 없음

프런트는 **이미** 이 키를 읽도록 되어 있었다.

- `sectionStructured.ts` 83행: `team_external_id` → `teamExternalId` 파싱(선수·부상 공통).
- `previewView.ts` 712~718행: 주목 선수 매핑에 `team_external_id: row.teamExternalId ?? null`
  (부상 매핑은 581행에 같은 줄이 있다).
- `teamGroups`(375행)는 `team_external_id`로 좌우를 확정하고, 없으면 이름 비교로 폴백한다.

즉 backend가 값을 내려주면 프런트 수정 **없이** 로고가 그려진다. 이번에 frontend는 손대지 않았다.

주의: 검토 중 frontend 파일이 **다른 작업자에 의해** 갱신되어(같은 세션의 동시 수정) 위 줄 번호는
22:5x 시점 기준이다. 계약(`team_external_id` → `teamExternalId` → `team_external_id`)과 주목 선수
매핑의 존재는 그 시점에도 동일했다. 이 워커가 편집한 frontend 파일은 **없다**.

## 5. 승인·재생성 영향 없음

이번 변경은 **표시용 구조 값의 부가 필드**다. 모델 프롬프트·본문·판정 로직·공급 경로가 그대로이므로
`IMPLEMENTATION_VERSION`·`PROVIDER_ODDS_IMPLEMENTATION_VERSION`·워크플로우 승인 버전을
올리지 않았다(과거 승인·저장 run·원문 보존).

## 6. 검사 명령과 결과

DB는 기존 가드(루프백 + `*_test` 이름)를 통과한 로컬만 사용. 실제 모델·HTTP 호출 0.

```
# 신규 대표 검사 2건(연결됨 / 확인실패 null)
./.venv/bin/python -m pytest tests/preview/test_bundle_review_fixes.py \
  -k "player_team_external_id or unverified_player_team" -q
  2 passed, 32 deselected

# 기존 직접 관련(주목 선수·부상 투영) 회귀
./.venv/bin/python -m pytest tests/preview/test_bundle_review_fixes.py -k "player or injury" -q
  11 passed, 23 deselected
```

**회귀 감지력**: 새 `team_id`/`team_external_id` 키를 코드에서 제거하면 신규 검사 2건이 **실패**하고,
복원하면 다시 통과한다(2 passed). 즉 이 검사는 이번 누락을 직접 잡는다.

추가한 검사:

| 검사 | 확인 | 실패하면 사용자에게 생기는 일 |
|---|---|---|
| `test_player_team_external_id_comes_from_verified_db_team` | 팀 이름만 있는 저장 행 → `13/50`, `4/36` | 주목 선수 카드에 팀 로고가 안 나온다 |
| `test_unverified_player_team_leaves_team_ids_null` | 미확인 팀·팀 표기 없음 → `null` | 다른 팀 로고가 붙어 잘못된 정보가 나간다 |

## 7. 한계 / 남은 일

1. **재기동 필요**: 현재 8000 프로세스는 수정 전 코드다. root 재기동 후 화면에 반영된다.
2. **저장 payload에는 team_id가 여전히 없다**: 화면 값은 읽기 투영에서 채운다(저장 원문 무변경).
   저장 payload에 넣으려면 재생성이 필요하며 이번 범위 밖이다.
3. `_players`의 `team_id`는 저장값을 **그대로 보존**한다. 저장 payload가 잘못된 ID 공간을 담고 있으면
   `team_external_id`가 `null`이 될 뿐, 값을 고쳐 쓰지 않는다(원문 보존).
4. 실제 브라우저 화면 확인은 root 담당이다(이번 검토는 jsdom·구조 값까지).

EDITING STOPPED
