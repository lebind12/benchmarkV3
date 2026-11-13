# 승인 근거 기반 홈 표시 독립 검토 (HP-EVIDENCE)

작성: DeepSeek 검토 워커(읽기 전용), 2026-11-13 02:47 KST. 모델 `deepseek-ai/deepseek-v4.1-flash-1017`.
입력: `home-approved-evidence-brief.md`, `home-approved-evidence-report.md`, `app/services/home_preview_document.py` 변경, `tests/unit/test_home_preview_document.py` 새 검사.
스킬: `.agents/skills/poteto-mode/SKILL.md` 전문은 이 세션에서 읽었고 해시 `70faeea6...b936`로 미변경을 확인해 재사용했다. 원칙 `principle-prove-it-works`·`principle-test-behavior-not-implementation`를 적용했다.

## 판정

**수용.** 재현된 직접 결함이나 요구 위반은 없다. 활성 승인이 정확히 가리키는 저장 행이 버전 문자열 불일치에도 표시되고, 근거는 다른 실행·다른 결과·다른 워크플로우로 확대되지 않으며, 기존 버전 승인 경로와 구성본 정확 선택·읽기 전용 조회가 보존된다. 실제 조회가 근거 필드를 읽어 선택 함수까지 전달하는 연결도 확인했다.

## 확인한 것

**1. 근거 집합의 경계.** `approved_evidence()`(`:108-134`)는 `active`인 승인만 보고 `(workflow_id, reviewed_run_id, section_result_id)` 세 값이 모두 있을 때만 원소를 만든다. 하나라도 없으면 버린다. 튜플에 실행 ID가 포함되므로 같은 섹션 이름의 다른 실행 결과와 넓어질 수 없다.

**2. 판정 순서.** `_displayable()`(`:137-167`)은 본문 없음과 `mode == "mock"`을 먼저 배제한 뒤 두 갈래를 본다. ① 워크플로우 버전이 활성 승인 버전과 일치(기존), ② 워크플로우·실행·섹션 결과가 모두 일치(증거). 어느 갈래도 아니면 거부다. 모의·빈 본문은 두 갈래보다 앞에서 막히므로 증거가 있어도 통과하지 못한다.

**3. 실행 범위.** 후보 행은 `_read_runs`가 외부 경기 ID로 먼저 거른 실행에서만 모인다(`:620`, `:630-638`). 증거 경로는 그 집합 안에서만 판정하므로 경기 범위를 넘길 수 없다.

**4. 연결.** `read_document`가 `_read_approvals`를 한 번 읽어 `approved_versions`와 `approved_evidence`를 모두 만들고(`:625-627`), `select_document(candidates, approved, evidence)`(`:639`)로 넘긴다. `_chosen_rows`가 `_displayable(row, approved, evidence)`를 두 루프에서 모두 호출한다(`:199`, `:203`). 근거 인자 기본값이 빈 집합이라 기존 호출부는 그대로 동작한다.

**5. 읽기 전용.** 이 모듈에 `session.add/delete/flush/commit`이 없다(전수 grep). `_read_approvals`는 `active` 행을 SELECT만 한다. 승인 행·섹션 행·구성본을 쓰지 않는다.

**6. 기존 경로 보존.** 버전 문자열 경로가 증거 없이도 그대로 동작하고, 구성본 정확 선택(`claimed`)의 대체 금지도 유지된다. 두 동작을 합성 입력으로 확인했다(아래).

**7. UUID 비교 일관성.** 승인 열은 `_text_of`가 `str()`로, 섹션 행은 `_section_row_view`가 이미 `str(row.id)`·`str(row.run_id)`로 만든다(`:450-451`). 두 값이 같은 표기로 비교된다는 것을 직접 확인했다.

## 확인 실행 (허용된 1회)

`.venv/bin/python -m pytest tests/unit/test_home_preview_document.py -q` → **15 passed (0.18s)**. 보고된 15와 일치한다. 14 passed에서 1건 늘어난 것도 보고서와 같다.

추가로 코드 경계만 합성 입력으로 확인했다(새 파일·새 검사 없이 프로세스 안 호출).

