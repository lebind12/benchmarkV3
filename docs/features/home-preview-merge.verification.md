# 홈 프리뷰·관리 기능 로컬 main 통합 검증 — 2026-10-26

사용자 지시: `/Users/woolee/benchmark-main`의 `feat/home-preview-json` 변경을 검증·커밋하고 관리 `278d152`가 반영된 로컬 main에 통합한다. 필요한 운영 DB 마이그레이션을 적용·확인한다. 원격 push·배포·서비스 재시작은 하지 않는다.

## 변경과 충돌 해결

- 남아 있던 홈 전체JSON·직접저장 회귀·프롬프트·생성시점·프론트 정리를 `c7608df`에 커밋했다.
- 로컬 main `278d152`를 홈 브랜치에 merge해 충돌을 해결했다. AGENTS/Plans/DB 문서와 의존성은 양쪽을 유지했고, plan.md는 관리 §1–11 및 메인 §12–14를 합쳤다. FastAPI는 관리 인증/CORS와 홈 router를 함께 등록한다.
- 인증·권한, 관리 화면/컴포넌트, 관리 목업 제거, 일일 수집 runner/scheduler 및 번역 보호는 `278d152` 내용을 유지한다. 해당 핵심 파일들은 main 원본과 byte 단위 Git diff가 없다.
- 관리 통합에서 scheduler가 `management_runs.start_scheduled_run`으로 바뀐 것을 반영했다. 성공적으로 DB를 커밋한 정기/인증 수동 수집 이후 홈 후처리를 연결한다. 실패·취소·비활성 설정에서는 호출하지 않고 프리뷰 오류가 성공한 축구 데이터 수집을 실패로 바꾸지 않는다. 기존 lease·슬롯·킥오프 제한은 그대로 적용한다.
- 배포 시 requirements.txt 설치 경로에서도 JSON Schema 의존성이 빠지지 않게 맞췄다.

## 자동 검증

- Backend: 전체 `tests/unit` 및 홈·관리·카탈로그·로그분석·번역조건의 PostgreSQL 통합 테스트 **534 PASS**, 51.93초. 테스트 DB는 로컬55441, 각 테스트가 무작위 schema를 생성/삭제한다.
- Backend 명령: `pytest tests/unit tests/integration/test_home_preview.py tests/integration/test_home_preview_single_call_storage.py tests/integration/test_home_preview_migration.py tests/integration/test_streamer_management.py tests/integration/test_catalog_discovery.py tests/integration/test_sync_log_analysis.py tests/integration/test_translation_affiliation_filters.py -q`.
- 새 migration 테스트는 빈 schema에서 Alembic 전체 head 적용 →0017로 downgrade하여 관리 테이블 보존/홈4테이블 제거 확인 →head 재적용을 검증했다. 관리 후처리5개 테스트는 commit 선행·성공/실패·취소·비활성·프리뷰 자체 오류를 검증한다.
- FE 전체 unit **233 PASS /35 files**, TypeScript/Vite production build PASS.
- 홈 Playwright **18 PASS**. 별도5192에서 생성시각/빈상태/접는출처/화면 정리를 확인했다.
- 관리 실제 Vue→FastAPI→Postgres Playwright **10 PASS**. 기존 서버와 분리한8022/5196, 로컬55441의 전용 `management_home_merge_20261026` schema를 사용했고 종료 후 해당 schema를 제거했다. 평가 목업 부재·권한·refresh·수집/취소/복원·번역충돌을 유지한다. 축구/Redis는 fixture이며 유료 호출은 하지 않았다.
- 홈 변경 Python Ruff 및 Git 공백 검사 PASS. 테스트용 코드의 포트/DB 선택은 명시 환경변수로 분리하며 기존 기본 설정도 유지한다.

## 운영 DB 적용과 사후 검증

