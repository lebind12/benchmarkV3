# PC-CONNECT 상위 예외 경로의 실행 근거 보완

작업 전에 `/Users/woolee/benchmark/.agents/skills/poteto-mode/SKILL.md` 전문을 읽고 적용한다. 같은 세션에서 직접 읽었고 미변경이면 확인한 해시로 재사용한다. 실제 모델 `deepseek-ai/deepseek-v4.1-flash-1017`, dsh-tui 프로필, 사용자 추론 강도 max를 유지한다. 하위 워커·모델 전환은 하지 않는다.

이것은 기존 승인 범위의 지적2에 빠진 실행 근거를 보완하는 작업이다. 직전 task_6af5a3a3558e의 네 수정과 19 passed는 보존한다. 보고서가 인정한 것처럼 상위 수집 예외 경로는 아직 실행 검사가 없다. 원래 명세는 네 지적 모두 직접 변경 경로의 대표 검사를 요구했고 `tests/unit/test_home_preview_collection.py`의 소유권도 부여했다. 새 테스트 파일을 만들 필요 없이 그 파일에서 실제 상위 진입점을 호출하는 검사를 추가할 수 있다.

## 소유권과 범위

- 편집: `tests/unit/test_home_preview_collection.py`, `docs/implementation/match-preview/preview-collection-connect-report.md`.
- 제품 파일은 기본 읽기 전용: `app/services/home_preview_collection.py`, `app/services/management_runs.py`, `app/services/worker_runs.py`. 새 검사가 이번 상위 예외 수정의 직접 결함을 드러내면 동일 소유자인 본인이 이 세 파일에서 필요한 최소 수정만 수행하고 이유를 보고한다.
- 새 시험 도구·실제 수집·UI·승인·DB 스키마·Plans.md는 편집하지 않는다.

## 필요한 실행 근거

management_runs와 worker_runs 각각 실제 상위 진입점에서 수집 준비/실행이 예외로 끝나는 대표 사례를 외부 연결 없는 대역으로 유도한다. 프리뷰 훅에 실패 상태가 전달돼 한 번 호출되고 원래 수집의 failed 상태와 오류가 보존되며 결과는 별도 home_preview에 남는 것을 확인한다. 함수 내부의 새 except 로직을 테스트에 복사해서 확인하지 않는다. 두 진입점의 배선이 다르므로 각 경로의 대표 사례는 현재 요구와 직접 연결된다.

추가 환경 행렬·전체 회귀·변이 실험은 하지 않는다. 기존 취소·승인·중복 검사와 앞선 세 지적의 유효한 근거는 재사용한다. 직접 명령은 `.venv/bin/python -m pytest tests/unit/test_home_preview_collection.py -q`이며 변경 후 한 번 실행한다. 실패하면 해당 실패에 필요한 수정과 재실행만 한다. 같은 원인의 두 차례 실패 시 최소 원인과 해결 범위를 보고한다.

실제 DB·외부 HTTP·모델·운영 수집·브라우저·서버·승인 POST·마이그레이션은 호출하지 않는다. 실행을 대역으로 격리할 수 없으면 실제 호출로 바꾸지 말고 구체적인 막힘을 보고한다. 보고서에 상위 두 경로의 실행 근거와 명령 결과를 남기고 EDITING STOPPED·백그라운드0으로 새 활성 Task/Dispatch에 한 번 완료 보고한다. 과거 Dispatch 복구·추가 메일 탐색은 하지 않는다.
