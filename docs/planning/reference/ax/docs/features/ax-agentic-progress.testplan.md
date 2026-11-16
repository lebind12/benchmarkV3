> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `ax` 워크트리의 `docs/features/ax-agentic-progress.testplan.md`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

---
feature_id: ax-agentic-progress
artifact: testplan
version: 2026-10-29
status: planning-reference
reviewer: fe-reviewer
reviewer_agent_id: /root/planning_review
---

# 검색 진행 표시 — 테스트 플랜

[spec](ax-agentic-progress.spec.md)의 AP-01~09와 [검색 testplan](ax-agentic-search.testplan.md)의 레이어/보안/배포 규칙을 따른다. 기존 테스트를 읽은 범위와 새로 필요한 검증을 구별한다. 이번 계획은 테스트 실행 결과가 아니다.

## 1. 요구·시나리오·레이어

| Case | 요구 | 시나리오·검증 포인트 | 레이어 | 기존 근거 / 신규 필요 |
|---|---|---|---|---|
| AP-T01 | AP-01 | POST 전송·accepted·keep-alive만 수신하면 연결 중, 실제 model/DB 진행을 추정하지 않음 | L1/L2/L3 | 현재 UI/코드 일부; 전용 신규 |
| AP-T02 | AP-02/03 | 실제 SQL작성 대기·시간→검증/DB/계산/재계획·답변의 순서/반복, 서버 duration 표시·퍼센트0개 | L1/L2/L3 | E2E '서버 이벤트로 SQL 에이전트 대기와 반복 조회 이력' 부분; MSW/서비스 신규 |
| AP-T03 | AP-02 | 중복/역순 sequence 무시, 같은 step start/end 1개 갱신, 완료 id를 running으로 되돌리지 않음 | L1/L2/L3 | parser 일부; reducer 모순/회귀 신규 |
| AP-T04 | AP-02/07 | chunk UTF-8/CRLF/multiline/comment, NaN/unknown stage·malformed JSON/shape·과대 response 안전 실패, 과거 이력 유지 | L1/L2/L3 | Zod/parser 코드 존재; 전체 경계 신규 |
| AP-T05 | AP-04 | DB 전 provider 실패·중간 실패 후 재계획·성공, 실패 이력 보존/최종 접기·clock 정리 | L1/L2/L3 | E2E '제공자 오류 시 멈춘 SQL 단계'·BE phase 실패 부분; 회복 신규 |
| AP-T06 | AP-05 | 최종 result 유실→같은 nonce/payload로 복구·turn 1개, disconnect 자체로 cancel/자동재실행 없음 | L1/L2/L3 | E2E '응답 유실' 부분; 호출수/proxy 신규 |
| AP-T07 | AP-06 | 명시 cancel/tombstone/unmount 후 늦은 progress/result 미반영, cancel API 실패시 미확인 안내 | L1/L2/L3 | E2E '취소된 느린 응답'·'모바일 다크 진행 패널과 취소' 부분; 실패/수명주기 신규 |
| AP-T08 | AP-07 | 익명/만료401·비활성/role403는 stream 전 JSON, 타 사용자/위조 ref/parent409, LLM·DB 시작0 | L1/L2/L3 | BE `test_stream_requires_same_authentication` 익명 부분; 역할/소유권/실서비스 신규 |
| AP-T09 | AP-07 | 질문/과거대화/DB 유래 role 위장·유출 지시·악성 label/error가 내부정보/canary/타사용자/SQL을 SSE/API/log에 내보내지 않음 | L1/L2/L3 | 신규 PI. 서버 강제 검사와 실제 Vertex holdout 별도 |
| AP-T10 | AP-07/08 | HTML/script/URL 같은 label·긴 정상 이름은 텍스트로 출력, 코드실행0·정상 인용 오차단 없음 | L1/L2/L3 | 신규 합성 악성/정상 대조군 |
| AP-T11 | AP-08 | 390px/light/dark·긴 label·keyboard cancel·live region·reduced-motion, 전체 폭 넘침0·tick 알림 과다0 | L1/L2/L3 | E2E 모바일 다크 부분; 접근성/motion 신규 |
| AP-T12 | AP-05/07/09 | 토큰 rotation/만료는 refs 자동 재사용 없음, preview 운영 비활성·keepalive 데이터 polling 아님 | L1/L2/L3 | 신규 서비스/세션 검증 |
| AP-T13 | AP-01/04/07/09 | 승인된 배포 후 실제 SSE/no-buffer/no-store·작업/결과·이력·비밀/mock 비노출, 핵심 read-only smoke | L4 (선행 L2/L3) | 미완료. 배포 허가 후 신규 |

## 2. 실행·증거·판정

L1은 step reducer/parser/clock·컴포넌트 Vitest, L2는 Playwright+MSW의 합성 stream/control errors다. 현재 `playwright.ax-search.config.ts`의 test auth/provider+실HTTP/PG는 L3-local 보조 증거다. 정식 L3는 승인된 preview·실BE/인증·실제 Vertex·전용 reader에서 Zod 응답·조건/근거와 proxy buffering을 확인한다. 단계 진행 정확성과 검색 정답 정확성을 각각 평가한다.

AP-T09/T10은 PI-03/04/07/09/11, AP-T07/T12는 PI-12에 매핑한다. SEC-01/02(생성 SQL 통계 위조·자유 설명 근거 검증)의 차단 결과가 SSE에서 성공으로 오인되지 않는지도 AS-T22/T23과 함께 검증한다. AP-T09는 [프롬프트 인젝션 보안 계획](../ax/natural-language-search/prompt-injection-security.md)의 공격/정상 case ID와 연결한다. 실제 비밀 대신 합성 canary를 사용하고 event/error/result/log별 노출 부재와 허용 밖 SQL/도구/타사용자 접근 부작용0을 검사한다. 악성 문자열을 단순히 출력하지 않은 것만으로 서버 경계 통과를 판정하지 않는다.

각 실행에 commit·endpoint/fixture/데이터/모델 버전·조건·선택/skip 수·exit·시간·event trace(안전한 필드)·screenshot·결과·검토자를 남긴다. 원문 인증값/provider payload·실비밀을 trace에 남기지 않는다. 새 테스트가 표준 unit/integration selector에서 빠지지 않는지 BE 수집 결과도 확인한다.

L1/L2·lint/type/build·bundle·독립 리뷰·서비스 L3·root가 승인한 머지/배포·L4를 각각 gate로 연결한다. 현재 테스트 개수나 local SSE 성공은 DONE 근거가 아니다. 보안 유출/인증 전 작업/타사용자 데이터·권한 우회는 출시 차단, 환경 부재/모델429/504/운영 갱신 미완료는 별도 보류다.
