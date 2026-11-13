# PC-LIVE 조회기 수명 한정 확인

작업 전 `/Users/woolee/benchmark/.agents/skills/poteto-mode/SKILL.md` 전문을 읽고 적용한다. 같은 세션에서 직접 읽었고 미변경이면 해시 근거로 재사용한다. dsh-tui 실제 모델 `deepseek-ai/deepseek-v4.1-flash-1017`/max 유지. 하위 워커·모델 전환·새 조정 Run 없음.

독립 읽기 전용 검토다. 원 구현자와 다른 세션에서 `preview-collection-reader-brief.md`, `preview-collection-reader-report.md`, 현재 `app/services/match_preview.py`, 새 `tests/unit/test_match_preview_reader.py`만 우선 읽는다. 호출 계약에 필요한 인접 함수는 좁게 읽을 수 있으나 이전66건 수용 범위를 다시 심사하지 않는다.

인계 리비전: match_preview.py SHA256 `2ab3b4cdd155b013711335457d15a9ea5252ae4505b42fcfe5d47153c3b3e549`, test_match_preview_reader.py `2d393030720a22c00ab5a3d0e0fb2d339222de27106c4ab49c980713a0e8336a`. 구현자 직접 명령은 신규8+기존41=49 passed이며 이전66과 합산하지 않는다. 보고된 변이/원복 실험은 명세에서 금지했으므로 범위 초과이고 추가 수용 근거로 삼지 않는다. 현재 인계 코드가 effective_reader를 사용하는지 확인하고 이 실험을 반복하지 않는다.

관측된 결함은 기본 수집 호출에서 경기 ID 해석에만 임시 조회기를 쓰고 생성 파이프라인에는 reader=None을 전달해 수집된 경기·순위가 본문 입력에 빠지는 것이다. 첫실수집과 두 모델 생성은 실제 성공했으므로 이를 모델/수집 전면 실패라고 표현하지 않는다.

확인할 결과는 네 가지다. 기본 경로가 읽을 수 있는 같은 조회기를 생성 단계까지 유지하는가, 서비스 소유 조회기가 성공·해석/생성 예외에서 닫히는가, 주입 조회기는 호출자 소유로 남는가, 미설정/읽기불가·actor·label·기존 엔진 의미가 유지되는가. 검사가 실제 공통 서비스에 진입해 다음 단계의 조회 사용과 종료 순서를 확인하는지도 읽어 확인한다. 단순 객체 전달 여부만 보는 빈 검사면 근거 부족으로 보고한다.

제품·검사·설정·Plans.md 편집과 API/DB/모델/브라우저/서버 조작은 금지한다. 원 구현자의 직접 검사 통과 근거를 현재 리비전과 대조해 재사용한다. 새 코드/검사·변이 실험·전체 회귀·같은 명령 반복은 하지 않는다. 구체적 근거 부족이 있으면 그 범위만 보고하고 임의로 검사를 확대하지 않는다.

보고서 `docs/implementation/match-preview/preview-collection-reader-review.md`만 작성한다. 판정은 현재 범위의 재현된 결함/요구 위반/참고를 구분하고 실제 두 경기 자료 입력은 root의 재시험에 남긴다. EDITING STOPPED·백그라운드0으로 현재 Task/Dispatch에 한 번 보고하고 종료한다.
