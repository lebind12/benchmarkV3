> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `ax` 워크트리의 `docs/ax/natural-language-search/README.md`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# 자연어 검색 AX

현행 기준: 2026-10-29. **에이전트 검색이 현재 구현이며, 서비스 인수는 미완료다.** 사용자 목표는 현행 기획 정리부터 검증 순서를 따라 완성된 서비스의 머지·배포까지 진행하는 것이다. 프롬프트 인젝션 대응을 출시 필수 검증에 포함한다.

현재 정본은 [서비스 완성 계획](plan.md), [제품 요구](../../features/ax-agentic-search.md), [진행 표시](../../features/ax-agentic-progress.md), [보안 인수](prompt-injection-security.md), Plans.md (원문 참조 경로: `../../../Plans.md`; 이 기획 묶음에 포함되지 않음)의 AX-R-*다. 현재 로컬 구현/과거 인수 한계는 구현 기록 (원문 참조 경로: `agentic-implementation.md`; 이 기획 묶음에 포함되지 않음)을 참조한다. 이전 완료 표기는 로컬 산출물 범위이며 정식 게이트 통과나 배포 완료가 아니다.

2026-10-29 재검증: 단위197/build/lint 통과, DB15는 명시 local config 부재로 skip. 최신 핵심 테스트4파일58개는 표준 marker 선택에서 제외되어 보완 대상이다. 실제 모델 전체 성공0·429/504 보류, 운영 reader/갱신·실제 계정·독립 holdout·성능/비용 인수는 미완료다.

2026-10-29 환경 재확인: 기존 관리 checkout의 로컬 설정에서 Vertex/DB 구성을 발견했다. 기존 서비스 계정 파싱·Google token refresh·project 일치 확인은 PASS다. 인증값은 출력/복사하지 않았다. 후속으로 fresh 축구 snapshot·전용 로컬 reader를 복원해 DB15 재실행 PASS, 지정 모델 최소 연결 요청1회 PASS를 확인했다. 환경 증거 (원문 참조 경로: `evaluation/reports/readiness-20261029.json`; 이 기획 묶음에 포함되지 않음)·모델 연결 (원문 참조 경로: `evaluation/reports/vertex-readiness-20261029.json`; 이 기획 묶음에 포함되지 않음)을 참조한다. 실제 전체 검색/의미/실계정 인수는 별도 미완료다.

## 2026-10-25 단계별 역사 기록

아래는 과거 목업·v1·초기 조사 문맥이다. “현재/다음/미구현”은 당시 단계의 기록이며 현행 작업 순서는 상단 정본을 따른다.

작성·조사 기준일: 2026-10-25.

축구 기록을 자연어로 질문하고 선수·팀·경기 목록, 순위, 비교 결과를 조회하는 작업의 시작점이다. 검색창 목업 이후의 조사와 구현 준비를 한 디렉터리에서 이어간다. 관리 기능·홈 추천/프리뷰의 작업 기록은 기존 문서에 유지한다.

## 읽는 순서

