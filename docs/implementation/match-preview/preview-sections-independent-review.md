# 새 프리뷰 경로 독립 읽기전용 검토 (PS-06)

작성: 2026-11-11 KST. 담당: 별도 새 DeepSeek 세션(Orca `dsh-tui`, `deepseek-ai/deepseek-v4.1-flash-1017`, Max).
성격: **독립 검토 보고서**. 구현·수정·검증 실행을 하지 않았다. 아래 지적은 조정자 판단용 근거이며
사용자 승인도, 완료 판정도 아니다.

- 검토 시작: `2026-11-11T13:52:48+09:00`
- 검토 종료: `2026-11-11T14:47:30+09:00`
- 기준 리비전: `HEAD = 4d2821de089a39742ca69df377cd02425e65da9c`
- 검토 대상은 **커밋이 아니라 작업 트리 상태**다. 새 경로 파일 대부분이 미추적(`??`)이거나 수정(` M`) 상태여서
  HEAD만으로는 재현되지 않는다. 그래서 아래 표에 파일별 SHA-256 앞 16자리를 남긴다.
- 지시 범위: 승인된 설계 [2026-11-11-preview-sections-design.md](../../superpowers/specs/2026-11-11-preview-sections-design.md)와
  구현 계획 Review Focus. 현재 수용 기준(6논리요청·LangGraph 합류/병렬·묶음→본문 연결·필수/선택 섹션·ID 공간/한글명)만 본다.
  전면 보안·아키텍처 감사, 전체 테스트, 미지원 플랫폼 가상 위험, 기사-DB 교차검증 엔진, Google 메타데이터 하드게이트는 범위 밖이다.

## 0. 검토 방법과 하지 않은 것

- 읽기: 아래 §1 파일들을 **함수 단위로 직접 읽었다.** 옛 R1/R2/R3/S1/프레임워크 소스 전체를 반복해 읽지 않았다
  (`players.py`·`availability.py`·`outlook.py`·`synthesis.py`는 새 경로가 실제로 부르는 진입점 주변만 봤다).
- 읽기: 저장된 증거 `evidence/ps05-live/*`, `evidence/ps01-preflight/recorded-preflight.json`,
  `ps05-live-run-report.md`의 주장과 **코드 경로를 대조**했다. 테스트는 개수·통과 주장이 아니라 의미 있는 단언을 확인했다
  (§5). 전체 스위트를 다시 돌리지 않았다.
- 정적 확인 보조로 프로젝트 `.venv`에서 **순수 함수만** 호출하는 짧은 in-process 점검을 했다(파일 저장·스크립트 생성 없음,
  네트워크 0, 모델 0, DB 0). 재현한 항목은 각 지적에 "재현"으로 표시했다.
- 하지 않은 것: 코드·테스트·설정·마이그레이션·DB 쓰기, 새 파일 생성(이 보고서 제외), 새 에이전트, 유료 모델/HTTP/API 호출,
  비밀값·환경변수 읽기, 운영 DB 접근, 단계/커밋, 서버 재시작.
- 알려진 기존 문제로 **제외**: `test_outlook_module.py` 시계 관련 15건 실패. 이번 판정 항목이 아니며 고치지도 다시 돌리지도 않았다.
- 완료되지 않은 유료 실행 메타데이터(§4)는 A가 아직 작업 중인 동안 결함으로 세지 않는다.

## 1. 읽은 파일과 해시 (검토 종료 시점)

| 파일 | SHA-256(16) | mtime |
|---|---|---|
| `app/preview/bundle_pipeline.py` | `708a515b5480435e` | 13:53:18 |
| `app/preview/provider.py` | `b75637a685f1e8ea` | 13:41:00 |
| `app/preview/send_ledger.py` | `9298f6fa12fb313a` | 13:11:28 |
| `app/preview/retrieval.py` | `43009bee999d3094` | 12:27:55 |
| `app/preview/discovery.py` | `38e1abd3e6b2999d` | 14:00:03 |
| `app/preview/information_bundle.py` | `d3069091c8435524` | 12:27:23 |
| `app/preview/modules/bundle_sections.py` | `b79a5ccf95cf46b5` | 12:53:39 |
| `app/preview/store.py` | `b779f3f5dd2cbb30` | 13:12:45 |
| `app/api/v1/preview_admin.py` | `4d47f99c85950a7b` | 13:15:42 |
| `app/preview/version_manifest.py` | `bad309401f7c693f` | 13:05:57 |
| `app/preview/registry.py` | `5634229732ab4d40` | 13:07:43 |
| `app/preview/retry.py` | `1f6a4a3cc4de428a` | 12:16:51 |
| `app/preview/sections.py` | `0c7049c4da68308c` | 05:25:22 |
| `app/preview/section_structured.py` | `4860d34e14e09703` | 13:26:26 |
| `app/preview/sources/player_stats.py` | `60bfb0013ead82e9` | 12:35:52 |
| `frontend/src/features/match-preview/informationBundle.ts` | `43781b2597c423ec` | 12:37:07 |
| `frontend/src/features/match-preview/api.ts` | `5a0c1397ea951876` | 12:07:29 |
| `docs/implementation/match-preview/section-interface-manifest.md` | `6a5a5f40c29e95cc` | 13:33:22 |

