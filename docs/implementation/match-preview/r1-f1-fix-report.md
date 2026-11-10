# R1 F1 수정 보고 — 덜어낸 과거 사실의 전제가 판단 문장에 남는 결함 (45b442a 기준)

**한 줄 결론.** F1은 **좁게 재현되는 결함**이었고, 이제 그 형태는 닫혔다. 같은 항목에서
근거를 확인하지 못해 덜어낸 과거 사건을 **전제로 삼은 부분만** 주장하지 않고 내려놓으며,
그 뒤의 미래 전망·선정·주관적 전술 평가는 그대로 남는다. 저장된 기준 v5·후보 v4를 같은
원문·같은 D0로 **외부 호출 0회** 재해석해 세 문장이 모두 해소됨을 확인했다.

## 1. 실행 환경과 경계

| 항목 | 확인값 |
|---|---|
| 에이전트 모델 | hive / `deepseek-ai/deepseek-v4.1-flash-1017`, `reasoningEffort=max`, 프로필 `dsh-tui` |
| 근거 | 현재 세션 `9f99462b-…`의 `session.v4.jsonl.zstd` `model/selection` (`provider: hive`, `model: deepseek-ai/deepseek-v4.1-flash-1017`, `reasoningEffort: max`) |
| 하위 워커 | **없음** (worker-start 0회) |
| 모델 호출 / API-Football 호출 | **0회 / 0회** |
| 승인 행 생성 | **0건** (`preview_section_approvals` = 0) |
| DB 쓰기 | **없음.** 모든 조회는 `conn.read_only = True` + `statement_timeout=20s` |
| 저장 행 변동 | 없음. `preview_attempts` 5, `preview_section_results` 11, `preview_results` 16, `preview_runs` 8 (수정 전과 동일) |
| 프론트/백엔드 | 8000·5173 재시작·접속 없음 |
| 설정 변경 | 없음. 프로필·제품 설정·비밀값 출력 없음 |
| Git | **staging/commit 없음.** 아래 4절의 unstaged 파일만 남겼다 |

독립 검토자(`term_a7ffb411`, task_1b9a334b96b2)는 이미 종료·물리적으로 닫힌 터미널이며,
이 작업에서 접촉·재개하지 않았다. 저장된 검토 문서
[r1-boundary-review.md](r1-boundary-review.md)의 F1 절만 근거로 재사용했다.

## 2. 결함의 정확한 형태 (재현)

F1은 "의견이면 통과"가 아니었다. **이미 근거 없음으로 덜어낸 사실이 다른 문장의 전제로
남아 확인된 지식처럼 읽히는** 형태다. 저장된 두 실행에서 세 문장으로 재현된다.

| 실행 | 문장 | 수정 전 처리 |
|---|---|---|
| 후보 `7c0af3c0` v4 | `최근 득점으로 자신감을 얻은 만큼 이번 맨시티전에서도 풀럼의 최전방을 책임질 것으로 기대됩니다.` | 근거 없는 득점 사실 문장은 **덜어냈지만**, 그 사건을 가리키는 전제가 남았다 |
| 기준 `6e59041a` v5 | `역사적인 상성 우위를 바탕으로 맨시티가 심리적 우위를 점한 채 경기를 주도할 가능성이 큽니다.` | `23차례 21승 2무` 사실은 덜어냈지만, 그 수치의 축약 전제가 남았다 |
| 후보 `7c0af3c0` v4 | `맨시티가 최근 지적받은 중원 제어력 문제를 해결하지 못한다면 …` | 누가 그렇게 말했다는 보도가 인용 근거에 없는데도 문장이 남았다 |

원인은 두 가지였다.

1. **전제 검사 부재.** 판정이 문장 단위 수치·사건 유무(`_NUMBER`/`_EVENT_WORDS`/
   `_PAST_EVENT`)만 봤다. 전제(`…을 바탕으로`, `…을 얻은 만큼`)는 어휘가 없어 판단으로
   분류됐다.
2. **완료 사건의 근거 대조 누락.** `_clause_supported`가 수치·부상 어휘만 대조하고
   `_PAST_EVENT`는 대조하지 않아, 숫자 없는 과거 사건("골을 터뜨렸습니다")은 근거가
   없어도 통과했다. 게다가 기존 어형이 `터뜨린`만 있어 실제 응답의 `터뜨렸`도 놓쳤다.

## 3. 바꾼 것 (form.py 한 파일, 국소 변경)

### 3.1 덜어낸 사실에 종속된 전제만 내려놓는다

`_filter_judgment_text`(`form.py:762`)가 세 단계로 판정한다.

1. 문장별로 수치·사건이 든 사실 조각인지 보고 근거와 대조한다(기존 규칙 유지).
2. **같은 항목에서** 사실이 덜어졌을 때만, 전제부가 **시간 지시어**(`최근·지난·역사·과거
   …`, `_TEMPORAL_DEIXIS`)로 과거를 가리키는 판단 문장의 **전제부만** 내려놓고 뒤의
   전망을 남긴다(`_BASIS_CONNECTIVE`, `_basis_split`).
