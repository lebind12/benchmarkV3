# PC-ACCEPT 기존 네 지적의 수정 확인

작업 전에 `/Users/woolee/benchmark/.agents/skills/poteto-mode/SKILL.md` 전문을 읽고 적용한다. 같은 세션에서 직접 읽었고 미변경이면 확인한 해시로 재사용한다. 실제 모델은 dsh-tui의 `deepseek-ai/deepseek-v4.1-flash-1017`, 추론 강도 max를 유지한다. 모델 전환·하위 워커는 없다. 착수 시 모델·스킬 로딩 근거·적용 원칙·읽기 전용 범위를 짧게 보고한다.

이 작업은 PC-CONNECT의 기존 독립 지적1~4에 대한 한정 수정 확인이다. 전체 기능을 다시 리뷰하지 않는다. 구현자는 수정과 실행 근거 보완을 끝냈고 두 터미널의 빈 입력·실제 모델과 편집 종료를 조정자가 확인했다. 과거 실패 Dispatch 복구·worker_done 재시도·메일 probe를 하지 않고 이번 활성 Task/Dispatch만 사용한다.

## 입력과 확인 리비전

- 기존 판정: `docs/implementation/match-preview/preview-collection-connect-review.md`의 요구 위반1~4.
- 구현 인계: `docs/implementation/match-preview/preview-collection-connect-report.md`의 네 지적 수정 절과 2026-11-13 04:58 상위 예외 실행 근거 절.
- 최초 수정 task_6af5a3a3558e, 보완 task_f2bef2cfc156. 최신 보고는 합성22 passed이며 실제 수집·DB·모델 성공 근거가 아니다.

04:58 KST 조정자가 읽은 SHA256:

| 파일 | SHA256 |
|---|---|
| app/services/home_preview_collection.py | fedb19539f5782c6216add8deba805e4dee619de2f00415f06f5ec1637dd8524 |
| app/services/management_runs.py | 4b22c0b946bf05c3f0f1ecc2da2fc489ebd44a6ca6bf459b248a3a5d3ecaa5d3 |
| app/services/worker_runs.py | 06f910cdd58160c15cdf0c4cd3c0094ab9ae54adc745bf9b3eed2a173e7aa7df |
| tests/unit/test_home_preview_collection.py | 6fef66514496e7dbc76c8b068e9e04ffd3d9849551d20f04f687ad464d203dc2 |

## 소유권·확인 대상

편집은 기존 `docs/implementation/match-preview/preview-collection-connect-review.md`에 수정 확인 절을 추가하는 것만 허용한다. 제품·검사·설정·Plans.md·시험 도구는 읽기 전용이다. 위 네 파일의 수정 경로와 필요한 직접 계약만 읽는다.

1. preview 기본 팩토리·관리 훅·승인 조회가 Session을 제공하는 동일 계약을 사용하며 이전 sessionmaker/with 실패가 해결됐는가.
2. 관리 execute_run과 worker start_daily_sync_run의 상위 수집 예외에서 프리뷰 훅이 한 번 호출되고 원래 실패 상태/오류가 보존되는가. 명시 취소·정상 경로 중복 방지가 유지되는가. 새 검사 세 개가 실제 진입점과 요구 경로에 도달해 위 결과를 고정하는가.
3. 생성 전 기존 admission_state를 사용해 not_ready/unknown은 생성하지 않고 ready만 진행하는가. 관리자 시험·승인 버전 계산을 바꾸지 않았는가.
4. 비예외 FAILED를 generated에 넣지 않고 실패 실행 ID·사유를 남기며 다음 경기 처리를 계속하는가.

기존 회차·경기별 잠금·실패 격리의 유효한 근거를 재사용한다. 이 수정이 만든 직접 회귀나 위 필수 조건의 실제 실패만 새 차단으로 보고한다. 참고 개선3~N을 새 전체 검토로 확대하지 않는다. 실제 advisory lock 동시 실행·미래 기간 지정 도구·실수집·본문 구조화는 이번 완료 조건이 아니다.

## 검증과 종료

허용 명령: `.venv/bin/python -m pytest tests/unit/test_home_preview_collection.py -q`를 현재 수정본에 한 번 실행한다. 이전14·19 통과와 합산하지 않는다. 실패 시 실패 근거를 기록하고 제품 수정·추가 재현을 하지 않는다. 변경이나 구체적인 증거 모순 없이 같은 명령을 반복하지 않는다.

새 코드·스크립트·인라인 Python 재현·변이 실험·설정 교체·stash/원복·전체 회귀는 금지한다. 실제 DB·외부 HTTP·모델·수집·브라우저·서버·승인 POST·마이그레이션도 호출하지 않는다. 기존 소스·새 검사·위 명령으로 확인한다.

보고서에는 네 지적별 해결/미해결, 근거 위치, 실행 명령·결과, 실제 연동 미확인을 남긴다. worker_done에 수용 또는 남은 직접 위반과 EDITING STOPPED·백그라운드0을 보고하고 종료한다. 과거 메일·Task 탐색으로 새 작업을 시작하지 않는다.
