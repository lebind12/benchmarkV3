# R4 실생성 1회 — 결과 없음 보고 (전송 1회 소모, 저장 실패)

작성: 2026-11-11 05:22 KST. 담당: DeepSeek 구현 워커
(`hive` / `deepseek-ai/deepseek-v4.1-flash-1017`, `max`, 프로필 `dsh-tui`). 하위 워커 없음.

상태: **결함 수정·무료 검증 완료. 생성물은 아직 없음(추가 유료 전송 미승인). 편집 종료(§10).**

## 0. 먼저 읽을 것

승인된 **실제 전송 1회는 소모됐고, 그 결과는 저장되지 않았습니다.** 응답은 파싱까지
되었지만 저장 직전 단계에서 예외가 나 트랜잭션이 롤백됐고, 사용자가 열어볼 실행·섹션
결과·시도·원문 행이 하나도 남지 않았습니다. 그래서 **생성물 링크를 드릴 수 없습니다.**

원인 결함은 수정·무료 검증했고(§6~7), 남은 것은 **추가 실제 전송 1회**입니다(§8).
재전송은 조정자 승인 없이 하지 않았습니다.

## 1. 실제로 일어난 일 (시도 2회, 실제 전송 1회)

| 시도 | 실제 전송 | 결과 |
|---|---|---|
| 1 | **0회** (전송 전 거부) | 내 스크립트 예산 버그: `model_requests=1`인데 `normal_model_calls`가 기본 5로 남아 "예약 > 상한"이 되어 첫 시도가 전송 전에 거부됐다 |
| 2 | **1회** (실제 Vertex 전송) | 응답을 받아 **파싱까지 성공**했고, 그 다음 단계에서 `KeyError`로 중단. 트랜잭션 롤백으로 모든 행 소실 |

시도 1이 전송 0회임은 버그 재현으로 확인했습니다
(`can_attempt` → `False, '모델 요청 예산(1회) 중 아직 시작하지 않은 필수 단계 몫(4회)을 남겨야 합니다.'`).
이 버그는 고쳤습니다(`normal_model_calls=1` 동반 지정).

## 2. 왜 저장에 실패했나 (근본 원인)

제가 MP-10에서 만든 어댑터가 R4가 기대하는 계약보다 좁았습니다.

| 지점 | 내용 |
|---|---|
| 호출자 | `app/preview/modules/players.py:449` → `resolve_team(original, id_space=...)` — 팀 **이름만** 넘긴다 |
| 제공자 | `app/preview/sections.py:1194` `_ResolverHandle.resolve_team` — `team_id`가 없으면 `KeyError` |
| 실제 해석기 | `DisplayNames.resolve_team(value, *, team_id=None, ...)` — 이름만으로도 조회한다 |

즉 R4는 이름 기반 조회를 쓰는데 제 어댑터는 ID를 요구했습니다. 오프라인(전송 없음)으로
확인했습니다: 실제 해석기에 팀 이름만 주면 `맨체스터 시티 / db_korean`을 정상 반환합니다.
문제는 해석기가 아니라 **제 어댑터**입니다.

크래시 지점(`players.py:1156`)은 `request_model` 반환 이후에만 도달할 수 있는 위치입니다.
그래서 시도 2에서 **실제 전송이 나갔다**고 판단합니다. 다만 롤백으로 `preview_attempts`·
`preview_artifacts` 행도 함께 사라져, 그 응답 원문은 복구할 수 없습니다.

## 3. DB·외부 호출 확인 (크래시 후 실측)

| 항목 | 값 |
|---|---|
| 새 run | **0** |
| 시도(attempt) 행 | **0** |
| 원문 artifact 행 | **0** |
| 승인 행 | **0** (기존과 동일) |
| API-Football 호출 | **0** |
| 실제 모델 전송 | **1** (위 시도 2, 결과 미저장) |

기존 실행·본문·승인·이력은 건드리지 않았습니다. `public` DDL·DML, 새 역할, 마이그레이션,
계정/세션 조작 없음.

## 4. 제가 하지 않은 것 (의도)

- **재전송하지 않았습니다.** 이 작업의 상한은 "실제 전송 최대 1회"였고 이미 소모됐습니다.
  실패 뒤 자동 재시도·프롬프트 수리·모델 대체를 하지 않는다는 지시도 그대로 지켰습니다.
- **`app/preview/sections.py`를 고치지 않았습니다.** 이 작업에서 허용된 소스 수정은
  스크립트 하나뿐이었습니다. 근본 수정은 그 파일에 있습니다.
