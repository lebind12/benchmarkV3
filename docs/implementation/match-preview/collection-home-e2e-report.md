# CE-E2E: 기존 수집 API → 새 정본 저장 → 홈 반영 (실행 보고)

작성 2026-11-18 10:15 KST. 작성 주체: DeepSeek 구현 워커 (task_42ebd9268358 / ctx_92e11eaf37b1).
세션 모델 `deepseek-ai/deepseek-v4.1-flash-1017`, provider `hive`, 추론 강도 `high`
(세션 캐시 `~/.dsh/storages/session_projcache/sessions/7b889e72-...json`의
`model`/`provider`/`reasoningEffort`에서 확인). 제품 모델은 건드리지 않았다:
`vertex` / `gemini-3.5-flash` / `global`.

## 결론 먼저

**E2E는 성공하지 못했다.** 수집 실행 1회를 실제로 보냈고 수집ID는 받았으나, 그 수집이
내가 만든 기동 환경의 결함(수집 자격 env 누락)으로 즉시 실패했고, 뒤이어 자동 생성이
호출돼 두 경기 프리뷰가 `failed`로 저장됐다. 그 실패 run이 잠시 홈을 대체했으며,
조정자 승인 아래 지원 cancel API로 두 run만 취소해 홈은 이전 정상 run으로 돌아왔다.

가장 먼저 실패한 경계는 **수집 transport**다. 요청 본문·인증·엔드포인트·승인 게이트·
자동생성 트리거·정본 저장 배선은 모두 실제로 동작했다. 그 뒤 두 번째 결함이 남았다:
`section_players`/`section_availability`의 **커밋된 저장 행이 없다**. 모델 응답은 200으로
수신된 것으로 장부에 남아 있으나, 첫 예외가 **모델 후처리인지 장부인지 정본 저장인지는
미확정**이다(6절 2항). 두 번째 문제는 API 키 누락과 무관하다.

## 1. 사용자 목표

사용자는 기존 수집 API를 한 번 호출하면 새 `preview_dev` 정본 테이블에 프리뷰가 저장되고
홈에 바로 반영되는 실제 E2E를 요청했다. 수집 후 별도 UI 생성 버튼을 누르는 경로가 아니라
**수집 완료가 자동 생성으로 이어지는 경로**가 검증 대상이다. 시험 범위는 2경기
(1557474, 1557470), 자동 생성은 각 1회, 중복 POST 금지.

## 2. 실행 시각과 endpoint

- 수집 POST 시각: 2026-11-18T00:57:47Z (09:57:47 KST)
- endpoint: `POST http://127.0.0.1:38003/api/v1/admin/management/runs/preview-test`
- 요청 본문(비밀값 없음):
  ```json
  {"target_ids":[13],"fixture_from":"2026-11-18T00:00:00+09:00",
   "fixture_to":"2026-11-21T15:00:00+00:00","preview_fixture_ids":[1557474,1557470],
   "generate_after_collection":true}
  ```
- 인증: 이미 로그인돼 있던 정상 ADMIN 브라우저 세션 재사용(`/api/v1/auth/refresh`로 받은
  access token, 계정 id 1, role `ADMIN`). 토큰 직접 발급·권한 우회는 하지 않았다.
- 응답: HTTP 200, 수집 실행ID **`3bee3ed9-3d4b-456d-b2b7-0d531020db3b`**, `status=queued`,
  `test_scope.generate_after_collection=true` 저장 확인. 중복 POST는 보내지 않았다.

## 3. 사전 확인(preflight) 결과

| 항목 | 실제 값 |
|---|---|
| 워크트리 HEAD | `a062215423863e37b62518a25327242895cf4634`, branch `lebind12/preview-api-migration`, clean |
| 38000 | PID 38299, 최신 워크트리, role `preview_dev_runtime`, `HOME_PREVIEW_ENABLED=false`, `WORKER_SCHEDULER_ENABLED=false` |
| 38003(작업 전) | PID 68684, **다른 워크트리 `preview-test-integration`(HEAD 0751683)**, cwd 불일치 |
| 대상 경기 | 1557474 Manchester City–Fulham NS 2026-11-21T12:30Z, 1557470 Chelsea–Leeds NS 15:00Z, 둘 다 league 1 / season 2026 |
| 수집 대상 | target 13 활성, EPL 2026, 상세·선수·순위 true, `fixture_limit=null` |
| 진행 중 수집 | 없음(active `management_run` 0건) |
| 승인 게이트 | `bundle_admission_state` **ready=true**, missing/stale 모두 빈 배열 |
| 승인 행 | 7건, 최신 approved_at 2026-11-17T21:52:31Z (작업 후에도 동일, 무변경) |
| JWT/CORS | 38000과 38003이 `JWT_SECRET_KEY` 동일 해시, `AUTH_COOKIE_NAME=benchmark_refresh_local`, `CORS_ALLOW_ORIGINS=http://localhost:5173,http://127.0.0.1:5173` |
| DB | 두 서버 모두 같은 원격 `postgres` 인스턴스, 계정만 다름(38000 `preview_dev_runtime` / 38003 `postgres`) |

플랜 preflight(`GET /preview-test/plan?fixture_ids=1557474&fixture_ids=1557470`)는
`can_collect=true`, `target_ids=[13]`, `fixture_from=2026-11-18T00:00:00+09:00`,
`fixture_to=2026-11-21T15:00:00+00:00`을 돌려줬다.

## 4. 실행 환경 변경 (허용 범위)

38003만 최신 워크트리로 정상 전환했다. 저장소 파일은 **수정하지 않았고**, 임시 런처
`/tmp/run_collect_38003.sh`(mode 0700, 비밀값 미출력, 0600 자격 파일 2개를 source)를 썼다.

- 중지: `PREVIEW_TEST_INTEGRATION` 워크트리의 PID 68684에 SIGTERM → 1초 내 정상 종료.
- 기동: 새 PID **96481**, cwd `preview-api-migration`, port 38003.
- 유지한 것: `JWT_SECRET_KEY`, `AUTH_COOKIE_NAME`, `AUTH_COOKIE_SECURE`, `AUTH_COOKIE_SAMESITE`,
  `CORS_ALLOW_ORIGINS`, `LOCAL_DEV_AUTH_ENABLED=true`.
- 계속 끈 것: `WORKER_SCHEDULER_ENABLED=false`, `HOME_PREVIEW_ENABLED=false`.
- 제품 모델 연결: `PREVIEW_MODEL_PROVIDER=vertex`, `PREVIEW_MODEL_NAME=gemini-3.5-flash`,
  `PREVIEW_MODEL_LOCATION=global`, `PREVIEW_MODEL_LIVE_ENABLED=1`, 자격 JSON은 기존
  `model-live.env`에서만 읽었다.