```text
버전 경로(증거 없음)        → ['a1']      기존 동작 유지
버전 불일치 + 정확한 근거   → ['res-1']   승인한 그 행만 표시
다른 실행 근거              → None        확대 없음
다른 워크플로우 근거        → None        확대 없음
모의 행에 근거 있음         → None        모의 제외 유지
```

## 참고 (차단 아님)

- **새 검사는 `select_document` 수준만 덮는다.** `test_approval_pointing_at_an_exact_result_is_displayed_despite_version_drift`(`:363-441`)는 `approved_evidence`와 `select_document`를 직접 호출한다. `read_document`가 `reviewed_run_id`/`section_result_id`를 읽어 넘기는 배선 자체를 지나는 검사는 없다. 기존 `_stub_approval`(`:238-243`)도 두 필드를 만들지 않는다. 이 배선은 `getattr(..., None)`로 안전하고 코드 4곳이 단순해 결함 소지가 낮지만, 관측된 누락이 실제 조회 경로에서 일어났던 일이므로 `read_document` 한 건이 있으면 근거가 더 단단해진다. 이 배선은 이후 root의 실제 조회로 확인됐다(아래).
- **UUID 표기 비교는 정규화된 소문자에 의존한다.** 승인 열과 섹션 행 ID는 모두 같은 ORM UUID에서 나와 표기가 일치하지만, 대문자 표기 문자열이 섞이면 불일치가 된다. 현재 두 경로 모두 `str(uuid)`를 쓰므로 실제 위험은 없고, 이번 변경이 만든 것도 아니다.
- 보고서가 밝힌 대로 `approvals.py`의 버전 재계산 사양은 F3 검사의 의도된 동작이라 손대지 않았다. 승인 서비스와 저장 행이 서로 다른 문자열을 갖는 상태는 그대로 남지만, 이제 홈 표시가 그 차이에 막히지 않는다.

## 실제 조회 확인 (root, 2026-11-13 02:48)

PID9352 서버의 실제 공개 GET에서 정확한 승인 근거 5섹션과 `complete=true`를 root가 확인했다. 이 검토가 코드 대조로 판정한 결과와 같은 결론이며, 위 참고의 "`read_document` 배선 검사 부재"도 실제 경로에서 문제없이 동작함으로 해소됐다.

같은 실제 조회에서 **별도 결함**이 드러났다. 관리자 원본 `d96fe824` section-results는 `photo_url` 6개가 정상인데 공개 home document는 모두 `null`이었다. 원인은 `_id_context`(`:601-607`)가 `StructuredIdContext`에 해석기(`bridge.names`)가 아니라 파사드(`bridge`)를 넘긴 연결 차이다. 확인이 전부 조용히 `None`이 되어 선수·부상 사진과 팀 외부 ID가 응답에서 빠졌다.

이 항목은 **HP-EVIDENCE 변경이 만든 것이 아니라 이전부터 있던 DOC-PRESENT 실제 실패**이며, root가 `home-photo-connection-brief.md` 범위로 원 구현자에게 분리 배정했다. 그래서 이 검토에서는 재검토·수정하지 않는다. 같은 파일이 수정될 수 있으므로 이 보고서의 판정은 승인 근거 경로(`approved_evidence`·`_displayable`·`_chosen_rows`·`select_document`·`_read_approvals`)에만 적용된다.

## 범위 준수

이번 변경은 `app/services/home_preview_document.py`와 `tests/unit/test_home_preview_document.py` 두 파일뿐이다(02:35 이후 변경 목록 확인). `app/preview/approvals.py`(mtime 02:31)와 `app/api/v1/home_preview.py`(00:31)는 이번 창에서 바뀌지 않았다. 새 코드·재현 스크립트·테스트·전체 회귀·DB/API/브라우저·서버·하위 워커를 쓰지 않았다. 이 검토에서 제품·검사 코드를 편집하지 않았고 백그라운드 작업도 시작하지 않았다. 02:48에 같은 파일의 `_id_context`가 별도 지시로 수정됐지만, 승인 근거 경로 함수들은 그대로임을 확인했다.
