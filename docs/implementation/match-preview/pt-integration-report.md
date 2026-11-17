# PT-INTEGRATE C 보고 — 병합·필수 타입 수정·연동 준비

작성: 2026-11-17 KST. 담당: DeepSeek 구현 워커 C (Orca `term_f06526cd`).
Task `task_d2a22b8d02ad` / Dispatch `ctx_55e8c1269bbc`.

워크트리 `preview-test-integration`, 시작 기준 HEAD `07e6cdc0f9c174b08337fcded81fb6f90f03bc42`
(branch `lebind12/preview-test-integration`), 착수 시 clean.

실제 모델: 세션 `7e643c5b-e227-41dc-a9ab-ca1441216ac7` 메타데이터 `model/selection` =
`provider=hive`, `model=deepseek-ai/deepseek-v4.1-flash-1017`, `reasoningEffort=high`.
모델·추론 강도를 바꾸지 않았고 다른 백엔드로 대체하지 않았다.

읽은 문서: `.agents/skills/poteto-mode/SKILL.md` 전문,
`docs/superpowers/plans/2026-11-17-preview-test-ui.md` 전문,
`docs/superpowers/specs/2026-11-17-preview-test-ui-design.md` 전문, B 보고서 §10.

적용한 원칙과 그것이 바꾼 결정:

- `principle-laziness-protocol` — 타입 오류는 보고된 5건만 고쳤다. 어댑터의 다른 구조와
  타입 파일 전체를 정리하지 않았다.
- `principle-prove-it-works` — 모의 대역 통과와 실제 수집·실제 AI 호출을 문서에서 분리해
  적었다. 실제 호출은 0회다.
- `principle-boundary-discipline` — 서버가 주는 `{code, message}`와 nullable 필드는
  경계 파서에서만 해석하고, 내부 화면 코드는 해석된 값만 받는다.
- `principle-fix-root-causes` — 새로고침 복원의 위치 기반 짝짓기는 증상(잘못된 문서 열림)이
  아니라 짝의 출처(주소에 경기 번호가 없음)를 고쳤다.
- `principle-test-behavior-not-implementation` — 새로 확인된 결함 하나에 대표 검사 하나만
  추가했고, A/B의 유효한 기존 검사는 재실행 근거로 재사용했다.

## 1. 결과 요약

A와 B의 최종 커밋을 이력 보존 병합했고(`--no-ff`), 실질 충돌은 **0건**이었다. 병합 트리에서
`vue-tsc -p tsconfig.app.json`이 B가 보고한 5건(기준 워크트리에서도 동일 재현)을 그대로
내므로 그 5건만 최소 수정했고, 이후 앱·노드 타입 검사와 `npm run build`가 모두 exit 0이다.
계약 직접 대조에서 **새로고침 복원 시 실행 ID를 경기와 짝짓지 않던 결함 1건**을 확인해
고쳤고(3경기 선택에서 다른 경기의 저장 문서가 열릴 수 있었다), 나머지 A/B 접점은 일치한다.

이번 배정에서 실제 수집·실제 AI 호출·공개 승인·실DB 쓰기·서버 전환·프로세스 기동은 **0회**다.
아래 통과는 전부 모의 대역·단위·합성 DB 근거이며 실제 공급자 응답의 증거가 아니다.

## 2. 병합

| 단계 | 커밋 | 결과 |
|---|---|---|
| A 병합 | `8243b63` (A `a899f9a60af50d839b87d593b9945459e43b22dc`) | ort 전략, 12파일 +3001. 충돌 없음 |
| B 병합 | `d756f24` (B `df7dc7bed65dd523d5aa44581061eab2942d5bb5`) | ort 전략, 12파일 +3551. 충돌 없음 |
| 타입 수정 | `f68255d` | §3 |
| 복원 짝짓기 수정 | `6755edf` | §5 |

포함 확인(ancestor 검사 3/3):

```
CONTAINED a899f9a60af50d839b87d593b9945459e43b22dc
CONTAINED df7dc7bed65dd523d5aa44581061eab2942d5bb5
CONTAINED 07e6cdc0f9c174b08337fcded81fb6f90f03bc42
```

A/B 팁과 병합 트리의 차이는 병합 이후 커밋 범위뿐이다(`git diff --stat a899f9a HEAD -- app/
tests/ scripts/`와 `git diff --stat df7dc7b HEAD -- frontend/`가 각 단계에서 해당 없음).
reset/rebase/squash를 쓰지 않았고 A/B 원 워크트리는 읽기만 했다.

