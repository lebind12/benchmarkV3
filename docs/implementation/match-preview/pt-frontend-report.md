# PT-FRONTEND B 보고 — 기존 프리뷰 탭의 기간 수집·다경기 생성·저장 문서

작성: 2026-11-17 KST. 담당: DeepSeek 구현 워커 B (Orca term_8c44b024).
Task `task_d53774e7c32d` / Dispatch `ctx_3ca9d129002c`.

기준 SHA: integration `07e6cdc0f9c174b08337fcded81fb6f90f03bc42`, worktree
`/Users/woolee/orca/workspaces/benchmark/preview-test-ui`.

실제 모델: 세션 메타데이터에서 확인한 `provider=hive`,
`model=deepseek-ai/deepseek-v4.1-flash-1017`, `reasoningEffort=high`
(`~/.dsh/sessions/.../68188d24-…/session.v4.jsonl.zstd`의 `model/selection` 이벤트).
모델을 바꾸지 않았고 다른 백엔드로 대체하지 않았다.

적용한 스킬·원칙: `.agents/skills/poteto-mode/SKILL.md` 전문,
`playbooks/feature.md`, `typescript-best-practices/SKILL.md`,
`principle-model-the-domain`, `principle-laziness-protocol`,
`principle-test-behavior-not-implementation`. 적용이 바꾼 결정은 §6에 적었다.

---

## 1. 결과 요약

기존 `/admin?tab=preview` 화면을 그대로 사용자 확인 환경으로 두고, 그 안쪽 위에
기간 수집 → 다경기 생성 → 저장 문서 열기 흐름을 붙였다. 새 진단 전용 페이지나 새
라우트는 만들지 않았고, `MatchPreviewBody`는 수정하지 않았다.

이번 작업에서 **실제 수집·실제 생성·실제 AI 호출은 0회**다. 아래 통과는 모두 모의 HTTP
대역에서 확인한 UI 동작이며, 실제 수집/생성이 성공했다는 근거가 아니다.

## 2. 변경 파일

B 소유 파일만 수정했다.

- `frontend/src/components/management/PreviewPanel.vue` — 기존 단일 경기 흐름 보존,
  시험 영역 마운트, 저장 불일치 섹션 차단과 원문 접힌 진단.
- `frontend/src/components/management/PreviewPanel.test.ts` — 직접 영향 사례 4개 추가.
- `frontend/src/components/management/PreviewTestPanel.vue` (신규) — 후보 선택, 기간·대상
  안내, 수집 실행·추적, 다경기 순차 생성, 경기별 생성/저장 분리 표시, 문서 열기.
- `frontend/src/components/management/PreviewTestPanel.test.ts` (신규) — 11 사례.
- `frontend/src/lib/api/previewTest.ts` (신규) — 수집 시험 API 클라이언트와 경계 파싱.
- `frontend/src/lib/api/collectionProxy.ts` (신규) — 수집 접두사 전용 프록시 규칙.
- `frontend/src/lib/api/collectionProxy.test.ts` (신규) — 프록시 4 사례.
- `frontend/src/lib/api/preview.ts` — `generatePreview`에 선택 `requestId` 전달.
- `frontend/src/lib/api/previewView.ts` — `storageMismatchSections`, `withoutBlockedSections`.
- `frontend/src/features/match-preview/api.ts` — `runBundle`에 선택 `request_id` 본문.
- `frontend/vite.config.ts` — 수집 접두사만 선택 환경변수로 프록시, 미설정 시 503.

`Plans.md`, backend, alembic, 기존 테스트 서버는 건드리지 않았다.

## 3. 사용자 흐름

1. 후보 목록에서 가까운 두 경기를 기본 선택하고 KST 킥오프·리그·시즌·경기 번호·추천
   순위를 본다. 세 번째를 고르면 가장 오래된 선택이 빠진다(수집 API가 정확히 두 경기).
2. 기간·활성 대상·범위 안내를 서버 응답 그대로 확인한다. 부상 자료(`/injuries`)가 이번
   수집에서 갱신되지 않는다는 문장을 표 위에 고정했다.
3. '기간 지정 수집'을 누르면 수집만 실행하고 상태를 GET으로 따라간다. 종료가 확인되면
   폴링만 멈춘다. **생성은 호출하지 않는다.**
