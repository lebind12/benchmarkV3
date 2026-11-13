# 수집 종료와 기존 프리뷰 생성 연결 (PC-CONNECT)

작성: DeepSeek 구현 워커, 2026-11-13. 실행기 `dsh-tui`, 모델 `deepseek-ai/deepseek-v4.1-flash-1017`, 추론 강도 `max`(사용자 설정 유지). 하위 워커·모델 전환 없음.

## 목표 재확인

사용자 확정 Q6의 요구는 **API 최신화가 실패해도 DB에 남은 대상 경기로 프리뷰 생성을 시도**하는 것이다. 이전 구현은 수집이 전체 `succeeded`일 때만 훅을 호출했고, 그 훅은 옛 `ProductionPreviewGenerator` 경로를 썼다. 두 가지를 이번에 바꿨다.

## 원인

두 곳이 함께 막고 있었다.

1. `app/services/management_runs.py`의 종료 경로가 `payload["status"] == "succeeded"`일 때만
   `run_home_preview_after_sync()`를 호출했다. 부분 실패(`partial_failed`)·실패(`failed`)에는
   생성 시도를 아예 하지 않았다.
2. `run_home_preview_after_sync()`가 `run_cycle(db.SessionLocal, execute=True)`를 호출했고,
   `run_cycle`은 옛 `ProductionPreviewGenerator`/`process_fixture`를 사용했다. 관리자 경로가
   쓰는 단일 서비스 `generate_match_preview()`와 다른 엔진이었다.

추가로 확인한 사실: 자동 후보·회차 중복·경기별 격리는 새 서비스에 자체 구현돼 있지 않았다.
그래서 수집 호출 경계에서 그 셋을 담당하도록 했다.

## 변경

### 새 수집 경계 모듈 `app/services/home_preview_collection.py`

- `collect_candidates()`: 기존 정책 그대로 NS·`now < kickoff <= now+6h`, 우선순위·킥오프·외부
  경기 ID 순. **성공한 리그로 후보를 제한하지 않는다.**
- `run_collection_generation()`: 수집 원래 상태를 **보존**하고 생성 결과를 별도로 돌려준다.
  경기마다 자기 세션을 열어 한 경기의 예외가 다음 경기를 막지 않는다. `cancelled()`가 참이면
  새 생성을 시작하지 않는다.
- 회차 중복: 실행 label에 `slot_time` 기반 회차 식별자를 넣어, 같은 자동 회차만 중복으로 잡는다.
  저장 구조는 기존 `preview_runs`를 읽기만 하고 **새 표·마이그레이션을 만들지 않았다.**
- 모델 transport가 없으면 모의로 대체하지 않고 `model_transport_unconfigured` 사유를 남긴다.
- 승인 상태(`admission_state`)는 **사실로만** 결과에 남긴다. 자동 생성 허용/불허를 이 값으로
  뒤집지 않는다(승인 정책 보존).

### `app/services/management_runs.py`

- 훅 조건을 `succeeded` 단독에서 `home_preview_enabled`로 바꿔 **성공·부분 실패·실패 모두**
  시도한다. 명시 취소는 `SyncCancelled` 경로에서 훅 이전에 빠져나가고, 처리 중 취소도
  `_cancel_requested()`로 전달되어 새 생성을 시작하지 않는다.
- `run_home_preview_after_sync(collection_status=..., cancelled=...)`가 원래 수집 상태를 받아
  경계로 넘긴다. 생성 실패는 예외를 밖으로 던지지 않고 `state: failed` 결과로 남겨 **수집
  결과를 덮지 않는다.**

### `app/services/worker_runs.py`

- 보조 수집 진입점도 같은 함수를 쓰도록 최소 변경. `result.has_errors`여도 생성하며
  `collection_status`를 `partial_failed`/`succeeded`로 넘긴다.

### `app/services/match_preview.py`

**변경 없음.** 이미 `trigger="collection"`, `actor_id=None`(시스템 호출, 관리자 ID 위장 없음)을
지원하고 있었다. 필요한 최소 변경이 없어 손대지 않았다.

## 확인한 실행 경계

