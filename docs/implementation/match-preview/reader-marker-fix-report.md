# 독자용 본문 내부 근거 ID 노출 수정 보고 (R1 본문 조립)

**범위.** 후보 실행 `7c0af3c0-4f55-4270-9266-be58c65d8f6b`의 저장 payload·본문에서 실제로
관측된 **표시 결함 1건**만 고친다: 모델이 문장 안에 남긴 내부 근거 식별자
`[api:standings-13]`이 **독자용 본문에 그대로 노출**됐다.

**한 줄 결론.** 조립기(`clean_model_labels`)가 이제 `[api:…]` 형태의 내부 식별자를 지운다.
근거 자체는 구조화된 `claims`·`sources`·관리자 진단에 **그대로 남아 있다**. 저장된 조사
결과를 외부 호출 0회로 다시 조립해 **본문 버전 v2를 추가**했고(v1 원문 보존), 사용자 승인
행은 만들지 않았다. 이 수정은 **표시 교정**일 뿐이며, 검색 인용이 없어 관전 포인트·주목
선수가 빠진 **실질 조사 공백은 그대로 남아 있다.**

## 1. 실행 환경

| 항목 | 값 |
|---|---|
| 에이전트 모델 | hive / `deepseek-ai/deepseek-v4.1-flash-1017`, `reasoningEffort=max` |
| 프로필 | `dsh-tui` |
| 하위 워커 | 없음 |
| 모델·생성 설정 변경 | **없음** (제품 기본 `application/json` 유지) |
| 유료 모델 호출 / API-Football 호출 | **0회 / 0회** |

## 2. 관측된 결함 (수정 전 실측)

후보 실행의 저장 payload에서 `match_importance`·`recent_form` 문장에는 모델이 붙인
사실/해석 라벨과 함께 **근거 ID가 대괄호로** 들어 있었다.

```
fact: 맨체스터 시티는 승점 21점으로 리그 3위이며, 풀럼은 승점 10점으로 리그 15위에
위치해 있습니다. [api:standings-13, api:standings-4] interpretation: …
```

저장된 v1 본문(528자)의 실제 문장:

```
맨체스터 시티는 승점 21점으로 리그 3위이며, 풀럼은 승점 10점으로 리그 15위에 위치해 있습니다. [api:standings-13, api:standings-4] AI 해석으로는, …
Manchester City는 맨체스터 시티는 최근 5경기에서 LLLWW의 폼을 기록 중입니다. [api:standings-13] AI 해석으로는, …
Fulham는 풀럼은 최근 5경기에서 DDWWL의 폼을 기록 중입니다. [api:standings-4] AI 해석으로는, …
```

원인은 `app/preview/modules/compose.py`의 `clean_model_labels`가 `사실(fact):`·
`해석(interpretation):` 표기만 처리하고 **대괄호 내부 ID는 처리하지 않았기** 때문이다.
기준 실행(6e59041a)은 모델이 `사실(fact):` 표기를 쓰고 대괄호를 넣지 않아 드러나지 않았다.

## 3. 수정 (최소 변경)

`app/preview/modules/compose.py`

```python
_INTERNAL_ID_MARKER = re.compile(r"\[\s*api:[^\[\]]*?\]", re.IGNORECASE)
...
raw = _INTERNAL_ID_MARKER.sub(" ", _clean(text))
```

- **대괄호 안이 내부 접두사 `api:` 로 시작하는 경우만** 지운다. 일반 대괄호 서술,
  숫자 인용(`[1]`), 실제 URL 링크는 건드리지 않는다(§5에서 실측).
- 근거 검증·출처 검증 로직은 **손대지 않았다**. 표시 단계에서만 지운다.
- 정규식 하나로 끝내고, 포맷별 살균 매트릭스나 R2/R3 리팩터는 하지 않았다.

`app/preview/sections.py` — 결과가 달라지는 변경이므로 조립 구현 버전을 올렸다.

