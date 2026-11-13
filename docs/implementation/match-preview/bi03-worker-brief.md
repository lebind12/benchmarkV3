# BI-03 — 원래 benchmark 관리 화면의 프리뷰 탭

당신은 DeepSeek 구현 C다. AGENTS.md의 최신 모델 정책에 따라 프론트 구현도 DeepSeek에 맡긴다. 기존 계획의 GPT 직접 구현 문구는 최신 역할 정책으로 대체한다. 실제 모델 deepseek-ai/deepseek-v4.1-flash-1017, 기존 Max 설정을 유지하고 시작 ACK에 확인한다. no sub-workers. 프로필/환경 비밀값 덤프 금지.

## 목표와 병렬 소유권

원래 benchmark의 서비스 관리 페이지 `/admin`에 기존 수집 대상/수집 실행/실행 이력/번역 검수와 나란한 **프리뷰 탭**을 연결한다. 외부 경기 번호 → DB 대진 확인 → 명시적인 생성 클릭 → 저장된 본문 확인. 별도 preview 앱이나 목업 서버를 iframe/링크로 대신하지 않는다. 사용자가 실제 생성과 콘텐츠 성공 판단을 직접 한다.

소유 파일은 `frontend/**` 중 이 기능에 필요한 파일이다. 기존 소스를 보존하고 root가 중단한 아래 변경을 인계받는다. backend, scripts, out, Plans.md는 수정하지 않는다. A는 원본 앱/인증/DB, B는 preview API/생성/재시도/저장 소유다. root는 코드 편집을 멈췄으므로 frontend 단독 소유권이 C에게 있다. 서버 5173/5174/8000 변경·재시작은 root만 한다. commit/stage/reset/전체 checkout 금지.

읽을 계획: docs/superpowers/plans/2026-11-12-benchmark-preview-integration.md의 BI-03 및 연결 계약. 상세 요구: 동명 specs 파일. UI를 새로 디자인하지 말고 확정 목업의 본문 레이아웃을 실제 데이터로 구동한다. TypeScript 스킬을 적용한다.

## 이미 완료된 인계 상태 — 복원을 다시 하지 말 것

root가 c4d7d32의 원래 frontend 296파일을 canonical `frontend/`로 복원했다. 중복10파일은 `out/benchmark-integration-backup/frontend-before-bi03/manifest.json` 및 같은 디렉터리에 백업했다. 현재 preview 기능 `src/features/match-preview/` 36파일은 그대로 보존했다. `.env*`는 복원/변경하지 않았다. npm ci --no-audit --no-fund 완료(335 packages), 다시 설치할 필요 없다.

root의 부분 변경을 확인해 이어받을 것:
- vite.config.ts: 원본 multi-entry 보존, envPrefix VITE_만, localhost5173 strictPort, /api는 기본 localhost8000(override BENCHMARK_BACKEND_URL), proxy timeout0/changeOrigin false. 현재 loadEnv import와 environment 변수가 미사용으로 남아 있으므로 정리한다.
- lib/api/base.ts: DEV는 same-origin으로 호출. root .env의 원격 VITE 값에 의해 Koyeb로 우회하지 않음.
- lib/api/http.ts: /api/v1/admin/preview 경로는 원본 session.ts의 authenticatedFetch 사용, 그 외 기존 fetch. error.detail을 우선 표시. 원본 JWT refresh/me 계약을 그대로 사용.
- vitest.config.ts: 원본 tests/unit/**/*.spec.ts와 기존 src/**/*.test.ts 둘 다 포함.

현재 떠 있는5173은 out/benchmark-connected/frontend의 이전 복사본이다. 파일만 고치고 화면이 바뀌었다고 주장하지 않는다. root가 A/B/C 인계 후 canonical frontend와 통합 backend로 전환한다. 5174 목업도 건드리지 않는다.

## UI·API 계약

