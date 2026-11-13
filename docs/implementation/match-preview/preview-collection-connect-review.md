# 수집 연결 독립 검토 (PC-ACCEPT)

작성: DeepSeek 검토 워커(읽기 전용), 2026-11-13 04:30 KST. 모델 `deepseek-ai/deepseek-v4.1-flash-1017`, 사용자 설정 max.
스킬: `.agents/skills/poteto-mode/SKILL.md` 전문은 이 세션에서 읽었고 현재 해시 `70faeea64f157a019b349137f3e8163c5df9a0ec5a2412e4b4e75e50d760b936`(24986 bytes, 11-09 17:53)로 미변경을 확인해 재사용했다. 적용 원칙은 `principle-prove-it-works`·`principle-boundary-discipline`·`principle-test-behavior-not-implementation`이다.

검토 리비전: `home_preview_collection.py` `8005eb65…84bf`, `management_runs.py` `9fa1057e…9676`, `worker_runs.py` `1fbccfdd…b8f1`, 테스트 `56ca1b0e…11a5`, 보고서 `eaff88a7…bbb6`. 보고서의 후속 보완(04:20, 잠금·회차)까지 포함한 상태다.

**리비전 확인(04:20 보완 반영 완료).** 조정자가 갱신한 최신 SHA256과 현재 파일이 일치함을 직접 확인했다(`home_preview_collection.py` `8005eb65…84bf`, 테스트 `56ca1b0e…11a5`). 즉 이 검토는 회차·잠금 보완이 **이미 반영된 최신본**을 대상으로 했고, 아래 판정도 그 최신본에 대한 것이다. 회차 의미(`slot_time(now)` → `generation_due_at(kickoff)`)와 `pg_try_advisory_lock` 경기 잠금, 관리자 실행 제외는 최신본에서 확인했으며 **해결된 항목으로 본다**(아래 참고 3번). 최신본에 없는 결함은 지적하지 않는다.

## 판정

**수용 불가.** 현재 요구 위반 4건이 있다. 그중 1번은 수집 연결의 존재 목적(Q6)을 실제 기본 경로에서 무력화한다. 나머지 3건은 승인 정책·상위 예외 처리·실패 기록의 요구 위반이다. 근거 부족 1건(검사가 기본 배선을 덮지 않음), 참고 3건을 함께 적는다.

## 현재 요구 위반

### 1. preview 세션 팩토리 계약 불일치 — 모든 후보가 생성 전에 실패한다 (차단)

**위치.** `app/services/management_runs.py:699`가 `preview_session_factory=_preview_session_factory`를 넘기고, `:714-718`의 `_preview_session_factory()`는 `get_session_factory()`를 **반환**한다. `app/preview/db.py:67-70`의 `get_session_factory()`는 `sessionmaker[Session]` **인스턴스**를 돌려준다. 즉 이 함수를 한 번 호출하면 세션이 아니라 팩토리가 나온다.

`app/services/home_preview_collection.py:258`은 `preview_factory = preview_session_factory or _default_preview_factory`로 받고 `:278`·`:320`에서 `with preview_factory() as write_session:`을 쓴다. 여기서 얻는 값이 `sessionmaker` 인스턴스이므로 `with`가 성립하지 않는다.

**실제 호출 계약 확인.** 설치된 SQLAlchemy 2.0.36에서 `sessionmaker` 인스턴스는 `__enter__`를 갖지 않고 `with`에 `TypeError: 'sessionmaker' object does not support the context manager protocol`을 낸다. 반면 `db.SessionLocal`은 `sessionmaker` **인스턴스 자체**이므로 `with session_factory()`(`app/db.py:88` + 호출)는 `Session`을 내고 정상이다. 같은 이름의 인자 두 개가 서로 다른 단계의 계약을 갖는다. 이 확인은 저장소 모듈을 치환하지 않고 라이브러리 계약만 실행해 얻었다(제품 코드 수정·monkeypatch 0).

