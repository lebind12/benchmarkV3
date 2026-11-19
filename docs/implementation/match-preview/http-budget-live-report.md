# HB-LIVE: HTTP 보호 정책 반영·두 경기 5섹션 E2E

작성 2026-11-19. DeepSeek 실행 워커(task_a67dae8db1a1 / ctx_7db76ca80728).
세션 모델 `deepseek-ai/deepseek-v4.1-flash-1017`·`hive`·`high`. 하위 워커 0.
명세 `docs/superpowers/plans/2026-11-19-http-budget-live.md`.

## 판정: **API 기준 5섹션 통과 / 실제 브라우저 확인 미완**

두 경기 모두 새 run에서 **5섹션 전부 ready·본문 존재·정본 저장·홈 ID 일치**를
확인했다. 이전 실행에서 배당이 예산 때문에 비었던 문제는 **재현되지 않았다**.
다만 **실제 브라우저 화면 확인은 도구 권한 문제로 못 했다**(아래 §6). 이 보고서는
근거 인계이며 **커밋·push 0**이다.

## 1. 사전 확인

- 제품 6해시가 명세와 **정확히 일치**: retry `4ba65558…`, retrieval `28244024…`,
  bundle_pipeline `da8ea8f1…`, provider `8cc28284…`, bundle_sections `3cb50029…`,
  home_preview_collection `14aa2a4a…`. HEAD `f6c7876`.
- 서버 재기동(두 프로세스만): 38000 pid 96946 → **48999**(16:17:31),
  38003 pid 97837 → **49094**(16:17:51). 5173·8000·5174·5175·5176·38001·38002·38004 유지.
- 설정 유지(값 비노출): `vertex`/`gemini-3.5-flash`/`global`,
  `WORKER_SCHEDULER_ENABLED=false`, `HOME_PREVIEW_ENABLED=false`, `API_FOOTBALL_KEY` 존재.
- 로드된 정책 확인: `HTTP_LOCAL_SHARE=10`, `HTTP_SHARED_SHARE=10`, `HTTP_TOTAL_LIMIT=30`,
  `RATE_LIMIT_WAIT_SECONDS=(60,300,600)`, `RATE_LIMIT_MAX_SENDS=4`(AI 정책 불변).
- ADMIN 세션 유효. 두 경기 `NS`. 활성 수집 0.
  plan: `can_collect=true`, `target_ids=[13]`, `2026-11-19T00:00+09:00 ~ 2026-11-21T15:00Z`.

## 2. 실행 (POST 1회)

- **2026-11-19T07:18:57Z**(16:18:57 KST), `POST /runs/preview-test`,
  `generate_after_collection=true`, **1회**.
- 수집 실행ID **`2a7b8453-f396-4ddd-8e5d-6b38315bfa14`**. 재POST·재전송 0회.
- 수집 `succeeded`. `home_preview.state=finished`, **`failed=[]`**.

## 3. 생성 결과 — 두 run 모두 succeeded, 5섹션 전부 ready

| 경기 | 새 run | 상태 | 섹션 |
|---|---|---|---|
| 1557474 City–Fulham | **`cf5572b9-0a88-40d6-bbea-6d733e1aceab`** | succeeded/ready | **5/5 ready** |
| 1557470 Chelsea–Leeds | **`d29d8899-5349-4ba7-afb8-62d69aa4c64c`** | succeeded/ready | **5/5 ready** |

| 경기 | players | availability | outlook | odds | ai_forecast |
|---|---|---|---|---|---|
| 1557474 | 392자 | 308자 | 392자 | **294자** | 460자 |
| 1557470 | 367자 | 363자 | 353자 | **294자** | 462자 |

**직전 실행과의 차이(핵심).** 직전 run `92d0fdb3`(1557470)은 배당이
`insufficient`·본문 0이었고 사유가 `API 요청 예산(24회)을 모두 사용했습니다`였다.
이번 두 run의 배당은 **본문 294자·ready**이고 진단에 예산 소진 사유가 **없다**
(`접근 가능한 공개 배당 표에서 … 확인하지 못했습니다`만 남아 실제 표 부재 사유).
→ 기사 수집이 배당 몫을 먹던 간섭이 **이번 실행에서는 나타나지 않았다.**

## 4. 홈·정본

| 표면 | 1557474 | 1557470 |
|---|---|---|
| home document run | `cf5572b9` (새 run) | `d29d8899` (새 run) |
| 홈 섹션 수 | **5** | **5** |
| 저장 ID = 홈 ID | **5개 전부 일치** | **5개 전부 일치** |
| 비정상 quality | 0 | 0 |

정본: 두 run 모두 watch 1·injury 1, 후보 0/1. 승인 행 **7건 무변경**.

## 5. 로직별 HTTP 사용 — **직접 대조 미완(정직 기록)**

- 영속된 번들 `network_usage`는 `http_used=16`(1557474)·`19`(1557470),
  `http_failed`/`redirects` 포함 값이 남아 있다.
- 그러나 **`http_owners`(소유자별 사용)와 `http_total_limit`은 이 실행의 영속 기록에
  남지 않았다**(`budget_state` 행 없음, 아티팩트에 `http_owners` 문자열 0건).
  그래서 "기사 N회·배당 M회·공유 잔량"을 **사후 증거로 직접 대조하지 못했다**.
- 같은 이유로 번들 `network_usage.http_limit`은 여전히 옛 값 **24**로 기록된다
  (판정에는 쓰지 않았다는 명세 조건대로, 이 값을 30 정책 근거로 쓰지 않았다).
