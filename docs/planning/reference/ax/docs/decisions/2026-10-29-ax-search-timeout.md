> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `ax` 워크트리의 `docs/decisions/2026-10-29-ax-search-timeout.md`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# AX 검색 시간 제한 — 2026-10-29

사용자 요청: “시간제한 정책을 수정하고 독립리뷰까지 끝내주세요.” 기존 180초의 원인을 분리하기 위해 직전 Q-GOALS 한 건을 진단용900초 상한으로 단1회 실행했다. 검색202.770초/프로세스205.988초, 모델5회/DB1회, 수치·순서 정답 일치였다. 조회 후 완료판단 호출135.492초가 가장 길었고 lookup/query 반복0, 자동 전체 재시도0이었다. 이 한 표본은 모집단 p95나 모든 질문 완료를 보장하지 않는다.

## 결정

- agentic 검색 전체 deadline900초. 생산 모드 진입부터 snapshot pin·계획·SQL·검토·답변·최종 commit까지 같은 deadline이다.
- SDK 각 호출은 min(900초, 원래 deadline까지 남은 시간)만 사용한다. 호출별 deadline 재설정·모델fallback·자동 전체 재실행0, SDK attempts1과 모델 최대12회 유지.
- 일반 브라우저 전송에는 기존처럼 임의180초 타이머가 없다. 수동취소/세션변경은 AbortSignal로 처리한다. 테스트용 HTTP proxy920초, Playwright 단일 작업 대기930초. 운영의 별도 gateway/idle timeout은 배포 전 설정 확인과 실제 환경 smoke 대상이며 이 로컬 결과로 배포 성공을 주장하지 않는다.
- 별도 component 평가 CLI는 기본900초, 여러 독립 사례를 순차평가할 때 batch 전체 최대3600초다. 이는 각 검색900초를 늘리지 않는다. model32/DB24/tokens500000 batch상한·unknownusage 중단을 유지한다. 실제사례를4개씩나눠평가할시간을확보하며 CLI경계900/3600허용·3601거절을SDK0 단위검증한다.
- E2E는 여러 검색을 한 시나리오로 실행하므로 전체5400초, 모델32회/DB24회/보고tokens500000 상한이다. 각 검색은900초/모델12회/보고tokens120000 이내여야 한다. 누락 usage/provider 실패/NOT_RUN은 통과가 아니다. tokens는 실측 후 판정이며 정확한 사전 금액 hard cap을 주장하지 않는다.
- 기존 launcher의 누적 token counter에 잘못 적용된 turn120000 상한을 이미 명세된 suite500000과 일치시킨다. per-turn120000 판정은 각 stage 차이로 유지한다. 새 운영 모델 예산 확장이 아니다.
- 취소 ack 후 nonce409와 늦은 SDK 응답의 저장0을 실제 관측한다. test-only instance observer는 응답/권한/모델을 대체하지 않고 private 숫자 counter만 기록한다. 취소된 nonce의 replay를 완료 관측으로 오인하지 않는다.
- 만료 뒤 결과 commit 금지, 반복 지문 차단·슬롯2·JWT/nonce binding·TTL1800·DB read-only/3초 query timeout·6시간 수집 신선도는 그대로 유지한다. JWT 만료와 검색 deadline은 서로 다른 정책이며 JWT 유효기간을 늘리지 않는다.

시간 한도의 server 정본은 app/ax/search_policy.py다. E2E의 ms 단위 상수와 proxy/PW 여유는 parity test가 검증한다. 실제 E2E/정확도/PI 및 BE/FE 독립 검토가 남아 있으며 이 정책 단위 테스트만으로 전체 서비스 인수나 머지 준비 완료를 승인하지 않는다. remoteDDL/push/merge/deployment/운영 환경 변경0.

독립검토 보완: runner의 원래deadline/취소상태를SQL executor에 전달하고 AST확인 전·connection 감사 후·EXPLAIN후 실제SELECT직전·결과반환전에같은deadline/취소를확인한다. 연결보유중새pool연결을열지않는다. DB3초timeout은그대로다. 이미시작한호출의즉시강제종료를보장하지않고만료후새SQL/결과commit을차단한다. 관측기등록부터startup전체를복원context로감싸고, frontend임시프로젝트준비중copy/link실패도자기프로젝트만제거한다.

최종dispatch guard는원래connection의execute/exec_driver_sql 두메서드만감싸므로audit내부의각SQL도동일deadline/취소를확인한다. pool대기후첫SQL전에도확인하며추가DB연결·새transaction을만들지않는다. 이미반환된결과의정답/조건/단위를보정하지않는다.
