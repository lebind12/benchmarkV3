# MP-05 완료 보고: 경기력·주목 선수 섹션(R1)과 이번 wave 통합

**목표.** 사용자가 저장된 경기를 고르고 `section_form` 섹션 워크플로우를 실행해,
자료 준비(D0 성격)→R1 조사→본문 조립까지 거친 **읽을 수 있는 한국어 본문과 근거**를
확인하고, 그 결과를 근거로 섹션 버전을 승인할 수 있게 한다. 내부 조사 모듈 하나만
동작하는 상태를 완료로 보지 않는다.

**한 줄 결론.** `section_form`이 실제 모델 1회 호출로 저장 경기 한 건
(Manchester City vs Fulham, fixture_id 1557474)의 본문·근거를 만들어 `preview_dev`에
남겼고, 관리자 화면에서 경기 선택→섹션 실행→본문·근거 확인→(사용자) 승인 흐름이
동작한다. 승인은 **만들지 않았다**. 사용자가 화면에서 직접 눌러야 한다.

## 실행 모델 (확인 근거)

| 항목 | 값 | 확인 방법 |
|---|---|---|
| 제공자 / 모델 | hive / `deepseek-ai/deepseek-v4.1-flash-1017` | 세션 로그 `model/selection` 레코드(`provider=hive`, `model=deepseek-ai/deepseek-v4.1-flash-1017`) |
| 추론 강도 | `max` (사용자 설정 유지) | 같은 레코드의 `reasoningEffort: "max"` |
| 프로필 | `dsh-tui` | `DSH_PROFILE=dsh-tui`, `DSH_SESSION_ID=f138c9e6-…` |
| 작업 디렉터리 | `/Users/woolee/benchmark` | CWD |
| 작업 ID / Dispatch | task_37c2999e7394 / ctx_cbbd679659d0 | 배정 프리앰블 |
| 하위 워커 | **없음** | 작업 지시(no subworkers) 준수 |
| 모델·설정 변경 | **없음** | 설정 파일을 수정하지 않았다 |

## 소유·편집한 경로

이번 wave의 **유일한 스테이징·커밋 담당**이다. MP-06/07은 각자 파일만 편집하고
편집 종료를 알렸으며, 그 인계를 받아 아래에 함께 스테이징한다(§8).

### 내가 작성한 공통·R1 파일

| 경로 | 내용 |
|---|---|
| `app/preview/modules/__init__.py` | 구현된 모듈 버전 표(`R1`·`R2`·`R3`), 미구현 모듈을 실행 가능으로 꾸미지 않음 |
| `app/preview/modules/form.py` | `research_form`(정상 호출 1회), grounding 해석, 근거 검증, `form_node` 노드 어댑터 |
| `app/preview/modules/compose.py` | 결정적 본문 조립(두 번째 모델 호출 없음), 모델 라벨 정리 |
| `app/preview/prompts/form.md` | R1 프롬프트(사실/해석 분리, URL 창작 금지, 7일 기준) |
| `app/preview/sections.py` | **실제 섹션 팩토리**(form/availability/outlook), 저장 자료 재사용 `prepare_data`, `recompose_section_body`(외부 호출 0회 재조립) |
| `app/preview/registry.py` | R1/R2/R3 실제 등록(`implemented=True`), `section_form`/`section_availability`/`section_outlook` 구현 표시 |
| `app/preview/provider.py` | `sent_attempt_count`(전송된 시도만 셈, 실패·재시도 포함, 모의·재생 제외) |
| `app/api/v1/preview_admin.py` | `/sections`, `/section-runs` 의 실제 실행 경로(live는 구현·설정·경기 식별 필요), live 미설정 422 |
| `frontend/src/features/match-preview/panels/FormPanel.vue` + `.test.ts` | 사실·해석·출처·제외 사유 분리 표시 |
| `frontend/src/features/match-preview/SectionRunView.vue` + `.test.ts` | **경기 선택→섹션 선택→실행→본문·근거→사용자 승인** 화면 |
| `frontend/src/router/index.ts` | `/admin/sections` 라우트 |
| `frontend/src/features/match-preview/api.ts`, `types.ts` | 섹션 실행 요청의 경기 식별자, `availability.model` |
| `frontend/src/features/match-preview/RunInspector.vue` | R1/R2/R3 전용 패널 연결, 본문 우선 유지 |
| `frontend/src/features/match-preview/PreviewRunsView.vue` | 상단 내비에 "섹션 실행" |
| `tests/preview/test_form_module.py` | R1 수용 기준 + 섹션 통합 검사 |
| `tests/preview/fixtures/form.json` | R1 기록 응답·grounding 모양(검사용) |
| `tests/preview/test_module_runner.py`, `test_inspection_api.py` | 등록부가 R1/R2/R3 구현을 반영하도록 기존 기대값 갱신 |
| `scripts/preview_section_live_run.py` | 실제 실행 1회 스크립트(승인 행을 만들지 않음) |
| `frontend/scripts/mp05-section-browser-check.mts` | 실제 Chromium 확인 스크립트 |
| `docs/implementation/match-preview/evidence/mp05/` | live 실행 요약 JSON, 브라우저 결과 JSON·스크린샷 |