- `scripts/run_preview_test_collection.sh`는 수정하지 않았다. 이 런처가 모델 설정을
  unset하는 것은 의도된 설계이며, 이번 요청은 자동 생성이 필요하므로 임시 런처로 분리했다.

**결함(내 원인)**: 1차 기동한 런처가 기존 수집 자격 파일의 `API_FOOTBALL_KEY`를
export하지 않았다. 그 결과 수집기가 "API-Football 키가 설정되지 않았습니다"로 즉시 실패했다.
이후 `API_FOOTBALL_KEY`를 export하도록 런처만 고쳐 재기동했다(PID 96481, env에 키 존재 확인).
수집 POST는 그 전에 이미 1회 소모됐다.

## 5. 실행 결과 대조

### 5-1. 수집

| 항목 | 값 |
|---|---|
| 수집ID | `3bee3ed9-3d4b-456d-b2b7-0d531020db3b` |
| 최종 상태 | **failed** |
| 실패 로그 | `RUN_FAILED` / "API-Football 키가 설정되지 않았습니다." (2026-11-18T00:57:50Z) |
| collection_evidence | `stored=0, planned=0, detail_stored=0, partial=true`, `stored_fixture_ids=[]` |

수집은 축구 자료를 한 행도 저장하지 못했다. public 데이터 변경은 0건이다.

### 5-2. 자동 생성 (수집 종료 훅)

수집이 실패했음에도 `_wants_home_preview`가 `test_scope is not None`으로 참이 되어
`run_home_preview_after_sync(collection_status="failed")`가 호출됐다. 승인 게이트는
`ready`였고 후보 2건이 선택됐다.

| 경기 | 자동생성 run ID | 상태 | 품질 | 완료시각 |
|---|---|---|---|---|
| 1557474 | `c8f6c36b-d5a1-4126-9359-36300927062f` | failed | insufficient | 2026-11-18T00:59:26Z |
| 1557470 | `55e19e64-f7ad-4fe5-8d00-98a46a21837c` | failed | insufficient | 2026-11-18T01:01:00Z |

실패 상세는 둘 다 `필수 섹션 본문을 만들지 못했습니다: section_players`다.
`home_preview` 결과: `state=failed`, `candidates=2`, `generated=[]`, `failed=2`,
`approval_gate.state=ready`.

### 5-3. 섹션 결과 (정본 저장)

| run | 저장된 섹션 | 품질 | 본문 길이 |
|---|---|---|---|
| c8f6c36b (1557474) | section_outlook / section_ai_forecast / section_odds | ready / ready / insufficient | 386 / 379 / 0 |
| 55e19e64 (1557470) | section_outlook / section_ai_forecast / section_odds | ready / ready / insufficient | 344 / 621 / 0 |

`section_players`와 `section_availability`는 저장 행이 없다. 아래 두 근거는 **서로 다른
관측 창**이며, 둘을 합쳐야 실제 상태가 된다.

**(가) 실행 트랜잭션 안의 기록은 롤백으로 사라졌다.** 취소 전에 읽은 `preview_attempts`는
run당 4행(`discovery_outlook`, `discovery_people`, `section_outlook`,
`section_ai_forecast`)뿐이었고, `preview_results`·`preview_section_results`는 run당 3행,
모듈 실행도 R3·S1·`section_odds-writer` 3행뿐이었다. 이 실행의 선수/부상 갈래가 만든 행은
커밋되지 않았다.

**(가-정정) 그 4행을 "전송 기록 없음"으로 읽은 것은 틀렸다.** 같은 구간의
`preview_write_audit`(장부)는 실행 트랜잭션과 **별도 세션**으로 커밋되므로 롤백 뒤에도
남아 있다. 그 장부를 읽으면 두 run 모두에서 6개 논리 호출의 전송·응답 수신이 확인된다.

| 근거(테이블/시점) | 무엇을 뜻하는가 |
|---|---|
| `send_charged` `counted=true`, `outcome=pending` (전송 **직전** 예약) | 전송 예약. run당 6행, players/availability 포함 |
| `send_charged` `counted=false`, `outcome=ok`, `http_status=200` (응답 **수신 직후** 보존) | 응답 200 수신. run당 6행, players/availability 포함 |
| `attempt_appended` run당 **4행** (실행 트랜잭션 커밋분) | 커밋된 시도만 남는다. players/availability는 여기 없다 |

즉 `section_players`(`R4`)·`section_availability`(`R2`)의 모델 응답은 **HTTP 200으로
수신됐다**. 없는 것은 전송이 아니라 **커밋된 저장 행**(모듈 실행·섹션 결과·attempts)이다.
이 두 사실이 모순처럼 보이는 이유는 **테이블과 시점이 다르기 때문**이며, 첫 예외가
모델 후처리인지 장부인지 정본 저장인지는 **아직 미확정**이다(6절 2항). 취소로
`preview_attempts` 8행과 원문 아티팩트는 삭제됐지만, 장부 행들은 감사 기록으로 남았다.

- `section_odds`는 모델을 쓰지 않으며 "정규시간 1X2 값이 모두 있는 배당 줄이 없어" insufficient로
  남았다. 진단에 "API-Football 키가 설정되지 않아 배당 보충 읽기를 시작하지 않았습니다"가 있다.
- 선수 정본 2표(`preview_injury_player_sections` 22행, `preview_watch_player_sections` 21행)와
  번역 후보(`preview_player_name_candidates`)는 이번 run에서 신규 행이 0이다. 섹션 결과가
  롤백되었으므로 후보 단계에 도달한 흔적도 커밋되지 않았다.

### 5-4. 홈 반영

| 표면 | 작업 전 | 실패 run 서빙 중 | 두 run 취소 후(현재) |
|---|---|---|---|
| `GET /api/v1/home/fixtures/1557474/document` | run `00d34c23`, `complete=true`, 5섹션 | run `c8f6c36b`, `complete=false`, 2섹션 | run **`00d34c23`**, `complete=true`, 5섹션 전부 ready |
| `GET /api/v1/home/recommendations` | `state=ready`, generated_at 2026-11-17T17:52:46Z | `state=partial`, generated_at 2026-11-18T00:57:54Z | `state=ready`, `served=current`, generated_at 2026-11-17T17:52:46Z |

실패 run이 저장된 직후 홈은 **새 run으로 바뀌었고 즉시 재조회에 반영됐다**. 즉 "수집 →
자동 생성 → 정본 저장 → 홈 노출"의 배선은 실제로 이어져 있다. 다만 그 run은 실패 run이라
5섹션 완전성이 깨진 상태로 홈에 노출됐다. 이 노출은 조정자 승인 아래 지원 cancel API로
두 run을 취소하며 해소됐고, 현재 홈은 이전 정상 run을 서빙한다.

