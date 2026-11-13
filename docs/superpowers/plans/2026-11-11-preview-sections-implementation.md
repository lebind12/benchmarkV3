# 경기 프리뷰 섹션 구현 계획

> 실행: 사용자가 설계 승인과 계획 작성 후 개발 착수를 지시했다. pstack 조정자는 GPT, 구현·독립 검토는 실제 Orca dsh-tui DeepSeek 세션만 사용한다. Superpowers의 별도 실행기를 중복 호출하지 않는다. 추가 계획 승인 대기로 멈추지 않는다.

**Goal:** 브라우저 없는 기사 수집과 DB 자료를 공유해 승인 가능한 섹션 및 최종 한국어 프리뷰를 관리자 화면에 저장·표시한다.

**Architecture:** 선수·부상 / 외부 매체·배당의 두 조사 묶음에서 URL을 찾고 공통 수집기로 실제 본문을 확보한다. 선수·부상·매체 작성은 독립 처리하고 배당은 결정적으로 정리한다. 최종 AI가 각 결과와 DB 경기력 자료로 전망·점수를 작성한 뒤 화면은 저장 결과를 배치한다.

**Tech Stack:** 기존 FastAPI/SQLAlchemy/PostgreSQL preview_dev, LangGraph, Vertex Google Gen AI SDK, Vue/Vite. 구현 조사 후 기본 HTTP는 httpx, 추출은 Trafilatura + Scrapling core parser로 결정했다. scrapling[fetchers]의 불필요한 브라우저 자동화 의존성과 브라우저 바이너리·별도 검색 SaaS·벡터DB를 추가하지 않는다.

**Spec:** [확정 설계](../specs/2026-11-11-preview-sections-design.md), [사실 조사](../../implementation/match-preview/section-workflow-integration-facts.md).

## Global Constraints

- 정상 모델6 / 전체 실제 전송8 / 동시2. 조사2+작성3+최종1. 비모델 HTTP/API24 공유, 동시2, 요청30초, 실행1800초. 실패/리다이렉트도 전송 계수.
- 새 구현에③을 같이 만들지 않는다. 자료 부족으로 자동 조사 반복·모델 교체·예산 초기화하지 않는다.
- public 기존 자료는 읽기만, 새 쓰기는 preview_dev. 운영 URL에 파괴적 fixture 실행 금지. 격리된 기존 test_* 또는 *_test DB만 합성 테스트에 사용.
- 기사와 DB 교차 대조/탈락 없음. Google 인용 메타데이터 필수 아님. 별도 사실 심사 엔진 없음.
- 필수: AI 전망·점수·주목 선수. 선택: 부상·매체·배당. 선택 누락은 독자 화면에서 생략, 관리자에서는 자료 없음/실패를 구분.
- 주목 선수 팀당2명 목표, 부상 최대2명/팀, 서로 다른 매체 최대3곳, 배당 정규시간1X2 소수점. 없는 선수/스코어/배당 생성 금지.
- DB 한글명 우선, 없으면 같은 응답의 한글 표기. 원문/옛 버전/승인 보존. 새 버전 승인 자동 생성 금지.
- 웹 섹션당 최대6출처·출처당3구간·구간1500자·웹16000자·DB 포함32000자. 전문과 전달구간을 구분.
- 기존 미커밋 삭제/정책/문서/환경/빌드 파일 보존. 구현 워커는 Plans.md를 편집하지 않는다.
- 구현4워커의 파일 소유권 분리. 어느 워커도 git add/commit하지 않는다. 최종 통합 워커만 인계가 확인된 명시 경로를 검토해 스테이징/커밋한다. 공유 인덱스 경합 금지.

## Review Focus

- 수집/준비 동작에서 의도치 않게 모델이 전송되지 않으며 재시작·후처리 오류에도 실제 전송 누적과 응답 원문이 남는가.
- 같은 기사/같은 경기의 중복 수집을 줄이면서도 다른 경기·자료 버전의 입력을 혼합하지 않는가.
- 부분 자료와 빈 부상표를 무부상/전체 성공으로 오인하지 않고 DB-only 최종 전망이 동작하는가.
- 출처ID·구간ID 연결 오류로 실제 수집자료를 전부 탈락시키거나 없는 출처를 채우지 않는가.
- 섹션 재생성/오프라인 재처리가 실제 저장 버전을 만들고 본문·원문·승인 버전을 혼동하지 않는가.

## 병렬 분해·파일 소유권