### 인계받아 함께 스테이징하는 파일(MP-06/MP-07 작성)

| 경로 | 작성자 |
|---|---|
| `app/preview/modules/availability.py`, `app/preview/prompts/availability.md` | MP-06 |
| `tests/preview/test_availability_module.py`, `tests/preview/fixtures/availability.json` | MP-06 |
| `frontend/src/features/match-preview/panels/AvailabilityPanel.vue` + `.test.ts` | MP-06 |
| `docs/implementation/match-preview/MP-06-report.md`, `evidence/mp06/recorded-section-availability.json` | MP-06 |
| `app/preview/modules/outlook.py`, `app/preview/prompts/outlook.md` | MP-07 |
| `tests/preview/test_outlook_module.py`, `tests/preview/fixtures/outlook.json` | MP-07 |
| `frontend/src/features/match-preview/panels/OutlookPanel.vue` + `.test.ts` | MP-07 |
| `docs/implementation/match-preview/MP-07-report.md`, `evidence/mp07/commands.txt`, `evidence/mp07/section-workflow-mock.json` | MP-07 |

**인계 후 내가 한 수정:** `provider.sent_attempt_count` 도입에 맞춰
`modules/outlook.py`의 외부 호출 계산을 공통 함수로 바꾸고(성공 여부가 아니라 전송된
시도 수), `test_outlook_module.py`의 recorded transport 표기를 `live`/`mock`으로
명시해 검사 의미를 실제 전송과 맞췄다. R3의 조사·검증·본문 로직은 손대지 않았다.

## 1. R1 모듈 (수용 기준별 근거)

| 수용 기준 | 구현 | 검사 |
|---|---|---|
| 근거 있는 사실·해석·관전 포인트·주목 선수 | `validate_response`가 항목별 채택/제외와 사유를 남긴다 | `test_form_claims_reference_sources` |
| 다음 단계로 정확한 출처 ID 전달 | `FormResearch.source_ids`(snapshot + 실제 URL)가 payload·`ModuleInput.snapshot_ids`로 이어진다 | 같은 검사에서 `payload["source_ids"]` 일치 확인 |
| 오래된 경기 소식 제외 | 킥오프 7일 이전 보도는 최근 흐름에서 제외, 사유 기록 | `test_old_match_news_excluded` |
| 근거 없는 선수 단정 금지 | "리그 최고" 등 단정 표현에 `superlative_basis` 요구, 없으면 제외 | `test_player_claim_without_evidence_rejected` |
| API 사실만으로도 결과 생성 | 검색 출처 0이어도 API 사실로 본문 생성, 검색 미확보는 진단에만 | `test_api_facts_remain_without_search` |
| 매체·맥락 검색 강제 | API 자료 유무와 무관하게 `tools=[{google_search:{}}]` | `test_one_normal_call_only`(요청 설정 확인) |
| grounding 보존 | 질의·출처·supports·Search Suggestions 보존, 링크 ≠ 원문 확인 | `test_grounding_metadata_preserved` |
| 정상 호출 1회 | `request_model` 1회, 예산 `model_used=1` | `test_one_normal_call_only` |
| 독자용 본문에 진단 없음 | 누락·실패·재시도 문구 미포함, JSON 붙이지 않음 | `test_body_has_no_diagnostics_and_is_reader_facing` |
| 모의 결과는 승인 불가 | 모의 섹션 결과 승인 시 `ApprovalRequestError` | `test_mock_section_result_cannot_be_approved` |
| 사용자 승인 경로 | 실제 결과에만 승인 행 생성 | `test_section_form_end_to_end_body_sources_then_user_approval` |

