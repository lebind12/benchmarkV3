# 메인 프리뷰 저장 구조

SQLAlchemy `app/models/home_preview.py`와 Supabase CLI migration `20261024235328_home_preview_storage.sql`이 같은 구조를 정의한다. 기존 Alembic baseline의 fixture/league/target/team을 재사용하고 변경하지 않는다. 관리 스키마 이후 Alembic bridge `0018_home_preview_storage`로 연결한다. 2026-10-26 사용자 승인으로 운영 Supabase에도 적용했고 컬럼·타입·제약·RLS 및 조회를 검증했다. 증거는 `docs/features/home-preview-production-db-verification.json`과 `home-preview-merge.verification.md`다.

| 테이블 | 책임·주요 제약 |
|---|---|
| home_preview_snapshot | 검증한 입력·원문 확인 metadata, as_of, fixture/fingerprint unique |
| home_preview_version | 불변 JSON, snapshot FK, nullable generated_at, fixture/fingerprint unique |
| home_preview_publication | fixture PK, 현재 version pointer·identity·refresh state·마지막 시도 시각 |
| home_preview_attempt | fixture/6시간 slot unique, owner UUID·상태·lease 시각·누적 usage·정제 reason |

모든 fixture FK는 cascade, version pointer 삭제는 SET NULL이다. 신규 테이블 RLS를 켜고 공개 직접 접근 policy는 추가하지 않는다. 공개 API는 서버 DB 연결로 검증된 응답만 제공한다. snapshot payload에는 preview·verification·generation의 model/generation_version/schema_version이 있고 비공개 metadata를 공개 envelope에 섞지 않는다.

공개 pointer는 유효성 검사를 마친 version과 같은 트랜잭션에서 전환한다. 실패/시간 초과/킥오프 통과/경기 identity 변경/이전보다 자료 손실 시 이전 유효본과 원래 시각을 보존한다. 1200초 실행 lease와 owner 검사를 통해 소유권을 잃은 실행의 게시를 차단한다. facts-only는 generated_at=null이다.

정리 CLI는 기본 dry-run이다. 알려진 target 시즌을 current_season 이하로 제한한 최신 2시즌 밖의 홈 전용 네 테이블만 정리한다. current_season이 불명확하면 보존하고 현재 보관 시즌의 비활성 리그도 삭제하지 않는다. fixture/team/league/번역은 정리 대상이 아니다. FK cascade·rollback·실패 보존·모델/DDL 제약·실제 삭제 범위는 격리 schema 테스트에서 확인했다.
