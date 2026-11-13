# HP-APPROVAL — 실제 승인 API 기본 시각 오류

작업 전 `/Users/woolee/benchmark/.agents/skills/poteto-mode/SKILL.md` 전문을 적용한다. 같은 세션에서 읽은 미변경 본문은 기존기록/해시로 재사용할 수 있다. 실제 DeepSeek flash-1017 Max 유지. 기존 HP-FIX는 종료됐고 이번은 사용자 승인 실행에서 관측된 새 결함의 좁은 수정이다.

사용자가 02:26에 저장된5섹션 워크플로우 버전 승인을 명시적으로 허가했다. root가 기존API로 첫 AI전망 승인POST를 보냈으나 서버에서 `app/preview/approvals.py:459`, `datetime.now(timezone.utc)`의 `NameError: name 'timezone' is not defined`로 실패했다. 직후 approvals GET은 approved=[]·forecast none으로, 실제 승인행은 아직 없다. root가 파일상단 `from datetime import datetime`과 이 참조를 대조했다. 기존 F2/F3 승인검사는 now=FIXED_NOW를 넣어 기본시각 경로가 검증되지 않는다. 이 사실을 재조사로 넓히지 않는다.

## 소유와 수용 기준

- `app/preview/approvals.py`: 승인시각 기본 경로가 유효한 UTC 시각을 기록하게 하는 최소 원인 수정만 허용한다. 승인버전/본문/권한/현재와저장버전 판단은 바꾸지 않는다.
- 새 `tests/unit/test_section_approval_timestamp.py`: now를 생략한 승인 호출이 실패하지 않고 UTC 승인시각과 근거 버전을 유지하는 대표 검사1건. 실제 DB 연결 없이 기존 패턴의 합성 session/경계 대역을 사용한다. 단순 import문을 확인하는 구현복제 검사는 쓰지 않는다. 기존 DB전용 승인검사들을 실행하거나 수정하지 않는다.
- `docs/implementation/match-preview/home-approval-time-fix-report.md` 짧은 보고만 허용. Plans.md/다른제품/검사/설정 수정 금지.

검사 이유: 사용자가 정상 저장본을 승인해도 기본시각 계산에서500이 나면 홈에 표시할 수 없다. 최소 수정 전 실패와 수정 후 성공을 한 사례로 보인다. 명령은 `.venv/bin/python -m pytest tests/unit/test_section_approval_timestamp.py -q`만 사용한다. 같은 원인2회 실패면 원인/최소범위를 보고하고 멈춘다.

금지: 실제 DB·API·승인POST·모델·수집·브라우저·서버재시작·설치·다른전체검사·mutation테스트·과거메일/Task복구·다른워커. 실제승인과화면확인은root가한다. 기존운영/개발데이터를테스트로초기화하지않는다.

수정 후 변경파일·실행명령/결과·원인·스킬이선택을바꾼점, EDITING STOPPED·백그라운드0을 보고하고 이번 새 Task/Dispatch로 worker_done 한 번만 보내 idle로 돌아간다. 이후 파일을 보며 추가 보완을 자동 시작하지 않는다.