| 문서 | 역할 |
|---|---|
| [실제 검색 구현](live-search.md) | 공통 인증·실제 Vertex·8개 지표·읽기 전용 SQL·실데이터 로컬 연결과 한계 |
| 실제 검색 직접 사용 (원문 참조 경로: `evaluation/manual-live-search.md`; 이 기획 묶음에 포함되지 않음) | 5188/search/live 접속·기존 계정 로그인·검증 재현 |
| data-audit.md (원문 참조 경로: `data-audit.md`; 이 기획 묶음에 포함되지 않음) | 읽기 전용 DB 실측·누락/이름 충돌·권한/시즌 문제와 재현 근거 |
| [semantic-catalog.json](semantic-catalog.json.md) | 실측 컬럼에 연결한 비활성 지표·범위·관계 정의 초안 |
| [retrieval-tool-contracts.md](retrieval-tool-contracts.md) | 4개 내부 조회 도구의 구체 입출력·후보/잘림·서버 판정 계약 초안 |
| [context.md](context.md) | 사용자 지시, 현재 구현, 정책, 코드 근거, 미확인 항목 |
| [research.md](research.md) | 관련 AX 사례 6개와 출처, 적용할 점과 적용 한계 |
| [dictionary-design.md](dictionary-design.md) | 지표·이름/별칭·범위 사전의 역할과 우선 작업 초안 |
| [entity-resolution.md](entity-resolution.md) | 질문 → 조회 담당 모델/내부 도구 → 사전·이름 후보 검색/선택 → Planner 문맥 전달 실행 계획 |
| [dictionary-rules.md](dictionary-rules.md) | 정규화·ID 연결·집계/누락·범위·재질문·수정/버전·평가 상세 규칙 초안 |
| [tech-stack.md](tech-stack.md) | 채택 구성, 로컬 설치 현황, 추가 개발·검증 과제 |
| [stack-comparison.md](stack-comparison.md) | SQL 조립·파서·사전 검색·Vertex 호출의 비교 기록과 선정 근거 |
| 직접 이름 점검 (원문 참조 경로: `evaluation/manual-name-lab.md`; 이 기획 묶음에 포함되지 않음) | 로컬 화면 접속·테스트 코드·입력 예시·현재 한계 |
| evaluation/README.md (원문 참조 경로: `evaluation/README.md`; 이 기획 묶음에 포함되지 않음) | 구현된 offline E1 평가 실행법·합성 fixture/52개 개발 사례·미구현/한계 |
| [evaluation-plan.md](evaluation-plan.md) | 개발 전 평가 준비·정답/fixture·단계별 정확도/안전성·성능/비용 측정과 통과 조건 |
| [plan.md](plan.md) | 자연어 검색의 상세 실행 순서, 완료 기준, 결정 항목 |

## 최신 결정

Vertex AI `gemini-4-argon` 사용, 로그인 필수, 기존 API-Football 기반 DB 재사용, 용어/엔티티 연결 사전 우선. [결정 기록](../../decisions/2026-10-25-natural-language-search.md)을 따른다. 후속 요청에 따라 SQLAlchemy Core·SQLGlot·Google Gen AI SDK·JSON 사전/DB 별칭·pg_trgm을 [채택 기술로 확정](../../decisions/2026-10-25-natural-language-search-stack.md)했다. 실제 모델 호출·공통 인증 authority·로컬 실제 데이터8지표·SQL/FE 연결과 AX 전용 의존성 설치는 완료했다. 운영 경로/전체 사전·독립 품질 인수는 미완료다.

## 문서의 책임

- 도메인 정책 정본: [AGENTS.md](../../../../main/domain-policy.md).
- 전체 작업·의존성·진행 상태 정본: Plans.md (원문 참조 경로: `../../../Plans.md`; 이 기획 묶음에 포함되지 않음)의 AX-9~12 및 관련 의존 작업.
- 관리·홈·검색의 상위 기획과 과거 조사: [루트 plan.md](../../../plan.md). 검색 상세 실행 계획은 이 디렉터리의 [plan.md](plan.md)에서 이어간다.
- 목업 화면/API 요구 초안: [ax-search-mock.md](../../features/ax-search-mock.md). 정식 endpoint 명세로 확정된 계약은 아니다.
- 이번 분리는 문서 정리다. 문서 분리와 운영 조사·검색 백엔드 구현·배포 완료를 구분한다. 2026-10-25 읽기 전용 DB 33개 조회는 완료했으며 로컬 실제 검색 런타임은 구현했으며 운영 등록·배포는 미완료다.

## 작업을 재개할 때

1. `context.md`의 확정·제안·미정을 구분한다.
2. `Plans.md`에서 진행 상태를 확인하고 `plan.md`의 해당 단계로 이어간다.
3. 코드를 바꾸기 전에 실제 적재 범위와 FE 응답 요구를 확인한다.
4. 새 근거는 출처·확인일·검증 범위를 남긴다. 조사 결과와 설계 판단을 구분한다.
5. 구현 후에는 증거를 해당 작업에 연결하고 `Plans.md` 상태를 갱신한다. 운영 적용 여부는 따로 기록한다.

브랜치 분리 기록 (원문 참조 경로: `branch-isolation.md`; 이 기획 묶음에 포함되지 않음): 이 커밋의 포함 범위와 기존 통합 문서/공통 구현의 경계를 확인한다.

현재 실제 화면/API 정본은 [ax-search-live.md](../../features/ax-search-live.md)와 [endpoint 명세](../../spec/endpoints/ax-search-live.md)다. 과거 목업·offline 문서는 해당 단계의 증거로 유지한다.
