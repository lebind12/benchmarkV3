# PF-B 후속 — API-Football 키 연결과 `/odds` 실제 1회 읽기

작성: 2026-11-12 KST. 담당: DeepSeek 구현 워커(PF-B 후속). 실제 모델 `deepseek-ai/deepseek-v4.1-flash-1017`(dsh-tui, Max 유지).
이 후속의 소유 범위: **외부 키 설정 파일**과 **이 보고서**뿐이다. backend 제품 파일·frontend·`Plans.md`·저장 결과·DB·서버는 수정하지 않았다.

## 1. 결론

| 항목 | 결과 |
|---|---|
| Koyeb `benchmark-v3/api` 배포에 API-Football secret 참조 존재 | **있음** (`API_FOOTBALL_KEY` → 같은 이름 secret) |
| 기존 secret 재사용(새 키 생성·회전 없음) | **완료.** 0600 `~/.config/match-preview/preview-dev.env`에 `API_FOOTBALL_KEY` 1줄 추가 |
| 기존 값 보존 | **완료.** `DATABASE_URL`·JWT·모델 설정 등 9개 키 값 변경 0(길이 비교) |
| 비밀값 노출 | **없음.** 터미널·보고서·저장소에 값 미출력. 임시 0600 파일은 사용 후 삭제, 검증용 백업도 삭제 |
| fixture 1557474 `/odds` 실제 읽기 | **1회 수행.** HTTP 200, 응답 1건, 북메이커 9곳, pre-match 1X2 9행 |
| 저장된 배당 섹션 갱신 | **하지 않음**(지시대로). 필요한 실행 경로만 §5에 정리 |
| 모델 호출·전체 생성·DB 쓰기·서버 재시작 | **0회** |

## 2. 배포 설정 확인(키 이름만, 값 미출력)

- 앱: `benchmark-v3` = HEALTHY
- 서비스: `api` (id `5178062c-…-e96df3d672cb`), 활성 배포 `6b6fbe4f-92eb-4cbe-9a09-68e1e9082287`
- 배포 `definition.env` 14개 항목 중 `API_FOOTBALL_KEY`가 **secret 참조**로 설정되어 있다(`secret: API_FOOTBALL_KEY`, 리터럴 값 없음).
- 조직 secret 목록에도 `API_FOOTBALL_KEY`(SIMPLE, 2026-05-19 생성)가 있다.

즉 애플리케이션은 이 값을 `Settings.api_football_key`로 읽는 기존 경로를 그대로 쓴다(`app/core/config.py:99`, env 접두사 없음).

## 3. 로컬 설정 반영

- 대상: `~/.config/match-preview/preview-dev.env` (mode 유지 `0600`)
- 추가: `API_FOOTBALL_KEY=<값>` 1줄. **값은 이 보고서에 쓰지 않는다.**
- 비밀값 처리 절차:
  1. `koyeb secrets reveal API_FOOTBALL_KEY` 출력을 **umask 077 + chmod 600** 임시 파일로만 받았다.
  2. 기존 env 파일을 `0600` 백업으로 복사한 뒤 키 1줄을 append하고 mode를 다시 `0600`으로 고정했다.
  3. 검증 후 **임시 파일과 백업 파일을 모두 삭제**했다(값이 든 사본을 남기지 않는다).
- 보존 검증(값 미출력, 키 이름·길이만 비교): 기존 9개 키가 모두 남아 있고 값 길이가 동일하다. 추가된 키는 `API_FOOTBALL_KEY` 하나다.
- 기존 런처 전달 경로 확인: `scripts/run_benchmark_dev.sh`는 자격 증명 파일을 `set -a`로 source하므로 **파일에 있는 키가 자동 export**된다. `unset` 목록(89~92행)은 옛 `PREVIEW_*_DATABASE_URL` 계열뿐이고 `API_FOOTBALL_KEY`는 포함되지 않는다. 따라서 **다음 기동 때 별도 스크립트 수정 없이** 앱이 키를 읽는다.
- 지시대로 **서버는 재시작하지 않았다.** 현재 실행 중인 8000 프로세스(기동 시점 키 없음)는 이 값을 아직 갖지 않는다.

## 4. `/odds` 실제 1회 읽기 (fixture 1557474)

`/tmp` 임시 스크립트로 기존 `daily_sync.api.ApiFootballClient`(`max_retries=1`)를 그대로 사용해 **한 번** 요청했다.

| 관측 | 값 |
|---|---|
| 키 설정 인식 | `Settings.api_football_key` 존재 True(불리언만 확인) |
| HTTP 상태 | **200** (클라이언트 예외 없음) |
| 봉투 `errors` | `[]` |
| 봉투 `results` | `1` |
| 응답 레코드 | 1건, `fixture.id = 1557474` (요청 경기와 일치) |
| 레코드 `update` | `2026-11-08T12:52:18+00:00` |
| 북메이커 수 | **9** |
| pre-match 1X2 행 | **9** (모두 `home/draw/away` 세 라벨 존재) |
| 업체 예 | William Hill, Bet365, Marathonbet, Betfair, BetVictor, Pinnacle … |
| 업체별 `book.update` | **없음(None)** — 레코드 update만 있다 |

