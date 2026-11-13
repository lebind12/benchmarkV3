# 섹션 워크플로우 통합 사실 조사 (읽기 전용)

작성: 2026-11-11 KST. 성격: **사실 조사 보고서**. 설계 검토·독립 리뷰·구현 계획·패치가 아니다.
코드·테스트·설정·정책·`Plans.md`는 수정하지 않았고, 커밋·스테이징·새 에이전트·모델 호출·
외부 HTTP·DB 쓰기·스키마/권한 변경·서버 재시작은 **0회**다. 저장소 편집은 이 파일 하나다.

모델: `hive` / `deepseek-ai/deepseek-v4.1-flash-1017`, 추론 강도 `max`, DSH 프로필 `dsh-tui`.

## 0. 읽은 자료

- `AGENTS.md`, `CLAUDE.md`, `Plans.md`(상단·작업표·최근 결과)
- `docs/superpowers/specs/2026-11-11-preview-evidence-first-design.md`(전문)
- `docs/implementation/match-preview/r4-information-bundle-trial.md`(전문, 정정 회계 포함)
- 소스: `app/preview/{registry,contracts,sections,runner,pipeline,retry,data,artifacts,inspection,version_manifest,jobs,section_preview,display_names,localized_names}.py`,
  `app/preview/modules/{form,availability,outlook,players,players_contract,synthesis,compose}.py`,
  `app/preview/prompts/*.md`, `app/preview/sources/{fixtures,api_football}.py`,
  `app/api/v1/preview_admin.py`, `app/core/config.py`, `app/auth/identity.py`,
  `scripts/preview_dev_{fixture_ro,names_ro}_provision.py`, `scripts/preview_dev_status.py`,
  `scripts/preview_r4_information_bundle_trial.py`(헤더·구조)
- DB: `~/.config/match-preview/preview-dev.env`의 좁은 읽기 전용 DSN 두 개로 **메타데이터·한정 조회만**.
  값을 출력하지 않았고 계정·비밀값을 옮겨 적지 않았다.

---

## 1. 현재 섹션/모듈 등록과 실제 동작 → 사용자 확정 섹션 매핑

### 1.1 등록 단위

| 사실 | 근거 |
|---|---|
| 모듈 등록은 `registry.py` 한 곳. 플러그인 자동 로더 없음 | `app/preview/registry.py:1-15` |
| 등록 모듈: `D0`(미구현, `implemented=False`), `R1`,`R2`,`R3`,`R4`,`S1`(구현), `mock_demo`(MOCK 전용) | `app/preview/registry.py:78-190` |
| 섹션 워크플로우 5개: `section_form`(D0,R1) · `section_availability`(D0,R2) · `section_outlook`(D0,R3) · `section_players`(D0,R4) · `section_synthesis`(R1,R2,R3,R4,S1) | `app/preview/registry.py:256-311` |
| 구현 버전 표는 `modules/__init__.py`의 `_IMPLEMENTED` (등록부와 어긋나면 테스트 실패) | `app/preview/modules/__init__.py:18-24` |
| 노드 구현이 있는 섹션 목록은 `sections._IMPLEMENTED_SECTIONS` (등록부와 별개로 여기서 정함) | `app/preview/sections.py:79-85` |
| 승인·실행 버전 산정의 단일 원천은 `version_manifest.py` (코드 상수만 사용) | `app/preview/version_manifest.py:1-20` |

### 1.2 사용자 확정 섹션과 현재 구현의 대응

