> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `ax` 워크트리의 `docs/ax/natural-language-search/plan.md`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# 자연어 검색 서비스 완성 실행 계획

기준일: 2026-10-29. 사용자 목표는 **완성된 서비스의 머지 및 배포**다. 기획→명세→검증 정합→실제 모델·서비스 통합 인수→독립 구현 리뷰→머지/승인된 배포 순서로 진행한다. 실행 상태는 Plans.md (원문 참조 경로: `../../../Plans.md`; 이 기획 묶음에 포함되지 않음)의 AX-R-*가 정본이다.

## 1. 현행 범위와 정본

- 제품 요구: [검색](../../features/ax-agentic-search.md), [실행 단계 표시](../../features/ax-agentic-progress.md). 기존 화면·에이전트 루프는 로컬 선행 구현이며 서비스 인수 완료를 뜻하지 않는다.
- 현행 구조: 서버가 인증·범위·근거·예산을 통제하는 LangGraph Planner→조회/SQL/계산→재계획→답변. 지정 Vertex `gemini-4-argon` 유지. 프롬프트 인젝션은 [보안 인수 요구](prompt-injection-security.md)를 따른다.
- 출시 지원: 8개 선수 시즌 지표, 목록/순위/다중 선수 비교, 대회별 최신2시즌·증감/비율, 후속 조건 수정/실제 결과 참조, 자연어 확인, 누락/부분 자료, SSE 진행·취소·유실 복구.
- 유지 정책: 활성 대회, 기존 API-Football 기반 DB-only·6시간, 공통 활성 USER/STREAMER/ADMIN 인증, 전용 읽기 role/view/pool, 서버 SQL/근거 검증, 일반 페이지 데이터 polling 없음.
- 보류: 팀 자체/경기 통계, 평점·국적/포지션·연봉, 외부 웹/통계 보충, 신규 벡터 DB/모델/별도 서비스, 검색 응답 Redis 캐시, 영속 대화 보관. 이 보류를 새 지원 구현으로 확장하지 않는다.
- 과거 단계: [v1 계획 보존본](plan-v1-history.md), [실제 검색 v1](live-search.md), [대화형 v1](conversational-search.md), [최초 에이전트 설계](agentic-search.md), 로컬 구현/한계 (원문 참조 경로: `agentic-implementation.md`; 이 기획 묶음에 포함되지 않음). 과거 문서의 “구현 전”은 당시 기록이다.

## 2. 현재 확인한 상태

2026-10-29 첫 점검은 단위197/build/correctness lint/diff 통과·설정 부재 DB15 skip이었다. 후속으로 기존 Vertex/DB 로컬 설정을 발견해 토큰 갱신·지정 모델 최소 연결1회 PASS, source READ ONLY 추출과 전용 로컬 reader 복원 후 DB15 재실행 PASS를 확인했다. 실제 검색 의미/브라우저 인수와 구별한다. 환경 증거 (원문 참조 경로: `evaluation/reports/readiness-20261029.json`; 이 기획 묶음에 포함되지 않음)·모델 연결 (원문 참조 경로: `evaluation/reports/vertex-readiness-20261029.json`; 이 기획 묶음에 포함되지 않음)을 따른다. 선행 실제 에이전트 모델 전체 성공은0이며 504/429로 인수 보류다. 실제 공통 계정 로그인, 운영 reader/view 및 갱신, 독립 holdout·성능/비용 기준선, production 라우팅은 미완료다.

기존 AX state/history/review와 정제 기획/endpoint-request 누락을 확인해 현재 시점에서 재등록한다. 과거 승인·머지 이력을 만들지 않는다. `Plans.md`의 이전 `완료`는 명시된 로컬 산출물 범위이며 출시 완료가 아니다.

## 3. 보완 순서와 통과 조건

