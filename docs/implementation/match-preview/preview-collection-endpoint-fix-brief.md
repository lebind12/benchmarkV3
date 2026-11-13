# PC-LIVE 실제 실행 전 연결 보완

작업 전 `/Users/woolee/benchmark/.agents/skills/poteto-mode/SKILL.md` 전문을 읽고 적용한다. 같은 세션에서 직접 읽었고 미변경이면 해시 근거로 재사용한다. dsh-tui의 `deepseek-ai/deepseek-v4.1-flash-1017`/max 유지, 모델 전환·하위 워커·새 Run 없음. 이번은 사용자 승인한 새 시험 엔드포인트가 실제 두 경기 생성에 도달하도록 하는 기존 범위의 결함 수정이다.

## 선행 결과와 소유권

- 독립 확인: `preview-collection-endpoint-review.md`. 기간 저장 게이트·두 ID 시간창 예외·시험 키는 유지한다. 입력 소속 검증·경기별 제외 사유·종료 훅 연결 검사 부족은 수정 대상이다.
- 읽기 조사: `preview-collection-admission-findings.md`. 실제 bundle 대상과 승인 판정 대상 불일치·저장/manifest 계약 축 차이·시험 요청이 전역 플래그에 막히는 원인을 해결한다.
- 실제 GET 근거: `preview-collection-live-evidence.md`. 승인5행은 유지하며 새로운 승인POST를 보내지 않는다.
- 조정자 추가 사실: 현재 management_runs.py:560~563은 성공 시 test_scope 검사 없이 prune_league_seasons를 호출한다. management.py:591~600의 이 함수는 Injury/PlayerSeasonStat/Standings/TeamSeason/TeamCoach/Fixture의 오래된 시즌 행을 DELETE한다. 따라서 보고서의 “시험에서 시즌 정리 없음”은 현재 코드와 일치하지 않는다. 이번 시험에서는 이 호출을 차단한다.

편집 소유권:

- app/services/management_runs.py
- app/services/home_preview_collection.py
- app/services/collection_test_scope.py
- app/api/v1/management.py (입력 검증에 필요할 때만)
- app/preview/pipeline.py (bundle 승인 판정 추가에 필요한 최소 범위)
- app/preview/version_manifest.py (실제 저장 계약과 현재 계산 일치)
- tests/unit/test_management_preview_test.py
- tests/unit/test_home_preview_collection.py
- tests/unit/test_bundle_collection_admission.py (필요한 순수 단위 검사 신규)
- docs/implementation/match-preview/preview-collection-endpoint-report.md

다른 제품·프롬프트·모델·원문·승인 행/승인 생성 코드·contracts.py·프론트·설정·Plans.md는 읽기 전용이다. runner 기간 필터는 이미 확인됐으므로 보존한다. 소유자가 직접 편집 종료를 보고한 뒤 배정했으며 동시에 제품을 편집하는 다른 워커는 없다.

## 수정해야 할 결과