| 작업 | 담당 | 수정 소유권 | 의존 |
|---|---|---|---|
| PS-01 공통 계약·전송보존·예산·통합 | A 통합 책임자 | information_bundle.py(신규), 기존 contracts/provider/retry/models/store/artifacts/runner/pipeline/sections/registry/version_manifest/approvals/inspection/section_preview/presentation/jobs, backend preview_admin.py/main/config, requirements/pyproject, 개발 마이그레이션 및 등록기 | 먼저 계약 공지, 통합은 B/C/D 인계 후 |
| PS-02 조사·수집·DB 자료 | B 자료 워커 | discovery.py/retrieval.py(신규), sources/player_stats.py(신규), prompts/discovery_*.md(신규), 좁은 stats 역할 신규 프로비저너, 전용 테스트 | 기존 입력으로 독립 구현, A 계약에 연결 |
| PS-03 섹션 작성 | C 작성 워커 | modules/bundle_sections.py(신규), 기존 players/players_contract/availability/outlook/synthesis 및 해당 prompts, modules/__init__.py, 전용 모듈 테스트 | A 계약, B 공개 인터페이스; 기록 자료로 병렬 구현 |
| PS-04 관리자·독자 화면 | D UI 워커 | frontend/src/features/match-preview 전용 파일 전체 및 router/index.ts, 해당 UI 테스트 | API 계약에 맞춰 기록 응답으로 병렬 구현 |
| PS-05 실제 통합·섹션 시험 | A | 인계 완료 파일의 통합, 기존 전용 로컬 서비스, 실생성 도구 신규 경로 | PS-01~04 |
| PS-06 독립 검토 | 별도 새 DeepSeek | 읽기 전용, 자체 보고서만 | 통합 리비전 및 직접 실행 증거 |

테스트 파일을 함께 열지 않는다. A는 test_bundle_runtime.py/test_bundle_integration.py(신규)와 기존 provider/retry/pipeline/approval 테스트, B는 test_bundle_retrieval.py/test_bundle_discovery.py/test_player_stats_reader.py(신규), C는 test_bundle_sections.py(신규)와 해당 모듈 테스트, D는 frontend 테스트만 소유한다. 공유 conftest는 A만 수정 가능하고 현재 기준상 필요 없으면 그대로 둔다.

## 공통 연결 계약

첫 통합 산출물은 `docs/implementation/match-preview/section-interface-manifest.md`다. A가 실제 계약·진입점·API 응답의 정확한 이름과 소유권을 공지한다. 다음은 그 문서가 만족할 인터페이스 요구사항이며 실행 가능한 구현이 아니다.

- `InformationBundle`: bundle ID/version/hash, fixture identity 및 team ID space, collected_at, discovery groups, sources, db_snapshot, delivered passages, diagnostics, network usage. Source는 URL/최종URL/자료성격/방법/제목/시각/본문 artifact/구간/실패를 갖는다. 비밀값은 없음.
- B의 `discover_candidates`: group A 또는 B, 경기·DB 문맥을 소비해 URL 후보/원문 artifact를 반환. 실제 모델 전송은 기존 provider와 A의 공유 RunBudget만 사용.
- B의 `collect_information_bundle`: 후보·DB 문맥·공통 네트워크 예산을 받아 실제 본문과 구간을 포함한 묶음을 반환. 수집 함수가 모델 작성까지 실행해서는 안 됨.
- C의 `build_bundle_section`: section_players / section_availability / section_outlook / section_ai_forecast 중 하나와 bundle/선택 결과 버전을 받아 기존 NodeImplementation/WorkflowImplementations에 연결 가능한 작성 단위를 반환. discovery용 검색 도구를 작성에 중복하지 않음.
- 배당은 B가 원문에서 사이트/시장/관측시각/홈·무·원정 값을 추출해 section_odds 결과 재료를 반환하고 A가 저장한다. 알 수 없는 DOM/시장 값은 진단으로 남기고 AI로 숫자를 만들지 않음.
- Backend 기존 `/sections`, `/section-runs`, `/runs/{run_id}`, `/runs/{run_id}/preview`를 유지·확장한다. 신규 GET `/runs/{run_id}/information-bundle`은 source 및 전달 구간·DB 입력을 관리자에게 제공한다. 기존 `/section-results` 및 비교·승인은 저장 섹션 버전 기준으로 연결한다.
- 섹션 재생성 요청은 workflow_id, fixture_id, source_mode(reuse 또는 refresh), 기준 bundle/run/result ID를 명시한다. 저장 응답 재처리는 별도 무전송 동작이다. A가 manifest에서 요청/응답 필드의 정확한 이름을 확정하며 D와 상호 ACK한다.