- 선정·근거 검증기를 결과를 얻게 하려고 완화하지 않았습니다.

## 5. 스크립트 변경 (허용 범위 내, 실제로 한 것)

`scripts/preview_section_live_run.py`만 수정했습니다.

- `--workflow {section_form, section_players}` 추가(기본 `section_form` 유지)
- `PREVIEW_NAMES_DATABASE_URL`을 환경으로 읽도록 추가 — 이게 없으면 R4 표시 이름이
  영어로 남습니다(기존 스크립트는 names 키를 싣지 않았음)
- `--one-send`(기본) 추가: `attempts_per_call=1`, `model_requests=1`,
  `normal_model_calls=1`로 **실제 전송 1회 상한**을 강제
- 실행 라벨에서 하드코딩된 `MP-05 section_form` 문구 제거
- 사용하지 않는 플래그 하나를 넣었다가 제거

dry-run으로 배선을 확인했습니다: `model: gemini-3.5-flash | location: global`,
`live_enabled: True`, 저장 경기 `Manchester City vs Fulham`, 해석기 생성 성공
(`_ResolverHandle`), 예산 `attempts_per_call=1 model_requests=1`.

## 6. 결함 수정 (조정자 A안 승인 후, 추가 전송 없이)

`app/preview/sections.py`의 `_ResolverHandle.resolve_team`만 수정했습니다.

- 실제 `DisplayNames.resolve_team`과 **같은 인자**를 받습니다
  (`value`, `team_id=None`, `external_id=None`, `id_space="internal"`).
- **실제 해석기에 위임**합니다. 이름→한국어 매칭을 새로 구현하지 않았습니다.
- 범위를 아직 읽지 않은 상태(콜드)에서는 예외 대신 `None`을 돌려주고, R4는 원래 팀
  표기를 유지합니다. 이전에는 여기서 `KeyError`로 실행이 중단됐습니다.
- 조회 범위는 **이미 읽은 그 경기의 두 팀**으로 한정합니다. 범위를 넓히지 않습니다.

## 7. 무료 검증 (추가 전송 0회)

| 확인 | 결과 |
|---|---|
| 어댑터 vs 실제 해석기 값 일치 | `Manchester City` → 양쪽 `맨체스터 시티`, `Fulham` → 양쪽 `풀럼` (**agree=True**) |
| 크래시 지점 오프라인 재현 | `resolve_selection_names` + 실제 어댑터 + 저장된 오프라인 예시 → **3건, unmapped 0, 팀 이름 모두 `db_korean`, KeyError 없음** |
| 콜드 경로 | 범위 없이 호출 시 예외 없이 `None` |
| 대표 검사 1건 추가 | `test_resolver_handle_accepts_name_only_team_lookup` 통과 |
| 영향 검사 | `test_pipeline` 16 passed, 관련 4개 스위트 **52 passed** |
| 전송 상한 확인 | 1회차 허용, 2회차 거부(시도 상한 1회) |

## 8. 산출물을 만들려면 아직 필요한 것

- **추가 실제 전송 1회**뿐입니다. 결함 수정과 무료 검증은 끝났습니다.
- 조정자가 사용자에게 추가 1회를 확인한 뒤 별도 지시하기로 했으므로, 저는 재전송하지
  않았습니다.

## 9. 한계와 정직성

- **사용자에게 보여줄 생성물이 없습니다.** 결과 본문·선정 선수·이유·매핑 상태를
  보고할 수 없습니다. 만들어지지 않았기 때문입니다.
- **과금된 전송이 결과 없이 소모됐습니다.** 이를 "성공"이나 "결과 저장"으로 표현하지
  않습니다.
- 브라우저 인증 화면은 확인하지 않았습니다(자격 증명 입력 금지).
- 유료 호출은 위 1회뿐이며, 그 외 모델·API 전송은 없습니다.

## 10. 편집 종료

수정 파일: `scripts/preview_section_live_run.py`(허용 범위), `app/preview/sections.py`
(A안 승인 후 결함 수정), `tests/preview/test_pipeline.py`(대표 검사 1건), 보고서·증거.
그 외 파일은 건드리지 않았고, 여기서 멈춥니다.

증거: [evidence/r4-one-live/01-live-run.txt](evidence/r4-one-live/01-live-run.txt),
[evidence/r4-one-live/summary.json](evidence/r4-one-live/summary.json)
