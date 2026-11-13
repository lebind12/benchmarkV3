# 수집 생성의 저장 경기 조회기 전달 누락 수정 (PC-LIVE)

작성: DeepSeek 구현 워커, 2026-11-13. 실행기 `dsh-tui`, 모델 `deepseek-ai/deepseek-v4.1-flash-1017`,
추론 강도 `max`(사용자 설정 유지). 하위 워커·모델 전환·새 조정 Run 없음.

## 원인

`app/services/match_preview.py`의 `generate_match_preview`가 **두 단계에서 서로 다른 조회기를
봤다.**

1. `resolve_stored_fixture(...)`는 `reader=None`이면 설정에서 조회기를 열어(`borrowed=True`)
   경기 ID만 해석하고 **자기 `finally`에서 닫았다.**
2. 이어서 호출되는 `run_bundle_pipeline`에는 원래 인자인 **`reader`(여전히 `None`)** 를 넘겼다.

그래서 파이프라인은 저장 경기 조회기 없이 실행됐다. 실제 관측과 정확히 일치한다.

- `db_snapshot.readable=false`, 경기 식별 coverage `not_run`,
  "저장 경기 자료 읽기 연결이 설정되지 않았습니다", `standings=[]`
- 같은 첼시 경기의 이전 관리자 실행(`32cc0aa9…`)은 `readable=true`·식별/순위 available
- 선수 통계는 58/55행이 있고 대부분 이번 수집 이후 갱신됨

즉 **자료가 없거나 DB가 고장 난 것이 아니라, 수집 경로가 조회기를 넘기지 않은 연결 결함**이다.
관리자 경로는 호출자가 조회기를 주입하므로 이 결함이 드러나지 않았다.

`bundle_pipeline`은 `reader`를 세 곳에서 실제로 쓴다: D0의 저장 경기 식별(ID 공간 보정),
`injuries_for_fixture`(부상), 그리고 그 밖의 저장 자료 준비. `None`이면 이 단계들이 조용히 빈다.

## 수정 (`app/services/match_preview.py` 한 파일)

조회기를 **한 번 열어 두 단계가 함께 쓰고, 서비스가 연 경우에만 닫는다.**

- `owned_reader`: 호출자가 `reader`를 주지 않았을 때만 설정에서 연다.
- `effective_reader`: 해석과 `run_bundle_pipeline` **양쪽에 같은 값**을 넘긴다.
- `try/finally`: 해석 오류·생성 오류·성공 어느 경로에서도 같은 지점에서 정리한다.
- `owned_reader is not None`일 때만 닫는다. **호출자 주입 조회기는 닫지 않는다**(호출자 소유).

바꾸지 않은 것: 시스템 actor(`COLLECTION_ACTOR_ID`)·회차 label·생성 엔진·승인 정책·
프롬프트·본문 스키마·본문 자료 해석 규칙. 새 연결 풀·조회 엔진·범용 수명 관리기를 만들지
않았다. 다른 제품 파일은 수정하지 않았다.

## 검사

`.venv/bin/python -m pytest tests/unit/test_match_preview_reader.py tests/unit/test_home_preview_collection.py tests/unit/test_management_preview_test.py -q`
→ **49 passed** (신규 8 + 기존 24 + 기존 17).

**합성 검사다.** 실제 DB·HTTP·모델·서버·승인 POST·마이그레이션은 0건이다. 조회기·세션·
파이프라인 경계를 대역으로 바꿨다.

새 검사 `tests/unit/test_match_preview_reader.py` (8건)가 고정하는 것:

| 검사 | 확인 내용 |
|---|---|
| `..._uses_one_open_reader_for_both_stages` | 조회기를 생략한 수집 호출에서 해석과 파이프라인이 **같은 열린 조회기**를 쓰고, 한 번만 연다 |
| `test_service_owned_reader_is_closed_after_success` | 서비스가 연 조회기는 파이프라인 **뒤**에 **정확히 한 번** 닫힌다 |
| `test_caller_supplied_reader_is_not_closed` | 주입 조회기는 닫지 않는다(호출자 소유) |
| `test_reader_is_closed_when_generation_raises` | 생성 예외에서도 정리된다 |
| `test_reader_is_closed_when_resolution_fails` | 해석 실패에서도 정리되고 모델을 보내지 않는다 |
| `test_unreadable_stored_data_still_fails_before_any_model_call` | 읽기 불가 시 기존 `reader_denied` 유지, 모델 0회 |
| `test_unconfigured_reader_keeps_its_clear_error` | 미설정 시 `reader_unconfigured` 유지(모의 대체 없음) |
| `test_collection_trigger_still_rejects_a_manage_actor` | 시스템 호출 위장 금지 유지 |

**대역이 실제 사용을 강제한다.** 조회기 대역은 **닫힌 뒤 쓰이면 실패**한다. 파이프라인
대역은 전달받은 조회기로 `injuries_for_fixture`를 실제로 호출한다. 그래서 "kwargs가 같다"만
보는 검사가 아니라, **넘긴 조회기가 그 시점에 유효하게 쓰일 수 있는지**를 확인한다.

**회귀 확인**: 파이프라인에 넘기는 값을 원래 `reader`로 되돌리면
`..._uses_one_open_reader_for_both_stages`와 `test_service_owned_reader_is_closed_after_success`가
실패한다(확인 후 원복). 즉 이 검사가 이번 결함을 실제로 잡는다.

## 적용 원칙

`poteto-mode/SKILL.md` 전문은 이 세션에서 읽었고 해시 `70faeea6...b936`(24986 bytes) 미변경을
확인해 재사용했다.

- **Fix Root Causes.** 증상(빈 `standings`·`readable=false`)을 화면이나 후속 단계에서 덮지 않고,
  조회기가 왜 비었는지 첫 지점(서비스의 이중 수명)까지 내려가 고쳤다. 그래서 수정이 한 파일·
  한 함수에 그쳤다.
- **Boundary Discipline.** 조회기 소유권을 "누가 열었는가"로 한 곳에서 판정한다(서비스가 열면
  서비스가 닫고, 주입이면 주입자가 닫는다). 소유 규칙을 여러 곳에 흩지 않았다.
- **Laziness Protocol.** 새 수명 관리기·연결 풀을 만들지 않고 기존 `_resolver_from_settings`와
  `close()` 계약을 그대로 썼다.

## 미확인

- 실제 공개/관리 GET에서 `db_snapshot.readable=true`·경기 식별 available·`standings`가 채워지는
 지는 **이번에 실행하지 않았다**. 이 수정은 연결 결함만 고쳤고 실제 재조회는 조정자 담당이다.
- 두 실행(`e6a78cd9…`, `54c1b9ee…`)의 기존 저장 본문은 이번 수정으로 바뀌지 않는다. 그 본문에
  순위·부상 자료가 채워진 새 실행이 필요하다.
- 수집 실행 `0178213b…`의 실행 기록·승인·저장 본문은 읽기만 했고 수정하지 않았다.

## 변경 파일

- `app/services/match_preview.py`
- `tests/unit/test_match_preview_reader.py` (신규)
- `docs/implementation/match-preview/preview-collection-reader-report.md` (이 문서)

`EDITING STOPPED`. 백그라운드 작업 0건.
