# BI-01~03 통합 경계 독립 검토 (읽기 전용 1회)

- 검토 시각: 2026-11-12 05:13~06:30 KST (읽기 전용 1회)
- 검토자: DeepSeek 독립 검토 세션 (구현 A/B/C와 별도). Orca `term_cbdbdf5c`, task `task_9966b18acd43`, dispatch `ctx_282fce8f1bf0`.
- 실제 모델: provider `hive`, model `deepseek-ai/deepseek-v4.1-flash-1017`, reasoningEffort `max` (`~/.dsh/sessions/--Users-woolee-benchmark--/70760de9-…/session.v4.jsonl.zstd`의 `model/selection`). 프로필/비밀값 열람·덤프 없음, 모델 변경 없음, 하위 워커 없음.
- 기준 커밋: `4d2821de089a39742ca69df377cd02425e65da9c` (작업트리 dirty, BI-01~03 변경 포함)
- **검토 중 동시 편집 발생**: 다른 워커가 검토 도중 `app/db.py`(06:15, 06:23, 06:24), `app/api/v1/auth.py`(05:56), `app/core/sessions.py`(05:56), `tests/unit/test_benchmark_preview_auth.py`(06:14), `tests/unit/test_benchmark_preview_runtime.py`(06:06, 06:26)를 수정했다. 이 검토는 **최종 스냅샷(06:28 이후 안정)** 기준으로 판정하며, 아래 B-3은 지적 시점과 최종 상태가 다르므로 따로 기록한다. 검토 도중 파일이 바뀌었으므로 B-1·B-2·B-4·B-5·D·R 항목은 최종 스냅샷에서 다시 확인한 결과다.
- 최종 스냅샷 해시(SHA-256 앞 12자, 06:28 확인): `db.py 8c3d3035257a` / `api/v1/auth.py 6d6be018a112` / `core/sessions.py 3ccb402b7b2b` / `bundle_pipeline.py c425d5b53fe1` / `retry.py 6b4037720cca` / `preview_admin.py fb423452a534` / `match_preview.py ec5d3ca92464` / `send_ledger.py d80661fe519d` / `benchmark_sessions.py fe8bbb604ead` / `preview/config.py a2c89d4da6ca` / `preview/db.py f70ecb24e4d1` / `preview/access.py 48a842da4cb4` / `PreviewPanel.vue 0a350c57c34b` / `preview.ts be8aeaedc06d` / `previewView.ts b919cf1a02a1` / `SectionRegenerationPanel.vue 2fdd9aaef041` / `CompositionPanel.vue e20dd24449dc` / `test_benchmark_preview_auth.py 39ccf03707be` / `test_benchmark_preview_runtime.py 5ad327051c11`
- 읽은 기준 문서: `Plans.md`, `docs/superpowers/specs/2026-11-12-benchmark-preview-integration.md`, `docs/superpowers/plans/2026-11-12-benchmark-preview-integration.md`(Review Focus 5개 + BI-01~03), `docs/implementation/match-preview/bi01-integration-report.md`
- 이번 검토에서 하지 않은 것: 제품/테스트/설정/스크립트 편집(유일 작성 파일은 이 보고서), HTTP, DB 연결·쓰기, 모델/생성 호출, pytest/vitest/build 실행, 새 테스트·재현 스크립트 작성. 네트워크·DB·파일쓰기가 없는 기존 순수함수(`RunBudget`)와 import 확인만 실행했다.

## 0. 판정 요약

| # | 판정 | 항목 | 근거 위치 |
|---|---|---|---|
| B-1 | **차단 (현재 수용 실패)** | preview 섹션 재생성/마지막 AI 버튼이 `mode`를 보내지 않아 서버 기본값 `mock`으로 떨어진다. "새 수집으로 재생성"은 모의 본문을, "마지막 AI 전망"은 항상 422를 돌려준다. | `SectionRegenerationPanel.vue:147-158`, `CompositionPanel.vue:161-167`, `preview_admin.py:149,816-818,913-957` |
| B-2 | **차단 (현재 수용 실패)** | `refresh` 재생성의 파생 예산이 실제 참여 모듈과 불일치한다. `module_ids`에 선택 섹션 1개만 넣어 전체 상한이 3이 되는데 refresh는 조사 모듈도 같은 예산으로 보낸다 → 3번째 전송 이후 "모델 전송 합계(3회)"로 잘린다. | `bundle_pipeline.py:2045-2054`, `2083-2123`, `retry.py:448-457` |
| B-3 | **검토 중 외부 수정으로 해소(수정 확인 필요)** | 지적 시점에는 계정 읽기 DSN(`PREVIEW_IDENTITY_DATABASE_URL`)이 실제 caller에 연결되지 않아 로그인·`/me`·ADMIN 판정이 `DATABASE_URL`(런처 기본은 fixtures DSN)로 `public.app_user`를 읽었다. 검토 도중 `app/db.py:169-212`·`api/v1/auth.py:41,97,152`·`core/sessions.py:153`이 identity 연결로 바뀌었고, 최종 스냅샷의 코드 경로는 계약을 만족한다. | 1절 B-3 참조 |
| B-4 | **차단 (현재 수용 실패)** | `tests/unit/test_benchmark_preview_auth.py`가 `DROP SCHEMA preview_dev CASCADE` 전에 loopback `*_test` 대상 검사를 하지 않는다(최종 스냅샷에서도 `assert_safe_test_database` 호출 0). `PREVIEW_TEST_DATABASE_URL` 하나로 임의 DB를 지울 수 있다. | `tests/unit/test_benchmark_preview_auth.py:24-27,111-125` |
| B-5 | **차단 (현재 수용 실패)** | BI-01 Interfaces가 요구한 "모든 preview caller·관련 검사·스크립트 import 이관"이 미완료다. `app.db`에서 제거된 `SCHEMA/Base/get_engine/get_session_factory`를 아직 import하는 preview 테스트 2개와 dev 스크립트 9개(16개 import 줄)가 `ImportError`/`AttributeError`로 죽는다. | 아래 5절 |
| D-1 | 현재 결함 (비차단) | `/section-results` 응답 실패가 빈 목록으로 바뀌어 화면이 "저장된 섹션 결과가 없습니다"로 표시한다(자료 없음 위장). 최종 스냅샷에서도 `sections_error` 없음. | `lib/api/preview.ts:61-76`, `PreviewPanel.vue:521` |
| D-2 | 현재 결함 (비차단) | 구성본으로 다른 실행의 선택 결과를 쓸 때, 그 섹션이 이 실행 `/section-results`에 없어 화면 본문에서 빠진다(서버 reader·저장에는 존재). | `previewView.ts:415-435`, `preview_admin.py:1142`, `section_preview.py:288-313` |
| R-1 | 참고 개선 | 조사(discovery) 요청에 `max_output_tokens`가 없다. 40000 상한은 작성 3회에만 적용된다. | `discovery.py:821-830`, `bundle_sections.py:1061` |
| R-2 | 참고 개선 | `app/auth/service.py`·`app/auth/tokens.py`는 앱에서 import되지 않는 죽은 코드다(A 보고 7-2와 일치). 정리 여부는 root 결정. | 4절 |

신규 지적이 **없지 않다**. 현재 시점 차단은 B-1·B-2·B-4·B-5 4건이고, B-3은 검토 중 다른 워커가 고쳐 최종 스냅샷에서 재확인이 필요하다. D/R 항목도 신규다.

## 1. 원래 앱·인증·개발 저장 경계 (검토 초점 1)

### 양호 (실제 호출 경로로 연결됨)