**귀결.** `:277-286`의 중복 조회 블록이 `TypeError`를 `except Exception`으로 잡아 `dedup_query_failed: TypeError`로 기록하고 `continue`한다. 따라서 **후보마다 생성이 시작되지 않고 실패로 기록**되며 `generated`는 항상 빈다. `:301-303`에서 `state`는 `failed`가 된다. `_generate_one`(`:320`)도 같은 팩토리를 쓰므로 도달하더라도 같은 지점에서 깨진다. `_approval_gate`(`:358`)도 `with session_factory()`로 같은 오류를 내 내부 `except`에 걸려 **항상 `state: unknown`**이 된다.

**사용자 영향.** 수집이 성공·부분 실패·실패로 끝나도 프리뷰가 새로 생기지 않는다. Q6("API 최신화가 실패해도 DB의 대상 경기로 생성한다")이 실제 기본 경로에서 성립하지 않고, 관리자 화면에는 프리뷰 실패만 쌓인다. 보고서 `:59-63`의 "preview_dev 세션으로 생성까지 도달한다"는 서술은 이 계약에서 성립하지 않는다.

**최소 수정 범위(구현은 하지 않음).** 두 인자 중 하나의 단계만 맞추면 된다. `management_runs`에서 `preview_session_factory`에 **팩토리 인스턴스**를 넘겨 `preview_factory()`가 `Session`을 내게 하거나, 래퍼를 유지하려면 모듈 쪽 호출을 `with preview_factory`(=이미 만든 팩토리)로 바꾼다. 한쪽만 고쳐야 하며 두 쪽을 동시에 바꾸면 다시 어긋난다. `_approval_gate`도 같은 팩토리를 쓰므로 함께 해소된다.

### 2. 상위 예외 종료가 프리뷰 생성에 도달하지 않는다

**위치.** `app/services/management_runs.py:564-575`의 훅은 `try`(`:431`) 블록 안, 정상 종료 직전에 있다. 상위 예외는 `:590-596`의 `except Exception`으로 빠지고 그 블록에는 훅 호출이 없다(`finally` `:597-604`에도 없다).

**사용자 영향.** API 키 미설정(`:433-434`), 클라이언트 생성 실패, 항목 루프에서 처리되지 않은 예외처럼 **수집 자체가 예외로 끝난 경우**에는 DB에 대상 경기가 남아 있어도 프리뷰를 시도하지 않는다. 배정문이 명시한 "정상 반환된 failed 결과뿐 아니라 실제 상위 예외 종료도 Q6 대상"을 충족하지 않는다. `worker_runs.py`도 같은 구조다(`:260-272`가 정상 `try` 안, 상위 `except`에는 훅 없음).

**최소 수정 범위.** 예외 종료 경로에서도 같은 훅을 한 번 호출하고, 그 호출의 예외가 원래 수집 실패 기록을 덮지 않게 감싼다. 훅 자체가 이미 예외를 흡수하므로 호출 위치 추가가 최소다.

### 3. 자동 생성에 승인 게이트가 없다

**위치.** `app/services/home_preview_collection.py`는 생성 전에 `admission_state`를 **판정에 쓰지 않는다**. `:304`의 `_approval_gate()`는 생성이 모두 끝난 뒤 사실만 기록한다. `generate_match_preview` → `run_bundle_pipeline` 경로에는 `admission` 참조가 0건이다(`bundle_pipeline.py`, `match_preview.py` 전수 grep).

**사용자 영향.** 승인된 섹션 워크플로우가 없거나 저장 버전이 현재 코드와 다른 상태에서도 자동 생성이 그대로 실행된다. 이는 원 brief `:48`(“승인된 실행 가능 버전이 없으면 분명한 건너뜀/실패 사유를 남기고 정상 승인 완료로 꾸미지 않는다”)과 `:24`(“관리자 시험 허용을 자동 생성 허용으로 확장하지 않는다”)를 충족하지 않는다. 모델 호출과 preview_dev 실행 행이 승인 정책과 무관하게 소비되고, 그 실행은 승인된 정책 실행과 구분되지 않는 `preview_runs` 행으로 남는다. `approval_gate`가 `not_ready`로 기록되기는 하나(그마저 위 1번 때문에 실제로는 `unknown`), 그 값은 **생성을 막지 않는다**.