| 사용자 확정 섹션 | 현재 대응 | 실제 상태 |
|---|---|---|
| 경기 전망 + AI 예상 스코어 | `section_outlook`(R3 매체 전망) + `section_synthesis`(S1 `ai_prediction`) | **두 섹션으로 분리돼 있고 한 섹션에서 함께 만들지 않는다**. S1 출력 계약에 `ai_prediction` 필드가 있다(`contracts.py:852-871`) |
| 주목 선수 각 팀 2명 (watchplayers2/team) | `section_players`(R4) | **현재 상한은 팀당이 아니라 전체 3명**이다(`players_contract.py:46`, `players.py:674`, `prompts/players.md:49`). 팀당 2명 상한은 코드에 없다 |
| 부상 주목 선수 팀당 최대 2명(확인된 부상만) | `section_availability`(R2) | 프롬프트에 `impact` 팀당 최대 2개, `player_updates`+`reported_absences` 합계 최대 8개(`prompts/availability.md:91`). 확정/불확실/무표기 상태를 분리하고 불확실을 확정으로 승격하지 않는다(`availability.py:122-141`) |
| 외부 매체 최대 3곳, 매체별 예상 스코어·이유, 없는 스코어 생성 금지 | `section_outlook`(R3 `media_forecasts`) | `MediaForecast`에 `publisher/url/published_at/statement/predicted_score`가 있다(`outlook.py:184-214`). 스코어를 지어내지 않도록 인용문에 없으면 `predicted_score`를 비운다(`outlook.py:939-945`). **매체 수 3 상한은 코드에 없다** |
| 공개 배당 정규시간 1X2 소수점 + 수집시각 | `section_outlook`(R3 `OddsObservation`) | 시장 판정으로 라이브·비1X2를 제외(`outlook.py:523-563`), 업체·시장·`observed_at`을 함께 보존(`outlook.py:148-183`) |

> **중요한 경계.** R3가 쓰는 배당·제공자 예측 원문은 **D0가 저장한 아티팩트에서만** 온다
> (`outlook.py:452-507`). 그런데 이 저장소에서 그 아티팩트를 만드는 API-Football 실행 경로
> (`data.prepare_match_data` → `api.d0_calls`)는 **테스트에서만 호출**되고 제품 실행 경로에
> 연결돼 있지 않다. `provider.py:82`에 `api_football_key` 비밀 이름만 정의돼 있고,
> `model-live.env` 키 목록에도 API-Football 키가 없다(값 미확인, 이름만 확인).
> 따라서 "R3가 배당을 실제로 읽어 본다"는 것은 **현재 데이터가 아니라 코드 경로만 존재**한다.

### 1.3 입력·출력 계약

| 계약 | 내용 | 근거 |
|---|---|---|
| `ModuleInput` | `module_id`, `fixture`, `snapshot_ids`, `selected_result_ids`, `input_hash`, `prompt_version`, `contract_version`, `implementation_version`, `delivered[]`, `parameters{}` | `contracts.py:425-463` |
| `ModuleResult` | `result_id`, `status`, `quality`, `claims[]`, `coverage[]`, `diagnostics[]`, `failure_code`, 버전 3종, `payload{}` | `contracts.py:466-520` |
| `SourceSnapshot` | `source_kind`, `provider`, `collected_at`, `provider_updated_at`, `fixture`, `artifact_id`, `validation_status` | `contracts.py:344-360` |
| `EvidenceClaim` | `claim_id`, `kind`, `text`, `snapshot_ids`, `decision`, `decision_reason`, 주체 id, `claimed_at`, `source_url` | `contracts.py:363-394` |
| `SectionResult`/저장 | `workflow_id`, `workflow_version`, `body`, `sources[]`, `module_execution_ids[]`, `result_ids[]`, `diagnostics[]`, `quality`, `unavailable_reason` | `store.py:531-560` |
| 섹션 노드 4단계 | `prepare_data → research → compose_body → finalize` (고정) | `runner.py:431-546` |
| 노드 1회 실행 기록 | 모듈 실행·결과·전달값을 남기고, 본문 없으면 `INSUFFICIENT`로 확정 | `runner.py:292-399`, `runner.py:517-535` |

**출력 계약 버전(현재 값):** `section_form-output-1`, `section_availability-output-1`,
`section_outlook-output-1`, `mp05p-r4-players-output-2`, `mp09-synthesis-output-1`
(`registry.py:256-311`).

### 1.4 모듈별 실제 동작(입력→출력)

