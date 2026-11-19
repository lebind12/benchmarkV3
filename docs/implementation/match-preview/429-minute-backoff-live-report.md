# RB-APPLY 실제 반영·E2E 결과 (2026-11-19)

작성 2026-11-19 04:2x KST. DeepSeek 실행 워커(task_1666cabd2e5c / ctx_a3042121de81).
세션 모델 `deepseek-ai/deepseek-v4.1-flash-1017`·`hive`·`high`. 명세
`docs/superpowers/plans/2026-11-19-rb-home-e2e.md`.

## 판정: **실패(부분완료)** — 커밋·push 금지 조건 유지

- fixture **1557470(첼시–리즈)**: 새 run `3cbd7a41` **5섹션 전부 ready**, 정본 저장,
  홈 동일 `section_result_id` 확인 → **통과**.
- fixture **1557474(맨시티–풀럼)**: 새 run `2c8cc12d` **failed**, 섹션 행 0개,
  홈은 여전히 **이전 run `4471fc0a`**를 서빙 → **실패**.
- 따라서 "두 경기 모두 5섹션 정상 표시" 조건 미충족. **커밋·push 0**, 보고서 untracked.

## 1. 착수 확인

- 제품 해시가 명세와 일치: `provider.py` 8cc28284dad9d216, `retry.py` c197dc368fe3dbad,
  `modules/bundle_sections.py` 3cb500297099f484.
- HEAD `f6c7876`, staged RB6파일 + 보완 unstaged. root `collection-home-e2e-report.md`
  미접촉, `refs/backup/rb-review-79a5418` 보존.

## 2. 서버 재기동 (38000/38003만)

| 포트 | PID | 기동 | 비고 |
|---|---|---|---|
| 38000 | 93324 | 04:02:06 | 제한 런타임, 현재 트리 |
| 38003 | 93911 | 04:02:35 | 수집 역할, 현재 트리 |

- 설정 유지 확인(값 비노출): `PREVIEW_MODEL_PROVIDER=vertex`, `NAME=gemini-3.5-flash`,
  `LOCATION=global`, `LIVE_ENABLED=1`, `WORKER_SCHEDULER_ENABLED=false`,
  `HOME_PREVIEW_ENABLED=false`, `AUTH_COOKIE_NAME=benchmark_refresh_local`.
- `API_FOOTBALL_KEY`·모델 자격 전달됨(존재만 확인, 값 미출력).
- 수정본 반영 확인: 서버 cwd가 이 워크트리이고 `retry.cpython-311.pyc`가 소스(03:51)보다
  뒤에 생성됨. 별도 인터프리터에서 `RATE_LIMIT_WAIT_SECONDS=(60,300,600)`,
  `RATE_LIMIT_MAX_SENDS=4`, `last_failure_was_rate_limited` 존재 확인.
- 5173은 기존 Vite 유지. 8000/5174/5175/5176/38001/38002/38004 미접촉.

## 3. 사전 확인

- ADMIN 세션 유효(refresh 200, role ADMIN). 토큰 직접 발급·추출 없음.
- 두 경기 `NS`, 킥오프 1557474 `2026-11-21T12:30Z`, 1557470 `2026-11-21T15:00Z`.
- 진행 중 수집 0건, 승인 7건(최대 approved_at 2026-11-17T21:52:31Z).
- 계획(2026-11-19 기준): `can_collect=true`, target_ids `[13]`,
  기간 `2026-11-19T00:00:00+09:00 ~ 2026-11-21T15:00:00+00:00`.

## 4. 실행 (POST 1회)

2026-11-18T19:04:13Z(04:04 KST) `POST /api/v1/admin/management/runs/preview-test` **1회**,
HTTP 200, 수집 실행ID **`3d2a117a-69ee-446e-9948-afcc6543410d`**,
`generate_after_collection=true`. **재POST·재전송 0회.**

수집 결과: `status=succeeded`, stage `메인 프리뷰 생성`, item `saved=55/55`, `failed=0`.
`collection_evidence.counts = {stored: 6, planned: 6, unverified: 0, detail_stored: 6}`,
`partial=false`, `stored_fixture_ids = [1557474, 1557468, 1557476, 1557470, 1557467, 1557471]`.

> 구분: 위 `55`는 **처리 단위 수**이고, 실제 저장된 경기는 **6건**이다(서로 다른 값).

## 5. 생성 결과

| 경기 | 새 run | 상태 | 섹션 |
|---|---|---|---|
| 1557470 첼시–리즈 | **`3cbd7a41-90a7-452e-83a3-4c638cba0bc7`** | **succeeded / ready** | **5개 전부 ready** |
| 1557474 맨시티–풀럼 | **`2c8cc12d-2466-4994-8a61-dc82cd2b14b7`** | **failed / insufficient** | **0개** |

### 5-1. 통과한 1557470 (`3cbd7a41`)