참고로 읽은 계약·증거: `section-interface-manifest.md`(§1·§4·§5·§6·§7.5), `prompts/bundle_*.md`,
`ps05-live-run-report.md`, `evidence/ps05-live/live-20261111T045112Z-…json`, `preverify-free.json`,
`stats-role-verification.txt`, `internal-id-and-stats-read.txt`, `evidence/ps01-preflight/recorded-preflight.json`,
`tests/preview/test_bundle_{pipeline,integration,runtime,sections,retrieval}.py`(단언 위주), `tests/preview/test_player_stats_reader.py`,
`frontend/.../InformationBundlePanel.test.ts`·`SectionRunView.test.ts`(픽스처 모양 확인).

### 1.1 검토 중 구현자 변경 (범위 통지)

- `app/preview/bundle_pipeline.py`가 검토 시작 뒤 **13:53:18**에 바뀌었다(시작 시 해시 `cee1b64d36fc017b` → 종료 시 `708a515b5480435e`).
  그래서 이 파일은 변경 후 내용을 **처음부터 다시 읽었고**, 아래 모든 인용은 `708a515b5480435e` 기준이다.
  이 파일은 미추적(`??`)이라 변경 전 바이트를 git으로 꺼낼 수 없어 **바이트 단위 diff는 확인하지 못했다.** 대신 현재 파일의
  최상위 정의 23개와 중복 정의 없음, 노드·엣지 구성(`START→D0→조사2‖→collection→작성4‖→forecast→finalize→END`)과
  `BundlePipelineOutcome` 키가 manifest §7.5와 일치함을 확인했다. 그 범위에서는 계약 변경이 없었다.
- `app/preview/discovery.py`가 **14:00:03**에 바뀌었다. 변경 부위(`generation_config`의 `tools` 부분, 현재 499–509행)를 다시 읽었다.
  조사 A/B만 `google_search`를 쓰고 작성·최종 전망에는 없다는 사실은 그대로다.
- 그 밖의 검토 대상 파일은 시작·종료 해시가 같다.
- 요청: 나머지 수정이 끝난 뒤 **한 번의 수정 후 확인(post-fix verification)** 만 요청한다. 전면 재검토는 요청하지 않는다.

## 2. 결론 요약

예산·전송 보존 계층(§7 판정표의 기준 (1)·(2))은 설계 의도대로 동작한다. 반면 **묶음 자료를 실제 프롬프트로 옮기는 구간**과
**재생성·필수 섹션 판정 구간**에서 현재 수용 기준을 위반하는 결함이 재현됐다.

- 현재 수용 기준 위반/직접 재현 결함: **9건**(F1–F9). 그중 F1–F5는 필수 섹션 결과의 정확성·정직성에 직접 닿는다.
- 참고 개선: **5건**(R1–R5). 이번 작업을 막지 않는다.

가장 무거운 것은 세 가지다.

1. **DB 근거가 작성 프롬프트에 도달하지 않는다**(F1·F2). D0이 실제로 읽은 순위·부상·선수 통계가 키 이름 불일치로
   `- 순위 값 없음` 또는 `- 후보 목록 없음`으로 바뀐다. DB-only 최종 전망(설계 §86)과 필수 '주목 선수'의 근거 기반이 무너진다.
2. **`source_mode=reuse` 재생성이 실제로는 묶음을 쓰지 않는다**(F5). 응답 문구는 "새 수집·검색 호출은 없고"라고 단정하는데
   실행되는 노드는 레거시 R2/R3/R4이며 `google_search` 도구를 포함한다.
3. **AI 예상 스코어가 필수인데 없어도 성공으로 끝난다**(F4). 예상 스코어 없는 전망 초안이 `ready`로 저장되고 실행이 `succeeded`가 된다.

## 3. 지적 (현재 수용 기준 실패·직접 재현 결함)

각 항목은 `파일:행` + 트리거 + 관측 가능한 영향 + 가장 작은 수정 방향(문장)이다. 실행 가능한 패치는 넣지 않는다.

