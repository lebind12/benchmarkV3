# 기간 재시험409의 현재 수집 식별 — 읽기 전용

작업 전 `/Users/woolee/benchmark/.agents/skills/poteto-mode/SKILL.md` 전문을 읽고 적용한다. 미변경인 같은 세션의 직접 읽기는 해시 근거로 재사용한다. 실제 dsh-tui `deepseek-ai/deepseek-v4.1-flash-1017`/max 유지. 새 하위 워커·모델 전환 없음.

조정자는 조회기 수정과 독립 확인을 수용하고 기존 로컬API를 정상 종료한 뒤 같은 scripts/run_benchmark_dev.sh로 PID15812를 시작했다. 첫 시험0178213b…는 이미05:49:42 KST에 종료됐다. 수정 반영 뒤 06:00:07 KST 같은 기간 시험POST를 한 번 요청했으나 HTTP409였고 새 실행ID가 없다. 응답에서 message/code를 조정자가 보존하지 못했으므로 내용을 추측하지 않는다. 코드상 active management 행 또는 daily sync advisory lock 두 갈래다. GET 관리수집 목록은7일 이전 행을 DELETE하므로 호출하지 않는다.

필요한 결과는 **현재 수집의 ID·상태·시작시각·heartbeat·stage·진행률**과 필요 시 **기존 daily sync advisory lock이 다른 세션에 보유돼 있는지**다. 이 사실만 알면 root가 개별GET으로 완료를 기다릴 수 있다. 정각 정기 수집일 가능성은 추정이며 확인 후 사실로 보고한다.

실제 DB 읽기를 이번 작업에 한해 허용한다. root가 이미 사용 중인 동일 연결 대상과 자격증명을 기존 설정 방식으로 재사용한다. 기존 launcher가 읽는0600 환경 파일의 비밀값을 화면·로그·보고·프롬프트에 출력하거나 복사하지 않는다. 별도 설정 변경·계정 변경·권한 부여는 없다. DB 연결은 읽기 전용 transaction으로 하고 관리 실행의 활성행과 잠금 메타데이터만 최소 SELECT한다. 저장소에 새 스크립트·검사·도구를 추가하지 않는다. 단발 읽기 쿼리는 허용하되 재현 실험으로 확대하지 않는다.

**금지:** UPDATE/DELETE/INSERT/DDL/마이그레이션, 잠금 획득·해제·세션 종료, 취소POST·수집POST·모델·외부API·서버재시작, 제품·검사·설정·Plans.md 편집, 반복 폴링·전체테이블 탐색·다른 업무자료 조회. 연결 실패 시 임의 접근 방식이나 비밀값 탐색으로 넓히지 말고 실패만 보고한다.

출력은 안전한 실행ID·상태·시각·진행·잠금 보유 유무만 남긴다. 필요하면 `docs/implementation/match-preview/preview-collection-active-read-report.md` 하나에 요약한다. 확인한 DB 호스트/역할은 원문 공개 없이 기존 대상과 일치 여부만 적는다. Task/Dispatch에 한 번 완료 보고하고 EDITING STOPPED·백그라운드0으로 종료한다. 원 생성·승인 기록과 다른 수집은 건드리지 않는다.
