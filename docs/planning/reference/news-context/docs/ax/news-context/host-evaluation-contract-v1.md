> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `news-context` 워크트리의 `docs/ax/news-context/host-evaluation-contract-v1.md`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# 실제 평가 실행·데이터 준비 계약 v1

상태: **구현 전 실행 명세**. 아래 script/config/fixture는 명시적으로 작성 예정이며 현재 존재·실행·PASS를 주장하지 않는다. Opus 비교의 실행 명세/적재 검증 지적에 대한 운영자 보완이다. Q-DATA/Q-VERIFY를 닫지 않는다.

## 1. 실행 경계와 순서

네트워크 가능한 운영자 host에서 원천 snapshot 준비 → 폐기 DB/서버 준비 → 실제 평가를 실행한다. 네트워크가 닫힌 공식 검증 명령은 생성된 증거를 읽어 검증한다. 별도 host 실행을 검증 sandbox 안의 명령인 것처럼 표기하지 않는다. 준비·개발·host 평가·최종 검증을 연결하는 실제 인계/왕복 확인은 Q-VERIFY의 필수 준비물이다.

아래 `<scratch>`와 `<evidence-root>`는 운영자가 배정하는 workspace 밖의 절대 경로다. 과거 실행은 별도 run_id 디렉터리에 보존하며 현재 실행 지문·원본 관찰을 확인한 manifest만 최종 검사 입력으로 지정한다. 값이 들어 있는 URL/토큰/credential을 argv·정답·manifest에 저장하지 않는다.

## 2. Snapshot 동결 — host 전용, 작성 예정

```text
python3 scripts/prepare_news_context_snapshot.py
  --source-url-env NEWS_CONTEXT_SOURCE_DATABASE_URL
  --scope tests/fixtures/news_context/source-scope.json
  --as-of <고정 UTC 기준시각>
  --output-dir <scratch>/source-snapshot
  --manifest-output <evidence-root>/snapshot-manifest.json
```

원천 연결은 READ ONLY transaction으로 고정하며 대상 table/PK/ID/시즌/시각/JSON coverage를 명시한다. 포함 대상은 축구 entity·번역·대회/시즌·경기/상세·기록·순위·이적·부상·관측 관계이며 운영 사용자·세션·인증 자료는 반입하지 않는다. 자료 없음과 실제 행이 있는 정상 이력 사례를 함께 확보한다. source-scope에는 선택한 실제 article/community 표본과 연결되는 대상·경기·기간을 기록한다.

snapshot manifest 필수값: `snapshot_id, extracted_at, as_of, scope_hash, table_row_counts, table_content_hashes, schema_version, competition_seasons, metric_coverage, source_type(real/synthetic), provenance_hashes`. DB 행수/JSON nonNULL만으로 자료 충족을 판정하지 않는다. 원천이 갱신돼도 동일 snapshot에서 독립 기대 조회가 재현돼야 한다.

## 3. 폐기 DB와 서버 준비 — host 전용, 작성 예정

```text
python3 scripts/prepare_news_context_local.py
  --database-url-env NEWS_CONTEXT_EVAL_DATABASE_URL
  --snapshot-manifest <evidence-root>/snapshot-manifest.json
  --scratch-dir <scratch>/local
  --baseline-alembic-head <검토 후 고정한 기존 head>
  --pending-supabase-migrations <이번 기능의 SQL migration 목록 파일>
  --provision-test-users 2
  --output-manifest <evidence-root>/local-manifest.json
```

helper는 loopback의 폐기 가능한 명시적 test DB만 허용하고 운영/공유 DB를 거부한다. 로컬 Postgres/Supabase 기동 도구·접속 가능 여부를 먼저 확인하며 없으면 명시 실패한다. 제공되지 않은 DB를 자동으로 운영 연결로 대체하지 않는다.

