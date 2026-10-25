# PRE-01 — 추천 경기·저장 프리뷰 조회 계약

2026-10-25. FE 요구/목업 계약이다. BE 구현·실제 데이터 검증·운영 반영 완료를 의미하지 않는다.

## 범위와 결과

기존 디자인을 유지하면서 `/home/mock`가 구조화된 추천 응답과 프리뷰 조회 상태를 소비한다. 메인 `/`는 아직 전환하지 않는다. 공개 조회는 DB 저장본만 읽고 생성/검색/enqueue하지 않는다. 6시간 갱신 정책과 진행 중 경기의 저장 상태 표시를 유지한다.

## 조회 envelope

`GET /api/v1/home/fixtures/{external_id}/prematch`는 transport v1.0을 반환한다. 저장 본문은 v1.1이다. 본문 v1.0→1.1 변경은 nullable generated_at과 최근 경기 status/penalties 추가이며 아직 운영 저장 데이터가 없으므로 PRE-03/04에서 저장 버전/이전본 호환을 명세한다. 기존 방송 Markdown API는 별도다.

| 상태 | publication | preview | refresh |
|---|---|---|---|
| 최초 준비 | pending, served=null, generation_pending | null, 생성/자료 시각 null | queued/running |
| 생성 실패·유효본 없음 | failed, served=null, generation_failed | null, 생성/자료 시각 null | failed, 실제 시도 시각/공개 reason |
| 생성 대상 시각 전 | unavailable, served=null, outside_generation_window | null, 시각 null | idle |
| 정상 저장본 | ready 또는 partial, served=current | 검증된 저장 본문 | idle |
| 갱신 중/실패·유효본 있음 | ready 또는 partial, served=previous | 이전 본문과 원래 시각 그대로 | queued/running/failed |
| 사실 자료만 저장 | partial, served=current | facts/external만 제공, 모든 analysis.data=null, generated_at=null | idle |

ready는 모든 영역 available인 경우이고 이외 유효본은 partial이다. previous는 coverage 상태가 아니라 served 포인터다. 두 fixture ID와 publication/body 시각이 반드시 일치한다. failed/running의 last_attempt_at은 실제 시도 시각이다. 갱신 시각으로 과거 생성 시각을 덮어쓰지 않는다. source/section 시각은 generated_at이 없으면 as_of 이전이어야 하고 모든 근거는 킥오프 전이어야 한다. 일반 사용자가 읽는 실패 reason은 enum이며 provider 원문·키·stack trace를 넣지 않는다. AI 예측 설명 reason은 근거를 인용하는 본문 텍스트로, 상태 코드와 별개다.

HTTP 제안: 잘못된 경로/날짜 422, DB에 없는 fixture 404, 존재하지만 미생성 200 envelope, DB 조회 장애 503. 조회 장애를 저장 생성 실패로 위장하지 않는다. 정확한 오류 body는 PRE-03 명세 gate에서 확정한다. GET은 202 생성 접수를 반환하지 않는다.

## 추천 목록

`GET /api/v1/home/recommendations?date=YYYY-MM-DD`. 미지정 시 서버의 현재 KST 날짜. 실제 달력 날짜를 검증한다.

- requested_date/display_date/timezone/fallback_reason, DB snapshot as_of, policy_version을 제공한다. 각 fixture에 상태를 확인한 status_as_of를 보존한다. 응답을 만드는 현재 시각을 DB 기준 시각으로 사용하지 않는다.
- ongoing → scheduled, 우선순위 1~8, kickoff_at, fixture_id 순. 최신 정책은 plan.md §5.2.1이다. 모든 자격 충족 경기를 반환하고 4개로 자르지 않는다. 중복·오늘 결과와 겹침·동일 팀끼리의 fixture를 거부한다.
- 오늘 자격 경기 없음: 보관 중인 활성 최신 2시즌의 미래 DB 일정에서 가장 가까운 자격 충족 예정 날짜. fallback은 scheduled만 허용한다. 미래 일정에도 없으면 빈 items, display_date=requested_date, fallback_reason=null이다. 미래 검색은 DB 조회이며 시즌 전체 AI 생성이 아니다.
- 동적 리그의 external_id/name/category/round를 전달한다. domestic_cup은 수집 대상 메타데이터에서 판정하며 초기 5개 ID/화면 이름으로 제한하지 않는다. 새 대회의 추천 자격 자체는 기존 우선순위 정책을 따른다.
- preview 요약에는 coverage state, served, generated_at/as_of만 담는다. 본문은 선택 fixture 조회에서 가져온다. 미생성 summary에 가짜 시각을 넣지 않는다.
- today_results는 요청 KST 날짜의 종료 경기와 DB 최종 점수다. ongoing 추천에는 점수를 제공하지 않는다. polling/카운트다운을 추가하지 않는다.

