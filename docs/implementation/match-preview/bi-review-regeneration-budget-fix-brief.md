# BI-02 한정 수정 — 독립 검토 B-2

DeepSeek 구현 전용. 실제 deepseek-ai/deepseek-v4.1-flash-1017 / Max 설정을 유지하고 시작 시 모델을 확인한다. 하위 워커·모델 교체 없음. 원 B는 실제 idle·EDITING STOPPED 화면을 조정자가 확인했으며, 아래 두 파일 경계를 인계한다. 다른 작업은 frontend와 테스트 안전가드/import에 한정돼 있다.

목표: 한 경기의 섹션 재생성에서도 각 참여 논리 AI 모듈에 최초 포함 3회의 전송 기회를 보장한다. 조사에 쓴 전송 때문에 작성 모듈이 자기 상한 전에 거부되는 B-2만 수정한다.

입력: docs/implementation/match-preview/bi-integration-review.md B-2. 현재 run_section_regeneration은 선택 작성 모듈만 budget.module_ids에 넣지만 refresh에서는 같은 예산으로 해당 조사 모듈도 호출한다. 조사 2회 + 작성 1회 뒤 작성의 두 번째가 합계3 상한으로 거부되는 현재 결함이다. 전체 프리뷰의 새 정책과 기존 장부는 재설계하지 않는다.

소유 파일:

- app/preview/bundle_pipeline.py의 run_section_regeneration 참여 모듈/예산 구성 경계
- tests/preview/test_bundle_integration.py의 기존 재생성 직접 사례
- 꼭 필요한 경우 tests/preview/test_retry_budget.py의 대표 사례만. retry.py/provider.py 정책·다른 제품 파일은 변경하지 않는다.

수용 기준:

1. 첫 전송 전 실제 실행 계획에 맞는 모듈 집합으로 예산을 구성한다. refresh는 현재 해당 섹션에서 실제 실행하는 조사와 작성 모듈을 포함한다. reuse는 검색·수집 없이 선택 작성만, 배당 작성은 모델0회라는 기존 동작을 유지한다. 새 조사 그룹/새 모듈/추가 모델 호출은 도입하지 않는다.
2. 조사 모듈이 기술 오류로 재시도하더라도 작성 모듈은 자신의 최초 포함3회까지 가능하고, 어느 모듈도 네 번째 전송은 불가하다. 실제 participant 수에서 계산한 합계는 모듈별 기회를 줄이지 않는다.
3. 과거 시험집합/다른 경기 누적은 차감하지 않는다. 성공 모듈 재전송·이중 재시도·새 품질 판정 없음. 40000, 요청별 타임아웃, HTTP 홉 제한, 원문/부분 본문/이전 결과 저장, composition 선택은 보존한다.

검증: 기존 RecordedTransport/기록 하네스로 위 결함을 직접 보여주는 대표 검사만 추가/수정한다. 조사 재시도 후 작성의 남은 기회가 실제 재생성 경로에 전달되는 것을 확인한다. 기존 reuse 대표 사례도 확인한다. 새 검증 스크립트·전체96스위트·모델·외부HTTP·운영DB쓰기·서버전환·commit/stage0. 변경 없는 전체 프리뷰 검사를 반복하지 않는다.

DB 테스트가 필요하면 기존 loopback *_test 안전가드가 먼저 적용돼야 한다. 다른 작업의 테스트DB 초기화와 겹치지 않게, 순수 검사/수정부터 완료하고 DB 검사 직전에 조정자에게 대상과 실행 명령을 알려 순서를 받는다. 조정자가 가드/import 담당의 검사 종료를 확인한 뒤 이어서 실행한다. 운영 URL로 pytest/DDL을 실행하지 않는다.

완료: 실제 변경 파일, refresh/reuse 참여 모듈 목록, 대표 실행 명령·결과, 남은 제한을 보고하고 EDITING STOPPED. 완료 등록 거부 시 status 한 번으로 인계하고 재전송/메일 탐색 루프를 만들지 않는다. Plans.md·검토 보고서·frontend·다른 제품 코드·비밀파일 편집 없음.
