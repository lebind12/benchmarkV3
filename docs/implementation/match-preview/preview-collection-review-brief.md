# PC-ACCEPT — 수집 연결 한정 독립 검토

04:21 KST 입력 갱신: 원 구현자가 지연 메일을 소비해 회차를 generation_due_at(kickoff)로 고치고 경기 단위 advisory lock을 추가한 뒤 편집 종료를 다시 보고했다(msg_5845027745ec). 최신 home_preview_collection.py SHA256은 8005eb652565713c6eb060cd277b3349ad23db6e8af7229fc00be69f412b84bf, 검사 파일은 56ca1b0e8231ffe50d35c8397a828acfc9b0d0593c1c1f95d204004ac25311a5다. 보고서 마지막 후속 절의 14 passed가 최신 주장이다. 아래의 slot_time(now) 대조 항목은 수정 전 관측이므로 현재 코드로 판정한다. 기존 1회 검토 안에서 두 변경 파일과 직접 영향만 반영하고 새 검토를 시작하지 않는다. 이전 11검사를 이미 실행했으면 실제 코드 변경이 있으므로 지정 명령으로 최신 검사를 1회 확인할 수 있다. 후속 Dispatch의 sender_not_assignee 등록 실패는 제품 판정과 분리하며 복구하지 않는다.

작업 전 `/Users/woolee/benchmark/.agents/skills/poteto-mode/SKILL.md` 전문을 직접 읽고 적용한다. 같은 세션에서 이미 전문을 읽었고 내용이 같으면 해시 확인 근거로 재사용한다. 필요한 플레이북/원칙만 읽고 실제 로딩 근거를 착수/완료 보고에 남긴다. AGENTS.md의 역할·검사 범위·종료 기준이 우선한다.

## 역할·범위

구현자와 별도인 실제 DeepSeek 세션의 읽기 전용 검토다. 확인 모델 `deepseek-ai/deepseek-v4.1-flash-1017`, 사용자 설정 max를 유지하며 다른 백엔드로 전환하거나 하위 워커를 만들지 않는다. 제품·테스트·검증 스크립트·설정·Plans.md를 편집하지 않는다. 유일한 쓰기 소유는 `docs/implementation/match-preview/preview-collection-connect-review.md` 보고서다. 구현 가능한 패치를 보고서에 대신 작성하지 않는다.

입력:

- `docs/implementation/match-preview/preview-collection-connect-brief.md` — 계약과 원래 소유권
- `docs/implementation/match-preview/preview-collection-connect-report.md` — 구현자 완료 보고
- 변경 제품 파일 `app/services/home_preview_collection.py`, `app/services/management_runs.py`, `app/services/worker_runs.py`
- 직접 검사 `tests/unit/test_home_preview_collection.py`
- 호출/저장 계약 대조에 필요한 기존 의존 파일만 읽기: preview db/config/provider/pipeline/bundle pipeline, match_preview 서비스, 기존 home_preview_generation/policy, 공개 문서 선택 경로. 무관한 프로젝트 전수 조사 금지.

구현 완료 Task/Dispatch는 task_0e24c17c119c / ctx_8008e508d509다. 11 passed는 합성 검사이며 실제 수집·모델·DB·홈 표시 성공으로 해석하지 않는다. 구현자 EDITING STOPPED/background0 보고와 완료 lifecycle을 확인했다. 그 뒤 착수 중 발송했던 중복 관련 메일이 미소비 timeout으로 보고됐다. 메일/Dispatch 복구나 기존 구현자 inbox 탐색은 이번 검토 범위가 아니다.

## 사용자 수용 기준

과거2/미래2의 기술 시험과 미래 내용은 사용자 통과다. 12월6일 본문을 부족한 미래 자료의 최소 구성 사례로 수용했고 사진·한글/ID 연결은 수집 연결 뒤 구조화로 넘겼다. 표본 재생성·내용 재심사·사진/매체 수정은 제외한다.

수집 연결의 기존 수용 기준을 확인한다:

1. 성공·부분 실패·실패 종료에서 DB 후보를 처리하며 명시 취소는 새 생성을 시작하지 않는다. 프리뷰 오류가 원래 수집 상태를 덮지 않는다. 정상 반환된 failed 결과뿐 아니라 실제 상위 예외 종료도 Q6 대상이다.
2. NS·0<남은시간<=6h, 기존 순서/한도를 유지하고 성공한 리그 필터는 없다. 관리자와 같은 generate_match_preview(trigger=collection, actor_id=None)를 호출하며 생성 실패가 다음 경기를 막지 않는다.
3. 기존 경기/회차 중복 의미를 유지한다. 관리자 문서는 자동 중복에서 제외하고 진행 중·완료·실패 이력을 고려해 새 실패 자동 재시도를 만들지 않는다. 실제 지원 진입점의 동시 실행에서 기존 중복 보장을 잃지 않아야 한다. 새 표가 없다는 사실만으로 통과시키지 않는다.
4. 실제 기본 팩토리/transport 계약과 호출이 맞고 preview_dev 쓰기 세션으로 생성까지 도달한다. 생성 결과가 비예외 실패 상태를 반환할 때에도 정상 생성으로 기록하는지 확인한다. 생성 실행 ID와 수집 결과의 연결을 확인한다.
5. 자동 전체 생성은 승인된 워크플로우 정책을 지킨다. 미승인/버전 불일치를 승인된 정상 완료로 표현하거나 관리자 시험 허용을 자동 생성 허용으로 확장하지 않는다. 기존 승인·버전·재시도 의미를 바꾸지 않는다.

## 조정자 대조에서 확인이 필요한 지점

다음은 독립 판정 전 코드/보고서 사이의 대조 항목이며 확정 결함 목록이 아니다. 직접 경로의 요구 위반인지 판정하고 코드 근거·사용자 영향을 남긴다.

- 보고서는 승인 상태를 생성 후 사실로만 기록하는 것이 정책 보존이라고 설명한다. 원 brief는 자동 생성 승인 정책 보존과 미승인/버전 불일치 시 정상 완료 금지를 명시했다. 두 설명이 양립하는지 확인한다.
- 새로운 slot은 slot_time(now), 기존 process_fixture는 generation_due_at(fixture.kickoff_at)를 썼다. label은 표시 팀명도 포함한다. 기존 회차 의미·관리자 제외·경기별 중복이 유지되는지, 조회와 생성 사이의 실제 지원 경로 보호를 확인한다.
- factory 함수는 get_session_factory()를 반환하고 호출부는 전달받은 함수를 with 문에 사용한다. 기존 함수가 실제로 반환하는 타입까지 대조한다. transport 설정 필드와 생성자 인자도 관리자 기존 경로의 실제 정의와 대조한다. 이런 기본 배선을 모의 경계가 가리고 있지 않은지 확인한다.
- management_runs/worker_runs 훅은 현재 정상 try 블록 안에 있다. 상위 예외 경로의 failed 종료도 프리뷰에 도달하는지 확인한다.
- tests는 후보·중복·생성기를 대역으로 사용한다. 11 passed가 어떤 수용 기준을 실제로 고정하며 어느 배선은 검증하지 못하는지 구분한다. 반복적 변이 검사나 전체 회귀를 추가하지 않는다.

이는 배정된 기능의 실제 기본 경로 확인이며 범용 동시성·장애 복구 플랫폼 설계가 아니다. 새 정책이나 미지원 환경을 완료 조건에 추가하지 않는다.

## 검증·종료

허용 명령은 `.venv/bin/python -m pytest tests/unit/test_home_preview_collection.py -q` 1회다. 기존 통과 근거를 재사용할 수 있으나 검사 근거 확인에 필요하면 이 명령만 실행한다. 제품 코드에 직접 도달하는 논리적 모순은 파일/행/실제 호출 계약으로 보고한다. 새 재현 스크립트·테스트 작성, 코드 메모리 치환, DB/외부 HTTP/모델/브라우저/운영 수집/서버 재시작/마이그레이션/승인 POST는 하지 않는다.

보고서는 현재 요구 위반/재현된 범위 내 결함, 근거 부족, 차단하지 않는 참고를 구분한다. 해결책은 최소 변경 범위를 설명하되 구현하지 않는다. 현재 승인 정책·기본 호출 실패는 단순 참고로 낮추지 않는다. 검사 개수나 완전 탐색을 목표로 하지 않는다. 1회 한정 검토 후 종료한다.

완료 시 새로 배정된 활성 Task/Dispatch로 worker_done 한 번을 보내고 EDITING STOPPED와 백그라운드 작업 수를 기록한다. 이전 settled/failed Dispatch와 probe를 사용하지 말고 추가 메일/Task 탐색 없이 idle로 돌아간다.