AI 생성 범위는 현재부터 킥오프 전 24시간 이내인 자격 충족 scheduled만이다. KST 00/06/12/18 수집 뒤 최대 네 번이라는 확정 정책은 유지한다. 24시간 밖의 미래 추천은 생성 대상 시각 전 상태를 표시할 수 있다.

## 최근 폼과 컵 결과

완료 FT/AET/PEN만, 모든 대회, fixture 킥오프와 근거 snapshot 이전의 최신 5경기다. PRE-05에서 실제 DB cutoff와 완료 확인 시각을 검증한다. goals_for/against는 해당 경기의 최종 점수이며 AET/PEN에는 연장 포함 점수다. 90분 점수를 추정하지 않는다. PEN의 penalties는 별도 보존하며 알려진 승부차기 점수로 승/패를 표시한다. 승부차기 점수 미확인이면 `?`이며 임의 무승부/승리로 만들지 않는다. FT/AET는 최종 점수 기준이다. FT/AET의 penalties는 null, 알려진 PEN 점수는 본경기 동점·승부차기 비동점이어야 한다. 1~4개만 있으면 partial, 0은 missing이다.

## 개발/검증 경계

Zod가 런타임 strict 구조와 교차 필드 불변식을 검사한다. `frontend/scripts/export-home-preview-contracts.ts`가 payload/response/recommendations/analysis JSON Schema와 상태별 예제를 만든다. 실행: frontend에서 `./node_modules/.bin/vite-node scripts/export-home-preview-contracts.ts --write`. 구조 스키마에는 Zod superRefine을 자동 이식하지 않는다. 위 시간/소유권/정렬 불변식은 Zod 단위 테스트에서 검증하고 PRE-03의 Pydantic 동등 실패 fixture로 이식한다. JSON Schema 단독 통과를 의미 검증 완료로 간주하지 않는다. Vertex subset은 별도 유지하며 PRE-02에서 provider 실응답 검증 전이다.

목업의 ‘다시 확인 (샘플)’은 로컬 상태 전환이다. 네트워크 생성·재시도 기능을 의미하지 않는다. `/home/mock`에 API 요청이 없다는 것을 E2E에서 확인한다. JSON 편집 도구는 raw payload 편집용이며 서버 publication metadata를 수정하지 않는다. 상태별 전체 envelope 예제는 responses.json이다.

## 다음 단계

PRE-02에서 DB coverage와 웹/부상/배당/Vertex 실응답·이용 범위·검색 한도를 조사한다. PRE-03에서 BE spec·실패 테스트·공통 fixture 및 리뷰를 수행한다. Supabase schema/ORM/API/스케줄러/실 메인 연동은 아직 미구현이다. management의 미커밋 인증 기반이나 AX 모델/사전을 가져오지 않는다.


## 검색 보완 계약 추가 (미배포 v1.1)

검색으로 검증한 외부 근거를 게시하는 경우 payload.search_suggestions에 Google 제공 rendered_content와 queries를 함께 저장·반환한다. 검색 결과를 사용하지 못했으면 null이다. FE는 제공 HTML/CSS를 바꾸지 않고 script와 same-origin 권한이 없는 iframe으로 표시한다. 임의 원문 HTML을 넣지 않는다. API 부상/배당이 있으면 그 값을 우선 유지하고 검색이 덮어쓰지 않는다. 검색 후보는 URL/공개 목적지/원문/동일 팀과 날짜/발표 시각/인용 근거를 서버가 확인해야 한다. 미확인 후보는 null 데이터와 unverified 상태다.


## API-Football 자체 전망의 구분

공식 `/predictions` 실응답을 확인했으므로 외부 전망 source.kind는 web 또는 api를 허용한다. API-Football 알고리즘 전망이라는 출처를 명시하며 자체 AI 예측이나 매체 의견으로 바꾸지 않는다. winner/win_or_draw와 원문 advice만 정규화한다. goals.home/away의 -1.5 같은 임계값을 예상 스코어로 해석하지 않는다. 웹 매체 의견은 web 출처로 따로 보존하고 검색이 API 값을 덮어쓰지 않는다.