A·B 제출 보고서의 사실 대조: A 보고의 "편집 종료·pytest 81 PASS", B 보고의 "직접 50 + 영향 64"
주장은 이번 트리에서 §6의 직접 재실행으로 확인했다. 다만 A 독립 검토는 별도 DeepSeek 세션
`ctx_55337cbaaa9f`에서 진행 중이며, 아래 C 자체 확인을 독립 검토 결과로 표현하지 않는다.

## 3. 필수 타입 수정 — `bundlePanelAdapters.ts` 5건

B 보고서 §10.2의 진단 문구 그대로 재현했고, 기준 워크트리 `player-section-integration`에서도
같은 5건이 나온다(기준선 회귀가 아니라 병합 전부터 있던 결함).

```
$ npx vue-tsc -p tsconfig.app.json --noEmit     # 수정 전
bundlePanelAdapters.ts(345,21): TS2339 Property 'source_url' does not exist on type 'ClaimView'
bundlePanelAdapters.ts(345,43): TS2339 (같은 원인)
bundlePanelAdapters.ts(384,9): TS2322 ... missing: status_short, origin, origin_note, run_id, and 2 more
bundlePanelAdapters.ts(399,29): TS2345 ... missing PreviewRunData: preview_error, sections_error, detail, detail_error
bundlePanelAdapters.ts(416,29): TS2345 (같은 원인)
exit 2
```

고친 방법과 근거:

1. `ClaimView`에 `source_url?: string | null`을 추가했다. 서버
   `app/preview/contracts.py`의 `EvidenceClaim.to_dict()`는 이 값을 항상 내보내고
   (`tests/preview/test_availability_module.py:355`가 payload의 `source_url`을 단언한다),
   이미 읽고 있던 R2 패널 타입(`AvailabilityR2ResultView.claims`,
   `panels/AvailabilityPanel.vue:92`)에도 이 필드가 있다. 그런데
   공용 `ClaimView`에만 없어서 어댑터가 읽지 못했다. 이전 저장 payload에는 없을 수 있으므로
   선택 필드로 두고, 읽는 쪽은 없으면 `null`로 둔다.
2. 두 어댑터가 만드는 카드 미리보기 입력에 `preview_error`/`sections_error`/`detail`/
   `detail_error`를 넘겼다. 투영은 `detail`을 별칭표 보강에만 쓰므로 이 어댑터는 `null`을
   넘겨 **지금과 같은 문서**를 그린다(동작 변경 없음).
3. 투영용 경기 후보는 표시 필드만 채우고, 목록 후보의 상태·출처 필드는 지어내지 않고
   "저장 목록 후보가 아님"으로 사실대로 채웠다(`origin: 'stored_db'`, `selectable: false`).
   기존 `homePreviewDocument.ts`도 같은 경계 처리(투영이 읽지 않는 필드는 값 창작 금지)를
   쓰고 있다.

실패 검사를 삭제하지 않았고 `any`·`ts-ignore`·`as unknown as`로 숨기지 않았다. 수정 후:

| 명령 | 결과 |
|---|---|
| `npx vue-tsc -p tsconfig.app.json --noEmit` | **exit 0** |
| `npx vue-tsc -p tsconfig.node.json --noEmit` | **exit 0** |
| `npm run build` (`vue-tsc -b && vite build`) | **exit 0**, built in 4.54s |
| `npx vitest run src/features/match-preview/BundlePanelAdapters.test.ts` | 1 passed |

루트 `tsconfig.json`은 `files: []` + 참조만 있어 `vue-tsc --noEmit`이 아무것도 검사하지
않는다. 이번 판정은 위 `-p tsconfig.app.json`/`-p tsconfig.node.json`/실제 빌드만 근거로 쓴다.

## 4. A/B 공통 HTTP 계약 직접 대조

소스 대조 결과(양쪽 실제 코드 기준):