### F1. D0이 읽은 순위·부상 사실이 작성·최종 전망 프롬프트에서 사라진다

- 위치: `app/preview/bundle_pipeline.py:213-221`(순위 행 `{team_id, text}`), `:250-260`(부상 행 `{player_name, team_id, expected_status}`),
  `app/preview/modules/bundle_sections.py:448-450`(키 목록), `:517-527`(순위 줄 생성), `:540-553`(부상 줄 생성), `:604-612`(부상 상태 문장).
- 트리거: 저장 DB에 그 경기의 순위 행 또는 부상 행이 있는 모든 실행.
- 영향(재현):
  - D0은 순위 문장을 `text`에 담는데 `_db_material`은 `_STANDING_KEYS = ("rank","position","points","played","goals_diff")`만 읽는다.
    그래서 프롬프트에는 `- api:standings-13: Manchester City — 순위 값 없음`이 들어간다. 실제로는
    "10경기 7승 0무 3패, 승점 21, 리그 3위, 최근 5경기 LLLWW"가 이미 D0 출력에 있었는데도 그 문장이 **대체·소실**된다.
    같은 행 모양을 조사 프롬프트는 `_db_context_text`(`bundle_pipeline.py:614-622`)에서 `text`로 정상 사용한다.
    그래서 같은 실행 안에서 조사는 순위를 알고 작성·최종 전망은 모른다.
  - 부상 행은 `player_name`이 `None`이고 키가 `expected_status`인데 `_INJURY_KEYS`에 `expected_status`가 없다.
    그래서 부상 행이 **1건 있어도** 인용 가능한 사실 id가 0건이 되고(`ids=()`), 진단에는
    "DB 행 1건은 필요한 열을 찾지 못해 근거 줄로 만들지 않았습니다"만 남는다.
  - 같은 프롬프트 안에서 `{injury_state}`는 "저장된 부상 행 1건을 전달했습니다"라고 쓰고 `{db_injuries}`는
    `- DB 경기 자료가 제공되지 않았습니다`를 쓴다(`bundle_sections.py:604-612`, `:1262`). 한 요청이 서로 반대되는 자료 상태를 말한다.
    모델은 부상 사실을 못 받았는데 "전달했다"는 문장을 읽는다.
- 왜 현재 기준 실패인가: 설계 §86(웹 수집이 실패해도 DB 경기/순위/최근 경기 자료로 최종 전망 작성), §62(정보 원문은 DB 자료를
  출처별로 연결), 계획 Review Focus 3(부분 자료·DB-only 최종 전망). 이 상태의 DB-only 경로는 "DB 자료로 작성"이 아니라
  "자료 없음 문장으로 작성"이다.
- 가장 작은 수정: D0이 순위·부상을 **프롬프트가 읽는 키로** 내보내거나(`rank/points/played` 또는 공통 `text`),
  `_db_material`이 `text`와 `expected_status`를 읽게 한쪽만 맞춘다. 부상 상태 문장은 실제 전달된 근거 건수로 계산해야 한다.

### F2. 선수 시즌 통계가 '주목 선수' 프롬프트의 후보 목록에 들어가지 않는다

- 위치: `app/preview/modules/bundle_sections.py:586-601`(`_roster_lines`가 `display_name`·`name_ko`·`english_name`을 찾음),
  `app/preview/sources/player_stats.py:105-119`(행 dict 키는 `display_name_ko`), `:314-324`·`:374`(`name_lookup`이 없으면 항상 `None`),
  `app/preview/bundle_pipeline.py:233-239`(`name_lookup` 없이 호출).
- 트리거: 선수 통계 읽기 역할이 설정된 실행(현재 적용·검증됨)에서 통계 행이 있는 모든 경기.
- 영향(재현): 55행을 읽어도 `_roster_lines`는 `- 제공된 선수 후보 목록이 없습니다. 자료에 적힌 표기만 쓴다.`만 낸다.
  즉 **필수 섹션인 주목 선수**가 후보 목록 없이 웹 구간만으로 선수를 고르게 된다. 웹 수집이 0건인 경기에서는
  근거가 아예 없어 `section_players`가 `insufficient`가 되고 실행 전체가 `failed`가 된다(§4 실제 실행과 같은 결과).
  부수적으로 `name_lookup` 미전달로 `display_name_ko` 자체도 항상 `None`이다.
- 가장 작은 수정: `_roster_lines`가 `display_name_ko`를 읽고, 파이프라인이 통계 조회 시 `name_lookup`을 넘기거나
  표시 이름을 만드는 기존 경로를 재사용한다. 후보가 없을 때만 "후보 없음" 문장을 쓴다.