### 부상 선수 표시명 — 2026-10-25

신규 수집 injuries 행은 API-Football 선수 external_id인 선택 필드 `player_id`를 보존한다. 기존 v1.1 저장본은 이 필드 없이도 유효하다. 공개 조회는 `player.external_id → player_translation.player_id`로 `name_ko`를 일괄 조회해 표시명에 적용하며, NULL/빈 번역이면 원문을 유지한다. ID가 있는 행은 이름 추정으로 연결하지 않는다. ID 없는 과거 저장본은 DB player.name과 정확히 일치하는 선수가 전역에서 한 명일 때만 번역을 적용하며 약칭/동명이인은 원문을 유지한다. 저장 원본 JSON/근거·생성 시각을 변경하거나 AI를 다시 호출하지 않는다.

### 주요 결장자 선택 계약 — 2026-10-25

v1.1은 과거 저장본 호환을 위해 선택 필드를 확장한다. injuries 행의 importance_evidence는 DB 근거 source_ids, 최근 표본 수/선발·출전 시간(NULL 허용), 명시된 시즌별 appearances/minutes, 서버 eligible 및 selection_reason을 담는다. analysis.key_absences는 기존 analysis 호출이 작성하는 선택 section으로, data는 team_id/player_id/reason/evidence_ids 배열이다. 팀당 2명·전체 4명, 후보 소속/적격/중복/상태 충돌/부상과 DB 출전 근거를 검증한다. 새 입력의 reason은 서버 selection_reason과 같아야 한다. 기존 데이터는 필드 없이 유효하며 기본 목록은 접힌 전체 명단으로 보여준다. AI는 선별과 순위만 판단하고 수치 설명은 DB 문장을 유지한다.

외부 predictions에는 API 자체 알고리즘과 독립 매체의 검증된 원문 의견을 함께 저장할 수 있다. API 값이 있어도 검색을 생략하지 않는다. 배당 home/draw/away 의미는 유지하며 화면 라벨은 해당 fixture의 팀 이름으로 표시한다. 공개 조회에서 검색/생성하지 않는다.

### 주요 선수·사진·기록 계약 확장

선택 facts.player_spotlights는 팀/선수 ID, 한글 표시명·원문 이름, photo_url, 해당 시즌 출전/득점/도움/시간(nullable), 최근 표본 수·연속 기록 카운트와 서버 record_notes, DB source_ids를 담는다. analysis.player_watchpoints는 team_id/player_id/focus/evidence_ids를 선택하고 새 모델 응답은 선수별 선정 이유 reason을 필수로 작성한다. 기존 저장본의 공개 계약에서는 reason을 선택 필드로 허용한다. 검증된 후보/팀·중복·팀당 2명/합계 4명·존재하는 기록 focus·DB 근거를 검증한다. injuries와 spotlight 행의 선택 photo_url은 HTTP(S) URL 또는 null이다. 중요도 후보의 recognition_name은 DB 선수 이름이며 인지도 우선순위 판단용이다. 사진/번역은 조회 시 ID로 적용하고 원본 저장본을 변경하지 않는다. 상세는 home-preview-players.md를 따른다.

LLM reason은 현재 기록에 대한 해석이며 기록 자체는 DB record_notes다. 카드 상세에서 ‘왜 눈여겨볼까요?’와 ‘확인된 기록’을 분리한다. reason이 없는 과거 저장본은 ‘선정 근거’와 저장된 기록만 제공하고 LLM 설명을 임의 생성하지 않는다. 새 provider 응답은 빈/누락 reason을 거절한다.

복합 이유 확장: reason은 새 모델에서 3~5문장·최대 1,000자이며 최소 두 개의 확인된 기록 축을 연결한다. facts.player_spotlights의 선택 recent_form은 팀 경기 수·확인 출전 수와 goals/assists/minutes의 값 및 각 sample 수를 구분한다. record_notes.recent_contribution과 focus recent_contribution은 최근 기록을 보여준다. 각 sample은 확인 출전 수 이하이며 sample=0일 때만 값이 null이다. 세부는 home-preview-players.md의 최신 절을 따른다.