### 1X2 값 채택 결과

`read_provider_odds()` 결과는 `sent=1`, `available=False`, `quotes=0`이다.

사유: **신선도 기준(6시간) 초과**. 응답의 기준 시각이 `2026-11-08T12:52:18Z`로, 수집 시점 대비 **94.2시간** 지났다. 실제 진단 문장:

```
William Hill: 수집 시점 기준 94.2시간 지난 배당이라 채택하지 않았습니다(기준 6시간).
Bet365: 수집 시점 기준 94.2시간 지난 배당이라 채택하지 않았습니다(기준 6시간).
Marathonbet: 수집 시점 기준 94.2시간 지난 배당이라 채택하지 않았습니다(기준 6시간).
```

해석(사실과 판단 분리):

- **사실**: 제공자는 이 경기의 1X2 배당 9행을 실제로 반환했다. 값 자체는 존재한다.
- **사실**: 그 값의 기준 시각은 4일 전이며 업체별 갱신 시각이 없다.
- **판단**: 기존 코드의 채택 규칙(`ODDS_FRESH_HOURS=6`, `odds_freshness`)이 이 줄들을 거부했다. 이 규칙은 "오래된 배당을 최신 배당으로 표시하지 않는다"는 기존 정책이며, 이번 후속에서 바꾸지 않았다(제품 파일 수정 금지 범위).
- 따라서 **지금 저장본에 실제 배당을 표시할 수 없다.** 없는 최신 값을 만들지 않는다.

## 5. 저장된 배당 섹션을 갱신할 때 쓸 기존 실행 경로(실행은 하지 않음)

지시대로 갱신은 하지 않았다. 키가 연결된 지금, 기존 경로만 정리한다.

1. **배당 섹션만 다시 만들기(권장, 모델 0회)**
   `POST /api/v1/admin/preview/bundle-runs`가 아니라 **`POST /api/v1/admin/preview/section-runs`** 를 쓴다.
   `workflow_id="section_odds"`, `mode="live"`, `source_mode="reuse"`, `base_run_id="6c2ce4c2-68c5-4d9b-8863-ac068e063c58"`.
   - 이 경로가 `bundle_pipeline.run_section_regeneration`으로 들어가고, 이번 PF-B 수정에서 **배당 섹션일 때만** `/odds` 1회 읽기를 붙였다(공개 표 채택값이 없을 때).
   - 모델 호출 0회(`_expected_section_model_calls("section_odds") == 0`), 부모 실행은 덮어쓰지 않고 새 실행에 새 버전으로 저장된다.
2. **새 전체 생성**: 금지·불필요(모델 6회 발생).
3. 실행해도 **현재 값은 6시간 기준을 넘겨 채택되지 않으므로** 여전히 빈 배당 섹션이 된다. 실제 표시가 필요하면 ①키프로바이더의 갱신 시각이 최신인 배당이 제공되거나 ②신선도 기준(6h)을 사용자가 조정해야 한다. ②는 정책 변경이므로 이 워커 범위가 아니다.

## 6. 정정 — 이전 보고의 검사 수치

지적대로 `109 passed`(완료 보고)와 `19/152/45`(보고서)는 **서로 다른 명령의 결과**다. 같은 실행의 다른 표기가 아니므로, `pf-backend-report.md` §5에 네 명령을 각각의 출력과 함께 적어 정정했다(새 검사 실행 없음, 기존 산출물 기준).

| 명령(파일 묶음) | 출력 |
|---|---|
| `test_bundle_review_fixes.py` 단독 | 19 passed |
| 번들·해석기·표시 7파일 | 152 passed, 2 skipped |
| `test_inspection_api`·`test_admin_access`·`test_run_store` | 45 passed |
| 변경 경로 6파일(최종) | 109 passed, 2 skipped |

## 7. 남은 문제 / 부족 항목

1. **실제 배당 표시 불가**: 제공자 값이 94.2시간 지나 채택 규칙에서 제외된다. 키 연결은 끝났고 조회도 성공했으므로 **부족한 것은 키가 아니라 최신 배당 자료**다.
2. **업체별 갱신 시각 부재**: 응답의 북메이커에 `update`가 없어 레코드 시각만 쓴다. 코드는 이를 정상 처리한다(신선도 판정은 레코드 시각).
3. **신선도 기준은 기존 정책**: 6시간 기준을 이번 범위에서 바꾸지 않았다. 바꾸려면 별도 승인이 필요하다.
4. 저장본 갱신은 §5의 `section-runs` 경로 1회로 가능하지만, 1번 이유로 지금 실행해도 빈 섹션이 된다.

EDITING STOPPED