- **한 FastAPI 앱**: `app/main.py:86-99`가 원래 라우터(`home/auth/broadcast/admin/management/general/fixture_detail/home_preview`)와 preview 라우터를 같은 `app`에 등록한다. `/health`는 `app/main.py:80-83`에서 원래 계약 그대로다. `create_app()`은 다른 앱을 만들지 않고 모듈 `app`을 돌려준다(`app/main.py:102-106`).
- **인증 라우터 중복 없음**: `/api/v1/auth`는 `app/api/v1/auth.py` 하나뿐이고, `app/core/sessions.current_user`가 Bearer JWT를 해석한다. preview 경계 `app/preview/access.py:41-51`은 그 결과에 `role == "ADMIN"`만 추가로 요구한다(비인증 401, 비ADMIN 403). 실제 import로 확인: `app.main`, `app.services.match_preview`, `app.api.v1.preview_admin`, `app.auth.benchmark_sessions`, `app.preview.access` 모두 import 성공(DB·네트워크 미개방).
- **기존 계정 무변경(로컬 프로필)**: `app/api/v1/auth.py:97`이 `touch_last_login=not local_profile`을 넘기고, `app/services/auth.py:103-105`는 `touch_last_login=False`일 때 커밋하지 않고 반환한다. 기본값은 `True`라 운영 동작은 그대로다.
- **원격 세션 저장소 무쓰기**: 로컬 분기(`auth.py:106-109,147-165,172-178`)는 `app/auth/benchmark_sessions.py`만 호출한다. 이 모듈은 `app/core/sessions`의 `encode_token/decode_token`만 재사용하고 저장은 `preview_dev.preview_admin_sessions`(모델 `app/auth/models.py:38-39`) 한 테이블이다. 토큰 원문 대신 SHA-256만 저장하고 회전은 조건부 UPDATE 1회다(`benchmark_sessions.py:110-125`).
- **preview 새 쓰기만 `preview_dev`**: `app/preview/db.py:26,46-56`이 `SCHEMA="preview_dev"`와 `search_path` 고정. preview/auth 모델은 모두 `app.preview.db.Base`에 등록된다(`app/preview/models.py:41`, `app/auth/models.py:17`). `app/preview/`·`app/auth/` 트리에서 `app.db`/`app.core.config` import는 0건이다(전수 grep).
- **원래 public 연결 읽기 전용 강제**: `app/db.py:24-40`이 로컬 프로필에서 `default_transaction_read_only=on`을 걸고, `describe_target()`은 비밀값 없이 대상 요약만 낸다. 런처는 `WORKER_SCHEDULER_ENABLED=false`·`HOME_PREVIEW_ENABLED=false` 기본, alembic 미실행, 0600 자격 파일 검증 후 프로세스 환경으로만 전달한다(`scripts/run_benchmark_dev.sh:31-48,88-101`). 실제로 `start_worker_scheduler`는 플래그가 꺼져 있으면 `None`을 돌려준다(`app/core/worker_scheduler.py:16-21`).

### B-3 (검토 중 외부 수정으로 해소 — 재확인 필요) — 계정 읽기 DSN 연결

**지적 시점(05:5x 스냅샷)의 상태**: `PREVIEW_IDENTITY_DATABASE_URL`이 실제 caller에 연결되지 않았다.

1. `POST /api/v1/auth/login` → `login_user(session, …)`의 `session`이 `Depends(db.get_db_session)`(당시 `auth.py:39`)이어서 `DATABASE_URL` 엔진으로 `public.app_user`를 SELECT했다(`app/services/auth.py:95-97`).
2. `GET /me`·preview ADMIN 판정도 같은 경로였다: `current_user`가 `Depends(db.get_db_session)`으로 `AppUser`를 읽었다(당시 `app/core/sessions.py:145-160`).
3. `PREVIEW_IDENTITY_DATABASE_URL`을 소비하는 유일한 코드는 `app/auth/service.py:80-83`이었고 그 모듈은 앱에서 import되지 않았다.
4. 런처 기본값은 `DATABASE_URL="${BENCHMARK_READ_DATABASE_URL:-${PREVIEW_FIXTURES_DATABASE_URL:?…}}"`(`run_benchmark_dev.sh:69`)이고, fixtures 역할의 문서화된 읽기 경계는 `public.fixture/team/league/injury/standings`뿐이라 `public.app_user`가 없었다(`app/preview/sources/fixtures.py:13-16,45-52`). A 보고 6.1의 "identity DSN이면 app_user SELECT로 충분"과 실제 caller가 어긋났다.

**검토 중 변경**: 다른 워커가 `app/db.py`(06:15·06:23·06:24)·`app/api/v1/auth.py`(05:56)·`app/core/sessions.py`(05:56)·`tests/unit/test_benchmark_preview_auth.py`(06:14)·`tests/unit/test_benchmark_preview_runtime.py`를 수정했다.

**최종 스냅샷(06:28) 확인 결과 — 지적 항목은 코드상 해소됨**:

- `app/db.py:169-197` `_account_session`: 운영 프로필은 전달된 `base` 세션(=`get_db_session`)을 그대로 쓰고, 로컬 프로필만 `get_auth_session_factory()`(identity DSN)로 새 세션을 연다. 연결 실패는 `AccountConnectionUnavailable`(503)로 올려 로그인 성공·역할 우회로 바꾸지 않는다.
- `app/db.py:200-212` `get_auth_db_session(base: Session = Depends(get_db_session))` — 운영에서는 같은 요청 세션 객체를 돌려주므로 `last_login_at` 갱신·세션 저장 동작이 그대로다.
- 계정 caller가 모두 이 의존성을 쓴다: `app/api/v1/auth.py:41` `AuthSession = Annotated[Session, Depends(db.get_auth_db_session)]` → login(97)·refresh(152), `app/core/sessions.py:153` `current_user`.
- `app/db.py:120-140` `make_auth_engine`이 `_identity_url_is_configured()`로 **명시 설정을 요구**하고, `preview.assert_identity_database()`로 대상 확정·비루프백 동의를 재사용하며, `AUTH_CONNECT_ARGS`로 `default_transaction_read_only=on` + `search_path=public`을 건다.
- `describe_target()`이 `auth_connection`/`auth_same_database`/`auth_read_only`를 비밀값 없이 요약한다(`app/db.py:203-243`).
- 순환 import 없음: `app/db.py:131,234`가 함수 안에서 `app.preview.config`를 지연 import한다. 두 순서(`app.preview.config`→`app.db`, `app.db`→`app.preview.config`)로 import해 둘 다 성공함을 확인했다(네트워크·DB 미개방).
- 새 검사: `test_local_account_lookups_use_the_identity_connection`(`test_benchmark_preview_auth.py:336-449`)이 `DATABASE_URL`을 닫힌 포트(55433)로 두고도 login·`/me`·refresh·ADMIN 판정이 identity 연결(55432)로 동작함을 확인한다. `test_account_reader_keeps_the_original_connection_in_the_production_profile`(`test_benchmark_preview_runtime.py:121-160`)이 운영 프로필의 동일 세션 계약과 `auth_connection="database_url"`을 단언한다.

**남은 확인(이 검토에서 실행하지 않음)**: 이 새 검사들은 실제 DB 연결이 필요하므로 실행하지 않았다. 수정 확인 시에는 두 테스트의 통과와, 실제 자격 증명 파일에서 `PREVIEW_IDENTITY_DATABASE_URL`이 `public.app_user` SELECT만 가진 역할인지(비밀값 미노출 introspection)만 보면 된다. 런처의 `DATABASE_URL` 기본값(fixtures DSN)은 이제 계정 조회에 쓰이지 않으므로 그대로 두어도 된다.

## 2. 경기 한 번·논리 모듈별 최초 포함 3회 (검토 초점 2)

### 양호