**보고서와의 양립 여부.** 보고서 `:35-36`·`:189-191`은 “사실로만 남긴다”를 정책 보존으로 설명한다. 승인되지 않은 결과를 승인된 것으로 표시하지 않는다는 점은 지켰지만, brief가 요구한 “건너뜀/실패 사유를 남기고 진행하지 않는다”는 지키지 않았다. 두 서술은 **양립하지 않는다**. 최소 수정은 생성 루프 앞에 한 번 `admission_state`를 읽어 `ready`가 아니면 후보를 `skipped`로 남기고 생성을 시작하지 않는 것이다(사유에 `missing_approval`/`stale_approval` 전달). 관리자 시험 경로는 손대지 않는다.

### 4. 비예외 실패 생성 결과를 `generated`로 기록한다

**위치.** `app/services/home_preview_collection.py:339-346`의 `_generate_one`은 예외 없이 반환된 결과를 상태와 무관하게 `result["generated"]`에 넣는다. `BundlePipelineOutcome.status`는 필수 섹션 본문이 없을 때 `RunStatus.FAILED`가 될 수 있다(`app/preview/bundle_pipeline.py:1383-1390`).

**사용자 영향.** 필수 섹션을 만들지 못한 실행이 `generated` 목록에 들어가고 `result["failed"]`는 비며 `:301-303`의 `state`도 `failed`로 내려가지 않는다. 수집 결과 요약이 실패 실행을 생성 성공으로 센다. 항목의 `status` 값이 `failed`로 남아 있어 완전한 은폐는 아니지만, 배정문 4항이 지목한 “비예외 실패 상태를 정상 생성으로 기록하는지”에 해당한다. 최소 수정은 `outcome.status`가 성공이 아니면 `failed` 목록으로 보내고 사유를 남기는 분기 하나다.

## 근거 부족

- **검사가 기본 배선을 덮지 않는다.** 테스트는 전부 `preview_session_factory=lambda: _Session(...)` 형태다(`tests/unit/test_home_preview_collection.py:108·209·280·307·322·379·416`). `_Session`은 `__enter__`를 가진 **세션 대역**이라 `preview_factory()`가 곧바로 세션을 내고 `with`가 성립한다. 실제 팩토리는 `sessionmaker`를 내므로 한 단계 다르다. 그래서 위 1번을 14건이 잡지 못한다. `test_collection_hook_passes_a_preview_session_factory`(`:334-357`)도 두 인자가 서로 다른 객체인지만 확인하고 반환 단계는 보지 않는다. 승인 게이트(3번)와 비예외 실패(4번)도 대역이 없어 고정되지 않는다.
- 보고서 `:91-95`·`:198-199`의 변이 확인은 회차·격리·잠금에 대한 것이고 위 항목들은 대상이 아니다.
- 검사 개수 14는 실제로 통과한다(아래 실행 근거). 다만 그 수는 수용 기준 충족의 근거가 아니다.

## 참고 (차단 아님)

- `_AdvisoryFixtureLock.__enter__`(`:163-172`)는 PostgreSQL이 아닐 때뿐 아니라 `pg_try_advisory_lock` 호출이 **실제 오류**로 실패해도 `acquired=True`로 진행한다. 잠금 실패를 중복 방지 해제로 해석하지 않으려면 오류 종류를 구분하면 좋다. 실제 동시 진입 확인은 root 몫이다.
- `_already_generated`(`:97-117`)는 `cancelled` 실행도 중복으로 본다. 자동 재시도를 만들지 않는다는 결정과 일관되지만, 취소된 회차를 다시 시도할지 여부는 정책 미정이다.
- **회차 의미는 해결됨.** `_round_key`가 `generation_due_at(kickoff)`를 쓰고(과거 `slot_time(now)` 아님) 관리자 실행은 label이 달라 자동 중복에서 제외된다. 표시 팀명이 label에 들어가지만 회차·경기 ID가 앞에 있어 판정 키로 충분하다. `test_round_key_uses_the_legacy_kickoff_due_slot_not_wall_clock`이 두 helper가 실제로 갈리는 시각(12:00 KST: due=06:00, slot=12:00)을 골라 고정한다. **이 항목은 요구 위반이 아니며 해결된 것으로 본다.**
- 잠금 미획득 시 생성하지 않고 `generation_in_progress_elsewhere`/`generation_lock_unavailable`로 구분하는 처리와, 생성 호출이 잠금 안에서 일어남을 순서로 확인하는 검사도 최신본에 있다. 다만 잠금 대역 검사는 실제 PostgreSQL 동시 진입의 근거가 아니므로 그 확인은 root 몫으로 남는다.

