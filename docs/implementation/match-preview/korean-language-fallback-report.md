# 축구 용어 한국어 표기 + AI 번역 이름 fallback 보고

작성: 2026-11-11 05:55 KST. 담당: DeepSeek 구현 워커
(`hive` / `deepseek-ai/deepseek-v4.1-flash-1017`, `max`, 프로필 `dsh-tui`). 하위 워커 없음.

상태: **구현·무료 검증 완료. 유료 호출 0회. 편집 종료(§9).**

## 1. 한 줄 결과

사용자 피드백대로 **읽는 사람이 보는 문장에서 영어를 한국어로** 바꿨습니다. 대회·용어는
공유 사전이, 팀·선수·감독 이름은 **DB 우선 + 없으면 모델이 같은 응답에서 준 번역**이
담당합니다. 저장 본문·원문·승인은 그대로입니다.

실제 live 결과(`6176a8c6` v1)에 남아 있던 영어 6개가 모두 사라지는 것을 확인했습니다.

| before(저장된 실제 live 본문) | after(표시 변환) |
|---|---|
| `RB Leipzig` | `RB 라이프치히` |
| `Champions League` | `챔피언스리그` |
| `Coventry City` | `코번트리 시티` |
| `hat-trick` | `헤트트릭` |
| `AEK Athens` | `AEK 아테네` |
| `Enzo Maresca` | `엔초 마레스카` |

## 2. 무엇을 바꿨나

### 2.1 축구 용어·대회명 사전 (AI 아님, 고정 표기)

`app/preview/football_terms.py` 하나에 모았습니다. 모듈마다 정규식을 흩지 않습니다.

- 사용자가 지정한 표기를 그대로 씁니다: **hat-trick → 헤트트릭**, Champions League →
  챔피언스리그. 표기 연구·논쟁을 하지 않았습니다.
- **조사도 함께 고칩니다.** 단순 치환은 `clean sheet를` → `무실점를`처럼 비문을 만듭니다.
  받침에 맞춰 `무실점을`로 고칩니다(한글이 아니면 판단하지 않고 그대로 둠).
- **URL 구간은 건드리지 않습니다.** 점수·사건·신원도 바꾸지 않습니다.
- 긴 표기 우선(`UEFA Champions League` > `Champions League` > `League` 없음).

### 2.2 이름 fallback: DB 우선, 없으면 모델 번역

우선순위는 사용자 확정 그대로입니다.

1. **DB 한국어 값**(`db_korean` / `db_short_korean`)이 있으면 **그 값이 이깁니다.**
   모델이 다른 표기를 줘도 DB 값을 덮어쓰지 않습니다(검사로 고정).
2. DB에 엔티티나 한국어 값이 **없을 때만** 같은 생성 응답이 준 `korean_labels`를
   `ai_translation`으로 씁니다.
3. 둘 다 없으면 원래 표기 유지.

지킨 경계:

- 번역은 **표시에만** 씁니다. 신원·ID·소속·감독 역할을 만들지 않습니다.
- 같은 영어 표기가 이미 다른 엔티티에 묶여 있으면(충돌) 덮어쓰지 않습니다.
- `db_korean` / `ai_translation` / `original` 구분은 **관리자 진단에만** 남깁니다.
  독자 본문에는 진단 문구가 들어가지 않습니다.
- `selected_player` / `selection_reason` 분리는 그대로입니다.

### 2.3 번역은 새 호출이 아니라 기존 응답 필드

- 새 번역 호출·번역 엔진·캐시·표를 만들지 않았습니다.
- R4 계약(`players_contract.py`)과 프롬프트(`prompts/players.md`)에 **`korean_labels`**
  (최대 12개, `original`/`korean`/`kind`)를 추가해, 평소 선수 선정 응답에 함께 오게
  했습니다.
- 모델이 번역을 못 하거나 확실치 않으면 그 항목을 빼도록 프롬프트에 적었습니다.
- 예산·호출 구조는 그대로입니다(정상 호출 수 증가 없음).

### 2.4 버전

프롬프트·출력 계약이 바뀌었으므로 올렸습니다.

| 대상 | 이전 | 이후 |
|---|---|---|
| R4 구현 | `mp05p-r4-1` | `mp05p-r4-2` |
| R4 프롬프트 | `mp05p-r4-prompt-1` | `mp05p-r4-prompt-2` |
| 출력 계약 | `mp05p-r4-players-output-1` | `mp05p-r4-players-output-2` |
| `section_players` | `@0f4df25ac59c0476` | `@4e632e66c83e3549` |

기존 저장 결과(`@0f4df25ac59c0476`)와 승인은 **그대로 보존**됩니다. 표시 정정은 옛 승인을
무효화하지 않습니다.

## 3. 감독 DB 조회 — 실제 확인 결과

**감독 표는 존재합니다**(`public`):

| 표 | 확인한 열(이름 관련) |
|---|---|
| `public.coach` | `id`, `external_id`, `name` (그 외 `photo_url`, `slug`, 생성/수정 시각) |
| `public.coach_translation` | `coach_id`, `name_ko`, `short_name_ko` |
| `public.team_coach` | `team_id`, `coach_id` (그 외 리그·시즌·시각 열) |