- 원래 AdminView → ManagementView 위치. 원래 /admin은 STREAMER도 쓰므로 프리뷰 탭/행위만 auth.isAdmin으로 제한. 서버도 ADMIN 확인(A 담당). 기존 네 탭은 유지.
- ManagementView의 현재 refresh는 모든 관리 API를 호출하고 전역 loading/error가 자식 전체를 막는다. 프리뷰 진입은 그 API들과 분리해 관련 없는 수집 정보 읽기 실패가 프리뷰를 막지 않게 한다. previewRun 같은 전용 query를 써서 원래 collection run과 충돌하지 않는다.
- GET /api/v1/admin/preview/fixtures/{fixture_id}: 기존 FixtureCandidate 단건. 404 없음,503 읽기불가, 모델0. 번호를 바꾸면 이전 응답으로 생성하지 않음.
- POST /api/v1/admin/preview/bundle-runs: {fixture_id, mode:live}. 기존 BundlePreviewRunResponse/run_id 유지. 중복 클릭 방지, POST 통신 오류를 자동 재전송하지 않는다.
- 기존 GET readerPreview/sectionResults/informationBundle/detail/list API를 재사용. 원래 JWT client 사용. 기존 types.ts/api.ts와 중복된 API·응답 모양을 만들지 않는다.
- 화면 진입/저장 결과 열기/다시 읽기/새로고침은 GET만. 결과 선택 및 직접 run id 열기로 이미 저장된 결과도 볼 수 있게 한다. 생성 중에는 시작한 경기와 상태 표시. quality/complete/insufficient 때문에 받은 본문을 숨기거나 새 모델 호출하지 않는다.
- 생성·재생성 정책 설명은 경기 한 번의 각 모듈 최초 포함3회. 전체8·시험집합 합산3 표현 제거. 기술 실패만 서버가 재시도하며 클라이언트는 POST 반복 안 함.

## 실제 저장 결과의 본문 디자인

재사용할 디자인 소스(읽기만): out/home-preview-mock/original-frontend/src/components/home-preview/MatchPreviewBody.vue, styles/match-mock.css 및 tokens.css. 정적 rawMock import를 가져오지 말고 props/adapter로 실제 저장 데이터에 연결한다. 홈 추천 정책은 이 단계에서 바꾸지 않는다.

- 전망 왼쪽2/3·점수 오른쪽1/3, 전망 근거는 전망 아래 별도 큰 글씨.
- 주목선수/부상은 팀별 좌우, 팀 로고/큰 팀명, 개별 옅은 그라데이션 패널, 큰 선수명, 세로 중앙·모든 모서리 동일 rounding 사진.
- 매체 최대3과 배당 패널. 배당은 소스별1X2 네모3칸, 없는 실제 배당을 합성 목업값으로 채우지 않음. API-Football 보충 문구 없음.
- **이름**은 기존 InlineEmphasis.vue와 같이 텍스트/strong 노드만 사용. v-html 금지. 내부 진단·면책문구를 프리뷰 본문에 섞지 않음.
- structured 없으면 저장된 섹션 본문 그대로 표시. 선수·팀 ID가 내부인지 외부인지 확인되지 않으면 이미지 URL을 추측하지 않는다. 533은 내부 Haaland ID로 API 사진 ID1100과 다르다. 하드코딩 매핑을 새로 만들지 말 것. API 값 부족하면 root에 정확한 요구를 알려 사진 없이도 본문을 보존한다.
- 구성본 선택 버전이 있으면 reader가 선택한 버전과 structured도 일치해야 한다. 최신 result를 무조건 섞지 않는다.

## 기존 기능 재사용

features/match-preview의 InformationBundlePanel, CompositionPanel, SectionRegenerationPanel, RunInspector 등의 본문 이후/접힌 진단 구조를 필요한 만큼 연결한다. 별도 검사 앱 라우트로 빠지지 않게 한다. 저장 원문 요청/응답·검색/수집·전달 기록이 문제 확인 시 열려야 한다. 사용자 클릭으로만 개별 섹션 재생성/저장 응답 재처리/구성본 최종 AI를 수행하며 자동 승인 행/자동 모델 호출 없음. 기존 미지원 행위를 완료된 기능처럼 버튼만 만들지 않는다.

## 수용과 검증 — 범위 제한

필요한 직접 검사만 frontend/src/components/management/PreviewPanel.test.ts에 연결:
1. 진입시 POST0, 번호 확인 후 해당 경기 POST1, 번호 변경/늦은 응답 혼입 방지, 더블클릭 POST1.
2. 부분 본문 표시, 저장결과 다시읽기GET만, 타경기 결과 혼입 없음, 강조 HTML 실행 안 함.
3. 기존 관리 탭 읽기 실패가 프리뷰 진입을 막지 않음과 ADMIN 표시 경계(같은 좁은 연결검사).

npm --prefix frontend run type-check 1회, 해당 vitest 파일 및 실제 수정한 기존 컴포넌트 직접 영향 검사만. 새 전체 suite/bench/유료 smoke 없음. 실패 시 현재 경계만 수정. 기존 mock/evidence는 테스트 자료로만 사용하고 live 응답인 척하지 않는다. 모델/외부수집/productionDB쓰기/서버전환/실제생성 클릭0.

완료 보고: 정확 변경 파일, 실행 명령/결과, 본문·진단/조합의 실제 연결, API 부족한 필드, 미검증 브라우저/로그인 구분, EDITING STOPPED. Plans.md 대신 root로 보고. 종료 전에 자기 dispatch 새 메일만 한 번 확인; 과거 다른 dispatch stale mail로 범위 확대 금지.
