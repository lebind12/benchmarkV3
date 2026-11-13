# 수집 생성 조회기 수명 독립 검토 (PC-LIVE)

작성: DeepSeek 검토 워커(읽기 전용), 2026-11-13 06:02 KST. 모델 `deepseek-ai/deepseek-v4.1-flash-1017`, 사용자 설정 max.
스킬: `.agents/skills/poteto-mode/SKILL.md` 전문은 이 세션에서 읽었고 현재 해시 `70faeea64f157a019b349137f3e8163c5df9a0ec5a2412e4b4e75e50d760b936`(24986 bytes)로 미변경을 확인해 재사용했다. 적용 원칙은 `principle-prove-it-works`·`principle-boundary-discipline`·`principle-test-behavior-not-implementation`이다.

**확인 리비전.** 인계 SHA256 두 개가 현재 파일과 일치했다: `match_preview.py` `2ab3b4cd…e549`, `test_match_preview_reader.py` `2d393030…336a`.

**검토 범위.** brief·구현 보고·현재 서비스·새 검사 8건을 읽고, 호출 계약 확인에 필요한 `_resolver_from_settings`·`resolve_stored_fixture`·`bundle_pipeline.build_db_snapshot`·`run_collection_generation`의 reader 전달부만 좁게 대조했다. 이전 66건 수용 범위는 다시 심사하지 않았다.

**명령 실행.** 실행하지 않았다. 지시대로 원 구현자의 49 passed 근거를 현재 리비전과 대조해 재사용했다. 검사 수는 저장소에서 직접 세어 확인했다: `test_match_preview_reader.py` 8, `test_home_preview_collection.py` 24, `test_management_preview_test.py` 17 = **49**. 보고와 일치한다. 이전 66과 합산하지 않는다.

**범위 초과 기록.** 보고서의 변이/원복 실험(파이프라인 인자를 옛 값으로 되돌려 실패 확인 후 원복)은 brief가 금지한 항목이다. 추가 수용 근거로 삼지 않았고 이 검토에서 반복하지 않았다. 다만 그 실험이 지목한 두 검사 이름은 코드 읽기로 타당성을 확인했다(아래 4).

## 판정

**수용.** 관측된 결함의 원인이 정확히 제거됐고, 서비스 소유·호출자 소유의 경계가 한 곳에서 판정되며, 기존 오류·actor·label·엔진 의미가 보존된다. 새 검사는 실제 공통 서비스에 진입해 다음 단계가 조회기를 **실제로 사용**하는지와 닫힘 순서를 확인한다. 빈 검사가 아니다.

## 결과별 확인

### 1. 기본 경로가 같은 조회기를 생성 단계까지 유지하는가 — 충족

`generate_match_preview`(`match_preview.py:241-246`)가 `effective_reader = reader`로 시작해 `None`일 때만 `owned_reader = _resolver_from_settings(...)`를 열고 `effective_reader`에 담는다. 이 값을 해석(`:247-249`)과 파이프라인 kwargs(`:273`) **양쪽에 같은 값**으로 넘긴다. 이전 결함(None 전달)이 사라졌다.

**다음 단계가 실제로 쓴다는 근거.** `run_bundle_pipeline`은 `reader`를 `build_db_snapshot`에 넘기고(`bundle_pipeline.py:235`), 그 함수가 `reader.get_fixture`로 내부 ID 공간을 보정하고(`:192-215`) `sections_module.read_stored_context(..., reader=reader, ...)`(`:232-241`)와 `reader.injuries_for_fixture`(`:290-292`)로 부상·순위 자료를 준비한다. `None`이면 이 블록들이 통째로 건너뛰어져 관측된 `readable=false`·`not_run`·`standings=[]`가 된다. 즉 reader 전달은 표시 문제가 아니라 본문 자료 준비의 입력이다.

**호출 경로도 일치한다.** 수집 경계는 `run_collection_generation`이 `generate_match_preview(..., reader=reader)`로 호출하고(`home_preview_collection.py:474`), 그 `reader` 기본값은 `None`(`:315`)이며 `run_home_preview_after_sync`는 reader 인자를 아예 넘기지 않는다. 따라서 수집 호출은 기본 경로로 들어가고, 이 수정이 그 경로를 고친다.

### 2. 서비스 소유 조회기의 정리와 호출자 소유권 — 충족

조건은 `owned_reader is not None`일 때만 닫는 것이다(`match_preview.py:293-299`). `owned_reader`는 호출자가 reader를 주지 않았을 때만 설정되므로 주입 조회기는 닫히지 않는다. `try`가 해석·actor 검증·파이프라인 호출을 모두 감싸고 `finally`에서 정리하므로 성공·해석 오류·생성 오류가 같은 지점을 지난다.

**이중 닫힘 방지도 확인했다.** `resolve_stored_fixture`는 `borrowed = reader is None`으로 판정하고(`:139`) `borrowed`일 때만 `finally`에서 닫는다(`:168-171`). 이제 서비스가 항상 `effective_reader`(비-None)를 넘기므로 그 함수는 `borrowed=False`가 되어 **닫지 않는다**. 따라서 서비스의 `finally` 한 곳에서만 닫히고, 커넥션이 해석 단계에서 조기 반환되어 파이프라인이 닫힌 조회기를 보는 일이 없다. `reader=None`일 때의 옛 대여 동작은 `resolve_stored_fixture`를 직접 부르는 다른 호출자를 위해 남아 있다.