정직하게 구분하면, 이번 실행으로 확인된 것은 **자동 경로가 홈까지 연결된다**는 사실이지
**정상 5섹션 프리뷰가 자동 생성돼 홈에 반영된다**는 사실이 아니다. 후자는 아직 미검증이다.

## 6. 원인과 최소 해결책

1. **첫 실패 경계: 수집 자격 env 누락(내 책임).** 38003을 최신 코드로 옮기면서 기존
   `scripts/run_preview_test_collection.sh` 대신 임시 런처를 썼고, 그 런처가
   `API_FOOTBALL_KEY`를 export하지 않았다. 기존 수집 자격 파일에는 이 키가 있으므로
   런처 한 줄 추가로 해결된다(이미 반영, 재기동 완료). 운영 코드 수정은 불필요하다.

2. **두 번째 실패 경계: 미확정.** players/availability의 저장 행이 커밋되지 않은 것은
   사실이지만, **모델 후처리·장부·정본 저장 중 어디서 난 첫 예외인지는 확정하지 않았다.**
   아래에서 관측 출처와 시점을 구분한다.

   **근거 A. 실행 트랜잭션 안의 행 (undo 이전에 읽음, 이후 삭제됨)**

   - 모듈 실행: 두 run 모두 `section_odds-writer`, `R3`, `S1` **3개**. players(R4)와
     availability(R2) 모듈 실행 행이 없다.
   - 섹션 결과·결과: run당 3행(outlook, ai_forecast, odds). `preview_attempts` run당 4행.
   - 이전 CE-E2E 보고에서 "모듈 실행 3개"라고 적은 것과 이번 CE-FIX 중 인용한 "R2 포함
     4모듈"은 **같은 테이블을 서로 다르게 읽은 것이 아니다.** 4라는 숫자는 두 실행이
     아니라 `SIGNATURE` 재현 실험(가설 주입 시 R2가 살아남은 로컬 재현)에서 나온 값이며,
     실제 두 run의 `module_started` 감사 기록은 둘 다 3건이다. 즉 **실제 run은 3모듈**이고
     4모듈은 로컬 실험값이다. 이전 보고의 3이 맞다.

   **근거 B. 별도 세션 장부 `preview_write_audit` (롤백·undo와 무관하게 보존)**

   출처 구분: 아래 12행 수치는 **원 실행 워커(CE-E2E/CE-FIX 담당)의 읽기 전용 조회 보고**이며,
   독립검토자가 자기 DB 실측으로 확인한 값이 아니다. 독립검토는 문서 diff만 반영했다.
   따라서 "장부에 성공 전송이 있다"는 이 보고서의 서술은 **워커 관측 근거**이고, 독립
   재측정 근거는 아직 없다.

   - 두 run 모두 `send_charged` **12행**: 논리 호출 6개 × (전송 전 예약 1 + 응답 수신 보존 1).
   - 그중 players/availability는 run당 각각 예약 1행(`counted=true`, `outcome=pending`)과
     응답 수신 1행(`counted=false`, `outcome=ok`, `http_status=200`)이 있다.
   - `attempt_appended`는 run당 **4건**뿐이다(outlook, ai_forecast 등). 즉 **장부의 성공
     전송 6건과 실행 테이블의 attempts 4행은 서로 다른 테이블의 서로 다른 시점 값**이다.
     attempts 4행은 실행 트랜잭션이 커밋한 범위이고, 장부 6건은 그와 별도 세션에서 즉시
     커밋된 전송 사실이다. players/availability의 attempts 행이 없는 것은 "전송이 없었다"가
     아니라 **그 갈래의 트랜잭션이 커밋되지 않았다**는 뜻이다.

   **정리하면**
   - 관측된 사실: 두 섹션의 모델 응답은 200으로 수신됐고(장부), 그 섹션들의 모듈 실행·섹션
     결과·attempts 행은 **커밋되지 않았다**. 원문 아티팩트는 undo 이전에 존재했고 이후 삭제됐다.
   - 미확정: 첫 예외가 **모델 후처리**(응답 파싱·처리 결과 계약)인지, **장부 경계**인지,
     **정본 저장**인지. 로컬 재현으로도 특정하지 못했다.
   - 가설(승인되지 않음): `processing.attempts`가 비면 `to_contract_result()`가 `None`이 되어
     `ContractError`로 롤백된다는 경로. 현장 서명과 일치하지만 확정 증거가 없어 **수정하지
     않았다**(조정자 결정: 방어적 수정 미승인).
   - API 키 누락과의 연결은 부정된다. 키가 없어 영향받은 것은 `section_odds`의 배당 보충
     읽기뿐이며 그 섹션 진단에 직접 문구가 남아 있다. players/availability는 저장된 DB 자료와
     수신된 모델 응답만 쓰므로 키와 무관하다.

3. **구조적 관찰(수정하지 않음).** 수집이 실패해도 종료 훅이 자동 생성을 시도한다
   (`collection_status="failed"`로도 호출). 이번 실행에서 그 결과로 실패한 프리뷰가
   홈의 현재 문서를 덮었다. 사용자가 원한 "수집 → 자동 생성" 배선 검증에는 유리했지만,
   수집 실패 시 홈 노출을 막을지는 제품 판단이 필요해 임의로 바꾸지 않았다. 이 현상은
   **별도 실제 결함 후보**로 기록하며, 재실행 성공으로 이 결함이 해결됐다고 말하지 않는다.

## 7. 시험 소유 실패 run 정리(조정자 승인)

근거를 모두 읽은 뒤, 이번 시험이 소유한 두 실패 run만 **지원되는 ADMIN cancel API**로
취소했다. 직접 SQL UPDATE/DELETE는 쓰지 않았다.

- 사전 확인: 두 run을 참조하는 승인 행 0건, 활성 승인 5건의 `reviewed_run_id`는 모두
  이전 run(d96fe824, 493ef4a9, 00d34c23), `preview_pipeline_runs` 행 0건, 섹션 결과의
  `supersedes_section_result_id` 전부 `None`, 결과의 `supersedes_result_id` 전부 `None`.
  즉 다른 실행·활성 승인이 참조하지 않는 이번 소유 데이터뿐이었다.
- `GET /api/v1/admin/preview/runs/{id}/undo`: 두 run 모두 `state=cancellable`,
  `can_cancel=true`, `blocked_reason=null`. 제거 예정은 run당 원문 35~36건, 스냅샷 1,
  시도 4, 결과 3, 섹션 결과 3, 모듈 실행 3이며 선수 섹션 3표는 0건이었다.