- **대신 사용한 근거**: 배당 섹션이 실제로 ready·294자로 생성됐고 예산 소진 사유가
  없다는 **결과 증거**다. 이것은 "배당 요청이 나갔다"는 간접 증거이며, 소유자별
  수치 대조를 대체하지 않는다.

## 6. 실제 브라우저 확인 — **미완**

- 홈·관리자 프리뷰탭 실화면을 열어 팀명·본문·5섹션·사진을 확인하려 했으나,
  `orca computer get-app-state`가 **"Accessibility permission is required"**로 거부했다.
  `orca computer permissions --json`은 accessibility·screenshots 모두 `granted`로
  보고해 **상태가 서로 모순**이며, 두 번째 시도(window-index)도 같은 오류였다.
- 따라서 **실제 브라우저 기준 통과를 주장하지 않는다.** 페이지 ID·팀명·본문 안정 확인은
  **미확인**이다. API 응답(home document/recommendations)만으로 실화면 통과라고 하지 않는다.

## 7. 미확정 / 남은 일

- **과거 City collection 첫 예외는 여전히 미확정**이다. 이번 실행에서 City는 정상
  생성됐고 `collection_failure`도 발생하지 않았다. 이 수정을 그 오류의 해결로 부르지 않는다.
- 실제 브라우저 확인(권한 문제)과 로직별 HTTP 수치의 영속 대조가 남았다.
- 두 경기 5섹션을 **API 기준으로는 충족**했으나, 사용자 게이트(실화면 포함)를
  만족했다고 단정하지 않는다. **commit/push 0** 유지.

## 8. 상태

- 제품·검사·설정 파일 편집 **0**. reset/stash/stage/commit/push **0**.
- root `collection-home-e2e-report.md`·Plans 미접촉, backup ref `79a5418` 보존,
  staged RB6 + 보완 unstaged 유지. 이전 run 증거 전부 보존.
- DB 직접 쓰기·승인행 변경·pytest·빌드·테스트 초기화 **0**. 서버는 재기동 상태로 유지.
- 이 보고서는 untracked.

## 9. 조정자 실제 화면 확인 — 2026-11-19 16:38 KST

워커의 접근성 오류 뒤 조정자는 CUA native Orca 접근에 성공했다. 브라우저 호스트 연결은 unavailable이었으나 Orca 앱의 실제 AX/스크롤/스크린샷으로 아래를 관측했다. 기존 ADMIN 세션을 사용했고 새 로그인·생성·수집·승인 POST는 없었다.

- 관리자 `/admin?tab=preview&previewRun=cf5572b9-0a88-40d6-bbea-6d733e1aceab`: City 본문 5섹션, 사진, 하단 배당까지 스크롤 가능. 홈 대조 목록의 5개 section_result_id 모두 일치.
- City 홈 `/?fixtureId=1557474`: 맨체스터 시티–풀럼 팀명과 최신 본문, AI 전망·주목 선수·부상/결장·외부 매체 전망·배당 5섹션을 AX 및 화면으로 확인. 저장 표시 11.19 16:20 KST.
- 관리자 `/admin?tab=preview&previewRun=d29d8899-5349-4ba7-afb8-62d69aa4c64c`: Chelsea 본문 5섹션과 홈 대조 5개 section_result_id 모두 일치. 기텐스 사진 없음은 연결 미확인 표시이며 본문 누락이 아니다.
- **미통과**: Chelsea 관리자 '홈에서 확인'을 누르면 URL은 `/?fixtureId=1557470`이지만 홈은 추천 1/1 맨체스터 시티–풀럼을 표시한다. 로딩 완료 후에도 경기 상세 링크는 `/fixtures/1557474`, 본문은 City의 홀란드·셰르키·세메뇨 내용이다. URL만 보고 Chelsea 실화면 성공으로 세지 않는다. 추천 목록은 2026.11.21 가장 가까운 경기 한 건만 표시한다. 선택 로직의 코드 원인은 이번 관측에서 조사하지 않았다.

관리자 화면에서 대조한 ID:

| workflow | City cf5572b9 | Chelsea d29d8899 |
|---|---|---|
| section_players | 68db8daf-5472-416b-8110-66a3da8b92bc | a4b9ed8e-da1f-4c26-b7ea-0c6a9cde7d0b |
| section_availability | 2373310a-385a-45ee-a392-d78701a3794c | 189be142-e94b-4341-a94d-2fc26a8bcb66 |
| section_outlook | 5526dea5-9d62-4f11-b496-a5792da26736 | 2f7f527b-b49d-4f6d-be7b-e4eef1b97b59 |
| section_odds | 4d10727d-2878-47e8-b38e-87c1045eb787 | 0596cc61-edd3-4509-864b-9d9cba4e00b0 |
| section_ai_forecast | 1cc0d93d-4b11-4d53-9b27-06e92a346191 | 5f9387d0-61a9-47cf-bbf2-139f4563a6c1 |

결론: 접근성 문제는 조정자 경로로 우회했으나 두 경기 실제 홈 표시 게이트는 아직 미통과다. 사용자 지시대로 **commit/push 없이 대기**한다. 제품 수정·테스트 반복·추가 모델 호출은 하지 않았다. HTTP 소유자별 수치 미영속과 원 City 예외 미확정은 그대로다. HEAD f6c7876 및 staged/unstaged 상태를 유지했다.
