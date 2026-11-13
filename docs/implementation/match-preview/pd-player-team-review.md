# PD-R-B — 주목 선수 팀 로고 ID 연결 독립 검토

작성: 2026-11-12 KST. 역할: 읽기 전용 독립 검토(DeepSeek `deepseek-ai/deepseek-v4.1-flash-1017`, Max 유지).
대조 범위: `docs/implementation/match-preview/pd-player-team-report.md`,
`app/preview/section_structured.py`의 `_players` 팀 ID 추가분,
`tests/preview/test_bundle_review_fixes.py`의 신규 2검사.
새 검사·재현 도구 작성, 명령 실행, DB·HTTP·브라우저·모델 호출은 **0회**다(정적 확인만).
프런트·배당·기존 참고 항목은 지시대로 제외했다. 제품 파일은 편집하지 않았다.

## 1. 판정

**통과. 차단 0건.** 수용 기준 5개를 모두 코드 경로로 확인했고, 보고서의 실측·검사 수치도
정적 계산과 어긋나지 않는다. 참고 5건(§3)은 버전 축·표시 일관성·검사 범위·재기동 안내이며
현재 화면 결과를 틀리게 만들지 않는다.

| 수용 기준 | 판정 | 근거 |
|---|---|---|
| 이 경기 두 팀 범위의 기존 DB resolver로 확인한 내부 `team_id`와 외부 `team_external_id`만 추가 | 충족 | `section_structured.py:309-338`, `team_by_name`(`:235-255`) |
| 내부/외부 공간 혼동 없음 | 충족 | `_int_id`(`:283-287`)로 정수만, 외부 변환은 `_resolve_team`(`:271-280`)의 `id_space="internal"` 한 경로 |
| 확인 실패 시 `null` | 충족 | 두 키 모두 `None` 기본값, 추측·순서 사용 없음(`:313-338`) |
| 기존 `player`/`photo_url`/본문/저장 payload 보존 | 충족 | `:323-341`에 기존 키 그대로 + 신규 2키만 추가, 저장 경로 무변경 |
| GET 외부 HTTP·모델·쓰기 0 | 충족 | 모듈에 session·http·httpx·urlopen import 없음(URL은 템플릿 상수뿐) |

## 2. 근거

**두 팀 범위 고정.** 이름→ID 확인은 `StructuredIdContext.team_by_name`이 이미 열린 해석기
(`DisplayNames`)에만 묻는다. 해석기의 색인은 `open_display_names`가 `team_ids=[home, away]`로
읽은 두 팀만 담으므로(`display_names.py:194-200`), 다른 팀 이름은 `team_by_name`이 후보 0건으로
`None`을 돌려준다(`localized_names.py:649-660`). 즉 경기 밖 팀이 붙을 경로가 없다.
`_resolve_team`도 `_teams_by_id`(색인에 있는 두 팀)만 보므로 내부→외부 변환이 범위를 벗어나지 않는다.

**공간 혼동 차단.** 저장 payload의 `team_id`는 `_int_id`로 정수만 받아 **내부 키로 그대로** 쓰고,
외부 값은 `team_external_id(team_id)`가 DB 색인에서 확인한 경우에만 채운다(`:334-338`).
색인에 없는 내부 ID(예: 외부값 50을 잘못 담은 행)는 `_resolve_team`이 `None` → `team_external_id=null`.
보고서 §2의 실측 서술과 코드가 일치한다. `bool`은 `_int_id`가 배제한다.

**확인 실패 null.** `team_id`가 없고 `team_name`도 없으면 두 키 모두 `None`이다.
`team_name`이 있어도 해석 실패면 `None`이다(추측·배열 순서·이름 유사도 사용 없음).
신규 검사 `test_unverified_player_team_leaves_team_ids_null`이 이 두 경우를 고정한다(`:1325-1351`).

**기존 키 보존.** 반환 dict는 `player`, `reason`, `team`, `player_id`, `external_player_id`,
`photo_url`을 그대로 두고 `team_id`·`team_external_id`만 더한다. 본문(`body`)과 저장 payload는
`_players`가 만들지 않으므로 변경 여지가 없다. `structured_from_payload`의
`available` 판정 키 목록(`players`/`injuries`/`media`/`odds`/`forecast`)도 그대로다.