| 모듈 | 입력 | 실제 동작 | 출력 | 근거 |
|---|---|---|---|---|
| D0(섹션) | `state["fixture"]` + 읽기 전용 DB reader | 저장된 경기·순위·부상만 읽고 사실 문장 생성. **외부 호출 0** | `facts[]`, `snapshot_ids[]`, `coverage[]` | `sections.py:163-402`, `sections.py:430-468` |
| D0(전체 프리뷰) | 동일 | 같은 `read_stored_context` 호출. API 수집 없음 | 동일 payload | `pipeline.py:292-358` |
| R1 | D0 `facts` | 모델 1회 + `google_search` 도구, 모델 URL이 공급자 grounding URL과 **정확히 일치**해야 웹 근거 인정 | `claims[]`, `coverage[]`, `sources[]` | `sections.py:517-537`, `form.py:871-903` |
| R2 | D0 `data` + 저장 부상 loader | 모델 1회, API 부상 표기와 검색 보도를 상충으로 보존 | `player_updates[]`, `impact` | `availability.py:1883-1920` |
| R3 | D0 `topics.odds`/`predictions` 아티팩트 + 모델 1회 | 배당 시장 판정, 매체 전망 grounding 대조 | `odds[]`, `media[]`, `prediction` | `outlook.py:409-507`, `outlook.py:911-990` |
| R4 | D0 `data` + 선택된 로스터/이름 해석기 | 모델 1회, `selected_player`/`selection_reason` 분리, DB 한글명 우선 | `players[]`, `korean_labels[]` | `players.py:576-676`, `players_contract.py:52-53` |
| S1 | **선택된** R1/R2/R3/R4 결과 버전 | 모델 1회, 새 검색 없음, 선택 facts 범위 안에서만 조합 | `headline`, `watch_points`, `ai_prediction`, `sources` | `synthesis.py:109-181`, `pipeline.py:666-757` |

### 1.5 전체 그래프 팬아웃과 예산(R4 포함)

| 사실 | 근거 |
|---|---|
| 전체 프리뷰 노드: `D0 → (R1‖R2‖R3‖R4) → V0 → S1 → V1` | `pipeline.py:104-107`, `pipeline.py:959-981` |
| **R4가 조사 갈래에 포함**되어 있다(4갈래 병렬) | `pipeline.py:104`, `pipeline.py:967-976` |
| 갈래마다 **자기 DB 세션**을 열고 커밋 후 닫는다(메인 스레드는 요약만) | `pipeline.py:494-550`, `pipeline.py:22-28` |
| 하나의 `RunBudget`을 갈래들이 **공유**한다(갈래별 예산 새로 만들지 않음) | `pipeline.py:17-20`, `pipeline.py:500-525` |
| 예산 상한(실값): 모델 요청 8 · 정상 모델 호출 5 · API 요청 24 · 호출당 시도 3 · 모델 동시 2 · API 동시 2 · 기한 1800초 | `retry.py:68-80`, `retry.py:163-182` |
| 미시작 정상 호출 몫을 예약해 재시도가 그 몫을 침범하지 못한다 | `retry.py:313-369` |
| 판정+차감을 한 잠금에서 처리(동시 통과로 상한 초과 방지) | `retry.py:371-389` |
| 동일 조합 진행 중 실행은 새로 만들지 않고 **기존 실행에 붙는다** | `pipeline.py:1098-1106`, `jobs.py:155-205` |
| 재개 시 같은 구현 버전의 성공 결과는 **재호출 없이 재사용** | `pipeline.py:483-492`, `pipeline.py:1553-1597` |
| 전체 프리뷰는 승인 없는 기본 실행을 거부(`AdmissionRefused`) | `pipeline.py:1082-1092` |

> **정상 5회 / 최대 8회는 코드 상수로 확인됐다**(`retry.py:71`, `retry.py:68`). 이는 **모델 호출**
> 기준이며, 수집 HTTP는 별도 `api_requests=24`(`retry.py:72`)로 센다.

### 1.6 섹션 단독 실행 vs 전체 실행

| 사실 | 근거 |
|---|---|
| 섹션 단독 실행은 같은 노드 4단계 그래프를 쓰고 활성 조사 구현만 1개 | `runner.py:625-775` |
| 전체 실행은 갈래별 `run_module`로 같은 모듈 구현을 호출 | `pipeline.py:468-552`, `runner.py:792-820` |
| 섹션 단독 실행은 `selected_result_ids`를 **호출자가 넘긴다**(실행기가 대신 고르지 않음) | `runner.py:640-651`, `runner.py:319-327` |

---

## 2. 웹 자료 수집 seam — 프로토타입 vs 제품

