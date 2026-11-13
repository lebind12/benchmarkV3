# PS-05 실제 1회 실행 + 통합 인계 보고

작성: 2026-11-11 (KST). 담당: A 통합 책임자(Orca dsh-tui DeepSeek 구현 워커).
성격: **실제 실행 관측 기록**이자 인계 보고다. 사용자 승인도, 다음 실행 승인도 아니다.

## 1. 실행 결과 (분리 보고)

run_id `0d938572-8427-409f-99f5-f805bee4c697`, fixture 1557474, mode=live.

| 항목 | 값 |
|---|---|
| 상태 / 품질 | `failed` / `insufficient` |
| 실제 모델 전송 | **4회** (조사 2 + 선수 작성 1 + 최종 전망 1) |
| 상한 | 정상6 / 전체8 / 동시2 — 초과 없음 (남은 4회) |
| 수집 HTTP | **0회** (출처 0건) |
| 실행 시간 | 32.0초 |
| 토큰 | 조사 818+886 in / 62+87 out, 선수 1034/128, 전망 964/308 |
| 장부 | charged 4, rows 8, unresolved 0 |
| 저장 섹션 행 | **5개 저장**(전부 `mode=live`, v1) |

### 5개 섹션 저장 / 완료 여부 (분리)

| 섹션 | 저장 | 완료 | 본문 | 사유 |
|---|---|---|---|---|
| section_ai_forecast | O | **O (ready)** | 330자 | AI 전망 + 예상 스코어 2-1 |
| section_players | O | X (insufficient) | 0자 | 응답에 선수·선정 이유가 없음 |
| section_availability | O | X (insufficient) | 0자 | 수집 본문·DB 부상 행 모두 없음 |
| section_outlook | O | X (insufficient) | 0자 | 외부 매체 전망 본문 없음 |
| section_odds | O | X (insufficient) | 0자 | 정규시간 1X2 완결 줄 없음 |

**선택 누락은 실패와 다르다.** 부상·매체·배당은 선택 섹션이며 자료가 없어 본문을 만들지
않았고, 독자 화면에서 생략 대상이다. 다만 **주목 선수는 필수**인데 본문이 없어 전체 상태를
`failed`로 남겼다(정상 완료로 위장하지 않음).

## 2. 왜 자료가 0건이었나 — 실제 결함 2건

### (1) 조사에 Vertex 검색 도구가 없었다

`discovery` 요청의 `generation_config`에 `tools`가 없었다. 설계는 "두 모델 요청은 독립
실행하며 **Vertex 검색 도구를 사용한다**"고 명시한다. 도구 없이 조사 모델은 실제 URL을
찾지 못하고 `{"candidates": [], "search_note": "…찾을 수 없습니다"}`를 돌려줬다.

수정: 조사 A/B에만 `tools: [{"google_search": {}}]` 추가. 작성 3회·최종 전망에는 넣지
않는다(설계 5항: 작성은 전달된 정보 원문으로만).

### (2) 조사 프롬프트에 자리표시자 팀명

`team 13 vs team 4`가 그대로 프롬프트에 들어가 모델이 "제공된 팀 ID에 해당하는 정확한
팀명을 식별할 수 없다"고 응답했다. 수정: D0이 읽은 저장 자료의 **실제 팀명**(Manchester
City / Fulham)과 DB 순위·부상·통계 문맥을 조사 프롬프트에 전달.

실제 DB로 렌더한 프롬프트 확인(모델 호출 0회):

```
resolved names: Manchester City vs Fulham
- 팀: Manchester City (내부 id 13)
- 팀: Fulham (내부 id 4)
- 순위: Manchester City는 10경기 7승 0무 3패, 승점 21, 리그 3위입니다. 최근 5경기 폼은 LLLWW입니다.
- 순위: Fulham는 10경기 2승 4무 4패, 승점 10, 리그 15위입니다. 최근 5경기 폼은 DDWWL입니다.
- 저장된 부상 행이 없습니다(부상자 없음의 증거가 아닙니다).
- 선수 시즌 통계 55행이 저장되어 있습니다.
```

### (3) 기사 추출 의존성 부재

