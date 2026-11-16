> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `ax` 워크트리의 `docs/ax/natural-language-search/production-runtime.md`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# 운영 읽기 경로·자료 버전 통합 요구

2026-10-29. 독립 BE 검토의 운영 설계 입력을 정리한 **구현 전 요구**다. 공개 endpoint를 추가하지 않는다. 현재 local mirror/실제 모델 component 검증은 운영 인수가 아니다. 정본 [실행 계획](plan.md) AX-R-5와 [공개 계약](../../spec/endpoints/ax-agentic-search.md)에 종속된다.

## 1. 공통 main과 스키마 선행 정합

현재 AX 기반과 `origin/main` 사이에는 공통 JWT·관리/홈·Supabase migration 등이 다르다. 원격 main의 커밋을 이 worktree에서 통합하고 공용 파일을 기존 구현으로 덮지 않는다. 같은 DDL을 Supabase CLI와 Alembic 독립 경로로 중복 적용하지 않는다. 신규 테이블은 SQLAlchemy 모델/읽기 mapping과 동기화하고 migration 적용·재실행/역방향 영향은 격리 PostgreSQL에서 검증한다.

## 2. 읽기 view와 세대 metadata

Supabase 원천 DB의 전용 search schema에서 최소 축구 컬럼만 노출한다. 새 복제 서비스·검색 Redis 캐시·공개 endpoint는 도입하지 않는다.

| 구성 | 요구 필드/의미 |
|---|---|
| search_entity_name | entity 종류/내부 ID/유효 외부 ID·원문/한글/짧은 이름·각 수정 시각 |
| search_player | player ID·번역 fallback한 검증된 표시명 |
| search_stat | player/team/league/season·goals/assists/minutes/appearances/yellow/red·updated_at, 원천 grain/NULL 유지 |
| search_league_scope | 활성/실제 현재·직전 저장 시즌·catalog/target 정책 일치와 관측 범위 |
| search_generation | 단조 증가 source generation·schema/policy version·변경 시각 |
| scope 수집 관측 | league/season/domain·유효한 수집 확인 시각·성공/부분/실패와 누락 근거 |

view와 서버 양쪽에서 활성 대회·실제 최신2시즌을 제한한다. 이름 조회가 원천 전체 entity를 다루더라도 통계 scope를 확대할 수 없다. 사용자/세션/refresh/worker 원문 로그·불필요한 JSON은 reader에 노출하지 않는다.

## 3. 원천 변경과 같은 transaction에서 세대 갱신

통계·entity/translation·활성/시즌/catalog/target 정책의 INSERT/UPDATE/DELETE와 generation 갱신이 원자적이어야 한다. 삭제·동일 시각 변경을 놓치는 MAX(updated_at)이나 워커 종료 로그 한 건은 대체 수단이 아니다. statement trigger 등은 격리 환경에서 lock/동시성 영향을 측정해 채택한다.

현재 daily-sync는 부분 commit하므로 완료 시점만 체크하면 중간 변경을 놓친다. 최초 운영 구현은 실행 중 generation이 바뀌면 안전한 재시도 안내/중단을 허용한다. 마지막 완성본만 원자 publish하는 versioned projection을 구현한 것으로 가장하지 않는다. 변경 빈도가 실제 가용성을 해치면 인수에서 측정하고 publication 구조를 별도 검토한다.

## 4. 불변 snapshot과 요청·대화·nonce