- 생성은 관리자와 **같은** `generate_match_preview()` → `run_bundle_pipeline()` 경로를 쓴다.
  모듈별 최대 3회 재시도는 `RunBudget.for_generation()`이 그대로 소유한다.
- 후보·경기 자료는 공개 스키마 세션(`db.SessionLocal`)으로 읽고, **프리뷰 실행 기록과 생성
  쓰기는 `preview_dev` 세션**(`app.preview.db.get_session_factory`)으로 한다. 두 세션을 섞지
  않는다. 이 분리는 구현 중 발견해 고쳤다(처음에는 한 팩토리로 쓰고 있었다).
- `run_bundle_pipeline`에는 승인 게이트가 없다는 것을 코드로 확인했다. 그래서 이 경계는
  승인을 우회하지도, 자동 승인하지도 않는다. 승인 상태는 결과에 사실로만 기록된다.
- 홈 최신 선택(`home_preview_document.read_document`)은 `PreviewRun`을 `fixture_id`로 읽는다.
  수집 생성이 남기는 실행도 같은 표에 저장되므로 같은 후보가 된다(코드 계약으로 확인).

## 검사

`.venv/bin/python -m pytest tests/unit/test_home_preview_collection.py -q` → **11 passed**

**합성 검사다.** 생성기는 대역(`_Recorder`)이고 실제 모델·검색·API·DB를 호출하지 않는다.
이 통과를 실제 생성 성공·저장 성공·운영 수집 연동 확인으로 인용하지 않는다.

검사 이유와 실패 시 사용자 영향:

| 검사 | 이유 / 사용자 영향 |
|---|---|
| `test_collection_failure_still_generates_from_db_and_preserves_collection_status` | 수집 실패 시 생성하지 않으면 DB 자료가 있어도 홈 문서가 안 생긴다(Q6) |
| `test_one_fixture_failure_does_not_stop_the_next_fixture` | A 실패로 B가 멈추면 표시 가능한 문서가 줄고 원인이 가려진다 |
| `test_same_automatic_slot_is_not_generated_twice` | 같은 회차 중복 실행은 같은 경기에 실행이 겹친다 |
| `test_existing_admin_document_does_not_block_collection_generation` | 관리자 문서 존재로 생성을 건너뛰면 최신본 정책(Q7)과 어긋난다 |
| `test_cancellation_does_not_start_generation` / `..._mid_cycle_...` | 사용자가 멈춘 작업이 계속된다 |
| `test_missing_model_transport_does_not_generate_or_fake_success` | 모의로 대체하면 실제 생성으로 오인된다 |
| `test_cycle_limit_defers_the_rest_without_dropping_them` | 후보가 유실된다 |
| `test_collection_label_carries_the_slot_...` | 회차가 없으면 첫 생성 뒤 자동 생성이 영구히 멈춘다 |
| `test_same_cycle_second_call_is_skipped_by_existing_slot_label` | 같은 회차 재호출이 중복 실행된다 |
| `test_collection_hook_passes_a_preview_session_factory` | 공개 세션으로 생성하면 저장이 실패해 홈에 문서가 안 생긴다 |

검사가 실제 회귀를 잡는지도 확인했다.

- 수집 실패 시 생성을 건너뛰는 옛 조건을 넣으면 5건이 실패한다.
- 경기별 예외 격리를 없애면 `..._does_not_stop_the_next_fixture`가 실패한다.
- 되돌린 뒤 11 passed로 복귀한다.

## 적용 원칙이 바꾼 결정

`poteto-mode/SKILL.md` 전문은 이 세션에서 읽었고 해시 `70faeea6...b936`(24986 bytes)로 미변경을
확인해 재사용했다. 이번 작업에서 `principle-fix-root-causes`와 `principle-laziness-protocol`을 읽었다.

- **Fix Root Causes.** 훅이 옛 생성기를 부르는 표면 증상만 고치지 않고, 생성 진입점을 단일
  서비스로 바꾸고 훅 조건까지 함께 바꿨다. 그래서 실패 시 미호출과 옛 엔진 호출이 동시에 사라졌다.