4. '선택 경기 프리뷰 생성'을 누르면 고른 순서대로 한 경기씩 생성한다. 첫 경기가 실패해도
   다음 경기를 계속한다.
5. 표에서 경기별로 생성 응답, 저장 판정, 문서 열기를 따로 본다. 저장 판정은 받은 실행
   ID로 `getPreviewRun`을 다시 읽어 판단하며, 생성 성공 표시와 다르다.
6. '저장된 문서 보기'는 같은 실행을 GET으로 연다. 주소(`previewRun`)에 남으므로
   새로고침해도 같은 문서가 열리고 POST는 나가지 않는다.

## 4. 직접 명령과 결과

`node_modules`는 기존 설치를 재사용하려고
`player-section-integration/frontend/node_modules`를 이 워크트리에 심볼릭 링크했다(패키지
설치·업그레이드 없음, `frontend/node_modules`는 gitignore 대상).

| 명령 | 결과 |
|---|---|
| `vue-tsc -p tsconfig.app.json --noEmit` | exit 2, 오류 5건 — **전부 기존** `bundlePanelAdapters.ts` (기준 워크트리와 동일) |
| `vue-tsc -p tsconfig.node.json --noEmit` | exit 0, 오류 0 |
| `vitest run src/components/management/ src/lib/api/` | 50 통과 (PreviewTestPanel 21, PreviewPanel 25, collectionProxy 4) |
| `vitest run src/components/home-preview/MatchPreviewBody.test.ts src/features/match-preview/PlayerSectionStorage.test.ts` | 14 통과 (MatchPreviewBody 10 + PlayerSectionStorage 4) |
| 위 네 파일 합계(영향 검사) | **64 통과** |
| `vitest run` (전체) | 13 파일 / 58 실패 — 기준 워크트리와 동일 |

**건수 정정(로그 근거).** 앞선 보고에는 영향 검사가 `14`와 `54`로, 다른 곳에는 `15`와
`55`로 적혀 서로 맞지 않았다. 실제 로그로 확정한 값은 위 표다. 차이는 **명령 범위**였다.
`BundlePanelAdapters.test.ts`(1 사례)를 포함한 명령은 15가 되고, 빼면 14가 된다. 두 수는
각자 자기 명령에서는 맞았지만 표에 함께 적혀 오해를 만들었다. 현재 값은
`src/components/management/` + `src/lib/api/` = 50, 위 두 파일 = 14, 합계 64다.

**주의(정정).** 이 패키지의 `tsconfig.json`은 `files: []` + 프로젝트 참조만 있어서
`vue-tsc --noEmit`(프로젝트 미지정)은 **아무 파일도 검사하지 않고 exit 0을 낸다.** 실제
검사는 `-p tsconfig.app.json`으로 해야 한다. 이 함정 때문에 아래 §8의 타입 결함 4건이
처음 보고에서 "통과"로 잘못 적혔다가 이후 발견·수정됐다.

전체 회귀 실패 13 파일·58 사례는 **기준 워크트리
`player-section-integration`에서 같은 명령으로 동일하게 재현**됐다(13 파일 / 58 사례).
내가 추가한 사례는 그 안에서 전부 통과한다. 이 실패들은 `FixtureSelector`,
`PreviewMetricsView`, `RunInspector`, `R4PanelAndBody` 등 인증·네트워크 mock 미연결
계열이며 이번 변경과 무관하다.

`PreviewPanel.test.ts` 실행 시 `getPreviewRun`에서 `stderr`로
`TypeError: Cannot read properties of undefined (reading 'ok')`가 한 번 찍힌다. 이는 기준
워크트리에서도 동일하게 나오는 기존 현상(대역이 세 GET을 모두 예약하지 않은 한 사례)이며
해당 사례는 통과한다.

## 5. 수용 기준별 근거

