# 맨시티–풀럼 첫 실패 재현·수정 (CF-REPAIR)

작성 2026-11-19. DeepSeek 구현 워커(task_56437c49434c / ctx_7003be146090).
세션 모델 `deepseek-ai/deepseek-v4.1-flash-1017`·`hive`·`high`. 하위 워커 0.

## 판정: 원인 **미확정** — 진단 보존만 착수

로컬 재현을 시도했으나 **첫 예외를 재현하지 못했다.** 명세 §50에 따라 진단 보존 변경과
직접 검사를 인계하고, 실재현은 독립 검토 뒤 별도 배정으로 넘긴다.
**이 변경은 원인 수정이 아니다.** 진단을 남길 수 있게 만드는 것뿐이다.

## 1. 흐름 정리 (요구된 선행 설명)

`_collection_node`(bundle_pipeline.py):

1. **입력 복원** — `state["discovery"]`의 후보 dict → `discovery.Candidate`,
   `entry["record"]` → `DiscoveryGroup`, `state["db_snapshot"]` → `DbSnapshot`.
2. **자료 조회/수집** — `retrieval.collect_with_bodies(...)`: 후보마다 URL 정책 검사 →
   HTTP 홉(예산 차감) → 본문 추출 → 출처/구간 생성, 배당 정규화.
3. **묶음 검증** — `store.save_information_bundle_with_bodies` 내부에서
   `information_bundle.ensure_valid_bundle`이 계약 위반 시 `BundleBuildError`.
4. **저장** — 출처 본문 아티팩트 저장 → 묶음 아티팩트 저장(`information_bundle_saved`).
5. **commit** — 실패하면 `session.rollback()` 후 `bundle=None`,
   `diagnostics=["공통 수집이 실패했습니다: {exc}"]` 반환.

이후 `_section_node`는 `bundle`이 없으면 "정보 원문 묶음이 없어 …"로 skip하고,
`_finalize_node`는 필수 섹션 누락만 `failure_detail`로 쓴다. 진단은
`BundlePipelineOutcome.diagnostics`까지 오지만 `_generate_one`이 `unavailable_reason`만
저장해 **영속 기록에서 사라진다**(이번에 확인한 손실 지점).

## 2. 로컬 재현 시도 (실패)

저장된 run1 입력만 사용했다. 네트워크·모델·DB쓰기·테스트초기화 0.

| 시도 | 결과 |
|---|---|
| 저장된 조사 응답 → `discovery.parse_candidates` | people 5건, outlook 8건, dropped 0 → **파싱 실패 아님** |
| 그 결과로 만든 DiscoveryGroup·14 findings → `ensure_valid_bundle` | 통과 → **출처·본문이 없는 상태의** 검증 거부는 아님(실제 본문 포함 검증은 미시험) |
| 저장된 13개 후보 URL → `is_public_http_url` | 전부 `public=True`(vertexaisearch 호스트) → **저장된 URL 입력에 대한** 정책 거부는 아님 |
| 13후보 전부 HTTP 403 응답하는 대역 client로 `collect_with_bodies` 실행 | usable 0·sources 13으로 정상 종료·검증 통과 → **본문 0건 경로만** 확인 |

**범위 한정(정정).** 위 결과는 **저장된 입력으로 재현할 수 있는 범위**에만 유효하다.
특히 403 대역 실험은 **실제 200 응답 본문을 만들지 않으므로** 출처 성격·수집 방법·구간
유무·발췌 상한을 보는 전체 검증 규칙을 시험한 것이 **아니다**. "묶음 검증이 원인이 아니다"라고
단정하지 않는다 — 확인한 것은 "본문이 0건인 경로에서는 검증이 거부하지 않는다"까지다.

→ 확정: 후보 파싱 실패는 아님(저장된 응답 기준), 저장된 URL의 정책 거부도 아님.
→ **미확정**: 실제 HTTP 수집(외부 사이트 200 응답·추출)과 저장/commit 단계. 그 입력은
원 실행 당시의 실제 응답이라 저장소에 없다. 따라서 로컬 재현 불가로 판단했다.

속성상 후보로 남는 것(근거 없음, 주장하지 않음): 실제 수집 중 예외(예: 추출기·인코딩·
타임아웃 계열) 또는 저장 시 무결성 오류. **어느 것도 증거가 없다.**

## 3. 변경 (진단 보존, 최소)

### 3-1. `app/preview/bundle_pipeline.py`

- `_collection_node`의 예외 경로가 `collection_failure`를 상태에 남긴다.
- `try` 안에서 **국소 단계 변수**를 갱신해 실제 호출 전 경계를 구분한다:
  `input_restore` → `collect` → `save` → `commit`. 검증을 중복 실행하거나 호출 순서를
  바꾸지 않고 표시만 남긴다.
- `_collection_failure_detail(exc, *, stage, at=None)`가 **구조 정보만** 담는다:
  `{stage, error_kind, cause_kind, sqlstate, site, reason, at}`.
  - `error_kind`: 예외 클래스 이름.
  - `cause_kind`: DB 드라이버 예외 계열이면 `integrity`/`operational`/`programming`/`data`/
    `interface`, 저장 전 계약 검증(`BundleBuildError`)이면 `contract_violation`, 아니면 `None`.
  - `sqlstate`: 드라이버가 주는 `pgcode`(없으면 `None`).
  - `site`: **우리 코드**의 `파일:함수:행`(지역 변수 값·traceback 원문은 담지 않는다).
  - `reason`: 단계·원인종류로 만든 **고정 설명** 문장. `str(exc)`를 넣지 않는다.
  - `at`: 실제 발생 시각(UTC). `plan.moment`(고정 실행 기준시각)를 쓰지 않는다.

