# 단일 LLM 호출 프롬프트 실험 — 맨유·본머스

현재4회 호출 worker를 교체하지 않는 요청안이다. 사용자는 맨유–본머스 기준 프롬프트와 DB 자료를 함께 구성하도록 요청했다. 외부 LLM/API 호출·DB 쓰기·게시·배포는 하지 않았다.

## 구성

- `system.md`: 검색·선정·판단·최종 JSON 생성을 한 요청 안에서 수행하는 한국어 지침.
- `response.vertex.schema.json`: 실험용 응답 계약. 현재 public endpoint 계약과 다르며, 기존 UI에 바로 게시하는 형식이 아니다. 부상마다 원인/사건 유형/날짜 정밀도/서술형 시점/근거를 연결한다.
- `scripts/build_home_preview_single_call_request.py`: 읽기 전용 DB 트랜잭션으로 원자료를 준비한다. provider를 호출하거나 자동 생성 설정을 바꾸지 않는다.

## 실제 준비 자료

경기1557445, 프리미어리그2026시즌, 맨체스터 유나이티드(홈33)–본머스(원정35), 킥오프2026-10-25 14:00 UTC(23:00 KST).

격리 로컬 DB55441의 현재 자료에서 양팀 최근5경기씩, 부상 후보12명과 출전 비중 자료, 관전 선수 후보8명의 시즌·최근 기록·확인된 연속 기록, 저장된 배당3개 북메이커, API-Football 알고리즘 예측을 입력했다. 선수·팀 번역명을 사용하고 정식 영문명은 검색 식별용으로 함께 보존한다.

fixture-scoped injury 테이블은0행이다. 부상·배당·API 예측은 해당 DB의 기존 version30에 보존된 API 수집본에서 읽었다. 출처·자료 시각·version을 명시하며 이전 LLM 분석/선정/웹 전망/원인 결과를 재입력하지 않았다. 최신 운영 DB의 상태를 대표한다고 주장하지 않는다.

출력 파일은 `out/home-preview/single-call-manutd-bournemouth/`에 있다.

- `db-input.json`: 실제 DB 자료 및 출처·시각.
- `prompt.md`: 시스템 지침+실제 DB 입력을 합친 검토용 전문.
- `request.json`: Google Search 도구·시스템 지침·DB 입력·responseSchema를 포함한 단일 generateContent 요청 body. 인증정보 없음.
- `manifest.json`: 모델 설정·기준 시각·후보 수·요청 크기 및 미실행 상태.

생성 당시 입력 기준10:55:26 UTC, request body 약47KB, 실제 모델/API0회·DB 쓰기0회다. Vertex에서 검색 도구와 이 구조화 schema 조합의 실제 호환성·grounding 반환·시간/비용/내용 정확도는 아직 실행 검증하지 않았다. 요청 body가 준비된 것과 실행 성공은 구분한다.

## 전달과 저장 원칙

LLM은 한 요청 안에서 DB를 해석하고, 주요 결장 선수 선정→해당 선수 원인/발생 시점 조사→외부 전망 검색→프리뷰 JSON을 작성한다. 원인과 발생 시점의 문맥 해석은 LLM에 맡기고, 날짜 형식·ID·원문 인용·출처 참조와 시각 정합성은 서버에서 검사하는 방향이다. 이 서버 adapter와 실제1회 호출은 이번 작업에 포함하지 않았다.

최초 발생·재발을 분리하고 날짜가 불명확해도 확인된 경기/훈련 시점은 timing_text에 남긴다. 3개 매체는 검색 목표이며 부족한 자료를 만들어 채우지 않는다. API 예측은 독립 매체 수에서 제외한다. 서버가 응답 본문과 groundingChunks/groundingSupports를 함께 보존하고 출처를 확인해야 하며, 모델의 original_checked 표시는 독립적인 검증 완료를 뜻하지 않는다.

## 재생성

메인 전용 환경에서 TEST_DATABASE_URL을 로컬 테스트 DB로 설정한 뒤 실행한다. DB 연결문자열은 저장 파일에 기록하지 않는다.

```sh
PYTHONPATH=. .venv/bin/python scripts/build_home_preview_single_call_request.py \
  --fixture-id 1557445 \
  --output-dir out/home-preview/single-call-manutd-bournemouth
```

응답 계약은 실험용이다. 검증 후 실제 worker 전환과 현재 FE 계약 adapter는 별도 구현한다. 기존6시간 갱신·DB-only 홈 조회·자동 생성OFF는 유지한다.

## 실제 호출·출처 보완·재시험 — 2026-10-25

초기 준비 이후 사용자가 실제 호출·로컬 표시 및 URL 보완 재호출을 요청했다. 아래 기록이 앞의 미실행 상태 설명을 대체한다. 기존 worker4회 흐름과 public publication은 변경하지 않았다.

첫 응답은11:04:55~11:05:34 UTC, 모델1회로 보존했다. 본문 정보와 URL 생성 오류를 구분해야 한다. 실제 Google grounding에 있던 Football365 링크는 올바른 match-preview 주소였지만 모델이 JSON에 작성한 /news/... 주소는404였다. Sports Mole의 모델 URL도 다른 기사 번호였다. 원문이 존재하는데 출처가 없다고 판단한 것은 정정한다.