- **단일 소유자**: `app/preview/retry.py:85` `MODULE_SEND_CAP = 3`, `for_generation`(`retry.py:293-315`)이 `module_send_cap`·`module_ids`를 세우고 `deadline_enforced=False`로 끈다. `bundle_pipeline.run_bundle_pipeline`은 정책과 다른 `module_send_cap`을 **거부**한다(`bundle_pipeline.py:1470-1474`) — 호출자가 더 좁은 상한을 다시 걸 수 없다.
- **전체 8회 병목 제거**: `effective_model_requests()`는 모듈 상한이 있으면 `3 × 모듈 수`를 돌려주고 옛 `model_requests` 값을 판정에 쓰지 않는다(`retry.py:448-457`). `can_attempt`는 모듈 상한이 있으면 그 값만 근거로 삼고 미시작 예약을 다시 빼지 않는다(`retry.py:498-534`). 순수함수 확인: 6모듈 예산에서 `effective_model_requests() == 18`, `deadline_enforced is False`.
- **전역 1800초 독립 중단 해제**: `seconds_left()`가 `inf`를 돌려줘 요청별 300초를 깎지 않는다(`retry.py:386-394`). 요청 타임아웃 상수는 `MODEL_TIMEOUT_SECONDS=300` 그대로다(`retry.py:90`).
- **다른 경기/trial 누적 차감 없음**: `module_total()`은 `sent_by_module`(이번 실행)만 보고 `prior_module_usage`는 표시용이다(`retry.py:464-476`). `can_attempt`의 거부 문구도 "이전 시험 집합의 N회는 이번 상한에 합산하지 않습니다"를 붙인다(`retry.py:498-511`).
- **기술 실패 재시도 의미**: 429·503·타임아웃은 `RETRYABLE_HTTP_STATUSES`, 401·403·400·404·422는 `PERMANENT_HTTP_STATUSES`로 즉시 STOP(`retry.py:100-156`). SDK 재시도는 `HttpRetryOptions(attempts=1)`로 꺼져 있고(`provider.py:318-321`), 재시도 루프는 `execute_request` 하나만 존재한다(`provider.py:869-930`). MAX_TOKENS/JSON 파싱 실패는 `content_check`로 같은 모듈의 남은 횟수에서 처리한다(`bundle_sections.py:1178-1189`, `1537`, `1849`, `2125`, `2554`; `discovery.py:833-837`).
- **성공 모듈 재전송 0**: `test_bundle_pipeline_does_not_refetch_or_repeat_sections`가 논리 호출 중복 0을 단언한다(`tests/preview/test_bundle_pipeline.py:470-492`).
- **모델 40000/동시 2/배당 0**: `max_output_tokens: 40000`(`bundle_sections.py:1061`), `ConcurrencyLimiter(budget_limits.model_concurrency)`=`2`(`bundle_pipeline.py:1506-1508`, 실제 적용 `796,982,1121`), 배당은 `LOGICAL_CALL_IDS[section_odds] = None`(`bundle_sections.py:111-114`)이고 `_odds_section`은 모델을 부르지 않는다(`bundle_sections.py:2211-2216`).
- **장부 보존**: 전송 전 `pending` 예약을 독립 트랜잭션으로 커밋하고, 장부를 못 쓰면 전송 자체를 시작하지 않는다(`provider.py:900-930`, `send_ledger.py:27-29`). 재개 시 `reconcile_budget_from_journal`이 장부 값이 더 크면 채택한다(`send_ledger.py:313-345`).

### B-2 (차단) — refresh 재생성의 파생 예산 불일치

재현 가능한 호출 경로: `POST /api/v1/admin/preview/section-runs` (`mode=live`, `source_mode=refresh`) → `preview_admin.py:816-846` → `bundle_pipeline.run_section_regeneration(source_mode="refresh")` → 예산 구성 `bundle_pipeline.py:2045-2054`:

```
budget.module_send_cap = MODULE_SEND_CAP            # 3
budget.module_ids = (LOGICAL_CALL_IDS[section_id],)  # 선택 섹션 1개뿐
budget.deadline_enforced = False
```

그런데 refresh 분기(`bundle_pipeline.py:2083-2123`)는 **같은 budget**으로 `discovery_module.discover_candidates`를 먼저 호출한다(조사 모듈 1개 추가 전송). `effective_model_requests()`는 `module_send_cap × len(module_ids)`이므로 **3**이다(`retry.py:455-456`). 즉 조사 2회 + 작성 1회를 쓰면 3에서 멈추고, 작성 모듈이 아직 자기 3회 중 1회만 썼는데도 "모델 전송 합계(3회)에 도달했습니다"로 잘린다.

순수함수로 재현(DB·네트워크 없음):

```
RunBudget.for_run(...); module_send_cap=3; module_ids=("section_players",)
→ effective_model_requests() == 3
charge("discovery_people") ×2 → allowed
charge("section_players") ×1  → allowed
can_attempt("section_players") → (False, '모델 전송 합계(3회)에 도달했습니다.')
module_total("section_players") == 1 / cap 3
```

사용자 영향: 새 수집을 포함한 재생성이 조사 단계에서 예산을 소진해, 모듈별 3회 정책이 실제로 시험되지 않고 부분/실패 결과가 저장된다. 계획·Review Focus 3이 금지한 "두 번째 병목"이 재생성 경로에 남아 있다.

가장 작은 수정 범위: refresh일 때 `budget.module_ids`를 **실제 참여 모듈 집합**으로 넓힌다(예: 선택 섹션 logical id + `discovery.LOGICAL_CALL_IDS[group]`). reuse는 현행(선택 섹션 1개)이 맞다. 판정식(`effective_model_requests`)은 바꾸지 않아도 된다.

## 3. 저장·조회·부분 본문·구성본 (검토 초점 3)

### 양호

- **GET은 DB만 읽는다**: `/runs/{id}/preview`(`preview_admin.py:1002-1051`), `/section-results`(`1115-1189`), `/information-bundle`(`1191-1252`), `/runs/{id}`(`287-317`) 모두 `store` 조회와 저장 행 투영만 한다. `build_bundle_reader_view`는 저장 행만 읽고 값을 만들지 않는다(`section_preview.py:253-345`).
- **품질·부분 본문으로 본문을 숨기지 않음**: `composition_section_blocks`는 본문이 있으면 `partial=True`라도 블록을 넣고, 필수 섹션은 사유만 `problems`로 분리한다(`section_preview.py:207-250`). `complete`는 표시 문턱이 아니라 진단이다. 화면도 `quality`를 게이트로 쓰지 않는다(`PreviewPanel.vue:495-520`).
- **같은 경기 선택 결과만 최종 AI로**: `resolve_selected_results`가 결과 ID마다 자기 실행을 찾고, 경기 ID가 다르면 `refused`로 거부하며, 선택되지 않은 최신 결과로 대체하지 않는다(`bundle_pipeline.py:1677-1740`). 저장된 구성본도 같은 검증을 거쳐 `composition_upstream`으로만 최종 입력이 된다(`bundle_pipeline.py:2168-2196`).
- **원문·이전 버전 보존**: 섹션 결과는 새 run에 새 행으로 쌓이고(`_save_draft` → `store.save_section_result`, `bundle_pipeline.py:434-527`), 부모 실행을 덮어쓰지 않는다. 재사용 재생성은 부모 구성본을 **복사**하고 이 실행의 새 결론만 덧붙인다(`bundle_pipeline.py:2263-2333`).
- **승인 자동 생성 없음**: 생성·재생성 경로에 `approve_section_version` 호출이 없다(전수 grep). 승인은 `POST /sections/{workflow_id}/approvals`에서만 일어난다(`preview_admin.py:426-460`, `app/preview/approvals.py:417`).
- **프롬프트/워크플로우 버전 기록**: 모듈 실행에 `prompt_version`·`contract_version`·`implementation_version`을 남기고(`bundle_pipeline.py:461-473`), 섹션 결과에 `workflow_version`·`output_contract_version`을 저장한다(`bundle_pipeline.py:500-523`).
- **새 품질 평가기 없음**: 생성 경로에 새 품질 판정·자동 재생성 훅이 없다.

### D-2 (현재 결함, 비차단) — 구성본으로 고른 타 실행 결과가 화면 본문에서 빠짐