실행 기록에 `extraction_dependency_missing · trafilatura가 설치되지 않아 … 표준 라이브러리
폴백으로만 수행` 진단이 남았다. `trafilatura==2.3.1`, `lxml==6.1.3`,
`lxml_html_clean==0.4.6`을 설치하고 requirements에 고정했다(Scrapling fetchers·브라우저
wheel은 미설치). 로컬 HTML 추출 확인: 564자, 핵심 사실 포함. 네트워크·모델 호출 0회.

## 3. Stats 읽기 역할 — 실제 적용·검증 (승인 범위)

| 항목 | 결과 |
|---|---|
| 대상 확인 | benchmark-v3/api `DATABASE_URL` secret의 host/db가 기존 ro DSN과 **동일**함을 비공개 비교로 확인 후 진행 |
| secret 취급 | CLI reveal → 자식 프로세스 env로만 전달. 파일 저장·화면/로그 출력 없음 |
| dry-run → apply | `would grant column SELECT: player_id, team_id, league_id, season_year, position, appearances, minutes, rating, goals, assists, updated_at` |
| 생성 역할 | `preview_dev_stats_ro` (superuser/createdb/createrole/bypassrls/replication 모두 false) |
| 부여 열 | 승인 **11열과 완전 일치**(카드 열 없음) |
| 거부 확인 | `raw_stats`, `shirt_number`, `id`, `public.app_user`, `public.fixture`, `preview_dev.preview_runs` 모두 InsufficientPrivilege |
| 권한 경계 | 표 전체 SELECT false, preview_dev USAGE false, public CREATE false |
| 기존 변경 | 역할/비밀번호/public 행 변경 없음. `--issue-password` 미사용. 새 DSN만 0600 파일에 append |

증거: `evidence/ps05-live/stats-role-verification.txt`.

## 4. 리그 ID 공간 결함 (실제 수정)

외부 경기 식별자의 `league_id=39`로 저장 표를 조회하면 0행이었다(저장 표의 내부 리그 id는
`1`). 그래서 순위·통계가 "자료 없음"처럼 보였다. 저장 경기 행의 **내부** league/season/team
id를 먼저 읽어 그 값으로 조회하고, 외부 id는 동일성·표시용으로만 쓴다. ID 공간 차이는
진단·coverage에 남긴다.

실측: standings 2행, 선수 통계 55행(`state=readable`), 카드/raw_stats 열 없음.
증거: `evidence/ps05-live/internal-id-and-stats-read.txt`.

## 5. 이번 Dispatch의 필수 구현 항목

### (1) LangGraph DAG (수동 루프 제거)

```
START → D0 → (discovery_people ‖ discovery_outlook) → collection
      → (players ‖ availability ‖ outlook ‖ odds) → forecast → finalize → END
```

- 기존 `pipeline.py`의 `StateGraph`·`Annotated` reducer·갈래별 독립 세션 패턴 재사용.
- 갈래 세션은 실행 세션의 **bind**로 만들어 같은 DB를 쓴다.
- 하나의 `RunBudget`·장부·상한 공유. 모델 동시는 `ConcurrencyLimiter(2)`.
- 병렬 증거(성능 벤치 아님): 서로를 기다리는 barrier를 둔 대표 기록 검사에서
  `broken=False`, peak 동시성 ≤2, 논리 호출 6개 중복 0, 장부 6, 상한 8 불변, 5섹션 저장.

### (2) 실제 네트워크 전송 fail-closed

- `transported_over_network()` + `JournalRequiredForNetworkSend`.
- 실제 어댑터는 `uses_network=True`, 기록/재생 transport는 `is_recorded_transport=True`로
  **명시 구분**(`mode=live` 기록 transport를 실제 전송으로 오인하지 않는다).
- 세션/장부가 없으면 실제 어댑터는 `transport.send` **전에** 예외. 카운터 프로브로
  전송경로 도달 0, 예산 차감 0 확인. 전역 테스트환경 우회 플래그 없음.

## 6. 검사 (변경 영향 범위만)

`113 passed` — bundle_pipeline(10) / bundle_discovery(9) / bundle_sections(10) /
bundle_runtime(14) / provider / retry_budget / bundle_retrieval / player_stats_reader /
bundle_integration. `test_outlook_module.py`는 기존 시계 문제로 제외(지시대로 미수정).
기록 preflight는 변경 후 재실행하지 않고 이전 증거를 재사용한다.

## 6.5 무료 사전검증 결과 (모델·네트워크 호출 0회)