| 요구 | 처리 | 근거 |
|---|---|---|
| 새로고침 GET-only | 주소의 `testFixtures`/`testRuns`/`testCollection`을 GET으로만 복원, POST 0 | `PreviewTestPanel.test.ts` "새로고침 복원은 GET만…", `previewRun` 복원은 기존 사례 유지 |
| 첫 경기 실패 후 다음 진행 | 생성 루프가 경기별 실패를 상태로 남기고 계속 | "첫 경기가 실패해도 두 번째 경기를 계속 진행한다" |
| 수집 후 자동 생성 금지 | 종료 확인 함수가 폴링만 멈춤, 생성 호출 없음 | "수집이 끝나도 생성 POST를 보내지 않고…" (POST 1건 유지 확인) |
| `storage_mismatch` 정상 렌더 차단 | 해당 섹션 본문·카드를 투영에서 제거, 문서 위 경고 + 접힌 원문 | `PreviewPanel.test.ts` "불일치 섹션은 정상 문서로 그리지 않고…", `withoutBlockedSections` 사례 |
| 기존 프리뷰 보존 | 단일 경기 번호 확인·생성·이력·진단·재생성 경로 손대지 않음 | 기존 21 사례 전부 통과 + 신규 4 사례 |
| 더블클릭·중복 방지 | 단일 경기 버튼 disabled 유지, 다경기 루프는 실행 중 재진입 차단 | 기존 더블클릭 사례, `canGenerateSelection` |
| request_id 보존·명시적 재시도 구분 | 통신 실패 재전송은 같은 값, 새 실행은 새 UUID | "응답을 못 받은 요청의 재전송은 같은 request_id…" |
| 늦은 응답 무시 | 경기별 순번 비교 | "붙잡힌 이전 요청의 응답이 늦게 도착해도…" |
| 저장 재조회 | 같은 실행 ID만 채택, 경기·run 불일치는 `unknown` | "저장 조회가 실패한 경기는 저장 성공으로 표시하지 않는다" |
| 수집 전용 프록시 | 접두사만 별도 대상, 미설정은 503 | `collectionProxy.test.ts` 4 사례 |
| `/injuries` 미갱신 명시 | 표 상단 고정 문장 | 첫 사례에서 `/injuries` 문구 확인 |

A가 인계한 run 상세 매핑(19:53·19:58 메시지)을 반영했다. `counts_kind`가
`processing_units`면 수량을 "처리 단위"로 적고, `legacy_unknown`이면 `미상`으로 두어 0으로
채우지 않는다. 실제 수집 경기 목록과 대상 `last_sync`는 응답에 없으므로 표시하지 않으며,
생성 대상 2개를 수집 경기 수로 대신 쓰지 않는다.

## 6. 원칙이 바꾼 결정

- **Model the Domain**: 경기별 상태를 `idle | generating | saved | failed` 판별 유니온으로
  두었다. "실행 ID는 있는데 저장 판정이 없는" 상태를 표현할 수 없게 만들어, 생성 성공을
  저장 성공으로 읽는 경로를 타입 수준에서 없앴다. 불리언 여러 개를 두는 대신 이 구조를
  골랐다.
- **Laziness Protocol**: 새 페이지·새 라우트·별도 저장소를 만들지 않고 기존
  `PreviewPanel` 안에 한 컴포넌트를 붙였다. `request_id`도 기존 실행 저장/잠금 계약을
  그대로 쓰고 새 표를 만들지 않았다.
- **Boundary Discipline**: 서버 응답 해석을 `parseCandidates`/`parsePlan`/`parseRun` 한
  곳으로 모으고, 안쪽 컴포넌트는 파싱된 타입만 받는다. 해석 실패를 빈 목록으로 바꾸지
  않고 사유를 그대로 올린다.
- **Test Behavior, Not Implementation**: 대역을 `authenticatedFetch` 한 곳에만 두어
  실제 모듈의 경로·본문·정규화를 그대로 실행했다. 검사는 화면에 보이는 문구와 나간 요청
  본문을 본다.

## 7. 미검증·남은 일

- 실제 수집 실행, 실제 두 경기 생성, 실제 DB 재조회, 실제 모델 호출은 **하지 않았다**.
  위 모든 통과는 모의 HTTP 대역 근거이며 실수집/실AI 근거가 아니다.
- A의 최종 backend 구현(후보·계획·수집 시작·목록 GET)이 이 워크트리에 없으므로 실제
  응답과의 대조는 C(통합)에서 필요하다. 특히 목록 envelope는 A가 `active/items/limit`로
  확정했으나 이 화면은 단건 `GET /runs/{id}`만 쓰므로 영향 없다.
- 수집 대상별 실제 경기 목록과 `last_sync`는 서버가 주지 않아 화면에 없다. A가 필드를
  추가하면 그때 연결한다.
