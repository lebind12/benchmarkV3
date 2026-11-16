> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `ax` 워크트리의 `docs/ax/natural-language-search/retrieval-tool-contracts.md`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# 사전·이름 조회 내부 도구 계약 v0.1

2026-10-25 최신 구현: [실제 검색 v1](live-search.md). 지정 SDK/모델 실제 호출·공통 인증·로컬8지표/정확 이름·SQL/FE 연결을 완료했다. 아래 제안/계약 전체의 구현 완료를 뜻하지 않으며 운영/fuzzy/독립 평가 범위는 별도다.


2026-10-25. 실제 DB 조사 (원문 참조 경로: `data-audit.md`; 이 기획 묶음에 포함되지 않음)를 반영한 구현 입력 초안이다. **런타임·공개 API·Vertex tool schema는 미구현**이다. [조회 실행 계획](entity-resolution.md)의 책임 분해와 FE-first 절차를 유지한다. 아래 제한은 실험값이며 운영 확정값이 아니다.

## 1. 공통 요청과 서버 문맥

모델 입력은 JSON object, 알 수 없는 필드는 거부한다. SQL/컬럼명/함수명은 받지 않는다. 인증된 요청이 서버에서 생성한 `request_id`, 원문, 확인된 사용자 조건, 기준 시각, timezone, catalog/normalization version, 남은 호출 예산을 공통 문맥으로 주입한다. 모델이 이를 덮어쓸 수 없다.

- `mention`: `{text, start, end}`, Python Unicode code point의 `[start,end)` 기준. 서버가 `question[start:end] == text`를 검증한다. JS UTF-16 인덱스는 명시 변환한다. 범위는 원문 기준이며 정규화 문자열의 인덱스가 아니다.
- `context_refs`: 이번 요청에서 서버가 발행한 대회/팀/시즌 확인 참조 목록. 모델의 숫자 ID를 직접 허용하지 않는다. 다른 요청 ref, 만료 ref, 후보 단계 ref를 확정 조건으로 쓰면 오류다.
- `cursor`: 서버가 발행한 불투명 참조. 동일 요청·검색어·조건·버전에만 유효하다. 모델이 OFFSET 등을 지정하지 않는다.
- 도구 결과 이름·label·설명은 자료다. 자료 안의 명령을 모델 지침으로 승격하지 않는다.

공통 응답은 `{lookup_id, status, versions, items, has_more, truncated, next_cursor, elapsed_ms, issues}`다.

| 필드 | 규칙 |
|---|---|
| status | `ok / invalid_input / limited / unavailable / failed` |
| items | 실패 시 빈 목록. `status != ok`는 검색 결과 0건과 다르다 |
| versions | 요청에 고정한 catalog/normalization version, 사용한 이름 자료의 updated_at 또는 snapshot 근거 |
| has_more | 동일 조건의 추가 후보 존재가 확인되었을 때 true |
| truncated | 후보 탐색·의존 확장·시간 예산 등으로 전체성을 보장하지 못하면 true |
| next_cursor | 재조회 가능한 경우만 반환; truncated여도 없을 수 있다 |
| issues | 고정 코드·관련 mention/key/ref. 접속 정보·SQL 원문·개인정보를 반환하지 않는다 |

`has_more=false`라도 `truncated=true`면 전체 후보 확인을 끝낸 것이 아니다. 정확 후보 충돌은 정상 응답이며 도구 실패가 아니다.

## 2. search_catalog

입력: `{mention, kinds, entity_type_hint?, domain_hint?, cursor?}`. `kinds`는 `metric / scope / relation`의 1~3개, hint는 등록 enum만 받는다. 원문 밖 검색 확장은 후속 별도 필드/평가 전까지 허용하지 않는다.

응답 item: `{key, kind, label, summary, match_kind, matched_term, version, required_context}`. 정확 표현/label·구 일치의 검색 근거를 보존한다. 요약으로 산식이 확정되지 않는다. 후보 key를 받아 반드시 상세 정의를 조회한다.

