# 자연어 검색 AX 기획 진입점

작성일: 2026-10-25. 이 브랜치는 현재 세션의 자연어 검색 목업·조사·사전 조회 계획만 분리한다. 다른 세션이 작성 중인 루트 통합 기획과 관리/홈 변경은 가져오지 않았다. 원래 체크아웃의 plan.md는 그대로 보존했다.

시작점: [자연어 검색 컨텍스트](docs/ax/natural-language-search/README.md). 상세 실행 계획은 [검색 plan.md](docs/ax/natural-language-search/plan.md), 작업 상태는 [Plans.md](Plans.md)를 따른다.

## 6. 자연어 → SQL 검색 AX

2026-10-25 후속 결정: Vertex AI `gemini-4-argon` 사용, 로그인 필수, 기존 API-Football 기반 DB 재사용, 지표·선수/팀 이름·별칭 연결 사전 우선. [결정 기록](docs/decisions/2026-10-25-natural-language-search.md)을 따른다. 모델 호출·검색 인증·사전 적재는 아직 구현 완료가 아니다.

후속 기술 확정: SQLAlchemy Core·Pydantic·SQLGlot·Google Gen AI SDK·JSON 사전/DB 별칭·pg_trgm을 채택했다. [기술 선정 기록](docs/decisions/2026-10-25-natural-language-search-stack.md)이 현재 구현 기준이며, 패키지 설치·DB 확장/권한·실제 모델 호출·품질 검증은 후속 작업이다.

사전/이름 조회 실행 계획은 [entity-resolution.md](docs/ax/natural-language-search/entity-resolution.md)를 따른다. 통합 기획 문서가 기존 작업에서 커밋된 뒤 검색 부분을 병합할 때 이 진입 링크와 결정을 유지한다.