3. "지적받은"류는 제3자 보도를 옮긴 표현이므로, 그 동사가 **인용한 근거에 없으면 그
   표현만** 덜어내고 남는 전술 평가·전망은 남긴다(`_REPORTED_ATTRIBUTION`).

`같은 항목` 게이트가 핵심이다. 덜어낸 사실이 없는 항목의 판단, 시간 지시어 없는 주관적
전술 평가(`…성향을 바탕으로`), 예측·선정은 **건드리지 않는다**. 항목 전체 거절도,
모든 의견의 출처 요구도 되살리지 않았다.

### 3.2 완료 사건을 실제로 대조한다

`_clause_supported`(`form.py:448`)가 `_PAST_EVENT` 일치 구간도 인용 문장에 있는지 본다.
어형 목록은 **활용형 하나만** 바로잡았다(`터뜨린` → `터뜨렸·터뜨린`, `넣었·넣은` 등).
미래 어형(`터뜨릴`)은 잡지 않으므로 전망을 사실로 오인하지 않는다. 새 사건 어휘를
덧붙이는 방향으로 확장하지 않았다.

### 3.3 무엇을 왜 뺐는지가 남는다 (F2 담당용 인터페이스)

- 관리자 진단 문장: `확인되지 않은 사실 조각 N개를 덜어냈습니다: …`,
  `덜어낸 사실을 전제로 삼던 부분을 주장하지 않고 내려놓았습니다: …`
- **구조화 값**: `validate_response()`가 돌려주는 `_Validated`에 추가 필드
  `dropped_facts` / `unasserted_premises`(항목 라벨이 앞에 붙은 문자열 튜플).
  기존 필드·`diagnostics` 문자열 모양은 그대로다.

### 3.4 바꾸지 않은 것

`compose.py`, `sections.py`, `approvals.py`, `version_manifest.py`, `registry.py`,
`modules/__init__.py`, `prompts/form.md`, 프롬프트 문구·생성 설정은 손대지 않았다.
프롬프트를 고쳐 모델에게 다시 요구하는 방식(새 지시·재호출)을 택하지 않았다.

## 4. 버전 (MP09가 등록해야 하는 정확한 값)

| 대상 | 값 | 비고 |
|---|---|---|
| R1 구현 | `mp05-form-2` → **`mp05-form-3`** | 검증 규칙 변경. `app/preview/modules/__init__.py` 등록은 **MP09 소유** |
| R1 프롬프트 | `mp05-form-prompt-2` (변경 없음) | 프롬프트 미수정 |
| R1 본문 조립 | `mp05-compose-2` (변경 없음) | compose 미수정 |
| D0 | `mp05-stored-d0-1` (변경 없음) | |
| 현재 stamp | `section_form@dff5ef9da8f20f8a` | `mp05-form-3` 등록 전 |
| 등록 후 stamp | **`section_form@3721e7df4a7f6a61`** | `constituents_for_workflow`로 계산(읽기 전용, 파일 미수정) |

즉 `modules/__init__.py`의 R1 항목을 `("mp05-form-3", "mp05-form-prompt-2")`로 바꾸면
approval 단위 버전이 `@3721e7df4a7f6a61`로 올라간다. 이 값은 **파일을 고치지 않고**
in-memory 계산으로만 확인했다.

## 5. 저장 실행 재검증 (호출 0회, 읽기 전용)

`evidence/f1-premise/reproduce_offline.py`가 저장 원문 artifact와 저장 D0 payload로
새 검증·조립을 다시 실행한다. DB는 read-only 트랜잭션이다.

| 실행 | 저장 본문 | 재검증 후 | 관전/선수/흐름 | 내려놓은 전제 |
|---|---|---|---|---|
| 기준 `6e59041a` | v5, 885자 | **868자** | 2 / 3 / 2 (동일) | 1 |
| 후보 `7c0af3c0` | v4, 878자 | **837자** | 3 / 3 / 2 (동일) | 3 |

### 5.1 문장 단위 before → after

| # | before (저장 본문) | after (재검증) |
|---|---|---|
| 1 | `역사적인 상성 우위를 바탕으로 맨시티가 심리적 우위를 점한 채 경기를 주도할 가능성이 큽니다.` | `맨시티가 심리적 우위를 점한 채 경기를 주도할 가능성이 큽니다.` |
| 2 | `역사적인 우위를 바탕으로 맨시티가 … 주도할 것으로 전망됩니다.` | `맨시티가 심리적 우위를 점한 채 경기를 주도할 것으로 전망됩니다.` |
| 3 | `맨시티가 최근 지적받은 중원 제어력 문제를 해결하지 못한다면 이워비의 … 고전할 수 있습니다.` | `맨시티가 중원 제어력 문제를 해결하지 못한다면 이워비의 창의적인 패스에 고전할 수 있습니다.` |
| 4 | `무니스는 최근 득점으로 자신감을 얻은 만큼 이번 맨시티전에서도 풀럼의 최전방을 책임질 것으로 기대됩니다.` | `무니스는 이번 맨시티전에서도 풀럼의 최전방을 책임질 것으로 기대됩니다.` |

