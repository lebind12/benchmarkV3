> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `ax` 워크트리의 `docs/features/ax-agentic-progress.devplan.md`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

---
feature_id: ax-agentic-progress
artifact: devplan
version: 2026-10-29
status: planning-reference
reviewer: fe-reviewer
reviewer_agent_id: /root/planning_review
---

# 검색 진행 표시 — 개발 방향

[spec](ax-agentic-progress.spec.md)·[testplan](ax-agentic-progress.testplan.md)을 따른다. 기존 패널·SSE를 재사용하고 별도 서버/Redis/polling을 추가하지 않는다.

## 1. 컴포넌트·상태

- AgenticProgress.vue는 표현 전용: steps/state/elapsed/runElapsed props와 cancel action slot. 실제 역할·stage·실패/취소/끊김 label·이력 접기를 합성한다.
- `axSearch.ts` 또는 추출 stream parser: fetch POST/인증·HTTP/SSE 경계, UTF-8/CRLF/frame·Zod·size·sequence 검증, terminal 처리.
- 검색 page/store: active serial/ref/payload, step map/order, current/total clock, final turn append·retry/cancel/session 수명주기를 소유한다. 다른 MPA entry나 전역 싱글턴에 진행 정보를 공유하지 않는다.
- 필요하면 `useAgenticProgress` composable로 시계/step reducer를 분리해 Vitest로 검사한다. 기존 Button을 cancel action에 합성할 수 있으며 새 UI 의존성은 필요 없다.

## 2. reducer·리소스 경계

전송부터 '연결 중', accepted 외 실제 server stage를 받은 뒤 작업 표시. 최신 sequence만 수용, 같은 step id update, terminal step 되돌림 금지. 순서가 동일한 label이어도 다른 step id면 다른 실행 이력이다. malformed·unknown stage·비일관 duration/과대 응답은 안전한 오류로 종료한다. 최종 이력의 source와 live 이력이 상충할 때 맹목 교체하지 않는다.

250ms 등 표시용 clock은 마지막 server timestamp에 기반해 elapsed만 갱신하고 phase를 추정하지 않는다. success/error/abort/unmount/session rotation에서 interval/reader/AbortController를 정리한다. disconnect는 명시 cancel과 다르며 same nonce 최종 결과 복구를 제공한다. 자동 요청 반복이나 같은 nonce의 payload 변경을 하지 않는다.

SSE endpoint는 AS feature와 중복 생성하지 않고 동일 endpoint-request를 의존한다. 신규 endpoint 후보는 없으며 기존 conversation/stream/cancel의 FE 계약을 보강한다. 프롬프트 인젝션/악성 label이 safe text 처리와 서버 권한·출력 검사를 모두 통과해야 한다는 요구를 BE에 전달한다.

## 3. MSW·기존 코드·보완

L2 handlers는 `POST conversation/stream`(정상·반복·오류·유실·malformed·oversize·악성텍스트), `POST conversation/cancel`(정상·401/403·실패), 공통 auth다. fixtures는 sequence/id/duration을 고정하고 fake timers로 clock을 분리한다. MSW를 건너뛰는 preview만으로 L2 gate를 충족하지 않는다.

기존 `ax-agentic-search.spec.ts`의 서버 단계/SQL 오류/유실/모바일 취소와 `test_ax_agentic_progress.py`의 실제 phase 기록/stream auth/최종 replay를 재사용한다. malformed·역순/중복·반복 실패 후 회복·HTML/canary·권한/rotation·시계/reduced-motion은 추가 검증한다. 기존 test provider의 단계 이벤트는 실제 Vertex 안전성 증거가 아니다.

## 4. 관측·handoff·완료

진단은 request/run·stage·sequence·안전한 code·시간/크기로 제한한다. SQL·비밀·내부 prompt/후보·원문 payload가 event/error/log에 들어가지 않도록 서버 출력 계약과 연결한다. 실제 모델 prompt injection은 [보안 계획](../ax/natural-language-search/prompt-injection-security.md)의 독립 suite에서 평가한다.

기획 승인 → FE gap 구현/L1/L2·리뷰 → 기존 search endpoint request 연결/BE 명세 승인·실행 → Zod/실서비스 SSE L3 → 승인된 배포·L4 순서다. 운영 proxy의 buffering/연결 timeout과 세션·ref는 실서비스에서 확인한다. 로컬 HTTP/SSE+PG 성공을 preview/prod L3·DONE으로 승격하지 않는다. root가 명시 배포 승인과 머지 대상을 관리한다.
