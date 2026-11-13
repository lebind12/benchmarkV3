# HOME-LIST-01: 프리뷰 저장소 부재와 추천 경기 목록 분리

사용자 목표: 원래 홈 추천 경기는 비로그인 사용자도 볼 수 있고, 프리뷰 미생성 때문에 경기 목록 자체가 실패해서는 안 된다. root가 단일 원래 DATABASE_URL로 서버를 재시작했다. health200, 관리자 무인증401, 프론트 경유 home/recommendations503을 확인했다. 기존 public의 home_preview_publication/version은 대상 DB에 없고, 현재 recommendations가 각 경기 read_preview를 호출해 그 테이블을 필수 조회한다. 테이블/프리뷰 생성은 이번 범위가 아니다.

담당: 실제 DeepSeek flash-1017 Max 구현 워커 1명. app/services/home_preview.py, 필요할 때 app/api/v1/home_preview.py, 이 경계의 기존 직접 검사 파일만 소유. 다른 코드/프론트/설정/Plans는 편집하지 않는다. 다른 HOME-DB 워커의 변경은 보존한다.

작업:
1. 새 런처와 같은 0600 설정을 사용해 원래 서비스 조회를 READ ONLY로 1회 실행하고 실제 첫 오류 종류/SQLSTATE/대상 테이블을 값 비출력으로 확인한다. 예상과 다르면 수정 전에 보고한다. 기존 비밀값·계정·운영 행을 출력하지 않는다.
2. 실제 경기 조회가 정상이고 알려진 프리뷰 publication/version 저장소만 없는 경우, 추천 목록과 실제 경기 식별은 계속 반환하고 해당 프리뷰는 기존 응답 계약의 미제공 상태로 표시한다. 없는 본문/승인/스코어를 만들지 않는다. 실제 경기/DB 연결 오류·권한 오류·다른 SQL 오류를 빈 성공 응답으로 숨기지 않는다. PostgreSQL 오류 뒤 같은 세션의 후속 조회도 정상이어야 한다.
3. prematch도 실제 경기 존재 확인 후 같은 미제공 계약을 재사용하며, 없는 경기404와 정상 저장된 프리뷰 제공 경로를 유지한다. 운영 테이블 생성/마이그레이션/public 쓰기/자동 생성/발행 없음. HOME_PREVIEW_ENABLED=false로 기존 저장본문까지 숨기는 우회는 하지 않는다.
4. 현재 관측 경계를 검증할 기존 대표 검사 1건을 보강하고 관련 직접 검사만 1회 실행한다. DB 테스트는 기존 안전 가드가 있는 루프백 *_test만; 운영 DB에 DDL/pytest/쓰기 탐침 금지. 광범위 suite·커버리지 목표·새 검증 도구 금지.

완료 조건: 같은 원래 DB에서 기존 추천 정책/대진/개수 보존, 공개 GET200·추천 경기 비어 있지 않음(실제 원천 데이터 기준), 프리뷰는 미제공 상태, paid0·기존 데이터 무변경. 서버 재시작은 root 담당이므로 코드 완료 후 직접 서비스 읽기로 확인해 인계. 정확한 변경 파일/대표 검사/실제 오류와 읽기 결과를 간단히 보고하고 EDITING STOPPED. 사진·디자인·홈에 새 프리뷰 연결/수집 연결로 확대하지 않는다.

## 실측 후 소유 범위 보완

작업 폴더에서 삭제된 tracked 계약 파일 때문에 실제 GET이 FileNotFoundError로 실패함을 관측했다. 조회에 필요한 docs/spec/schemas/home-preview-recommendations.schema.json, home-preview-response.schema.json, home-preview-payload.schema.json 세 파일만 HEAD 원문 그대로 worktree에 복원하도록 root가 승인했다(msg_e60a8e68319b). 다른 세 파일·디렉터리 전체 복원·스테이징·스키마 내용 변경은 제외한다. 복원 전후 blob 동일성과 기존 실제 GET 200/200/404를 1회 확인하고 종료한다. 전체 unit 검사 재실행은 하지 않는다.