초기 구현은 이름 변경이 필요하면 manifest를 먼저 변경하고 조정자에게 통지한다. 타입 파일 동시 수정으로 계약을 맞추지 않는다. 계약 공지 전에는 B/C/D가 자기 자료/함수/화면을 기록 입력으로 구현하고, 공유 파일을 대신 수정하지 않는다.

### PS-01: 계약·예산·원문 보존

- [ ] A가 기존 타입·예산·provider 트랜잭션 경계를 읽고 manifest를 먼저 작성·공지한다. 세부 소유권은 위 표 유지.
- [ ] 대표 직접 검사: 실제 전송 직후 후처리 예외를 주입해도 redacted 요청/응답과 전송 사용량이 보존되고 collect-only는 전송0이며 프로세스 재개가8상한을 초기화하지 않음을 확인한다. 이를 위한 작은 기록 transport 검사를 추가한다.
- [ ] 현재 코드에서 실패함을 확인하고 provider/예산/저장 경계를 구현한다. 실행 전체6회 예약과 미시작 취소 예약 반환, 중복 전송 방지, unknown 보존을 적용한다.
- [ ] `pytest tests/preview/test_bundle_runtime.py -q` 및 실제 변경 영향에 해당하는 기존 provider/retry 검사만 실행한다. 전용 loopback test DB 사용.
- [ ] 기존 preview_dev 아티팩트/JSONB 그릇을 우선 사용하고 부족할 때만 preview_dev 한정 새 migration을 추가한다. public 구조·RLS·계정은 바꾸지 않는다.

### PS-02: 두 조사 묶음·브라우저 없는 수집·DB

- [ ] 기존 후보 URL·격리 실험 결과를 재사용해 조사 A/B 응답과 기사형/목록/403/JS셸 대표 입력을 만든다. 새 모델 전송 없이 모양을 맞춘다.
- [ ] `pytest tests/preview/test_bundle_retrieval.py tests/preview/test_bundle_discovery.py tests/preview/test_player_stats_reader.py -q`의 현재 수용 동작을 작성하고 실패 확인 후 구현한다. 새 테스트는 중복1회수집/구간연결/차단반환/예산/역할읽기 경계에 한정한다.
- [ ] httpx 일반 HTTP + Trafilatura와 Scrapling core 목록 텍스트 폴백을 구현한다. HTTP의 private/loopback 대상 및 리다이렉트 재검사는 현재 수집 경계의 직접 제약으로 둔다. 브라우저/프록시/CAPTCHA 도입 금지. 초기 Scrapling HTTP 제안은 의존성 조사 후 이 경량 경로로 구체화했다.
- [ ] 배당은 접근 가능한 공개 자료의 실제 한 경로를 좁게 지원한다. 후보 사이트와 시장·시간이 맞는지 직접 확인하고 구조를 못 읽으면 미지원으로 남긴다. 비공개 인증/유료 서비스가 필요하면 자동 도입하지 않는다.
- [ ] 선수 시즌 통계는 실제 열·ID/리그/시즌 범위를 확인한다. 필요 시 신규 `preview_dev_stats_ro` 역할에 해당 통계의 필요한 열 SELECT만 주고, PREVIEW_STATS_DATABASE_URL을 기존0600파일에 저장하는 신규 프로비저너를 준비한다. 실제 적용은 조정자와 대상·소유권을 확인하고 A의 설정 연결과 순서화한다. 기존 역할/비밀번호·public행은 변경하지 않는다. 권한·자료가 없으면 unknown으로 반환한다.
- [ ] 기사 전문은 redacted preview_dev artifact 또는 임시 증거에, 저장소 문서에는 짧은 발췌·해시만 둔다. B는 requirements를 직접 편집하지 않고 검증한 최소 패키지 버전을 A에 전달한다.
- [ ] 공개 인터페이스·정확한 파일 목록·기록 테스트 결과·미지원 수집 경로와 EDITING STOPPED를 보고한다.

### PS-03: 근거 묶음에서 섹션 작성

**재개 시 최우선 범위 제한:** 이전 워커가 약40분 기존 모듈 조사만 반복해 어댑터/직접 검사 파일을 만들지 못했고 조정자가 중단했다. 기존 프롬프트 신규4개(bundle_players/bundle_availability/bundle_outlook/bundle_forecast.md)는 보존한다. 새 워커는 manifest §3/§3.1, provider.request_model의 실제 시그니처, 기존 한글명/본문 조립의 필요한 진입점만 읽고 먼저 modules/bundle_sections.py와 test_bundle_sections.py를 작성한다. 오래된 R1~S1 내부 전체 조사·전면 리팩터링·별도 주장검증 분석을 하지 않는다. SectionDraft와 build_bundle_section의 첫 기록 입력 동작을 조기 산출물로 보고하고, 통합에 필요한 새 어댑터만 우선 완성한다. 공유 파일과 옛 모듈의 광범위 변경은 A가 인계 후 필요 범위만 연결한다. 현재 작업을 구현으로 진행할 수 없는 구체적 계약 충돌이 있으면 즉시 가장 작은 질문으로 보고하고 조사를 계속 늘리지 않는다.