### F3. `section-results`의 구조화 값이 AI 전망을 읽지 못해 `available=false`가 된다

- 위치: `app/preview/section_structured.py:164-186`(`_forecast`가 `ai_prediction` 또는 최상위 `score`/`lean`만 봄),
  `app/preview/modules/bundle_sections.py:1955-1970`(저장 payload는 `structured.forecast` 아래에 `lean`/`score`/`reasoning`을 둠),
  `app/api/v1/preview_admin.py:983-1005`(그 값을 그대로 응답에 붙임).
- 트리거: 새 경로가 만든 모든 AI 전망 섹션.
- 영향(재현): `structured_from_payload`가 `forecast=None`을 돌려주고 `available=False`가 된다. 그래서 예상 스코어·근거 이유가
  표로 표시되지 않는다. 화면(`SectionStructuredView.vue`)은 `structured.forecast`를 그릴 준비가 되어 있고
  프론트 파서(`sectionStructured.ts:232`)도 `forecast`를 읽으므로, **서버 투영만 계약에서 벗어난 상태**다.
  설계 §78이 요구하는 필수 본문(AI 전망+예상 스코어) 확인이 관리자 화면에서 표로 이어지지 않는다.
- 왜 테스트가 못 잡았나: `test_section_results_expose_stored_structured_values`는 players/media/odds만 단언한다
  (`tests/preview/test_bundle_integration.py:829-`). 전망 키를 검사하는 단언이 없다.
- 가장 작은 수정: `_forecast`가 `forecast` 하위 dict를 먼저 읽게 한다(현재 병합 로직은 `structured`만 최상위로 올린다).

### F4. AI 예상 스코어가 필수인데 없어도 섹션 `ready`·실행 `succeeded`가 된다

- 위치: `app/preview/modules/bundle_sections.py:1971-1987`(`quality=READY if forecast else INSUFFICIENT`, 스코어 없음은 진단만),
  `app/preview/prompts/bundle_forecast.md:71`("스코어를 제시할 수 없으면 `null`이다"),
  `app/preview/bundle_pipeline.py:1074-1091`(필수 판정은 섹션 존재·`unavailable`만 봄).
- 트리거: 모델이 `forecast`는 쓰고 `predicted_score`를 `null`로 준 경우(프롬프트가 명시적으로 허용).
- 영향(재현): 초안 품질 `ready`, `unavailable_reason=None`, 본문에는 `## AI 경기 전망`만 있고 스코어 절이 없다.
  진단에만 "예상 스코어를 제시하지 않았습니다(값을 만들지 않음)"가 남는다. 실행은 `status=succeeded`로 끝난다.
  설계 §78의 필수 본문은 "경기 전망·AI 예상 스코어·주목 선수"이므로, **필수 항목이 빠진 프리뷰가 정상 완료로 표시**된다.
- 가장 작은 수정: 예상 스코어 부재를 그 섹션의 `insufficient`로 올리고(값을 만들지 않는다는 원칙은 유지), 프롬프트의
  `null` 허용 문장과 필수 조건 중 어느 쪽이 제품 기준인지 조정자가 확정한다.

### F5. `source_mode=reuse` 재생성은 실제로 저장 묶음을 쓰지 않는다

- 위치: `app/api/v1/preview_admin.py:753-788`(묶음 조회·검증만 함), `:790-800`(실행은 `runner.run_section_workflow` + `_section_implementations`),
  `:830-850`(응답 `note`: "저장된 정보 원문 묶음을 재사용해 … 새 수집·검색 호출은 없고"),
  `app/preview/sections.py:550-633`(라이브 구현은 기존 모듈), `app/preview/modules/players.py:1029-1033`(`tools: [{"google_search": {}}]`),
  `app/preview/modules/availability.py:1541`, `app/preview/modules/outlook.py:114`(`GROUNDING_TOOL`).
- 트리거: 관리자가 `source_mode=reuse`로 `POST /section-runs`를 실행할 때(`mode=live`).
- 영향: `reuse_bundle`은 **진단 주석에만** 쓰이고(`_annotate_section_reuse`), 섹션 본문을 만드는 경로는 묶음을 읽지 않는
  레거시 노드다. 그 노드는 검색 도구를 포함하므로 "새 검색 호출 없음"은 사실이 아니다. 응답은 `bundle_reused=true`,
  `bundle_id=<부모 묶음>`을 내므로 화면은 "저장 원문 재사용"으로 표시한다. 설계 §80(재생성 전 재사용/새 수집 구분)과
  계획 Review Focus 5(재생성이 실제 저장 버전을 만들고 원문·승인 버전을 혼동하지 않는가)를 직접 위반한다.