## 실행·범위 준수

- 지정 명령을 **2회** 실행했다. 1차는 최초 검토 시(같은 리비전, 14 passed), 2차는 조정자가 리비전 갱신 메일에서 이 리비전 기준 1회를 허용해 실행한 확인이다(14 passed, 0.68s). 같은 리비전에 대한 동일 명령이므로 두 결과는 같은 근거이며, 보고서의 11 passed는 후속 보완 이전 수치이고 현재는 14다. 이 중복 실행은 엄격히는 "1회" 한도에 걸치므로 사실대로 적는다.
- 그 밖에 DB·외부 HTTP·모델·브라우저·운영 수집·서버 재시작·마이그레이션·승인 POST를 실행하지 않았다. 새 테스트·재현 스크립트를 작성하지 않았고 제품 모듈을 메모리에서 치환하지 않았다.
- 제품·테스트·설정·Plans.md를 편집하지 않았다. 이 보고서만 작성했다. 백그라운드 작업 0건.
- 14 passed를 실제 수집·모델·DB·홈 표시 성공으로 해석하지 않았다. 위 판정은 파일·행·실제 호출 계약 대조에 근거한다.

`EDITING STOPPED`. 백그라운드 작업 0건.

## 지적 1~4 수정 확인 (2026-11-13 05:05)

한정 수정 확인이다. 위 본문의 "수용 불가" 판정은 **수정 전 리비전**에 대한 것이고, 아래는 현재 리비전에 대한 재판정이다.

**확인 리비전.** 조정자가 제시한 SHA256과 현재 파일이 모두 일치했다. `home_preview_collection.py` `fedb1953…8524`, `management_runs.py` `4b22c0b9…a5d3`, `worker_runs.py` `06f910cd…a7df`, 테스트 `6fef6651…3dc2`. 스킬 `poteto-mode/SKILL.md` 해시 `70faeea6…b936`(24986 bytes)도 미변경이라 기존 읽기를 재사용했다.

**실행.** `.venv/bin/python -m pytest tests/unit/test_home_preview_collection.py -q` → **22 passed (0.65s)**. 이전 14·19와 합산하지 않는다. 이 22건은 합성 검사이며 실제 수집·DB·모델 성공 근거가 아니다.

### 지적 1 — preview 팩토리 계약: 해결

`home_preview_collection.preview_session_factory()`(`:193-207`)가 `get_session_factory()()`로 maker를 **한 번 더 호출**해 `Session`을 낸다. docstring이 이전 실패(인스턴스를 그대로 넘기면 `with`가 `TypeError`)를 근거로 남긴다. `management_runs`의 별도 wrapper는 삭제되고 같은 정의를 import한다(`:703-716`, `_preview_session_factory` grep 0건). `_default_preview_factory`는 같은 함수 별칭이다(`:211`). 이제 `preview_factory()`가 `app.db.SessionLocal`과 같은 단계이므로 `with preview_factory()`가 성립한다. 생성 쓰기(`:361`)와 승인 조회(`:417`)가 같은 계약을 쓴다.

검사 `test_preview_session_factory_calls_the_maker_so_with_gets_a_session`이 maker 대역으로 "부르면 세션이 나온다"를 고정하고, `test_default_preview_factory_is_the_same_contract`가 별칭 동일성을 고정한다. **검토 지적의 근본 원인이 제거됐다.**

### 지적 2 — 상위 예외 종료: 해결