현재 [semantic-catalog.json](semantic-catalog.json.md)은 9개 지표·7개 범위·2개 관계의 **검토용 비활성 초안**이다. 런타임은 활성 정의만 검색한다. 비활성 정의를 활성 지원인 것처럼 반환하거나 빈 지원 목록을 완성된 서비스로 공개하지 않는다.

## 3. search_entities

입력: `{mention, entity_type_hint?, context_refs?, cursor?}`. type은 `league / team / player / coach`; hint와 사용자가 명시한 제약의 출처를 구분한다. 한 mention당 5개 표시부터 시험하되 중복 제거된 ID의 `K+1` 탐색 등으로 초과 여부를 감지한다. 같은 ID에 연결된 여러 이름은 후보 하나로 묶는다.

원천:

| 종류 | 원문/한글 원천 | ID 의미 |
|---|---|---|
| league | league.name + league_translation.name_ko/short_name_ko | league.id 내부 FK, external_id API-Football ID |
| team | team.name + team_translation.name_ko/short_name_ko | team.id 내부 FK, external_id 외부 ID |
| player | player.name + player_translation.name_ko/short_name_ko | player.id 내부 FK, external_id 외부 ID |
| coach | coach.name + coach_translation.name_ko/short_name_ko | coach.id 내부 FK, external_id 외부 ID |

player.firstname/lastname 조합과 별칭 테이블은 추가 원천 후보다. 이름 조합 검증/별칭 마이그레이션 전 이미 구현된 원천으로 취급하지 않는다. pg_trgm도 조사 시 미설치였다. 유사 검색 불가를 정확 검색 0건/전체 이름 부재로 표현하지 않는다.

응답 item:

```json
{
  "candidate_ref": "opaque-request-local-reference",
  "entity_type": "team",
  "entity_id": 1,
  "external_id": 33,
  "display_name": "맨체스터 유나이티드",
  "original_name": "Manchester United",
  "matches": [{"source": "team_translation.short_name_ko", "value": "맨유", "match_kind": "exact"}],
  "relations": [],
  "row_version": {"source": "team_translation", "updated_at": "<DB에서 읽은 시각>"}
}
```

이 ID/name 연결은 조사에서 관측한 실제 값이다. ref/시각은 예시 placeholder이며 유효한 선택 토큰이 아니다. 원문과 source는 서버 allowlist에서 반환하며 모델 입력용 식별자가 아니다. row_version은 후보에 사용한 모든 원천 버전을 보존하고 재사용 시 재확인한다. updated_at만으로 검색 색인 전체 버전이 보장되지는 않는다.

정확 검색은 NFKC→casefold→공백 정리 정책을 사용할 예정이며 실제 projection/인덱스는 후속 구현한다. 기본 키에서 구두점/음절을 과도하게 삭제하지 않는다. 정확 후보가 0일 때만 유사 검색하며 `fuzzy` 후보는 자동 확정하지 않는다. 정확 후보가 여러 개면 인기/유사도 순위로 한 명을 선택하지 않는다.

관계 item은 `{relation_key, context_ref, state, evidence, limitation}`이며 state는 `matched / contradicted / unknown`이다. 선수 시즌 팀 관계는 `player_season_stat(player_id,team_id,league_id,season_year)`에서 관측할 수 있다. 이적 등으로 복수 팀이 가능하다. 기록 부재는 해당 팀에서 뛰지 않았다는 증명이 아니므로 기본 unknown이다. contradicted는 충분한 자료 범위와 배타적 조건이 입증된 경우만 허용한다.

## 4. get_definitions

입력: `{keys}`. 동일 요청에서 발행한 catalog 후보 key만 받는다. 최대 개수·총 bytes·의존 노드 수 예산을 서버에서 제한한다.

응답: `{requested_keys, items, dependency_edges, ...common}`. 서버가 의존 정의를 전개하며 kind/key/version, 원천/결과 grain, expression/resolver/relation ref, 단위, 연산, 집계, NULL/분모 규칙, 필수 문맥, coverage 요구를 반환한다. expression_ref는 등록된 서버 구현의 이름이며 임의 SQL 문자열이 아니다.