증거: `evidence/ps05-live/preverify-free.json`.

| 항목 | 결과 |
|---|---|
| A. 요청별 `generation_config.tools` | 조사 2회(`discovery_people`, `discovery_outlook`)만 `[{google_search:{}}]`. 작성 3회·최종 전망은 `None` |
| B. 자리표시자 | `team 13`/`team 4` **없음**. 실제 팀명과 DB 순위·부상 문맥이 프롬프트에 포함 |
| C. 추출 의존성 | `dependency_problem=null`, `trafilatura 2.3.1`/`lxml 6.1.3` 로드, 로컬 HTML 229자 추출·핵심 사실 유지 |
| D. 제안 예산(6/6/1) 정합성 | 초기 예약 6, 6회 모두 허용, 6회 후 사용 6·예약 0, **7번째 거부** |

자료가 없는 섹션은 호출을 시작하지 않고 예약을 반환한다(예: media_odds 출처가 없는
묶음에서 `section_outlook` 호출 0회, `cancelled_calls=['section_outlook']`).

**무료로 확인되지 않는 것**: 실제 후보 URL의 품질·커버리지. 그것은 조사 모델 호출이
필요하다. 위 A~D는 요청 설정·프롬프트 입력·의존성·예산 정합성만 확인한다.

## 7. 남은 일

1. **두 번째 실제 실행** — 위 수정 후 1회. 조사가 실제 후보 URL을 내고 수집이 본문을
   확보하는지 확인하는 것이 목적이다. 조정자가 제시한 범위는 **추가 최대 6회 / 누적 최대
   10회 / 호출당 1시도·자동 재시도 0 / 두 번째 전체 실행 정확 1개**이며, 사용자 예산 응답
   대기 중이다. 그 전에는 유료 호출을 열지 않는다(이전 4회 사용분은 보존).
2. 사용자 확인 — 실행 후 `GET /runs/{id}/section-results`(본문+구조화)와
   `GET /runs/{id}/information-bundle`(출처·구간·DB·배당)로 눈으로 확인.
3. 8000/5173 재시작은 root가 순서화. 이 작업에서 서버를 건드리지 않았다.
4. 독립 검토는 별도 새 DeepSeek 읽기전용 세션(PS-06)에서 수행.

## 8. scoped 변경 파일

신규: `app/preview/information_bundle.py`, `send_ledger.py`, `bundle_pipeline.py`,
`section_structured.py`, `discovery.py`, `retrieval.py`, `sources/player_stats.py`,
`modules/bundle_sections.py`, `prompts/{discovery_*,bundle_*}.md`,
`scripts/preview_bundle_preflight.py`, `scripts/preview_bundle_live_once.py`,
`tests/preview/test_bundle_{runtime,integration,pipeline,sections,discovery,retrieval}.py`,
`test_player_stats_reader.py`, `docs/implementation/match-preview/section-interface-manifest.md`.

수정: `provider.py`(장부·fail-closed), `retry.py`(예약 반환·정상6), `store.py`(묶음·전문·
장부 요약), `pipeline.py`(예약 반환), `registry.py`(bundle 5섹션), `version_manifest.py`,
`inspection.py`, `preview_admin.py`(bundle-runs·정보원문·구조화), `core/config.py`(stats DSN),
`requirements.txt`, `sources/player_stats.py`(11열), `scripts/preview_dev_stats_ro_provision.py`,
`tests/preview/test_{retry_budget,section_approvals,bundle_discovery}.py`,
`frontend/.../informationBundle.ts`·`SectionRunView.test.ts`(필드명만).

## 9. 알려진 미해결

- 조사 후보 0건이면 필수 섹션(주목 선수)이 비어 `failed`가 된다. 이는 정직한 상태이며
  자료 부족을 성공으로 바꾸지 않는다.
- `test_outlook_module.py` 15건 실패는 기존 테스트 시계 문제(별도 후속).
- 배당 사이트 공개 접근은 조사 단계 12개 probe에서 확보 실패로 보고됨 → 선택 누락으로 남긴다.
  유료 서비스·우회 도입 없음.

**EDITING STOPPED** — 이 보고 시점 이후 내 소유 경로의 자율 편집을 멈춘다. 추가 수정은
조정자 지시가 있을 때만 한다.