| 항목 | 제품 코드 | 프로토타입(시험 스크립트) |
|---|---|---|
| HTTP 클라이언트 | **없음**. `app/preview/sources/__init__.py:9`가 `httpx`·`requests`·`socket` 미import를 명시 | `httpx` 사용(`scripts/preview_r4_information_bundle_trial.py:1006-1031`) |
| 본문 추출 | **없음**. `requirements.txt`에 추출 라이브러리 미포함 | Trafilatura + 텍스트 폴백(`…trial.py:244-337`) |
| 검색 | Vertex `google_search` 도구만(모델 요청 내부) | 저장된 두 응답의 URL 후보 재사용, 새 검색 0회(`…trial.py:176`) |
| 검증기 | `form.validate_response` = grounding URL 정확 일치 + API 문자열 대조(`form.py:871-903`) | `validate_bundle_references`로 **대체**, `google_search` 도구 제거(`r4-information-bundle-trial.md:43-46`) |
| 예산·시도·원문 저장 | `provider.execute_request` 하나가 소유(`provider.py:611-800`) | **그대로 재사용** |
| 실행/저장 | `runner.run_section_workflow`, `store`, `artifacts` | **그대로 재사용** |

**제품에 스크래퍼/수집 HTTP 경로가 없다는 것은 코드 부재로 확인된다.** `requirements.txt`의
`httpx==0.28.1`은 "test only" 표기다(`requirements.txt` 마지막 절). 프로토타입은 제품 의존성을
늘리지 않았다(같은 파일 주석).

### 2.1 저장·실행·검사 seam (재사용 가능한 것)

| seam | 무엇을 하는가 | 근거 |
|---|---|---|
| `artifacts.save_artifact` | 원문 아티팩트 저장 + 비밀값 마스킹(`_is_secret_key`, `redact`) | `artifacts.py:64-171` |
| `store.record_source_snapshot` | 출처 스냅샷 기록(provider·collected_at·artifact 연결) | `store.py`, `sections.py:358-372` |
| `store.save_section_result` | 섹션 결과 버전 저장(빈 본문+사유 없음은 거부) | `store.py:531-566` |
| `store.get_run_detail` | 실행·모듈·결과·스냅샷·시도·아티팩트·섹션결과 조회 | `contracts.py:940-964` |
| `inspection.build_run_inspection` | 요청/원문응답/정규화변환/다음입력 4탭 조회 모델 | `inspection.py:39-60`, `inspection.py:201`, `inspection.py:362` |
| `section_preview.build_reader_view` / `build_diagnostics_view` | 독자용 보기 / 관리자 진단 분리 | `section_preview.py:83-184` |
| API | `GET /sections`, `POST /section-runs`, `GET /runs/{id}/preview`, `…/preview/diagnostics`, `…/section-results`, `GET /registry` | `preview_admin.py:596-698`, `preview_admin.py:701-827`, `preview_admin.py:885` |
| UI | `SectionRunView.vue`가 `detail.section_results`의 `body`·`sources`·`quality` 표시 | `frontend/src/features/match-preview/SectionRunView.vue:180,312-345` |

### 2.2 현재 "독립 섹션 실행"이 실제로 소비하는 것

- `section_players`: D0 저장 사실 + (선택) 로스터/이름 해석기 + 모델 1회. **웹 본문 입력은 없다.**
  (`sections.py:577-591`, `players.py:1264-1330`)
- `section_outlook`: D0가 남긴 `topics.odds`/`topics.predictions` 아티팩트 + 모델 1회.
  D0 저장 경로에는 `topics`가 없으므로(`sections.py:445-462`) 실제로는 **배당·예측 없이 진행**하고
  그 사실을 `coverage`에 남긴다(`outlook.py:468-475`).
- `section_availability`: D0 `data` + `injuries_for_fixture` 읽기 전용 loader + 모델 1회.
- `section_synthesis`: 선택된 결과 버전만. 새 수집·검색 없음(`synthesis.py:7-11`, `pipeline.py:666-757`).

### 2.3 정보 원문 "묶음" 개념의 위치

