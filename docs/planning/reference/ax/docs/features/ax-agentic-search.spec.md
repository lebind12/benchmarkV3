> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `ax` 워크트리의 `docs/features/ax-agentic-search.spec.md`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

---
feature_id: ax-agentic-search
artifact: spec
version: 2026-10-29
status: planning-reference
reviewer: fe-reviewer
reviewer_agent_id: /root/planning_review
---

# 축구 기록 대화 검색 — 정제 명세

입력 정본: [요구사항](ax-agentic-search.md). 도메인: [AGENTS](../../../main/domain-policy.md). 이 명세는 현재 시점의 재검토이며 기존 구현/테스트의 승인·머지·운영 완료를 소급하지 않는다. [진행 표시 명세](ax-agentic-progress.spec.md)는 이 기능의 하위 패널 계약이다.

## 1. 요구사항과 출시 범위

| ID | 요구·관측 가능한 합격 조건 |
|---|---|
| AS-01 | 서비스의 canonical 진입은 `/search`. 운영에서 이 경로가 실제 agentic 화면을 표시하고 DEV 플래그가 없어도 사용할 수 있다. 서비스 구성이 없으면 준비되지 않음 안내를 하고 목업 결과로 fallback하지 않는다. |
| AS-02 | 활성 USER/STREAMER/ADMIN만 검색. 비로그인은 입력을 보존한 로그인 동선으로 안내하고 서버 인증 전 LLM/축구 조회는 0회. 비활성/허용 밖 role은 403, 인증 서비스 장애는 안전한 실패다. |
| AS-03 | 검색창은 한 줄부터 최대 7줄까지 확장·축소한다. 빈/공백/500자 초과 제출을 막고, Enter 제출·Shift+Enter 줄바꿈·IME composition 보호·중복 제출 방지·처리 후 포커스 복귀를 제공한다. 서버도 입력을 검증한다. |
| AS-04 | 8지표(득점/도움/출전 분/출전 횟수/경고/퇴장/공격포인트/90분당 득점)의 목록·순위·다중 선수·두 시즌 차이/비율과 조건 조합을 지원한다. 2명 고정 의미 제약 없음. 자원 제한은 범위/이유/잘림을 표시한다. |
| AS-05 | 대회별 활성 상태·현재/실제 직전 시즌을 서버가 확인한다. 이름/별칭은 실제 ID로 연결하며 동명이인·모호한 기간/지표·per90 최소 출전 분은 확인한다. 단순 연도-1이나 임의 종합 점수로 대체하지 않는다. |
| AS-06 | 같은 선수의 복수 소속 행은 지표 정의대로 집계하고 ID로 결합한다. NULL·미수집·0·분모0·동률·결과 잘림을 구별한다. 전체 자료가 없으면 전수 순위/전체 최고를 주장하지 않는다. |
| AS-07 | 질문·답변·표·실제 적용 조건·정의/단위·자료 기준 시각·관측 범위/누락·잘림을 구조화 응답에서 표시한다. 숫자를 설명문에서 추출하거나 예시값으로 보충하지 않는다. |
| AS-08 | 후속 질문은 해당 대화의 검증된 조건/이전 결과 ID만 참조한다. 새 대화·다른 사용자·만료/버전 변경 문맥과 섞이지 않는다. |
| AS-09 | 취소·중복 요청·응답 유실·충돌·실패를 구별한다. 취소된 늦은 응답을 추가하지 않고, 응답 유실만 같은 request_ref로 복구한다. 새 실행은 새 ref를 사용한다. |
| AS-10 | 공통 인증을 재사용한다. 로그아웃/재시작/30분 만료/12턴 제한/토큰 rotation 시 입력과 안전한 표시 이력을 보존하고 재로그인·새 대화 안내를 한다. 메모리 대화 영속성을 보장하지 않는다. |
| AS-11 | DB-only·6시간·전용 reader·실행 제한을 유지하고 운영 갱신 실패를 숨기지 않는다. 오래된 자료는 조회 차단과 갱신 안내로 처리한다. 데이터 polling 없음. |
| AS-12 | 사용자/대화/DB 이름·별칭·조회 결과의 직접·간접 프롬프트 인젝션이 서버 role/scope/tool/ref/SQL·근거·예산을 바꾸지 못한다. 내부 SQL·비밀·프롬프트·타 사용자 문맥 유출과 근거 위조를 차단한다. 정상 인용·특이한 이름을 키워드로 일괄 거절하지 않는다. |
| AS-13 | 모바일·라이트/다크·키보드·스크린리더·reduced-motion을 지원한다. 표는 내부 가로 스크롤, 페이지 폭 넘침 없음. 상태는 색만으로 구별하지 않는다. |

