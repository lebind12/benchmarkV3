> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `ax` 워크트리의 `docs/features/ax-agentic-progress.spec.md`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

---
feature_id: ax-agentic-progress
artifact: spec
version: 2026-10-29
status: planning-reference
reviewer: fe-reviewer
reviewer_agent_id: /root/planning_review
---

# 검색 진행 표시 — 정제 명세

[요구사항](ax-agentic-progress.md)·[검색 spec](ax-agentic-search.spec.md)에 종속된다. 단독 공개 페이지/권한/데이터 polling을 추가하지 않는다. 현재 SSE 코드가 존재하나 이번 명세 승인과 실제 운영 검증은 별개다.

## 1. 요구 식별과 동작

| ID | 합격 조건 |
|---|---|
| AP-01 | `/search` 대화 내 패널. 전송 시작은 '연결 중'이며 서버 이벤트 전 모델/DB가 동작한다고 표시하지 않는다. |
| AP-02 | 서버 발행 sequence·step id로 실제 시작/완료/실패를 갱신한다. 계획/조회/SQL작성·검증/DB/계산/재계획/답변의 반복을 허용한다. 같은 id를 추가해 이력을 중복하지 않고 역순/중복 sequence를 재적용하지 않는다. |
| AP-03 | 전체/현재 작업 경과를 클라이언트 시계로 표시하되 서버 duration과 구별한다. 퍼센트·가짜 완료시각·순환 가짜 단계 없음. 서버 완료/실패 duration을 최종 이력으로 사용한다. |
| AP-04 | 결과 또는 오류 후 타이머 정리, 기존 대화 유지. 중간 실패 후 재계획 이력을 보존하고 성공 시 이력을 접어 확인할 수 있다. |
| AP-05 | 연결 유실은 실패/취소와 구별, 마지막 단계 보존. 자동 재연결/재실행 없음. 같은 request_ref/payload로 최종 결과 복구, 1개 turn만 표시. |
| AP-06 | 명시 cancel은 UI 늦은 이벤트/결과 수용을 멈추고 서버 cancel을 보낸다. cancel 실패를 완료로 표시하지 않는다. disconnect만으로 서버 중단을 보장하지 않는다. |
| AP-07 | 스트림은 검색과 같은 인증/활성 role·사용자 소유권·멱등성. 인젝션/악성 label/오류로 내부 SQL·프롬프트·비밀·사고전문·타사용자 payload를 전송하거나 HTML로 실행하지 않는다. |
| AP-08 | 모바일/다크/긴 label·키보드·스크린리더·reduced-motion 지원, 취소 button viewport 내. 반복 시계 tick을 매번 스크린리더 알림으로 보내지 않는다. |
| AP-09 | DEV preview에 예시 표시. 운영에서 preview=1/모의 이벤트 비활성. SSE keep-alive는 실행 진척/축구 데이터 갱신으로 보지 않는다. |

## 2. 전송·데이터 계약

POST `/api/v1/search/agentic/conversation/stream`, body·인증은 검색 spec §3과 동일. `text/event-stream`, no-store와 no buffering. 이벤트를 받기 전 인증/입력/role 실패는 일반 HTTP JSON이다. 열린 스트림에서 서버 오류는 검토된 안전 code의 error event다.

| event | 필드·의미 |
|---|---|
| progress | `{sequence: nonnegative integer, step:{id:string(1..64),stage,label:string(<=160),status,started_ms:finite nonnegative number,duration_ms:finite nonnegative number|null}}` |
| result | 검색 spec의 단일 응답과 같은 최종 schema, `turn.progress_steps`에 종료 이력. 최종 응답 1개만 수용. |
| error | `{status:integer(400..599),detail:safe_code}`. SQL/provider 원문·비밀 payload 금지. |
| keep-alive | SSE comment만. phase 변경·모델실행 증거 아님. |

stage는 accepted/planning/review/lookup/scope/sql_generation/validation/database/calculation/answer, status는 running/completed/failed. started_ms는 서버 실행 시작 이후, duration_ms는 해당 단계 소요. 한 id는 동일 작업 identity를 유지하며 종료 뒤 running으로 되돌리지 않는다. 중복/역순은 무시하되 invalid schema/모순/과대 응답은 안전한 연결 오류로 종료한다. label은 신뢰하지 않는 데이터다.

클라이언트는 UTF-8 chunk 분할·CRLF·multiline data·comment를 처리하고 JSON/Zod 확인 후 갱신한다. 기존 구현 상한(총 stream 2MiB, buffer 300,000문자, 최종 progress_steps128)은 현재 로컬값이며 공개 계약은 BE 리뷰 후 동일 단위/byte로 확정한다. 상한 초과·NaN·unknown stage·형식 불일치는 이전 이력을 유지한 안전한 실패다. 최종 응답의 progress_steps와 live 이력이 상충하면 검증 없이 덮어쓰지 않는다.

## 3. UI·복구·보안

연결 중/진행/완료/서버 실패/연결 끊김/취소 요청/취소 확인 실패를 텍스트·아이콘으로 구별한다. 화면의 역할 이름은 내부 prompt/도구 payload를 의미하지 않으며 사용자용 작업 요약만 보인다. cancel 후 서버 DB/모델 호출이 즉시 멈추지 않을 수 있다는 한계를 안내한다.

인증 만료/rotation은 검색 spec의 세션 정책을 적용한다. 타 사용자 ref·오래된 parent/nonce를 stream이 우회하지 못한다. 직접 질문·DB/대화 유래 인젝션에 대해서 progress/error/최종 result/진단 로그까지 합성 canary·내부정보 비노출을 검증한다. Vue 텍스트 escaping, 서버 출력 제한·권한·근거 검사는 서로 대체하지 않는다.

AP-07은 [보안 정본](../ax/natural-language-search/prompt-injection-security.md)의 PI-07/09/11/12 및 SEC-01/02에 연결한다. progress가 성공했다고 표시하더라도 위조 SQL 통계나 근거 없는 자유 설명이 검증된 것은 아니다. 검색의 의미·보안 차단 결과는 최종 result와 별개 검증하며 오류/label 유출도 검사한다.

## 4. 완료 기준

[테스트 플랜](ax-agentic-progress.testplan.md) AP-T01~13의 요구/레이어/근거를 연결한다. 실제 이벤트 기반 UI 통과는 모델의 통계 정답·자연어 안전성을 승인하지 않는다. L3-local은 보조 증거, 정식 L3/독립 리뷰/승인된 배포와 L4 전에는 DONE이 아니다.