## 2. 실제(live) 실행 1회 — 사용자 검토용 결과

- 스크립트: `scripts/preview_section_live_run.py --fixture-id 1557474`
- 설정: 기존 배포와 같은 값(`gemini-3.5-flash`, `global`,
  `project-bde7516a-98dc-40f5-92e`), `PREVIEW_MODEL_LIVE_ENABLED=1`. **대체 모델 없음.**
- 실행: `run_id=6e59041a-3767-4756-a412-991008873f50`,
  `mode=live`, `status=succeeded`, `quality=ready`, `external_calls=1`,
  시도 1회(`outcome=ok`, `http_status=200`, `model=gemini-3.5-flash`),
  사용량 `input_tokens=1340`, `output_tokens=2954`(제공자 보고값).
- 예산: `model_used=1 / 8`, `api_used=0 / 24`, 재시도 없음.
- 근거: 저장 API 자료 스냅샷 1건. 검색 grounding은 **질의 8건**이 실행됐지만
  `grounding_chunks`가 **0건**이었다(제공자가 인용 출처를 반환하지 않음).
- 섹션 결과: v1(502자) → v2(454자) → v3(442자). v2·v3은 **외부 호출 0회**
  `recompose_section_body`로 문장 조립 규칙만 다시 적용한 결과다(같은 실행의
  저장 조사 결과를 입력으로 씀, 새 근거 없음).

현재 최신 본문(저장본 v3 그대로):

```
Manchester City와 Fulham의 맞대결입니다. Premier League 경기이며, 킥오프는 2026-11-21 12:30 UTC입니다.

맨체스터 시티는 현재 리그 3위(승점 21점)이며, 풀럼은 리그 15위(승점 10점)에 머물러 있습니다. AI 해석으로는, 맨체스터 시티는 선두권 경쟁을 유지하기 위해, 풀럼은 강등권과의 격차를 벌리기 위해 승점 확보가 절실한 경기입니다.

Manchester City는 최근 5경기에서 2승 3패(LLLWW)를 기록하며 리그 3위에 위치해 있습니다. AI 해석으로는, 최근 연패 흐름을 끊고 2연승을 거두며 분위기 반전에 성공한 상태입니다. Fulham는 최근 5경기에서 2승 2무 1패(DDWWL)를 기록하며 리그 15위에 위치해 있습니다. AI 해석으로는, 패배가 적은 편이나 무승부가 많아 승점 쌓기가 더딘 흐름을 보이고 있습니다.
```

### 이 결과의 한계 (사용자가 알아야 하는 것)

1. **관전 포인트·주목 선수는 채택되지 않았다.** 모델은 3개 관전 포인트와 3명
   (Haaland·Iwobi·Munuiz)을 제시했지만, 근거로 든 값이 **검색 인용 URL**이었고
   이번 응답에는 `grounding_chunks`가 없었다. 그래서 `validate_response`가
   "근거 식별자(snapshot 또는 검색 출처 URL)가 없어 채택하지 않았습니다"로 제외했다.
   **창작을 막은 결과이며, 조사가 부족했다는 사실 그대로다.**
2. **본문이 리그 순위·최근 폼 수준에 머문다.** 채택된 근거가 저장 순위 자료뿐이라
   선수 단위 사실(출전 기록·부상)은 들어가지 않았다. `public.player`,
   `public.player_season_stat`은 승인된 읽기 경계 밖이다.
3. 검색 질의는 실행됐으나 인용 출처가 없어 `매체·맥락 검색` coverage는
   `unknown`(질의는 있었지만 인용 없음)으로 남았다. `search_not_found`와 구분했다.

## 3. 사용자 테스트 단위(섹션 워크플로우) 화면

`/admin/sections`(신규)에서 한 화면에서 끝난다.