재현 경로: 구성본이나 `upstream_result_ids`로 **다른 실행**의 섹션 결과를 고른 뒤(`section_preview.py:288-313`가 reader 응답에는 그 행을 더한다) 그 run의 `/section-results`를 열면, 서버는 `store.list_section_results(session, run_id)`로 **이 실행 소유 행만** 돌려준다(`preview_admin.py:1142`, `store.py:650-664`). 화면의 `pickSections`는 reader 블록의 `section_id`+`version`에 맞는 **로컬 행**만 고르므로(`previewView.ts:415-435`), 타 실행 결과 섹션은 `sections` map에 들어가지 않는다. 결과적으로 reader `body`에는 있는 그 섹션 본문이 관리 화면 카드·섹션 목록에서는 사라진다.

사용자 영향: 구성본으로 섹션을 골라 "이 실행"을 열면, 고른 본문 일부가 화면에 보이지 않아 선택이 적용되지 않은 것처럼 보인다. 최종 AI 전망 입력은 서버에서 정상 연결되므로 데이터 손실은 아니다.

가장 작은 수정 범위: 둘 중 하나만. (a) `/section-results`가 구성본 선택 ID의 타 실행 행도 함께 돌려준다(서버에 `get_section_result_any_run` 이미 있음), (b) `previewView`가 로컬 행이 없는 섹션에 대해 reader 블록의 `body`·`sources`로 폴백한다.

## 4. 원래 관리 UI의 실연결 (검토 초점 4)

### 양호

- **원래 4탭 + ADMIN 전용 프리뷰 탭**: `ManagementView.vue:13-25`가 기존 네 탭을 그대로 두고 `preview`만 `adminOnly`로 필터한다. `AdminView.vue`는 `ManagementView`를 그대로 마운트한다(iframe·별도 서버 링크 없음).
- **탭 자체 데이터 경계**: 프리뷰 탭에서 `refresh()`가 즉시 반환하고 수집·번역 API를 읽지 않는다(`ManagementView.vue:59-62`). 그래서 기존 관리 API 실패가 프리뷰 진입을 막지 않는다(테스트 `PreviewPanel.test.ts:853-866`).
- **진입·확인·새로고침은 무생성**: `checkFixture`(185)/`openStoredRun`(216)/`reread`(274)/`loadHistory`(279)/`toggleDiagnostics`(295)는 GET만 보낸다. POST는 `generate()`(253) 한 곳뿐이고 `generating` 가드로 더블클릭 1회, `lookupSequence`·`fixtureId.value !== requested`로 늦은 응답·입력 변경을 버린다. 테스트가 세 경우를 모두 단언한다(`PreviewPanel.test.ts:297-365`).
- **같은 run GET**: 생성 응답의 `run_id`로만 `openStoredRun(response.data.run_id, fixture)`를 호출한다(`PreviewPanel.vue:270-271`).
- **강조는 strong/text만**: `InlineEmphasis.vue`가 `**…**`를 `<strong>` 또는 텍스트 노드로만 렌더하고, 세 검토 대상 파일에 `v-html`/`innerHTML`이 없다. 테스트도 이를 단언한다(`PreviewPanel.test.ts:442-467`).
- **본문에 진단을 섞지 않음**: `MatchPreviewBody.vue`는 `preview` prop만 그리고, `missing`(사진 안내)은 `PreviewPanel.vue:515`의 접힌 진단 영역에서만 보여준다.
- **사진/로고 추측 없음**: `previewView.ts`의 `logoHref`는 서버가 준 http(s)만 통과시키고, `photo_url`은 `row.photoUrl ?? null`이다(`previewView.ts:190-196,576-583`). 내부 `player_id`로 URL을 조립하지 않는다 — 알려진 미완료(사진 nullable 필드 부재)를 그대로 반영한다.
- **버전 섞기 방지**: reader가 고른 `version`과 같은 행만 고르고, reader가 없을 때만 섹션별 최신 1건을 쓴다(`previewView.ts:415-435`). 타경기 혼입 단언도 있다(`PreviewPanel.test.ts:404-440`).

### B-1 (차단) — 재생성/마지막 AI 버튼의 `mode` 누락

재현 가능한 호출 경로 2건:

1. **섹션 재생성**: `PreviewPanel.vue:572-578`이 `SectionRegenerationPanel`을 마운트하고, 사용자가 "새 수집으로 재생성"을 눌러 `regenerate()`가 실행되면 payload는 `{workflow_id, fixture_id, source_mode, base_run_id?, base_result_id?, bundle_id?}`뿐이다(`SectionRegenerationPanel.vue:147-158`). `mode` 키가 없다.
   - 서버 `SectionRunRequest.mode` 기본값은 `RunMode.MOCK.value`다(`preview_admin.py:149`).
   - 새 경로 분기는 `workflow_id in REGENERABLE_SECTIONS and mode is RunMode.LIVE`에서만 진입한다(`preview_admin.py:816-818`).
   - 따라서 이 요청은 옛 경로로 떨어지고, `_section_implementations(mode=mock)`이 모의 구현을 돌려 모의 본문을 저장한다(`preview_admin.py:621-633`). 응답 note는 "모의 시연 실행입니다"(984-987), `no_model_call=True`(996)로 표시된다. 화면은 `describeOutcome`이 `no_model_call`을 먼저 보므로 "모델 호출 없이 처리됐습니다(외부 호출 0회)"라고 표시하고(`SectionRegenerationPanel.vue:180-186`), 저장된 본문 자체도 "…모의 시연 본문입니다 … 실제 경기 조사 결과가 아닙니다"로 시작한다(`app/preview/runner.py:988-1001`). 그래서 완전히 숨겨지지는 않지만, 사용자가 누른 "새 수집으로 재생성"과 마지막 AI 호출은 **실행되지 않고** 모의 본문이 새 실행·새 버전으로 저장된다. 계획 BI-03 항목 5가 구분하라고 한 "새 모델 호출"이 실제로 발생하지 않는다.
   - reuse일 때는 오히려 422로 정직하게 거절된다(`preview_admin.py:913-957`). 그래서 패널의 기본 동작(reuse)은 실패하고, refresh는 조용히 모의로 성공한다. 두 동작이 모두 계약과 다르다.
2. **마지막 AI 전망**: `CompositionPanel.vue:161-167`도 `{workflow_id: section_ai_forecast, fixture_id, source_mode: 'reuse', base_run_id, composition_id}`만 보낸다(`mode` 없음). 서버는 mock으로 떨어져 `source_mode="reuse"` 옛 경로 거부에 걸려 **항상 422** "정보 원문 묶음 경로로 재생성할 수 없습니다"가 된다(`preview_admin.py:929-957`).

근거 보강: `SectionRegenerationPanel.test.ts:130`이 `expect(payload.mode).toBeUndefined()`로 **결함을 계약처럼 고정**하고 있다. manifest는 같은 요청에 `"mode": "live"`를 명시한다(`docs/implementation/match-preview/section-interface-manifest.md:503`).

사용자 영향: 관리자 화면의 섹션 재생성·마지막 AI 버튼이 실제 LangGraph 경로에 닿지 못한다. 전자는 모의 본문이 실제 결과처럼 저장되어 승인 판단을 오염시키고, 후자는 기능 자체가 동작하지 않는다. 계획 BI-03 항목 5와 BI-02 Interfaces("`POST /section-runs`·composition API도 같은 인증·세션·재시도 정책을 사용한다")를 만족하지 못한다.

가장 작은 수정 범위: 두 패널이 `mode: 'live'`를 payload에 넣고, 테스트의 `toBeUndefined()` 단언을 `toBe('live')`로 바꾼다. 서버 기본값을 live로 바꾸는 방법은 쓰지 않는다(다른 호출자의 모의 시연 계약을 깬다). 모의 시연이 필요한 화면은 이미 `SectionRunView.vue:47,162`처럼 `mode`를 명시한다.

## 5. 검증 경계와 증거 (검토 초점 5)

### 양호