- 인증 후 짧은 READ ONLY/REPEATABLE READ에서 generation·이름·scope·통계/coverage를 함께 읽고 connection을 반환한다. 모델 대기 중 connection을 보유하지 않는다.
- source_generation, schema/definition/scope-policy version, 안정 dataset_version, 내용 checksum, loaded_at과 수집 확인 시각을 구별한다. 로컬 gzip hash 모드와 운영 generation 모드를 명시적으로 분리한다.
- 매 요청 진입 시 generation 확인, 변경 시 bounded 단일 reload 또는503. 실행 중 Dataset을 제자리 변경하지 않고 request에 고정한다.
- 각 SQL transaction과 최종 대화 commit 직전에 고정 generation/취소 상태를 확인한다. 서로 다른 세대 결과를 섞거나 유료 전체 실행을 자동 반복하지 않는다.
- 과거 대화/artifact/candidate뿐 아니라 **성공 nonce replay**도 새 generation 뒤에는 안전하게 만료시킨다. FE는 입력·읽기 전용 표시 이력을 보존하고 새 대화를 안내한다.
- cancel ledger는 data refresh와 구별해 이전 실행의 명시 취소를 잃지 않는다. reload·동시 요청·종료 cleanup과 예산은 bounded다.

## 5. 6시간 신선도

원천6시간+메모리6시간으로12시간 지연을 만들지 않는다. 새 generation은 다음 TTL까지 기다리지 않고 감지한다. 같은 원천을 reload했다고 수집 신선도 시계를 리셋하지 않는다. 과거 시즌 row의 오래된 updated_at만으로 전체 서비스를 stale 판정하지 않는다. scope의 유효한 수집 관측 시각·실패/부분·unknown을 별도로 사용한다.

기존 worker 로그에서 scope/영역 확인이 불가능하면 추정해 complete/fresh로 처리하지 않는다. 필요한 수집 관측을 기존 daily-sync 책임 안에 기록한다. 검색 요청이 워커/API-Football을 실행해서 보충하지 않는다.

## 6. 명시적 운영 모드와 권한

별도 opt-in `production_db_views` 모드를 사용한다. local host 검사를 풀거나 공통 쓰기 DATABASE_URL로 fallback하지 않는다. 지정 Supabase project/host/database·TLS와 전용 reader 접속을 검증한다. reader의 role flag뿐 아니라 membership·effective grants·원천/사용자 테이블 직접 접근·schema/view owner/RLS/security 설정까지 확인한다. 필요한 view SELECT만 허용하고 runtime은 role/view 생성·권한 변경을 하지 않는다.

고정 schema/search_path·READ ONLY·timeout/pool/행·byte·EXPLAIN 한도, 공통 JWT/활성 role을 유지한다. 운영에서 local auth proxy/lab authority fallback을 허용하지 않는다. 모델/reader 자원은 단일 앱 lifespan에서 정리한다.

검색 구성/권한 검증 실패는 검색을503으로 닫고 기존 일반 API·워커를 불필요하게 중단시키지 않는 방향으로 통합한다. health/readiness·로그는 비밀이나 내부 DSN을 노출하지 않는다. 구체 자원 수명주기/동시성·권한 검사 인터페이스는 내부 명세·격리 테스트에서 확정한다.

## 7. 필수 격리 인수

- shape·NULL/0·복수 소속 grain·2시즌/활성·시즌 전환, role/membership/grants와 view 누락 fail-closed.
- 로드 중/모델 대기 중/SQL 사이/최종 commit 직전 원천 변경 및 INSERT/UPDATE/DELETE/번역/정책 변경 감지.
- 실패/부분 sync의 freshness 오승격0, 5h59 원천 reload 후 신선도 재부여0, 과거 시즌 불필요 차단0.
- 신규 generation 후 과거 대화/nonce replay 차단·취소 유지·late commit0·모델 대기 중 연결 점유0.
- refresh 실패/동시 refresh/pool/대용량/종료, migration·모델/기존 일반 API·워커 영향 및 복구.

## 8. 실제 적용 경계

설계/코드/격리 migration 검증과 실제 운영 적용을 구분한다. 운영 role credential·설정/재시작·migration/배포는 최종 검토 가능한 변경과 복구 계획을 준비한 뒤 AGENTS.md의 명시 배포 요청 경계를 따른다. rollback은 우선 검색 비활성화·reader 차단이며 원천 축구 데이터를 보존한다. DDL 제거는 기존 앱 의존성을 확인한 별도 migration으로 수행한다.