제품 코드에 `bundle`이라는 개념은 **없다**(grep 결과 `runner.py`의 `implementations` 묶음뿐).
묶음 스키마·발췌 상한·`discovery_only` 표시는 시험 스크립트와 설계 문서에만 있다
(`r4-information-bundle-trial.md:115-125`, 설계 §6, §6.1).

---

## 3. 허용된 DB 읽기 사실 (실제 probe 결과)

연결: `~/.config/match-preview/preview-dev.env`(mode 600, 저장소 밖). 역할 이름만 확인:
`preview_dev_fixture_ro`, `preview_dev_names_ro`. DSN·계정·비밀번호는 이 보고서에 없다.
모든 probe는 `default_transaction_read_only` + `statement_timeout 5000ms` + 한정 WHERE/LIMIT.

### 3.1 역할별 실제 권한 (introspection)

| 역할 | 부여된 것 | 근거 |
|---|---|---|
| `preview_dev_fixture_ro` | **표 단위 `SELECT` 5개**: `public.fixture`, `public.injury`, `public.league`, `public.standings`, `public.team` | probe `information_schema.table_privileges`; `scripts/preview_dev_fixture_ro_provision.py:46-52` |
| `preview_dev_names_ro` | **열 단위 `SELECT`만**: `team(id,external_id,name)`, `team_translation(team_id,name_ko,short_name_ko)`, `player(id,external_id,name,firstname,lastname,current_team_id)`, `player_translation(player_id,name_ko,short_name_ko)`, `coach(id,external_id,name)`, `coach_translation(coach_id,name_ko,short_name_ko)`, `team_coach(team_id,coach_id)` | probe `information_schema.column_privileges`; `scripts/preview_dev_names_ro_provision.py:38-56` |

**열 단위 부여라서 `has_table_privilege(...,'SELECT')`는 거짓으로 나온다** — 설계된 동작이며
스크립트가 그 이유를 명시한다(`preview_dev_names_ro_provision.py:27-29`).

### 3.2 사용자 확정 섹션별 DB 읽기 가능성

| 필요한 자료 | 표 존재 | 이 역할로 읽기 | 판정 |
|---|---|---|---|
| 최근 팀 성적(폼·순위) | `public.standings`(존재) | **가능** | 확인됨 |
| 최근 경기 결과 | `public.fixture`(존재, 3,256행) | **가능** | 확인됨 |
| 부상·출전 불확실 | `public.injury`(존재) | **가능하지만 표가 비어 있음**(전체 0행) | "부상자 없음"의 증거가 아니다 — 코드도 같은 규칙(`sources/fixtures.py:19-20`, `sections.py:300-310`) |
| 선수 시즌 기록 | `public.player_season_stat`(존재, 열 확인: appearances/minutes/goals/assists/rating 등) | **불가 — `InsufficientPrivilege`** | **스키마 존재 ≠ 사용 가능 데이터** |
| 배당 | **표 자체가 없음**(`%odd%`/`%bet%` 0건) | 해당 없음 | DB 경로 없음 |
| 경기 상세(이벤트·라인업·통계) | `public.fixture_detail`(존재) | **불가 — `InsufficientPrivilege`** | 범위 밖 |
| 기사 원문 | `public.news_article`(존재) | **불가 — `InsufficientPrivilege`** | 제품 경로에서 쓰지 않음 |
| 계정 | `public.app_user`(존재) | `fixture_ro`로 **불가**. 별도 `identity_ro`만 `app_user` SELECT | 경계 분리 확인 |

### 3.3 경계가 걸린 한정 조회 (fixture 1557474, 팀 13/4만)

| 항목 | 확인된 값 | 근거 |
|---|---|---|
| 경기 | 내부 `41125`, external `1557474`, league `1`, season `2026`, home `13`, away `4`, kickoff `2026-11-21T12:30Z`, status `NS` | `public.fixture` 한정 조회 |
| 팀 이름 | `13 Manchester City` / `4 Fulham` (`public.team`), 한국어 `맨체스터 시티` / `풀럼` (`team_translation`) | `fixture_ro` + `names_ro` |
| 순위 | `13` → 3위 10경기 7승0무3패 득21 실13 승점21 폼 `LLLWW`; `4` → 15위 10경기 2승4무4패 득10 실12 승점10 폼 `DDWWL` | `public.standings` |
| 최근 FT 경기 | 팀13 5건(예: `1557465` 18 vs 13 3-1), 팀4 5건(예: `1557461` 4 vs 2 1-1) — `LIMIT 5` | `public.fixture` |
| 부상 | 이 경기 0행, 두 팀 전 시즌 0행, **표 전체 0행** | `public.injury` |
| 로스터 | 팀13 33명, 팀4 33명(이름 열만) | `names_ro` |