- [ ] 현재 파서/한글명/본문 조립을 재사용할 범위를 정하고 새 bundle_sections 진입점과 버전 축을 manifest에 연결한다. 기존 모든 모듈을 전면 재작성하지 않는다.
- [ ] 기사-ID/구간-ID와 DB 입력을 수용하고 공급자 chunks/supports 부재로 탈락하지 않는 대표 검사를 먼저 실패 확인한다. 선수4명 분배, 부상최대2/팀, 매체3곳/점수미제시, DB-only 최종 전망, 입력의 진단이 본문에 새지 않음만 직접 확인한다.
- [ ] 작성3개와 최종전망은 기존 request_model만 사용하고 검색 도구 없이 전달 구간을 소비한다. 배당은 LLM 호출 없음. 기사·DB 비교 필터/별도 평가 모델을 추가하지 않는다.
- [ ] `pytest tests/preview/test_bundle_sections.py -q`와 바뀐 기존 모듈의 대표 검사만 실행한다. 거짓 grounding metadata를 만들어 기존 필터를 통과시키는 우회 금지.
- [ ] 정확한 factory/출력 shape·버전/프롬프트 상수와 EDITING STOPPED를 A에게 인계한다. 구현 도중 새 유료 호출은 하지 않는다.

### PS-04: 정보 원문·본문·재생성·비교·승인 화면

- [ ] 기존 관리자 세션/API 래퍼와 SectionRunView/RunInspector/MatchPreview를 사용한다. 새 디자인 체계를 만들지 않는다. manifest의 API와 서로 ACK한다.
- [ ] 본문·근거를 먼저, 정보 원문과 모델 전체응답은 펼치는 진단으로 제공한다. source_mode와 무호출 재처리/실재생성을 구분한다. 부족한 선택 섹션은 독자 화면에서 생략한다.
- [ ] 기존 저장 응답 형태로 선수명/선정이유 분리·팀별2명·부상상태·매체3곳·1X2 표를 구현한다. frontend 전용 타입·API·라우터의 단일 소유자는 D다.
- [ ] 바뀐 화면의 Vitest 직접 동작 검사와 `npm --prefix frontend run type-check`를 실행한다. 통합 전 placeholder 응답을 live로 표시하지 않는다. 본문 직접편집/출처선택 UI는 만들지 않는다.
- [ ] 정확한 변경 파일/검사결과/남은 backend 연결점 및 EDITING STOPPED를 인계한다. 서버 restart와 실제 사용자 자격증명 사용은 하지 않는다.

### PS-05: 통합·실제 자료 확인

- [ ] A는 세 워커의 명시 인계와 실제 편집 종료를 확인하고 공유 라우터/등록부/버전/파이프라인을 연결한다. 옛 승인·실행은 보존하고 새 기본 경로에서 R1 중복 작성은 제거한다.
- [ ] 기록 transport로 정상6전송/최대8/2동시, 부분자료·DB-only, 섹션독립재실행과 저장응답재처리의 새결과버전, 정보원문→요청→본문 연결을 `pytest tests/preview/test_bundle_integration.py -q`로 확인한다. 유효한 워커 테스트 결과는 재사용한다.
- [ ] 허용된 운영 자료 읽기와 preview_dev 실행소유쓰기/조회·기존 영역 쓰기권한없음을 확인한다. DB public 변경·데이터 초기화 금지.
- [ ] 통합 후 한 번의 실제 프리뷰 시험을 실행한다. 사용자 추가 호출 허용 범위에서 이 계획의 정상6/최대8 task 전체 예산을 적용하고, 별도 smoke pong이나 데이터수집 단계의 숨은 모델 호출은 하지 않는다. 한 차례 실패를 고쳐 재시도할 때도 같은 전체계수를 이어가며 상한에 도달하면 저장응답으로 분석하고 보고한다.
- [ ] 실제 공개 기사·배당 확보량, DB 입력, source ID, 모델요청/응답, 토큰/시각, 저장 섹션 본문과 관리자 조회 결과를 직접 확인한다. 부족한 섹션/미검증 DB-only 경로를 숨기지 않는다. 사용자 워크플로우 승인은 자동 생성하지 않는다.
- [ ] 기존 backend8000/frontend5173를 조정자와 한 번만 순서화해 반영한다. 사용자 세션은 보존하고 frontend HMR로 충분하면 불필요하게 재시작하지 않는다. 실제 브라우저는 사용 가능한 로그인 세션 또는 격리된 테스트 계정만 사용한다.
- [ ] 소유경로를 검사해 한 통합 소유자만 scoped commit한다. 필요 시 dependency단위로 나누되 다른 워커 파일이 인계되기 전에는 stage하지 않는다. push/deploy 없음.