최초 지원에서 제외: 팀 자체/경기 통계, 평점, 국적/포지션 조건, 연봉/비용, 실시간, 외부 웹 통계 보충. 팀 이름은 선수 소속 조건으로 지원한다. 등록된 활성 대회를 초기 5개 상수로 제한하지 않는다. 미지원 표현이 섞인 질문은 제공 가능한 부분과 누락을 명시하거나 확인한다.

## 2. 화면/상태 계약

`/search`는 AgenticSearchView를 canonical로 사용한다. `/search/agentic`, `/search/live`는 DEV 회귀 경로로 유지하고 운영에서는 `/search`로 replace redirect한다. `/search/names`는 운영 404이며 `preview=1`은 운영에서 목업 모드를 켜지 못한다. 이 routing 변경은 요구사항의 canonical 결정 범위 안이다.

| 상태 | 화면과 다음 동작 |
|---|---|
| 초기/인증 복원 | 입력은 유지하고 복원 중 중복 제출 차단. 사용 가능 여부가 결정된 뒤 정상 제출. |
| 비로그인 제출 | 공통 로그인 dialog/route로 안내, 질문 보존. 로그인 성공 후 명시적으로 큐에 둔 첫 제출 1회만 실행. 취소/실패는 입력 보존. |
| 실행 중 | 현재 질문을 pending으로 표시, 입력/기존 답변 보존, 제출 중복 차단·취소 제공. 실제 단계는 progress feature가 표시. |
| results | 실제 답변/표·조건·단위·기준 시각·coverage 표시, 후속 질문 가능. |
| partial | 확인된 자료만 표/답변, 누락 항목·이유·잘림 범위 표시. NULL은 '자료 없음', 0은 숫자 0. |
| clarification_required | 확인 질문과 이유, 자연어 응답 입력. 초기 agentic 계약은 options=[]이며 미지원 choice_ref를 전송하지 않는다. 이전 질문과 표 유지. |
| no_matches | 관측 범위에서 조건에 맞는 기록 0건임을 표시. 미수집이나 NULL과 구별. |
| data_unavailable / unsupported | 각각 자료 없음/미지원 이유를 표시. 가짜 빈 표나 수치 없음. 입력 수정·새 질문 가능. |
| 오류/연결 유실 | 기존 대화/입력 보존. 오류의 안전한 설명·복구 동작 제공. 유실은 동일 ref 복구, 409 문맥 만료는 새 대화. |
| 취소 | 즉시 UI에서 늦은 결과 수용 중지. 서버 cancel 완료/실패를 구별. DB/모델 호출이 이미 진행 중이면 즉시 중단을 보장하지 않으며 그 한계를 안내. |

30분·12턴은 현행 로컬 계약이며 운영 한도는 측정/리뷰 후 확정한다. 변경 시 문서·서버·Zod·테스트를 함께 갱신한다. 토큰 rotation으로 session binding이 바뀌면 기존 conversation/parent/request ref를 새 세션에 자동 재전송하지 않는다. 기존 표는 읽기 전용 이력으로 보존하고 새 대화를 안내한다. 재로그인 후 새로운 nonce로 실행하려면 사용자가 새 질문/새 대화를 선택해야 한다. 공통 인증과 안정적 세션 binding을 도입해 이어받는 경우는 BE 독립 검토 후 계약을 갱신한다.

## 3. 화면에서 도출한 데이터/API 요구

FE 수요로부터 도출한 계약 초안이다. [기존 API 문서](../spec/endpoints/ax-agentic-search.md)는 현재 구현 근거이며 endpoint-request/BE spec review를 통해 아래 보완을 확정해야 한다.