### 5.2 유지된 것 (사용자 기준 확인)

- **미래 전망·선정**: `득점포를 가동할 가능성이 매우 높습니다`, `최전방을 책임질 것으로
  기대됩니다`, `가장 유력한 해결사`, `가장 날카로운 무기` 모두 유지.
- **주관적 전술 평가**: `강력한 압박`, `압도적인 천적 관계`(제목), `과감하게 슈팅을
  시도하는 성향을 바탕으로 …` 유지.
- **부분 부상 맥락**: R2 경로·`test_injury_reason_usable_with_unknown_onset_*` 그대로 통과.
- 근거에 연결된 API 사실(순위·폼)과 출처 0건 상태의 선정 항목은 변동 없음.

## 6. 검증 명령과 결과

| 명령 | 결과 |
|---|---|
| `.venv/bin/python -m pytest tests/preview/test_form_module.py -q` | **21 passed** |
| `… test_form_module.py test_workflow_version.py test_module_runner.py test_section_approvals.py test_presentation.py test_synthesis.py -q` | **83 passed** |
| `.venv/bin/python docs/…/evidence/f1-premise/reproduce_offline.py` | 기준 885→868자 premises=1, 후보 878→837자 premises=3 |

새 대표 회귀 1건: `test_rejected_fact_premise_not_left_as_asserted_opinion`. 사용자 결과
중심으로 (1) 덜어낸 사건의 전제는 주장되지 않음, (2) 그 뒤 전망·선정은 유지,
(3) 주관적 전술 평가·덜어낸 사실이 없는 항목은 무변경을 확인한다. 기존 적용 사례
`test_api_fact_supported_opinion_accepted_without_search_url`(선정 자체에 외부 증거 불요),
`test_unverified_statistic_not_smuggled_through_as_opinion`(수치 위장 차단)은 그대로 통과한다.

명령 원문과 결과는 [evidence/f1-premise/commands.txt](evidence/f1-premise/commands.txt),
재현 스크립트는 [reproduce_offline.py](evidence/f1-premise/reproduce_offline.py), 결과 값은
[evidence.json](evidence/f1-premise/evidence.json)에 있다.

요청대로 전체 95/296 스위트, 프론트엔드 테스트·빌드·브라우저, 광범위 수치/이벤트 코퍼스는
실행하지 않았다.

## 7. 남은 한계 (다음 작업자에게)

1. **새 저장 행 없음.** 이 작업은 R1/section 결과를 **저장하지 않았다**. 5절의 after는
   오프라인 재검증 결과이며, 저장된 최신 후보는 여전히 v4/v5다. 후보 생성·저장은 MP09가
   인계 후 수행한다.
2. **버전 등록 미완.** `mp05-form-3`은 아직 `modules/__init__.py`에 없다(소유권 밖).
   등록 전에는 stamp가 `@dff5ef9da8f20f8a`로 남는다.
3. **F2 진단 저장 미수정.** 글자 배열로 쪼개지는 섹션 진단 저장(`sections.py:855–859`)과
   재검증 R1 결과 행 미저장은 이번 범위가 아니다. 다만 이번 변경으로 `_Validated`에
   `dropped_facts`/`unasserted_premises` 구조 값이 생겼으므로 F2 담당이 그대로 쓸 수 있다.
4. **F3 승인 버전 원천**도 이번 범위가 아니다(MP09).
5. **규칙의 경계.** 전제 판정은 시간 지시어 + 연결 어형이라는 **구조 신호**만 본다.
   시간 지시어 없이 과거 사건을 함축하는 표현, 또는 인용 근거에 없는 다른 종류의 주장은
   잡지 않는다. 동의어·정규식 목록을 늘리는 방식으로 확장하지 말 것 — 이 결함의 최소
   해결은 "같은 항목에서 덜어낸 사실에 종속된 전제"라는 구조다.
6. **후보 v4 관전 포인트 2**(R1 지적, 차단 아님)는 여전히 제목만 남는다. 표시 개선 후속.

## 8. 소유·인계

- 수정·소유 파일: `app/preview/modules/form.py`, `tests/preview/test_form_module.py`,
  이 보고서, `evidence/f1-premise/{evidence.json,reproduce_offline.py}`.
- 손대지 않은 공유 파일: `sections.py`, `approvals.py`, `version_manifest.py`,
  `registry.py`, `modules/__init__.py`, `modules/compose.py`, `prompts/form.md`,
  `Plans.md`, 정책 문서.
- **staging/commit 없음.** MP09가 위 4절 버전 값을 등록하고 후보를 생성한다.
