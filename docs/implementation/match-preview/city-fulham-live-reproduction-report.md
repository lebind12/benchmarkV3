# City–Fulham 재현 1회 실행 결과 (CF-LIVE)

작성 2026-11-19. DeepSeek 실행 워커(task_d8075a24fc20 / ctx_2562d7d4d841).
세션 모델 `deepseek-ai/deepseek-v4.1-flash-1017`·`hive`·`high`. 하위 워커 0.
명세 `docs/superpowers/plans/2026-11-19-city-fulham-live-reproduction.md`.

## 판정: **원래 실패가 재현되지 않았다** (1557474 이번엔 성공)

이번 실행에서 City(1557474)는 **5섹션 전부 ready로 성공**했다. 따라서 **과거
`2c8cc12d`의 collection 실패 원인은 이번 관측으로 확정되지 않았고, "해결됐다"고
단정하지 않는다.** 재현 실패를 성공으로 꾸미지 않기 위한 반복 호출은 하지 않았다.

## 1. 사전 확인

- 제품 5해시가 명세와 **정확히 일치**: bundle_pipeline `5b72240f…`, home_preview_collection
  `14aa2a4a…`, provider `8cc28284…`, retry `c197dc36…`, bundle_sections `3cb50029…`.
  HEAD `f6c7876`, 미커밋 변경 그대로 실행.
- 서버 재기동(두 프로세스만): 38000 pid 93324 → **96946**(05:28:28), 38003 pid 93911 →
  **97837**(05:28:48). `bundle_pipeline.cpython-311.pyc`가 소스보다 뒤에 생성돼 현재 진단이
  로드됨을 확인했다. 5173/8000/5174/5175/5176/38001/38002/38004 유지.
- 설정 유지(값 비노출): `vertex`/`gemini-3.5-flash`/`global`, `LIVE_ENABLED=1`,
  `WORKER_SCHEDULER_ENABLED=false`, `HOME_PREVIEW_ENABLED=false`, `API_FOOTBALL_KEY` 존재.
- ADMIN 세션 유효. 두 경기 `NS`(1557474 11-21T12:30Z, 1557470 11-21T15:00Z). 활성 수집 0.
  plan: `can_collect=true`, `target_ids=[13]`, `2026-11-19T00:00+09:00 ~ 2026-11-21T15:00Z`.

## 2. 실행 (POST 1회)

- 시각 **2026-11-18T20:29:42Z**(2026-11-19 05:29:42 KST).
- `POST /api/v1/admin/management/runs/preview-test`, `generate_after_collection=true`, **1회**.
- 수집 실행ID **`720806ac-c890-4e0f-acb5-d32c4b5321db`**. 재POST·재전송 0회.
- 단건 bundle API로 전환하지 않았다(진단이 management에 보존되는 같은 경로 유지).

## 3. 수집

`status=succeeded`, stage `수집 결과 확인`, 종료 2026-11-18T20:35:38Z.
item `saved=55/55`. `home_preview.state=finished`, **`failed=[]`**.

> 55는 **처리 단위 수**이며 실제 저장 경기 수와 다른 값이다(별도 미인용).

## 4. 생성 결과 — 두 run 모두 succeeded

| 경기 | 새 run | 상태 | 섹션 |
|---|---|---|---|
| 1557474 City–Fulham | **`74d4cb09-2b07-4a50-a1e7-7a1dd6818428`** | succeeded / ready | **5개 ready** |
| 1557470 Chelsea–Leeds | **`92d0fdb3-c70f-43bf-bb8e-dff0a598bdc4`** | succeeded / ready | 4 ready + **odds 1건 insufficient** |

### 4-1. 1557474 (과거 실패 경기) — 이번엔 5섹션 성공

| 섹션 | 결과 ID | 품질 | 본문 |
|---|---|---|---|
| players | `8f7f5654-8f46-47c2-be72-9bf99514e793` | ready | 383자 |
| availability | `a5fbc21c-04ad-42d0-9de1-585b93da2139` | ready | 273자 |
| outlook | `b534e984-9cc9-493e-8989-c2b8caf33315` | ready | 337자 |
| odds | `480be83f-e6da-482e-836c-9c778feb8c0c` | ready | 294자 |
| ai_forecast | `55b1f19e-b40a-40ed-bc24-c97f27754159` | ready | 613자 |

정본: watch 1, injury 1, candidates 0. `failure_detail=None`,
`home_preview.failed=[]` → **collection_failure 기록 자체가 없다**(진단이 남을 실패가
발생하지 않았다). 즉 **진단이 동작할 기회가 없었고, 원인도 재현되지 않았다.**

### 4-2. 1557470 — odds 1건 미충족(원 버그와 무관한 예산 소진)

`section_odds` = `insufficient`, 본문 0. 사유:
`정규시간 1X2 값이 모두 있는 배당 줄이 없어 …`, 진단에
`API 요청 예산이 없어 제공자 배당 읽기를 보내지 않았습니다: API 요청 예산(24회)을 모두 사용했습니다.`

attempts를 보면 `section_outlook`이 **429 → 재시도 → 200**으로 성공했고(내부 60초 대기
정책 작동), 그 과정에서 API 예산 24회를 소진해 배당 보충 읽기가 나가지 못했다.
**배당은 선택 섹션이므로** 이 미충족은 기존 설계대로 "생략 + 관리자 사유"다.
과거 City 실패(collection 단계)와는 **다른 원인**이며, 코드 수정 없이 그대로 둔다.

## 5. 홈·정본

| 표면 | 1557474 | 1557470 |
|---|---|---|
| home document | run `74d4cb09`, **5섹션**, complete=true | run `92d0fdb3`, **4섹션**, complete=true |
| section_result_id 일치 | 홈 5개 = 저장 5개 **일치** | 홈 4개 = 저장 4개 일치(odds 없음) |

**`complete=true`는 5섹션 보장이 아니다** — 1557470이 그 증거다(완전성 판정은 players·
ai_forecast 두 섹션만 본다). 승인 행 7건·최대 approved_at **무변경**(신규 승인 0, 삭제 0).

## 6. 미확정 / 다음 단계

- **원인 미확정 유지.** 이번 1회는 실패를 재현하지 못했으므로 `2c8cc12d`의 첫 예외는
  여전히 모른다. 진단(`collection_failure`)은 이번에 실제로 발동하지 않았다.
  `sqlstate`가 psycopg3 래퍼에서 `None`인 점은 참고사항이며 원인 판정에 쓰지 않았다.
- 재현되지 않았으므로 **성공으로 원인 해결을 주장하지 않는다.** 과거 실패가 간헐적인지,
  코드/자료 상태가 달라졌는지는 이 증거로 판단할 수 없다.
- 두 경기 5섹션 E2E는 **아직 미통과**(1557470 odds 1건 누락). 사용자 게이트에 따라
  **commit/push 0**.

## 7. 상태

- 코드·검사·설정 파일 편집 **0**. root 문서·Plans·backup ref·staged RB6 보존.
- reset/stash/stage/commit/push **0**. 승인행 추가·undo·cancel·기존 증거 삭제 **0**.
- 테스트DB 초기화·pytest·빌드 추가 실행 **0**. 서버는 재기동 상태로 유지.
- 이 보고서는 untracked.