| 섹션 | 결과 ID | 품질 | 본문 |
|---|---|---|---|
| players | `27a3770d-768d-424c-981d-cb259bbe2254` | ready | 336자 |
| availability | `e295edf0-edcb-40bc-96b7-31c18dbff7c7` | ready | 254자 |
| outlook | `0b8ecefa-0334-4ae1-bf6c-038cb562d9b1` | ready | 276자 |
| odds | `9011c97f-4ccc-426f-bb9b-93e355e8d8b9` | ready | 294자 |
| ai_forecast | `30621f9b-6629-4ea5-80c2-2101125294ea` | ready | 404자 |

정본: watch 1행, injury 1행, 후보 1행(`review_status=pending`, `846c15c9-…`).
홈 문서 `complete=true`이고 위 5개 `section_result_id`가 **홈 응답과 완전히 일치**함을 확인했다.

### 5-2. 실패한 1557474 (`2c8cc12d`)

- run `status=failed`, `quality=insufficient`,
  `failure_detail = "필수 섹션 본문을 만들지 못했습니다: section_ai_forecast, section_players"`.
- **`preview_section_results` 0행, `preview_module_executions` 0행.**
- `preview_attempts` 2행(둘 다 D1 `discovery_people`·D2 `discovery_outlook`, `ok/200`).
- `preview_artifacts` 12개(요청 6·응답 6). 응답 본문은 모두 **정상 내용**(오류 payload 없음):
  발견 요약 2건(19452·17332 bytes × 2), coverage 1324 bytes, standings facts 687 bytes.
- 같은 시각에 1557470은 정상 진행했다. 즉 공급자 전면 장애가 아니다.
- 19:05:55 시작 → 19:07:25 종료(약 90초). 그 사이 **섹션 단계가 한 번도 실행되지 않았다.**

**확정한 것:** 이 실패는 429 시도 상한 소진이 **아니다**(attempts 2건 모두 200 ok,
error 0건). 승인 부재도 아니다.
**확정하지 못한 것:** 조사(D1/D2) 성공 후 섹션 단계로 넘어가지 않은 **원인**은 이번
관측만으로 특정하지 못했다. 서버 로그에 예외 traceback이 남지 않았고(uvicorn access 로그만
기록, 워커 스레드 예외는 미기록), `preview_pipeline_runs`에도 해당 실행 행이 없어
어느 경계에서 끊겼는지 코드로 확정하지 않았다. **추정을 원인으로 보고하지 않는다.**

## 6. 429 재시도 실동작 (이번 실행에서 실제 발생)

1557470의 `section_players`에서 **429가 실제로 발생**했고 새 정책이 그대로 동작했다.

| ordinal | 결과 | HTTP | 분류 | wait_ms | 시작 |
|---|---|---|---|---|---|
| 0 | error | 429 | rate_limited | — | 19:08:23 |
| 1 | error | 429 | rate_limited | 60000 (60초) | 19:09:37 |
| 2 | **ok** | 200 | — | 300000 (300초) | 19:14:40 |

즉 60초 → 300초 대기 후 3번째 전송에서 성공했고, 그 덕분에 1557470은 5섹션을 모두
채웠다. **실대기 구간이 실제 실행에서 작동함을 확인**했다(600초 구간은 이번엔 미사용).

## 7. 홈·화면

| 표면 | 1557470 | 1557474 |
|---|---|---|
| `/api/v1/home/fixtures/{id}/document` | 새 run `3cbd7a41`, 5섹션 | **이전 run `4471fc0a`, 3섹션** |
| recommendations | (항목에 1557474만 노출, `ready`·generated_at 17:17Z=이전 실행) | 동일 |

- 1557474가 새 결과를 서빙하지 않으므로 **홈 5섹션 동일성 조건은 검증 불가**다.
- 관리자 `/admin?tab=preview` 실화면 확인은 이 실패 상태에서 보류했다(새 문서가 없어
  비교 대상이 없다). 로딩 잔존 여부를 새 run 기준으로 확인할 수 없다.

## 8. 실패 원인 후보(확정 아님, 추가 실행 금지)

- 명세 금지사항에 따라 **추가 생성·재실행·undo·코드수정·승인·커밋·push를 하지 않았다.**
- 다음 판단에 필요한 질문: 1557474의 조사 산출물은 정상인데 섹션 노드로 전이되지 않은
  이유가 (a) 그래프 전이/분기 조건, (b) 워커 스레드 예외의 조용한 종료, (c) 동시 실행
  중 자원 경합 중 무엇인지. 이 중 어느 것도 이번 증거로 확정되지 않았다.

## 9. 변경·상태

- 코드·검사·프롬프트 편집 **0**. root 문서·Plans 미접촉.
- 커밋 **0**, push **0**. 이 보고서는 **untracked**로만 존재한다.
- 서버 38000/38003은 재기동 상태로 유지.
- 승인 행 7건 무변경(신규 승인 0, 삭제 0). DB 직접 쓰기 0(실제 쓰기는 승인된 수집/생성 내부만).
