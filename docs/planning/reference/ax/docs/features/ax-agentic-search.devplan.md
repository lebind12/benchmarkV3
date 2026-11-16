> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `ax` 워크트리의 `docs/features/ax-agentic-search.devplan.md`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

---
feature_id: ax-agentic-search
artifact: devplan
version: 2026-10-29
status: planning-reference
reviewer: fe-reviewer
reviewer_agent_id: /root/planning_review
---

# 축구 기록 대화 검색 — 개발 방향

[spec](ax-agentic-search.spec.md)·[testplan](ax-agentic-search.testplan.md)을 따른다. 이 문서는 구현 계획이며 기존 코드의 승인이 아니다.

## 1. 라우팅과 책임 분해

- router의 `/search`를 실제 AgenticSearchView canonical로 연결한다. DEV alias/v1 회귀는 유지, 운영 alias는 replace redirect·lab404·preview 비활성. 기존 DEV flag로만 실제 검색이 열리는 조건은 보완 대상이다.
- AgenticSearchView: page orchestration·입력/레이아웃. 현재 한 파일의 인증/대화/stream 로직을 필요한 단위로 추출한다.
- SearchComposer: 자동 높이/IME/500자/제출·취소와 접근성. SearchTranscript: question·answer·clarification. SearchResultTable: artifact 표/NULL/단위/overflow. SearchEvidence: 구조화 applied/coverage/시각·누락/잘림. SearchSessionNotice: 만료/재로그인·새 대화. AgenticProgress: 별도 feature 그대로 합성한다.
- `components/ui/button`의 기존 shadcn-vue Button을 합성할 수 있다. 새 UI 패키지를 설치하지 않고 기존 dialog·table의 의미 구조/스타일을 보존한다. 컴포넌트 분해는 테스트·수명주기 경계에 도움이 되는 만큼만 수행한다.

## 2. 인증·store·수명주기

공통 Pinia auth store를 권한 정본으로 재사용한다. 현재 `axSearch.ts`의 별도 searchUser/accessToken과 공통 auth의 차이를 실계정 통합 단계에서 해소한다. 새 장기 토큰 저장소/localStorage JWT·임의 mockRole fallback을 만들지 않는다.

대화 store는 app/page 인스턴스 범위이며 `{turns,conversationRef,parentTurnRef,query,pendingRequest,failedRequest,sessionState,progress}`를 가진다. 요청별 nonce/serial/AbortController와 재시도 payload hash를 보관하고 다음 규칙을 단일 경계에서 강제한다.

- 동일 실패 요청의 유실 복구는 같은 nonce/payload, 새 질문은 새 nonce.
- 취소/새 대화/unmount는 serial을 무효화하고 늦은 결과를 append하지 않는다. 명시 cancel과 disconnect를 구별한다.
- 401/토큰 rotation/로그아웃은 실행 refs를 회수하고 기존 이력은 읽기 전용, 입력 보존·새 대화 안내. 토큰 갱신이 상태 변경 요청을 자동 재실행하지 않는다.
- expiration/자료 버전/parent 충돌은 서버 결정으로 처리하고 로컬 시간이 권한을 연장하지 않는다.
- 모든 listener/timer/observer 해제. MPA 다른 entry에 검색 상태/라이브 polling을 끌어오지 않는다.

## 3. API·MSW·형식 검증

[spec §3](ax-agentic-search.spec.md)의 세 search endpoint와 공통 auth가 후보다. 기존 endpoint를 FE→BE request 파일로 연결한다. API 추가를 백엔드가 선제 추정하지 않는다. applied/coverage/단위/기준 시각 보완은 서버와 먼저 typed 계약을 합의하고 스키마·예제·독립 정답을 동기화한다.

개발 순서: 승인된 FE 계획 → 현재 화면의 gap/목업 보완 → L1/L2·독립 FE 리뷰 → endpoint-request → BE spec/testplan·독립 리뷰 → 서버 보완 → FE 실 API/Zod 전환·L3. 기존 local 서버를 썼다는 이유로 앞 단계 승인/머지를 자동 생성하지 않는다.

L2 MSW handler 목록(신규 필요): auth login/refresh/logout/me, agentic conversation/cancel/stream. fixtures는 public 정상/partial/clarify/no_matches/unavailable/unsupported와 안전한 오류·malformed·oversize·인젝션 텍스트를 포함한다. native browser SSE 대신 기존 fetch POST 스트림을 흉내 내며 nonce/타이밍을 검증한다. preview generator의 직접 호출만으로 L2 MSW gate를 대신하지 않는다. 운영 번들에서는 MSW·preview fixture가 활성화되지 않아야 한다.

모든 HTTP/SSE 최종 응답은 Zod 검증, 오류 code도 검증된 안전 문구로 매핑한다. canary/SQL/키를 브라우저 로그·trace artifact에 남기지 않는다. 보안 fixture는 합성 값만 사용한다. 유효하지 않은 자료는 이전 결과를 보존한 안전한 실패로 표시한다.

## 4. 기존 자산과 보완

| 자산 | 재사용 범위 | 보완 |
|---|---|---|
| AgenticSearchView.vue | 글래스/대화/다중표/취소/preview | canonical 운영 라우팅·공통 auth/store·구조화 applied/coverage·세션 명확화 |
| axSearch.ts | Zod/POST/stream parser·오류 문구 | 공통 세션·일관된 bounds·cancel schema·회전/만료·정상/공격 경계 |
| ax-agentic-search.spec.ts | 결정론적 provider+실HTTP/로컬reader의 3명/두시즌·후속·취소·유실·다크 | L2 MSW 별도·서비스 L3/실모델 oracle·권한/오류/PI·accessibility 확장 |
| v1 conversation tests | 서버 소유권·멱등성 개념 회귀 | 새 구조에서 동일 요구를 별도 검증, v1 통과 수치 전용 금지 |

### 보안 구현 handoff

[보안 인수 정본](../ax/natural-language-search/prompt-injection-security.md)의 SEC-01/02와 PI-01~12를 endpoint-request/BE testplan에 연결한다. FE가 SQL의 안전성·의미 정확성을 재판정하거나 설명문을 사실로 추출하지 않는다. 위조 metric/name/ID가 담긴 artifact, 근거 없는 자유 설명/clarification/unsupported reason은 서버가 차단해야 하며 UI는 안전한 상태만 렌더링한다. schema 검증은 의미 검증의 대체가 아니다.

## 5. 관측·서비스 연결·게이트

사용자에게 현재 작업·조건·한계만 표시한다. 진단은 request/case/version·안전한 code·소요/토큰·차단 단계로 제한하고 질문/후보 원문 무제한 로깅을 피한다. 실비밀 유출 검증은 승인된 수집 지점에서 수행한다.

공통 인증·운영 read role/view·6시간 projection 갱신·동적 대회/시즌·공통 app 등록/가용성·노출 설정·실계정 인수는 root/BE 의존이다. 현재 runtime loader는 local mirror 전용이고 실제 Vertex 전체 인수는 429/504로 보류다. FE가 기본 DB 권한이나 목업으로 우회하지 않는다.

구현·검증 결과와 변경 기록을 현재 시점부터 남긴다. 계획 수립 후에도 구현·백엔드 연동·통합 검증이 남는다. L3-local을 L3_RUN 통과나 DONE으로 표시하지 않는다. 서비스 지연/비용 한도는 첫 기준선 후 별도 승인하며 FE가 임의 확정하지 않는다.