migration 순서: 빈 test DB → **검토한 기존 Alembic baseline head**로 기반 schema 구성 → 이미 Alembic에 대응된 Supabase 관리/홈 SQL은 중복 적용하지 않음 → **이번 기능의 미적용 Supabase migration만** 명시 목록 순서대로 적용 → SQLAlchemy 모델/실제 schema 정합성 검사 → snapshot 반입 → 원천 자료 읽기 권한/피드백 쓰기 영역 분리 → 폐기 계정 A/B 준비. baseline head와 mirrored/pending migration 목록·hash를 local manifest에 기록한다. 임의 `alembic upgrade head`와 전체 Supabase SQL 이중 적용을 허용하지 않는다. 운영 DB migration/push/reset은 이 명령에 포함하지 않는다.

후속 준비 helper는 격리 backend/frontend를 띄우고 실제 할당한 주소를 local manifest에 남긴다. backend의 DB는 폐기 DB, scheduler는 비활성화, 일반 분석/호버에서 API-Football 호출은 금지다. 모델 호출은 host 실제 평가에서만 허용한 설정을 사용한다. 권한별 token과 비밀은 manifest에서 제외한다.

환경변수 이름(값 제외): `NEWS_CONTEXT_SOURCE_DATABASE_URL`, `NEWS_CONTEXT_EVAL_DATABASE_URL`, `NEWS_CONTEXT_EVAL_API_BASE_URL`, `NEWS_CONTEXT_EVAL_UI_BASE_URL`, `NEWS_CONTEXT_EVAL_JWT_SECRET`, 기존 Vertex 인증 allowlist. 테스트 사용자는 폐기 DB에만 만들고 원천 DB 사용자/권한을 변경하지 않는다.

## 4. 실제 평가 — host 전용, 작성 예정

```text
python3 scripts/run_news_context_evaluation.py
  --corpus tests/fixtures/news_context/corpus.jsonl
  --gold tests/fixtures/news_context/gold.jsonl
  --evaluation-manifest tests/fixtures/news_context/evaluation-manifest.json
  --snapshot-manifest <evidence-root>/snapshot-manifest.json
  --local-manifest <evidence-root>/local-manifest.json
  --api-base-url-env NEWS_CONTEXT_EVAL_API_BASE_URL
  --ui-base-url-env NEWS_CONTEXT_EVAL_UI_BASE_URL
  --repetitions 3
  --decision-states v0,v1,v2
  --output-dir <evidence-root>/runs/<run_id>
  --manifest-output <evidence-root>/runs/<run_id>/manifest.json
```

입력은 본문/출처/기준일/언어/실제·합성 구분을 가진 corpus, 원문 영역·대상/경기·조회조건·기대 DB 값·NULL·필수연결/금지/허용확인의 독립 gold, 58개 시나리오 대응표·반복/평가 규칙·입력 hash가 고정된 evaluation manifest다. source snapshot·격리 DB·코드·모델·프롬프트·정답의 동일성을 실행 전후에 확인한다.

각 반복에서 판단 DB를 동일 초기 상태로 준비한다. `v0`: 저장 전 A/B의 기대 결과. `v1`: A가 UI/API로 확인/거부를 저장한 후 B가 다른 글을 새 요청으로 분석. `v2`: A의 수정/취소 후 B가 재분석하고 열린 구버전 카드도 확인. 원천 snapshot은 변경하지 않고 판단 상태만 바꾼다. 적용/미적용 반례, 초기 후보 밖 검색, 순차/동시 충돌, 타 STREAMER의 다른 사람 job/SSE/취소 접근 거부도 검증한다. 각 상태/반복마다 새 분석 ID를 사용해 동일 본문 cache를 개선 증거로 삼지 않는다.

5만 자 한/영/혼합 자료는 앞·중간·끝·30개 초과 등장·경계 지시어를 대조한다. 구간별 종료 상태·인용/코드포인트·실제 token/finish reason·재시도/재분할·총 호출/비용·대기시간을 기록한다. 자동 복구 테스트에서 제출 뒤 추가 사용자 클릭 없이 전체 결과가 공개돼야 하고 부분 결과를 완료로 표시하면 실패다. 필수 누락/오연결/수치·ID·구간 오류는 3회 모두0이어야 한다. 소수 실행을 안정적인 p95 증거로 쓰지 않는다.

## 5. 증거 manifest와 공식 V06

manifest 필수값:

