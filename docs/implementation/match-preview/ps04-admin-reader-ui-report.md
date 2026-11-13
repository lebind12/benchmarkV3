# PS-04 관리자·독자 화면 — 인계 보고

작성: 2026-11-11 KST. 담당: PS-04 D UI 워커(Orca dsh-tui DeepSeek 구현 워커).
성격: **화면 구현과 자체 검증 기록**이다. 사용자 승인도, 실제 API 연결 완료도 아니다.

기준 계약: [section-interface-manifest.md](section-interface-manifest.md) §1·§4·§5·§7
(`INFORMATION_BUNDLE_VERSION = "mp11-information-bundle-1"`).
설계: [확정 설계](../../superpowers/specs/2026-11-11-preview-sections-design.md).
계획: [구현 계획](../../superpowers/plans/2026-11-11-preview-sections-implementation.md) PS-04.

## 결론 먼저

- 화면 4개(정보 원문 패널·구조화 표시·재생성/비교/승인 패널·독자 배당 표)를 만들었고,
  기존 관리자 화면 3개(`SectionRunView`·`RunInspector`·`MatchPreview`)에 연결했다.
- 필드 이름은 manifest §1/§4/§5의 **실제 이름**을 쓴다. 조정자와 상호 ACK를 마쳤다
  (msg_15d26cacaadc: (1)~(7) 확인, (a) Google 전체 응답은 기존 `/runs/{id}` 아티팩트에
  유지·bundle-level raw 필드 없음, (b) `availability.artifact_id`는 provenance ID이지
  다운로드 URL이 아님 → 가상 endpoint 호출 금지).
- **UI 완료와 API 실연결은 다르다.** `GET /runs/{id}/information-bundle`은 manifest §4에
  "계획 (A)"으로 남아 있다. 그래서 화면은 404를 "경로가 아직 없거나 실행이 없음"으로
  정직하게 표시하고, 빈 묶음을 만들어 성공처럼 그리지 않는다.
- 유료 모델 호출 0회, 운영 DB 쓰기 0회, 서버 재시작 0회, git stage/commit 0회.

## 바꾼 파일 (전부 D 소유 경로)

### 신규

| 파일 | 역할 |
|---|---|
| `frontend/src/features/match-preview/informationBundle.ts` | `InformationBundle` 화면 타입 + 방어적 파서(`parseInformationBundle`), `usableSources`/`failedSources`/`sourceHref`/`redirectNote`/`isBundleEmpty` |
| `frontend/src/features/match-preview/InformationBundlePanel.vue` | 출처 먼저 · 후보 구간/실제 전달/DB/배당/조사 상태는 접힌 진단 |
| `frontend/src/features/match-preview/sectionStructured.ts` | 섹션 결과 구조화 타입 + 파서(`structuredFromSectionResult`, `playersFromBody`, `injuryStatusLabel`, `scoreText`, `EMPTY_STRUCTURED`) |
| `frontend/src/features/match-preview/SectionStructuredView.vue` | 선수(팀별, 이름/사유 분리)·부상(상태 원문)·매체(점수 미제시 유지)·1X2 배당 표·AI 예상 |
| `frontend/src/features/match-preview/SectionRegenerationPanel.vue` | `reuse`/`refresh`/`reprocess` 구분, 버전 비교, 승인 이벤트 |
| `frontend/src/features/match-preview/InformationBundlePanel.test.ts` | 8검사 |
| `frontend/src/features/match-preview/SectionStructuredView.test.ts` | 11검사 |
| `frontend/src/features/match-preview/SectionRegenerationPanel.test.ts` | 8검사 |

### 수정

| 파일 | 변경 |
|---|---|
| `frontend/src/features/match-preview/types.ts` | `SectionRegenerationRequest`(manifest §5 이름), `SourceMode`, `SectionReprocessMode`, `SectionResultsResponse`, `ReaderPreviewOdds` + `ReaderPreview.odds?`, `SectionRunResponse` 확장 필드 9개(모두 선택) |
| `frontend/src/features/match-preview/api.ts` | `informationBundle(runId)`(GET, `unknown` 반환), `sectionResults(runId)`(GET), `regenerateSection(payload)`(POST) — 경로 상수를 각각 한 곳에 모음 |
| `frontend/src/features/match-preview/SectionRunView.vue` | 본문 → 근거 → 구조화 → 정보 원문 → 재생성 → **승인(마지막)** 순서, 번들 ID로 재사용 모드 개방, 재처리는 기존 replay 경로 |
| `frontend/src/features/match-preview/RunInspector.vue` | 섹션 결과 아래에 구조화 표시 + 정보 원문 패널(조회 전용) |
| `frontend/src/features/match-preview/MatchPreview.vue` | 독자용 배당 표(정규시간 1X2). 값 없는 줄·키 없음이면 카드 자체를 만들지 않음 |
| `frontend/src/features/match-preview/{SectionRunView,MatchPreview}.test.ts` | 번들 배선 2검사, 배당 2검사 추가 |

