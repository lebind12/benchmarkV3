# PC-VERSION-REVIEW — 기존 검사 한 함수의 한정 독립 확인

작업 전 `/Users/woolee/benchmark/.agents/skills/poteto-mode/SKILL.md` 전문을 읽고 적용한다. 같은 세션에서 이미 읽었고 내용이 그대로면 읽기 근거와 변경 없음 확인을 재사용한다. 필요한 원칙만 추가로 읽는다. 실제 모델 `deepseek-ai/deepseek-v4.1-flash-1017`과 사용자 max 설정을 유지하며 다른 모델·하위 워커·새 조정 Run을 만들지 않는다.

## 범위

구현자 term_00fb0f6f와 별도 DeepSeek의 읽기 전용 검토다. 대상은 `tests/preview/test_bundle_review_fixes.py`의 `test_odds_workflow_version_changed_and_others_kept` 하나와 그 의미 확인에 필요한 `app/preview/version_manifest.py`의 버전 계산 경로뿐이다. 이 명세와 `collection-version-test-brief.md`를 입력으로 삼는다. 다른 과거 홈/e2e/승인/배당 검토·메일 조사는 재개하지 않는다. 특히 앞선 approved=[]·승인 POST 0 관측은 11월13일 승인 이전의 재전달이며 이후 승인·홈 실화면 확인은 완료됐다. 새 승인 상태 문제로 확대하지 않는다.

제품·검사·Plans.md 편집은 금지한다. 결과는 worker_done 메시지에 남기면 충분하고 별도 보고서를 만들 필요는 없다. 종료 시 편집 0·백그라운드 0을 명시한다.

## 변경과 기존 근거

조정자가 수정 전 기존 node ID를 실행해 availability의 과거 고정 해시 기대만 실패함을 확인했다. PC-LIVE의 bundle 계약 축 정렬은 이미 승인·수용된 제품 변경이므로 되돌리지 않는다.

구현자는 동일 함수 안에서 기존 odds 해시와 compose/provider 연결 단언을 유지하고, provider 구현 버전만 일시 대역으로 바꿀 때 odds는 달라지고 availability는 유지되는 관계 단언으로 바꿨다. 02:00 조정자가 현재 함수·아래 SHA256 일치·제품 manifest 무변경·구현자 EDITING STOPPED와 실제 빈 입력창을 확인했다.

- 검사 파일 현재 SHA256: c700e3d3505a1b999afdba202eba9007de925c4b9aa5d968a7146a52300c44da
- 제품 manifest 시작/현재 SHA256: d518c7a36e5ed6e87c464be0b87193787f5a7286273b0853a90387d08fdd570d
- 허용된 직접 실행: `env -u PREVIEW_TEST_DATABASE_URL .venv/bin/python -m pytest tests/preview/test_bundle_review_fixes.py::test_odds_workflow_version_changed_and_others_kept -q`
- 구현자 결과: 1 passed (0.38s). 같은 리비전의 이 근거를 재사용하고 재실행하지 않는다.
- 구현자는 허용 명령 외에 별도 일시 대역 값 확인과 파일 컴파일도 했다고 보고했다. 이 추가 실행은 필요 검증으로 요구하지 않았으므로 수용 근거에 더하지 않으며 반복하지 않는다. 제품 파일 변이·실제 DB·HTTP·모델·수집·브라우저 호출은 없다고 보고했다.

## 확인할 수용 기준과 종료 조건

1. 배당 제공자 버전 변경이 odds 승인 버전에 영향을 주고 무관한 availability에는 영향을 주지 않는다는 검사의 목적을 현재 코드 아래에서 실제로 검사하는가.
2. 과거 availability 해시에 대한 부적절한 고정을 제거하면서 odds 버전·구현 연결 단언을 보존했는가. skip/xfail·무조건 성공·제품 되돌리기로 통과시킨 것이 아닌가.
3. pytest의 대역이 검사 종료 후 복원되며 실제 DB fixture나 외부 호출을 새로 유발하지 않는가. 설명과 검사 의미가 현재 요구와 맞는가.

검사/브라우저/DB/API/모델/서버/전체 회귀·새 재현 코드·변이 실험을 실행하지 않는다. 한 번 읽기 확인하고 요구 위반 여부·정확한 리비전·근거 재사용·직접 편집/실행 0을 보고하면 종료한다. 참고 문구 개선을 반복 수정의 완료 조건으로 확대하지 않는다.
