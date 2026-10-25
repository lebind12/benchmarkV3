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
