# 사진 연결 수정 독립 검토 (HP-PHOTO)

작성: DeepSeek 검토 워커(읽기 전용), 2026-11-13 02:56 KST. 모델 `deepseek-ai/deepseek-v4.1-flash-1017`, 추론 강도 max.
입력: `home-photo-connection-brief.md`, `home-photo-connection-report.md`, `app/services/home_preview_document.py`의 `_id_context`, `tests/unit/test_home_preview_document.py`의 새 검사.
스킬: `.agents/skills/poteto-mode/SKILL.md` 전문은 이 세션에서 읽었고 해시 `70faeea6...b936`로 미변경을 확인해 재사용했다. 원칙 `principle-prove-it-works`·`principle-test-behavior-not-implementation`을 적용했다.

## 판정

**수용.** 의존성 연결이 `StructuredIdContext`의 계약대로 해석기를 받고, 팀 범위·요청 종료 정리·내부 ID 비공개·HP-EVIDENCE 승인 경로가 모두 보존된다. 새 검사는 관측된 실제 결함(사진 전부 없음)을 잡는 형태다. 구현자의 `16 passed`와 "잘못 연결하면 `None == 1100`으로 실패" 근거도 코드 대조와 일치한다.

## 확인한 것

**1. 계약 일치.** `StructuredIdContext.__init__(self, names, *, scope_team_ids=())`는 첫 인자를 `self._names`로 받고, docstring이 "이미 열린 이름 해석기(`DisplayNameBridge.names`)"를 요구한다고 명시한다. `_resolve_player`/`_resolve_team`(`section_structured.py:257-280`)은 `getattr(self._names, "resolve_player"/"resolve_team", None)`이 callable일 때만 진행하고 아니면 `None`을 돌려준다. 현재 `_id_context`는 `StructuredIdContext(bridge.names, scope_team_ids=scope)`로 해석기를 넘긴다(`:606`).

**2. 실패 모드가 관측과 일치.** 파사드(`DisplayNameBridge`)는 `app/preview/display_names.py`에 `resolve_player`·`resolve_team`을 정의하지 않는다(전수 grep 결과 없음). 그래서 파사드를 넘기면 두 `getattr`이 `None`이 되어 모든 확인이 조용히 `None`이 되고, `player_photo_url(None)`이 사진을 만들지 않는다. 예외가 없어 오류로 드러나지도 않는다. 이것이 관리자 원본에 있던 6개 사진이 홈에서 전부 `null`이 된 경로다.

**3. 관리자 경로와 같아졌다.** `preview_admin.get_section_results`는 `resolver = getattr(names, "names", None)`(`:1154`)을 만들어 `StructuredIdContext(resolver, scope_team_ids=...)`로 넘긴다(`:1162`). 즉 두 경로가 같은 해석기를 넘기게 됐다. 관리자에서만 사진이 보이던 비대칭의 원인과 수정이 서로 맞는다.

**4. 팀 범위 보존.** `scope`는 여전히 실행의 `home_team_id`·`away_team_id`를 int로 모은 튜플이고(`:596-600`), 그대로 `scope_team_ids`로 전달된다. 이름-only 부상은 이 범위가 비면 확인하지 않는다(`player_by_name`이 `self._scope`를 요구). 구성본이 타 실행 섹션을 고르는 경우에도 그 실행의 payload ID를 같은 범위에서 확인하므로 확대되지 않는다.

**5. 요청 종료 정리 보존.** `read_document`의 `finally`에서 `bridge.close()`를 호출하는 경로(`:669-671`)가 그대로다. `_id_context`는 여전히 `(id_context, bridge)` 쌍을 돌려주고 실패 시 `None`으로 흡수한다.

**6. 내부 ID 비공개 보존.** `_public_row`의 화이트리스트(`:309`, `:318`)는 `external_player_id`·`team_external_id`·`photo_url`만 남기고 `player_id`·`team_id`는 넣지 않는다. 이번 변경은 이 함수를 건드리지 않았다.

**7. 승인 경로 보존.** HP-EVIDENCE의 `approved_evidence`·`_displayable`·`_chosen_rows`·`select_document`·`_read_approvals`는 이번 창에서 변경되지 않았다. 변경은 `_id_context` 한 줄과 그 위 주석뿐이다.

**8. 새 검사가 결함을 잡는 형태다.** `test_photo_and_logo_ids_survive_when_the_resolver_is_connected`(`:505-598`)는 실제 `_id_context`를 호출하고 `open_display_names`만 대역으로 바꾼다(DB·설정을 열지 않는다). 대역 `_Bridge`는 `names` 속성에 해석기를 담고 실제 파사드 구조를 따른다(`:493-502`). 검사는 다음을 단언한다. `external_player_id == 1100`, `photo_url == .../1100.png`, `team_external_id == 50`, `player_id`/`team_id` 키 부재, 이름-only 부상도 같은 값, 그리고 이름 확인이 모두 `(13, 36)` 범위였다는 점.

**9. 잘못 연결하면 실제로 실패한다.** `_Bridge`에는 `resolve_player`/`resolve_team`이 없으므로 `StructuredIdContext(bridge, ...)`로 되돌리면 `_resolve_player`가 callable 검사에서 `None`을 돌려주고 `external_player_id`가 `None`이 되어 `assert player["external_player_id"] == 1100`이 실패한다. 구현자가 보고한 `assert None == 1100` 실패와 같은 지점이다. 검사가 구현을 그대로 반복하는 빈 검사가 아니며, 사용자가 보는 결과(사진 없음)를 기준으로 판정한다.

**10. 검사 파일 안전성.** 이 파일은 `create_engine`·`SessionLocal`·`connect(`·`requests`·`httpx`·`DATABASE_URL`을 쓰지 않고 `pytest.mark.unit`만 표시한다. 새 검사도 `monkeypatch`로 팩토리만 대체한다.

## 명령 실행 여부

**실행하지 않았다.** 지시대로 코드 읽기와 보고 근거 대조로 판정했다. 구현 보고의 수정 전 15 → 수정 후 16 passed와 연결 되돌림 실패 재현은 위 코드 근거와 모순되지 않는다. 검사 수는 저장소에서 `def test_` 16건으로 확인했다.

## 참고 (차단 아님)

- 새 검사는 `_id_context` → `structured_row_from_section_result` → `_public_row` 경로를 직접 호출하고 `read_document` 전체를 지나지는 않는다. `read_document`가 이 컨텍스트를 실제로 쓰는 배선은 변경되지 않았고 앞선 실제 GET 확인(root)이 그 경로를 함께 검증한다.
- 팀 로고는 이 검사에서 `team_external_id`로 확인되지만 브라우저 렌더링 자체는 root의 실제 확인 몫이다.

## 범위 준수

제품·검사 파일은 읽기 전용으로만 봤고 이번 검토에서 편집하지 않았다. API·DB·브라우저·서버·메일 탐색·하위 워커를 쓰지 않았고 백그라운드 작업도 시작하지 않았다. 보고서는 이 파일 하나만 작성했다.
