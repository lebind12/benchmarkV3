# 승인 기본 시각 수정 독립 확인 (HP-APPROVAL)

작성: DeepSeek 검토 워커(읽기 전용), 2026-11-13 02:35 KST. 모델 `deepseek-ai/deepseek-v4.1-flash-1017`.
입력: `home-approval-time-fix-report.md`, `app/preview/approvals.py` diff, `tests/unit/test_section_approval_timestamp.py`.
적용 스킬: `.agents/skills/poteto-mode/SKILL.md` 전문은 앞선 seq26/27에서 읽었고 해시 `70faeea6...b936`로 미변경을 확인해 재사용했다. 원칙 `principle-prove-it-works`·`principle-test-behavior-not-implementation`를 이 확인에 적용했다.

## 판정

**수용.** 직접 요구 위반은 없다. 한 줄 수정이 실제 원인을 고쳤고, 대표 검사가 그 기본 경로를 실제로 호출하며, 승인 버전·권한·본문 정책은 바뀌지 않았다. 보고된 `1 passed` 근거를 재사용했고 테스트를 다시 실행하지 않았다.

## 확인 결과

**1. 원인과 수정 범위.** `app/preview/approvals.py`의 diff는 `1 insertion / 1 deletion`, `from datetime import datetime` → `from datetime import datetime, timezone` 한 줄뿐이다. 이 파일에서 `timezone`은 29줄(import)과 459줄(`moment = now or datetime.now(timezone.utc)`) 두 곳에만 나오고, 같은 파일의 다른 `datetime.now` 호출은 없다. 따라서 import 추가가 다른 계산에 영향을 주지 않는다. 그 파일의 mtime은 02:31이고 이번 수정 창(02:25 이후)에서 제품 코드로 바뀐 파일은 이 하나다.

**2. 기본 경로가 실제로 고쳐졌다.** 관리자 API 호출부(`app/api/v1/preview_admin.py:440-446`)는 `approve_section_version`에 `now`를 넘기지 않는다. 그래서 459줄이 유일한 시각 계산이고, import가 없던 동안 이 경로가 `NameError`로 실패했다. 수정 후 같은 줄이 `datetime.now(timezone.utc)`로 실행되어 시간대 있는 UTC 값을 만든다. API 파일과 승인 저장소는 이번 창에서 변경되지 않았다(`preview_admin.py` mtime 11-12 19:46).

**3. 검사가 그 경로를 호출한다.** `tests/unit/test_section_approval_timestamp.py:101`은 `now`를 **생략한** 호출이다. 합성 session으로 `_require_section_evidence`의 조건(실행 존재·비취소·섹션 행 일치·워크플로우 일치·본문 있음·`mode` live 일치)을 모두 통과시킨 뒤 `_reviewed_constituents`를 지나 459줄에 도달한다. 검사는 소스 문자열 존재가 아니라 승인 결과를 본다. `approved_at`이 `datetime`이고 `tzinfo`가 있으며 `utcoffset` 0, `before <= approved_at <= after`, 근거 실행·섹션 ID 일치, `workflow_version`이 워크플로우 ID로 시작, 승인자 ID, 구성 버전 비어 있지 않음, 승인 행 1건·`active=True`를 단언한다. 검사 파일은 DB·네트워크를 호출하지 않는다(`create_engine`·`SessionLocal`·`connect(`·`requests`·`httpx` 없음).

**4. 정책 미변경.** 승인 버전 계산(`_reviewed_constituents`·`release_version`), 근거 검증(`_require_section_evidence`), 모의 실행 거부, append-only 승계(`active` 내림·`supersedes_approval_id`), 감사 행 기록이 모두 수정 전과 같다. diff가 import 한 줄이므로 이 경로들은 문자 그대로 바뀌지 않았다.

**5. 기존 검사가 왜 못 잡았는지도 일치한다.** 저장소의 다른 `approve_section_version` 호출부는 모두 `now=FIXED_NOW`를 넘긴다. 예외는 `tests/preview/test_module_runner.py:337` 한 곳인데, 그 호출은 다른 실행의 결과를 지정해 `_require_section_evidence`에서 `ApprovalRequestError`가 나기를 기대하므로 459줄에 도달하지 않는다. 459줄에 닿는 기본 경로를 고정하는 검사는 실제로 없었고, 이것이 보고서 설명과 같다.

## 남은 확인

실제 승인 POST와 그 뒤 홈 문서 표시는 root 담당이다. 이 수정은 그 요청이 500으로 끝나지 않게 하는 최소 원인 수정이며, 승인 후 화면까지 확인한 것은 아니다. 승인 기록이 비어 있는 상태(`approved=[]`)는 이 수정이 만들거나 바꾼 것이 아니다.

## 범위 준수

테스트 실행·새 코드·재현·mutation·실제 API·DB·서버·브라우저·추가 워커를 쓰지 않았다. 보고된 1 pass 근거와 앞선 검토 근거를 재사용했다. 이 확인에서 제품·검사·도구 코드를 편집하지 않았고 백그라운드 작업도 시작하지 않았다.