- `POST /api/v1/admin/preview/runs/{id}/undo` (HTTP 200, 두 건):
  - `55e19e64-f7ad-4fe5-8d00-98a46a21837c` → cancelled_at 2026-11-18T01:27:43Z,
    removed 원문 35·스냅샷 1·시도 4·결과 3·섹션 3·모듈 3. kept `preview_runs`,`preview_write_audit`.
  - `c8f6c36b-d5a1-4126-9359-36300927062f` → cancelled_at 2026-11-18T01:27:50Z,
    removed 원문 36·스냅샷 1·시도 4·결과 3·섹션 3·모듈 3. kept 동일.
- 관리 수집 run `3bee3ed9-...`의 실패 기록은 **보존**했다(취소하지 않음).
- 취소 후 확인: 두 run `status=cancelled`(quality insufficient 유지), 남은 섹션 결과 0행,
  승인 행 7건·최신 approved_at 2026-11-17T21:52:31Z **무변경**, 활성 관리 수집 run 0건.
- 홈 복구 확인: `GET /api/v1/home/fixtures/1557474/document` → run
  `00d34c23-a1d6-43d0-b8e2-fe9962184f3b`, `complete=true`, 5섹션 전부 `ready`
  (players 8aa0ffaf…, availability c8a19c2f…, outlook 6620a3f2…, odds 31b75881…,
  ai_forecast 6c6b1556…). `GET /api/v1/home/recommendations` → `state=ready`,
  `served=current`, generated_at 2026-11-17T17:52:46Z. 실패 run이 홈을 대체했던 상태는
  해소됐다.

## 8. 런처 결함과 재실행 준비 근거

- 원인: 1차 임시 런처가 기존 수집 자격 파일의 `API_FOOTBALL_KEY`를 export하지 않았다.
- 조치: 런처에 `API_FOOTBALL_KEY`를 자격 파일에서 필수로 받아 export하는 한 줄을 넣고
  38003을 재기동했다. 비밀값은 출력하지 않았고, 존재 여부만 확인했다(프로세스 env에 존재).
- 모델 설정(비밀값 비노출 대조): `PREVIEW_MODEL_PROVIDER=vertex`,
  `PREVIEW_MODEL_NAME=gemini-3.5-flash`, `PREVIEW_MODEL_LOCATION=global`,
  `PREVIEW_MODEL_LIVE_ENABLED=1` — 38000과 같은 값이며 자격 JSON은 기존 `model-live.env`.
- DB reader 설정: HEAD 코드는 옛 per-name DSN을 읽지 않는다(`app/preview/config.py`의
  호환 property가 전부 원래 `DATABASE_URL`을 돌려준다). 그래서 런처는
  `PREVIEW_DEV_/IDENTITY_/FIXTURES_/NAMES_/STATS_DATABASE_URL`을 unset해 다른 계정 분기를
  남기지 않았다. 실제 D0 스냅샷은 `readable=true`, `roster` 55행, `standings` 2행,
  `teams` 2행을 읽었고 `team_id_space=internal`이었다.
- 재실행 준비 판정: 수집 경로는 준비됐다(수집 자격 키 포함). 다만 players/availability의
  첫 예외가 **미확정**이라, 같은 조건으로 다시 실행하면 같은 증상이 날 수 있다(추정).
  그 원인 확정과 수정은 이번 단위 범위 밖이며 A로 미착수다. 이번 CE-FIX는 그 실패가
  홈을 덮지 않게 하는 B와, 다음번에 예외 종류를 남기는 C만 다룬다.

## 9. 미검증 / 막힘

- **미검증**: 5섹션 `complete=true` 홈 일치, 선수 정본 2표/번역 후보의 신규 기록,
  섹션별 result_id→홈 문서 id 대조.
- **막힘**: players/availability의 커밋된 행이 왜 없는지(첫 예외의 위치)를 확정하지 못했다.
  모델 후처리·장부·정본 저장 중 어디인지는 **미확정**이며, 서버 stdout에도 예외가 남지 않는
  구조(`_section_node`가 예외를 상태로만 반환)였다. 조정자 결정으로 로컬 재현 추가탐색은 종료.
- **보류**: 재수집 1회는 조정자 결정 대기다(추가 POST 미실행).

## 10. 프로세스 유지 상태와 변경 범위

- 38003: PID **96481** (최신 워크트리 `preview-api-migration`, `API_FOOTBALL_KEY` 포함,
  scheduler off, `HOME_PREVIEW_ENABLED=false`, 제품 모델 설정 연결됨).
- 38000: PID 38299 (작업 전과 동일, 손대지 않음).
- 5173 → 38000, `/api/v1/admin/management/preview-test` → 38003 프록시 그대로.
- 5174/38001, 5175/38002, 8000, 5176/38004는 건드리지 않았다.
- 임시 런처 `/tmp/run_collect_38003.sh`(0700), 로그 `/tmp/collect_38003.log`.

**저장소 변경 파일은 시점별로 다르다.** "변경 파일 1개/0건"은 CE-E2E 첫 실행 시점의
사실이고, 그 뒤 CE-FIX 단위가 제품 2파일·검사 2파일을 더 바꿨다. 합산하지 않고 나눠 적는다.

| 시점 | 제품 코드 | 검사 | 문서 | 지속 설정 |
|---|---|---|---|---|
| CE-E2E 첫 실행(보고서 5a2b9ab까지) | 0건 | 0건 | 이 보고서 1개 | 0건(임시 런처·프로세스 env만) |
| CE-FIX 단위(eb17f76, 55b601f) | 2파일(`home_preview_document.py`, `bundle_pipeline.py`) | 2파일(`test_home_preview_document.py`, `test_bundle_pipeline.py`) | 이 보고서 | 0건 |
| 이번 C/D 보완(본 항목) | 1파일(`bundle_pipeline.py`, 라벨·주석) | 1파일(`test_bundle_pipeline.py`, 기대값) | 이 보고서 | 0건 |

`scripts/run_preview_test_collection.sh`는 어느 시점에도 수정하지 않았다.

## 11. CE-FIX 수정 단위 결과 (2026-11-18)

계획서 `docs/superpowers/plans/2026-11-18-collection-home-fix-task.md`의 A~D 중
**A는 미재현으로 미착수**, **B·C·D는 완료**했고, 독립검토 B 통과 뒤 C/D 지적 3건을
**최소 보완**했다(아래 "독립검토 지적 보완").

### B. 실패 실행이 홈 공개 문서를 대체하지 않게 수정

`app/services/home_preview_document.py`의 공개 후보 필터 한 곳만 바꿨다.

- `_NON_PUBLIC_RUN_STATUSES = frozenset({"cancelled", "failed"})` 도입.
- `_is_eligible_document_run`과 `_read_runs` SQL이 같은 집합을 쓴다(추천 목록과 document가
  같은 `_load_selection_context` → `select_document`를 쓰므로 두 표면의 선택은 계속 동일).
