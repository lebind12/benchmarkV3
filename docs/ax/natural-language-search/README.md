# 자연어 검색 AX 작업 컨텍스트

작성·조사 기준일: 2026-10-25.

축구 기록을 자연어로 질문하고 선수·팀·경기 목록, 순위, 비교 결과를 조회하는 작업의 시작점이다. 검색창 목업 이후의 조사와 구현 준비를 한 디렉터리에서 이어간다. 관리 기능·홈 추천/프리뷰의 작업 기록은 기존 문서에 유지한다.

## 읽는 순서

| 문서 | 역할 |
|---|---|
| [context.md](context.md) | 사용자 지시, 현재 구현, 정책, 코드 근거, 미확인 항목 |
| [research.md](research.md) | 관련 AX 사례 6개와 출처, 적용할 점과 적용 한계 |
| [dictionary-design.md](dictionary-design.md) | 지표·이름/별칭·범위 사전의 역할과 우선 작업 초안 |
| [entity-resolution.md](entity-resolution.md) | 질문 → 조회 담당 모델/내부 도구 → 사전·이름 후보 검색/선택 → Planner 문맥 전달 실행 계획 |
| [dictionary-rules.md](dictionary-rules.md) | 정규화·ID 연결·집계/누락·범위·재질문·수정/버전·평가 상세 규칙 초안 |
| [tech-stack.md](tech-stack.md) | 채택 구성, 로컬 설치 현황, 추가 개발·검증 과제 |
| [stack-comparison.md](stack-comparison.md) | SQL 조립·파서·사전 검색·Vertex 호출의 비교 기록과 선정 근거 |
| [plan.md](plan.md) | 자연어 검색의 상세 실행 순서, 완료 기준, 결정 항목 |

## 최신 결정

Vertex AI `gemini-4-argon` 사용, 로그인 필수, 기존 API-Football 기반 DB 재사용, 용어/엔티티 연결 사전 우선. [결정 기록](../../decisions/2026-10-25-natural-language-search.md)을 따른다. 후속 요청에 따라 SQLAlchemy Core·SQLGlot·Google Gen AI SDK·JSON 사전/DB 별칭·pg_trgm을 [채택 기술로 확정](../../decisions/2026-10-25-natural-language-search-stack.md)했다. 실제 모델 호출·검색 인증·사전 적재·신규 의존성 설치는 미완료다.

## 문서의 책임

- 도메인 정책 정본: [AGENTS.md](../../../AGENTS.md).
- 전체 작업·의존성·진행 상태 정본: [Plans.md](../../../Plans.md)의 AX-9~12 및 관련 의존 작업.
- 관리·홈·검색의 상위 기획과 과거 조사: [루트 plan.md](../../../plan.md). 검색 상세 실행 계획은 이 디렉터리의 [plan.md](plan.md)에서 이어간다.
- 화면 구현과 API 요구 초안: [ax-search-mock.md](../../features/ax-search-mock.md). 정식 endpoint 명세로 확정된 계약은 아니다.
- 이번 분리는 문서 정리다. 운영 조사·검색 백엔드 구현·배포 완료를 의미하지 않는다.

## 작업을 재개할 때

1. `context.md`의 확정·제안·미정을 구분한다.
2. `Plans.md`에서 진행 상태를 확인하고 `plan.md`의 해당 단계로 이어간다.
3. 코드를 바꾸기 전에 실제 적재 범위와 FE 응답 요구를 확인한다.
4. 새 근거는 출처·확인일·검증 범위를 남긴다. 조사 결과와 설계 판단을 구분한다.
5. 구현 후에는 증거를 해당 작업에 연결하고 `Plans.md` 상태를 갱신한다. 운영 적용 여부는 따로 기록한다.

[브랜치 분리 기록](branch-isolation.md): 이 커밋의 포함 범위와 기존 통합 문서/공통 구현의 경계를 확인한다.