- 함께 확인된 제약: `section_odds`·`section_ai_forecast`는 `sections._IMPLEMENTED_SECTIONS`(`sections.py:79-85`)에 없어
  `mode=live` 재생성이 422로 거부된다. 즉 새 경로의 두 섹션은 이 화면에서 다시 만들 수 없다.
- 가장 작은 수정: `source_mode=reuse`(와 `refresh`)에서 재생성 실행기가 `bundle_sections.build_bundle_section`을 쓰도록
  연결하고, 연결 전까지는 "묶음을 재사용해 다시 만들었다"는 응답 문구를 사실에 맞게 내린다.

### F6. `information-bundle` 응답이 `availability` 중첩이 아니라 평면 키다 (문서·프론트와 불일치)

- 위치: `app/api/v1/preview_admin.py:1028-1053`(`return {"run_id": ..., **record}`), `app/preview/store.py`의
  `load_information_bundle` 반환(`available/reason/artifact_id/sequence/bundle/summary`),
  `frontend/src/features/match-preview/informationBundle.ts:471-480`(`root.availability`를 읽음),
  `docs/.../section-interface-manifest.md:348-365`(계약은 `"availability": {...}` 중첩).
- 트리거: 묶음이 없는 실행(=수집 이전 종료, 보관 만료)을 관리자 화면에서 열 때. 그리고 모든 정상 응답의 키 모양.
- 영향: 프론트 `parseInformationBundle`은 `availability`가 없어 `{}`로 떨어뜨린다. 묶음이 있으면 `bundle !== null` 덕분에
  `available`이 참으로 보이지만, **묶음이 없을 때 서버가 준 구체 사유("보관 기간이 지났다" / "이 실행에는 묶음이 없다")가
  화면에 전달되지 않는다**(`unavailableReason=null`). 화면은 일반 문구로 대체한다.
  백엔드 테스트는 평면 키를, 프론트 테스트는 중첩 키를 각각 단언하므로 **어느 쪽 테스트도 이 불일치를 잡지 않는다**
  (`test_bundle_integration.py:296-`는 `payload["available"]`, `InformationBundlePanel.test.ts:31`은 `availability`).
- 가장 작은 수정: 응답을 manifest 모양(`availability{available,reason,artifact_id}`)으로 내거나, manifest와 프론트 파서를
  실제 응답에 맞춘다. 한쪽만 고치면 계약이 계속 갈라진다.

### F7. 리다이렉트 홉 예산이 전송 **후**에 차감되어 상한이 초과될 수 있다

- 위치: `app/preview/retrieval.py:1150-1180`(첫 홉만 전송 전 차감, `fetch.hop_count-1`은 응답 뒤 차감),
  `:146-148`(`hop_count = max(1, len(redirects))`).
- 트리거: 후보 URL이 리다이렉트를 2회 이상 포함하고 남은 API 예산이 그보다 적을 때.
- 영향(재현, 가짜 HTTP 클라이언트로 계상 경로만 관측): `api_requests=3`, `hop_count=4`(시작 1 + 리다이렉트 3)를 보고한
  응답 1건에서 클라이언트 호출은 1회였고 그 안에서 4홉이 일어났다고 보고됐는데, 예산 계상은 3회,
  `network_usage.http_used`도 3으로 남았다. 그리고 그 출처는 정상 수용됐다. 즉 **허용된 상한보다 많은 홉이 예산 밖에서**
  발생하고 사용량 보고가 실제보다 적다. 같은 코드 경로가 실제 `ScraplingHttpClient`/`StandardHttpClient`에도 적용된다
  (두 클라이언트 모두 리다이렉트를 내부 루프로 따라간 뒤 `redirects`를 채워 돌려준다, `retrieval.py:314-377`·`:226-290`).
  설계 §45("요청 전 예약·차감", "리다이렉트와 실패도 전송으로 센다")와 어긋난다.
  기존 테스트 `test_budget_charge_counts_redirect_hops_and_stops_at_ceiling`은 상한 2·2홉 사례만 보므로 이 초과를 관측하지 않는다.
- 가장 작은 수정: 홉 차감을 클라이언트 루프 안에서 다음 홉을 보내기 **전에** 하거나, 호출 전에 `MAX_REDIRECT_HOPS+1`을
  예약하고 실제 사용분만 남기고 반환한다.

### F8. 전달 기록을 붙인 뒤에도 저장 묶음의 `bundle_hash`가 갱신되지 않는다