- **Laziness Protocol.** 회차 중복을 위해 새 기록 구조를 만들지 않고 `preview_runs.label`에
  회차를 넣어 기존 표를 읽는 방식으로 끝냈다. 모델·마이그레이션 소유권을 요청하지 않아도 됐다.
- **Boundary Discipline.** 후보·회차·격리를 수집 경계 한 모듈에 모으고 `match_preview.py`는
  손대지 않았다.

## 구현 중 스스로 잡은 결함

1. 회차를 label에 넣지 않아 **첫 생성 뒤 모든 회차가 중복으로 막히는** 상태였다. 넣어 고쳤다.
2. 취소 확인을 `tracker.check_cancelled()`로 그대로 넘겨, 취소가 프리뷰 실패로 기록될 수 있었다.
   비예외 플래그로 바꿨다.
3. 공개 세션 하나로 생성까지 쓰려 해 preview_dev 저장이 실패할 수 있었다. 세션을 분리했다.

## 남은 항목

- **실제 운영 수집은 실행하지 않았다.** 이 연결이 실제 수집 종료에서 동작하는지는 실수집
  연동 확인이며 미확인이다.
- 생성기는 모의였다. 실제 모델 호출·실제 preview_dev 저장·홈 화면 표시는 이 검사의 근거가 아니다.
- 승인 기록이 비어 있는 상태에서 자동 생성물이 공개되지 않는 것은 의도된 기존 정책이다.
  승인 상태가 갖춰졌을 때의 실제 공개는 별도 확인 대상이다.
- `run_cycle`(옛 경로)은 CLI(`__main__.py`)에 남아 있다. 수집 훅에서는 더 이상 쓰지 않지만,
  CLI 직접 호출 경로를 제거·통합하는 일은 이번 소유 범위 밖이라 손대지 않았다.

## 변경 파일

- `app/services/home_preview_collection.py` (신규)
- `app/services/management_runs.py`
- `app/services/worker_runs.py`
- `tests/unit/test_home_preview_collection.py` (신규)
- `docs/implementation/match-preview/preview-collection-connect-report.md` (이 문서)

`app/services/match_preview.py`는 변경하지 않았다. `app/preview/models.py`·마이그레이션·프론트·
공용 렌더·홈 조회·프롬프트·원문·승인 행·Plans.md도 무변경이다.

`EDITING STOPPED`. 백그라운드 작업 0건.

## 후속 보완: 중복 방지 4조건 (2026-11-13 04:20)

조정자가 후속으로 네 조건을 요구했다. 조회 필드 존재만으로 중복 방지가 충족됐다고 보지
말라는 지적이 맞았고, **조건 2는 실제 결함이었다.** 나머지는 근거가 없었으므로 추가했다.

### 1. 관리자 실행은 자동 중복에서 제외된다

자동 중복 조회는 `preview_runs.fixture_id` + **자동 회차 label**로만 한다. label은 수집
경계가 만든 실행에만 붙고, 관리자 실행은 `정보 원문 프리뷰 · live` 형태의 다른 label을
쓴다. 그래서 관리자 문서가 있어도 자동 생성이 건너뛰지 않는다(사용자 확정 Q7).
`test_administrator_run_is_not_counted_as_an_automatic_duplicate`로 고정했다.

### 2. 회차 의미 — **수정한 실제 결함**

처음 구현은 회차를 `slot_time(now)`(실행 시각의 KST 6시간 bucket)로 만들었다. 기존
생성 파이프라인의 회차는 `generation_due_at(kickoff)`(킥오프 직전 마지막 정기 수집 시각)다.
두 값은 12:00 KST 킥오프처럼 정기 수집 시각에 걸친 경기에서 **서로 다르다**(due=06:00,
slot=12:00). 실행 시각 기준으로 두면 같은 경기가 회차가 달라져 중복 생성되거나, 반대로
기존 회차와 어긋나 판정이 틀어진다.

`_round_key()`를 `generation_due_at(kickoff)`로 바꿔 **킥오프에 고정**했다. 검사는 두
helper가 실제로 갈리는 시각을 골라 `_round_key()`가 due 값을 쓰는지 확인한다. `slot_time`으로
되돌리면 이 검사가 실패한다(확인함).

