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
`section_players`/`section_availability`는 **모델 호출에 성공했지만 정본 저장 단계에서
사라졌다**(장부·원문·attempts로 확인). 이 둘은 서로 다른 원인이고, 두 번째는 API 키
누락과 무관하다.

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
남아 있다. 그 장부를 읽으면 두 run 모두에서 6개 논리 호출의 성공 전송이 확인된다.

| 근거 | 무엇을 뜻하는가 |
|---|---|
| `send_charged` `counted=true`, `outcome=pending`, note "전송 전 예약. 후처리·롤백과 무관하게 남는다." | 전송 **직전** 예약. players/availability 포함 12행(run당 6) |
| `send_charged` `counted=false`, `outcome=ok`, `http_status=200`, note "응답 수신 직후 보존. 실행 트랜잭션 롤백과 무관하다." | **응답 수신 성공**. players/availability 포함 12행(run당 6) |

즉 `section_players`(`R4`)·`section_availability`(`R2`)는 **모델 응답을 정상 수신했다**
(HTTP 200). 없는 것은 전송이 아니라 **저장 행**이다. 취소로 `preview_attempts` 8행과 원문
아티팩트는 삭제됐지만, 이 장부 행들은 감사 기록으로 남아 있어 위 사실을 사후에 확인할 수 있다.

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

2. **두 번째 실패 경계: 선수 섹션 정본 저장 단계(호출 전 제외도, 호출 실패도 아님).**
   조정자 지시대로 장부와 실행 기록을 대조해 세 경우를 갈랐다. 결론은 **모델 호출은
   성공했고, 그 뒤 정본 저장(save) 단계에서 갈래가 죽었다**이다.

   - **호출 전 제외 아님(장부 근거).** `preview_write_audit`의 `send_charged` 행에
     `section_players`와 `section_availability`의 **counted=true 예약 4행**(run당 2:
     players 1, availability 1)이 남아 있다. 조기 반환 경로라면 `budget.cancel_call`만
     남고 charged 행이 생기지 않는다.
   - **호출 실패 아님(장부 + 원문 근거).** 같은 장부에 두 섹션의 `outcome=ok`,
     `http_status=200`, `counted=false`(응답 수신 보존) 행이 **4행** 남아 있다. 같은 실행의
     원문 아티팩트도 원래 있었다: `1d646f07...`(players, 3247바이트, `players` 4명·
     한글 라벨 6건), `4d645651...`(availability, 4988바이트, `injuries` 4건). 그 아티팩트와
     `preview_attempts` 행은 이후 지원 cancel로 삭제됐지만, 장부는 롤백·삭제와 무관하게
     남는다는 것이 그 행의 note에 명시돼 있다.
   - **확정된 사실(장부·행 근거).** 이 실행에서 players/availability의 모듈 실행 행과
     섹션 결과 행이 **커밋되지 않았다**(모듈 실행은 R3/S1/section_odds-writer 3개,
     섹션 결과는 outlook/ai_forecast/odds 3개). 즉 실패 지점은 전송이 아니라 그 뒤의
     저장 경로다.
   - **추정(확정 아님).** 저장 경로의 어느 검사가 막았는지는 **로컬 재현에서 확정하지
     못했다**. 후보 검사군은 ①`_validate_parent_ownership`의 소유·`output_contract_version`
     일치, ②`save_section_candidates`의 NOT NULL, ③4개 `*_translation_candidate_id` FK
     순서, ④`processing.attempts`가 비면 `to_contract_result()`가 `None`이 되어
     `ContractError`로 롤백되는 경로다. ④는 현장 서명(players 모듈 실행·섹션 행 동시 부재)
     과 일치하지만 가설일 뿐이다. 이번 CE-FIX에서 actor 0/7, 실제 응답 모양, AI 후보 경로,
     이름 해석기 유무를 모두 시도했으나 로컬(55432 `preview_mp01_test`)에서는 실패가
     재현되지 않았다(계획서 A의 "재현이 안 되면 추정 수정 금지"에 따라 A는 미착수).
   - **API 키 누락과의 연결은 부정된다.** 키가 없어 영향받은 것은 `section_odds`의
     배당 보충 읽기뿐이다(그 섹션 진단에 직접 문구가 남아 있다). players/availability는
     저장된 DB 자료와 이미 성공한 모델 응답만 쓰므로 키와 무관하다. 따라서
     **"키만 고치면 두 번째 실패도 해소된다"는 추정은 근거가 없다.**

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
- 재실행 준비 판정: 수집 경로는 준비됐다. 다만 **선수 섹션 저장 결함이 남아 있어** 같은
  조건으로 다시 실행하면 동일하게 필수 섹션 누락으로 실패할 것으로 본다(추정).
  이 결함의 원인 확정과 수정은 새 코드 변경이므로 이번 단위에서 하지 않았다.