- 위치: `app/preview/information_bundle.py:859`(`payload["bundle_hash"] = self.bundle_hash or bundle_hash(payload)`),
  `app/preview/bundle_pipeline.py:1032-1051`(`with_section_delivery` 후 다시 저장).
- 트리거: 새 경로의 모든 실행(수집 저장 → 마무리 저장 2회).
- 영향(재현): 수집 시점 해시(`a11d5d61…`)가 전달 기록 1건을 추가한 뒤에도 그대로 저장된다. 같은 내용으로 다시 계산하면
  `4cce476a…`가 나온다. 그래서 관리자 화면·아티팩트의 `bundle_hash`는 **저장된 묶음 내용을 설명하지 않는다.**
  `bundle_summary`도 이 값을 그대로 쓰므로 인계·비교 근거로 쓸 수 없다.
- 가장 작은 수정: `to_dict()`가 항상 현재 내용으로 해시를 계산하거나(`from_dict`로 받은 값을 신뢰하지 않거나),
  전달 기록을 붙인 뒤 해시를 다시 계산해 저장한다.

### F9. 배당 섹션은 새 경로에서 구조적으로 항상 비어 있다

- 위치: `app/preview/bundle_pipeline.py:735-746`(`collect_with_bodies`에 `home_team_names`/`away_team_names` 미전달),
  `app/preview/retrieval.py:1080-1081`(기본값 빈 튜플)·`:1569-1574`(조기 반환)(팀 이름이 없으면 즉시 `team_names_required`로 미채택).
- 트리거: 수집한 출처 본문에 정규시간 1X2 표가 실제로 들어 있는 경우.
- 영향: 팀 이름이 인자로만 들어오므로 `_collect_odds`가 항상 조기 반환한다. 그래서 `section_odds`의 채택 줄 수는 항상 0이고,
  진단에는 내부 사유 문자열 `team_names_required`가 남는다. 배당은 선택 섹션이라 필수 판정을 막지는 않지만,
  **표를 확보해도 표시될 수 없는 배선**이라 "공개 자료에서 정규화한다"는 설계 §35·§58의 기능이 새 경로에서 작동하지 않는다.
  D0이 이미 팀 이름을 알고 있으므로(`db_snapshot.teams`) 배선 누락으로 보인다.
- 가장 작은 수정: 파이프라인이 DB 스냅샷의 홈/원정 팀 이름을 `collect_with_bodies`에 넘긴다. 이름이 정말 없을 때만
  미채택 사유를 남긴다.

## 4. 실제 실행 증거와 대조 (A 보고 vs 코드)

`evidence/ps05-live/live-20261111T045112Z-0d938572-…json`을 코드 경로와 대조했다. 이 실행은 run
`0d938572-8427-409f-99f5-f805bee4c697`, 시각 `04:51:12Z`–`04:51:44Z`, `mode=live`, 결과 `failed/insufficient`다.

| 관측값 | 코드와 일치 | 비고 |
|---|---|---|
| 실제 전송 4회, 상한 8, `api_used=0`, `reservations_returned=2` | 일치 | 조사2 + 선수1 + 전망1. 시작하지 않은 작성 2건 예약 반환 |
| 장부: 시도 4행·`section_deliveries` 5건 | 일치 | 배당·미시작 섹션은 `model_delivered=false` |
| `sources` 0건, `diagnostics`에 `no_usable_sources`·`extraction_dependency_missing` | 일치 | trafilatura 미설치 상태였고 그 사실을 숨기지 않음 |
| `section_players` 본문 0자 → 전체 `failed` | 일치 | 필수 섹션 미완을 정상 완료로 위장하지 않음(정직) |
| AI 전망 본문 "구체적인 리그 순위 정보가 제공되지 않아" | **F1과 같은 증상** | 당시엔 리그 ID 공간 문제도 겹쳤다. 현재 코드에서도 `_db_material` 키 불일치로 같은 문장이 나온다(재현) |
| 배당 줄 0 | F9와 정합 | 팀 이름 미전달로 항상 0 |

정직성 측면에서 이 실행은 잘못된 성공을 만들지 않았다. 다만 **필수 섹션이 비어 실패로 끝난 원인의 절반은 자료 부재가 아니라
F1·F2의 배선 결함**이다. A 보고 §9는 "조사 후보 0건이면 필수 섹션이 비어 failed"라고만 적었고, 같은 실행에서
DB 순위·통계를 읽었음에도 프롬프트에 전달되지 않은 사실은 적지 않았다. 이번 검토의 F1·F2가 그 부분을 보완한다.

## 5. 저장된 검사 증거 점검 (개수 아닌 단언)

