# HP-PHOTO 실제 홈 사진 누락 수정

먼저 `/Users/woolee/benchmark/.agents/skills/poteto-mode/SKILL.md` 전문을 읽고 적용한다. 같은 세션의 직접 읽기와 미변경 확인은 재사용한다. 실제 DeepSeek flash-1017 / max 유지.

HP-EVIDENCE는 인계 완료했고 PID9352 공개 GET에서 승인한 구성본 493ef4a9의 정확한 5섹션과 complete=true를 확인했다. 하지만 현재 수용 기준인 선수/부상 사진·팀 로고가 홈에서 빠지는 실제 결함을 root가 관측했다. 관리자 원본 실행 d96fe824의 section-results GET에는 선수 4명과 부상 2명의 photo_url/external_player_id/team_external_id가 모두 있지만 홈 document에서는 같은 값이 전부 null이다. 브라우저도 주목 선수 4명과 부상 2명 모두 '사진 없음', 저장본문 내 팀 로고는 2개뿐이다.

조사 단서: home_preview_document._id_context는 StructuredIdContext에 DisplayNameBridge 자체를 전달한다. 기존 관리자 get_section_results는 bridge.names 해석기를 전달한다. StructuredIdContext의 계약도 DisplayNameBridge.names를 요구한다. 이 차이를 우선 확인하고 최소 연결을 수정한다. 팀 범위와 선택된 구성본의 타 실행 섹션도 정확히 유지한다. 추정 ID나 하드코딩을 넣지 않는다.

제품 소유는 `app/services/home_preview_document.py`의 해당 연결, 검사 소유는 `tests/unit/test_home_preview_document.py`의 대표 1건, 보고서는 `docs/implementation/match-preview/home-photo-connection-report.md`만이다. HP-EVIDENCE 변경은 보존하며 승인/저장행/원문/모델/프론트/공용 렌더/Plans.md는 수정하지 않는다. 새 원문 생성·API·DB·서버·브라우저·외부 조회는 root가 담당하므로 워커는 실행하지 않는다.

수용 기준은 기존 해석기 경로를 재사용해 확인된 선수와 부상 사진/외부 팀 ID를 공개 투영까지 보존하고, 내부 ID는 여전히 제외하며, 이름-only 부상은 해당 경기 두 팀에 한정하는 것이다. 기존 무자료 처리와 요청 종료 연결 정리도 보존한다. 대표 검사는 잘못된 객체 연결일 때 사진이 사라지는 사용자 결과를 잡아야 한다. 최소 명령 `.venv/bin/python -m pytest tests/unit/test_home_preview_document.py -q`만 허용한다. 전체 회귀·기존 검토/참고 확대·새 실행 도구는 금지한다.

원인·변경·직접 검사·편집 종료/백그라운드 0을 보고하고 현재 배정 Task/Dispatch로 worker_done을 한 번 보낸다. 실제 공개 GET에서 사진 6개/팀 외부 ID와 브라우저 이미지를 확인하는 것은 root 담당이다. 같은 파일의 독립 검토자는 읽기만 하며 이번 수정의 별도 한정 확인은 인계 후 조정자가 전달한다.