- `tests/preview/conftest.py:79`가 세션 autouse 픽스처에서 `assert_safe_test_database(TEST_DATABASE_URL)`를 먼저 호출하고, `engine`·`schema`가 그 픽스처에 의존한다. `_dbguard`는 URL 하나의 목적지 확정·루프백·`test_*`/`*_test` 이름을 모두 요구하며 `PREVIEW_ALLOW_NONLOCAL_DB` 우회를 테스트에서 의도적으로 무시한다(`tests/preview/_dbguard.py:1-78`).
- `tests/preview/test_retry_budget.py:290-392`는 6모듈×3회, 4번째 거부, 타 경기 독립 3회, prior 비차단, 복구 시 사용분 보존, 파생 상한 18, 전역 기한 미적용을 **실제 판정 함수**로 단언한다.
- `tests/preview/test_provider.py:558-680`과 `test_bundle_sections.py:555-625`는 MAX_TOKENS→JSON오류→정상의 3전송, 4번째 0, 짧지만 파싱 가능한 본문 재전송 0, 401 재전송 0을 기록 transport로 확인한다.
- `test_bundle_pipeline.py:495-548`은 옛 8회 상한이 판정에 쓰이지 않음과 호출자의 더 좁은 상한 거부를 확인한다.
- `PreviewPanel.test.ts`는 진입 POST 0, 확인한 1경기 POST 1, 더블클릭 1, 입력 변경 시 이전 응답 무시, reread GET only, 부분 본문 표시, 타경기 미혼입, strong-only, 배당 미합성, ADMIN 전용 노출을 단언한다. 단언 약화·가짜 writer로 실제 전달을 우회하는 흔적은 찾지 못했다.

### B-4 (차단) — unit auth 검사에 대상 제한 없음

`tests/unit/test_benchmark_preview_auth.py`는 `TEST_DATABASE_URL`을 `PREVIEW_TEST_DATABASE_URL` 환경변수에서 그대로 받고(`24-27`), autouse 모듈 픽스처에서 `DROP SCHEMA IF EXISTS preview_dev CASCADE`(`113`)와 정리 시 같은 DROP(`123`)을 실행한다. `assert_safe_test_database`/`_dbguard` import도, 루프백·`*_test` 이름 검사도 없다(전수 확인). `pyproject.toml:49`의 `testpaths=["tests"]` 때문에 전체 실행에서 이 픽스처가 돌 수 있다.

사용자 영향: 누군가 `PREVIEW_TEST_DATABASE_URL`을 개발/운영 DSN으로 지정해 이 파일만 또는 전체 pytest를 돌리면 `preview_dev` 스키마가 통째로 삭제된다. AGENTS.md의 "파괴적 fixture 전에 대상 확인" 기준과 Review Focus 5의 요구를 위반한다.

가장 작은 수정 범위: 같은 파일의 autouse 픽스처 첫 줄에서 `from tests.preview._dbguard import assert_safe_test_database` 후 `assert_safe_test_database(TEST_DATABASE_URL)` 호출(DDL 이전). conftest를 새로 만들지 않아도 된다.

### B-5 (차단) — preview caller/스크립트 import 이관 미완료

`app/db.py`가 원래 benchmark 계약(`make_engine/engine/SessionLocal/get_db_session`)으로 복구되면서 HEAD에 있던 preview 이름(`SCHEMA`, `Base`, `get_engine`, `get_session_factory`)이 사라졌다. 그런데 다음 파일이 아직 그 이름을 import한다(실제 import 실행으로 `ImportError` 확인):

| 파일 | import |
|---|---|
| `tests/preview/test_availability_module.py:80` | `from app.db import SCHEMA, Base` |
| `tests/preview/test_f2_f3_revalidation_approval.py:113` | `from app.db import SCHEMA, Base` |
| `scripts/preview_admin.py:24` | `from app.db import get_engine, reset_engine` |
| `scripts/preview_bundle_preflight.py:258` | `from app.db import SCHEMA, Base` |
| `scripts/preview_dev_mock_runs.py:64` | `get_session_factory, reset_engine` |
| `scripts/preview_grounding_one_call.py:158,181,249` | `get_session_factory` |
| `scripts/preview_model_probe.py:153` | `get_session_factory` |
| `scripts/preview_outlook_reprocess_once.py:94` | `get_session_factory` |
| `scripts/preview_r4_information_bundle_trial.py:1778,1882,2074` | `get_session_factory` |
| `scripts/preview_section_live_run.py:135` | `get_session_factory` |
| `scripts/preview_ui_fixture.py:81,89` | `get_engine, get_session_factory, reset_engine, Base` |

추가로 같은 스크립트들이 `from app.core.config import get_settings`로 옛 설정을 읽고 `settings.model_name`·`fixtures_database_url`·`model_live_enabled`를 접근한다(예: `preview_section_live_run.py:127-131`, `preview_model_probe.py:94-97,139-141`, `preview_grounding_one_call.py:246-247,283-284`). 이 필드들은 `app.core.config.Settings`에 없다(스키마 확인: 6개 필드 모두 `False`) → `AttributeError`로 죽는다. `scripts/preview_bundle_live_once.py:132-143`만 새 이름공간으로 이관돼 있다.

사용자 영향: 제품 실행 경로는 아니다(런처·앱은 영향 없음). 그러나 계획 BI-01 Interfaces가 명시한 "모든 preview caller와 관련 검사·스크립트의 import를 함께 이관한다"가 미완이고, 2개 preview 테스트가 수집 단계에서 깨져 회귀 검증 범위가 줄었다. 이번 검토에서 pytest를 돌리지 않았으므로 확인된 것은 import 실패까지이고, 해당 테스트의 단언 통과 여부는 미확인이다.

가장 작은 수정 범위: 위 표의 import를 `app.preview.db`/`app.preview.config`로 바꾸고, 스크립트의 옛 설정 필드 접근을 새 이름공간으로 옮긴다. 로직 변경 없음.

### D-1 (현재 결함, 비차단) — 섹션 결과 조회 실패가 "자료 없음"으로 표시됨

`lib/api/preview.ts:61-76`은 `sections` 호출이 실패하면 `{ run_id, section_results: [] }`로 대체하고 사유를 **버린다**(`sections_error` 필드 없음). 화면은 `storedSections.length === 0`일 때 "저장된 섹션 결과가 없습니다"를 출력한다(`PreviewPanel.vue:521`). 503·네트워크 실패와 실제 미저장이 같은 문구가 된다. 같은 함수가 `preview`·`detail` 실패는 `preview_error`/`detail_error`로 보존하는 것과 비대칭이다. `runError`도 `preview===null && sections.length===0`일 때만 세워진다(`PreviewPanel.vue:243-247`).

사용자 영향: 일시적 조회 실패를 "저장된 결과가 없다"로 오인해 재생성 같은 불필요한 작업을 하게 된다. Review Focus 5/계획 BI-03 항목 3의 "조회/저장 응답 재처리/새 모델 호출을 구분"과 "저장 API 실패를 자료 없음으로 바꾸지 않음"에 어긋난다.

가장 작은 수정 범위: `PreviewRunData`에 `sections_error`를 추가하고 실패 사유를 담아, `PreviewPanel`에서 빈 목록 대신 오류 문구를 보여준다.

## 6. 이미 알려진 미완료와의 관계

- 브라우저·로그인 연결 미검증: 그대로 남는다. 이번 검토는 서버를 건드리지 않았다. B-3은 지적 시점의 계정 DSN 미연결 문제였고 검토 중 다른 워커가 수정했으나, 실제 로그인 성공은 여전히 사용자/root 확인 몫이다.
- 사진·팀 로고 nullable 필드 부재: 코드가 정직하게 `null`로 두고 추측 URL을 만들지 않는다. 추가 지적 없음.
- 원래 home/management 읽기 권한 부족·`home_preview_*` 표 부재: 이번 검토는 계정/preview 경로만 봤다. 계정 경로는 지적 시점 B-3이 실제 blocker 후보였고, `home_preview_*` 부재는 preview ADMIN 기능의 blocker가 아니다(그 표를 읽는 코드가 preview 경로에 없다).
- 테스트 DB 잠금 충돌: 이번 검토는 DB를 연결하지 않았다. B-4는 잠금이 아니라 **대상 제한 누락**이다.
- 미사용 옛 auth/service/tokens: R-2로만 기록한다.

