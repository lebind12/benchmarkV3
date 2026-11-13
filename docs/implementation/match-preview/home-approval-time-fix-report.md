# 승인 API 기본 시각 오류 수정 (HP-APPROVAL)

작성: DeepSeek 구현 워커, 2026-11-13. 모델 `deepseek-ai/deepseek-v4.1-flash-1017`, 추론 강도 max 유지.

## 원인

`app/preview/approvals.py:459`의 `moment = now or datetime.now(timezone.utc)`가 쓰는
`timezone`이 이 파일에 import되어 있지 않았다. 파일 상단은 `from datetime import datetime`
한 줄뿐이었고, 같은 이름은 이 파일에서 이 한 곳에서만 쓰인다.

그래서 관리자 API가 승인 요청에 `now`를 넘기지 않는 **기본 경로**에서
`NameError: name 'timezone' is not defined`로 실패했다. root가 실제 첫 AI전망 승인 POST에서
관측한 500이 이것이며, 승인 행이 만들어지지 않아 홈에 표시할 문서가 생기지 않는 상태였다.

기존 F2/F3 승인 검사들이 이 결함을 잡지 못한 이유는 모두 `now=FIXED_NOW`를 넘겨
기본 시각 계산 줄을 지나가지 않았기 때문이다.

## 수정

`app/preview/approvals.py` 한 줄.

```diff
-from datetime import datetime
+from datetime import datetime, timezone
```

승인 버전·본문·권한·현재와 저장 버전 판단은 바꾸지 않았다. 다른 파일·설정·Plans.md 무변경.

## 검사

`.venv/bin/python -m pytest tests/unit/test_section_approval_timestamp.py -q` → **1 passed**

새 검사 `tests/unit/test_section_approval_timestamp.py` 대표 사례 1건은 `now`를 **생략한**
승인 호출이 실패하지 않고, 시간대를 가진 UTC 승인시각을 남기며, 승인 근거 섹션 ID·실행 ID와
구성 버전이 유지되고 승인 행이 활성으로 남는지 확인한다. 실제 DB에 연결하지 않고 승인 경로가
쓰는 조회·쓰기만 흉내 내는 합성 session을 쓴다. import 문만 확인하는 구현 복제 검사는 쓰지 않았다.

수정 전 실패도 같은 사례로 확인했다. import를 원래대로 되돌리면 이 검사가
`NameError: name 'timezone' is not defined` (approvals.py:459)로 실패하고, 되돌리면 통과한다.
즉 검사가 실제 결함을 잡는다.

## 스킬이 선택을 바꾼 점

poteto-mode `SKILL.md` 전문은 이 세션에서 읽었고 파일 해시 `70faeea6...b936`(24986 bytes, 11-09 17:53)로
미변경을 확인해 재사용했다. 적용한 원칙은 **Prove It Works**와 **Test Behavior, Not Implementation**이다.

- **Prove It Works.** 수정 후 통과만 보이지 않고 import를 되돌려 실패를 재현했다. 이 결정 때문에
  검사가 "통과하는 빈 검사"인지 아닌지를 보고서에 근거로 남겼다.
- **Test Behavior, Not Implementation.** 검사를 소스에 `timezone` 문자열이 있는지 확인하는
  방식 대신, `now`를 생략한 승인 호출이 실제로 UTC 시각과 근거 버전을 남기는지를 본다.

## 남은 항목

- 실제 승인 POST와 화면 확인은 root 담당이다. 이 수정은 그 요청이 500으로 끝나지 않게 하는
  최소 원인 수정이며, 승인 후 문서 표시까지 확인한 것은 아니다.
- 승인 기록은 이 작업 시점에 여전히 비어 있다(`approved=[]`). 이 수정은 그 상태를 만들거나
  바꾸지 않는다.

`EDITING STOPPED`. 백그라운드 작업 0건.