`frontend/src/router/index.ts`는 **고치지 않았다**. 필요한 화면이 모두 기존 라우트
(`preview-sections`, `preview-runs`, `preview-reader`) 안에서 열리기 때문이다.

## API seam (A가 채울 자리)

| 화면 동작 | 경로 | 요청/응답 핵심 |
|---|---|---|
| 정보 원문 조회 | `GET /api/v1/admin/preview/runs/{run_id}/information-bundle` | `{run_id, availability{available,reason,artifact_id}, summary, bundle\|null}` |
| 섹션 결과 목록 | `GET /api/v1/admin/preview/runs/{run_id}/section-results` | `{run_id, section_results[]}` |
| 섹션 재생성 | `POST /api/v1/admin/preview/section-runs` | `source_mode`(`reuse`\|`refresh`), `bundle_id`(reuse 필수), `base_run_id`, `base_result_id`, `selected_result_ids[]` |
| 재생성 응답 | 위와 동일 | `source_mode, bundle_id, bundle_reused, expected_model_calls, parent_run_id, base_result_id, new_version, no_model_call` |
| 저장 응답 재처리 | `POST /api/v1/admin/preview/results/{module_result_id}/replays` | 기존 경로. 요청은 **모듈 결과 ID**이며 섹션 결과 ID가 아니다 |
| 승인 | `POST /api/v1/admin/preview/sections/{workflow_id}/approvals` | 기존 경로 그대로 |

읽는 `bundle` 키(실 구현 `InformationBundle.to_dict()`와 일치):
`bundle_id, bundle_version, fixture, team_id_space, collected_at, as_of, mode, sources[],
db_snapshot, discovery_groups[], odds, section_deliveries[], available_passages[],
passage_semantics, diagnostics[], network_usage, available_chars,
browser_used, cross_checked_with_db, requires_grounding_chunks, bundle_hash`.

**전달 후보 vs 실제 전달(계약 갱신 반영).** `sources[].passages`와 `available_passages[]`는
수집·정규화된 **후보**이며 각 항목이 `delivered: false`다. 실제 모델 전달은
`section_deliveries[]`의 `SectionDelivery`만 밝힌다:
`section_id, logical_call_id, model_delivered, passage_ids[], source_ids[], payload_sha256,
input_chars, available_passage_ids[], excluded_passage_ids[], sent_attempts,
implementation_version, prompt_version, created_at, note`.
배당은 `model_delivered=false`이고 `passage_ids`가 비어 있다. 화면은 전달 기록이 없는
구간을 '전달됨'으로 승격하지 않으며, 전달 기록이 아예 없으면 후보/전달 표시를 만들지 않는다.

`sources[]`: `source_id, discovery_group, requested_url, final_url, nature, method, title,
published_at, captured_at, http_status, redirects, extractor, body_chars, passages[],
failure, notes[], usable, delivered_chars`.

`db_snapshot`: `fixture, team_id_space, collected_at, teams, standings, injuries,
recent_matches, roster, source_tables, coverage[], diagnostics, readable`.

`odds.quotes[]`: `site, market, observed_at, home_decimal, draw_decimal, away_decimal, complete`.

`network_usage`: `http_used, http_failed, redirects, api_used, http_limit, api_limit, note`.

## 지킨 것 (설계·정책)

- **본문·근거가 먼저.** 정보 원문·후보 구간·실제 전달 기록·DB·배당·조사 상태는 모두 접힌 진단이다.
  승인 블록은 화면 **마지막**으로 옮겼다(확인 → 조정 → 승인 순서).
- **무호출 재처리 vs 실제 재생성 구분.** 세 동작을 라디오로 먼저 보여주고, 요청은
  사용자가 버튼을 눌러야만 나간다. 재처리는 재생성 API를 부르지 않는다(테스트로 고정).
- **전송 수를 추정하지 않음.** 재사용/새 수집/무호출 표시는 서버가 준
  `bundle_reused`·`no_model_call`·`external_calls`로만 쓴다. 값이 없으면 단정하지 않는다.
- **승인 자동 생성 금지.** 마운트 시점에 승인 호출 0회. 승인 가능 결과가 아니면
  버튼 자체를 열지 않고 사유를 보여준다.
- **값을 만들지 않음.** 없는 선수·점수·배당을 채우지 않는다. `unknown` 상태를 확정
  부상으로 바꾸지 않는다. 부상 0건을 "부상자 없음"으로 쓰지 않는다.
