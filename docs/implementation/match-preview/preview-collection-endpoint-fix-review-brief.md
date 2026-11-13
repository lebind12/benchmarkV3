# PC-LIVE 여섯 연결 보완의 한정 수정 확인

먼저 `/Users/woolee/benchmark/.agents/skills/poteto-mode/SKILL.md` 전문을 읽고 적용한다. 같은 세션에서 직접 읽었고 미변경이면 해시로 재사용한다. 실제 dsh-tui `deepseek-ai/deepseek-v4.1-flash-1017`/max를 유지한다. 모델 전환·하위 워커·새 Run 없음. 착수 시 모델·스킬 로딩 근거·원칙·읽기 전용 범위를 보고한다.

이번은 이미 검토한 시험 엔드포인트의 수정 확인이다. 최초 전체 검토를 반복하지 않는다. 구현 task_d6801dc4a3c4·ctx_a421b12be0a3의 완료·편집 종료·백그라운드0을 받고 현재 터미널의 모델과 빈 입력을 확인했다. 실제 POST는 조정자가 이후 한 번 실행한다.

## 입력과 편집 범위

- 요구: `preview-collection-endpoint-fix-brief.md`의 여섯 결과.
- 구현: `preview-collection-endpoint-report.md`의 05:35 보완 절, 합성66 passed.
- 실제 근거: `preview-collection-live-evidence.md`, `preview-collection-admission-findings.md`.
- 편집은 기존 `preview-collection-endpoint-review.md`에 한정 수정 확인 절 추가만 허용한다. 제품·검사·설정·Plans.md는 읽기 전용이다.

05:37 KST 현재 SHA256:

| 파일 | SHA256 |
|---|---|
| app/services/management_runs.py | f560511b8962932f7d59b68618760272ce0e19c57e7d3a3565b44d06ee18690d |
| app/services/home_preview_collection.py | e58adfeb7efa43093e252b9fe510b59f76f075c67822c50733f2f03974bfcec1 |
| app/preview/pipeline.py | dbf65a50e2617cf6107d1dc513f6b5f6ed0af01244fbbc6fbf366ee18d2c27c8 |
| app/preview/version_manifest.py | d518c7a36e5ed6e87c464be0b87193787f5a7286273b0853a90387d08fdd570d |
| tests/unit/test_management_preview_test.py | 940d41dc377b41ad3a6289baa4f4484f4273950704b237e197028e5d482f341f |
| tests/unit/test_home_preview_collection.py | 730809e1ee05abe6e1c2509ae551d665103efd9bd6fba4b371a9c5ca06ee53f7 |
| tests/unit/test_bundle_collection_admission.py | 4189c993326aea6db0423f1e53d60931e9df53b75cb96b9d5582e4146a0fcff9 |

## 여섯 항목의 수용 판정

1. 두 외부 경기 ID가 요청 대상의 리그/시즌·기간·미래NS에 속하는지 접수 전 실제 저장 모델 관계로 검사하는가. 리그 내부/외부 ID 공간을 대역 모양만으로 판단하지 않는다. 틀린 입력은 작업/외부 호출 전에422인가.
2. 수집 후 제외된 지정 경기의 ID/사유가 남고 생성 직전에도 기간을 존중하는가. 6시간 안/밖 모두 해당하며 다른 경기로 대체하지 않는가. 기존 지적 범위의 구현을 확인한다.
3. 명시적 시험은 전역 플래그false에서도 정상/예외 훅에 한 번 도달하고 일반 경로·취소는 보존되는가. 새 연결 검사가 실제 execute_run→실제 종료 훅→실제 생성 경계를 지나는가.
4. 시험에서 prune_league_seasons를 호출하지 않는가. 최초 보고서의 “시즌 정리 없음” 판정은 당시 코드의 성공 분기에서 무조건 호출한 사실과 달랐으므로 해당 설명을 정정한다. 새 검사는 target 객체가 있고 succeeded인 경로에 도달해 미호출을 확인하는가.
5. 수집 승인 판정은 실제 information_bundle.SECTION_IDS와 같은 출처를 쓰고 옛 admission_state의 의미는 보존하는가. form/synthesis를 요구하지 않고 odds/ai_forecast를 빠뜨리지 않는가. 기존 승인 없거나 실제 버전이 다르면 계속 차단하는가.
6. bundle 모듈의 실제 저장 계약과 manifest가 같고 D0/compose/옛 경로는 보존되는가. 승인 행을 만들거나 고치거나 ready를 강제하지 않는가. 현재 승인과 정확히 같은 구성의 비교 오류를 고치는 일과 의미 변경을 새로 승인하는 일을 구분한다.

현재 변경이 만든 직접 회귀·위 필수 조건의 실제 실패만 추가 차단으로 보고한다. 새 정책·미지원환경·범용 보강을 끌어오지 않는다. 구현이 명백히 위 조건을 충족하면 종료하고 같은 검사를 반복하지 않는다.

## 검증·종료

허용 명령1회: `.venv/bin/python -m pytest tests/unit/test_management_preview_test.py tests/unit/test_home_preview_collection.py tests/unit/test_bundle_collection_admission.py tests/unit/test_home_preview_document.py -q`.

제품 수정·새 테스트/스크립트·인라인 재현·변이 실험·코드 치환·stash/원복·전체 회귀는 하지 않는다. 실제 DB·외부 API·모델·브라우저·서버·승인POST·마이그레이션도 호출하지 않는다. 합성 결과를 실제 수집 성공으로 보고하지 않는다.

보고서에 여섯 결과의 해결/미해결과 근거 위치·실행 결과·실제 확인이 남은 점을 남긴다. worker_done으로 수용 여부와 EDITING STOPPED·백그라운드0을 한 번 보고한다. 과거 Dispatch 복구·추가 메일/Task 탐색 없이 종료한다.