### 3. 실패·진행 중 기록도 중복 판정에 포함된다

`_already_generated()`는 상태를 구분하지 않고 같은 경기·같은 회차의 실행 이력을 중복으로
본다. 성공·실패·진행 중 모두 새 자동 생성을 막는다. 실패 기록을 지우거나 재시도 상태로
바꾸지 않으므로 **새 자동 재시도 정책을 만들지 않는다**(사용자 확정 Q3 유지).

### 4. 조회와 생성 사이 경쟁 — 경기 단위 최소 잠금

중복 조회와 생성 시작 사이에는 창이 있다. 두 수집 종료가 거의 동시에 같은 경기를 보면
둘 다 "아직 없음"을 읽고 둘 다 시작할 수 있다. 확인한 사실:

- `run_bundle_pipeline`에는 중복 억제가 없다(`find_active_run`/`dedup_key` 참조 0건).
- 기존 `preview_pipeline_runs`의 active 유니크 키는 **진행 중 실행**만 합치며, 이 경계는
  그 표를 쓰지 않는다(생성 서비스 소유).

그래서 새 잠금 엔진을 만들지 않고, 이 저장소가 이미 쓰는 `pg_try_advisory_lock` 패턴을
**경기 단위 키**로 한 번만 썼다(`_AdvisoryFixtureLock`, namespace 730001 + fixture_id).
잠금을 못 잡으면 생성을 시작하지 않고 `generation_in_progress_elsewhere` 사유로 건너뛴다
(동시 중복을 만들지 않는 쪽을 택함). 잠금은 `_generate_one()` 호출까지 감싼다.

검사 두 건: 잠금 미획득 시 생성 0건, 그리고 생성 호출이 **잠금 안에서** 일어남을 순서로
확인(`["enter:101", "generate:101", "exit:101"]`). 후자는 잠금을 잡고도 생성이 밖에 있으면
창이 그대로 남기 때문에 넣었다.

### 승인 게이트

`admission_state` 의미는 그대로다. 자동 생성 허용/불허를 이 값으로 뒤집지 않고, 결과에
사실로만 남긴다(`state: ready|not_ready`, `missing_approval`, `stale_approval`). 미승인·버전
불일치를 정상 완료로 표시하지 않는다.

### 검사 결과

`.venv/bin/python -m pytest tests/unit/test_home_preview_collection.py -q` → **14 passed**
(기존 11 + 관리자 제외 1 + 잠금 2, 회차 검사는 강화).

회귀 확인: `_round_key`를 `slot_time`으로 되돌리면 회차 검사가 실패하고, 잠금 대역을
미획득으로 바꾸면 잠금 검사가 실패한다. 되돌린 뒤 14 passed로 복귀한다.

### 남은 항목 (변경 없음)

- 실제 운영 수집·모델·DB는 여전히 실행하지 않았다. 잠금은 PostgreSQL 세션 advisory lock이며
  실제 동시 진입에서의 동작은 실수집 연동 때 확인해야 한다. 이 검사는 잠금 대역으로 경계
  로직만 확인했다.
- 생성기는 여전히 모의다. 실제 생성·저장·홈 표시의 근거가 아니다.

## 독립 검토 지적 4건 수정 (2026-11-13 04:45)

입력: `preview-collection-connect-review.md`의 현재 요구 위반 1~4. 회차/잠금 보완은 보존했다.
검토가 지적한 네 건 모두 코드로 원인을 확인한 뒤 고쳤고, 3건은 실제 회귀로 재현한다.

### 지적 1 — preview 세션 팩토리 계약 불일치 (차단, 실제 결함)

**원인.** `_preview_session_factory()`/`_default_preview_factory()`가
`app.preview.db.get_session_factory()`의 **반환값인 `sessionmaker` 인스턴스**를 그대로
넘겼다. 그래서 `preview_factory()`가 `Session`이 아니라 `sessionmaker`를 냈고,
`with preview_factory()`가 `TypeError`로 실패했다.

