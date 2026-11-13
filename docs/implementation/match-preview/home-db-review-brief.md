# HOME-DB-R 단일 연결 변경 한정 검토

독립 DeepSeek flash-1017, 사용자 설정 Max 유지. 읽기 전용 1회. 유일 작성 파일 docs/implementation/match-preview/home-db-single-connection-review.md. 제품/테스트/Plans/비밀파일 편집 금지. 모델·DB·HTTP·pytest/전체 suite·서버 조작 금지.

입력: HOME-DB-02(task_d8182b8fad2b) 완료 보고, 현재 파일, docs/superpowers/plans/2026-11-12-backend-read-connection-repair.md 및 home-db-final-runtime-brief.md. 원래 사용자 요구는 원래 DATABASE_URL 한 개의 원래 전체 권한 계정으로 기존 benchmark 기능과 preview를 통합하는 것이다. 새 제한 역할을 제안하지 않는다.

확인할 경계:
- core config의 원래 DATABASE_URL이 일반 조회/인증/preview reader·writer의 단일 자격 증명인지, 옛 PREVIEW DSN 우회가 실제로 사라졌는지.
- launcher가 원래 값을 덮어쓰지 않는지, 미설정 실패와 local auth/JWT·ADMIN/공개 GET 계약을 보존하는지.
- 기존 public 자료 무변경과 preview_dev 명시 저장·서로 다른 Base 보존. 구현자가 보고한 test_pipeline USER 로그인200 실패가 현재 ADMIN 생성 경로의 실제 회귀인지 소스상 경계만 판별(전체 검사 재실행 금지).
- 구현자 보고 24/67 검사의 현재 수용 기준 관련성. 전체 suite 추가 실행은 범위 이탈로 기록하되 재실행/일반 수리 확대 금지.
- runtime 후속의 최소 권한 부여 범위가 기존 원래 계정/preview_dev 기존 테이블뿐인지(실행 자체는 구현자). 비밀값이 출력/추적 파일에 들어가지 않는지.

현재 수정이 만드는 필수 경로의 실제 결함만 차단한다. 새 범용 설계/모든 caller 재심사/무관 기존 결함은 후속 참고로 남긴다. 원래 home publication 테이블 부재는 알려진 별도 이슈이며 이 검토에서 해결하지 않는다. 파일 위치·관측 근거와 결론을 간결하게 보고하고 종료한다.