1. 저장된 경기 목록에서 경기 선택(외부 호출 0회, 읽기 전용 좁은 역할)
2. 섹션 선택(실제 구현 여부 표시, 미구현 섹션은 live 옵션 비활성)
3. 실행(mock/live 표시), 실행 후 **본문·근거 먼저** 표시
4. 모의 결과면 승인 버튼을 열지 않고 이유 표시
5. 실제 결과면 사용자가 승인 버튼을 눌러야만 승인 행 생성
6. "실행 검사 화면에서 진단 보기"로 R1 전용 패널(사실/해석/제외 사유/검색 상태)

## 4. 실행한 명령과 결과

```
PREVIEW_TEST_DATABASE_URL=…/preview_mp05_test .venv/bin/python -m pytest tests/preview -q -p no:cacheprovider
  → 296 passed (전체 백엔드 프리뷰 검사)

PREVIEW_TEST_DATABASE_URL=…/preview_mp05_test .venv/bin/python -m pytest tests/preview/test_form_module.py -q
  → 15 passed

npm --prefix frontend run test:unit
  → 12 files, 81 tests passed

npm --prefix frontend run type-check
  → 통과(출력 없음)

npm --prefix frontend run build
  → ✓ built (SectionRunView 청크 포함)

.venv/bin/python scripts/preview_section_live_run.py --fixture-id 1557474 --dry-run
  → model: gemini-3.5-flash | live_enabled: True | fixtures_reader: set | fixture 확인

.venv/bin/python scripts/preview_section_live_run.py --fixture-id 1557474 --json-out …
  → mode=live, external_calls=1, attempt 1회, 본문 저장

npx tsx frontend/scripts/mp05-section-browser-check.mts   (격리 백엔드 8022 · 프론트 5181)
  → 12/12 통과 (아래 표)
```

### 브라우저 확인 (실제 Chromium, 격리 환경)

증거: `evidence/mp05/browser/browser-checks.json`, 스크린샷 `01`~`04`.

| 항목 | 결과 |
|---|---|
| 합성 관리자 로그인 | 통과 |
| `/sections` API가 `section_form.real_generation_available=true` | 통과 |
| 섹션 목록이 모델 설정 상태를 함께 제공 | 통과(`configured=false`: 격리 백엔드에는 모델 설정을 넣지 않았다) |
| 저장 경기 목록 렌더 | **50행** |
| 경기 목록 조회 외부 호출 | **0회** |
| 경기 선택 → 선택 표시 | 통과(fixture_id 1557474) |
| 실행 전 결과 영역 없음 | 통과 |
| 실행 후 본문 표시 | 통과 |
| 실행 방식 표시(mock) | 통과 |
| 근거 영역 표시 | 통과 |
| 모의 결과는 승인 버튼 없음 + 불가 사유 표시 | 통과 |
| 실행 검사 화면의 R1 전용 진단 패널 | 통과 |

격리 환경은 `preview_mp05_ui_test`(루프백 전용)와 합성 계정
`mp02-ui-admin@example.test`를 썼다. 사용자 계정·운영 자료를 바꾸지 않았다.
확인이 끝난 뒤 격리 서버(8022·5181)는 종료했고, 사용자 프로세스(8000·5173)는
건드리지 않았다(종료 후에도 200 확인).

## 5. 공통 계약 변경 (동결 계약을 임의로 바꾸지 않음)

- `app/preview/contracts.py`는 **수정하지 않았다.** SectionResult/ModuleResult/
  ModuleInput/ExecutionContext/request_model/execute_request 그대로 쓴다.
- 추가한 것은 `provider.sent_attempt_count(result, transport_mode)` 하나다.
  "실제로 전송된 시도만 외부 호출로 센다"는 규칙을 한 곳에 두어 R1/R3가 같은 기준을
  쓴다. 실패·재시도한 시도는 세고, 모의·재생 transport와 설정 부족 시도는 세지 않는다.
- `registry.py`의 R1/R2/R3 등록과 섹션 워크플로우 `implemented` 값은 실제 구현 상태와
  일치하도록 갱신했다. **S1과 D0는 여전히 `implemented=False`**다.