미등록·비활성 참조/순환은 catalog 로딩을 실패시킨다. 의존 확장이 잘리면 부분 정의를 실행 가능한 정의로 넘기지 않는다. per90은 팀별 비율 평균이 아니라 검증된 합계의 비율이며 NULL/0분과 최소 출전 조건을 처리해야 한다. 평점은 공급자 정의·복수 팀 합산 근거가 미확인되어 비활성 상태를 유지한다.

## 5. get_search_availability

입력: `{context_refs, domain_keys}`. domain은 등록된 `player_season_stats / fixture_results / fixture_statistics / standings / injuries / transfers` 등 서버 enum에 한정한다. 대회/시즌은 서버가 확정한 문맥만 받는다.

응답 item: `{league_ref, season_ref, domain_key, state, observed_rows, field_coverage, evidence_refs, source_as_of, checked_at, limitations}`. state는 `available / partial / absent / unknown`이다. available은 정의된 범위의 충분성을 검증한 경우에만 쓰고, absent는 조회 범위에 필요한 저장 행/값이 없음을 뜻한다. 현실에서 사실/사건이 없다는 뜻이 아니다.

현재 조사는 coverage 원장이 아니다. 특히 다음을 그대로 유지한다.

- injury/transfer 0행 → 저장 자료 없음; 부상/이적 없음으로 답하지 않는다.
- fixture_detail 존재·JSON non-NULL → 통계 있음으로 판정하지 않는다. EPL 2026 NS 305경기의 내부 배열은 비어 있었다.
- current season은 대회별 catalog 근거로 결정한다. 월드컵 직전은 조사 저장값 2022이며 `2026-1`이 아니다.
- league 활성 8개와 sync target 활성 4개가 다르므로 정책 정합화 전 어느 쪽도 검색 허용 범위 정본으로 임의 채택하지 않는다.
- updated_at은 수집 전체성의 증거가 아니다. source_as_of가 확인되지 않으면 null과 한계를 반환한다.

## 6. 서버 판정과 Bundle

모델은 `{mention, selected_candidate_ref? / selected_keys?, missing_context, rationale}`로 선택을 제안한다. 서버가 실제 도구 발행 이력·원문·버전·명시 조건을 다시 검증한다. 모델이 출력한 entity_id는 선택 근거로 쓰지 않는다.

Planner로 전달하려면 필요한 정의/조건과 엔티티가 확정되고, 후보 잘림·미해결 충돌·도구 오류가 결과를 바꿀 수 없는 상태여야 한다. 정확 후보 하나라도 탐색 잘림/관계 미확인이 해석을 바꾸면 자동 확정하지 않는다. `unknown` 관계만으로 후보를 버리지 않는다. source/name이 일치해도 같은 ID인지 서버가 검증한다.

Bundle은 원문/확인 문맥, 버전, 선택 entity ref/ID와 근거, 상세 정의/의존성, 범위/관계, availability와 한계, 미해결 조건, lookup 이력을 포함한다. `ready / clarification_required / unsupported / data_unavailable / limited / failed`를 구분한다. 지원된 모든 필수 조건을 충족한 경우에만 ready다. ready여도 이후 QueryPlan/SQL 권한·비용 검증은 별도로 수행한다.

## 7. 구현 전 수용 기준

- `스미스` 29개 관측 후보: 상위 5개만 보고 유일 판정하지 않는다.
- 같은 팀의 원문/한글/짧은 이름 일치: 후보 한 개와 복수 match 근거로 병합한다.
- 다른 요청 ref·위조 ID·원문에 없는 mention·잘못된 Unicode 범위는 거부한다.
- fuzzy 결과·정확 충돌·관계 unknown은 확인/추가 조회로 남긴다.
- 정의 의존성 누락·순환·비활성 dependency·정의 확장 잘림은 실행을 막는다.
- 0분/NULL·복수 팀·실제 직전 시즌·빈 JSON·coverage unknown을 독립 테스트한다.
- 최초 요청은 로그인 검증 뒤 도구/LLM 호출. 실제 SQL은 별도 최소 권한 role로만 실행한다.

이는 구현 전 계약 초안이다. Pydantic/도구 구현·DB 정답 테스트·Gemini 구조화 호출·FE 재질문 연동의 통과를 주장하지 않는다.