| 접점 | A(서버) | B(클라이언트) | 판정 |
|---|---|---|---|
| `blocking_reasons` | `{code, message}` 객체 목록 (`preview_test.py:164-248`) | `TestBlockingReason`으로 객체 해석, 문자열도 허용 (`previewTest.ts:244-259`) | 일치 |
| `fixture_to` nullable | `max(kickoffs) if kickoffs else None` (`preview_test.py:251`) | `string \| null`, `null`이면 `can_collect=false` 확정 (`previewTest.ts:269,298`) | 일치. 값을 만들지 않음 |
| `can_collect` | `not blocking and bool(targets) and fixture_to is not None` | `root.can_collect === true && fixture_to !== null` | 일치(둘 다 실행 불가로 보수적) |
| 후보 응답 | `as_of/timezone/candidates/reason`, 후보 7필드 (`preview_test.py:82-107`) | `parseCandidates` 동일 7필드 | 일치 |
| 계획 targets | `id/league_name/season/include_details` | 동일 | 일치 |
| 수집 시작 요청 | `fixture_ids/fixture_from/fixture_to`, `extra="forbid"` (`management.py:225-245`) | 정확히 세 필드만 전송 (`previewTest.ts:521-526`) | 일치(422 회피) |
| 목록 envelope | `{active, items, limit}`, active는 진행 중 1건/null, items는 종료 실행 (`preview_test.py:286-307`) | 목록 미사용(단건 GET만) | 연결돼 있으나 미사용. 아래 참고 |
| 단건 조회 | `payload_view`(부작용 없음), 없으면 404 (`preview_test.py:310-317`) | `/runs/{run_id}` GET, 실패를 사유로 표시 | 일치 |
| `request_id` | `request_id` UUID 선택, 같은 값 재전달은 저장된 실행 재사용·모델 0회, 다른 경기는 409 (`preview_admin.py:2049-2088`) | `runBundle(fixtureId,{requestId})`, 재전송은 같은 값·명시적 새 실행은 새 UUID | 일치 |
| GET-only 복구 | 조회 경로에 `_recover_orphans` 미호출 | `restoreFromQuery`는 GET만, POST 없음 | 일치(테스트로 확인) |
| persisted/storage_mismatch | 신계약 행에 `persisted/storage_status/storage_mismatch/storage_error` 주입 (`preview_admin.py:360-373`, `player_section_read.py:271`) | `storageMismatchSections`로 해당 섹션 카드·본문 차단, 원문은 접힌 진단만 | 일치 |
| 선택 제약 | 수집 API만 정확히 2개(422) | 생성 선택은 개수 제한 없음, 수집 버튼만 2개 조건 + 안내 문구 | 일치(생성 3개 이상·수집 정확히 2개 보존) |

`collection_evidence`(A `a62545c`)는 `scope/planned/stored/detail_stored/unverified`,
`partial`, `counts`, `notes`를 모두 만들고(`management_runs.py:571-700`), B의 경계 파서가
같은 키를 읽는다(`previewTest.ts:321-359`). 객체 부재는 `null`(근거 미기록)로 두고 0건으로
채우지 않으며, `counts`가 없으면 목록 길이로만 계산한다. `notes`에 "detail_stored는 정상
빈 응답 포함", "미확인을 실패로 단정하지 않음", "계획과 저장을 구별", "생성 대상 두 경기는
이 목록과 다름"을 서버가 직접 문장으로 남긴다.

참고(차단 아님): A가 만든 목록 `GET /preview-test/runs`(`active/items/limit`)를 B 화면은
쓰지 않는다. 단건 GET만 쓰므로 수집 이력의 active 표시는 이 화면에 없다. 사용자 흐름상
필요한 정보는 아니나, 후속에서 이력 목록을 붙일 때 `active`와 `items`를 합치지 않아야 한다.

## 5. 새로 확인한 계약 연결 결함 1건 (수정)

**증상.** 세 경기를 골라 생성을 돌리고 첫 경기 생성이 실패하면, 새로고침 뒤 주소에 남은
저장 실행이 **선택 순서**로 짝지어져 둘째 경기의 실행이 첫 경기 행에 붙었다. 그 상태에서
'저장된 문서 보기'를 누르면 사용자가 보지 않은 다른 경기의 저장 프리뷰가 열린다.

**원인.** `syncQuery`가 실행 ID만 순서대로 남겼고(`testRuns=run-b,run-c`),
`restoreFromQuery`가 `selectedIds.slice(0, runIds.length)`로 위치 짝짓기를 했다. 게다가
선택 복원이 `if (ids.length === 2)`로 제한돼 3경기 선택은 복원되지 않았다.

**수정.** 실행을 `경기번호:실행ID` 짝으로 남기고(`testRuns=1557470:run-b,1557476:run-c`),
복원은 그 짝을 그대로 쓰며 짝이 없거나 선택에 없는 경기의 실행 ID는 채택하지 않는다. 선택
복원의 2개 제한도 없앴다(생성 선택은 원래 개수 제한이 없다).

