# 맨시티–풀럼 실패 원인 조사 (CF-INV) — 인벤토리

작성 2026-11-19. DeepSeek 조사 워커(task_d76667ed60a6 / ctx_398762c178ee).
세션 모델 `deepseek-ai/deepseek-v4.1-flash-1017`·`hive`·`high`. 조사 전용, 제품/테스트 편집 0.

**결론: 원인 미확정.** 첫 예외의 원문이 영속 기록에 남지 않아 특정하지 못했다.
아래는 실제로 확인한 것과 확인하지 못한 것의 구분이다. 추정 수정은 하지 않았다.

## 1. 확정한 사실

### 1-1. 실패 정황 (조정자 제공 근거와 일치)

- 실패 run `2c8cc12d-2466-4994-8a61-dc82cd2b14b7`(fixture 1557474),
  시작 19:05:55.729847Z → 종료 19:07:25.913726Z, `status=failed`, `quality=insufficient`.
- `preview_runs.failure_detail` = `필수 섹션 본문을 만들지 못했습니다: section_ai_forecast, section_players`
  단 하나뿐이다.

### 1-2. 공통 수집(bundle) 단계가 완료되지 않았다 — 감사행 비교

`preview_write_audit`의 action 집합을 성공 run과 비교했다.

| action | run1(실패) | run2(성공) |
|---|---|---|
| `artifact_saved` | 12 | 50 |
| `attempt_appended` | 2 | 8 |
| `run_created` / `run_finished` | 1 / 1 | 1 / 1 |
| `send_charged` | 4 | 16 |
| `snapshot_recorded` | 1 | 1 |
| **`information_bundle_saved`** | **0** | **2** |
| **`module_started`** | **0** | **5** |
| **`section_result_saved`** | **0** | **5** |
| **`result_saved`** | **0** | **5** |
| `player_section_saved` | 0 | 2 |
| `player_name_candidate_saved` | 0 | 1 |

또한 run1은 `source_body` 아티팩트가 **0건**이고 run2는 **6건**이다.

→ 근거가 지지하는 경로: **공통 수집이 bundle을 저장하지 못해**
`_section_node`가 "정보 원문 묶음이 없어 …"로 skip하고, `_finalize_node`가 필수 섹션
없음만 `failure_detail`로 남겼다. 섹션 단계가 예외로 죽은 흔적(`module_started` 없음,
`section_result_saved` 없음, `module_executions` 0행)도 이 경로와 일치한다.

### 1-3. 첫 예외의 원문은 **영속 기록에 없다** (코드로 확인)

- `_collection_node`(`bundle_pipeline.py:985~1055`)는 수집·저장·커밋 전체를 `try`로 감싸고
  예외 시 `bundle=None`, `diagnostics=["공통 수집이 실패했습니다: {exc}"]`를 상태로 돌려준다.
- 그 문자열은 `BundlePipelineOutcome.diagnostics`까지 도달한다(`final_state["diagnostics"]`).
- 그러나 `home_preview_collection._generate_one`은 실패 시
  `reason="generation_status_failed"`와 `detail=outcome.unavailable_reason`만 남긴다.
  `unavailable_reason`은 finalize가 만든 **필수 섹션 없음** 문구이지 collection 예외가 아니다.
- 결과: `preview_runs.failure_detail`, `management_run.payload.home_preview.failed[]` 모두
  collection 원예외를 포함하지 않는다(실제 값으로 확인).

**즉 원인을 좁히지 못한 이유는 조사 부족이 아니라, 그 값이 저장되지 않는 구조 때문이다.**

### 1-4. 후보 파싱·bundle 검증은 원인이 아니다 (오프라인 재현)

저장된 run1 입력만 사용해 기존 순수 함수로 재현했다(네트워크·DB쓰기·모델 0).

- 저장된 조사 응답 2건을 `discovery.parse_candidates`에 넣으면
  people=**5건**, outlook=**8건**, dropped=0 → 후보 파싱 실패가 아니다.
- 그 결과로 만든 `DiscoveryGroup`·`search_findings`(14건 병합)를
  `information_bundle.ensure_valid_bundle`에 넣으면 **예외 없이 통과** → 저장 직전 계약
  검증 거부도 아니다.

→ 두 후보 가설(파싱 실패, 묶음 검증 실패)은 **근거로 기각**된다.

## 2. 확인하지 못한 것 / 철회한 추론

- **첫 예외의 예외 종류·메시지**: 어디에도 남지 않아 미확정.
- **철회한 추론 1**: "API 전송이 0회였다"는 처음에 `send_charged`의 class가 전부 `model`인
  것을 보고 판단했으나, **성공한 run2도 `send_charged` 16건이 전부 `model`인데 실제 HTTP
  수집 본문 6건을 저장**했다. 따라서 `send_charged`의 class 분포로 HTTP 발생 여부를
  판정할 수 없다. 이 추론은 근거가 없어 철회한다.
- **서버 로그**: 38000 로그에는 uvicorn access 로그만 있고 워커 스레드 traceback이 없다.
  다만 `_collection_node`가 예외를 잡아 상태로 바꾸므로 **traceback이 없는 것은 정상**이며,
  로그 부재를 원인 추정 근거로 쓸 수 없다.
- run1에 동일 artifact(sha 동일)가 일부 2건씩 있는 현상(19452·17332 응답, 4976·5519 요청)을
  확인했으나, attempts는 각 1건뿐이라 **설명하지 못했다**. 원인 후보로 주장하지 않는다.

## 3. 가장 작은 후속 수정 후보 (실행하지 않음, 승인 필요)

1. **진단 보존(1순위, 최소)**: `_generate_one`이 실패 시 `outcome.diagnostics` 중
   collection 관련 항목을 `preview_runs.failure_detail` 또는 감사 detail에 남긴다.
   그러면 같은 실패가 재발할 때 첫 예외 원문이 사라지지 않는다.
   → 이 수정은 원인 은폐가 아니라 **다음 관측 가능성**을 만드는 것이며, 원인 자체를 고치지 않는다.
2. 워커 스레드 예외 로깅: 생성 스레드의 처리되지 않은 예외를 서버 로그에 남긴다.
3. 위 1을 반영한 뒤 **1회 재현**(재수집/재생성)이 있어야 실제 예외를 특정할 수 있다.
   재현에는 새 실행 승인이 필요하다.

## 4. 상태

- 코드·테스트·기존 보고서 편집 **0**. root 문서·Plans 미접촉.
- 커밋·push **0**. 이 보고서만 untracked.
- DB는 `SET TRANSACTION READ ONLY`(on 확인) + rollback으로만 읽었다. 자격값 미출력.
- 네트워크·새 모델 호출·DB 쓰기·테스트 초기화·재수집·undo **0회**. 서버 재시작 0회.