보완 사항:

- 모델 응답 schema에서 URL/게시일/verification 필드를 제거했다. 모델은 출처 ID·매체·제목과 주장·인용을 반환한다. 모델 URL을 fetch하거나 게시하지 않는다.
- `home_preview_grounding.py`가 원 응답 JSON의 문자열 필드 경로와 Google groundingSupports의 UTF-8 바이트 범위를 연결한다. segment text/범위/partIndex를 검증하며 잘못된 구간을 다른 주장에 붙이지 않는다.
- 실제 URL은 groundingChunks의 URI를 따라가 원문 응답에서 확정한다. 검색 메타데이터의 매체 도메인만 기존 수집 목록에 호출 단위로 추가하고 HTTPS/redirect/공개IP/시간/크기 제한은 유지한다. 모델이 적은 호스트는 추가하지 않는다.
- 출처별 짧은 인용을 원문과 대조해 동일 매체·유일한 기사에만 연결한다. 임의의 같은 매체 기사나 비슷한 도메인으로 대체하지 않는다. 문장부호·대시 차이만 정규화한다. 주장과 출처의 연결과 사실 전체의 확정은 구분한다.
- 웹 근거가 있는 summary/key_points/player_watchpoints에는 웹 출처 ID도 인용하도록 프롬프트를 보완했다. 원 응답은 수정하지 않고 별도 resolved.json에 서버 URL과 필드별 grounding_links를 기록한다.

재시험은 `out/home-preview/single-call-manutd-bournemouth-v2/`에 보존했다. 첫 요청은 HTTP429로 실패했고 attempt-1.json을 보존했다. 대기 후 같은 요청이36초에 성공했다. 이번 모델 요청 누적2회(실패1+성공1), 추가 분석/추출 LLM0회, 검색 쿼리8개, groundingChunks5개다. 정상 흐름은1회 요청이며 재시도를 숨기지 않는다. DB 입력은 최초 읽기 전용 입력을 그대로 사용해 URL 보완 전후를 비교했다.

|출처|새 응답 전망|서버가 확정한 실제 URL|검증|
|---|---|---|---|
|Sports Mole|맨유1–2본머스|https://www.sportsmole.co.uk/football/man-utd/preview/man-utd-vs-bournemouth-prediction-team-news-lineups_607577.html|Google 출처·원문 인용 일치|
|Sports Illustrated|1–1|https://www.si.com/soccer/man-utd-vs-bournemouth-preview-predictions-lineups-10-25-26|Google 출처·원문 인용 일치|
|Goal|2–2|https://www.goal.com/en-us/betting/tips/manchester-united-vs-bournemouth-predictions-10-25-2026/A%3Abltdf693f236e81339c|Google 출처·원문 인용 일치|
|Football365|관전 포인트/선수 기사 근거|https://www.football365.com/match-preview/man-utd-v-bournemouth-prediction-preview|해당 문장과 Google 출처 연결|

새 응답에는 URL 문자열 생성0, 서버가 모델 URL을 사용한 횟수0, 원문 fetch 실패0, segment 검증 오류0, 필드별 출처 연결9개다. 외부 전망3곳의 각 예상 스코어 인용을 확인했다. **모든 문장의 의미를 자동 검증했다고 주장하지 않는다.**

마이누10월10일/스콧10월3일이라는 발생일은 LLM이 반환했지만, 이번 메타데이터에는 해당 RotoWire/Guardian 출처가 없어 원문 URL을 확정하지 못했다. 내용이 틀렸다는 판정이 아니라 출처 연결 미확인이다. 날짜를 지우거나 확인 완료로 바꾸지 않고 로컬 화면에 미검증으로 표시한다.

첫 응답도 새 resolver로 회귀 확인했다. Football365는 기존 Google 출처, Sports Mole은 사용자가 제공한 원문으로 URL·인용을 확인했으며 origin을 각각 기록했다. 이는 새 응답의 Google-only 검증과 구분한다.

로컬 화면: http://127.0.0.1:5191/home/single-call/1557445 (개발 전용). 메인에 진입 링크를 추가했다. 실제 응답 본문·모델 발생일·출처 확인 상태·DB 번역명/선수 사진·기존 저장본·첫/두번째 원문 JSON을 볼 수 있다. 기존 검증 프리뷰 DB를 미확인 응답으로 교체하지 않았다. 배포 빌드에는 실험 route/data가 포함되지 않는다.

검증: BE46 PASS(출처 연결/UTF-8/URL 생성 거절/비슷한 매체 도메인/기존검색), FE29 PASS, frontend build PASS. 실제 로컬 브라우저에서 메인 링크→새 응답 본문/JSON 일치·실제 기사607577/Football365 주소·첫 잘못된 URL 미사용·발생일·선수 이유·데스크톱1440/모바일390·overflow0/pageerror0를 확인했다. 결과/스크린샷은 v2 폴더에 보존한다. 단일 호출 실험 자체에 DB 쓰기/운영 반영/원격 push/merge/배포는0회다.