- **선수 표시는 이름/사유 분리 + 팀별 묶음.** 상한을 넘겨 오면 자르지 않고 그대로
  보여준다(계약 위반을 숨기지 않음).
- **선택 섹션 생략.** 독자 화면은 `odds` 키가 없거나 값이 비면 카드를 만들지 않는다.
- **비밀값 없음.** 타입에 쿠키·토큰·계정이 없고 화면도 그런 값을 그리지 않는다.
- **가상 endpoint 호출 없음.** `availability.artifact_id`로 다운로드를 시도하지 않는다
  (조정자 ACK (b)). 기사 전문이 필요하면 실행 상세의 실제 아티팩트만 쓴다.
- **계약 위반 노출.** `browser_used`/`cross_checked_with_db`/`requires_grounding_chunks`가
  true로 오면 경고를 띄운다(계약상 항상 false).

## 검증 (직접 실행)

```
$ cd frontend && npx vitest run src/features/match-preview
Test Files  16 passed (16)
     Tests  115 passed (115)

$ cd frontend && npx vue-tsc --noEmit
(출력 없음, 종료 0)
```

전체 `npx vitest run src`도 17 파일 / 120 검사 통과(로그인 화면 포함). 새로 추가한 검사만
세면 27건(정보 원문 8 + 재생성 8 + 구조화 11)이며, 모두 이번 수용 기준
(본문·근거 우선, 무호출/유료 구분, 승인 자동화 금지, 값 미생성, 선택 섹션 생략)에
직결된다. 브라우저 자동화·전체 회귀는 실행하지 않았다(계획 PS-04 범위 밖).

## 남은 일 / 인계 사항

1. **A: `GET /runs/{run_id}/information-bundle` 구현.** 지금은 manifest §4에 "계획"이며,
   화면은 404를 정직하게 표시한다. 구현되면 화면은 코드 변경 없이 값을 읽는다
   (파서 키가 §1.2와 일치).
2. **A: `POST /section-runs` 확장 필드.** `source_mode`/`bundle_id`/`base_run_id`/
   `base_result_id`를 받고 응답에 `bundle_reused`·`no_model_call`·`expected_model_calls`를
   주면 재생성 패널이 실제 결과를 정확히 표시한다. 현재 서버는 이 필드를 무시하므로
   재생성 요청은 기존 실행 경로로 떨어진다(오류로 표시되지는 않음).
3. **A/C: 섹션 결과의 `structured` 값.** 지금 `SectionResultView`에는 구조화 필드가 없다.
   구조화 값이 없으면 화면은 본문만 보여주고, 선수만은 기록된 라벨
   (`선정 선수:`/`선정 이유:`)로 읽는다. C의 `SectionDraft.structured`를 A가 섹션 결과에
   실어 주면 부상·매체·배당·예상 표가 그대로 뜬다(화면 추가 수정 불필요).
4. **A: 재처리 경로 확인.** 화면은 기존 `POST /results/{module_result_id}/replays`를 쓴다.
   섹션 결과에 `result_ids`가 비어 있으면 재처리 버튼이 사유를 표시하고 요청하지 않는다.
5. **조정자: 실제 화면 확인은 사용자 몫.** 자동 검사 통과는 사용자 승인이 아니다.
   승인 행은 사용자가 버튼을 눌러야만 만들어진다.
6. **Google 전체 응답 위치(ACK (a)).** 정보 원문은 기사·DB·후보 구간·전달 기록만 담고, 모델 전체
   JSON은 기존 실행 상세(`/runs/{id}`)의 아티팩트·응답 탭에 남는다. 기존 full API JSON
   정렬 보기(`ModuleResultPanel`/`AttemptPanel`)는 건드리지 않았다.

## 하지 않은 것

- `frontend/src/router/index.ts` 수정(불필요), Hallmark 재디자인, 본문 직접 편집 UI,
  출처 선택·제외 UI, 새 디자인 체계.
- backend·공유 타입 파일 수정, DB 쓰기, 유료 모델 호출, 서버 재시작, 브라우저 자동화.
- git add/commit/push/deploy/stage. 인덱스에 아무것도 올리지 않았다.

## EDITING STOPPED

PS-04 소유 파일(`frontend/src/features/match-preview/**`)에 대한 편집을 여기서 멈춘다.
`frontend/src/router/index.ts`는 편집하지 않았다. 인계 후 이 워커는 위 경로를 다시
수정하지 않는다. 추가 수정이 필요하면 새 Dispatch로 배정해야 한다.

기존 삭제·미커밋 변경(`D` 상태 파일, 정책·문서·환경·빌드 파일)은 그대로 보존했다.
backend 8000 / frontend 5173 프로세스는 재시작·종료하지 않았다.