| 항목 | 값 |
|---|---|
| 조립 구현 버전 | `mp05-compose-1` → **`mp05-compose-2`** |
| 변경 이유 | 산출 문장이 실제로 달라짐(내부 ID 제거) |
| 적용 범위 | `section_form`(R1) 조립 노드만. R2/R3 조립 버전은 그대로 |
| 재조립 진단 | `조립 구현 버전: mp05-compose-2.` 를 진단 문장에 남김 |

> 참고: 승인 단위인 `workflow_version`(`section_form@9f0d2e9bcb33c26d`)은 모듈/프롬프트/
> 계약 버전으로만 계산되어 이번 변경에도 값이 같다. 그래서 차이를 **모듈 구현 버전과
> 재조립 진단 문장**으로 남겼다. 승인 버전 계산식 자체는 이번 범위에서 바꾸지 않았다.

## 4. 회귀 검사 1건 (실패 → 수정 → 통과)

`tests/preview/test_form_module.py::test_internal_source_ids_do_not_reach_reader_body`

관측된 모양 그대로(`[api:standings-13, api:standings-4]`)를 **읽히는 한국어 문장 안에**
넣고 세 가지를 함께 검증한다.

1. 독자용 본문에 `[api:` / `api:standings` 가 **없다**
2. 문장 자체는 남는다(`맨체스터 시티는 승점 21점으로 리그 3위입니다`)
3. 구조화된 근거(`claims[].claim_id`, `snapshot_ids`, `sources`)는 **그대로 남는다**

**수정 전 실패 증거(실행 기록):**

```
BEFORE FIX body:
… 맨체스터 시티는 승점 21점으로 리그 3위입니다 [api:standings-13, api:standings-4] AI 해석으로는, …
contains '[api:': True
AssertionError: FAILS AS EXPECTED: internal marker leaks
```

**수정 후:** 통과.

## 5. 오탐 방지 실측 (보존 확인)

| 입력 | 출력 |
|---|---|
| `맨체스터 시티는 3위입니다 [부상자 명단 미확정].` | 그대로 유지 |
| `최근 23경기 무패 [1] 기록입니다.` | 그대로 유지 |
| `근거는 https://www.bbc.com/sport 입니다.` | 그대로 유지 |
| `값은 [API 문서] 참고입니다.` | 그대로 유지(대괄호 안이 `api:`로 시작하지 않음) |

## 6. 저장 결과 갱신 (외부 호출 0회, 이력 보존)

기존 `sections.recompose_section_body` 경로(저장 payload 재조립, 외부 호출 없음)를 그대로 썼다.

| 항목 | 값 |
|---|---|
| 실행 | `7c0af3c0-4f55-4270-9266-be58c65d8f6b` |
| v1(원본) | `2489bb7a-c8dd-41cd-a791-88a8111b438a`, 528자, **`[api:` 포함 — 보존, 수정 안 함** |
| **v2(추가)** | **`1bd1c82c-edf1-4337-93c5-6181fc84ae75`, 455자, `[api:` 없음** |
| v2 진단 | `본문 조립 규칙만 다시 적용했습니다(외부 호출 0회). … 조립 구현 버전: mp05-compose-2.` |
| v2 quality/mode | `ready` / `live` (실제 생성 결과의 재조립이며 모의 아님) |
| 원문 응답 아티팩트 | `95f5e638-7f73-41df-a439-a88450d58630`, 16,855 B, sha256 `bc835368…` — **무변경** |
| 승인 행 | **0건** (전체 0, 이 실행 0) |

v2 본문(실제 저장본):