- **바꾸지 않은 것**: 부분 성공(성공 상태인데 일부 섹션 미표시)·미승인 필터·구 기록·구성본
  호환. 실패 실행의 기록은 관리자 진단에 그대로 남는다.

검증(대표 2건, 각각 현재 사용자 실패와 연결):
- `test_failed_run_never_replaces_the_previous_healthy_document` — 과거 정상 + 새 failed →
  과거 정상 선택. **수정 전 red, 수정 후 green** 확인.
- `test_newer_successful_run_still_wins_over_older_one` — 새 정상 성공 → 새 문서 선택 유지.

### C. 섹션 실행 예외 종류 보존

`app/preview/bundle_pipeline.py`에서 섹션 갈래 예외 시 `failure_kind`(예외 클래스 이름)와
`failure_stage`(`section_execution`)를 상태에 남기고, 마무리 단계가 이를 실행 기록의
`failure_detail`에 덧붙인다. **원문 메시지·SQL·DSN·비밀값은 넣지 않는다**(종류와 라벨만).

**한계(중요).** `_section_node`의 `try`는 작성기 호출·모델 전송·응답 후처리·정본 저장을
**한꺼번에** 감싼다. 그래서 이 경계는 "어느 세부 단계에서 났는지"를 구분할 수 없다. 라벨을
`section_write`로 두면 저장 단계로 단정하는 잘못된 신호가 되므로, 세부 단계를 특정하지 않는
`section_execution`(전체 섹션 실행)으로 바꿨다. 세부 단계 계측 확장은 이번 범위가 아니다.

검증: `test_section_save_exception_kind_survives_in_run_failure_detail` — 저장 계약 위반을
주입하면 `ContractError@section_execution`이 남고, `section_write` 문자열이 없으며,
`postgres`·원문 조각이 없음을 확인. **수정 전 red, 수정 후 green**.

### A. 미재현(추정 수정 금지 준수)

로컬 `55432/preview_mp01_test`에서 다음을 모두 시도했으나 "모듈 실행·섹션 행이 함께
사라지는" 현장 서명을 만들지 못했다: actor_id 0/1 이상, 실제 응답 모양(한글명·player_ref·
evidence 없음), DB가 선수를 못 찾는 AI 후보 경로, 이름 해석기 부착/미부착. 부착 시 players
ready, 미부착 시 insufficient지만 **행은 저장**됐다. 계획서 지침대로 추정 수정을 하지 않고
조정자 판단을 요청했다(msg_157270a040a0).

조정자 결정(msg_cb527a542423): **가를 선택**했다. A는 미재현·원인미확정으로 유지하고,
`processing.attempts`가 비었다는 가설의 방어적 수정은 **승인하지 않는다**. 로컬 재현 조합
추가탐색과 검사 확대도 여기서 종료한다. 따라서 A는 코드 변경 0건이며, 저장 실패의 첫 예외는
**미확정**으로 남긴다(5-3·6-2절의 확정 표현 철회 반영).

### 증거 출처 정리(모순 해소)

앞선 보고들에서 섞여 보이던 세 숫자의 출처를 구분한다.

| 값 | 출처 | 해석 |
|---|---|---|
| 모듈 실행 3개(`section_odds-writer`, R3, S1) | 실제 두 run의 `preview_module_executions`·`module_started` 감사 | **실제 run 값** |
| 모듈 4개(R2 포함) | CE-FIX 중 `SIGNATURE` 재현 실험(가설 주입) | **로컬 실험값**, 실제 run 아님 |
| `attempts` 전부 `ok` | 취소 전 `preview_attempts` 4행(rename 전 관측) | 실행 트랜잭션 **커밋분만** |
| "응답 장부 없음" | 같은 시점 `preview_attempts`만 본 판단 | 틀렸다. `preview_write_audit`에는 성공 행이 있다 |

정리하면 **attempts 4행(커밋분)과 장부 12행(별도 세션)은 모순이 아니라 서로 다른 테이블의
서로 다른 시점 값**이다. 장부가 사실이라면 players/availability는 전송·응답 수신이 있었고,
커밋된 저장 행만 없다. 첫 예외의 위치(모델 후처리/장부/정본 저장)는 여전히 미확정이다.

### 직접 실행한 검사 (로컬 테스트 DB, 단일 파일)

| 명령 | 결과 |
|---|---|
| `pytest tests/unit/test_home_preview_document.py -q` | 19 passed |
| `pytest tests/preview/test_bundle_pipeline.py -q` | 17 passed, 1 skipped |
| `pytest tests/preview/test_player_section_integration.py -q` | 9 passed |
| `pytest tests/unit/test_preview_api_storage_migration.py -q` | 7 passed |

대상은 `preview_mp01_test`(127.0.0.1:55432)이며 `_dbguard`가 루프백·`*_test` 이름을 먼저
검사한다. 운영 URL 테스트·초기화·동시 pytest 없음. 추가 수집·모델 호출·승인 변경·서버
재시작은 0회다.

## EDITING STOPPED

**시점별로 구분한다.** CE-E2E 첫 실행 단위에서는 코드·테스트 수정 0건이었고, 그 뒤 CE-FIX
단위가 제품 2파일(`home_preview_document.py`, `bundle_pipeline.py`)과 검사 2파일을 수정했으며,
이번 C/D 보완이 `bundle_pipeline.py` 라벨·주석과 그 검사 기대값 1건을 고쳤다. 어느 시점에도
빌드 설정 수정은 0건이다.

공통으로 유지한 것: 승인 행·계정·기존 테이블 변경 0건, 운영 연결에 pytest/초기화/삭제 0건.
DB 쓰기는 (a) 승인된 정상 수집 1회, (b) 자동 생성 경로가 만든 preview_dev 행, (c) 조정자
승인으로 지원 API를 통해 취소한 이번 소유 run 기록뿐이다.

**서버 상태 표기 정정.** 위 10절의 38003 상태(진단 라벨 포함)는 **CE-FIX 코드를 서버에
반영한 상태가 아니다.** 38003 재기동은 0회였고, 그 프로세스는 CE-FIX 이전 코드를 그대로
실행 중이다. 즉 새 실패가 나면 `section_execution` 라벨은 아직 찍히지 않는다. 이 보완의
적용은 조정자가 배정할 서버 재기동 단위에서 일어난다.

A는 미착수이고, 모델 후처리/장부/정본 저장 중 첫 예외는 **미확정**이다. 남은 작업(원인 확정,
재수집 1회, 38000·38003 재기동)은 조정자 배정 대기다.

### 독립검토 지적 보완 (4건)

독립검토가 C/D에 남긴 3건과, 55b601f 문서 diff 검토 뒤 추가로 지목된 D 잔존 1건을 최소
보완했다. B는 변경하지 않았다.