### PS-06: 독립 검토·사용자 인계

- [ ] 별도 새 DeepSeek 읽기전용 세션에 확정 리비전·위 Review Focus·필요 증거를 전달한다. 구현 워커를 독립 검토자로 재사용하지 않는다.
- [ ] 검토는 현재 수용 기준 위반/직접 재현 결함/참고 개선으로 구분한다. 수정 확인은 지적항목과 직접 영향경로만, 전면 반복검토 금지.
- [ ] 조정자가 실제 저장 본문/원문/전송계수와 Plans.md를 대조해 완료/미완료를 기록한다. 사용자에게 섹션 본문과 정보 원문을 확인할 경로를 제시한다. 워커 완료·테스트 성공은 사용자 버전 승인이 아니다.

## 병렬 실행과 종료 기준

### 독립 검토 후 한정 수정 분담

PS-06 읽기전용 검토에서 F1~F9를 확인했다. 코드 동결 상태의 A를 아래 범위에서만 다시 진행하고, 별도 DeepSeek E가 겹치지 않는 변환 파일을 수정한다. 사용자 예산 응답 대기는 유료 실행에만 적용하며 이 코드 수정은 원래 승인된 개발 범위다.

- E 단독 소유: modules/bundle_sections.py, prompts/bundle_forecast.md 및 필요한 bundle 프롬프트, section_structured.py, test_bundle_sections.py, 신규 test_bundle_review_fixes.py. F1/F2의 실제 D0키→프롬프트 연결, F3전망 구조화, F4점수필수, 현재 한글명/같은응답fallback 사용을 수정한다. 새 검증 엔진·기사DB대조 없음.
- A 단독 소유: bundle_pipeline.py의 실제팀/이름조회기/통계문맥 배선·필수판정, preview_admin.py와sections.py/해당통합테스트의 reuse/refresh 실제새작성경로, retrieval.py의홉별전송전예산과팀명배선, information_bundle.py/store.py의현재내용해시와availability응답 계약, version_manifest/등록부. E파일은 편집·스테이징하지 않는다.
- reuse는 실제저장bundle을새작성모듈에주입하고검색/수집0, 다른섹션재호출0이어야 한다. refresh는 선택섹션에필요한조사/수집만 새로하고 다른성공섹션을재작성하지 않는다. 최종전망 refresh는필요한두조사자료/DB를갱신하되기존선택된상위섹션결과버전을명시해재사용한다. 예상호출은실제경로대로표시하며 미지원이면422로정직하게거부하고옛검색경로를묶음재사용으로표시하지않는다.
- 참고개선은 별도 후보로 남기되 R2/R3의 DB한글명 우선·동일응답fallback 미연결은 이미확정한기능이므로 E/A의현재이름배선수정에 포함한다. R4해시대조절차문서는A가짧게명시할수있고새서비스는만들지않는다.
- 검토보고서 §8의8개영향경로와 위이름경로의대표검사만 실시한다. 통과한전송/동시성/전체검사반복·새독립전면검토금지. 기존검토자에게수정항목만1회확인받는다. 고친코드만으로실제외부수집성공을주장하지않는다.
- 추가 유료 예산은 여전히미승인이다. 사용자승인이오더라도수정확인전실제실행하지않고, 허용시새실행한개/추가최대6/누적10/호출당1시도를유지한다.

초기4명은 동시에 각각 공통계약/수집/작성/화면의 자기 파일만 진행한다. A의 manifest가 공유 연결의 기준이며 이후 B/C/D가 인계하면 A가 단독 통합한다. 추가 워커는 독립 검토와 실제로 소유권이 분리되는 차단 해소에만 배정한다. 이미 진행 중인 공유 파일에 속도를 이유로 다른 writer를 추가하지 않는다.

완료 기준은 위 섹션 저장·조회·부분출력·독립재생성·실제자료작성 및 예산/응답보존 증거다. UI 목업만·파일본문만·HTTP200만을 제품 완료로 표시하지 않는다. 필수기능 실패는 남기고 참고개선/미지원사이트 때문에 작업을 무한 확장하지 않는다.