```
Manchester City와 Fulham의 맞대결입니다. Premier League 경기이며, 킥오프는 2026-11-21 12:30 UTC입니다.

맨체스터 시티는 승점 21점으로 리그 3위이며, 풀럼은 승점 10점으로 리그 15위에 위치해 있습니다. AI 해석으로는, 맨체스터 시티는 선두권 경쟁을 이어가기 위해, 풀럼은 하위권 탈출을 위해 승점 확보가 매우 중요합니다.

Manchester City는 맨체스터 시티는 최근 5경기에서 LLLWW의 폼을 기록 중입니다. AI 해석으로는, 최근 공식전 연패를 끊고 연승을 거두며 분위기 반전에 성공했으나, 리그에서의 안정감을 되찾기 위해 승리가 필요합니다. Fulham는 풀럼은 최근 5경기에서 DDWWL의 폼을 기록 중입니다. AI 해석으로는, 최근 경기에서 무승부를 거두며 다소 주춤했으나, 강팀들을 상대로 승점을 따내는 끈끈한 경기력을 보여주고 있습니다.
```

## 7. 구조화 근거 보존 (내부 데이터는 그대로)

| 항목 | 값 |
|---|---|
| R1 `claims` | **5건** (모두 채택) |
| claim ID | `api:standings-13`, `api:standings-4`, `r1-importance-0`, `r1-form-0`, `r1-form-1` |
| `source_ids` | `['52f3c43a-3fb2-4442-b7df-4fa0a11ec8f2']` |
| v2 `sources` | `[{"label": "API-Football 저장 자료", "url": null, "kind": "api", "note": "수집 2026-11-10T13:14:24.051542+00:00 · API-Football 저장 자료"}]` |
| 관리자 진단 | v1의 제외 사유 6건(관전 포인트 3, 주목 선수 3)은 v1 행에 그대로 남아 있음 |

즉 지운 것은 **독자 문장 안의 내부 표기**뿐이고, 근거 식별자·스냅샷 참조·제외 사유는
어디에서도 사라지지 않았다.

## 8. 실행한 검사

```
.venv/bin/python -m pytest tests/preview/test_form_module.py -q
  → 16 passed        (새 회귀 1건 포함, R1 조사·조립·승인 경로)
.venv/bin/python -m pytest tests/preview/test_availability_module.py tests/preview/test_module_runner.py -q
  → 38 passed        (공유 모듈·실행기 영향 확인)
```

전체 백엔드 296건, 프론트엔드 빌드·타입·브라우저 검사는 변경 영향이 없어 실행하지 않았다
(프론트 파일 변경 0).

## 9. 변경 파일

| 경로 | 내용 |
|---|---|
| `app/preview/modules/compose.py` | 내부 `[api:…]` 마커 제거(대괄호+`api:` 한정) |
| `app/preview/sections.py` | 조립 버전 `mp05-compose-2`, 재조립 진단에 버전 표기 |
| `tests/preview/test_form_module.py` | 회귀 1건 추가 + 테스트가 버전 상수를 쓰도록 정리 |
| `docs/implementation/match-preview/reader-marker-fix-report.md` | 이 보고 |
| `docs/implementation/match-preview/evidence/reader-marker-fix/evidence.json` | 전/후 본문·버전·근거 보존·0콜 증거 |

## 10. 남은 것 (품질 공백은 그대로)

1. **관전 포인트·주목 선수는 여전히 0건**이다. 검색 인용(`grounding_chunks`)이 제공자
   응답에 없어 근거 검증에서 제외된 결과이며, 이번 수정은 표시만 고쳤다. **실질 조사
   품질은 좋아지지 않았다.**
2. 선수·부상 단위 사실은 여전히 읽기 경계(`public.player*`) 밖이다.
3. 이 수정이 실제 생성 흐름에 적용되려면 **백엔드 8000 프로세스 재시작**이 필요하다.
   나는 재시작하지 않았으며, 사용자 화면 확인 전에 조정자가 재시작 시점을 정해야 한다.
   (프론트는 변경 없음 → 5173 재시작 불필요)
4. 저장된 v2는 사용자 승인 근거가 아니다. 승인은 화면에서 사용자가 판단한다.