- 서버 재시작·5173/38000 반영·프록시 환경변수 실설정·브라우저 화면 확인은 이번 배정
  범위 밖이다(C 담당).
- `storage_mismatch` 차단은 이 화면의 문서 wrapper에서만 적용된다. 홈 공개 문서와 다른
  관리 화면의 투영은 바꾸지 않았고, 그쪽 동작은 이번에 확인하지 않았다.

## 8. 후속 수정 — A 소스 대조로 발견한 계약 불일치 2건과 타입 결함 4건

조정자가 A 커밋 `f9bc34c`를 읽으라고 인계한 뒤, 그 **실제 소스**를 직접 대조해 아래를
발견하고 고쳤다. 처음 착수 시에는 A 응답을 문자 그대로 믿었고 그것이 틀렸다.

### 8.1 `blocking_reasons`는 문자열 목록이 아니라 `{code, message}` 객체 목록

A의 `app/services/preview_test.py`는
`blocking.append({"code": "fixture_started", "message": ...})` 형태로 만든다. 처음 구현은
문자열 목록으로 파싱해 **사유 6종이 화면에서 모두 사라졌다**(`textList`가 객체를 걸러냈고
`can_collect=false`만 남았다). 그러면 사용자는 "이유 없이 실행 불가"만 본다.

수정: `TestBlockingReason = {code, message}`로 모델링하고 `message`를 그대로 표시, `code`는
진단용으로만 쓴다. 문자열만 주는 구현도 계속 받는다.

### 8.2 `fixture_to`는 `null`일 수 있다

A는 `fixture_to = max(kickoffs) if kickoffs else None`이며, 킥오프 시각이 없는 경기가 있으면
`None`을 준다. 처음 구현은 `null`을 파싱 실패로 처리해 **정상 응답을 오류로 표시**했다.

수정: `fixture_to: string | null`로 받고, `null`이면 `can_collect`를 `false`로 확정한다.
`startCollection`은 끝 시각이 없으면 요청을 보내지 않고 사유를 보여준다(값을 만들지 않는다).

### 8.3 `vue-tsc --noEmit` 무검사 함정과 타입 결함 4건

위 수정 중 `fixture_to: string | null`을 `string` 자리에 넣었는데도 타입 검사가 exit 0을
냈다. 원인은 `tsconfig.json`이 `files: []` + 참조만 가진 것이라 **프로젝트를 지정하지 않은
`vue-tsc --noEmit`이 아무 파일도 검사하지 않는다**는 점이다. `-p tsconfig.app.json`으로
다시 돌려 아래 4건을 잡아 고쳤다.

1. `PreviewTestPanel.vue` — `fixture_to` nullable을 시작 요청에 넘기던 곳.
2. `PreviewTestPanel.vue` — 불가 사유 객체를 `:key`로 쓰던 곳.
3. `PreviewTestPanel.test.ts` — 대역 단계 유니온의 `held` 분기 좁히기 누락.
4. `PreviewTestPanel.test.ts` — `sectionRow` 반환 타입이 `SectionResultView`를 만족하지 않음.

수정 뒤 `-p tsconfig.app.json`의 남은 오류는 기준 워크트리와 동일한 5건
(`bundlePanelAdapters.ts`, 이번 소유 파일 아님)뿐이다.

### 8.4 새로 확인한 계약(코드 확인)

- 후보 응답 `candidates`/`as_of`/`timezone`/`reason`과 후보 7필드는 A 소스와 일치한다.
- 수집 계획 `targets[]`는 `{id, league_name, season, include_details}`로 일치한다.
- 수집 시작 `POST /preview-test/runs`는 `fixture_ids`/`fixture_from`/`fixture_to`만 받고
  `extra="forbid"`다(계획의 `target_ids`를 함께 보내면 422). 이 화면은 세 필드만 보낸다.
- 단건 조회는 `id`를 키로 주며 `payload_view`를 쓴다. 목록은 A가 아직 `items`/`limit`만
  주지만(`active` 미포함), 이 화면은 목록을 쓰지 않으므로 영향 없다.
- `bundle-runs`의 `request_id`는 저장된 실행 재사용, 같은 값 다른 경기는 409,
  생성 중 재전달도 409다. 재전송 시 같은 값을 쓰는 이 화면 동작과 맞는다.

### 8.5 이번 후속의 검사