- 적용 전: Alembic0017 관리 스키마/RLS 존재, 홈4테이블 없음. 기존 관리 SQL을 다시 실행하지 않았다.
- 추가: Supabase 정본 `20261024235328_home_preview_storage.sql` 및 Alembic bridge `0018_home_preview_storage`(parent0017).
- Supabase CLI `db query --db-url … --file …`로 홈 DDL과 Supabase migration journal/0018 revision을 **하나의 DO 문 트랜잭션**에서 적용했다. 이 CLI는 여러 prepared commands를 받지 않아 최초 batch는 SQLSTATE42601로 실행 전 거부되었고, 단일 atomic statement로 적용했다. 배포·환경변수 변경·서비스 재시작은 하지 않았다.
- 사후 READ ONLY 트랜잭션에서 ORM과 실제 컬럼/타입/nullability/PK/UNIQUE/CHECK/FK 삭제 동작/인덱스/RLS를 대조했다. 직접 접근 policy는0개이며 홈 네 테이블은 모두0행이다. 운영 프리뷰 생성/기존 축구 데이터 변경은 하지 않았다.
- 관리 RLS와 사람 수정 보호 trigger4개 유지. 통합 코드 TestClient가 운영 DB를 READ ONLY로 조회하여 추천/프리뷰 공개GET 모두200, `generation_due_at` 제공, GET시 생성 미실행을 확인했다. 운영 실행 중인 서비스의 배포 상태를 검증한 것은 아니다.
- 비밀값을 제외한 실행 증거: [home-preview-production-db-verification.json](home-preview-production-db-verification.json).

## 최종 Git 반영 방식

관리·AX의 checkout/HEAD/인덱스/파일은 수정하지 않는다. 검증된 통합 merge commit을 만든 다음 이 worktree에서 로컬 main을 fast-forward한다. 최종 main SHA와 관리/홈 양쪽 ancestry는 Git으로 확인하여 사용자에게 보고한다. 원격 반영과 배포는 별도다.

## 2026-10-26 홈 스크롤 정비 후속

사용자 요청으로 main의 중첩 스크롤을 정리했다. 바깥 `UiReviewHomeView`만 높이/스크롤을 소유하고 공통 `panel-scroll`을 사용한다. 안쪽 래퍼는 고유 클래스의 div로 바꿔 부모 scoped CSS가 자식 루트에 같은 고정 높이/패딩을 적용하지 않도록 했다. `100dvh`로 모바일 viewport 높이를 반영하며 키보드 진입/스크롤을 지원한다. 짧은 내용에서도 생기던24px 외부 넘침을 제거했다.

글래스 색상 장식은 절대 위치의 별도 backdrop에 넣고 해당 레이어에만 `overflow:clip`을 적용한다. 음수 위치와 고정 높이가 본문 scrollHeight/scrollWidth를 늘리지 않으면서 카드 그림자·glass·스크롤 reveal은 유지한다. 공유 CSS를 사용하는 목업도 같은 레이어 구조를 적용했다. 제거된 대시보드용 home store bootstrap/teardown을 빼고 추천/저장프리뷰 요청만 사용한다.

검증: FE 전체unit233 PASS, TypeScript/Vite build PASS. 기존 홈E2E18+데스크톱/모바일 ready/pending 스크롤4=22 PASS; 이어 빈 화면2 PASS로 총24개 브라우저 검증. 새 검증은 단일 main/세로스크롤 owner1개, 숨긴스크롤바·PageDown·상세링크 접근, 가로넘침 없음, 짧은 프리뷰 장식 containment, 빈 화면 가로/세로 초과0px 및 대시보드 API 요청 부재를 확인한다. 이미지/측정/로그는 `out/home-preview/scroll-diagnosis/`에 보존했다. Git 공백 검사 PASS. 운영DB/배포/원격push/서비스재시작은 수행하지 않았다.

스크롤 후속 커밋 시 main은 다른 세션이 `/Users/woolee/benchmark`에 체크아웃했고, 메인 전용 worktree는80be026의 detached HEAD인 상태였다. 공용 checkout/HEAD/인덱스/파일을 변경하지 않고 수정 커밋을 `feat/home-preview-json`에 보존했다. 이 스크롤 후속 변경의 main 반영은 아직 하지 않았다.