**GET 무부작용.** 이번 변경 구간(`:309-338`)은 순수 함수 내부다. 이 모듈의 import는
`__future__`와 `typing`뿐이고 `session`·`http`·`httpx`·`requests`·`socket` 참조가 없다(전수 grep).
`preview_admin.py`(19:46)·`section_preview.py`(05:28)의 mtime이 PD-B 변경 시각(22:54)과 달라
조회 경로 코드도 이번에 바뀌지 않았다. PD-B 창(22:40~23:05)에서 수정된 파일은
`section_structured.py`·`test_bundle_review_fixes.py` **둘뿐**이다(신규 파일 없음).

**보고서 수치 정합(정적 계산).** `test_bundle_review_fixes.py`는 총 34검사이고
`player|injury`에 걸리는 이름이 11건, 신규 2검사 이름이 2건이다. 보고서의
`2 passed / 32 deselected`, `11 passed / 23 deselected`는 34건과 각각 합이 맞는다.
새 검사 2건은 모두 `StructuredIdContext(_names_resolver(), scope_team_ids=(13, 4))`로
fixture의 두 팀(13/50, 4/36)을 쓰므로 실측 표(13/50·4/36)와 같은 값을 고정한다.
보고서가 재사용을 지시한 `d96fe824` 실측과 기존 `2/11 passed`는 이 검토에서 재실행하지 않았다.

## 3. 미해결 / 참고 (차단 아님)

1. **`STRUCTURED_VERSION` 미상향 — 자체 선례와 불일치.** 이 모듈은 버전 2에서
   "선수·부상 행에 외부 ID와 사진 URL(nullable)을 덧붙였다"는 이유로 버전을 올렸다
   (`section_structured.py:42-44`). 이번 변경은 **같은 행에 같은 성격의 nullable 키 2개**를
   더하는데도 `mp11-structured-2`를 유지한다. 소비자는 `structured_version`으로 분기하지 않고
   (`frontend/src/features/match-preview/types.ts:433`은 선택 문자열 필드뿐), 프런트도
   optional로 읽으므로 **기능 영향은 없다**. 다만 축의 의미를 지키려면 상향 여부를 정하는 편이 낫다.
   승인 버전(워크플로우)은 표시용 부가 필드라 올리지 않은 판단(보고서 §5)에 동의한다.
2. **`team` 표시 이름 로컬라이즈 비대칭.** `_players`는 **`team_id`가 없을 때만** 저장된 팀 이름을
   DB 한국어 값으로 바꾼다(`:315-322`). `team_id`가 있는 행은 `team` 문자열을 그대로 둔다
   (`_injuries`는 `team_id` 유무와 무관하게 팀 이름을 해석한다, `:384-388`). 표시 전용 차이라
   데이터가 틀리지는 않지만, 같은 경기의 선수·부상 카드가 다른 팀 표기를 쓸 수 있다.
3. **저장 payload의 ID 공간 오류는 여전히 값이 이긴다.** 저장 `team_id`가 실제로는 외부 ID이고
   그 숫자가 이 경기 팀의 **내부** ID와 우연히 같으면, 확인된 것으로 취급되어 다른 팀 로고가
   붙을 수 있다. 이번 변경이 만든 위험이 아니라 저장 payload 품질 문제이며, 보고서 §7-3도
   "저장값을 그대로 보존한다"고 밝히고 있다. 현재 `d96fe824` 저장 행에는 `team_id`가 아예 없다.
4. **검사 범위.** 신규 2검사는 `team_id`/`team_external_id`만 단언하고 기존 키 보존
   (`photo_url` 등)은 단언하지 않는다. 이 검토가 코드로 보존을 확인했으므로 차단 사유는 아니나,
   회귀 고정이 필요하면 구현자 후속으로 한 줄 추가할 수 있다.
5. **재기동 필요(보고서 §7-1).** 현재 8000 프로세스는 수정 전 코드이므로 화면 반영은 root 몫이다.
   이 검토는 화면을 보지 않았다.

EDITING STOPPED
