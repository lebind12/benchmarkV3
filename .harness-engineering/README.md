# benchmark 하네스 개선 기록

이 디렉터리는 단일 프로젝트의 하네스 개선을 위한 관찰·진단·후보 비교·사용자 결정·버전 이력을 저장한다. 활성 역할은 `.codex/agents/`, 범위 설정은 `.harness/config.json`, 실행은 `scripts/harness-improve.sh`다.

- `inspector/`, `optimizer/`: 역할 안내
- `schemas/`: 개선 입력과 상태 검증
- CLI가 생성하는 `observations`, 제안별 자료와 평가/이력: 실제 파일 배치는 실행 명세 참조

일반 서비스 작업의 `work-flow` 상태와 구분하며 과거 승인을 덮어쓰지 않는다. 승인 JSON에 사용자의 실제 확인이 없으면 적용 권한이 생기지 않는다. 승인 전 후보와 테스트 로그는 공개 자료가 아니다.