- 공통 auth login/refresh/logout/me: 기존 실제 사용자 세션을 사용한다. AX 테스트 코드/별도 role 저장을 운영 fallback으로 사용하지 않는다.
- POST `/api/v1/search/agentic/conversation`: `{request_ref: string(16..64), message: string(1..500), conversation_ref?: string, parent_turn_ref?: string}`. continuation은 두 ref를 함께 보낸다. SQL·ID·scope·역할 지시를 권한 필드로 받지 않는다.
- POST `/api/v1/search/agentic/conversation/stream`: 같은 입력·인증, 최종 result는 단일 응답과 같은 스키마. progress 명세 참조.
- POST `/api/v1/search/agentic/conversation/cancel`: `{request_ref}`, 검증된 응답 `{status:'cancelled'}`. 요청 사용자에 한정한다.
- 최종 응답: `{conversation_ref, expires_in, turn}`. turn에는 `turn_ref, question, answer, status, tables[], steps[], missing[], sources[], clarification?, progress_steps?`가 있다. 공개 scalar는 finite number|string|null. Pydantic·Zod 경계/개수/byte 제한을 동일하게 확정한다.
- tables는 `{artifact_ref,title,columns:[{key,label,unit?}],rows:[record]}`. row에 없는 셀을 0으로 만들지 않는다. 컬럼/row key 일관성·실제 ref·순서·숫자 출처는 서버 검증 대상이다.
- **보완 필요:** results/partial/no_matches에는 설명문과 별도로 `applied`를 제공한다. 최소 `scopes[]`(실제 대회 식별/표시명·시즌·소속 조건), `metrics[]`(key/표시명/단위/정의), `filters[]`(지표/연산/값), `minimum_minutes`, `sort[]`, `selection`(선수 선택 기준·반환 상한/잘림)을 구조화한다. 복수 조회의 조건은 artifact_ref와 연결한다. 현재 agentic 응답에는 이 계약 전체가 없으므로 구현 완료가 아니다.
- **보완 필요:** sources/각 artifact에 `coverage`(관측/부분/미수집·관측 행/알려진 지표·제외된 NULL·잘림), `exported_at`과 실제 `source_as_of` 및 자료 버전을 연결한다. 설명문 날짜 파싱/클라이언트 now로 대체하지 않는다. unknown 상태를 complete로 승격하지 않는다.

오류는 HTTP 401 인증, 403 role/활성, 409 문맥/parent/nonce 충돌·취소, 422 입력/계획/근거, 429 제한/provider, 502 모델/응답, 503 인증/DB/자료/구성, 504 deadline을 구별한다. 스트림 개시 후 오류는 progress 명세의 error event다. 내부 exception/provider 원문 대신 검토된 code만 사용자 문구로 매핑한다. unknown code는 안전한 일반 오류로 표시한다. 인증 오류를 무조건 비밀번호 오류로 오인시키지 않는다.

## 4. 보안과 검증 경계

FE는 모든 텍스트를 Vue escaping으로 출력하며 v-html/외부 링크/HTML 실행으로 해석하지 않는다. 모델/DB 유래 지시는 사용자·시스템 role로 승격하지 않는다. API 클라이언트는 응답/Zod와 크기 제한을 통과한 구조만 렌더링한다. 서버의 인증·실제 ref/scope·SQL 게이트·계산·근거/출력 검사·실행 예산이 권한 경계이며 FE 숨김과 프롬프트 문구는 방어의 대체가 아니다.

AS-12는 직접 role 위장/인코딩된 지시, 이전 대화의 권한 변경 요구, 악성 DB 이름/별칭/결과, 위조 artifact/타 사용자 ref, 위험 SQL 제안, 시스템/비밀 canary 유출, 가짜 숫자/출처, 무한 도구 반복과 정상 인용/이름을 포함한다. L1 서버 강제 검사와 실제 모델 holdout을 구분하고 API/SSE/답변/로그에서 유출·부작용 부재를 확인한다. 실제 비밀 대신 합성 canary를 사용한다.

### 보안 인수 연결

[보안 인수 정본](../ax/natural-language-search/prompt-injection-security.md)의 SEC-01(생성 SQL의 지표/이름/ID·집계 source lineage 위조 차단), SEC-02(자유 설명·확인 질문·미지원 reason의 근거 없는 claim 검증)는 출시 차단 조건이다. 안전한 SELECT/발급된 셀 ref라는 사실만으로 통계 의미가 검증됐다고 보지 않는다. 임의 숫자 차단이나 ASCII 숫자 검사만으로 자연어 이름·한글 수사·가짜 출처·인과를 검증하지 않는다. 서버가 검증할 수 없는 표현은 공개 fact로 승격하지 않고 독립 실제 모델 의미 평가를 함께 수행한다.

## 5. 승인/완료 경계

[테스트 플랜](ax-agentic-search.testplan.md)의 요구별 증거와 독립 FE/BE 리뷰를 연결한다. 기존 결정론적 UI provider는 화면/SQL 연결 증거이며 Gemini 의미 정확도 증거가 아니다. L3-local은 보조 증거다. preview+실서비스 BE L3, 실제 계정/모델·reader·운영 갱신, 독립 정답/holdout·지연/비용·보안 기준선, 변경 커버리지와 CI, 승인된 머지/배포 후 L4가 완료돼야 서비스 DONE이다. 배포 요청 전에는 deployment/환경변수 변경/재시작/자동 배포 유발 머지를 실행하지 않는다.