**검사(먼저 실패를 확인한 뒤 고쳤다).** `첫 경기가 저장되지 않은 세 경기 선택도 저장 실행을
제 경기에 붙여 복원한다` — 수정 전 실행에서 `run-b`가 맨시티 행에 붙는 것을 관측했고, 수정
후 통과한다. B의 기존 복원 검사는 주소 표기가 바뀌었으므로 `testRuns` 한 줄을 새 짝 표기로
맞췄다(검사 의미는 그대로).

## 6. 직접 검사 명령과 결과

기존 A 81 PASS와 B 직접 50 + 영향 64 근거는 재사용했고, 전체 회귀·기준선 반복은 하지 않았다.

| 명령 | 결과 |
|---|---|
| `npx vue-tsc -p tsconfig.app.json --noEmit` | exit 0 |
| `npx vue-tsc -p tsconfig.node.json --noEmit` | exit 0 |
| `npm run build` | exit 0 |
| `npx vitest run src/components/management/ src/lib/api/ src/features/match-preview/BundlePanelAdapters.test.ts` | **52 passed** (PreviewTestPanel 22, PreviewPanel 25, collectionProxy 4, BundlePanelAdapters 1) |
| `pytest tests/unit/test_management_preview_test.py` | **27 passed** |
| `pytest tests/unit/test_home_preview_collection.py tests/preview/test_preview_test_requests.py` | **54 passed** |
| 앱 임포트·라우트 확인(`app.main`) | preview-test 4경로 + `bundle-runs` 등록 확인, 총 100 라우트 |

합성 DB 초기화는 **하지 않았다**. 위 pytest는 합성 DB를 요구하지 않았고(0.8s/2.5s, 외부
연결 없음), 55432의 공유 `preview_mp01_test`를 건드리지 않았다. 실제 DB에는 테스트 fixture를
연결하지 않았다.

## 7. 서버 전환 전제 조사 (읽기 전용)

프로세스 기동·전환·실수집·로그인 검증은 하지 않았다. 아래는 파일과 실행 중 프로세스의
환경을 읽어 비교한 결과이며 비밀 원문은 출력·복사하지 않았다(값은 길이·해시·사용자명만).

### 7.1 자격 파일과 대상

| 항목 | 기존 제한(`~/.config/match-preview/preview-dev-restricted.env`, 600) | 수집 후보(`preview-dev.env`, 600) |
|---|---|---|
| `DATABASE_URL` 사용자 | `preview_dev_runtime.xhsqnjezvqzzfebshsvl` | `postgres.xhsqnjezvqzzfebshsvl` |
| 호스트/포트/DB | `aws-1-ap-northeast-1.pooler.supabase.com:5432/postgres` | 같음 |
| 키 수 | 6 | 10 |

- 두 파일은 **같은 서버·같은 DB**를 가리키고 **사용자만 다르다**. 즉 "대상 동일성"은
  충족하고, 권한은 파일별로 분리돼 있다.
- 실행 중 38000 프로세스의 `DATABASE_URL`은 제한 파일과 **완전히 일치**한다(비교 True).
  수집 후보 파일과는 다르다. 수집 프로세스만 후보 파일을 쓰면 된다.
- 공통 키: `API_FOOTBALL_KEY`(존재, 길이 32, 두 파일 동일), `JWT_SECRET_KEY`(두 파일 동일,
  sha256 앞 12자 `8f3d56ba1f51` 일치 → **서명 호환**), `PREVIEW_DEV_DATABASE_URL`(동일),
  `PREVIEW_ALLOW_NONLOCAL_DB=1`.
- 제한 파일에만 `LOCAL_DEV_AUTH_ENABLED=true`. 수집 후보 파일에는 없어서 launcher가
  기본값 `true`로 채운다.
- 수집 후보에만 있는 `PREVIEW_ALLOW_NONLOCAL_IDENTITY_DB`와 `PREVIEW_*_DATABASE_URL` 3종은
  현재 코드가 읽지 않는다(`app/preview/config.py:15`가 명시). 추가 조치 불필요.

### 7.2 preview 역할의 public 비쓰기 (실DB 읽기 전용 확인)

`preview_dev_runtime`으로 **read-only 트랜잭션**(`default_transaction_read_only=on`,
statement_timeout 25s)에서 권한만 조회하고 rollback했다. 행을 읽거나 쓰지 않았다.

```
public(CREATE,USAGE) = (False, True)      preview_dev(USAGE,CREATE) = (True, False)
public management_run (insert,update,delete,select) = (False,False,False,False)
public 테이블 28개 중 쓰기 권한 보유 = 0
preview_dev 테이블 18개 중 INSERT 권한 보유 = 18
```