설치된 SQLAlchemy 2.0.36에서 직접 확인했다. `sessionmaker` 인스턴스는 `__enter__`가 없고
`with`에 넣으면 `TypeError: 'sessionmaker' object does not support the context manager
protocol`이 난다. `db.SessionLocal`은 `sessionmaker` 인스턴스 자체이므로 `with
session_factory()`가 `Session`을 내 정상이다. 같은 이름의 두 인자가 **서로 다른 단계**의
계약을 갖고 있었다.

귀결은 검토 서술과 같다. 중복 조회 블록이 이 `TypeError`를 `except Exception`으로 삼켜
`dedup_query_failed`로 기록하고 `continue`했으므로 **모든 후보가 생성 전에 실패**했고
`generated`는 항상 비었다. `_approval_gate`도 같은 팩토리를 써서 항상 `unknown`이었다.

**수정.** 계약을 하나로 만들었다. `home_preview_collection.preview_session_factory()`는
maker를 **한 번 더 호출**해 `with`에 쓸 `Session`을 낸다. `management_runs`의 별도 wrapper는
삭제하고 **같은 정의를 import**해 쓴다(한쪽만 고쳐 다시 어긋나는 일을 막는다).
`_default_preview_factory`는 같은 함수를 가리키는 호환 이름이다. `_approval_gate`를
`_admission`으로 바꿔 생성 **전** 판정에 쓴다(지적 3).

**검사.** `test_preview_session_factory_calls_the_maker_so_with_gets_a_session`이 maker 대역으로
"부르면 세션이 나온다(그 자체를 반환하지 않는다)"를 확인한다. DB 없이 계약만 본다. maker를
그대로 반환하도록 되돌리면 이 검사가 실패한다(확인함). 검토가 지적한 대로 기존 14건은
세션 대역을 직접 주입해 이 단계를 지나가지 않았으므로, 대역이 아닌 계약 검사를 따로 두었다.

### 지적 2 — 상위 예외 종료가 프리뷰 생성에 도달하지 않음 (실제 결함)

**원인.** 훅이 정상 경로의 `try` 안에만 있어, API 키 미설정·클라이언트 생성 실패 같은
상위 예외 종료에서는 프리뷰를 시도하지 않았다. `management_runs`의 `except Exception`과
`worker_runs`의 상위 `except` 모두 해당.

**수정.** 두 경로의 상위 예외 처리에서 같은 훅을 **한 번** 호출한다.
- 중복 방지: `preview_started` 플래그를 `try` **밖에서** 초기화하고 정상 경로에서 `True`로
  올린다. 예외 경로는 이 값이 거짓일 때만 호출한다.
- 원래 수집 상태·오류 보존: 훅 호출 결과는 `payload["home_preview"]`에만 쓰고
  `payload["status"]`, `stage`, 로그는 건드리지 않는다. 훅 호출 자체도 `try/except`로 감싸
  프리뷰 실패가 수집 오류를 덮지 않게 했다.
- 명시 취소: 취소는 `SyncCancelled` 경로로 빠져 프리뷰 훅에 도달하지 않는다(기존 유지).

**구현 중 스스로 잡은 결함.** `worker_runs`에서 플래그를 `try` 안쪽에 두어, 그보다 먼저
예외가 나면 `UnboundLocalError`로 **원래 오류를 가리는** 상태였다. `try` 밖으로 올려 고쳤다.

**검증 한계(정직하게).** 이 두 경로는 `management_runs`/`worker_runs` 상위 흐름이라 이번
직접 명령(`tests/unit/test_home_preview_collection.py`)의 대상이 아니다. 새 테스트 파일을
만드는 것은 소유 범위 밖이므로, 이 항목은 **코드 경로 확인**(플래그 초기화 위치·호출 조건·
감싸기)으로만 보고한다. 실행 검증은 하지 않았다.

### 지적 3 — 자동 생성에 승인 게이트가 없음 (실제 결함)

**원인.** `admission_state`는 생성이 모두 끝난 뒤 `approval_gate`로 **기록만** 됐고 생성
여부를 가르지 않았다. `bundle_pipeline`·`match_preview`에는 `admission` 참조가 0건.