1. **접수 전 소속 확인.** 지정한 두 외부 경기 ID를 기존 DB에서 읽어 선택한 활성 수집 대상의 실제 리그/시즌·요청 기간 양 끝 포함·미래 NS 조건과 대조한다. 내부/외부 리그 ID를 혼동하지 않는다. 부적합하면 수집 작업 생성·외부 호출 전422로 거부하고 어느 경기의 어떤 조건인지 알린다. 범용 옵션·새 유효성 엔진은 만들지 않는다.
2. **수집 후 범위와 사유.** 일정/상태/소속이 바뀌어 지정 경기가 제외되면 해당 ID별 skipped 사유를 남긴다. 실제 생성 직전에도 요청 기간/소속을 존중한다. 현재 예외 후보는 now+365일 안의 ID만 찾으므로 “기간 밖이면 항상 no_candidates”라는 리뷰 서술을 가정하지 않는다. 요청 기간 밖 ID는 생성하지 않아야 한다. 새 임의 기간 상한은 추가하지 않는다.
3. **명시적 시험 훅과 실제 연결 검사.** 일반 HOME_PREVIEW_ENABLED=false는 존중하되 검증된 test_scope가 있는 명시적 시험 요청은 정상/상위 예외 종료에서 훅을 한 번 호출한다. 전역 설정은 켜지 않는다. 실제 관리 실행→실제 종료 훅→수집 생성 경계를 통과하고 모델/DB 외부 경계만 대역으로 삼는 대표 검사로 두 경기와 수집ID가 이어지는지 확인한다. 훅 자체를 대체한 호출 횟수만으로 이 요구를 증명하지 않는다. 일반 경로·명시 취소의 기존 동작은 유지한다.
4. **시험에서 시즌 정리 제외.** 시험 범위가 있으면 prune_league_seasons를 호출하지 않는다. 기간 내 정상 갱신과 기존 일반 수집의 정리 정책은 유지한다. 이 시험을 전체 시즌 수집 완료로 기록하지 않는다. 위 연결 검사에서 대상 객체가 실제 존재하고 수집 성공이 되는 경우로 확인해 target=None 때문에 정리 경로에 닿지 않는 빈 검사를 만들지 않는다.
5. **실제 bundle 대상 승인 판정.** 공통 생성 서비스가 실제 만드는 information_bundle.SECTION_IDS를 동일 출처로 사용한다. 옛 pipeline.required_workflows/admission_state는 그 경로의 의미를 보존하고, 수집 경계는 bundle 대상의 준비 상태를 판정한다. 승인 없음/실제 버전 불일치는 계속 차단한다. bundle 생성에 없는 form/synthesis를 요구하지 않고 odds/ai_forecast를 포함한다. 관리자 기존 GET/admission이 옛 경로 판정이라는 사실은 인계에 명시한다.
6. **같은 결과의 계약 비교를 일치시킨다.** 실제 bundle 저장 경로가 R2/R3/R4/S1 결과에 SECTION_RESULT_CONTRACT_VERSION을 쓰는 근거를 확인하고, 현재 manifest도 해당 경계에서 같은 축을 사용한다. D0·compose·옛 워크플로우 축을 무조건 바꾸지 않는다. 기존 승인 근거의 구현/프롬프트/출력 계약을 전부 비교해 실제 의미 변경이 없음을 확인한다. 승인 행을 수정하거나 ready를 강제하지 않는다. 실제 버전이 달라진 경우는 미승인으로 유지한다.

조사 보고서의 “재확인이 필요할 수 있다”는 미확인 추론을 일괄 신규 승인 필요로 해석하지 않는다. 정확히 같은 승인 근거와 실제 구성의 비교 오류를 고쳐 기존 승인 버전과 일치하면 그것은 새 승인 생성이 아니다. 수정 후에도 의미 있는 차이가 남으면 구체적인 차이만 보고하고 승인POST를 하지 않는다. 이번 시험의6시간 예외는 승인 정책 예외가 아니다.

## 직접 검사·종료

대표 입력: 현재 두 경기와 기간의 정상 접수, 범위 밖 지정 ID의 접수 전 거부, 수집 후 한 경기 상태/기간 변경의 명확한 제외, HOME_PREVIEW_ENABLED=false에서도 명시적 시험의 두 경기 생성과 기간 밖 시즌 정리 미호출, 일반 경로의 기존 정책 보존, 실제 bundle 집합만의 승인 판정, 저장 근거와 manifest 계약 일치 및 실제 프롬프트/출력 변경 시 불일치 보존.

기존 단위 검사 환경만 쓴다. tests/preview의 DB fixture 검사를 운영 URL로 실행하지 않는다. 새 승인 단위 검사는 외부 연결 없는 합성 행/순수 계약으로 작성한다.

직접 명령은 `.venv/bin/python -m pytest tests/unit/test_management_preview_test.py tests/unit/test_home_preview_collection.py tests/unit/test_bundle_collection_admission.py tests/unit/test_home_preview_document.py -q`다. 새 승인 검사 파일은 이 명령에 맞게 작성한다. 마지막 파일은 manifest/승인 변경이 기존 공개 저장본 선택에 영향을 주지 않는지 보는 기존 직접 검사이며 편집하지 않는다. 한 번 실행해 통과하면 종료하고 실패 시 해당 실패에 필요한 수정/재실행만 한다. 전체 회귀·변이 실험·코드 원복 실험·임의 인라인 재현은 하지 않는다.

실제 DB·외부 API·모델·서버·환경 비밀값 탐색·승인POST·마이그레이션은 하지 않는다. 테스트 수 목표는 없고 현재 수용 결과만 검사한다. 같은 원인의 두 차례 실패 시 조사 범위를 늘리지 말고 최소 원인과 해결 범위를 보고한다.

보고서의 잘못된 시즌 정리/승인 판정 설명을 정정하고 실제 요청·종료 판정·승인 확인 방법·리비전·명령 결과·미확인을 남긴다. 완료 시 EDITING STOPPED·백그라운드0으로 새 Task/Dispatch에 한 번 보고한다. 독립 수정 확인과 실제 새POST1회는 조정자가 이어간다.