**범위 준수:** 전체 로스터 덤프·PII·계정 데이터 없음. 선수 개인 식별 정보는 이름 열 조회
가능성 확인에 그쳤고 이 보고서에 개별 선수를 나열하지 않았다.

### 3.4 선수 통계·배당 읽기가 불가능한 이유(정직하게)

- `public.player_season_stat`은 **존재하고 열도 확인**되지만 `fixture_ro`에 `SELECT`가 없고
  `names_ro`는 열 단위 이름 열만 갖는다. 두 역할 중 어느 것으로도 읽을 수 없다.
- 배당 표는 **카탈로그에 없다**. `/odds` 응답은 오직 모델/시험 경로에서만 다뤄졌다
  (`api_football.parse_odds`) → `data.prepare_match_data` → 아티팩트. 그 실행 경로는 제품에
  연결돼 있지 않고, API-Football 자격증명도 설정에 없다(키 이름 목록으로 확인).
- 결과적으로 "배당을 DB에서 읽는다"거나 "선수 통계를 DB에서 읽는다"는 진술은 **현재 사실이 아니다.**
- 이 거부는 **작업 실패가 아니라 사실**이다. 권한·스키마를 넓히지 않았고 프로비저닝도 하지 않았다.

---

## 4. 수집 공유·중복 제거·병렬 조립이 걸릴 수 있는 지점 (사실 목록만)

### 4.1 소유·경로 목록 (구현 서명·패치 없음)

| 지점 | 현재 소유자 | 파일:줄 |
|---|---|---|
| D0 공유 자료 준비(섹션·전체 공용) | `sections.read_stored_context` / `pipeline._prepare_node` | `sections.py:163-402`, `pipeline.py:292-358` |
| 조사 갈래 병렬 실행 + 갈래별 세션 | `pipeline._branch_node` | `pipeline.py:468-552` |
| 단일 예산·예약·동시 gate | `retry.RunBudget` / `ConcurrencyGate` / `ConcurrencyLimiter` | `retry.py:229-470` |
| 실제 전송·재시도·원문 아티팩트 | `provider.execute_request` | `provider.py:611-800` |
| 요청 분류(모델 vs API) | transport별 `request_class` (API=166, MODEL=240) | `provider.py:120,166,240` |
| 진행 중 중복 실행 합치기 | `jobs.dedup_key` + `find_active_run` | `jobs.py:155-205`, `pipeline.py:1098-1106` |
| 재개 시 성공 결과 재사용 | `pipeline._existing_success` | `pipeline.py:1553-1597` |
| 섹션 결과 버전 저장 | `store.save_section_result` | `store.py:531-566` |
| 결정적 본문 재조립(외부 호출 0) | `sections.recompose_section_body` | `sections.py:662-736` |
| 저장 원문 재해석(외부 호출 0) | `sections.revalidate_section_from_stored_response` | `sections.py:739+` |
| 독자/진단 보기 분리 | `section_preview.build_reader_view` / `build_diagnostics_view` | `section_preview.py:83-184` |
| 이름 해석 캐시(실행 내) | `sections._ResolverHandle._cache` | `sections.py:1168-1187` |

### 4.2 구분해야 할 세 축 (코드로 확인된 사실)

| 축 | 현재 사실 | 근거 |
|---|---|---|
| **발견(discovery)** | Vertex `google_search`가 모델 요청 내부에서 수행. 별도 수집 노드 없음 | `form.py:561-630`, `outlook.py:817-856` |
| **쓰기(write)** | `preview_dev` 스키마에만. 기존 `public`는 읽기 전용 | `app/core/config.py:1-14`, `AGENTS.md` 개발 DB 기준 |
| **모델 호출** | `provider.request_model`(`provider.py:915`)이 `execute_request`(`provider.py:611`)로 전송. 예산 공유 | `provider.py:611-800,915`, `retry.py:340-389` |
| **HTTP(비모델)** | 제품에 없음. 예산 축(`api_requests=24`)만 정의돼 있음 | `retry.py:72`, `sources/__init__.py:9` |
| **결정적 조립** | 모델 호출 0으로 본문 재조립/재해석 경로가 이미 존재 | `sections.py:662-736`, `sections.py:739+` |

