# PC-LIVE 실제 승인 판정의 불일치 조사

작업 전에 `/Users/woolee/benchmark/.agents/skills/poteto-mode/SKILL.md` 전문을 읽고 적용한다. 같은 세션에서 읽고 미변경이면 해시 근거를 재사용한다. dsh-tui `deepseek-ai/deepseek-v4.1-flash-1017`/max 유지, 하위 워커·모델 전환 없음. 이번은 다음 수정 범위를 정하기 위한 읽기 조사이며 제품 구현이나 독립 검토가 아니다.

엔드포인트 구현은 별도 검토자가 현재 리비전으로 읽고 있으므로 **제품·검사·설정 파일을 수정하지 않는다.** 편집은 `docs/implementation/match-preview/preview-collection-admission-findings.md` 하나만 허용한다. 테스트/새 재현/인라인 Python/실제 DB/API/모델/서버/승인POST는 모두 하지 않는다. 코드를 읽고 아래 실제 관측과 대조한다.

## 조정자의 실제 읽기 관측 (2026-11-13 05:20~05:22 KST)

- 현재 API PID13279는 새 경로 미반영(openapi에 preview-test 없음). 기존 개발 런처 scripts/run_benchmark_dev.sh는 HOME_PREVIEW_ENABLED 기본값false이며 실행 시각을 바꾸지 않는다. 실제 프로세스 환경값은 아직 확인하지 않았다.
- 기존 ADMIN 클라이언트로 targets/두 fixture GET 모두200. target13 활성·EPL2026·상세/선수/순위true·fixture_limit=null, 두 경기 모두NS·2026-11-21T15:00:00Z다.
- GET /api/v1/admin/preview/admission: ready=false, missing_approval=[section_form,section_availability,section_outlook,section_players,section_synthesis], stale_approval=[].
- GET approvals: section_odds만 active이며 section_availability/outlook/players/ai_forecast는 pinned_approval이 있고 state=superseded. section_form/synthesis에는 승인 기록이 없다.
- 네 pinned 승인과 current_constituents는 조사 모델 모듈(R2/R3/R4/S1)의 contract_version이 승인 근거 mp04-section-result-1 대 현재 manifest mp02-1로 다르다. 표시된 implementation_version/prompt_version은 동일했다. 나머지 구성요소도 해당 GET에서 동일했다.
- 기존 다섯 승인 기록은 사용자가 저장 맨시티 문서를 승인한 근거로 이미 생성됐고 홈은 정확한 승인 근거를 사용한다. 승인 행을 추가/변경하거나 예외로 간주해 우회하지 않는다.
- pipeline.required_workflows는 section_form/availability/outlook/players/synthesis, version_manifest의 bundle 대상은 players/availability/outlook/odds/ai_forecast로 코드에 나타난다. 실제 공통 생성 서비스는 bundle_pipeline을 사용한다.

## 답할 질문과 종료 기준

1. 수집 승인 판정이 실제 생성할 bundle 섹션 집합과 일치하는가. 실제로 만들지 않는 form/synthesis를 요구하는 연결이 있다면 호출 근거와 최소 수정 위치를 제시한다.
2. 기존 승인 네 건의 contract_version 차이가 실제 결과 의미 변경인가, 같은 실행의 계약을 서로 다르게 계산한 것인가. 승인 근거·현재 생성 저장·version_manifest의 직접 계약만 대조하고 현재 승인 보존하에 해결 가능한 최소 변경을 설명한다. 이 조사를 새 승인으로 기록하지 않는다.
3. 새 명시적 시험 엔드포인트도 일반 home_preview_enabled=false에서 훅이 생략되는가. 요청별 시험 의도를 통해 작동하게 할 최소 위치와 정기 경로를 보존할 조건을 제시한다. 설정 파일/환경은 열거나 바꾸지 않는다.

보고서에는 확인 사실·추론·미확인을 구분하고 수정할 최소 파일과 사용자 승인 의미에 영향이 있는지를 적는다. 범용 승인 엔진·모든 경로 재설계·새 테스트 구현을 제안/실행하지 않는다. 같은 원인에 필요한 직접 호출 계약까지만 읽고 종료한다. 편집 종료·백그라운드0으로 새 Task/Dispatch에 한 번 보고한다. 오래된 메일/Task 복구를 하지 않는다.