## 7. 한계

- pytest/vitest/build·HTTP·DB 연결·모델 호출을 하지 않았다. 따라서 "실패한다"는 판정은 소스 경로와 순수함수 실행(`RunBudget`), import 실행(파일 로드만)에 근거한다. 실제 엔드포인트 4xx/5xx와 테스트 실패 수는 이 검토에서 측정하지 않았다.
- 자격 증명 파일을 읽지 않았으므로 실데이터 로그인·권한 성립 여부는 확정하지 못했다. B-3 수정 코드의 대상 검사(`_identity_url_is_configured`·`assert_identity_database`)까지는 코드로 확인했다.
- 검토 중 다른 워커의 동시 편집이 있었다. B-1·B-2·B-4·B-5·D·R은 최종 스냅샷(06:28, 해시 위 표)에서 다시 확인했고, B-3은 지적과 수정 시점을 분리해 기록했다. 최종 스냅샷 이후 추가 편집이 있었다면 이 보고의 해당 항목은 재확인이 필요하다.
- 5173/8000이 이전 프로세스라는 사실은 그대로이며, 새 코드의 브라우저 동작은 미확인이다.
- B/C가 보고한 통과 수치(96 passed, PreviewPanel 12, MatchPreview 8, type-check exit 0)는 재실행하지 않았다. 그 수치를 수용 근거로 쓰지 않았고, 위 차단 항목은 수치와 무관하게 코드 경로로 확인했다.

## 8. 수정 확인 시 볼 범위 (후속, 지적 항목만)

1. B-1: 두 패널 payload의 `mode`와 `SectionRegenerationPanel.test.ts:130` 단언(`toBeUndefined()` → `toBe('live')`).
2. B-2: `run_section_regeneration`의 refresh 분기 `budget.module_ids`와 그 경로의 새/기존 테스트 중 최소 1건.
3. B-3: 이미 수정됨. `test_local_account_lookups_use_the_identity_connection`·`test_account_reader_keeps_the_original_connection_in_the_production_profile` 통과 확인만.
4. B-4: unit auth 테스트의 guard 호출 위치(DDL 이전).
5. B-5: 위 표 11개 파일 + 스크립트 3개 설정 필드.
6. D-1·D-2: `sections_error` 표시와 구성본 타 실행 행 표시. 회귀 확인은 영향 경로만.

## 9. 수정 확인 (원 지적 B-1~B-5/D-1/D-2 한정) — 2026-11-12 07:03~07:33 KST

- 확인자: DeepSeek 독립 검토 세션(구현 A/B/C와 별도). 실제 모델 provider `hive`, model `deepseek-ai/deepseek-v4.1-flash-1017`, reasoningEffort `max`(`~/.dsh/sessions/--Users-woolee-benchmark--/dc582aa3-…/session.v4.jsonl.zstd`의 `model/selection`). 모델 변경·하위 워커 없음.
- 이번에 **하지 않은 것**: 제품/테스트/설정/`Plans.md` 편집, pytest/vitest/build, HTTP, DB 연결·쓰기, 모델 호출, 새 재현 스크립트 작성, 전체 재검토. B 최종 증거(integration 28 / pipeline 17 / retry 20)와 A/C 인계 수치(vitest 33·type-check 0, auth+runtime 21)는 **재실행하지 않고 인계 근거로만** 대조했다. 이 절의 실행은 순수함수 호출(`_dbguard.assert_safe_test_database`, DB 미연결)과 정적 분석(`pyflakes 3.0.1`, `ast`/`symtable`/`dis`)뿐이다.
- 유일 작성 파일: 이 보고서(수정 전 해시 `4b9d115094f1`). 아래 내용은 현재 작업트리 파일 기준이다.

### 9-1. 현재 파일 해시 (SHA-256 앞 12자, 07:31 기준)

| 파일 | 현재 | 원 검토 06:28 스냅샷 |
|---|---|---|
| `app/db.py` | `8c3d3035257a` | 동일 |
| `app/api/v1/auth.py` | `6d6be018a112` | 동일 |
| `app/core/sessions.py` | `3ccb402b7b2b` | 동일 |
| `app/preview/retry.py` | `6b4037720cca` | 동일 |
| `app/preview/config.py` | `a2c89d4da6ca` | 동일 |
| `app/api/v1/preview_admin.py` | `fb423452a534` | **동일** |
| `app/preview/bundle_pipeline.py` | `e3a5ffbcdbb0` | `c425d5b53fe1` (B-2 수정 반영) |
| `frontend/src/features/match-preview/SectionRegenerationPanel.vue` | `75b25b935f1b` | `2fdd9aaef041` |
| `frontend/src/features/match-preview/CompositionPanel.vue` | `37722dadbbf4` | `e20dd24449dc` |
| `frontend/src/components/management/PreviewPanel.vue` | `fb71019351de` | `0a350c57c34b` |
| `frontend/src/lib/api/preview.ts` | `10a510d037d6` | `be8aeaedc06d` |
| `frontend/src/lib/api/previewView.ts` | `1f48b6e4dad4` | `b919cf1a02a1` |
| `tests/unit/test_benchmark_preview_auth.py` | `e037d4d77056` | `39ccf03707be` |
| `tests/unit/test_benchmark_preview_runtime.py` | `5ad327051c11` | 동일 |
| `tests/preview/test_bundle_integration.py` | `6de5fde1eb9d` | — (B-2 검사 추가) |
| `tests/preview/test_availability_module.py` | `9ce6d272c28c` | — (import 이관) |
| `tests/preview/test_f2_f3_revalidation_approval.py` | `54ce2bca16e6` | — (import 이관) |

`bundle_pipeline.py`·`preview_admin.py`·`tests/unit/*`·`frontend/src/lib/api/*`·`PreviewPanel.vue`·두 패널은 작업트리에서 untracked(`??`)이거나 HEAD와 다른 상태다. `preview_admin.py`가 원 검토 스냅샷과 **같은 해시**라는 사실은 9-3의 E-1이 이번 수정이 만든 것이 아님을 뜻한다.

### 9-2. 원 지적별 판정

| # | 원 지적 | 현재 판정 | 근거 |
|---|---|---|---|
| B-1 | 재생성/마지막 AI 버튼 `mode` 누락 | **요청 필드·검사 해소** (사용자 결과는 E-1·E-2로 미달) | 아래 9-2-1 |
| B-2 | refresh 파생 예산 불일치 | **해소** | 아래 9-2-2 |
| B-3 | 계정 identity DSN 미연결 | **해소 유지**(코드 무변경, 인계 21통과) | 9-2-3 |
| B-4 | unit auth 검사에 대상 제한 없음 | **해소** | 9-2-4 |
| B-5 | preview caller·스크립트 import 미이관 | **해소** | 9-2-5 |
| D-1 | 조회 실패를 "자료 없음"으로 표시 | **해소** | 9-2-6 |
| D-2 | 구성본 타 실행 섹션이 화면에서 빠짐 | **해소**(같은/다른 실행 version 숫자 충돌은 잔여) | 9-2-7 |

#### 9-2-1. B-1 — `mode: 'live'` 명시와 검사