1. **C 라벨이 저장 단계를 단정했다.** `_section_node`의 `try`는 작성기 호출·모델 전송·
   응답 후처리·정본 저장을 한꺼번에 감싸므로 어느 단계인지 구분할 수 없는데 라벨이
   `section_write`여서 저장 단계로 읽혔다. → `section_execution`(전체 섹션 실행)으로
   바꾸고 주석·검사 기대값·이 보고서를 같은 이름으로 맞췄다. 세부 단계는 확정할 수 없다는
   한계를 위 C절에 명시했다. 예외 종류 보존과 비밀 원문 미기록은 그대로다.
2. **D의 변경 파일 수 표기가 시점을 뭉갰다.** 10절·EDITING STOPPED의 "변경 파일 1개/0건"은
   CE-E2E 첫 실행 시점의 사실인데, CE-FIX가 제품 2파일·검사 2파일을 더 바꿨다. → 시점별
   표로 분리했다.
3. **서버 반영 오해 소지.** 38003 재기동은 0회이므로 CE-FIX 라벨은 아직 실행 중 코드에
   없다. → EDITING STOPPED에 명시했다.
4. **D 잔존 문구(55b601f 검토 뒤 추가 지적).** 요약 18행이 여전히 "정본 저장 단계에서
   사라졌다"고 단정했고, 275행·352행의 "변경 0건" 주장이 시점 구분 없이 남아 있었다.
   → 18행은 "커밋된 저장 행이 없다 + 첫 예외는 미확정"으로 고쳤고, 275행은 시점별 표로,
   352행(EDITING STOPPED)은 시점 구분 문장으로 바꿨다(앞선 커밋에서 이미 반영, 이번에
   18행을 마저 정정). 아울러 장부 12행 수치는 **원 실행 워커의 관측값이며 독립검토자의
   DB 실측이 아님**을 6-2절에 명시했다.

검증은 기존 C 대표검사 1건만 실행했다: `1 passed`
(`tests/preview/test_bundle_pipeline.py::test_section_save_exception_kind_survives_in_run_failure_detail`,
로컬 `preview_mp01_test`, `_dbguard` 통과, 동시 pytest 없음). 52건 전체·변형 반복은 이번
지시대로 하지 않았다. 서버·실 API·모델·승인 호출은 0회다.

## 12. CE-E2E2 실제 재실행 결과 (2026-11-18, 실패)

계획서 `docs/superpowers/plans/2026-11-18-collection-home-e2e-second.md`에 따라 재시작 후
수집 API를 1회 실행했다. **수집은 성공했고 자동 생성은 실패**했으며, 이번에는 **첫 예외의
성격과 위치를 확정**했다. 코드·검사·승인 변경은 0건이다.

### 12-1. 서버 (소유 확인 후 재시작)

| 서버 | 이전 PID | 새 PID | cwd | 역할/자격 |
|---|---|---|---|---|
| 38000(홈) | 38299 | **57643** | 이 워크트리 | `preview_dev_runtime`: `public.fixture` UPDATE=**false**, `preview_dev.preview_runs` INSERT=true |
| 38003(진단·수집) | 96481 | **58185** | 이 워크트리 | `postgres`: fixture UPDATE=true, management_run INSERT=true, preview_runs INSERT=true |

두 서버 모두 이전과 같은 런처·같은 설정으로 재시작했다. 5173/다른 포트/8000/뉴스 환경은
건드리지 않았다. 공통 확인: `JWT_SECRET_KEY` 해시 동일, `AUTH_COOKIE_NAME=benchmark_refresh_local`,
CORS 동일, `WORKER_SCHEDULER_ENABLED=false`, `HOME_PREVIEW_ENABLED=false`,
`LOCAL_DEV_AUTH_ENABLED=true`. 제품 모델은 `vertex`/`gemini-3.5-flash`/`global`,
`PREVIEW_MODEL_LIVE_ENABLED=1`. 38003에는 `API_FOOTBALL_KEY`와
`PREVIEW_MODEL_CREDENTIALS_JSON`이 존재함을 비밀값 미노출로 확인했다.

### 12-2. 사전 확인과 요청

- 진행 중 수집 0건, admission `ready=true`(missing/stale 없음), 두 경기 모두 NS,
  승인 행 7건·최신 approved_at 2026-11-17T21:52:31Z(작업 후에도 동일), DB now 2026-11-18T02:54:59Z.
- 정상 ADMIN 세션(계정 id 1, role `ADMIN`)으로 2026-11-18T02:55:34Z에
  `POST /api/v1/admin/management/runs/preview-test` **1회** 실행. HTTP 200,
  수집 실행ID **`5cf4b3f6-affd-4fb4-80db-fe3ec8ed634a`**.
- 요청(비밀값 없음): `target_ids=[13]`, `fixture_from=2026-11-18T00:00:00+09:00`,
  `fixture_to=2026-11-21T15:00:00+00:00`, `preview_fixture_ids=[1557474,1557470]`,
  `generate_after_collection=true`. 중복 POST·별도 bundle/section 생성 POST는 0회다.

### 12-3. 수집 결과 (성공)

- 상태 `succeeded`, stage `수집 결과 확인`, 종료 2026-11-18T03:00:19Z.
- 대상 item: `saved=55`, `total=55`, `failed=0`.
- `collection_evidence`: `counts={stored:6, planned:6, unverified:0, detail_stored:6}`,
  `partial=false`, `stored_fixture_ids=[1557474, 1557468, 1557476, 1557470, 1557467, 1557471]`.
- 즉 **수집 경로는 정상 동작**했다(API 키 누락 재발 없음).

### 12-4. 자동 생성 결과 (실패)

| 경기 | 생성 run ID | 상태 | 품질 | 종료 |
|---|---|---|---|---|
| 1557474 | `639cb2a0-1d6e-4687-a77c-85ba0b5d2de4` | failed | insufficient | 2026-11-18T02:58:42Z |
| 1557470 | `176271d7-f79a-403d-82e1-90b38cf81590` | failed | insufficient | 2026-11-18T03:00:19Z |

`home_preview`: `state=failed`, `generated=[]`, `skipped=[]`, 실패 사유 원문:

```
필수 섹션 본문을 만들지 못했습니다: section_players
(섹션 작성 예외: section_availability=ProgrammingError@section_execution,
 section_players=ProgrammingError@section_execution)
```

**C(진단 보존)가 실제로 작동했다.** 이전 실행에서는 이 정보가 남지 않아 원인 확정이
막혔지만, 이번에는 예외 종류가 실행 기록에 남았다.

