# PC-LIVE 시험 엔드포인트 한정 독립 확인

작업 전에 `/Users/woolee/benchmark/.agents/skills/poteto-mode/SKILL.md` 전문을 읽고 적용한다. 같은 세션에서 직접 읽었고 미변경이면 해시 근거로 재사용한다. dsh-tui의 실제 `deepseek-ai/deepseek-v4.1-flash-1017`/max를 유지하고 모델 전환·하위 워커·새 Run은 만들지 않는다. 모델·스킬 로딩 근거·읽기 전용 범위와 적용 원칙을 착수 보고한다.

사용자 요청은 실제 새 엔드포인트→기간 수집→지정 두 경기만6시간 조건 예외→실제 생성 연결이다. 앞선 별도 시험 프로세스와 가상 시각은 폐기됐다. 구현 task_3954f06466ab·ctx_d152dfe2a692는 완료·편집 종료·백그라운드0을 보고했고 조정자가 실제 두 터미널의 모델과 빈 입력을 확인했다.

## 입력·소유권

- 설계: `docs/superpowers/specs/2026-11-13-preview-collection-test-endpoint-design.md`
- 계획: `docs/superpowers/plans/2026-11-13-preview-collection-test-endpoint.md`
- 인계: `docs/implementation/match-preview/preview-collection-endpoint-report.md`
- 편집 허용은 새 `docs/implementation/match-preview/preview-collection-endpoint-review.md` 하나다. 제품·검사·설정·Plans.md는 읽기 전용이다.

현재 리비전 SHA256:

| 파일 | SHA256 |
|---|---|
| app/api/v1/management.py | 7fbe177266a304de31d33ba2cf6693eaaef9c9672c07c60239a9c4829917e910 |
| app/services/management_runs.py | 683fa931880fa8144c0a228087c76bb2a739720183cf719c24a37132643c6d41 |
| app/workers/daily_sync/runner.py | 39a8df6210ab850e7e78c5d6d967fc4dae81b95ae6530d32fa9ae083ab40798d |
| app/services/collection_test_scope.py | 5af19812d450fdd872867693e6607daf8b07f187b348522213fd9e58f5c09f1c |
| app/services/home_preview_collection.py | 5ad2b2c8b806f422fb9a3bbda8aa2ed4bb8dbff7d74f2d28f44528ba059a423e |
| tests/unit/test_management_preview_test.py | 28603f836428094cdd79c2c1b72b958fe2e0addba9684e3219eaac95c39d602e |
| tests/unit/test_home_preview_collection.py | 5cbabe8837d0c5524075c0499f4d741eb20596e9c9051c41c4efce59e3bf97c3 |

## 확인할 수용 기준

1. **실제 요청 경계:** POST /api/v1/admin/management/runs/preview-test가 기존 인증과 작업 실행기에 연결되는가. 시간대·순서·정확히 두 양수 ID·중복 검증뿐 아니라 선택한 대상/시즌/기간에 속하는 미래 NS 경기인지 수집/모델 호출 전에 확인하는가. 수집 뒤 일정/상태가 달라지면 명확한 제외 사유를 남기는가.
2. **기간의 실제 효력:** 요청 범위가 측정→fixture_external_ids→경기 저장·상세 수집까지 전달되는가. 출력만 필터링하지 않는가. 기간 밖 경기 처리와 시험에 불필요한 시즌 정리가 없고 전체 시즌 완료로 기록하지 않는가. 보조 팀/선수/순위 수집의 리그 범위는 이미 허용된 한계다.
3. **두 경기 한정 예외:** 현재 실제 시각의6시간 밖 두 ID만 생성 대상이 되는가. 기간·대상 범위와 NS/미래/승인 조건은 유지되는가. 일반 수집/정기 경로와 미지정 경기에는 예외가 새지 않는가. 기본 인자의 존재만이 아니라 실제 후보 결과를 근거로 확인한다.
4. **종료 훅과 결과:** 한 요청의 범위·실행 ID가 정상/실패 종료 훅까지 이어지고 기존 생성 서비스로 두 경기를 처리하는가. 원래 수집 상태·취소·경기별 실패 격리·FAILED 분류·승인 게이트를 보존하는가. 각 프리뷰 실행 ID로 추적할 수 있는가.
5. **중복과 기존 동작:** 시험 키는 수집 실행ID+경기ID이며 정기 회차를 소모하지 않는가. 기존 관리자 문서가 시험 생성을 막지 않는가. 이미 수용한 PC-CONNECT 전체를 새로 재검토하지 말고 이번 변경의 직접 영향만 확인한다.

검사 누락이 있으면 어느 수용 결과가 검증되지 않았는지 적는다. 현재 범위의 실제 결함/요구 위반/참고 개선을 분리하고, 임의 환경·미래 확장을 차단 조건으로 추가하지 않는다.

## 명령·종료

허용 명령은 `.venv/bin/python -m pytest tests/unit/test_management_preview_test.py tests/unit/test_home_preview_collection.py -q` 1회다. 이전22와 합산하지 않는다. 합성 대역 통과를 실제 API/DB/모델 성공으로 인용하지 않는다.

새 테스트·스크립트·인라인 Python 재현·제품 치환·변이 실험·설정 교체·stash/원복·전체 회귀는 금지한다. 실제 DB·외부 HTTP·모델·수집·브라우저·서버·승인POST·마이그레이션도 하지 않는다. 지정 소스·검사·직접 명령을 근거로 보고한다.

보고서에 요구별 판정·위치·직접 검사 결과·실제 호출 전 막힌 점을 남긴다. 같은 현재 리비전을 반복 검사하지 않는다. worker_done에 수용/현재 위반과 EDITING STOPPED·백그라운드0을 한 번 보고하고 종료한다. 과거 Dispatch·메일 복구 작업을 시작하지 않는다.