`management_runs`: `preview_started`를 `try` **밖**(`:432`)에서 초기화하고 정상 경로에서 `True`(`:567`), 예외 경로는 거짓일 때만 훅 호출(`:603-610`). 결과는 `payload["home_preview"]`에만 쓰고 `status`·`stage`·로그를 건드리지 않는다. 훅 호출은 내부 `try/except`로 감싸 원래 오류를 덮지 않는다. `worker_runs`도 같은 형태이며 `preview_started`를 `try` 밖(`:234`)에 둬 조기 예외의 `UnboundLocalError` 위험을 없앴다(`:293-306`).

세 검사가 **실제 진입점**을 호출한다. `test_execute_run_top_level_exception_still_calls_the_preview_hook`은 `mr.execute_run`을, `test_daily_sync_top_level_exception_calls_the_preview_hook`은 `wr.start_daily_sync_run`을 직접 부르고 외부 경계만 대역으로 바꾼다. 후자는 `run.status == "failed"`, `"sync exploded" in run.error`, 훅 1회·`collection_status == "failed"`, `home_preview`가 별도 키에 남음을 단언한다. `test_execute_run_normal_path_does_not_call_the_hook_twice`가 `calls == 1`로 중복 호출 방지를 고정한다. 명시 취소는 기존 `SyncCancelled` 경로로 빠져 훅에 도달하지 않는다(정상 경로 블록 유지).

### 지적 3 — 승인 게이트: 해결

생성 루프 **앞**에서 `gate = (admission or _admission)(preview_factory)`(`:279`)를 한 번 판정하고, `ready`가 아니면 후보를 `skipped`로 남기고 `state: skipped`로 반환한다(`:281-301`). `not_ready`는 `approval_not_ready`에 `missing_approval`/`stale_approval`을 항목별로 전달하고, `unknown`은 `approval_query_failed`로 승인을 가정하지 않는다. 생성 호출 전에 반환하므로 모델·preview_dev 쓰기가 소비되지 않는다.

관리자 경로는 손대지 않았다. `match_preview`의 `trigger='admin'` 서술·`bundle_pipeline`의 `admission` 참조 0건이 그대로이고, `approvals.py`(mtime 02:31)·`pipeline.py`(03:36)도 이번 창에서 무변경이다. 승인 버전 계산과 승인 행은 그대로다.

검사 두 건이 생성 0건·사유·목록 전달을 고정한다. 게이트 대역은 주입된 것이고 실제 승인 행을 읽은 근거가 아니라는 점은 보고서대로 미확인으로 남는다.

### 지적 4 — 비예외 FAILED: 해결

`_generate_one`(`:380-397`)이 실제 `RunStatus`로 판정한다(`:28` import). `SUCCEEDED`가 아니면 `failed`에 `run_id`·`reason: generation_status_<값>`·`detail`을 남기고 `generated`에 넣지 않으며 `return True`로 다음 경기를 계속한다. `test_non_exception_failed_outcome_is_recorded_as_failed_not_generated`가 두 경기 모두 failed·generated 빔·다음 경기 계속·`state == "failed"`를 고정하고, 대역이 문자열 흉내 대신 실제 enum을 쓴다.

### 참고 (차단 아님)

`_generate_one`은 `status is None`(결과 객체에 status 속성이 없는 경우)이면 성공으로 본다(`:384`). 실제 `BundlePipelineOutcome`은 `status: RunStatus`를 필수 필드로 가지므로(`bundle_pipeline.py:127`) 현재 생성기에서는 발생하지 않는다. 요구 위반이 아니라 계약을 느슨하게 읽은 여유분이며, 이번 수정이 만든 것도 아니다.

### 이번 수정이 만든 직접 회귀

없다. 회차(`generation_due_at`)·경기별 advisory lock·실패 격리·관리자 실행 제외는 그대로이고 관련 검사도 22건 안에서 함께 통과한다. 새로 생긴 필수 조건 실패는 발견하지 못했다.

### 실제 연동 미확인 (변동 없음)

실제 운영 수집·모델 호출·preview_dev 실쓰기·advisory lock 동시 진입·승인 `ready` 상태에서의 자동 생성과 홈 공개는 여전히 미확인이다. 22 passed는 그 근거가 아니다.

`EDITING STOPPED`. 백그라운드 작업 0건.