| 작업 | 산출물/통과 조건 | 다음 단계 조건 |
|---|---|---|
| AX-R-1 현행 기획 | feature 식별·역할·지원/제외·상태·보안·결정 권한·출시 목표를 정규화; historical/current 분리 | 제품 요구를 입력으로 planner 수행 |
| AX-R-2 정제 FE 계획/독립 리뷰 | 검색·진행 표시 spec/devplan/testplan, 요구 ID→L1/L2/L3/L4 시나리오 매핑, 실제 독립 PLAN_REVIEW | APPROVE만 계획 승인 기록 |
| AX-R-3 FE 요청/BE 명세 | 화면 기반 endpoint-request, endpoint state/task/history, 명확한 shape/오류/TTL/취소/멱등성/인증 경계·독립 정답·testplan, 독립 SPEC_REVIEW | 승인 후 기존 구현과 차이 수정 |
| AX-R-4 제품 테스트 정합 | marker 선택, 관련 파일·로그·결과·변경 영역 coverage·의존성·누락/skip 확인, 실제 회귀 | 일반 제품 테스트와 정상/실패 회귀 확인 |
| AX-R-5 서버·FE 서비스 통합 | 공통 세션/JWT·토큰 rotation/만료·권한 회수, 운영용 reader/views/migration·자료 갱신/일관성, /search production 노출·DEV 도구 차단·zod·명확한 상태 | 격리된 production 유사 환경에서 실제 계정→API→reader→화면 |
| AX-R-6 독립 정답/보안 인수 | versioned snapshot/기준 SQL·독립 expected/holdout, 실행완료와 정답 분리, 실제 지정 모델 질의/후속·직접/간접 인젝션·출력/타사용자 격리, 비용/지연/오류 기준선과 출시 한도 고정 | provider 실패/정답 오류를 미완료로 유지, 위반0 |
| AX-R-7 구현 독립 리뷰 | FE/BE 구현 리뷰, 표준 단위·DB·UI·type/build·coverage·CI 로그를 commit/데이터/실행 설정에 연결, 전체 차단 이슈 해소 | 머지 가능한 PR/commit·복구 방법·변경 영향 확정 |
| AX-R-8 머지·배포 | 대상 브랜치/환경/서비스 확인, 승인 조건 확인, PR 기반 통합·필요 migration/구성 적용·배포, 인증/검색/권한/갱신/오류 post-deploy smoke | 실제 배포·검증 증거 후 서비스 완료 |

기획/검증·보안 수정은 격리 검증한다. 실제 모델 인수보다 성능 최적화/RAG를 먼저 진행하지 않는다. 운영 준비 설계와 격리 구현은 진행하되 실제 운영 권한·환경 변경/배포는 별도 경계를 따른다.

## 4. 검증·증거의 해석

- 파일 지정 테스트 개수와 정식 `pytest -m unit`/`-m integration` 선택을 일치시킨다. 테스트가 존재해도 선택되지 않으면 게이트 증거가 아니다.
- 결정론적 provider의 HTTP/SQL/UI 통과는 자연어 이해 정확도 증거가 아니다. 실제 모델의 반환 성공과 ID/값/조건/상태/근거 정확성을 분리한다.
- independent expected를 구현 결과에 맞춰 갱신하지 않는다. holdout을 프롬프트 수정에 쓰면 회귀군으로 전환하고 새 holdout을 준비한다.
- fresh 운영 통합과 고정 snapshot oracle를 별도로 관리한다. 고정 snapshot의 captured_at/TTL을 바꿔 실제 최신 데이터로 가장하지 않는다.
- 로컬 통합은 L3-local 보조증거다. 기존 workflow의 preview L3·배포 후 L4를 통과했다고 기록하지 않는다. 배포 전 단계는 구현/리뷰/릴리스 준비 상태로 남긴다.
- 품질·안전성·비용/지연 기준선·보안 공격군은 requirement/case/run ID, 코드/사전/데이터 버전, 기대/실제·실패/skip·토큰/비용 미확인을 기록한다. 단위197은 현재 로컬 실행이고 과거 DB/UI 수치는 역사 증거다.

## 5. 작업·머지·배포 경계

현재 worktree `/Users/woolee/benchmark-ax`, branch `feat/ax-natural-language-search`에서만 편집한다. 현 미커밋 산출물을 보존하고 전체 일괄 커밋/stash/reset/clean을 하지 않는다. 다른 세션과 공용 파일은 PR/커밋 기반으로 조정한다. 다른 worktree의 HEAD/인덱스/파일을 수정하지 않는다.

사용자는 머지·배포를 최종 목표로 지정했다. AGENTS.md의 명시적 “배포해” 요청은 여전히 필요하다. deployment를 트리거하는 push/merge·환경변수 변경·서비스 재시작은 배포 경계다. 그 전까지 검토 가능한 변경·PR 본문·테스트·migration/구성안·롤백/사후검증을 준비한다. 코드/격리 검증을 진행하기 위한 반복 승인 요청은 하지 않는다.


## 6. 미확정의 해소 시점

운영 reader/갱신 방식·접속 환경·권한·자료 기준 시각과 source completeness는 AX-R-3/5에서 실측하고 migration/모델 정합을 검토한다. 비용·지연·할당량·동시성·로그 보관 최소화는 AX-R-6에서 실측 후 고정한다. 머지 대상/자동배포 연계·운영 비밀/권한 가용성은 읽기 조사 후 불명확할 때만 사용자에게 확인하며 확인 전 위험한 기본값을 적용하지 않는다.