`run_id, started_at, finished_at, command_argv, exit_code, code_tree_hash_before/after, contract_hash, prompt_hash, model_id/version/config, corpus_hash, gold_hash, evaluation_manifest_hash, snapshot_id/hash, local_manifest_hash, scenario_ids, repetitions, decision_states, user_contexts(A/B), applied_decision_ids/versions/effects, observations, browser_artifacts, provider_finish_reasons, token/latency/retry_metrics, artifact_paths/hashes, failures, skipped, real_or_replayed`.

UI/API/DB/provider의 원본 관찰과 실행 종료코드를 연결하고 비밀·운영 전문을 로그에 넣지 않는다. 반복/상태/필수 시나리오가 빠지거나 skip·미실행·실패·지문 불일치·재생 응답뿐이면 통과하지 않는다. 파일 존재나 PASS 문자열만 검사하지 않는다.

공식 네트워크 차단 검증(V06)의 **후속 동결 시 argv 형태**, 검사기 작성 예정:

```text
python3 scripts/verify_news_context_evidence.py
  --manifest <evidence-root>/runs/<고정한 실제 run_id>/manifest.json
  --expected tests/fixtures/news_context/evaluation-manifest.json
  --workspace <개발 worktree 절대경로>
  --require-real-runs 3
  --require-decision-states v0,v1,v2
  --reject-incomplete
```

실제 검사에 쓸 경로·run_id·code/contract 지문 연결은 host 실행/인계 방식과 함께 확정한다. 증거를 생성하려고 닫힌 sandbox의 네트워크를 열거나 일반 테스트가 임의 host 명령을 실행하도록 우회하지 않는다. 현재 Q-VERIFY는 미해결이며 실제 실행 파일·전달 경로·폐기 fixture 왕복이 확인돼야 구현 진입 준비를 완료할 수 있다.

## 6. 이적/부상 적재 검증 — 작성 예정

`tests/unit/test_daily_sync_transfers_injuries.py`와 `tests/fixtures/api_football/news_context/`를 작성 대상으로 둔다. 기존 worker-client로 관찰한 원천 응답의 출처·기준일·해시와 실제/합성 구분을 기록한다. credential은 fixture에 넣지 않는다.

검증: 실제 endpoint 모양→player/team/fixture/league ID 대조→대회별 2시즌 날짜 범위→upsert→같은 응답 재실행·부분 실패 후 재시작의 멱등성. missing FK·NULL fixture·동일 날짜 복수 이적·미수집/0·일부 페이지 실패를 구분한다. 기존 번역과 사람 수정 보호를 확인하고 루머를 확정 이력으로 만들지 않는다. V05에 이 전용 파일을 추가하며 R05-S04의 주 근거로 매핑한다. 기존 홈 조회 테스트의 PASS만으로 적재를 입증하지 않는다.

## 7. 기존 기준의 정합화와 재사용

기존 `tests/integration/test_news_analysis.py:63`은20,001자를 거부한다. 50,000자 목표와의 정합화를 **init/동결 전에** 운영자 테스트 준비로 수행하고 전후 diff·사용자 요구·독립 기대값·재검증 범위를 기록한다. 새50,000 유효/50,001 초과와 Unicode 기준을 추가하며 기존 진단 변경·인증/URL/오류 회귀를 보존한다. 동결 후 구현자가 테스트를 약화해 통과시키지 않는다.

기존 h2h_fixture/fixture_detail 서비스와 h2h/team-recent/league-standings endpoint를 우선 조사한다. 경기·대회·기준일·NULL·분모가 새 문맥과 일치하는 부분만 재사용하고 현재값을 과거 사실로 바꾸지 않는다.

`contract.timeout_seconds`는 현재 controller의 **모델 세션별 기한**이고 verification_commands의 timeout은 **명령별 기한**이다(controller.py:237,418). 합계2460초를 전역1800초 제한으로 해석하지 않는다. 별도 host 실행/준비의 전체 예산은 실제 호출 계획에서 정하고 timeout/skip을 성공으로 처리하지 않는다.

job/events/취소는 현재 역할 외 **요청자 소유권**도 검사한다. STREAMER/ADMIN 권한만으로 다른 사람의 임시 원문·작업을 읽거나 취소할 수 없다. 서비스 공통 판단의 공유 범위와 임시 작업 소유권을 혼동하지 않는다.