원 응답·검증 결과:
- `response.txt` / `response.json`: 수정하지 않은 LLM 응답.
- `grounding.json`: Google 원 검색 메타데이터.
- `resolved.json`: 실제 URL·필드별 출처를 연결한 결과.
- `source-resolution.json`: 출처별 원문 인용 확인/연결 미확인 진단.
- `original-pages.json`: 실제 가져온 원문 및 URL/게시 정보.
- `execution.json` / `attempt-1.json`: 성공·429 및 누적 호출 수.

재검증은 추가 LLM 호출 없이 다음과 같이 수행한다.

```sh
PYTHONPATH=. .venv/bin/python scripts/resolve_home_preview_single_call.py \
  --run-dir out/home-preview/single-call-manutd-bournemouth-v2
```

기술 근거: Google GenerateContentResponse의 GroundingSupport/Segment는 출처 인덱스와 UTF-8 바이트 구간을 제공한다. https://cloud.google.com/vertex-ai/generative-ai/docs/reference/rest/v1/GenerateContentResponse


## 2026-10-25 후속: 기존 공개 JSON 계약 복원

이 절은 앞의 별도 실험 응답 형식 설명을 대체한다. `system.md`와 요청 생성 도구는 이제 `docs/spec/schemas/home-preview-payload.schema.json`에서 변환한 Vertex 스키마를 사용한다. 기존 `analysis/facts/external/sources` 필드·자료형·null 정책을 보존한다. AI 경기 예측은 `analysis.ai_prediction.data`의 `home_goals/away_goals/confidence/reason/evidence_ids`를 채우며, 문자열 스코어·null 스코어·API 알고리즘 소개로 대신하지 않는다. 실제 요청과 최종 저장본에 기존 JSON Schema 및 BE 의미 검증을 적용한다.

DB 폼·선수 기록·번역명·사진·부상 후보의 출전 상태·배당·DB/API 근거는 원본과 대조한다. 선택한 부상 선수만 기존 `cause` 필드에 원인/확인된 발생일을 담으며, 출처 메타데이터는 서버에서 연결한다. 카드에서는 선수·출전 상태·부상/원인·확인된 발생일만 표시한다. 출처와 선정 기록은 내부 데이터에 보존하며, 카드의 출전 기록/출처/미확인 날짜 줄은 제거했다.

실행 도구: `python -m scripts.run_home_preview_existing_contract --fixture-id 1557445 --output-dir <실행 폴더> --env-file <인증 파일> [--as-of <로컬 재현 기준 시각>] [--publish]`. TEST_DATABASE_URL은 전용 로컬 127.0.0.1:55441/home_preview_test만 허용한다. `--prepare-only`는 요청 파일만 작성하며 모델 호출/DB 쓰기가 없다. 정상 완료 모델 요청1회, 실패 시 최대3회로 제한하고 모든 시도 원문·사용량·실제 실행 시각을 보존한다. 출처가 연결되지 않은 부상 원인/날짜는 확인된 값으로 저장하지 않는다. 새 버전 저장과 publication 포인터 갱신은 한 트랜잭션이며, 기존 버전을 보존하고 저장 전후 fixture/포인터 변경을 검사한다.

맨유–본머스는 작업 도중 실제 킥오프(2026-10-25 14:00 UTC)를 지났다. 정상 생성 정책을 우회하거나 생성 시각을 조용히 바꾸지 않는다. 테스트 시계 고정 재현은 사용자 확인 후 실행하고 실제 호출/생성 시각을 snapshot 및 실행 기록에 별도로 보존한다. 프롬프트 수정·테스트 완료와 실제 새 생성·DB 반영 완료는 구분한다.

## 2026-10-26 최신: 직접 저장과3회 연속 성공

최신 동작/목표 정본은 [targets.md](targets.md)다. 앞선 URL resolver·문장 파싱·저장 전 문구 검사 설명은 이번 직접 저장 회귀에 적용하지 않는다. 실제 생성 회귀 실행기는 `scripts/run_home_preview_direct_regression.py`이며, 저장용 계약 전체를 프롬프트 입력에 포함한다. 수집 원문 재사용과 새 브라우저 검색 실행은 구분한다. 완료 여부는 실제 execution.json으로 판정한다.

### 최종 직접 저장 검증

2026-10-26 맨유–본머스의 DB입력값 검증3회 연속 성공(version49/50/51). 최종 실행은 유효후보3개/HTTP4요청(429전송재시도1개)다. 응답후 원인·날짜·이유를 추출/교체하지 않고 JSONB에 원문객체를 저장하며, 새DB session·실제HTTP·화면과 대조했다. 실제결과·파일·판정기준·전송재시도 구분은 [직접 저장 검증](direct-storage-verification.md)을 따른다. BE104/FE33/E2E17/build PASS. 기존수집원문을 재사용한 로컬과거재현이며 정상worker전환/운영적용과 구분한다.