운영 통합의 구현 전 요구는 [production-runtime.md](production-runtime.md)에 정리한다.

## 7. main 통합 준비에서 확인한 의존성

2026-10-29 `origin/main`을 읽기 fetch로 확인했다(관측 HEAD `bf23b93`). AX 선행 HEAD와 main 사이에 관리/홈 등255파일 차이가 있으므로 인증 파일만 임의 복사하거나 AX의 오래된 공통 파일로 main을 덮지 않는다. 공통 JWT/refresh(`app/core/sessions.py`, auth router), config/CORS, router/header/auth store, main 앱 등록, pyproject/production 설치 경로, Plans/루트 기획의 충돌을 커밋 기반으로 병합·검증해야 한다. 원격 코드 조회/fetch는 다른 worktree의 HEAD/인덱스/작업 파일을 바꾸지 않았다.

기존 서비스 계정과 DB 설정은 원본 로컬 환경 파일을 참조하며 비밀값을 repo로 복사하지 않는다. 격리 PostgreSQL 복원은 이 세션이 새로 만든 AX 전용 loopback 컨테이너만 사용했다. 공통 auth를 검증할 때는 다른 프로젝트가 쓰는 localhost8000을 기존 football authority로 가정하지 않는다.


## 8. 실제 E2E 인수 체크포인트 — 2026-10-29

사용자 요청: “E2E 테스트까지 진행해주세요. 머지 직전까지”. 현재 단계는 **AX-R-6 실제 모델·브라우저 인수**이며 실패가 남아 AX-R-7 최종 승인으로 넘어가지 않는다. 머지·push·배포는 실행하지 않았다.

- 실제 production-mode 브라우저 3회에서 로그인은 통과했으나 첫 검색이 완료되지 않았다. SDK 504를 관측했고 후속·복구·회전·취소 단계는 NOT_RUN이다. 실패 결과를 보안 통과나 정확도 통과로 세지 않는다.
- 단순 득점 Q-GOALS는 planner→SQL→실제 reader 조회→finish까지 성공했지만 answer 역할이 504로 끝났다. 짧은 동일 모델 연결 진단 4.477초 성공만으로 이 검색을 정상 판정하지 않는다. provider latency와 복잡도 영향은 분리 조사해야 하며 “인증/네트워크 단절만이 원인”이라고 단정할 수 없다.
- 실제 SQL `row_budget` 거절도 관측했다. 기존 1..100 리터럴/intent limit 규칙을 설명하는 SQL 지침 후보를 명확히 했으며 validator·권한·정답·180초·12 attempts는 유지했다. 이 지침의 실제 비교 검색 성공은 아직 미관측이다.
- source bf23b936의 최신 main을 별도 임시 복사본에 결합해 기존 홈·관리·방송 파일을 보존했다. 원본 main/관리 worktree와 AX HEAD·인덱스는 변경하지 않았다. 이 후보의 BE unit 최종1,257 PASS(표준 marker1,068 + 별도189, 분할 실행), FE unit292 PASS, type/build PASS. SQL limit 보안 회귀 등113건도 별도로 PASS했다. 이는 actual E2E 완료가 아니다.
- AX PostgreSQL 실제 통합88건과 독립 report 경로1건, MSW 브라우저13건은 통과했다. AX 변경 runtime34파일의 합산 coverage는 모두80% 이상이다. 최종 후보·독립 리뷰/모델/CI/배포 근거를 대신하지 않는다.
- 실제 비슈퍼유저 CREATEROLE 격리 TLS fixture에 Supabase CLI migration 적용/후속 membership cleanup/재실행을 확인했다. 운영 DB DDL0. fixture 두 시즌 관측은 원천 export 시각을 쓰는 통제값으로 운영 수집 성공의 증거가 아니다.
- 유료 전체 재시도는 중단했다. 테스트 전용 Redis prefix의 세션11개를 제거했고 다른 prefix 접근/삭제0이다. 같은 모델·같은180초 한도에서 실제 Q/E/PI/SEC와 독립 질문 조합 인수, 최종 FE/BE 독립 리뷰를 완료하기 전 머지 준비 완료로 표시하지 않는다.

allowlist된 실제 결과는 premerge-actual-e2e-20261029.json (원문 참조 경로: `premerge-actual-e2e-20261029.json`; 이 기획 묶음에 포함되지 않음)에 있다. 원문/계정/토큰/SQL/민감 진단은 workspace 밖 private0700/0600 보관이다.
