# 실제 홈 사진 누락 수정 (HP-PHOTO)

작성: DeepSeek 구현 워커, 2026-11-13. 모델 `deepseek-ai/deepseek-v4.1-flash-1017`, 추론 강도 max.

## 원인

`app/services/home_preview_document.py`의 `_id_context`가 `StructuredIdContext`에
**표시 이름 파사드(`DisplayNameBridge`)를 그대로** 넘기고 있었다. 파사드는 dataclass이고
해석기는 그 안의 `bridge.names`에 들어 있다.

`StructuredIdContext`는 `resolve_player`/`resolve_team`을 가진 **해석기**를 요구한다.
파사드를 넘기면 `getattr(self._names, "resolve_player", None)`이 `None`이 되어
모든 확인이 조용히 실패하고 `None`을 돌려준다. 예외가 나지 않아 오류로 드러나지도 않는다.

결과는 공개 응답에서 다음과 같이 나타났다. 관리자 원본 실행 `d96fe824`의 section-results
GET에는 선수 4명·부상 2명의 `photo_url`/`external_player_id`/`team_external_id`가 모두
있었지만, 홈 document에서는 같은 값이 전부 `null`이었다. 사진 주소는 확인된 외부 ID에서만
만들어지므로(`player_photo_url`), 화면은 선수 4명·부상 2명 모두 '사진 없음'을 보여줬다.

관리자 경로(`preview_admin.get_section_results`)는 같은 클래스에 `bridge.names`를 넘긴다.
그래서 관리자에서는 사진이 보이고 홈에서만 사라지는 비대칭이 생겼다.

## 변경

한 줄이다. `app/services/home_preview_document.py`의 `_id_context`.

```diff
-        return StructuredIdContext(bridge, scope_team_ids=scope), bridge
+        return StructuredIdContext(bridge.names, scope_team_ids=scope), bridge
```

이유를 코드에 남겼다. 파사드를 넘기면 해석기 메서드가 없어 모든 확인이 조용히 `None`이
되고 사진·팀 외부 ID가 사라진다는 사실이다.

바꾸지 않은 것: 팀 범위(`scope`)는 그대로 실행의 두 팀 내부 ID이고, 선택된 구성본이 다른
실행의 섹션을 고를 때도 그 실행의 payload ID를 같은 범위에서 확인한다. 요청 종료 시
`bridge.close()`로 읽기 전용 연결을 닫는 경로도 그대로다. 추정 ID·하드코딩은 넣지 않았다.
HP-EVIDENCE 변경(승인 근거 경로)도 보존했다.

## 수정하지 않은 것

승인·저장행·원문·모델·프론트·공용 렌더·`Plans.md`. 표시 이름 파사드와
`StructuredIdContext` 자체도 읽기만 했다. 내부 ID를 공개하지 않는 화이트리스트
(`_public_row`)는 그대로다.

## 검사

`.venv/bin/python -m pytest tests/unit/test_home_preview_document.py -q`

- 수정 전: **15 passed**
- 수정 후: **16 passed**

새 대표 검사 1건 `test_photo_and_logo_ids_survive_when_the_resolver_is_connected`.
검사 이유는 "홈에서 선수·부상 사진이 모두 빠지고 팀 로고가 일부만 남는 실제 화면"이다.
저장 payload에 내부 선수 ID 533·팀 ID 13이 있는 선수 1명과 이름만 있는 부상 1명을 넣고,
해석기를 연결했을 때 `external_player_id=1100`·사진 주소·`team_external_id=50`이 공개
투영까지 남는지, 내부 `player_id`/`team_id`는 여전히 빠지는지, 이름-only 부상의 확인이
이 경기 두 팀 `(13, 36)` 범위로 제한되는지를 한 시나리오에서 확인한다.

검사가 실제 결함을 잡는지도 확인했다. 연결을 `bridge`로 되돌리면 이 검사가
`assert None == 1100`으로 실패한다. 즉 외부 ID가 `None`이 되어 사진 주소가 만들어지지
않는데, 그것이 root가 관측한 '사진 없음'과 같은 증상이다. 되돌린 뒤 16 passed로 복귀한다.

실제 API·DB·서버·브라우저·외부 조회·전체 회귀는 실행하지 않았다.

## 스킬·원칙이 바꾼 결정

`poteto-mode/SKILL.md` 전문은 이 세션에서 읽었고 해시 `70faeea6...b936`(24986 bytes)로
미변경을 확인해 재사용했다.

- **Fix Root Causes.** 화면에서 사진을 채우는 대신, 사진 주소를 만드는 유일한 입력인
  외부 ID가 왜 비는지까지 내려가 연결 한 곳을 고쳤다. 이 결정 때문에 수정이 한 줄로 끝났고
  폴백 이미지나 추정 ID를 넣지 않았다.
- **Prove It Works.** 수정 후 통과만 보이지 않고 연결을 되돌려 `None == 1100` 실패를
  재현했다. 이 결정 때문에 새 검사가 빈 검사가 아님을 보고서에 근거로 남겼다.
- **Boundary Discipline.** 확인 경계(`StructuredIdContext`)는 그대로 두고, 호출자가 넘기는
  의존성만 계약에 맞췄다. 경계 안에 폴백 로직을 더하지 않았다.

## 변경 파일

- `app/services/home_preview_document.py`
- `tests/unit/test_home_preview_document.py`
- `docs/implementation/match-preview/home-photo-connection-report.md` (이 문서)

## 남은 항목

- 실제 공개 GET에서 사진 6개(선수 4 + 부상 2)와 팀 외부 ID가 채워지는지, 브라우저에서
  이미지가 실제로 그려지는지 확인은 root 담당이다. 이 수정은 확인 경계의 연결만 바로잡았고
  공개 GET을 직접 호출해 검증하지 않았다.
- 저장본문 내 팀 로고가 2개뿐이던 원인이 이 연결과 같은 원인인지는 이번 검사로 확인하지
  않았다. 로고는 확인된 `team_external_id`가 있을 때만 그려지므로 같은 수정으로 함께
  개선될 것으로 **추정**하지만, 실제 개수를 측정하지 않았다. root의 실화면 확인에서
  판정해야 한다.

`EDITING STOPPED`. 백그라운드 작업 0건.