| 명령 | 결과 |
|---|---|
| `vue-tsc -p tsconfig.app.json --noEmit` | exit 2, 오류 5건 전부 기존 `bundlePanelAdapters.ts` |
| `vue-tsc -p tsconfig.node.json --noEmit` | exit 0 |
| `vitest run src/components/management/ src/lib/api/` | 42 통과 (PreviewTestPanel 13) |
| `vitest run` (전체) | 13 파일 / 58 실패 — 기준 워크트리와 동일 |

여전히 실제 수집·생성·모델 호출은 0회이며, 위 통과는 모의 대역 근거다.

## 9. 후속 수정 — 생성 선택 상한 해제와 collection_evidence 연결

조정자 지시(2026-11-17 20:40 KST)에 따라 두 가지를 고쳤다. 지시의 핵심은 **수집의
정확히2개 제약과 다경기 생성 선택은 별개**라는 점이었다.

### 9.1 생성 선택에서 기존 선택 자동 제거를 없앴다

이전 구현은 세 번째 경기를 고르면 가장 오래된 선택을 자동으로 뺐다(`slice(-2)`). 이는
확정 설계가 아니었고, 사용자가 고른 경기가 소리 없이 사라지는 동작이었다.

수정: 선택은 **고른 것을 그대로 유지**하고 개수 제한이 없다. 제약은 선택을 깎는 대신
수집 버튼에만 적용한다.

- `hasSelection`(1개 이상) → 생성 버튼 조건. 선택 전체를 순서대로 실행한다.
- `collectionScopeReady`(정확히 2개) → 수집 버튼 조건과 계획 조회 조건.
- 선택이 2개가 아니면 `ptp-collection-scope-hint`가 "기간 수집은 정확히 두 경기가
  필요합니다(현재 N경기)"를 보여 주고, 생성은 N경기 전체로 계속 쓸 수 있음을 함께 적는다.
- 계획 조회는 2개일 때만 보낸다(서버가 3개 이상을 422로 거부하는 요청을 보내지 않는다).

기본 선택 2개는 유지한다.

### 9.2 `collection_evidence` 연결

A 커밋 `a62545c`의 `collection_evidence`를 경계에서 해석해 화면에 표시한다.

| 필드 | 화면 처리 |
|---|---|
| `scope_fixture_ids` | "생성 대상"으로 따로 표시. 아래 수집 목록과 **합치지 않는다** |
| `planned_fixture_ids` | 계획(기간 내). 저장 성공으로 읽지 않는다 |
| `stored_fixture_ids` | 저장 확인(커밋 근거) |
| `detail_stored_fixture_ids` | 상세 응답 저장. 정상 빈 응답 포함이라 자료 확보와 다름을 함께 적는다 |
| `unverified_fixture_ids` | 저장 미확인. **실패로 단정하지 않는다**는 문장을 함께 표시 |
| `partial` | 확인 범위가 전체가 아님을 경고로 표시 |
| `counts` | 접힌 요약 줄의 건수. 서버 값을 우선하고, 없으면 목록 길이로 계산 |
| `notes` | 접힌 영역의 서버 문장 그대로 |
| 객체 없음 | "아직 근거가 기록되지 않았습니다(0건으로 추정하지 않습니다)" |

목록은 기본 접힘이고 요약 줄에 네 건수를 보여 준다. 건수는 목록 길이에서 계산할 수 있는
경우에만 채우고, 목록도 counts도 없으면 `—`로 두어 0과 구분한다. `/injuries` 미포함 안내는
그대로 유지한다.

### 9.3 이번 후속의 검사

| 명령 | 결과 |
|---|---|
| `vue-tsc -p tsconfig.app.json --noEmit` | 오류 5건 전부 기존 `bundlePanelAdapters.ts` |
| `vitest run src/components/management/ src/lib/api/` | **50 통과** (PreviewTestPanel 21) |
| 영향 검사 4파일 합계 | **64 통과** |

추가한 대표 사례:

- 세 경기 선택 유지 + 세 경기 순차 생성(첫 경기 실패 후 둘째·셋째 진행·저장 확인) 1건.
- 선택이 2개가 아닐 때 수집 버튼 안내 + 계획 미조회 1건.
- 근거 3/2/1/1 표시, 근거 부재, 부분 확인 각 1건.
- 경계 정규화: `target_not_found` 사유의 message·code 보존, `fixture_to=null` 확정,
  근거 네 목록·건수 이관과 부재 시 `null` 각 1건.