커밋된 섹션(두 run 동일 모양): outlook·odds·ai_forecast 3개.
`section_players`·`section_availability`는 모듈 실행·섹션 결과 행이 없다.
장부(`preview_write_audit`)에는 두 섹션 모두 `outcome=ok`, `http_status=200` 응답 수신이
남아 있어 **모델 호출은 성공**했고 실패는 그 뒤다.

### 12-5. 첫 예외 확정 — 원인

**확정된 원인: 세 선수 정본 표에 대한 INSERT 권한 부재.**

| 표 | 소유자 | ACL에 `postgres=` 존재 | `postgres` INSERT |
|---|---|---|---|
| `preview_watch_player_sections` | `preview_dev_app` | **없음** | **false** |
| `preview_injury_player_sections` | `preview_dev_app` | **없음** | **false** |
| `preview_player_name_candidates` | `preview_dev_app` | **없음** | **false** |
| `preview_section_results` | `preview_dev_app` | 있음 | true |
| `preview_runs` | `preview_dev_app` | 있음 | true |
| `preview_results`·`preview_attempts`·`preview_artifacts`·`preview_write_audit`·`preview_source_snapshots`·`preview_module_executions` | — | 있음 | true |

- 세 선수 표의 ACL은 `{preview_dev_app=arwdDxtm/preview_dev_app, preview_dev_runtime=arwd/...}`로
  **`postgres` 항목이 아예 없다.** 나머지 preview 표는 모두 `postgres=arwd/...`를 갖는다.
- `postgres`의 `preview_dev_app` 멤버십은 `inherit_option=false`이고 `postgres`는
  슈퍼유저가 아니므로(rolsuper=false, rolbypassrls=true) **멤버십으로 상속되지 않는다.**
- 그래서 수집 프로세스가 `postgres` 자격으로 선수 표에 INSERT하는 순간
  `permission denied for table ...`가 나고, psycopg는 이를
  `InsufficientPrivilege`(→ `ProgrammingError`의 하위 클래스)로 올린다. 이것이 실행 기록의
  `ProgrammingError@section_execution`과 정확히 일치한다.
- 저장 경로 순서(`_save_draft`: 모듈 실행 → 결과 → 섹션 결과 → `save_player_section`)상
  선수 표 INSERT에서 예외가 나면 그 세션의 **모든 행이 롤백**된다. 그래서 outlook/odds/
  ai_forecast만 남고 선수 섹션 행은 물론 모듈 실행·시도 행도 사라진다(관측과 일치).
- 역할별 실측: `preview_dev_runtime`(38000이 쓰는 역할) INSERT=**true**,
  `preview_dev_app`(표 소유자) INSERT=**true**, `postgres`(38003이 쓰는 역할) INSERT=**false**.
  즉 **표 자체는 정상이고, 자격에 따라 갈린다.** 관리자 경로로 만든 기존 성공 run
  `00d34c23`이 선수 행을 정상 저장한 것과 모순되지 않는다. 실패는 수집 경로(`postgres`)에서만 난다.

**부수 확인(확정 아님)**: 관측 창 안에서 `preview_watch_player_sections`의 마지막 INSERT는
2026-11-17T17:52:46Z로, 이번 두 run 이후 새 행이 없다. 위 권한 진단과 일치하는 방향이다.

### 12-6. 정상 홈 보호 확인 (B 동작)

| 표면 | 결과 |
|---|---|
| `GET /api/v1/home/fixtures/1557474/document` | run **`00d34c23`**, `complete=true`, 5섹션 전부 ready(본문 444/305/398/294/443자) |
| `GET /api/v1/home/recommendations` | `state=ready`, `served=current`, generated_at 2026-11-17T17:52:46Z |
| `GET /api/v1/home/fixtures/1557470/document` | run `4efe5b1e`, `complete=true`, `available` |

**새 실패 run(`639cb2a0`, `176271d7`)은 홈을 대체하지 못했다.** B(실패 run 공개 후보 제외)가
실제 환경에서 의도대로 동작했다. 1557470이 추천 목록에 없더라도 document가 정상이므로
불일치로 판정하지 않는다(계획서 6항).

### 12-7. 실패 기록 보존 / 하지 않은 일

- 두 실패 run에 대해 **undo·cancel을 하지 않았다**. `cancelled_at=null`, `failure_detail` 보존.
- 원문 아티팩트(run당 raw_request 16, raw_response 16~17, normalized_transform 2),
  attempts 4행, `preview_write_audit` 12행이 모두 남아 있다.
- 실모델 재호출·추가 POST·코드 수정·검사 추가·승인 변경·migration·계정 변경은 **0회**.
- 정상 홈을 보호하기 위한 직접 SQL·승인 우회는 하지 않았다.

### 12-8. 성공 판정

**이번 단위는 실패다.** 수집 API 1회에서 실모델 호출까지는 이뤄졌으나, 새 정본 커밋이
선수 섹션에서 막혀 새 run이 홈 문서가 되지 못했다. HTTP 200·수집 성공·이전 run 서빙을
E2E 성공으로 표현하지 않는다. 다음 조치는 **권한 부여(GRANT)** 이며, 이는 기존 테이블의
권한 변경이므로 이번 승인 범위(코드·검사·승인 변경 0) 밖이다. 별도 배정이 필요하다.

## 13. CE-E2E3 실제 재실행 결과 (2026-11-18, **성공**)

CE-ACL(권한 보완) 이후 같은 계획서 범위로 재실행했다. **이번에는 사용자가 정의한 E2E가
끝까지 성립했다**: 기존 수집 API 1회 → 실모델 자동 생성 → 새 preview_dev 정본 커밋 →
새 run이 공개 홈 문서·추천이 됨. 코드·검사·승인 변경은 0건이다.

### 13-1. 시작 상태 (재기동 0회)

- HEAD `fe3373b2a7d973093bd9edaf8bfe7f54d5f52ec4`(제품 `a4cbb71`), 워크트리 clean.
- 38000 = PID **57643**, 38003 = PID **58185**. 둘 다 이 워크트리, `woolee` 소유.
  두 프로세스는 11:53~11:54에 시작해 제품 커밋(`a4cbb71`, 11:45)과 진단 라벨 커밋
  (`46baf79`, 11:47) 이후에 떴다. **권한 부여는 DB 객체이므로 재기동이 필요 없다.**
- 공통 설정: `JWT_SECRET_KEY` 해시 동일, `AUTH_COOKIE_NAME=benchmark_refresh_local`, CORS 동일,
  `WORKER_SCHEDULER_ENABLED=false`, `HOME_PREVIEW_ENABLED=false`,
  `LOCAL_DEV_AUTH_ENABLED=true`, 모델 `vertex`/`gemini-3.5-flash`/`global`,
  `PREVIEW_MODEL_LIVE_ENABLED=1`. 38003은 `API_FOOTBALL_KEY`·모델 자격 존재(비밀값 미노출).
