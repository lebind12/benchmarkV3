# HP-PHOTO 한정 수정 확인

`/Users/woolee/benchmark/.agents/skills/poteto-mode/SKILL.md` 전문을 읽고 적용한다. 같은 세션의 실제 읽기와 미변경 확인은 재사용한다. 실제 모델 DeepSeek flash-1017 / max를 유지한다.

별도 실제 홈 확인에서 관리자에는 있던 사진6개와 팀 외부 ID가 홈에서 null인 것을 재현했고, 원 구현자가 `home_preview_document._id_context`의 의존성 연결 한 줄을 수정했다. `home-photo-connection-brief.md`, `home-photo-connection-report.md`, 해당 함수 변경, `tests/unit/test_home_preview_document.py`의 새 대표 검사만 읽는다. 이전 HP-EVIDENCE와 홈 전체 검토는 반복하지 않는다.

확인 기준: 기존 StructuredIdContext가 요구하는 이름 해석기를 전달하며 팀 범위/요청 종료 정리/내부 ID 비공개와 승인 경로가 보존되는지, 새 검사가 실제 누락 원인을 잡는지 확인한다. 구현자의 16 passed와 잘못 연결했을 때 실패한 근거를 대조한다. 코드 읽기로 충분하므로 검사 재실행·추가 합성 호출/재현 코드 작성·API/DB/브라우저·서버·메일 탐색·하위 워커는 하지 않는다. root가 실제 GET과 이미지 로드를 병렬 확인한다.

제품/검사 파일은 읽기 전용이고 `docs/implementation/match-preview/home-photo-connection-review.md`만 작성한다. 참고는 차단하지 않는다. 판정과 코드 근거·실행0·편집종료/백그라운드0을 현재 배정으로 worker_done 한 번만 보내고 idle로 돌아간다.
