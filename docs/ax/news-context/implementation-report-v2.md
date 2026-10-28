# 글 속 축구 정보 호버 v2 구현 보고서

- FULL / news-developer / work id `news-context-v2`, revision 1
- 계획: `docs/ax/news-context/service-plan-v2.md`
- 브리프: `docs/ax/news-context/work-brief-v2.json`
- 구현 커밋: `69846917c0b6ea54ef20a6d1c8b96c1460fa28f7`
- 전용 작업 위치: `/Users/woolee/.codex/worktrees/news-context/benchmark`, `codex/news-context`
- v1 제출 이력 `7448f391c8195448c388d5fd484a2f2e69ec1916`을 보존하고 v2 사용자 범위를 확장했다.

## 변경 및 기준별 위치

| 기준 | 구현과 근거 |
|---|---|
| AC-1~2 | v1 route verifySession/활성 STREAMER·ADMIN 및 서버 manager_user/JWT 검증 유지. 입력20,000자/URL2,048자, HTTP(S)/credentials/제어문자 검증 유지. 문구는 기사·커뮤니티 공통 '글 본문'으로 변경. |
| AC-3~4 | `app/services/news_analysis.py`의 실제 원문 위치·인용·이름 경계 및 DB 유일 후보 검증 유지. `annotations.ts`가 같은 JS 원문 snapshot에서 evidence 안의 mention을 검증하고 텍스트 조각으로 분절. `ArticleAnnotations.vue`는 강조 이름에서 카드 및 기존 상세 링크 제공. |
| AC-5~6 | NewsAnalysisView 분석중·완료·다른 주제·불확실·대상 미확인·보류·실패 구분. 입력 보존/재시도, 중복 요청·입력 변경시 abort/세대값 검증 유지. 카드별 loading/ready/error와 retry 별도. |
| AC-7~8 | 기존 한 번의 bounded 모델 호출만 사용. hover는 일반 DB 상세 GET만 호출하며 모델/외부 축구 API/polling 없음. URL 미수집, 원문 로그 없음, 저장·발행·DB 변경·migration 없음. |
| AC-9 | `news_analysis_vertex.py` 구조화 schema에 relevance(football/not_football/uncertain)와 relevance_evidence 필수. association football과 미식축구/게임 단독/동명이인/명령문을 구분하고 혼합 글은 축구 부분만 추출하도록 지시. 서버는 원문 근거 불일치/빈 근거를 uncertain으로 낮춤. football 외에는 DB 후보 조회와 링크 없음. |
| AC-10 | `annotations.ts` evidence 출현 안의 첫 검증 이름만 강조, 전체 반복 치환 없음. UTF-16은 JS 안에서만 계산. Latin/악센트 문자 경계와 한글 조사 허용. 긴 이름 우선·겹침 제거, 동일 start/end에 다른 id/type이면 강조 보류하고 동일 대상 중복만 제거. 본문은 interpolation/text nodes + white-space:pre-wrap으로 공백·줄바꿈·한글·이모지·HTML 텍스트 보존. |
| AC-11 | ArticleAnnotations 이름 button의 mouseenter/focus/click으로 dialog 개방. 180ms 닫힘 유예로 카드 내부 이동 유지. Tab/ArrowDown으로 카드 첫 focusable 진입, Escape는 닫고 이름에 focus 반환, anchor/card 외 본문·외부 pointerdown 닫힘. viewport 기준 fixed 좌표·폭·최대높이 제한. |
| AC-12 | generalApi.team/player GET 재사용. 팀은 국가·홈구장·최근3경기 대회/날짜/스코어. 선수는 국적·현재 팀·식별 가능한 최신 시즌의 대회/팀별 출전/골/도움 행을 유지하고 합산하지 않음. NULL은 '정보 없음', 0은 0. 화면 내 type+id cache로 중복 요청 차단, key별 저장/분석 epoch로 응답 역전 차단. 실패만 명시 retry. |
| AC-13 | DB firstname 첫 토큰 + 전체 lastname의 결정론적 후보를 원명/번역명/fullname과 같은 SQL OR 쿼리로 합집합 조회. 하나의 실제 row만 유일할 때 연결하며 exact/derived 충돌은 ambiguous. 성 일부·이니셜·임의 별칭 추측 없음. |

목업/변경 endpoint 계약을 먼저 제출하고 운영자의 검토·backend 착수 지시 후 서버를 변경했다. 최종 기본 화면은 실제 authenticated POST다. DEV의 '가상 호버 예시' 버튼만 명시적 가상 글/연결/정보 카드 props를 사용하며 운영 빌드에서 해당 버튼은 표시하지 않는다.

## 실행 결과

- `/Users/woolee/benchmark/.venv/bin/python -m pytest tests/unit/test_news_analysis.py tests/integration/test_news_analysis.py -q`: **33 passed**. 실제 JWT/manager dependency와 in-memory SQLite만 사용. non-football/uncertain DB 무조회, 부정확 근거 downgrade, schema 실패, derived/exact 충돌, 성/별칭 보류, 혼합 글, 기존 권한/URL/예산/timeout/escaping 검증 유지.
- frontend에서 `./node_modules/.bin/vitest run --config /tmp/news-context-vitest.config.mjs`: **11 passed**. 원문 보존·evidence 위치·Latin/악센트·조사·반복·겹침·상충 id/type, hover→카드 유지·focus/Tab·tap·Escape/outside, GET 캐시·역전·실패 재시도, 최신 대회별 기록 및 NULL/0, v1 입력/권한/중복/stale/오류·retry와 relevance gating.
- frontend `npm run build`: **PASS** (vue-tsc + Vite).
- 추가/변경 Python 5파일 `ruff check`: **All checks passed**.
- `git diff --check`: **PASS**.
- 실제 Vertex 및 읽기 전용 DB smoke는 운영자가 수행했으며 별도 증거 `docs/ax/news-context/verification/v2/live-smoke.json` 소유를 보존했다. 자체 stub 테스트를 일반 모델 정확도 평가로 주장하지 않는다.
- 독립 browser→API→DB GET 검증은 별도 tester가 제출 SHA 기준으로 수행해야 한다. 이 보고서는 개발자 자체 확인이며 독립 PASS/머지 승인이 아니다.

## 제약

- 축구 관련성의 의미 판단은 모델에 의존한다. 서버는 schema와 원문 근거를 확인하나 의미 분류의 일반 정확도를 보장하지 않는다. 근거가 부족하면 보류한다.
- 정확한 원명·번역명·DB 파생 이름만 연결하므로 한국 커뮤니티의 별명/철자차이는 보류할 수 있다.
- 동일 인용이 여러 번 존재하면 첫 검증 출현만 강조한다. 연결할 위치를 추정해 모든 반복을 강조하지 않는다.
- 카드의 자료는 현재 저장본이며 글 작성 당시 기록으로 단정하지 않는다. 기존 상세 GET의 데이터 신선도와 결측 한계를 따른다.
- 기존 v1 제한: 단일 인스턴스 메모리 예산, provider timeout 후 진행 중 thread의 강제 종료 대신 슬롯을 유지. 운영 DB·Upstash·외부 수집·public 뉴스 변경 없음.
- 계획/브리프/progress/verification 파일은 개발자 커밋에 넣지 않았다. push·merge·배포·서비스 재시작 없음.
