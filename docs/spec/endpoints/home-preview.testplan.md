# Home preview test plan

1. Shared contract fixtures: valid states and strict extra-field, invalid public reason, unknown evidence, clocks, fixtures, full/partial count, PEN validation.
2. Pure priority tests across eight groups, ongoing-first, stable tie and dynamic English cup classification; other countries' Cup not treated as domestic English cup.
3. Isolated PostgreSQL 127.0.0.1:55441 only. Build existing baseline tables + apply new Supabase migration; inspect constraints; fixtures use generated test IDs. Seed deterministic DB evidence, no source/provider calls. Verify no operational DB writes.
4. Service/API integration: recommendations → chosen fixture → same stored payload; pending, facts-only, previous after failure; no valid version; invalid stored mock/identity; bounded calls; rollback and duplicate slot; kickoff crossing and target disable.
5. Vertex adapter: fixed STOP response, MAX_TOKENS/blocked/empty/malformed/extra fields/unregistered refs. Production HTTP calls only in explicit smoke command.
6. FE type/build/E2E: request identity cancellation, errors retain correct selected fixture, no polling/live score, missing sources, source clocks; L3 local API with external-call traps.

PRE-02 external coverage gaps do not authorize synthesizing provider responses. MCP is unavailable; official API read-only responses were captured before adapters were implemented. No automatic publication of unverified grounding claims.


## 2026-10-25 후속: 선택 원인·발생 시점과 매체 coverage

최신 정책/계약은 `docs/features/home-preview-research.md`가 이전 검색 예산·호출 수 설명을 대체한다. 분석 후 확정된 key_absences만 팀당 최대2명 원인/발생일을 검색한다. 원문·API 충돌/기사일·복귀일/미확인 날짜/대상 외 선수·기존 facts 불변을 검증한다. 매체 목표3곳은 API 자체 예측 제외, 부족하면 partial, 기존 저장본의 조회는 DB 출처만으로 coverage를 계산한다. 기본 자동 생성 OFF/검색 ON; 선택 원인 단계 포함 최대 모델3회(4슬롯 최대12회), provider 내부 질의 수는 실제값과 초과 여부를 기록한다. 홈 상세 버튼은 기존 fixture-detail route를 선택 external_id로 사용한다.

최종 로컬 검증: BE107/FE unit29/E2E17/실제 DB L3 4/build/lint PASS, 통합 skip0. 단순 링크 추가와 별개로 날짜·월 표시/원인 출처·선택 후 링크 갱신/클릭 이동을 브라우저에서 확인했다. 실제 맨유–본머스 새 연구 후보의 웹 전망0/원인0은 게시하지 않았고 기존 정상 저장본을 보존했다. 웹3곳 달성과 PRE-12 독립 인수/운영 적용 완료를 주장하지 않는다.