## 9. 미검증 / 막힘

- **미검증**: 5섹션 `complete=true` 홈 일치, 선수 정본 2표/번역 후보의 신규 기록,
  섹션별 result_id→홈 문서 id 대조.
- **막힘**: 선수 섹션 저장 경로에서 어느 검사가 막았는지 저장 기록만으로 특정하지 못했다.
  서버 stdout에 예외가 남지 않는 구조(`_section_node`가 예외를 상태로만 반환)도 확인했다.
- **보류**: 재수집 1회는 조정자 결정 대기다(추가 POST 미실행).

## 10. 프로세스 유지 상태와 변경 범위

- 38003: PID **96481** (최신 워크트리 `preview-api-migration`, `API_FOOTBALL_KEY` 포함,
  scheduler off, `HOME_PREVIEW_ENABLED=false`, 제품 모델 설정 연결됨).
- 38000: PID 38299 (작업 전과 동일, 손대지 않음).
- 5173 → 38000, `/api/v1/admin/management/preview-test` → 38003 프록시 그대로.
- 5174/38001, 5175/38002, 8000, 5176/38004는 건드리지 않았다.
- 저장소 안 변경 파일: 이 보고서 1개. `scripts/run_preview_test_collection.sh`는 수정하지
  않았다. 지속 설정 변경 0건(임시 런처와 프로세스 env만).
- 임시 런처 `/tmp/run_collect_38003.sh`(0700), 로그 `/tmp/collect_38003.log`.

## 11. CE-FIX 수정 단위 결과 (2026-11-18)

계획서 `docs/superpowers/plans/2026-11-18-collection-home-fix-task.md`의 A~D 중
**A는 미재현으로 미착수**, **B·C는 수정·검증 완료**, **D는 위 5-3/6절 정정으로 완료**했다.

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

### C. 저장 경계 예외 종류·단계 보존

`app/preview/bundle_pipeline.py`에서 섹션 갈래 예외 시 `failure_kind`(예외 클래스 이름)와
`failure_stage`(`section_write`)를 상태에 남기고, 마무리 단계가 이를 실행 기록의
`failure_detail`에 덧붙인다. **원문 메시지·SQL·DSN·비밀값은 넣지 않는다**(종류와 단계만).

검증: `test_section_save_exception_kind_survives_in_run_failure_detail` — 저장 계약 위반을
주입하면 `ContractError@section_write`가 남고, `postgres`·원문 조각이 없음을 확인.
**수정 전 red, 수정 후 green**.

### A. 미재현(추정 수정 금지 준수)

로컬 `55432/preview_mp01_test`에서 다음을 모두 시도했으나 "모듈 실행·섹션 행이 함께
사라지는" 현장 서명을 만들지 못했다: actor_id 0/1 이상, 실제 응답 모양(한글명·player_ref·
evidence 없음), DB가 선수를 못 찾는 AI 후보 경로, 이름 해석기 부착/미부착. 부착 시 players
ready, 미부착 시 insufficient지만 **행은 저장**됐다. 계획서 지침대로 추정 수정을 하지 않고
조정자 판단을 요청했다(msg_157270a040a0).

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

코드·테스트·빌드 설정 수정 0건. 승인 행·계정·기존 테이블 변경 0건. 운영 연결에
pytest/초기화/삭제 0건. DB 쓰기는 (a) 승인된 정상 수집 1회, (b) 자동 생성 경로가 만든
preview_dev 행, (c) 조정자 승인으로 지원 API를 통해 취소한 이번 소유 run 기록뿐이다.
CE-FIX 단위에서는 B·C 수정과 해당 검사만 했고 A는 미착수다. 남은 작업(선수 섹션 저장
결함의 실제 원인 확정, 재수집 1회 여부)은 조정자 결정 대기다.