- `SectionRegenerationPanel.vue:152-158`가 `mode: 'live'`를 payload에 넣고, 이유를 주석으로 남겼다. `regenerate()`는 사용자 클릭에서만 호출되고, reuse인데 `bundleId`가 없으면 요청 자체를 보내지 않는다(`:147-151`). 재처리(`reprocess`)는 별도 경로로 모델 호출 0회다(`:211-228`).
- `CompositionPanel.vue:165-173`가 `regenerateSection({workflow_id: FINAL_SECTION, mode: 'live', source_mode: 'reuse', base_run_id, composition_id})`로 보낸다.
- 검사: `SectionRegenerationPanel.test.ts:124-134`(클릭 1회·`payload.mode === 'live'`·`bundle_id`), `:165-168`(refresh도 `mode === 'live'`, `bundle_id` 없음), `:95`(마운트만으로 `regenerateMock` 0회), `CompositionPanel.test.ts:99-104`(마운트 시 save/run 0회), `:116-123`(`mode === 'live'`). 원 검토가 지적한 결함 고정 단언(`expect(payload.mode).toBeUndefined()`)은 두 파일에서 **0건**이다.
- 서버 계약은 그대로다: `SectionRunRequest.mode` 기본값 `mock`(`preview_admin.py:149`), 새 경로 진입 조건 `workflow_id in REGENERABLE_SECTIONS and mode is RunMode.LIVE`(`preview_admin.py:816-819`). 기본값을 live로 바꾸지 않았고 `SectionRunView.vue:47,162`의 명시적 mock UI도 그대로다. 즉 B-1이 지적한 "payload에 mode가 없어 mock으로 떨어짐"은 현재 파일에서 재현되지 않는다.
- 다만 **사용자 결과는 아직 미달**이다. mode를 명시해 새 경로에 들어가면 E-1(`preview_admin.py:873` `version_manifest` NameError)이 응답 생성에서 항상 터지고, 구성본 경로는 E-2(`bundle_pipeline.py:2330/2348` 미할당 지역변수)로 그 전에 멈춘다. 두 건 모두 9-3에 따로 적었다.

#### 9-2-2. B-2 — refresh 참여 모듈 집합

- 예산은 `regeneration_logical_call_ids(section_id, source_mode=...)`로 **첫 전송 전에** 확정한다(`bundle_pipeline.py:2095-2099`). 이 함수는 refresh에서 조사 1개 + 선택 작성 모듈을, reuse에서 선택 작성 모듈만 돌려준다(`:1907-1933`). 배당(`section_odds`)은 `bundle_sections.LOGICAL_CALL_IDS[SECTION_ODDS] is None`(`bundle_sections.py:111-114`)이라 목록이 비고 기존 전체 상한 경로를 쓴다.
- 실제 조사 호출도 **같은 함수**를 쓴다: refresh 분기의 `group = regeneration_discovery_group(section_id)`(`:2149`) — 예산과 호출이 한 곳에서 갈라지지 않는다.
- 순수 판정: refresh `("discovery_people","section_players")` → `effective_model_requests() == 6`(3×2), reuse `("section_players",)` → 3, 배당 reuse → 빈 목록. `can_attempt`는 모듈 상한이 있으면 파생 합계만 본다(`retry.py:527-534`). 원 지적의 "3에서 잘림"은 현재 파일에서 재현되지 않는다.
- 검사: `test_bundle_integration.py:943-1033` `test_regeneration_budget_covers_the_modules_that_refresh_actually_runs`가 위 목록·6 상한·4번째 거부를 단언하고, 기록 transport로 조사 3전송(503×2 후 성공)+작성 3전송=6과 진단 문구를 확인한다. transport는 `RecordedTransport`(`mode=LIVE`, 네트워크 없음)이고 `retry_after_seconds=0`이다. 인계된 integration 28건에 이 검사가 포함되며, 나는 재실행하지 않았다.
- 수정 범위도 원 지적의 "가장 작은 수정"과 일치한다: `module_ids`만 실제 참여 집합으로 넓히고 판정식은 건드리지 않았다.

#### 9-2-3. B-3 — identity 연결

- `app/db.py`·`app/api/v1/auth.py`·`app/core/sessions.py`의 해시가 원 검토 최종 스냅샷과 **같다**(9-1). 즉 06:28 이후 편집이 없고, 원 보고 1절이 확인한 계약이 그대로다: `get_auth_db_session(base)`(`db.py:200-212`), `AuthSession = Depends(db.get_auth_db_session)`(`auth.py:41` → login 97 · refresh 152), `current_user`(`sessions.py:153`), `_identity_url_is_configured`·`assert_identity_database`·`AUTH_CONNECT_ARGS`(`db.py:73-147`).
- 인계 근거 대조: `test_benchmark_preview_auth.py` 13개 정의(7: 차단 목록의 13건과 일치) + `test_benchmark_preview_runtime.py` 8개 = **21**. 인계의 "auth/runtime 최종 21통과"와 수가 맞는다. 다만 나는 실행하지 않았으므로 통과 사실은 인계 근거다.
- 새 검사 두 건의 계약도 원 보고와 같다: identity 연결 선택·좁은 읽기 옵션·`DATABASE_URL` 닫힌 포트(`test_benchmark_preview_auth.py:343-455`), 운영 프로필 동일 세션·`auth_connection="database_url"`(`test_benchmark_preview_runtime.py:121-160`). 같은 요청 세션 보존·로컬 identity caller 연결을 확인하는 기존 증거를 재사용했고 재실행하지 않았다.

#### 9-2-4. B-4 — unit auth 검사의 대상 제한

- `tests/unit/test_benchmark_preview_auth.py:25`가 `assert_safe_test_database`를 import하고, autouse 모듈 픽스처 **첫 문장**에서 호출한다(`:73`). 환경변수 변경(`:75-77`)·엔진 재생성(`:113`)·DDL(`:118-122`)·정리 DROP(`:130`)보다 앞선다. 즉 연결·환경변경·DDL 전에 대상 판정이 끝난다.
- 거부 동작은 실행 없이 확인했다(순수함수, DB 미연결): `preview_mp01_test` → 수용(`127.0.0.1:55432`), `preview_mp01_dev` → `UnsafeTestDatabase`. 가드 자체의 거부 사유는 기존 `tests/preview/test_db_isolation.py:28-70`이 개발/운영/공유 기본 DB·비루프백·sqlite·우회 플래그를 모두 단언한다.
- 인계의 "auth 13통과"는 이 파일의 정의 수 13과 일치한다(실행은 하지 않음).

#### 9-2-5. B-5 — preview caller·스크립트 import 이관

- 원 지적 표의 11개 파일이 모두 `app.preview.db`/`app.preview.config`로 옮겨졌다: 테스트 2건(`test_availability_module.py:80`, `test_f2_f3_revalidation_approval.py:113`)과 스크립트 9건(`preview_admin.py:23-24`, `preview_bundle_preflight.py:258`, `preview_dev_mock_runs.py:63-64`, `preview_grounding_one_call.py:158,181,242,249`, `preview_model_probe.py:125,153`, `preview_outlook_reprocess_once.py:88,94`, `preview_r4_information_bundle_trial.py:2348`, `preview_section_live_run.py:123,135`, `preview_ui_fixture.py:80-81,89`).
- 정적 전수 감사(ast): `from app.db import SCHEMA|Base|get_engine|get_session_factory` 잔존 **0건**(app/tests/scripts 전체). `scripts/`에 `app.db`·`app.core.config` 참조 **0건**. 스크립트가 `app.preview.db`에서 가져오는 이름은 모두 실제 정의되어 있고(누락 0), 옛 설정 필드(`model_name`·`model_live_enabled`·`model_location`·`fixtures_database_url`)도 `app.preview.config.Settings`에 존재한다(`config.py:57-88`).
- 원래 benchmark import는 보존됐다: 두 테스트의 변경은 **각 1줄**(import 경로)뿐이고(`git diff`: 2 files, +2/−2), 나머지 기존 import·픽스처·단언은 그대로다. 스크립트 tracked 6건의 diff도 `app.core.config`→`app.preview.config`, `app.db`→`app.preview.db` 치환만이다.
- collect 30 / import 9 증거는 인계 근거로 재사용했고 스크립트 `main`은 실행하지 않았다.

