# HP-APPROVAL 한정 독립 확인

작업 전 `/Users/woolee/benchmark/.agents/skills/poteto-mode/SKILL.md` 전문을 적용한다. 기존 seq26/27 읽기와 미변경은 재사용한다. 실제 DeepSeek flash-1017 Max 유지. 구현자와 별도인 기존 검토 세션으로 읽기 전용 확인한다.

입력은 `home-approval-time-fix-report.md`, `app/preview/approvals.py`의 timezone import 변경, 새 `tests/unit/test_section_approval_timestamp.py`다. 사용자 승인 후 실제POST가459행 timezone NameError로500이었고 승인0을 root가 확인했다. 구현자는1줄수정·합성1passed·EDITINGSTOPPED·백그라운드0을 보고했다.

수용: now생략기본경로의오류가고쳐지고UTC시각을기록하며,승인버전/권한/본문정책을바꾸지않았는지,대표검사가그경로를실제로호출하는지한번만읽어확인한다. 기존승인계산전체·홈·e2e·참고지적을다시검토하지않는다. 테스트실행/새코드/재현/mutation/실제API/DB/서버/브라우저/추가워커는금지한다. 보고된1pass근거를재사용한다. 실승인과화면확인은root가병행한다.

보고서는 `docs/implementation/match-preview/home-approval-time-review.md`만 짧게 작성한다. 직접요구위반이없으면수용하고추가개선을만들지않는다. 완료시이번새Task/Dispatch로worker_done한번·편집종료·백그라운드0을보고하고idle로돌아간다.과거메일/timeout/다른Dispatch를탐색하거나복구하지않는다.
