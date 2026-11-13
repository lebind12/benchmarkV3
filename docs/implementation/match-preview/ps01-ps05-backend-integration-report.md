# PS-01·PS-05 백엔드 통합 인계 보고

작성: 2026-11-11T13:33:40+09:00 (KST). 담당: A 통합 책임자(Orca dsh-tui DeepSeek 구현 워커).
성격: **구현·자체 검증 기록**이다. 사용자 승인도, 실제 유료 실행 완료도 아니다.

## 결론 먼저

- 새 기본 경로(정보 원문 묶음 → 섹션 5개 → 저장)가 **백엔드에서 끝까지 동작**한다.
  관리자 API `POST /api/v1/admin/preview/bundle-runs`로 실행하고, `run_id`로 섹션 본문·
  정보 원문 묶음을 다시 연다.
- 기록 transport로 정상 **모델 6회**(조사 2 + 작성 3 + 최종 1)가 확인됐고, 배당은 0회다.
  전체 실제 전송 상한 8회·동시 2회·HTTP 24회 공유가 유지된다.
- 검사: `tests/preview` **454 passed**(`test_outlook_module.py` 제외 — 아래 참조).
  기록 preflight 9개 항목 all_passed. **유료 모델 호출 0회**, git stage/commit 0회.
- 남은 것: **실제 live 1회 실행**과 그 결과 확인. 서버 재시작 여부는 조정자가 순서를 정한다.

## 이번에 만든/고친 것

### 신규 파일

| 파일 | 역할 |
|---|---|
| `app/preview/information_bundle.py` | 정보 원문 묶음 계약(`InformationBundle`·`BundleSource`·`Passage`·`DbSnapshot`·`DiscoveryGroup`·`OddsMarket`·`SectionDelivery`·`DeliveryLimits`) + 검증·요약·B 결과 어댑터 |
| `app/preview/send_ledger.py` | 전송 사용량 **내구 장부**(전송 전 예약 + 응답 직후 결과, 독립 트랜잭션) |
| `app/preview/bundle_pipeline.py` | 새 기본 경로 실행기(조사2 + 수집 + 작성3 + 배당0 + 최종1 + 저장) |
| `app/preview/section_structured.py` | 저장 payload → 화면 구조 값(선수/부상/매체/1X2/AI 예상) |
| `docs/implementation/match-preview/section-interface-manifest.md` | 공유 연결 계약(이름·응답 모양·소유권) |
| `scripts/preview_bundle_preflight.py` | 기록 전송 preflight(9 checks, 유료 0회) |
| `tests/preview/test_bundle_runtime.py` (11) | 내구성·상한·예약반환·장부 노출 |
| `tests/preview/test_bundle_integration.py` (16) | 묶음 저장/조회·전문·재생성·구조화 |
| `tests/preview/test_bundle_pipeline.py` (7) | 새 경로 전체 + 관리자 라우트 |
| `tests/preview/test_bundle_sections.py` (10) | C 작성 어댑터 대표 동작 |

### 수정(내 소유 경로)

- `contracts.py`(변경 없음), `provider.py`, `retry.py`, `store.py`, `pipeline.py`,
  `registry.py`, `version_manifest.py`, `inspection.py`, `preview_admin.py`,
  `core/config.py`, `sources/player_stats.py`, `scripts/preview_dev_stats_ro_provision.py`,
  `frontend/.../informationBundle.ts`(주석)·`SectionRunView.test.ts`(픽스처 이름).

### 다른 워커 파일

- B: `discovery.py`(now 인자 처리 1줄 수정), `retrieval.py`, `sources/player_stats.py`
  (11열 정리) — 인계 후 최소 수정.
- C: `modules/bundle_sections.py` + `prompts/bundle_*.md` **보존**(중단 시점 그대로),
  컴파일·동작 확인만 하고 필요한 최소 수정만 했다.
