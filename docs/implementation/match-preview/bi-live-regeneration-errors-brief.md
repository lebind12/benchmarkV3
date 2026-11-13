# BI 재생성 실제 호출 경계 — E-1 / E-2 최소 수정

DeepSeek 구현 전용. 실제 deepseek-ai/deepseek-v4.1-flash-1017 / Max 유지, 하위 워커·모델 교체 없음. 기존 구현자들은 EDITING STOPPED 및 물리 종료가 확인됐다. 원 검토 보고서 9-3의 E-1/E-2만 맡는다. 전체 코드 검토·리팩터링·다른 참고 지적은 범위 밖이다.

사용자 목표: 관리자가 live 섹션 재생성/구성본의 마지막 AI를 실행했을 때 실제 저장된 결과와 그 결과의 응답을 받는다. GET은 저장본만 조회하고 모델 호출하지 않는다. 모듈별3회·원문 보존·사용자 내용 판단 정책은 변경하지 않는다.

소유 파일:

- app/api/v1/preview_admin.py의 create_section_run live 반환 경계
- app/preview/bundle_pipeline.py의 run_section_regeneration 구성본 복사 및 현재 결과 조회/메타데이터 경계
- tests/preview/test_bundle_integration.py의 해당 실제 호출·저장 대표 사례만

확인된 경로:

1. E-1: live 재생성 함수가 완료·commit된 뒤 SectionRunResponse를 만들 때 version_manifest 이름이 미정의다. 기존 workflow version 조회 계약을 실제 import/바인딩해 연결한다. 새로운 버전 생성기·예외 삼키기·mock 대체로 피하지 않는다.
2. E-2: upstream_items가 있으면 구성본 복사 블록이 quality/unavailable/row를 초기화보다 먼저 읽는다. selected_result_ids 분기의 row는 이전 선택 항목일 수도 있다. 새 구성본에서 이 실행이 재생성한 항목의 result_id/run_id/version/quality/사유는 반드시 방금 저장된 새 결과와 일치해야 한다. 다른 선택 항목은 기존 ID/버전 그대로 보존하고 부모 구성본·원문·이전 결과는 덮어쓰지 않는다. 예외를 삼키거나 구성본 복사를 생략하지 않는다.

검증 범위:

- 기존 RecordedTransport와 loopback *_test DB 안전가드로 실제 live API 반환과 저장 구성본 재생성 경계를 확인한다. 외부 모델·HTTP 없음. 현재 실패를 먼저 관측하고 수정 후 같은 대표 사례로 확인한다.
- 저장 구성본에서 마지막 AI를 실행해 새 결론을 덧붙이는 경우와 기존 결론을 교체하는 경우의 관측된 분기만 확인한다. 가능하면 같은 대표 검사의 두 입력으로 E-1/E-2를 함께 검증한다. 선택한 기존 본문/버전은 보존되고 응답 run_id와 새 결과 메타데이터가 저장행과 일치해야 한다. 500이 없다는 단언만으로 대체하지 않는다.
- 지정 새/수정 사례와 바로 영향을 받는 기존 reuse 대표 사례만 실행한다. 전체 integration28/pipeline17/retry20 또는 전체96 반복 금지. 새 검증 스크립트·범용 재생 도구·가짜 성공 결과·단언 삭제 없음.
- 모든 다른 구현 검사는 종료돼 DB 충돌 없이 순차 실행할 수 있다. 기존 tests.preview._dbguard를 통해 loopback 전용 *_test 대상부터 확인한다. 운영 DB 연결/pytest/DDL·권한변경·유료·외부HTTP·서버전환·commit/stage0.

유일 완료 보고: 정확한 변경 파일, 실제 명령별 결과, 수정 전 오류와 수정 후 저장/응답 근거, 남은 제한. 이어서 EDITING STOPPED. 같은 검사를 반복하거나 해결 뒤 새 범위를 찾지 않는다. lifecycle 거부 시 status 한 번 후 중단. Plans·검토 보고서·frontend·인증·예산 정책·비밀파일 편집 없음.
