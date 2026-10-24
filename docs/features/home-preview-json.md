# 메인 프리뷰: DB·웹 근거 분리와 JSON 계약

2026-10-25 사용자 요청. 메인 목업의 하드코딩 본문을 JSON 기반 렌더링으로 전환하고 후속 생성/조회 계약을 작성했다. **이번 완료 범위는 FE 목업·JSON 샘플·스키마·검증·BE 요구 정리다. 실제 생성 API의 Markdown 출력을 변경하거나 DB 저장/수집을 구현한 것은 아니다.**

## 역할 분담

| 항목 | 기준 경로 | 보완/누락 처리 |
|---|---|---|
| 경기 ID·팀·번역명·엠블럼·대회·라운드·킥오프·장소 | DB | ID를 외부 경기 ID로 통일. AI가 이름/경기/일정을 재작성하지 않음 |
| 양 팀 최근 완료 5경기·결과·득실 | DB | 기존 team-recent API/서비스 재사용. 현재 경기 제외, 킥오프 이전 완료 경기, 실제 표본 수 보존. 부족한 결과를 웹 추측으로 채우지 않음 |
| 순위·시즌 지표·H2H·선수 기록 | DB | 현재 보유/coverage 확인. 과거 프리뷰라면 당시 snapshot이 없을 때 최신 누적값을 과거 근거로 사용하지 않음. 현재 목업 계약의 필수 화면 항목은 아님 |
| 부상·징계·출전 변수 | 저장된 injury/공식 자료 우선 + 웹 보완 | 기존 daily-sync의 실제 injury 적재/신선도는 미확인. 공식 발표·신뢰 가능한 보도에 근거, 확정/불확실·게시/확인 시각 보존. 목록이 없음을 결장자 0명으로 처리하지 않음 |
| 감독 발언·전술 맥락·팀 뉴스·예상 라인업 | 웹 검색 | 공식 인터뷰/발표·최근 보도. 예상 라인업과 확정 라인업 구별. 근거 없는 전술·심리 단정 금지 |
| 외부 사이트별 예상 결과 | 웹 검색 | 정확히 같은 경기의 원문 전망, 사이트/원문 URL/게시·확인 시각. 일반 기사·AI 예측을 외부 전망으로 바꾸지 않음 |
| 경기 전 배당 | 수집 경로의 구조화 API 원본 → DB 우선 | 북메이커·90분 승무패·decimal·수집 시각이 검증되는 원본만 사용. 웹은 같은 조건을 직접 확인할 수 있을 때 보완. 실응답/coverage 확인 전 특정 API 지원을 구현 완료로 취급하지 않음 |
| 한줄 전망·관전 포인트·AI 예상 결과·그 이유 | 위 근거를 입력받는 AI | AI 전용 analysis JSON만 생성. DB 기록/부상 사실/외부 전망/배당은 서버가 원본에서 합침. AI가 전체 사실 데이터를 재생성하지 않음 |

웹 검색은 수집·생성 경로에서 수행한다. 일반 사용자의 메인 진입/화살표 조작은 저장된 JSON을 DB에서 조회한다. 기존 일반 페이지 6시간 정책을 유지하며 새 상시 워커/주기는 이번에 확정하지 않는다.

## 생성 파이프라인

```text
추천 fixture 선택
  → DB 사실 snapshot 조립
  → 부족한 웹 근거 수집 + 원문/grounding metadata 보존
  → 출처 registry·fixture·게시/확인 시각·시장·coverage 검증
  → 검증된 근거만 AI에 전달
  → responseMimeType + responseSchema로 analysis JSON 생성
  → JSON 파싱 + strict schema + source ID/시점 검증
  → 서버가 사실/외부 원본과 analysis를 최종 JSON으로 합침
  → fixture + 입력 fingerprint + 생성 버전으로 DB 저장
  → 공개 GET으로 저장본 조회 → 메인 렌더링
```

검색과 최종 생성을 기본적으로 두 단계로 분리한다. 모델·플랫폼에 따라 검색 도구와 structured output 동시 지원이 달라질 수 있으므로 실제 Vertex 모델/계약 검증 없이 같은 요청에서 항상 가능하다고 가정하지 않는다. 두 단계 모두 횟수·시간·비용·중복 실행 제한을 두며 실패 시 기존 유효본을 보존한다. 현재 기존 코드는 Gemini + Google Search의 Markdown 생성 경로이고 이를 공개 GET에 직접 연결하지 않는다.

## JSON 계약과 파일

- 최종 응답 샘플: `frontend/src/mocks/home-preview/previews.json`. 키는 fixture ID이며 각 값이 독립된 최종 JSON이다. 일정·사실·분석·출처는 모두 목업용 가상 데이터다.
- 최종 응답 런타임 검증: `frontend/src/lib/api/homePreviewSchema.ts`의 `homePreviewSchema`.
- AI 출력 전용 strict JSON Schema: `docs/spec/schemas/home-preview-analysis.schema.json`.
- Vertex의 responseSchema 지원 형식: `docs/spec/schemas/home-preview-analysis.vertex.schema.json`.
- 실제 호출 전 검토할 요청 예제: `docs/spec/schemas/home-preview-generation.request.example.json`. 검색 tools 없이 검증된 입력을 주입하는 예제이며 실행하지 않았다.
- FE endpoint 요청: `frontend/endpoint-requests/GET__api_v1_home_fixtures_external_id_prematch.request.json`.

최종 JSON의 최상위 키:

| 키 | 책임 |
|---|---|
| schema_version / is_mock | 버전과 목업 여부. 운영 서버는 is_mock=false만 공개하며 클라이언트 입력으로 운영 모드를 선택하지 않음 |
| fixture | 서버의 정확한 경기 identity·양 팀·킥오프 |
| generated_at / as_of | 생성 시각과 입력 snapshot 시각. 자료 시각이 생성보다 뒤일 수 없음 |
| sources[] | fixture별 고유 ID, db/web/api 종류, 제목, 원문 URL, 게시/확인 시각. 실제 외부 근거에는 HTTP URL 필요 |
| facts | injuries, home_form, away_form. 서버가 DB/검증된 근거에서 결정적으로 조립 |
| external | predictions, odds. 사이트 의견과 숫자 원본을 AI 분석과 분리 |
| analysis | summary, key_points, ai_prediction. 입력에 존재하는 evidence_ids만 인용 |

각 영역은 `status / reason / as_of / source_ids / data`를 갖는다.

- `available`: data와 기준 시각·출처 필요. 최근 5경기는 정확히 5개.
- `partial`: 일부 data와 누락 사유 필요. 최근 경기는 실제 1~4개만 사용.
- `missing`: 수집/자료 없음. data=null, reason 필수.
- `unverified`: 자료는 있으나 확인 불가. data=null, reason 필수.
- `error`: 조회/생성 실패. data=null, reason 필수. 내부 provider 오류 문자열은 공개 reason에 포함하지 않음.

확인된 결장자 0명은 `available`, `reason=confirmed_no_absences`, 빈 배열과 실제 출처를 함께 갖는 경우에만 표현한다. 누락과 0을 구분한다. 출처가 없는 정상 0을 만들지 않는다.

예측 confidence는 low/medium/high이며 임의 승리 확률을 뜻하지 않는다. 경기 결과·득실·배당을 예측처럼 합성하지 않는다. JSON의 예상 스코어만 예측이고 사실 기록은 원본 값이다.

## 강제와 검증의 경계

기존 프롬프트의 `Markdown만 반환`을 새 경로에서는 사용하지 않는다. `application/json` MIME과 response schema를 함께 보낸다. Vertex 지원 필드로 표현하기 어려운 additionalProperties·길이·참조/시점 규칙은 서버의 strict Pydantic 검증으로 다시 강제한다. 완성 JSON도 서버에서 검증하고 FE에서 Zod로 검증한다. JSON.parse만 성공했다고 공개하지 않는다.

현재 FE 검증은 알 수 없는 키·필드 누락·다른 경기/팀·알 수 없는 출처·근거 참조·잘못된 표본 수·현재/미래 경기 혼입·잘못된 배당 시장·생성 이후 근거/배당·킥오프 이후 생성 등을 거부한다. 형식과 참조 검증은 사실의 진실성을 증명하지 않는다. 게시 시각·경기 매칭·원문 주장/수치·grounding support의 사실 대조는 후속 수집/BE 단계에서 별도로 구현한다.

검증 실패는 제한된 재시도/복구 대상으로 처리한다. 무제한 JSON 수선·출처 추측·빈 배열 성공 처리·Markdown으로의 조용한 fallback을 하지 않는다. 이전 유효본이 있으면 그 자료/생성 시각을 유지한다.

## 목업에서 확인하는 방법

`/home/mock` → 평가 도구 → `프리뷰 JSON`: 현재 fixture의 전체 JSON을 편집/적용한다. JSON의 분석·예상 스코어·부상·폼·외부 전망·배당 변경이 화면에 반영된다. 부적합한 JSON은 오류를 표시하고 마지막 유효 화면을 유지한다. 기존 항목별 자료 상태 조작도 같은 계약을 거쳐 렌더링한다. 새로고침 시 샘플로 복원된다.

## 후속 BE 단계

1. FE endpoint-request를 기준으로 별도 BE spec·테스트를 작성한다.
2. 기존 DB 조회 재사용과 실제 injury/odds 적재 coverage를 확인한다. API-Football 신규 원본 모델 작성 전에 MCP 실응답 검증이 필요하다.
3. 기존 웹 검색 어댑터에서 본문뿐 아니라 grounding metadata/원문/게시·확인 시각을 보존하고 source registry를 만든다.
4. 새 JSON generation adapter와 Pydantic 검증을 구현한다. 기존 방송 Markdown 응답을 깨뜨리지 않는다.
5. Supabase CLI 저장 마이그레이션과 ORM을 동기화하고 공개 조회는 DB 전용으로 구현한다.
6. FE를 저장본 GET으로 교체하고 fixture 전환/부분 실패/이전본/출처·실제 DB 결과까지 검증한다. 배포는 별도 명시 요청 때만 수행한다.

## 공식 문서 확인

- [Vertex structured output](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/multimodal/control-generated-output): JSON MIME + response schema, 지원 schema subset 및 unsupported field 처리.
- [Gemini structured output](https://ai.google.dev/gemini-api/docs/generate-content/structured-output): 모델/도구 조합에 따른 지원 범위와 JSON Schema. 플랫폼 간 지원을 동일하다고 추정하지 않는다.

## 구현 계획 정본

2026-10-25 후속 사용자 요청으로 상세 실행 계획을 작성했다. **설계/경계/검증은 [plan.md §14](../../plan.md), Task/DoD/Depends/Status는 [Plans.md PRE 표](../../Plans.md)가 정본**이다. 위 후속 BE 단계의 상위 설명을 세분화하며, 구현 완료를 뜻하지 않는다. 첫 작업은 PRE-01의 생성 전·실패·이전본 응답과 추천 endpoint-request 보완이다. 새 웹/AI·DB 저장·공개 GET·실 메인·정기 실행은 아직 미구현이다.
