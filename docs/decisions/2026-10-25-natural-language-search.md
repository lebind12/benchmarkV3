# 2026-10-25 — 자연어 검색의 모델·접근·데이터·사전 우선순위

## 사용자 결정

- 자연어 검색의 LLM은 기존 Vertex AI를 유지하고 Gemini 4 Argon을 사용한다.
- 검색은 로그인이 필요하다. 활성 USER / STREAMER / ADMIN이 사용할 수 있도록 서버에서 인증을 검증한다. 방송/관리 전용 권한으로 제한하는 결정은 아니다.
- 데이터는 기존 API-Football 기반 Supabase DB를 재사용한다. 검색을 위한 별도 외부 통계 공급자나 축구 데이터 복제 DB를 전제로 하지 않는다.
- 축구 지표·선수/팀 이름·별칭을 실제 데이터와 연결하는 사전을 우선 과제로 삼는다. 기존 데이터 점검은 이 사전의 매핑·집계·누락을 확인하는 데 사용한다.

## 공식 문서 확인과 적용 경계

2026-10-25에 확인한 [Google 개발자 가이드](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/guides/gemini-4-argon)의 API 모델 ID는 `gemini-4-argon`이다. 계정/리전 접근·실제 호출·구조화 출력·지연/비용은 아직 검증하지 않았다.

- 공급자/모델 비교 선정 작업은 지정 모델의 적합성·접근·해석 품질·비용 검증으로 바꾼다. 실패 시 다른 모델로 자동 변경하지 않는다.
- 검색용 모델 설정은 방송/프리뷰 설정과 분리한다. 기존 기능의 모델을 일괄 변경하거나 운영 환경변수를 수정한 결정이 아니다.
- 기존 DB 안에 검색용 view·제한된 읽기 role·별도 연결 pool을 두는 설계는 유지한다. 이는 축구 데이터 소스 변경이 아니다.
- 최신 2시즌·DB 저장본 조회·6시간 갱신·일반 페이지 polling 금지·Upstash 캐시 확대 제외 정책을 유지한다.
- 최초 결정에서는 SQL 파서 제품/버전을 미정으로 두었다. 후속 [기술 선정](2026-10-25-natural-language-search-stack.md)으로 SQLGlot을 채택했다. 정확 버전은 구현 검증 후 고정한다.
- 후속 [기술 선정](2026-10-25-natural-language-search-stack.md)으로 JSON 지표/범위 사전 + DB 별칭 테이블을 채택했다. 별칭 세부 schema·추가/수정 책임·관리 UI·자동 추천은 후속 설계다. 이번 결정으로 관리 endpoint나 UI를 선제 구현하지 않는다.

## 현재 산출물

계획과 컨텍스트를 갱신하고 [용어 사전 설계 초안](../ax/natural-language-search/dictionary-design.md)을 작성한다. 검색 인증·모델 설정·DB 구조·백엔드의 실제 구현/운영 적용과 구분한다.

상세 계획: [검색 plan.md](../ax/natural-language-search/plan.md). 작업 상태 정본: [Plans.md](../../Plans.md).