### 4.3 중복 제거가 이미 있는 곳 / 없는 곳

- **있음(실행 단위):** `jobs.dedup_key`(경기·스냅샷·버전)로 진행 중 실행 합치기. 같은 실행
  재개 시 `_existing_success`로 성공 갈래 재호출 방지.
- **있음(이름 해석):** `_ResolverHandle` 실행 내 팀 단위 캐시.
- **없음(URL/문서 단위):** canonical URL 정규화·문서 해시 기반 중복 제거는 제품 코드에 없다.
  시험 스크립트에는 `_candidate_key`/`canonical` 정규화가 있다(`…trial.py:382-392,1050`).

### 4.4 예산 상한을 늘리는 선택지에 대한 언급 없음

`normal_model_calls=5`/`model_requests=8`은 **코드 상수**이고(`retry.py:68-71`), 설계 §9의
검색·추출 상한(합계 24, 검색 8, 추출 4, URL 16)은 **미승인 제안**이다(설계 §9 표).
이 보고서는 어느 쪽도 선택하지 않는다.

---

## 5. 필요한 제품 변경 vs 현재 능력

| 요구 | 현재 능력 | 격차 |
|---|---|---|
| AI 전망 + AI 예상 스코어를 함께 생성 | S1이 `ai_prediction`을 만든다(`contracts.py:865`) | **능력 있음.** 단, R3 매체 전망과 별도 섹션이다 |
| 주목 선수 **팀당** 2명 | 전체 3명 상한(`players_contract.py:46`) | **상한 축이 다르다.** 팀당 배분 개념 없음 |
| 부상 주목 선수 팀당 최대 2명 | 프롬프트 상한만 존재(`prompts/availability.md:91`) | 모델 지시이며 코드 강제 없음 |
| 외부 매체 최대 3곳 | `MediaForecast` 무제한 수집(`outlook.py:924-990`) | **개수 상한 코드 없음** |
| 매체별 스코어/이유, 없는 스코어 미생성 | 스코어 미포함 시 비움(`outlook.py:939-945`) | **능력 있음** |
| 공개 배당 1X2 + 수집시각 | 시장 판정·`observed_at` 보존(`outlook.py:148-183,523-563`) | 코드 있으나 **데이터 경로 미연결** |
| 웹 본문 수집 후 근거 인용 | 제품에 HTTP/추출 없음 | **주요 격차** |
| 기사 내용을 API·DB와 교차검증하지 않고 채택 | 현 R1 검증기가 **grounding URL 일치를 요구**(`form.py:871-903`) | 정책과 코드가 어긋남(설계 §2가 같은 지점을 지적) |
| 새 claim 검증 엔진 없이 | 시험 스크립트는 "참조가 묶음에 있는가"만 봄(`r4-information-bundle-trial.md:279`) | 요구 없음이 사용자 확정 |
| 근거 기반 선수 선정 사유 | R4가 이미 수행 | 능력 있음 |

### 5.1 가장 작은 다음 사실적 전제 조건

1. **웹 본문 수집 경로가 제품에 없다** — 어느 노드가 HTTP를 소유할지 정해져야 R3/R4가 기사
   본문을 입력으로 받을 수 있다. 현재 `sources/__init__.py:9`가 그 부재를 명시한다.
2. **R3 배당 입력이 저장 아티팩트 의존** — D0 저장 경로에 `topics`가 없어(`sections.py:445-462`)
   배당·예측 없이 조사한다. API-Football 자격증명·전송 연결도 없다.
3. **R1 grounding URL 정확 일치 규칙**이 기사 본문 채택을 막는다(`form.py:871-903`).
   R4도 같은 공유 판정 경로를 호출한다(`players.py:679-695`).