- 세 마이그레이션·스키마 변경 없음.

## 6. 데이터 경계

- 기존 운영 자료(경기·계정)는 **읽기 전용**으로만 읽었다
  (`preview_dev_fixture_ro`). 기존 행을 수정·삭제하지 않았다.
- 새 쓰기는 `preview_dev` 스키마의 이번 실행 기록(run·모듈 실행·시도 1·원문·결과·
  섹션 결과 3버전)뿐이다.
- 격리 UI 확인용 쓰기는 루프백 테스트 DB `preview_mp05_ui_test`에만 있었다.
- 비밀값(서비스 계정 JSON, API-Football 키)은 출력·보고서·아티팩트에 넣지 않았다.
  원문 아티팩트는 기존 가림 경로를 지난다.
- API-Football **실호출 0회**. 저장된 자료를 읽기 전용으로 재사용했다.
  API-Football 보완 수집은 이번 범위에서 필요하지 않아 연결하지 않았다.

## 7. 하지 않은 것 / 남은 것

| 항목 | 상태 |
|---|---|
| 사용자 승인 | **없음.** 승인 행을 만들지 않았다. 화면에서 사용자가 눌러야 한다 |
| 실제 조사 품질(관전 포인트·주목 선수) | **미달.** 검색 인용 출처 0건으로 선수·관전 항목이 전부 제외됐다 |
| 순위·폼 외 자료(선수 기록·부상 명단) | 읽기 권한 밖(`public.player*`). 필요하면 읽기 경계 승인 필요 |
| 검색 인용 출처 확보 | 제공자가 `grounding_chunks`를 주지 않았다. 재시도·프롬프트 반복은 하지 않았다 |
| 섹션 재실행으로 품질 개선 | **하지 않았다.** 1회 실행 승인 범위를 지켰다 |
| S1 종합·전체 프리뷰 | 미구현(`implemented=False`). 이번 범위 아님 |
| R2/R3 live 실행 | **없음.** 두 모듈은 기록 응답 기반 검사만 통과했다(각자 보고서 참조) |
| 운영 DB 대상 live 섹션 실행 | 이 실행은 `preview_dev`(개발)`environment=dev`다 |
| 공유 서버 재시작 | **조정자에게 요청함.** 내가 8000/5173을 재시작하지 않았다 |
| 배포·푸시·환경 변수 변경 | 없음 |

## 8. 커밋

경로 한정 스테이징·커밋만 했다. `git add -A`/`.`/`--amend`/`reset`/`restore`/
`rebase`/`clean`을 쓰지 않았고, 기존 808건 삭제는 그대로 미스테이징으로 남아 있다.

| 항목 | 값 |
|---|---|
| 커밋 | `6326a5f` `feat(preview): add real form/availability/outlook research sections with user-run section workflow` |
| 파일 수 | 47 (신규 40, 수정 7) |
| 변경량 | 14,755 insertions(+), 65 deletions(-) |
| 삭제 항목 | **0** (기존 808건 삭제는 스테이징하지 않음) |
| 포함하지 않은 것 | `Plans.md`, `AGENTS.md`, `CLAUDE.md`, 비밀값 env, `frontend/dist`, 마이그레이션 |

스테이징 전 `git diff --cached --name-only`로 목록을 확인했고, 커밋도 같은 pathspec으로
했다. MP-06·MP-07 파일은 **편집 종료 인계를 받은 뒤** 해당 경로만 함께 넣었다.

## 9. 다음 사람이 이어받을 때

1. **사용자 검토부터.** 위 §2 본문이 실제 검토 대상이다. 승인은 화면에서 사용자가 한다.
2. 품질을 올리려면 **검색 인용 출처가 실제로 오는지**를 먼저 확인해야 한다. 이번
   응답은 질의 8건·인용 0건이었다. 프롬프트·모델 변경은 새 버전 확인 대상이다.
3. 선수 단위 사실을 넣으려면 읽기 경계(`public.player`, `public.player_season_stat`)를
   먼저 승인받아야 한다. 앱이 관리자 역할로 우회하지 않는다.
4. R2/R3는 자기 보고서의 남은 항목(live 미검증)을 확인한 뒤 섹션 단위로 실행한다.
