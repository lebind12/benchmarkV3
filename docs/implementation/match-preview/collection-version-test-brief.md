# PC-VERSION-TEST — 승인 계약 축 변경 후 기존 검사 정합성

작업 전 `/Users/woolee/benchmark/.agents/skills/poteto-mode/SKILL.md` 전문을 읽고 적용한다. 같은 세션에서 전문을 읽었고 내용이 그대로면 읽기 근거와 변경 없음 확인을 재사용한다. 필요한 원칙만 추가로 읽고, 실제 모델과 적용 원칙을 착수 보고에 남긴다.

## 역할과 소유권

DeepSeek 구현 작업이다. 현재 `deepseek-ai/deepseek-v4.1-flash-1017`, 사용자 max 설정을 유지한다. 모델 전환·하위 워커·새 조정 Run은 없다.

수정 소유권은 `tests/preview/test_bundle_review_fixes.py`의 `test_odds_workflow_version_changed_and_others_kept` 하나다. 보고는 완료 메시지로 충분하며 별도 보고서·Plans.md·제품 파일을 수정하지 않는다. 기존 파일 전체가 Git untracked 상태이므로 다른 검사와 이전 작업을 반드시 보존한다. 원 소유 세션의 EDITING STOPPED 및 현재 빈 입력창을 조정자가 확인했다.

## 재현된 문제와 유지할 결정

2026-11-14 조정자가 아래 기존 검사만 실행해 1 failed를 확인했다. section_odds 기대값은 맞고 section_availability의 과거 고정값만 실패했다.

- 과거 기대값: section_availability@643296ca23b42faf
- 현재 실제값: section_availability@7dc7fec4ec7919ac
- 원인: PC-LIVE에서 bundle 계약 축을 저장과 같은 mp04-section-result-1로 맞춘 승인된 변경. 전역 mp02-1로 되돌리지 않는다.
- 관련 근거: `preview-collection-endpoint-review.md`의 여섯 연결 보완 수용, `pf-latest-odds-review.md`의 2026-11-14 재확인 절.
- 시작 SHA256: 검사 파일 5f3b68a2e8c00686dc5577b1cd96e4c833ac118ddb4ca234e0bdcb6248886606; version_manifest.py d518c7a36e5ed6e87c464be0b87193787f5a7286273b0853a90387d08fdd570d.

## 수용 기준

기존 검사의 목적은 배당 제공자 구현 버전이 배당 승인 버전에 반영되며, 그 배당 변경만으로 무관한 availability 버전이 바뀌지 않는 것이다. 합법적인 공통 계약 축 변경까지 과거 해시에 묶지 않도록 이 목적을 현재 계약 아래에서 검증한다. 단순 단언 삭제, 무조건 성공, skip/xfail, 제품을 옛 계약으로 되돌리는 방법은 허용하지 않는다. 기존 배당 버전 및 제공자 구현 버전 연결 확인을 유지한다. 검사 내부의 일시적인 대역은 가능하지만 제품 파일을 고쳤다 되돌리는 변이 실험은 하지 않는다.

검사 설명과 실제 단언의 의미를 맞추고 위 함수 범위만 최소 수정한다. 실제 프리뷰 생성·저장·승인·표시 동작은 변경하지 않는다.

## 검증과 종료

허용 명령은 다음 기존 node ID 하나이며 수정 후 한 번 실행한다. 실패하면 같은 원인의 최소 수정 후 재실행할 수 있다.

`env -u PREVIEW_TEST_DATABASE_URL .venv/bin/python -m pytest tests/preview/test_bundle_review_fixes.py::test_odds_workflow_version_changed_and_others_kept -q`

이 검사는 DB fixture를 요청하지 않는 순수 계산 검사다. conftest의 기본 loopback 시험 URL은 문자열 안전 검사만 지나며 engine/schema fixture를 쓰지 않는다. 파일 전체·전체 회귀·실제 DB·HTTP·모델·수집·브라우저·서버 재시작·승인 POST·마이그레이션·환경 비밀 탐색은 금지한다. 새 재현 스크립트/검증 도구를 만들지 않는다.

완료 보고에는 변경 의미, 정확한 명령/결과, 변경 후 검사 파일 SHA256, 제품 manifest의 시작 SHA256 유지 여부, 수정 함수 밖 보존, EDITING STOPPED와 백그라운드 0을 남긴다. 인계 후 별도 DeepSeek가 이 함수의 요구 충족과 근거만 읽기 검토한다. 지나간 메일·Task 복구를 시작하지 않는다.