#### 9-2-6. D-1 — 조회 실패와 빈 목록 구분

- `frontend/src/lib/api/preview.ts:47,83`이 `sections_error`를 두고 실패 사유를 보존한다(빈 목록 대체와 별개로 사유 유지).
- `PreviewPanel.vue:562-572`이 `sections_error`가 있으면 "읽지 못했습니다(자료 없음이 아닙니다). {사유}"를, 없을 때만 "저장된 섹션 결과가 없습니다."를 쓴다. 실행 전체 오류도 읽힌 본문이 하나도 없을 때만 세우고 사유를 함께 남긴다(`:273-284`). 재생성·구성본 영역도 조회 실패를 별도 문구로 알린다(`:614`, `:644`).
- 검사 `PreviewPanel.test.ts:555-601`이 503 실패에서 ①조회 오류 문구+사유 표시 ②"저장된 섹션 결과가 없습니다" 미표시 ③`preview-run-error` 없음 ④읽힌 독자 본문 유지 ⑤생성·재생성 POST 0회를 단언한다.

#### 9-2-7. D-2 — 구성본 타 실행 섹션 표시

- `previewView.ts:469-504` `readerOnlySections`가 **로컬 행이 없는 섹션만** reader 블록의 `body`·`sources`로 채우고 `from_reader_selection: true`를 남긴다. 합성 루프(`:579-585`)는 로컬 행이 있는 섹션을 덮어쓰지 않는다(`if (sections[sectionId]) continue`). `pickSections`는 reader가 고른 (section, version)과 같은 **로컬** 행만 고르고, reader가 없을 때만 섹션별 최신 1건을 쓴다(원 보고 4절의 버전 섞기 방지 유지).
- 진단 영역은 사유를 나눈다: 조회 실패면 "독자 응답에서 읽은 섹션", 구성본 선택이면 "구성본이 고른 다른 실행의 섹션"(`PreviewPanel.vue:178-188`), "임의의 최신 버전으로 바꾸지 않습니다" 문구 포함(`:673-690`).
- 검사 `PreviewPanel.test.ts:604-679`가 로컬 행 목록에 없는 `section_players` 본문·근거 URL을 표시하고, `v3` 등 reader 선택 버전을 그대로 쓰며, 조회 오류 문구를 쓰지 않음을 단언한다.
- **잔여(비차단)**: 선택 결과를 **ID로** 맞추는 계약이 화면까지 내려오지 않는다. reader 블록은 `section_result_id`를 담지 않고(`section_preview.py:236-248`), 섹션 결과 버전은 실행 단위로 1부터 다시 매겨진다(`bundle_pipeline.py:417-431`). 그래서 "이 실행에 같은 섹션·같은 version 숫자의 로컬 행이 이미 있는" 경우 `pickSections`가 reader가 고른 타 실행 결과 대신 로컬 행을 고를 수 있다. 현재 정상 경로(재생성 1회 실행은 자기 섹션 행 하나만 가짐)에서는 충돌하지 않아 원 지적의 재현 사례는 해소됐지만, 같은 실행에서 같은 섹션을 여러 번 만든 뒤 타 실행 결과를 고르는 조합은 남아 있다. 선택 ID 계약/저장 경로를 새로 설계하지 말라는 지시에 따라 여기 기록만 한다.

### 9-3. 이번 확인에서 새로 드러난 두 건 (수정 회귀 아님 · 정적 판정)

두 건 모두 **실행으로 확인하지 않았다**(pytest/HTTP 금지). `pyflakes 3.0.1`과 `ast`/`symtable`/`dis`로만 판정했고, 그 근거를 함께 적는다.

**E-1 — `preview_admin.py:873` `version_manifest` 미정의 (live 재생성 응답이 항상 실패)**

- `create_section_run`의 live 재생성 반환부가 `workflow_version=version_manifest.workflow_version_of(...)`를 쓴다. 이 모듈은 `version_manifest`를 import하지 않고(모듈 스코프 바인딩 없음), 함수 안 지역 import도 없다(함수 내 import는 `app.preview` → `bundle_pipeline_module` 하나뿐). star import·`globals()` 주입·모듈 `__getattr__`도 없다.
- 정적 근거: `pyflakes` → `app/api/v1/preview_admin.py:873:30: undefined name 'version_manifest'`. 컴파일 코드 객체의 `co_names`에 `version_manifest`가 있고 `co_freevars`/`co_cellvars`는 비어 있다 → 전역 조회 → `NameError`.
- 실행 순서상 `session.commit()`(`:869`) 뒤 응답 생성에서 터지므로, 저장은 남고 응답은 500이 된다. 즉 B-1로 mode를 명시해도 "새 수집으로 재생성"·"마지막 AI"의 live 응답은 사용자에게 실패로 보인다.
- **회귀 아님**: 이 파일 해시가 원 검토 스냅샷(`fb423452a534`)과 같다(9-1). 즉 원 검토가 읽은 파일에 이미 있던 결함이고, 이번 B-1~B-5/D 수정이 만든 것이 아니다. 원 검토가 이 줄을 지적하지 못한 것은 내 누락이다.

**E-2 — `bundle_pipeline.py:2330/2348` 미할당 지역변수 (`quality`·`unavailable`·`row`)**

- `run_section_regeneration`의 "구성본을 새 run에 복사" 블록(`:2317-2355`)이 `row.version`·`quality.value`·`unavailable`을 읽는데, `quality`·`unavailable`은 `:2386-2387`에서, `row`는 `:2265`(다른 분기)와 `:2397`(이후)에서만 대입된다. bytecode `LOAD_FAST`가 첫 `STORE_FAST`보다 앞선다(`quality` 2회·`unavailable` 4회). `pyflakes` → `:2331,2332,2333,2349,2350,2351: undefined name ...`.
- 도달 조건: `upstream_items`가 비어 있지 않은 재생성. 즉 ①저장된 구성본으로 마지막 AI를 다시 만드는 경로(구성본 항목에 이 섹션이 없으면 `:2341-2355`를 타고 `row` 미할당 → `UnboundLocalError`)와 ②`selected_result_ids` 경로(`:2264-2272` 루프의 마지막 `row`를 그대로 읽어, 새 결과의 version/quality를 **다른 항목 행** 값으로 기록)다. ①은 CompositionPanel의 "마지막 AI" 실행이 서버에서 완료 전에 멈춘다는 뜻이고, ②는 저장되는 구성본 항목의 표시 메타데이터가 어긋난다는 뜻이다.
- **회귀 여부 불명**: 이 블록은 이전 보고(`search-fallback-review.md:496-500`)가 이미 "해결"로 서술한 기존 코드이고, `bundle_pipeline.py`가 untracked라 수정 전 내용과 비교할 baseline이 없다. B-2의 예산 변경(`:2095-2099`)과는 다른 위치다.
- 참고: `tests/` 전체에 구성본 관련 단언이 0건(`grep -c "composition" tests/` = 0)이라, B의 integration 28건이 통과해도 이 경로는 검사되지 않는다.

### 9-4. 이번 확인의 한계

- pytest/vitest/build/HTTP/DB/모델 호출을 하지 않았다. B-1·B-2·B-3·B-4·B-5·D의 "해소" 판정은 소스 경로와 인계된 실행 증거(integration 28 / pipeline 17 / retry 20 / vitest 33·type-check 0 / auth+runtime 21) 대조에 근거한다. vitest 33은 인계가 지목한 영향 4파일의 `it(` 정의 수 합(8+2+17+6)과 일치한다.
- E-1·E-2는 정적 분석 판정이며 실제 500 재현은 하지 않았다. 조정자가 실행으로 확정하려면 영향 경로 1건씩이면 충분하다(전체 재검사 불필요).
- 새 전체 심사·새 기능 제안·테스트 확대는 하지 않았다. R-1/R-2는 이번 범위가 아니므로 그대로 둔다.

EDITING STOPPED.