- D: 프론트 구조는 그대로, 옛 필드 이름(`delivered_passages`)만 새 이름으로 정리.

## 실행 예산 (실측)

| 항목 | 값 | 근거 |
|---|---|---|
| 정상 모델 호출 | **6** (조사 2 + 작성 3 + 최종 1) | `test_bundle_pipeline_normal_path_six_model_calls` |
| 배당 섹션 모델 호출 | **0** | `test_odds_section_makes_no_model_call` |
| 전체 실제 전송 상한 | 8 (불변) | `NORMAL_MODEL_CALLS=6`, `MODEL_REQUEST_BUDGET=8` |
| 미시작 확정 호출 예약 반환 | 동작 | `test_reservations_return_for_cancelled_calls_without_raising_the_cap` |
| 재시작 후 상한 | 초기화되지 않음 | `test_restart_does_not_reset_the_eight_send_cap` |
| 전송 직후 예외·롤백 | 원문·사용량 보존 | `test_live_send_and_usage_survive_post_processing_failure` |
| 전송 전 크래시 | 예약이 사용량으로 남음 | `test_presend_crash_keeps_the_reservation_counted_and_reports_it` |
| 비모델 HTTP | 24 공유, 실패·리다이렉트도 계수 | `bundle_summary()['network_usage']` |

## 정직성 경계 (구현된 그대로)

- **전달 후보와 실제 전달을 섞지 않는다.** `available_passages[]`는 후보이고, 실제 전달은
  `section_deliveries[]`(`payload_sha256`·`passage_ids`·`sent_attempts`)만 주장한다.
- **배당은 선택**이다. 불완전·미지원 배당 줄은 채택하지 않고 진단으로만 남기며, 묶음
  검증이나 필수 작성(전망·점수·주목 선수)을 막지 않는다.
- **필수 섹션 본문이 없으면 정상 완료로 표시하지 않는다**(`status=failed`).
- **자료가 전혀 없으면** 최종 전망 요청을 보내지 않고 예약을 반환한다.
- 기사↔DB 교차 검증·Google `grounding_chunks` 필수 조건·별도 사실 심사 엔진은 **없다**.
- 모의 결과는 `mode=mock`으로 남고 승인 근거가 아니다. 새 경로는 mock 실행을 거부한다.

## 남은 일

1. **실제 live 1회**(fixture 1557474, 정상 6/최대 8) — 서버 설정 확인과 재시작 순서를
   조정자가 정한 뒤 실행. 이 보고는 그 실행 전 상태다.
2. 사용자 확인: 실행 후 `GET /runs/{id}/section-results`(본문+구조화)와
   `GET /runs/{id}/information-bundle`(출처·구간·DB·배당)로 눈으로 확인.
3. `test_outlook_module.py`의 15건 실패는 **기존 테스트 시계 문제**다(테스트가
   `MOMENT=2026-11-10T16:00Z`를 고정해 예산 기한이 이미 지난 상태로 실행됨). 내 변경과
   무관하며, coordinator 지시대로 이번 작업에서 고치지 않는다.
4. 프론트(v2 패널)는 D 소유 파일이며, 백엔드 구조화 값·묶음 응답과의 최종 연결 확인은
   D의 실제 중단 확인 후 진행한다.

## 검사 명령(재현)

```sh
.venv/bin/python -m pytest tests/preview -q --ignore=tests/preview/test_outlook_module.py
PREVIEW_TEST_DATABASE_URL='postgresql+psycopg://preview:preview_local_dev@127.0.0.1:55432/preview_mp01_test' \
  .venv/bin/python scripts/preview_bundle_preflight.py --json
npm --prefix frontend run type-check
npm --prefix frontend run test:unit -- src/features/match-preview/InformationBundlePanel.test.ts
```

**EDITING STOPPED** — 이 보고 시점 이후 내 소유 경로에 자율 편집을 하지 않는다.
추가 수정은 조정자 지시가 있을 때만 한다.