즉 프리뷰 역할은 **public 쓰기 0, preview_dev 쓰기만** 허용이며 계획의 권한 분리와 일치한다.
이 역할로는 수집(public.management_run 기록·축구 자료 갱신)을 실행할 수 없으므로 수집은
후보 자격을 쓰는 별도 프로세스여야 한다.

### 7.3 포트 소유 (조사 시각 21:12 KST)

| 포트 | 소유 프로세스 | 조치 |
|---|---|---|
| 5173 / 38000 | `player-section-integration/frontend` vite / `benchmark/.venv uvicorn` 38000 | 사용자 확인용. **유지**(전환은 후속) |
| 5175 / 38002 | `player-section-integration` vite / uvicorn 38002 | 유지 |
| 5174 / 38001 | `player-section-generation` vite / uvicorn 38001 | 유지 |
| 8000 | Docker(`com.docke`) | 유지 |
| **38003** | **비어 있음** | 수집 프로세스 후보로 사용 가능 |

38003은 현재 아무도 듣지 않는다(`lsof` 무출력). 기동은 하지 않았다.

### 7.4 기동 시 필요한 조치 (실행은 후속)

1. `scripts/run_preview_test_collection.sh`의 기본 python은 `$PWD/.venv/bin/python`인데
   이 워크트리에는 `.venv`가 없다. 기동 시
   `BENCHMARK_PYTHON=/Users/woolee/benchmark/.venv/bin/python`처럼 실제 인터프리터를
   지정해야 한다(스크립트가 이 변수를 지원한다). 별도 조치로 이 워크트리에 venv를 만들지
   않았다.
2. 수집 후보 자격 파일은 600이고 필수 키(`DATABASE_URL`, `PREVIEW_ALLOW_NONLOCAL_DB`,
   `JWT_SECRET_KEY`)가 모두 있다. 스크립트는 scheduler·home preview를 끄고 모델 설정을
   제거하므로 수집만 실행에 모델 전송이 없다.
3. 프론트는 `BENCHMARK_COLLECTION_BACKEND_URL=http://127.0.0.1:38003`을 주고 띄워야
   수집 접두사만 38003으로 간다. 미설정이면 그 접두사는 503 + 명시 문구이고 다른 서버로
   대체하지 않는다(설계대로).
4. 5173/38000 전환은 이번 배정 범위 밖이다. 현재 38000은 제한 자격으로 동작 중이며 public
   쓰기가 없으므로, 수집 버튼은 38003 프로세스가 없으면 실패한다(정상적인 분리 동작).

## 8. 미검증·남은 일

- 실제 수집 1회, 실제 두 경기 생성, 실제 DB 재조회, 실제 모델 호출: **0회**. 정상 ADMIN
  로그인을 포함한 사용자 검증은 조정자 후속이다.
- `collection_evidence`의 stored/detail_stored/partial 판정은 A의 **합성 검증**이며 실제
  공급자 응답에서 확인된 값이 아니다. 실제 수집 뒤 값이 비어 있으면 "근거 미기록"으로 보인다.
- 목록 `active/items`는 서버에 있으나 화면 미사용(§4 참고).
- `storage_mismatch` 차단은 이 화면의 테스트 문서 wrapper에서만 확인했다. 홈 공개 문서와
  다른 관리 화면 투영은 이번에 확인하지 않았다.
- 참고 개선(범위 밖): 38000 프로세스의 `actor` 필드가
  `user.nickname or user.email if user else "정기 수집"`로 쓰여 있어(기준 커밋부터 존재)
  닉네임만 있고 email이 없으면 `None`이 될 수 있다. 이번 변경이 만든 것이 아니고 사용자
  흐름에 영향이 없어 고치지 않았다.
- 브라우저에서 실제 화면을 열어 본 확인은 하지 않았다(5173은 기존 서버 소유이며 전환은 후속).

## 9. 인계

- 병합·타입 수정·복원 짝짓기 수정까지 커밋했고 워크트리는 clean이다(편집 종료).
- 다음 단계(조정자): 서버 전환 → 38003 수집 프로세스 기동 → 5173 프록시 설정 →
  정상 ADMIN 로그인 → 기간 수집 1회 → 사용자 수집 결과 확인 → 사용자 수동 생성.
- 검토자는 이번 B 변경과 C 직접 수정·연결만 보면 되고, 이미 수용된 A 부분을 다시 전체
  심사할 필요는 없다. C 자체 확인은 독립 검토(`ctx_55337cbaaa9f`)를 대체하지 않는다.