- 현재 이름 역할(`preview_dev_names_ro`)은 **감독 표 읽기가 거부**됩니다
  (`InsufficientPrivilege`를 실제 연결로 확인).
- 프로비저너(`scripts/preview_dev_names_ro_provision.py`)에 **이름 열만** 추가했습니다
  (통계·사진·계정 열 없음, 기존 행 수정 없음, public DDL 없음).
- 그러나 **적용하지 못했습니다**: 프로비저너는 `PREVIEW_PROVISION_ADMIN_URL`(관리자 DSN)을
  요구하는데 그 값이 이 환경에 없습니다. 관리자 자격 증명을 새로 구하거나 추측하지
  않았습니다.
- 그래서 감독은 현재 **모델 번역 fallback**으로 동작합니다. 권한이 생기면 DB 값이
  자동으로 우선합니다(코드 경로는 이미 있음).
- **감독 스키마를 새로 만들지 않았습니다**(표가 이미 있으므로 불필요).

권한이 없어도 실행이 깨지지 않음을 확인했습니다: 감독 로딩은 실패 시 건너뛰고
팀·선수 해석은 정상 동작합니다.

## 4. 검증 (유료 호출 0회)

```sh
PREVIEW_TEST_DATABASE_URL=...preview_mp10_test \
  .venv/bin/python -m pytest tests/preview/test_localized_names.py tests/preview/test_pipeline.py \
    tests/preview/test_resume.py tests/preview/test_presentation.py \
    tests/preview/test_synthesis.py tests/preview/test_workflow_version.py -q
#   85 passed
```

실제 live 본문으로 확인한 것(읽기 전용 재사용, 저장 행 변경 없음):

- 영어 6개가 모두 한국어로 바뀜(§1 표)
- 저장된 live 행은 **버전·본문 길이 그대로**(`section_players@0f4df25ac59c0476` v1, 369자)
- 승인 0건 유지, 이 작업에서 쓴 행 0건(runs/attempts/artifacts 모두 0)

새 대표 검사 2건(cheap, 이번 동작에 직접 연결):

1. `test_football_terms_are_korean_and_do_not_touch_urls_or_facts` — 헤트트릭·챔피언스리그
   치환, URL 보존, 조사 교정, 고유명사·사건 문장 불변.
2. `test_db_korean_wins_over_model_label_and_missing_db_uses_it` — DB 값이 모델 표기를
   이기고, DB에 없을 때만 모델 표기를 쓰며, 신원을 만들지 않음.

## 5. 정직하게 구분해야 하는 세 가지

| 구분 | 상태 |
|---|---|
| 앞으로 생성되는 결과의 표시 | **구현됨**(모델이 `korean_labels`를 함께 내면 반영) |
| 이미 저장된 본문의 표시 | **구현됨**(읽을 때 변환, 저장 값 불변) |
| 실제 AI 번역 품질 | **미검증** — 실제 응답이 아직 `korean_labels`를 낸 적이 없습니다 |
| 감독 DB 한국어 값 | **미검증** — 역할 권한이 없어 코드 경로만 존재 |

증거의 AI 번역 레코드는 **합성(synthetic)** 이며 실제 모델 번역 증거가 아닙니다.
`korean_labels`를 실제로 받으려면 새 유료 호출이 필요하고, 이 작업은 그 권한이 없습니다.

## 6. 하지 않은 것

- 유료 모델·API 호출 **0회**. 새 live 생성 없음.
- 새 번역 엔진·캐시·표·마이그레이션 없음.
- `public` DDL·DML, 역할 생성, 기존 행 수정 없음. 승인 행 0건.
- 서술 품질 평가·문체 실험·대규모 용어/이름 행렬 없음.
- backend(8000)/frontend(5173) 재시작·종료 없음.
- `Plans.md`·정책 문서 미수정.

## 7. 변경 파일

- `app/preview/football_terms.py` (신규): 용어·대회명 사전 + 조사 교정 + URL 보호
- `app/preview/localized_names.py`: `AI_TRANSLATION` 출처, `register_model_labels`,
  감독 이름 행·로더·조회, 엔티티 키 바인딩
- `app/preview/display_names.py`: 브리지에 용어 치환·모델 라벨 등록 연결
- `app/preview/modules/players.py`: `korean_labels` 파싱·payload 전달, 버전 상향
- `app/preview/modules/players_contract.py`: `korean_labels` 스키마, `ai_translation`, 버전 상향
- `app/preview/prompts/players.md`: 번역 필드 지시(10번 항목)
- `app/preview/modules/__init__.py`, `app/preview/registry.py`: 버전·계약 등록
- `scripts/preview_dev_names_ro_provision.py`: 감독 이름 열 부여(적용은 미실행)
- `tests/preview/test_localized_names.py`: 대표 검사 2건

## 8. 재시작 필요

런타임 코드가 바뀌었습니다. 다만 이번 변경은 **읽기 시점 표시 변환**이라 저장 데이터
마이그레이션이 없습니다. 새 코드가 화면에 적용되려면 backend 8000 **재시작 1회**가
필요합니다(조정자 수행, 제가 하지 않았습니다).

## 9. 편집 종료

여기서 편집을 멈춥니다. 추가 지시는 조정자가 새 작업으로 배정해야 합니다.

증거: [evidence/korean-fallback/summary.json](evidence/korean-fallback/summary.json)