- `_GraphState`에 `collection_failure` 키 추가(없으면 LangGraph가 값을 버린다 — 실제로
  최소 그래프 실행으로 키 보존을 확인했다).
- `BundlePipelineOutcome.collection_failure` 필드 추가 및 `final_state`에서 채움.

단계 표시가 실제 호출 전 경계와 대응하는 방식:

| `stage` | 표시 시점(호출 전) | 그 구간에서 나는 실패 |
|---|---|---|
| `input_restore` | try 진입 | 조사 후보/그룹/DbSnapshot 파싱 |
| `collect` | 파싱 완료 직후, `collect_with_bodies` 호출 전 | URL 정책·HTTP 홉·본문 추출 |
| `save` | 수집 완료 직후, 저장 호출 전 | 묶음 계약 검증·아티팩트/묶음 쓰기 |
| `commit` | 저장 완료 직후, `session.commit()` 전 | 커밋 실패 |

- 저장 안의 **계약 검증 실패**는 `cause_kind=contract_violation`으로, 쓰기 실패는
  드라이버 예외 분류(`integrity`/`operational`/…)로 구분한다. 둘 다 `stage`가 `save`라
  구분이 필요하기 때문이다.
- 검증을 미리 성공했다고 가정하지 않고, **검증을 중복 실행하지도 않는다**. 호출 순서는
  그대로이며 표시 변수만 갱신한다.

**정정 사유(검토 지적 2).** 이전 판은 `str(exc)`를 redaction 후 300자로 잘라 넣었다.
그러나 DB 예외 본문은 `DETAIL: Failing row contains (…, 김민재, …)`, `[SQL: INSERT INTO …]`,
`[parameters: …]`처럼 **여러 줄**로 구성돼 있어, 첫 줄 절단이나 DSN·Bearer 패턴 치환으로는
행 값·SQL·테이블 구조를 막을 수 없다(검토자가 실제 형태로 확인). 그래서 자유 문구를
**아예 담지 않는** 구조화 방식을 택했다.

실제 형태의 DB 예외로 확인한 출력(누출 없음):

```
{"stage":"save","error_kind":"_NotNullViolation","cause_kind":null,"sqlstate":"23502",
 "site":null,"reason":"정보 원문 묶음 검증·저장 중 실패했습니다.",
 "at":"2026-11-18T20:11:53.087181+00:00"}
```

→ `김민재`, `INSERT INTO`, `Failing row`, `parameters:` 모두 **포함되지 않음**.

### 3-2. `app/services/home_preview_collection.py`

- `_generate_one`의 실패 기록에 `collection_failure`가 있으면 함께 넣는다.
  기존 `detail`(필수 섹션 문구)은 **그대로 유지**한다(덮지 않는다).

변경하지 않은 것: provider/retry/bundle_sections(RB 소유), 프롬프트·모델, retrieval/store
동작. 예외 삼키기·fallback·빈 본문 성공 처리·보호 제거 **0**.

## 4. 직접 검사

| 명령 | 결과 |
|---|---|
| `pytest tests/preview/test_bundle_pipeline.py tests/unit/test_home_preview_collection.py -q`(직접 2파일 1회) | **58 passed, 1 skipped** |

대표 검사(검토가 요구한 두 형태):

- `test_collection_failure_detail_carries_no_sql_rows_or_credentials` — 실제 형태의
  다중행 DB 예외(SQL·`Failing row`·선수 실명·`parameters`)를 넣어 **누출 0**과 고정 설명만
  남는지 확인. 한 줄 메시지 형태도 `reason`이 고정 문장인지 함께 본다.
- `test_commit_stage_is_reported_when_commit_raises` — **실제 `_collection_node`를 실행**해
  commit에서 예외를 내고 `stage == "commit"`·rollback을 확인. 단계 표시를 지우면 이 검사가
  실패함을 변이로 확인했다(검사가 실제로 stage를 보게 함).
- `test_collection_failure_detail_separates_contract_violation_from_write_failure` —
  저장 안 계약 검증(BundleBuildError)을 쓰기 실패와 구분.
- `test_collection_failure_detail_records_real_utc_time_not_the_fixed_moment` — `at`이
  실제 UTC이며 고정 `plan.moment`가 아님.
- `test_collection_failure_diagnostic_survives_the_required_section_message` — 진단이
  "필수 섹션 없음" 문구에 **덮이지 않고 함께** 남는지 확인.
- `test_successful_generation_has_no_collection_failure_key` — 정상 결과엔 키 없음.

기존 RB 60검사·전체 회귀는 지시대로 반복하지 않았다.

## 5. 사용자 영향 / 다음 단계

- 지금은 **버그가 고쳐지지 않았다.** 같은 실패가 재발하면 `collection_failure`
  (`stage`·`error_kind`·`cause_kind`·`sqlstate`·`site`·고정 `reason`·실제 UTC `at`)가
  `home_preview.failed[]`에 남아 **네트워크 실패인지 저장/commit 실패인지** 구분된다.
- 남기지 않는 것: 예외 원문 문구, SQL, 파라미터, 행 값, URL/DSN.
- 필요한 다음 단계(별도 배정): 진단 반영 후 **City 실패 재현 1회**로 실제 예외 확보 →
  그 예외의 원인 함수만 최소 수정 → 동일 재현 통과 확인 → 최종 E2E.

## 6. 상태

- 두 경기 5섹션 홈 확인 전 **commit/push 0**(사용자 조건 유지).
- root `collection-home-e2e-report.md`·Plans 미접촉. backup ref 보존. reset/stash 0.
- 실모델·재수집 POST·서버 재시작·운영DB 쓰기 **0회**. DB는 READ ONLY로만 읽었다.
- 이번 단위 보고서는 untracked.
