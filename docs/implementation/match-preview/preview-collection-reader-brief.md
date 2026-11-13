# PC-LIVE 실제 생성에서 확인한 조회기 전달 누락

작업 전 `/Users/woolee/benchmark/.agents/skills/poteto-mode/SKILL.md` 전문을 읽고 적용한다. 같은 세션에서 직접 읽었고 미변경이면 해시 근거로 재사용한다. 실제 dsh-tui 모델 `deepseek-ai/deepseek-v4.1-flash-1017`, 사용자 max 유지. 하위 워커·모델 전환·새 조정 Run 없음.

## 관측과 범위

실제 새 POST 1회는 종료됐다. 수집 실행 `0178213b-6cf8-4b38-a9d1-2554e4faeee1`, 수집 succeeded, 승인 ready, 두 생성 succeeded, failed/skipped 빈 배열이다. 첼시–리즈 새 실행 `e6a78cd9-a32e-4038-86a4-566634cf3845`, 토트넘–입스위치 `54c1b9ee-dc40-4f8d-8d89-b5533fc2b62a` 모두 live·5섹션·홈 complete=true다. 실제 수집은 기간 내 경기6개와 보조 자료를 처리했으며 원 실행은 보존한다.

그러나 실제 정보묶음 GET은 두 실행 모두 `db_snapshot.readable=false`, 경기 식별 coverage가 `not_run / 저장 경기 자료 읽기 연결이 설정되지 않았습니다.`, standings=[]다. 별도 선수 통계는 각각58/55행이며57/55행의 갱신시각이 이번 수집 이후다. 같은 첼시 경기의 이전 관리자 실행 `32cc0aa9-905d-4d89-85cd-90deef1bba9f`는 readable=true, 경기 식별·순위 available, standings2행이었다. 자료 없음이나 DB 전체 장애가 아니라 수집 호출의 reader 전달 누락이다.

코드 사실: management 종료 훅은 reader를 전달하지 않는다. 공통 생성 서비스는 resolve_stored_fixture에서 설정으로 조회기를 열어 경기 ID를 해석하고 닫지만, 다음 run_bundle_pipeline에는 원래 reader=None을 전달한다. 조정자는 구현 코드를 작성하지 않는다. 이 연결의 수명·소유권을 구현자가 최소 범위에서 바로잡는다.

## 소유권과 수용 기준

- 제품 소유: `app/services/match_preview.py`. 기존 공통 서비스 안에서 설정 기반 조회기를 쓰는 기본 호출과 명시 주입 호출을 일관되게 연결한다. 다른 제품 파일 수정이 필요하면 이유와 최소 범위를 보고한다.
- 검사 소유: 새 `tests/unit/test_match_preview_reader.py`.
- 보고서: `docs/implementation/match-preview/preview-collection-reader-report.md`.
- 기존 관리/수집/runner/승인/manifest/프롬프트/모델/본문 스키마/프론트/설정/Plans.md는 수정하지 않는다. 별도 이름 해석기의 register_model_labels 진단은 이번 범위가 아니다.

수용할 결과:

1. reader를 생략한 실제 수집의 기본 호출에서도 저장 경기 해석과 본문 자료 준비가 같은 유효한 읽기 조회기를 사용한다. 모델 호출 단계에 None이나 이미 닫힌 조회기가 전달되지 않는다.
2. 서비스가 연 조회기는 성공/해석 오류/생성 오류에서 정리한다. 호출자가 주입한 조회기는 호출자 소유권을 유지한다. 새 연결 풀·조회 엔진·범용 수명 관리기를 추가하지 않는다.
3. 저장 경기 읽기 불가·미설정 시 기존 명확한 오류를 유지하고 모델을 보내지 않는다. 시스템 actor·회차 label·생성 엔진·승인 정책을 바꾸지 않는다.
4. 실제 공통 생성 함수를 호출하는 대표 합성 검사에서 다음 단계가 조회기를 실제 사용할 수 있고 닫힘 순서가 올바른지 확인한다. 단순 kwargs 동일성 검사만으로 종료하지 않는다. 검사 이유는 이번처럼 수집된 순위 자료가 생성 입력에서 빠지는 문제를 잡는 것이다.

직접 명령: `.venv/bin/python -m pytest tests/unit/test_match_preview_reader.py tests/unit/test_home_preview_collection.py tests/unit/test_management_preview_test.py -q`. 외부 DB·HTTP·모델을 대역 처리한다. 이 명령이 통과하면 종료한다. 전체 회귀·변이/원복 실험·새 인라인 재현·실제 DB/API/모델/서버/승인POST/마이그레이션은 금지한다. 원 실행과 승인·저장 본문을 수정하지 않는다.

최종 변경·리비전·직접 명령 결과·미확인·적용 원칙을 보고하고 EDITING STOPPED·백그라운드0으로 종료한다. 실제 자료 읽기 재확인과 새 기간 수집 요청은 독립 한정 확인 뒤 조정자가 수행한다. 이번은 수집 입력 연결 결함 수정이며 후속 본문 구조화 작업을 시작하는 것이 아니다.
