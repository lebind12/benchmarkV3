# HP-EVIDENCE 한정 독립 검토

먼저 `/Users/woolee/benchmark/.agents/skills/poteto-mode/SKILL.md` 전문을 읽고 적용한다. 같은 세션에서 실제 전문을 읽었고 내용이 같으면 기존 읽기 근거를 재사용한다. 실제 모델은 `deepseek-ai/deepseek-v4.1-flash-1017`, 사용자 추론 강도 max를 유지한다.

사용자는 맨체스터 시티–풀럼의 저장된 구성본을 표시하도록 명시 승인했다. 실제 승인 5행의 근거 ID는 정확하지만 기존 역사 버전 계산과 저장 섹션 스탬프가 다른 4개 섹션이 홈에서 제외됐다. 구현자는 활성 승인에 적힌 정확한 워크플로우·검토 실행·섹션 결과를 홈 조회가 읽도록 보완했다. 기존 승인 버전 계산, 저장 행, 현재 생성 워크플로우의 승인 정책은 바꾸지 않는다.

읽기 범위는 `app/services/home_preview_document.py`의 이번 approved_evidence 및 연결 변경, `tests/unit/test_home_preview_document.py`의 새 대표 검사, `home-approved-evidence-brief.md`와 `home-approved-evidence-report.md`다. 이전 홈 전체·프론트·e2e·승인 시각 수정의 검토를 반복하지 않는다. 필요할 때 승인 모델의 필드 정의만 참조한다.

수용 기준:

- 활성 승인 근거가 정확히 가리키는 저장 행은 버전 문자열이 달라도 표시한다.
- 다른 실행·다른 결과·다른 워크플로우로 근거를 확장하지 않는다. 비활성 승인, 모의 결과, 빈 본문은 제외한다.
- 기존 버전 승인 경로, 구성본 정확 선택과 경기 범위, 읽기 전용 조회를 보존한다.
- 실제 조회가 근거 필드를 읽어 선택 함수까지 전달하며, 대표 검사가 관측된 누락을 잡는다.

검증은 코드와 기존 15 passed 근거 대조가 기본이다. 구체적인 근거 부족이 있을 때만 `.venv/bin/python -m pytest tests/unit/test_home_preview_document.py -q`를 1회 실행할 수 있다. 새 코드·재현 스크립트·테스트·전체 회귀·DB/API/브라우저·서버·하위 워커는 금지한다. 실제 5섹션과 화면 확인은 root가 병렬로 진행한다.

보고서 `docs/implementation/match-preview/home-approved-evidence-review.md`만 작성한다. 재현된 직접 결함/요구 위반과 참고를 구분하고 수용 여부·읽기 범위·명령 실행 여부를 짧게 기록한다. 완료 시 편집 종료/백그라운드 0을 명시하고 현재 배정된 Task/Dispatch로 worker_done을 한 번만 보낸다. 과거 New messages/timeout의 메타데이터 복구나 추가 메일 탐색은 하지 않는다.