- `evidence/ps01-preflight/recorded-preflight.json` — 기록 transport 기준 9개 확인이 모두 `ok`다. 특히
  `normal_six_sends`(예산 6·장부 6), `ninth_send_refused_without_transport`(시도 8에서 멈춤), `post_send_failure_keeps_charge_and_body`
  (전송 1·사용량 있는 행 1), `ledger_unchanged_by_replay`(재생 후에도 8)는 수용 기준 1의 핵심을 실제로 관측한다.
  이 파일도 "live 성공으로 인용하지 않는다"고 스스로 밝힌다.
- `test_bundle_pipeline.py::test_branches_run_in_parallel_with_one_budget_and_own_sessions` — 장벽으로 **병렬을 강제**하고
  `barrier.broken=False`, `peak<=2`, 논리 호출 6개 중복 0, 장부 6, 상한 8, 저장 섹션 5개, 갈래 세션이 실행 DB에 붙음을 단언한다.
  수용 기준 2에 대해 의미 있는 단언이다(성능 수치가 아니라 겹침·중복·상한을 본다).
- `test_bundle_pipeline.py::test_bundle_pipeline_db_only_still_reaches_forecast` — DB 자료만으로 전망 호출이 나가고
  선수 미작성이 전체 실패를 유발함을 단언한다. 다만 "DB 자료가 프롬프트에 실제로 들어갔는가"는 단언하지 않는다(F1의 사각지대).
- `test_bundle_runtime.py` — 후처리 예외 후 원문·사용량 보존, 수집 전용 0전송, 재시작 상한 유지, 8에서 정지,
  설정부족 미계상, 예약 반환, 수동 결과 미중복 계상, mock/replay 미계상, 전송 전 크래시 시 예약 유지·보고,
  장부 없는 네트워크 전송 거부(`JournalRequiredForNetworkSend`), 기록 live transport는 장부 불요를 각각 단언한다.
  수용 기준 1의 요구를 실제로 덮는다.
- `test_bundle_sections.py` — 선수 팀당 2명/전체 4명 상한, 부상 팀당 2명, 매체 3곳·점수 미제시 시 `None`,
  스코어가 인용문에 있을 때만 유지, 프롬프트 버전 상수 안정성을 단언한다. 정직성 규칙(수치 생성 금지)을 직접 본다.
- 사각지대(위 F들과 대응): 전망 구조화 투영(F3), 스코어 없는 전망의 필수 판정(F4), reuse 실행기가 실제로 묶음을 쓰는지(F5),
  `availability` 키 모양(F6), 다중 리다이렉트 홉 초과(F7), 전달 추가 후 해시(F8), 배당 팀 이름 배선(F9)에 대한 단언이 없다.
- `test_outlook_module.py` 15건은 기존 시계 문제로 제외 지시대로 확인·수정·재실행하지 않았다.

## 6. 참고 개선 (이번 작업을 막지 않음)

- **R1. 배당 승인 버전 축이 비어 있다.** `registry.py:303-311`의 `section_odds`는 `module_ids=("D0",)`이고
  `version_manifest.py:100-120`의 `_compose_manifest`가 `section_odds`에 `("", "")`를 돌려준다. 계산된 버전은
  `section_odds@61e09b66690638fb`로 **D0와 출력 계약만** 반영한다. 실제 배당 정규화(`retrieval._collect_odds`/`parse_odds_table`,
  `bundle_sections._odds_section`)가 바뀌어도 승인 버전이 그대로다. 설계 §88이 배당을 "결정적으로 정리한 완결 결과"로 승인 대상에 넣었으므로
  버전 축에 그 구현이 들어가야 한다.
- **R2. `korean_labels`를 파싱하고 쓰지 않는다.** `bundle_sections.py:1058`에서 `_model_korean_labels(parsed)`를 변수에만 담고
  이후 사용하지 않는다. 설계 §66의 "없으면 같은 모델 응답의 한글 표기를 활용"이 새 경로에서 구현되지 않은 상태다.
- **R3. 이름 해석기를 주입하지 않는다.** `bundle_pipeline.py:827-835`가 `build_bundle_section`에 `resolver`·`fixture_names`를
  넘기지 않으므로 DB 한국어 이름 해석 경로(`_name_resolver`, `display_names`)가 새 경로에서 쓰이지 않는다. 현재 저장 팀명이
  이미 한국어여서 표면화되지 않았을 뿐이다.