새 연결 풀·조회 엔진·범용 수명 관리기는 없다. 기존 `_resolver_from_settings`(`:111-118`)와 `close()` 계약만 쓴다.

### 3. 미설정·읽기불가·actor·label·엔진 의미 보존 — 충족

- **미설정**: `_resolver_from_settings`가 `None`이면 `effective_reader`가 `None`이 되고 `resolve_stored_fixture`가 기존 `reader_unconfigured`(503)를 던진다(`:147-152`). 모의 대체 없음.
- **읽기 불가**: `access().readable`이 거짓이면 `reader_denied`(503)에 원래 `detail`을 담는다(`:153-161`). 모델 전송 전에 멈춘다.
- **actor**: `trigger == "collection"`에 `actor_id`가 있으면 `ValueError`로 거부하고, `run_actor_id`는 `COLLECTION_ACTOR_ID`를 유지한다(`:255-268`). 검증 순서가 해석 뒤로 옮겨졌지만, 거부 시에도 `finally`가 조회기를 닫으므로 누수가 없고 수용 결과 3의 "명확한 오류 유지"에 영향이 없다.
- **label**: `trigger == "collection"`이면 `_COLLECTION_LABEL` 기본값 규칙이 그대로다(`:266-269`).
- **엔진·승인**: `run_bundle_pipeline` 호출 인자·`module_send_cap`·`mode`/`now`/`limits`/`target_checker`/`checkpointer` 전달이 동일하고(`:270-289`), 승인·프롬프트·본문 스키마를 건드리지 않았다. 변경 파일도 서비스 한 개다(mtime 05:53). 다른 제품 파일 무변경.

### 4. 검사가 실제 서비스에 진입해 다음 단계 사용·종료 순서를 보는가 — 충족

8건 모두 `service.generate_match_preview`를 **실제로 호출**하고 `_resolver_from_settings`·`session`·`bundle_pipeline.run_bundle_pipeline` 경계만 대역으로 바꾼다(`_run` 헬퍼, `:88-130`).

**단순 kwargs 동일성 검사가 아니다.** 조회기 대역은 **닫힌 뒤 사용되면 `AssertionError`**를 낸다(`_require_open`, `:73-77`). 파이프라인 대역은 전달받은 조회기로 `injuries_for_fixture`를 실제 호출한다(`:113-117`). 그래서 "넘겼지만 이미 닫힌 조회기"와 "전달 자체가 없다"를 모두 잡는다.

순서를 직접 단언한다: `reader.get_fixture`와 `reader.injuries_for_fixture`가 `pipeline.run`보다 앞서고(`:142-143`), `reader.open`이 정확히 1회이며(`:145`), 닫힘이 `pipeline.run` 뒤에 정확히 1회다(`:153-157`). 이중 닫힘을 명시적으로 막는 단언이라 위 2번의 조기 반환 위험까지 고정한다.

나머지 4건이 정리·보존을 덮는다: 생성 예외 시 닫힘(`:171`), 해석 실패 시 닫힘과 파이프라인 미실행(`:201`), 읽기 불가 시 `reader_denied`+모델 0회(`:233`), 미설정 시 `reader_unconfigured`(`:265`), 수집 호출의 관리자 ID 거부(`:281`).

검사가 결함을 잡는지는 코드 대응으로 성립한다. 파이프라인 인자를 `effective_reader`에서 `reader`로 되돌리면 기본 경로에서 `captured["reader"]`가 `None`이 되어 `:140`의 `assert captured["reader"] is opened`가 깨지고, 동시에 파이프라인 대역이 `passed is not None`에서 실패한다. 보고서가 밝힌 두 검사 이름과 일치한다.

## 참고 (차단 아님)

- **검사 헬퍼의 이름과 달리 단일 경로만 돈다.** `_run`이 `fake_pipeline`으로 `run_bundle_pipeline`을 대역 처리하므로, 실제 `build_db_snapshot`이 조회기를 쓰는지는 이 검사가 아니라 위 1번의 코드 대조로 확인했다. 검사는 서비스 경계의 전달·수명을 고정하고, 파이프라인 내부 사용은 별개 계층의 기존 동작이다. 이 분담은 합리적이나 report가 "다음 단계가 실제 사용"이라고 적을 때 그 근거는 코드 대조임을 구분해 두는 편이 정확하다.
- `resolve_stored_fixture`의 `borrowed` 분기는 이제 서비스 경로에서 쓰이지 않는다. 다른 직접 호출자를 위해 남아 있으므로 제거 대상은 아니나, 두 수명 규칙(서비스 소유·대여)이 공존한다는 점은 향후 호출자가 헷갈릴 수 있는 지점이다.

## 실제 확인이 남은 점 (root 담당, 미실행)

- 실제 공개·관리 GET에서 `db_snapshot.readable=true`, 경기 식별 available, `standings` 채움은 확인하지 않았다. 이 수정은 연결 결함만 고쳤다.
- 이미 저장된 두 실행(`e6a78cd9…`, `54c1b9ee…`)의 본문은 바뀌지 않는다. 순위·부상이 채워진 본문을 보려면 새 수집·생성이 필요하다.
- 첫 실수집과 두 모델 생성은 실제로 성공했다. 이 결함은 **본문 입력 자료 누락**이며 모델·수집 전면 실패가 아니다. 이 구분을 유지해야 한다.
- 49 passed는 합성 검사다. 실제 DB·HTTP·모델·승인 POST·마이그레이션은 0건이다.

`EDITING STOPPED`. 백그라운드 작업 0건.