전체 회귀는 지시대로 반복하지 않았고 기존 유효 증거를 재사용했다. 실제 수집·생성·모델
호출은 여전히 0회다.

## 10. B 배정 종료 확인과 C 인계용 진단 원문

조정자 메시지 `msg_f1bd601f2f07`는 남은 B 작업이 `msg_709ebdd8353a`(수집2개/생성3개이상
선택 분리)와 `msg_dbc6a758442c`(collection_evidence 연결)뿐이며 소스에 아직 `slice(-2)`,
`selectionReady=2`, evidence 미연결이 남아 있다고 보았습니다. 그 메시지는 **이전 커밋
`27846bf` 시점의 소스**를 본 것입니다. 아래처럼 이미 `f2ebce4`/`855b03d`에서 처리됐고,
지시의 추가 범위도 없습니다.

| 지적 | 현재 소스 | 커밋 |
|---|---|---|
| `slice(-2)` 자동 제거 | 없음. 선택은 그대로 유지되고 개수 제한 없음 | `f2ebce4` |
| 생성 `selectionReady=2` | 없음. `hasSelection`(1개 이상)이 생성 조건 | `f2ebce4` |
| evidence 미연결 | `collection_evidence` 7회 참조, scope/planned/stored/detail_stored/unverified 분리 표시 | `855b03d`, `f2ebce4` |

```
$ grep -n "slice(-2)" frontend/src/components/management/PreviewTestPanel.vue   → 없음
$ grep -n "selectionReady" frontend/src/components/management/PreviewTestPanel.vue → 없음
$ grep -c "collection_evidence" frontend/src/components/management/PreviewTestPanel.vue → 7
$ grep -n "hasSelection\|collectionScopeReady" …/PreviewTestPanel.vue
182: const hasSelection = computed(() => selectedIds.value.length > 0)
185: const collectionScopeReady = computed(() => selectedIds.value.length === 2)
```

### 10.1 대표 직접검사(재실행 근거)

```
$ vitest run src/components/management/PreviewTestPanel.test.ts -t "세 경기를 골라도 선택이 유지되고"
→ 1 passed | 20 skipped
$ vitest run src/components/management/PreviewTestPanel.test.ts -t "계획·저장 확인·상세 저장·미확인을 각각"
→ 1 passed | 20 skipped
```

전체 Vitest와 기준선 재실행은 지시대로 하지 않았습니다.

### 10.2 C가 통합 빌드에서 처리할 기존 오류 5건(정확한 진단 문구)

`vue-tsc -p tsconfig.app.json --noEmit`은 exit 2이며, 오류는 **전부 이번 소유 밖**
`src/features/match-preview/bundlePanelAdapters.ts`입니다. 기준 워크트리
`player-section-integration`에서 같은 명령으로 동일하게 재현됩니다. B는 이 파일을 고치지
않았습니다.

```
src/features/match-preview/bundlePanelAdapters.ts(345,21): error TS2339: Property 'source_url' does not exist on type 'ClaimView'.
src/features/match-preview/bundlePanelAdapters.ts(345,43): error TS2339: Property 'source_url' does not exist on type 'ClaimView'.
src/features/match-preview/bundlePanelAdapters.ts(384,9): error TS2322: Type '{ fixture_id: number; league_id: number; season: number; home_team_id: number | null; away_team_id: number | null; kickoff_at: string; league_name: string; home_team_name: null; away_team_name: null; label: string; } | null' is not assignable to type 'FixtureCandidate | null'.
src/features/match-preview/bundlePanelAdapters.ts(399,29): error TS2345: Argument of type '{ run_id: string; preview: null; sections: { run_id: string; section_results: SectionResultView[]; }; fixture: FixtureCandidate | null; }' is not assignable to parameter of type 'PreviewRunData & { fixture?: FixtureCandidate | null | undefined; }'.
src/features/match-preview/bundlePanelAdapters.ts(416,29): error TS2345: (399,29)와 같은 문구.
```

내 소유 파일(`PreviewTestPanel.vue`, `previewTest.ts`, `PreviewPanel.vue`, `previewView.ts`,
`collectionProxy.ts`, `api.ts`, `preview.ts`, `vite.config.ts`)에서는 오류가 0건입니다.