- **R4. 전달 해시 대조에 한 단계 추출이 필요하다.** `SectionDelivery.payload_sha256`은 `{"contents": [...]}`로 계산되는데
  (`bundle_sections.py:854`), 저장된 요청 아티팩트는 `{endpoint, provider, model, parameters:{contents…}}` 모양이다
  (`provider.py:348-358`). manifest §1.2의 "저장된 요청 아티팩트와 대조해 확인"을 하려면 `parameters.contents`를 꺼내야 한다.
  값은 일치하나 대조 절차가 문서에 없다.
- **R5. 관리자 화면의 '전달 후보'와 '실제 전달' 구분은 잘 되어 있다.** `informationBundle.ts:483-491`과
  `InformationBundlePanel.vue`가 후보 구간을 실제 전달로 그리지 않고 `section_deliveries`만 신뢰한다. 이 부분은 참고로 남긴다
  (결함 아님). 다만 F6 때문에 묶음 부재 사유만 전달되지 않는다.

## 7. 현재 수용 기준별 판정

| 기준 | 판정 | 근거 |
|---|---|---|
| (1) 6논리요청·숨은 단계 없음·전송 전 장부·pending 상한 유지·응답 원문 보존·비밀값 없음 | **통과** | 파이프라인 노드 구성(조사2·작성3·전망1, 배당0), `_journal(pending)`→`transport.send`→결과 장부 순서, `preflight`·`test_bundle_runtime`의 단언. 상한 초과 없음 |
| (2) LangGraph 합류·갈래 세션·예산 일관, 중복 호출·유실 없음 | **통과** | `build_bundle_graph`의 fan-out/join, `sessionmaker(bind=session.get_bind())`, 장벽 병렬 검사, 논리 호출 중복 0, 섹션 5건 저장 |
| (3) 묶음→요청 구간/해시→본문→DB 구조화·원문 UI 연결, 재생성/재처리 새 버전 | **부분 실패** | F3(전망 구조화 미연결), F5(reuse 재생성이 묶음 미사용), F8(해시 불일치). 재처리 새 버전·다른 섹션 미재호출은 통과 |
| (4) 필수(AI 전망·스코어·선수)/선택(부상·매체·배당) 처리, 승인 버전 | **실패** | F4(스코어 없이 성공), F1·F2(필수 섹션 근거 미전달), F9(배당 항상 0), R1(배당 승인 축) |
| (5) 출처·ID 공간·한글명·팀 수·매체 점수 미제시·확정 부상·1X2 미조작 | **부분 실패** | ID 공간은 D0이 내부 값 우선으로 고침(통과), 매체 점수·부상 상태 승격 금지·1X2 값 범위는 통과. F1(부상 근거 미전달)·R2(한글 표기 미사용)가 남는다 |

## 8. 수정 후 확인 요청 범위

전면 재검토가 아니라 아래 항목만 본다.

1. F1·F2: 같은 픽스처(순위 2행, 부상 1행, 통계 55행)에서 작성·전망 프롬프트에 순위 문장·부상 사실·선수 후보가 실제로 들어가는지.
2. F3: 새 경로 전망 결과의 `structured.forecast.score`가 저장 payload와 일치하는지.
3. F4: 스코어 없는 전망이 `insufficient`로 내려가고 실행이 성공으로 표시되지 않는지.
4. F5: `reuse` 실행이 실제로 묶음만 쓰는지(검색 도구 요청 0), 또는 응답 문구가 사실에 맞게 바뀌었는지.
5. F6: 묶음 없는 실행에서 서버 사유가 화면 값으로 전달되는지.
6. F7: 다중 리다이렉트에서 실제 전송 수와 계상 수가 같은지.
7. F8: 전달 기록이 붙은 묶음의 저장 해시가 그 내용으로 다시 계산한 값과 같은지.
8. F9: 팀 이름이 있는 경기에서 배당 표가 채택되는지(자료 없을 때는 여전히 미채택).

## 9. 검토 한계

- 실제 유료 실행·HTTP 수집·DB를 다시 호출하지 않았다. 그래서 F1·F2·F9의 **최종 사용자 화면** 영향은 저장된 실행 1건과
  코드 경로로 판정했다. 실제 수집이 성공한 실행에서의 본문 품질은 A가 받을 후속 실행 증거로만 확인할 수 있다.
- 프론트엔드는 F6의 계약 불일치만 확인했다. 시각·레이아웃·접근성 검사는 이번 범위가 아니다.
- `bundle_pipeline.py`와 `discovery.py`가 검토 중 바뀌었다(§1.1). 인용은 종료 시점 해시 기준이며, 이후 추가 변경이 있으면
  §8의 좁은 확인으로 다시 맞춘다.

**EDITING STOPPED** — 이 보고서 작성 이후 이 세션은 어떤 파일도 추가로 만들거나 고치지 않는다.