**수정.** 생성 루프 **앞에서** 한 번 판정한다.
- `not_ready`(missing/stale): 후보를 `skipped`로 남기고 `state: skipped`,
  `reason: approval_not_ready`. 각 항목에 `missing_approval`/`stale_approval` 목록을 전달한다.
- `unknown`(승인 조회 실패): 생성하지 않고 `reason: approval_query_failed`. 승인을
  가정하지 않는다.
- `ready`일 때만 기존 동일 생성 서비스로 들어간다.

관리자 시험(`trigger="admin"`)과 승인 행·버전 계산은 손대지 않았다. 이제 보고서의
"사실로만 남긴다"는 서술은 **생성 전 판정**으로 바뀌었으므로 아래와 같이 정정한다:
이전 서술은 승인 정책을 보존했다고 말했지만 실제로는 생성을 막지 않아 brief의 "건너뜀/실패
사유를 남기고 진행하지 않는다"를 충족하지 못했다. 검토 지적이 맞다.

**검사.** `test_approval_not_ready_blocks_generation_before_any_call`(생성 0건·사유·목록 전달),
`test_approval_query_failure_is_a_failure_not_a_pass`. 게이트를 무력화하면 두 건이 실패한다(확인함).

### 지적 4 — 비예외 실패 결과를 generated로 기록 (실제 결함)

**원인.** `_generate_one`이 `outcome.status`를 보지 않고 `generated`에 넣었다. 필수 섹션을
만들지 못한 실행은 `RunStatus.FAILED`로 끝난다(`bundle_pipeline` 계약).

**수정.** 실제 enum(`app.preview.contracts.RunStatus`)으로 판정한다. `SUCCEEDED`가 아니면
`failed`에 `run_id`·`reason: generation_status_<값>`·`detail`(unavailable_reason)을 남기고
`generated`에는 넣지 않는다. 다음 경기는 계속 처리한다. 검사 대역도 문자열 흉내 대신
**실제 `RunStatus`**를 쓰도록 바꿨다.

**검사.** `test_non_exception_failed_outcome_is_recorded_as_failed_not_generated`가 두 경기 모두
failed로 가고 generated가 비며 다음 경기가 계속됨을 확인한다. 분기를 무력화하면 실패한다(확인함).

### 검사 결과

`.venv/bin/python -m pytest tests/unit/test_home_preview_collection.py -q` → **19 passed**
(기존 14 + 지적별 대표 5).

변이 확인: 팩토리 계약 되돌리기 1건 실패, 승인 게이트 무력화 2건 실패, 실패 상태 분기
무력화 1건 실패. 각각 되돌린 뒤 19 passed로 복귀한다.

**합성 검사다.** 실제 DB·모델·수집·브라우저·승인 POST·마이그레이션은 0건이다. 승인 게이트
검사도 승인 상태 대역을 주입한 것이며 실제 승인 행을 읽은 것이 아니다.

### 남은 항목

- 지적 2(상위 예외 훅)는 이번 직접 명령의 대상이 아니어서 실행 검증이 없다. 코드 경로로만
  확인했다. 전용 검사가 필요하면 새 테스트 파일 소유권이 필요하다.
- 실제 운영 수집·모델 호출·실제 advisory lock 동시 진입은 여전히 미확인이다.
- 승인 상태가 실제로 `ready`인 환경에서의 자동 생성·공개는 별도 확인 대상이다.

`EDITING STOPPED`. 백그라운드 작업 0건.

## 지적 2 상위 예외 경로 — 실행 근거 보완 (2026-11-13 04:58)

앞 절에서 "지적 2는 코드 경로로만 확인했고 실행 검증이 없다"고 적었다. 이번에 두 상위
진입점을 **실제로 호출**하는 검사를 같은 파일에 추가했다. 새 테스트 파일은 만들지 않았다.

### management_runs — `execute_run`

`test_execute_run_top_level_exception_still_calls_the_preview_hook`.
`execute_run(payload, guard)`를 직접 호출하고 바깥 경계만 대역으로 바꿨다
(`get_settings`, `RunTracker`, `run_home_preview_after_sync`). `api_football_key = None`
으로 두어 실제 코드가 `ManagementError`를 던져 상위 예외 경로로 들어가게 했다.