- 권한 확인: 선수 3표 `postgres` INSERT/UPDATE/DELETE = true(부여 결과 유지).
- 사전 상태: 진행 중 수집 0건, admission `ready=true`, 두 경기 NS, 승인 7건
  (최대 approved_at 2026-11-17T21:52:31Z), 계획 `can_collect=true`,
  기간 2026-11-18T00:00:00+09:00 ~ 2026-11-21T15:00:00+00:00.

### 13-2. 요청 (1회)

정상 ADMIN 세션(계정 id 1, role ADMIN)으로 2026-11-18T03:24:56Z에
`POST /api/v1/admin/management/runs/preview-test` **1회**, HTTP 200.
수집 실행ID **`72937d21-17c7-4447-9497-9b76fc930d1d`**.
`target_ids=[13]`, `preview_fixture_ids=[1557474,1557470]`, `generate_after_collection=true`.
별도 bundle/section 생성 POST 0회, 승인 변경 0회, 반복 호출 0회.

### 13-3. 수집 (성공)

`status=succeeded`, 종료 2026-11-18T03:30:04Z, item `saved=55/55`, `failed=0`.
`collection_evidence`: `counts={stored:6, planned:6, unverified:0, detail_stored:6}`,
`partial=false`, `stored_fixture_ids=[1557474, 1557468, 1557476, 1557470, 1557467, 1557471]`.

### 13-4. 자동 생성 (성공 — 이번이 첫 성공)

`home_preview`: `state=finished`, `failed=[]`, `approval_gate={state:ready, missing:[], stale:[]}`.

| 경기 | 생성 run ID | 상태 | 품질 |
|---|---|---|---|
| 1557474 | **`9e4e1052-d532-4397-b27d-fe4818731145`** | succeeded | ready |
| 1557470 | **`e22339c4-4436-4163-996e-da0ddf2993bc`** | succeeded | ready |

두 run 모두 모듈 실행이 `R2, R3, R4, S1, section_odds-writer` **5개**다. 이전 실패 run에서
빠져 있던 `R2`(부상)·`R4`(주목 선수)가 이번에는 정상 실행·저장됐다. 권한 부여가 실제 원인
판정과 일치함을 실측으로 확인한 지점이다.

### 13-5. 새 정본 (섹션 5개 + 선수 정본 표)

| 경기 | players | availability | outlook | odds | ai_forecast |
|---|---|---|---|---|---|
| 1557474 | `291fa5bf-57d7-44ce-867c-9bb044451b2f` (ready, 377자) | `71e9c47d-b9d0-41c5-840f-b0f78bbdfc10` (ready, 416자) | `8fed3e7e-4b55-4850-8abc-ef37efdafd58` (ready, 428자) | `6be04e76-12d5-43cc-9028-05291f72c7a3` (ready, 294자) | `dfc7694c-f5bd-418b-9d50-2ecbfea68d9b` (ready, 509자) |
| 1557470 | `1c877097-1541-41ea-b927-be0318ab302a` (ready, 365자) | `d617f7dd-f2f1-44b7-8238-ae83989223d4` (ready, 289자) | `e0fb753f-4235-4ed9-81f8-cb9550b91116` (ready, 354자) | `8bb24f5c-6c5e-4194-83dc-5ee6697e4016` (ready, 294자) | `9789b4d8-d105-4f54-9ce6-90aff9de88dd` (ready, 431자) |

선수 정본 표(이번 단위의 직접 목표):

| run | `preview_watch_player_sections` | `preview_injury_player_sections` | `preview_player_name_candidates` |
|---|---|---|---|
| 9e4e1052 (1557474) | **1행** | **1행** | 0행 |
| e22339c4 (1557470) | **1행** | **1행** | **1행** |

번역 후보 0행은 정상이다. 그 run은 슬롯 이름이 모두 DB 한글명(`db_ko`)으로 확인돼
AI 후보를 만들 필요가 없었다(후보가 필요한 슬롯이 있을 때만 생성된다).

### 13-6. 홈 반영 (새 run이 실제로 서빙됨)

| 표면 | 결과 |
|---|---|
| `GET /api/v1/home/fixtures/1557474/document` | run **`9e4e1052-d532-4397-b27d-fe4818731145`**, `complete=true`, 5섹션 전부 ready |
| `GET /api/v1/home/recommendations` | 1557474 `state=ready`, `served=current`, generated_at 2026-11-18T03:26:42Z |
| `GET /api/v1/home/fixtures/1557470/document` | run **`e22339c4-4436-4163-996e-da0ddf2993bc`**, `complete=true`, 5섹션 ready |

문서의 `section_result_id`가 위 13-5 표의 새 ID와 **문자 단위로 일치**한다. 추천 목록에
1557470이 없더라도 그 경기의 document가 정상이므로 불일치로 보지 않는다(계획서 6항).

### 13-7. 실제 본문·사진 확인

- 주목 선수 본문(1557474): 4명(엘링 홀란드 / 라얀 셰르키 / 알렉산더 츄카 이워비 / 오스카 보브)이
  `선정 선수:`·`선정 이유:` 두 줄 형식으로 표시되고, `structured.players`에
  `external_player_id`와 `photo_url`(예: `https://media.api-sports.io/football/players/1100.png`)이
  실려 있다.
- 부상·결장 본문: 팀별로 상태(결장 확정/출전 불확실)와 영향이 표시되고, `structured.injuries` 4건에
  `photo_url`이 있다.
- AI 경기 전망 본문: 실제 시즌 성적·결장자·상대 흐름을 근거로 서술됐다.
- **추가 승인 없이 반영**됐다. 승인 행은 7건·최대 approved_at 2026-11-17T21:52:31Z로 **무변경**이며,
  이번 run은 기존 승인 버전으로 자동 생성됐다(approval_gate ready).

### 13-8. 보존·불변 확인

- 이전 실패 run `639cb2a0`(1557474), `176271d7`(1557470)은 **그대로 보존**했다
  (`status=failed`, `cancelled_at=null`). 이번 성공 run과 별개 행이다.
- 승인 7건·계정·public 데이터 무변경. 코드·검사·마이그레이션 변경 0건.
- 실패 run 대비 이번 시도만의 차이는 **선수 3표 권한 부여(CE-ACL)** 하나다.

### 13-9. 판정

**성공.** 근거는 수집 API 1회에서 실모델 자동 생성이 두 경기 모두 성공하고, 새 정본 섹션
5개와 선수 정본 표가 커밋되며, 그 새 run이 홈 문서·추천으로 실제 서빙되고 본문·사진이
표시된 것이다. HTTP 200이나 수집 성공만으로 판정하지 않았고, 이전 정상 홈(`00d34c23`)과
다른 새 run ID임을 확인했다.
