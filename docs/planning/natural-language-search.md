# 로그인 기반 자연어 검색 AX

현재 상태: **기획 보존 / 구현 삭제**. 기존 완료·검증 수치는 과거 기록이다.

## 사용자 결정과 지원 범위

- `/search`에서 활성 USER/STREAMER/ADMIN이 자유로운 한국어 질문으로 저장된 축구 기록을 찾는다. 인증 전 모델·축구 조회를 실행하지 않는다.
- 모델은 기존 사용자 지정 Vertex AI `gemini-4-argon`이다. 실패를 이유로 자동 변경하지 않는다.
- 기존 API-Football 기반 DB, 활성 대회, 대회별 현재·실제 직전 시즌, 6시간 갱신 정책을 사용한다. 외부 웹이나 별도 통계 공급자로 부족한 값을 보충하지 않는다.
- 최초 범위는 선수 시즌 **득점, 도움, 출전 분, 출전 횟수, 경고, 퇴장, 득점+도움, 90분당 득점**의 8개 지표다. 목록·순위·다중 선수 비교·두 시즌 차이/비율과 후속 조건 변경을 포함한다.
- 팀은 선수의 소속 조건과 이름 후보에 사용한다. 팀 자체·경기 통계, 평점, 국적/포지션, 연봉, 실시간, 영속 대화 보관, 검색 Redis 응답 캐시는 보류 범위다.

## 경험과 근거

질문 입력→사전·대회·시즌·이름 확인→필요한 경우 자연어 재질문→조회/계산→설명·표·적용 조건·단위·정렬·자료 시각·누락 표시→후속 질문으로 이어진다. 동명이인이나 조건 모호성을 임의 확정하지 않는다. 이전 결과의 선수 참조와 조건 변경을 실제 ID에 연결한다.

진행·지연·취소·연결 유실·결과 복구를 한국어로 구분하고 SSE 기반 진행 표시를 설계한다. 내부 추론 원문·민감 SQL·토큰을 사용자에게 노출하지 않는다. 일반 데이터 polling을 도입하지 않는다.

## 조회 구조와 보호 요구

LangGraph의 계획→조회/SQL/계산→재계획→답변 방향, JSON 지표/범위 사전과 DB 별칭, SQLGlot 검증 방향을 보존한다. 모델 제안과 서버 실행 권한을 분리하고 전용 읽기 role/view/pool, 허용 범위·SQL·근거·결과 검사를 둔다. 사용자 입력·대화·DB 문자열을 지시 권한으로 승격하지 않으며 직접/간접 프롬프트 인젝션과 타 사용자 격리를 수용 기준에 포함한다.

NULL/0, 소속별 중복·합계, 동률, per90 분모와 최소 출전 분, 두 시즌의 실제 데이터 범위를 사전과 독립 정답에 연결한다. 정확한 값 없이 모델이 통계나 ID를 창작하지 않는다.

## 최신 시간 제한 결정

검색 한 건의 전체 기한은 **900초**다. 계획·조회·답변·최종 저장이 같은 기한을 공유하며 매 모델 호출마다 초기화하지 않는다. 모델 최대 12회, SDK attempts 1, 자동 전체 재실행·모델 fallback 없음이라는 기존 제한을 보존한다. 취소·만료 후 새 SQL과 결과 저장을 차단하고 진행 중 외부 호출의 즉시 종료를 보장한다고 표현하지 않는다. DB 읽기 query timeout 3초는 별도 제한이다. 옛 180초 기록은 최신 정책이 아니다.

## 남은 검증 과제

실제 모델의 질문·후속 대화·누락·보안·취소/복구를 독립 정답과 고정 자료로 확인해야 한다. HTTP 성공과 정답을 구분하고 provider 오류·NOT_RUN을 통과로 세지 않는다. 전용 reader/갱신, 공통 인증, gateway/idle timeout, 지연·비용·동시성 기준은 재구축 후 새로 검증한다. 현재 로컬 인수·실제 E2E·운영 배포는 이번 정리에서 실행하지 않았다.

## 근거

- [검색 제품 요구](reference/ax/docs/features/ax-agentic-search.md)
- [진행·취소 화면 요구](reference/ax/docs/features/ax-agentic-progress.md)
- [사전 설계](reference/ax/docs/ax/natural-language-search/dictionary-design.md)
- [조회 도구 계약](reference/ax/docs/ax/natural-language-search/retrieval-tool-contracts.md)
- [보안 수용 요구](reference/ax/docs/ax/natural-language-search/prompt-injection-security.md)
- [900초 정책 결정](reference/ax/docs/decisions/2026-10-29-ax-search-timeout.md)
- [정확도 평가·채점 설계 초안](reference/main/output/evaluation/ax-accuracy-v1/rubric.md)
- [40과제·64턴 질문과 기대 답변 기획](reference/main/output/evaluation/ax-accuracy-v1/questions-and-answers.md)