확인한 사용자 결과: 훅이 **정확히 1회** 호출되고 `collection_status="failed"`가 전달된다.
`payload["status"]`는 `failed`, `stage`는 `수집 실행 실패`로 보존되며(프리뷰가 덮지 않음),
결과는 별도 `payload["home_preview"]`에 남는다. 훅 호출을 지우면 이 검사가 실패한다(확인함).

`test_execute_run_normal_path_does_not_call_the_hook_twice`. 정상 경로를 **실제로 지나가게**
만들어(측정 1건·성공 backfill 대역) 정상 훅이 1회 돈 뒤 예외를 유도했다. 가드가 살아 있으면
호출은 1회, 가드를 없애면 **2회**가 되어 실패한다(확인함).

### worker_runs — `start_daily_sync_run`

`test_daily_sync_top_level_exception_calls_the_preview_hook`.
`start_daily_sync_run()`을 직접 호출한다(스레드로 실행되며 종료까지 대기). 분산 잠금·
설정·spec 로딩·`run_backfill_batch`·로그 저장만 대역으로 바꾸고 `run_backfill_batch`가
`RuntimeError`를 내 상위 예외로 끝나게 했다.

확인한 사용자 결과: `run.status == "failed"`이고 `run.error`에 원래 오류 문자열이 남는다.
훅은 1회, `collection_status="failed"`로 호출되며 결과는 `run.result["home_preview"]`에
별도로 남는다. 훅 호출을 지우면 0회가 되어 이 검사가 실패한다(확인함).

### 검사가 무의미해지지 않게 고친 것

작성 중 세 가지 함정을 직접 확인해 고쳤다. 그대로 두면 "통과하지만 아무것도 고정하지 않는"
검사가 됐을 것이다.

1. 정상 경로 검사가 `assert len(calls) <= 1`이었다. 훅이 아예 안 불려도 통과하므로 `== 1`로
   바꿨다. 바꾼 뒤 가드 제거 시 2회로 실패하는 것을 확인했다.
2. `ApiFootballClient` 대역을 `def __init__(self, **kwargs)`로 만들어, 실제 호출이
   `api_key`를 **위치 인자**로 넘기는 바람에 정상 경로에 닿기 전에 예외가 났다. 로그를 직접
   찍어(`C.__init__() takes 1 positional argument but 2 were given`) 확인하고
   `def __init__(self, api_key=None, **kwargs)`로 고쳤다. 그 전까지 정상 경로 검사는 실제로는
   상위 예외 경로만 타고 있었다.
3. 쓰지 않게 된 `_RaisingTracker` 대역을 남겨 두었다가 삭제했다.

### 검사 결과

`.venv/bin/python -m pytest tests/unit/test_home_preview_collection.py -q` → **22 passed**
(기존 19 + 상위 두 경로의 실행 검사 3).

변이 확인: `execute_run` 상위 예외 훅 제거 → 1건 실패, 정상 경로 가드 제거 → 1건 실패(2회
호출), `worker_runs` 상위 예외 훅 제거 → 1건 실패(0회). 각각 되돌린 뒤 22 passed로 복귀한다.

**합성 검사다.** 실제 DB·외부 HTTP·모델·운영 수집·브라우저·승인 POST·마이그레이션은 0건이다.
세션·클라이언트·동기화 배치·훅을 모두 대역으로 바꿨으므로, 이 통과를 실제 수집 성공이나
실제 프리뷰 생성 성공으로 인용하지 않는다.

### 남은 항목

- 실제 운영 수집에서의 동작은 여전히 미확인이다(대역 검사만 있다).
- `_DailySyncAdvisoryLock`의 실제 동시 진입 동작, 승인 상태가 `ready`인 환경에서의 자동
  생성·공개도 실제 확인 대상으로 남는다.
- 앞선 세 지적(1·3·4)의 근거는 그대로 유효하며 이번에 다시 실행해 22 passed에 포함된다.

`EDITING STOPPED`. 백그라운드 작업 0건.