4. **팀당 상한·매체 수 상한이 코드에 없다** — 계약 값 변경이 필요하다.
5. **DB 읽기 범위** — 순위/경기/부상은 읽히고, 선수 통계·배당은 읽히지 않는다(§3).

### 5.2 범위 밖으로 둔 것

전체 보안 감사, 새 테스트 스위트, 마이그레이션, 권한 프로비저닝, 모델·API 호출, 배포.
`AGENTS.md`의 테스트·검토 범위 규칙에 따라 현재 수용 기준과 무관한 확장은 하지 않았다.

---

## 6. R4 시험 회계의 정확한 현재 서술

인용 시 다음을 그대로 쓴다.

- 실제 Vertex 전송은 **최소 2회**(1차 유실·2차 보존). "1회"로 쓰지 않는다.
  (`r4-information-bundle-trial.md:9,143-158`)
- 저장된 섹션 행 `4d5b51c2-…`는 **`quality=insufficient`, 본문 0자**이고, 보이는 본문은
  **오프라인 재처리 파일**이다(`…:311-319`).
- DB는 **경기 식별·순위·지난 경기·후보 범위·표시 이름**으로 쓰였고, **최종 사실 문장은 전부
  웹 구간을 인용**한다 → **DB 기반 전망 경로는 입증되지 않았다**(`…:294-296`, `Plans.md:13`).
- 이번 경기 프리뷰 성격 기사 확보 **0건**(`…:99,250`).
- 검증 범위 §7.2 구조화 claim 검증은 **철회됐고 제품 필수 게이트가 아니다**(`…:288-298`).

---

## 7. 수용 기준 대조표

| # | 수용 기준 | 결과 | 근거 |
|---|---|---|---|
| 1 | 현재 모듈/섹션 등록과 입출력 계약 확인 | 충족 | §1.1, §1.3 |
| 2 | form/availability/outlook/players/synthesis 동작 → 사용자 섹션 매핑 | 충족 | §1.2, §1.4 |
| 3 | 실제 그래프 팬아웃(R4 포함)과 공유 DB 세션·예산 | 충족 | §1.5 |
| 4 | 웹 검색 프로토타입 seam vs 제품(제품에 스크래퍼 없음) | 충족 | §2 |
| 5 | 저장/실행/아티팩트/섹션 검사 seam과 독립 섹션이 실제 소비하는 것 | 충족 | §2.1, §2.2 |
| 6 | DB 읽기 가능 사실(최근 성적·선수 통계·부상·배당) + 역할 권한 | 충족 | §3.1-3.3 |
| 7 | 선수통계/배당 읽기 불가를 정직하게 설명 | 충족 | §3.4 |
| 8 | 수집 공유·중복제거·병렬 조립 hook 지점(소유·경로만) | 충족 | §4.1-4.3 |
| 9 | 정상 5/최대 8 확인, 발견/쓰기/모델 vs HTTP 구분, 결정적 조립 옵션 | 충족 | §1.5, §4.2 |
| 10 | 필요한 제품 변경 vs 현재 능력, 최소 다음 전제 | 충족 | §5 |
| 11 | R4 회계 정확 서술(전송 2회·DB 전망 미입증·검증엔진 철회) | 충족 | §6 |
| 12 | 비밀값·PII·전체 로스터 덤프 없음 | 충족 | §3.3 |
| 13 | 코드/설정/정책/Plans 미수정, 커밋·스테이징 없음 | 충족 | 아래 범위 |

---

## 범위 준수

- 편집한 파일: 이 문서 하나(`docs/implementation/match-preview/section-workflow-integration-facts.md`).
- 제품 코드·테스트·스크립트·설정·`requirements.txt`·정책·`Plans.md`: **수정 없음**.
- git 스테이징/커밋: **없음**. 기존 삭제·dirty 파일 그대로 보존(`git status` 확인만).
- DB: 읽기 전용 SELECT와 카탈로그 introspection만. **쓰기 0회**, 스키마·권한 변경 0회, 프로비저닝 0회.
- 모델 호출·API-Football 호출·공개 웹 fetch: **0회**.
- 새 에이전트·서버 재시작·배포: **없음**.
- DSN·계정·비밀번호 원문: 이 문서와 세션 출력에 **없음**. 역할 이름만 기록.

EDITING STOPPED
