# 홈 최신 저장 프리뷰 구현 보고 (HP-IMPL)

작성: DeepSeek 구현 워커, 2026-11-13. 계획: `docs/superpowers/plans/2026-11-13-home-stored-preview.md`.
설계: `docs/superpowers/specs/2026-11-13-home-stored-preview-design.md` (사용자 승인).

## 결과 요약

홈 추천 경기 선택이 `preview_dev`의 최신 공개 가능 저장 문서를 읽어 기존 `MatchPreviewBody`로
본문·점수·사진·카드를 표시한다. 저장 문서가 없으면 기존 6시간 안내를 그대로 쓴다. 조회
오류는 문서 없음과 분리해 다시 확인 동작을 제공한다.

`EDITING STOPPED`. 편집과 백그라운드 작업을 모두 끝냈다. 커밋·되돌리기·포맷 변경은 하지 않았다.

## 확정한 공개 계약

`GET /api/v1/home/fixtures/{external_id}/document` (GET 전용, 저장 조회만 수행)

- `schema_version`(1.0), `fixture_id`, `status`(`available`|`none`), `reason`, `reason_text`,
  `saved_at`, `run_id`, `complete`, `fixture`, `headline`, `sections[]`.
- `fixture`는 표시용 외부 ID·이름·로고·킥오프·대회명만 담는다. 내부 기본키·시즌·리그 ID는 넣지 않는다.
- `sections[]`는 `section_result_id`, `run_id`, `workflow_id`, `workflow_version`, `version`,
  `title`, `body`, `sources`, `quality`, `partial`, `created_at`, `structured`.
- `structured`는 화이트리스트 투영이다. `player_id`(내부)와 `team_id`(내부)는 **공개하지 않고**,
  확인된 `external_player_id`·`team_external_id`·`photo_url`만 남긴다.
- 실행 진단·프롬프트·원문·계정·비밀값은 계약에 없다.

선택 규칙은 승인 설계를 그대로 구현했다. 최신 기준은 **문서 저장 시각**이고, 구성본이 있으면
그 선택 ID가 정본이며, 본문 없는 새 실행은 이전 문서를 밀어내지 않고, 6시간 밖 저장본도
표시하며, 동률은 실행 ID로 결정한다. 새 품질 문턱(최소 길이·필수 섹션 개수)은 추가하지 않았다.

## 변경 파일

- `app/services/home_preview_document.py` (신규): 저장 실행·섹션·구성본에서 표시 가능한 최신
  문서를 고르고 공개 화이트리스트로 투영한다. 승인 버전만 게시하고 모의 실행은 제외한다.
- `app/api/v1/home_preview.py`: `/fixtures/{external_id}/document` 추가. 공개 세션(`app.db`)으로
  경기 표시 값을, `preview_dev` 세션(`app.preview.db`)으로 저장 문서를 읽는다. 문서 없음은 200
  `status=none`, 저장소 읽기 실패는 503으로 구분한다. 기존 `prematch`·`recommendations` 경로는
  그대로 두었다.
- `frontend/src/lib/api/homePreviewDocument.ts` (신규): zod 계약과 표시 모델 변환. 기존
  `toMatchPreviewView`를 재사용해 두 번째 본문 규칙을 만들지 않았다.
- `frontend/src/lib/api/homePreview.ts`: `getHomePreviewDocument` 추가.
- `frontend/src/components/home-preview/HomeRecommendedSection.vue`: 저장 문서 분기 추가.
  `loading`/`ready`/`none`/`failed`를 분리하고, `none`일 때만 기존 안내 경로를 연다. 경기 전환
  시 앞 본문을 먼저 비우고 늦은 응답은 순번으로 무시한다.

수정하지 않은 것: `MatchPreviewBody.vue`, `body.css`, 관리자 기능, 원문 저장, `Plans.md`,
`previewView.ts`(우선 재사용), 공통 본문 디자인.

## 검사 명령과 결과

수치를 실행별로 구분한다. 서로 다른 실행의 통과 수를 더해 하나의 숫자로 보고하지 않는다.

**1차 구현 시점 (2026-11-13 00:47)**

- `.venv/bin/python -m pytest tests/unit/test_home_preview_document.py -q` → **11 passed**
  (선택 7 + 저장 조회 3 + 내부 ID 비노출 1).
- `.venv/bin/python -m pytest tests/unit -q` → **36 passed**.
- 요구 프론트 파일 5개 실행 → **36 passed, 2 failed**. 실패 2건은 `publication.spec.ts`의
  `TypeError: resolve is not a function`이며 **내 변경 전에도 동일하게 실패**한다.
- 완료 메시지에 "총 47건 통과"라고 적은 값은 위 실행들을 더한 수라 **부정확했다**. 정정한다.

**사용자 추가 기준 반영 후 (2026-11-13 00:59, 최신 변경 직접 검사만)**

- `.venv/bin/python -m pytest tests/unit/test_home_preview_document.py -q` → **13 passed**
  (1차 11 + `absence` 경계 2).
- 요구 프론트 직접 검사 4개 파일(`storedDocument.spec.ts`, `HomeRecommendedSection.test.ts`,
  `MatchPreviewBody.test.ts`, `recommendations.spec.ts`) → **26 passed**.
- `npx vue-tsc -b --pretty false` (cwd `frontend`) → 새 오류 0. 남은 8건은 내가 만들지 않은
  파일(`PreviewPanel.test.ts` 6건, `BundleGenerationPanel.test.ts` 1건, `preview.ts` 1건)이며
  변경 전과 같다.
- 위 4개 파일에서 `publication.spec.ts`를 뺐다. 같은 환경 결함으로 실패하는 파일이라
  반복하지 않고 기존 결과를 인용한다.

새 검사의 이유와 사용자 영향:

- 후보 선택 검사: 저장 시각 기준이 틀어지면 본문 없는 새 실행이 보이던 본문을 가려 홈이 빈다.
- 구성본 우선 검사: 선택을 무시하면 관리자가 저장한 조합과 다른 본문이 섞여 나온다.
- 모의·미승인 제외 검사: 검증용 본문이 실제 홈 기사처럼 보이면 안 된다.
- 사유 분리 검사: 장애가 "생성 예정" 안내로 위장되면 사용자가 확인 없이 기다린다.
- 내부 ID 비노출 검사: 내부 ID로 사진 주소를 조립하면 다른 선수 사진이 나온다.
- 컴포넌트 상태 검사: 오류와 문서 없음을 같은 화면으로 보여주면 재확인 필요 여부를 알 수 없다.

## 기존 실패 (내 변경과 무관, 재현 확인)

`frontend` 전체 검사는 68 failed / 345 passed다. 내 파일을 stash로 제거한 상태에서도
**68 failed / 338 passed**로 실패 수가 같고, 내가 추가한 7건만 빠진다. `publication.spec.ts`
실패는 `node:path`의 `resolve`가 vitest에서 함수로 오지 않는 환경 문제로, 최소 재현
검사(`import * as path from 'node:path'`)에서도 같은 오류가 난다. 계획의 "기존 오류와 새 오류
구분" 요구에 따라 이 2건을 기존 오류로 분류했다.

## 승인 기록 확인 (사실만 보고)

이 작업 환경에는 `DATABASE_URL`이 없고 `.env`도 없다. 그래서 `preview_dev`의 실제
`preview_section_approvals` 행을 **조회하지 못했다**. 승인이 없다고 단정하지 않았고, 승인을
만들어 통과시키지도 않았다.

구현상 공개 게시 조건은 기존 승인 정책을 따른다. 활성 승인 행이 있는 워크플로우 버전만
게시하고, 승인이 하나도 없으면 문서는 `status=none`·`reason=no_approved_version`으로 나간다.
따라서 **승인 기록이 실제로 없으면 홈에 저장 본문이 표시되지 않고 기존 6시간 안내가 나간다.**
이것은 구현 결함이 아니라 승인 정책을 보존한 결과이며, HP-HOME의 실제 화면 확인 전에
조정자가 승인 기록 유무를 확인해야 한다.

승인 POST·DB 쓰기·모델 생성·외부 HTTP 조회는 하지 않았다. GET 저장 조회만 구현했다.

## 적용한 원칙과 달라진 선택

- **Prove It Works.** 자기 보고 대신 실제 검사 실행 결과로 확인했고, 승인 기록은 읽지 못한
  사실을 그대로 적었다(추정으로 "승인됨"이라 쓰지 않았다).
- **Laziness Protocol.** 새 홈 전용 본문·별도 생성기를 만들지 않고 기존 `MatchPreviewBody`와
  `toMatchPreviewView`를 재사용했다.
- **Model the Domain.** 공개 응답을 화이트리스트 투영으로 만들고 내부 기본키를 구조 값에서
  제거하는 경계를 두었다. 이 선택 때문에 내부 ID 누출 검사를 추가했다.
- **Test Behavior, Not Implementation.** 검사는 내부 함수 호출 순서가 아니라 홈이 받는
  응답과 화면 분기를 확인한다.

## 미해결

1. 실제 DB가 있는 환경에서 승인 기록 유무를 확인해야 한다. 승인이 없으면 홈에 저장 본문이
   나오지 않는 것이 정상 동작이다.
2. `publication.spec.ts` 2건과 나머지 기존 실패는 이 작업 범위 밖이다. 손대지 않았다.
3. `previewView.ts` 입력형을 좁히지 않고 타입 경계에서 맞췄다. 계획이 요구한 대로 파일 소유권
   변경 전 보고 대상이며, 실제 계약 확정 후 좁히는 편이 좋다.

## 사용자 추가 기준 반영 (2026-11-13 00:59)

조정자 후속 메일 5건(msg_7e5b040ce870, msg_6dd45be4d6c5, msg_c8985fb2dce5, msg_281a86b9b6eb,
msg_d0e5a8d1b70c)과 `2026-11-13-home-stored-preview-acceptance.md`를 읽고 최소 보완만 했다.
메일 소비는 msg_1e2e3d935ecc로 보고했다.

### 원칙 로딩 보완

지적대로 처음에 적용을 선언한 두 원칙의 leaf를 읽지 않은 상태였다. 이번에 직접 읽었다.

- `.agents/skills/principle-laziness-protocol/SKILL.md`: 결정은 한 곳에 모으고 diff를 최소화한다.
- `.agents/skills/principle-model-the-domain/SKILL.md`: 분기를 흩어 놓지 말고 자료 구조 하나로
  도메인을 표현한다.
- `poteto-mode/SKILL.md`는 shasum `70faeea6...b936`(24986 bytes)로 미변경 확인했다.

### 달라진 선택

- **absence를 서버가 한 값으로 정한다.** 화면에서 `kickoff_at`과 현재 시각을 다시 비교하면
  클라이언트 시계에 따라 같은 경기가 다른 문구로 보인다. 서버가 `upcoming_overdue` /
  `upcoming` / `past` 중 하나를 정해 내려주고 화면은 문구만 고른다(Model the Domain).
- **경계 상수를 한 곳에 둔다.** `ABSENCE_DUE_SECONDS = 6h` 하나만 쓰고 화면·서버에 6시간
  비교를 반복하지 않는다(Laziness Protocol: 결정 통합).
- **기존 prematch 렌더 경로를 홈에서 제거했다.** 문서 없음은 "안내 문구만 있는 단일
  컴포넌트"라는 요구를 지키려면 옛 경로가 함께 그리지 않아야 했다. 그 결과 홈은 저장 문서
  한 곳만 읽는다. `getHomePreview` 클라이언트 함수는 남겨 두었다(다른 용도 삭제는 범위 밖).

### 문서 없음 상태

`absence` 상태별로 문구 하나만 표시하고 빈 카드·중복 생성 예정 문구·자료 시점 설명·
다시 확인 버튼을 두지 않는다. 조회 오류만 별도 상태로 남겨 "다시 확인"을 제공한다.

- `upcoming_overdue`(0 < 남은시간 <= 6h): "경기 시작이 6시간 이내로 다가왔지만 프리뷰가 아직
  생성되지 않았습니다." 실제 실패 근거가 없으므로 실패로 단정하지 않는다.
- `upcoming`(6시간 초과 미래): 기본 생성 시점 안내.
- `past`(킥오프 시각 이후): 앞으로 생성 예정이라고 표현하지 않는 없음 안내.

경계는 고정 시각 합성 검사로만 확인했다. 시스템 시각·DB 경기 시각·계정은 변경하지 않았다.

### 첫 진입 자동 표시와 스크롤 흐림→선명

- 첫 진입에서 추천 목록을 받은 뒤 기본 선택 경기의 문서를 바로 요청한다. 별도 클릭이 필요 없다.
  추천 순서는 프리뷰 유무로 바꾸지 않았다.
- 스크롤 효과는 기존 `updateReveals`를 그대로 쓰고 대상에 홈 컨테이너 안의
  `.hp-stored-document .mpv-section`을 더했다. `--reveal` 값은 최대값으로 누적되므로 이미
  선명해진 섹션은 다시 흐려지지 않는다. 규칙은 `home-preview.css`에만 추가했고 공통
  `body.css`·`MatchPreviewBody.vue`는 고치지 않았다. reduced-motion에서는 즉시 선명하다.

### 추천 preview 상태와 실제 본문 불일치 (확인 결과)

불일치가 **있다**. `GET /api/v1/home/recommendations`의 `items[].preview`는 여전히 옛
publication/version 저장소 값을 보고하므로, 새 문서가 있어도 `pending`/`unavailable`로 나올 수
있다. 다만 이 필드는 **홈 화면이 읽지 않는다**(`HomeRecommendedSection.vue`는 `items[]`에서
`fixture_id`·대진·대회·상태·킥오프만 쓴다). 그래서 사용자가 보는 본문과 상태가 어긋나지는
않는다.

최소 연결을 `app/services/home_preview.py` 범위에서 하려면 `recommendations()`가 후보마다
`preview_dev`를 조회해야 하는데, 그 함수는 public 세션(`app.db`)만 받고 `preview_dev`
세션은 다른 의존성이다. 이 변경은 세션 배선과 응답 계약(스키마·계약 JSON)을 함께 건드려
"최소"가 아니고, 이번 요구의 사용자 관점 결과도 바꾸지 않는다. 그래서 **구현하지 않고
사실만 보고**한다. 필요하면 별도 작업으로 세션 주입과 계약 갱신을 함께 처리해야 한다.

### 이번에 바꾼 파일

- `app/services/home_preview_document.py`: `absence_notice`, `empty_document`의 `absence`,
  `read_document`의 `now` 주입.
- `frontend/src/lib/api/homePreviewDocument.ts`: 계약에 `absence` 추가.
- `frontend/src/components/home-preview/HomeRecommendedSection.vue`: 문서 단일 소스,
  문서 없음 단일 안내, 섹션별 흐림→선명 대상 추가, prefetch 제거.
- `frontend/src/styles/home-preview.css`: 홈 한정 `.mpv-section` reveal 규칙.
- `tests/unit/test_home_preview_document.py`: 경계 2건 추가.
- `frontend/src/components/home-preview/HomeRecommendedSection.test.ts`: 없음/미생성/오류 3건.

`MatchPreviewBody.vue`, `body.css`, 관리자 기능, 원문 저장, `Plans.md`는 그대로다.

`EDITING STOPPED`. 편집과 백그라운드 작업을 모두 끝냈다.

## HP-FIX 검토 지적 1·2 수정 (2026-11-13 02:00)

입력: `home-stored-preview-review.md` 지적 1·2, `2026-11-13-home-stored-preview-acceptance.md`,
이 보고서의 앞 절. 참고 지적 3~9는 이번 범위가 아니므로 손대지 않았다.

### 지적 1 — 구성본 선택이 공개 불가일 때 다른 행으로 대체되던 결함

`_chosen_rows`가 선택 행을 `continue`로 건너뛴 뒤 두 번째 루프에서 같은 워크플로우를
최신 공개 가능 행으로 다시 채우고 있었다. 함수 docstring은 "대신 넣지 않는다"고 적혀
있어 코드와 설명이 어긋난 상태였다. 이제 선택이 걸린 워크플로우를 `claimed`에 먼저
기록하고 채우기 대상에서 제외한다. 그 섹션은 빠지고 다른 버전이 대신 들어가지 않는다.
설계가 말한 "섹션 제외"가 코드에서 실제로 성립한다. 호출부·공개 계약·승인 정책·
무쓰기 GET은 그대로다.

수정 전후를 직접 대조했다. 합성 입력 `a1(v1, 승인)`, `a2(v2, 미승인)`, 선택 `["a2"]`에서
수정 전 알고리즘은 `["a1"]`을 골랐고(대체 발생), 수정 후에는 표시 가능한 섹션이 없어
문서가 만들어지지 않는다.

### 지적 2 — 경기 전환 지연 응답 대표 단위 검사

`HomeRecommendedSection.test.ts`에 두 경기 추천에서 첫 경기 문서 응답 promise를 붙잡아
두고 둘째 경기로 전환한 뒤, 붙잡아 둔 응답을 늦게 resolve시켜 제목·본문·`data-fixture-id`가
둘째 경기로 남는지 확인하는 검사 1건을 추가했다.

이 검사가 실제로 결함을 잡는지도 확인했다. 두 가드(순번 `documentId`, 경기 ID 일치)를
모두 제거하면 `expected '주목 선수첫 경기 본문' to contain '둘째 경기 본문'`으로 실패한다.
한쪽만 제거하면 통과한다. 즉 두 가드가 독립적으로 겹쳐 방어하고 있으며, 제품 코드는
고칠 필요가 없어 손대지 않았다(지시 2항).

### e2e 계약 갱신

`frontend/e2e/home-preview-live.spec.ts`를 현재 계약으로 다시 썼다. 옛 `/prematch` mock을
`/document` 합성 응답으로 바꾸고, 사라진 선택자(`.hp-lead`, `.hp-tools`, `preview-sources`,
`data-gap-summary`, `key-absence`, `player-watchpoint`, `.hp-prediction`)를 저장 본문의
대응 동작으로 교체했다.

제거된 옛 UI 요구와 그 대체:

| 옛 요구 | 처리 |
|---|---|
| `.hp-lead` 한줄 전망 | 저장 본문의 `match-preview-body` 카드·본문 섹션으로 대체 |
| 출처 접이식(`preview-sources`), 자료 확인 현황(`data-gap-summary`) | 제거된 UI. 출처는 카드 하단 `mpv-sources`로 대체되고, 본문에는 접이식이 없음을 단언 |
| 핵심 결장 카드 상한 4·전체 목록(`key-absence`/`all-injuries`) | 부상 카드(`mpv-entry`)와 저장 본문으로 대체 |
| 주목 선수 아코디언(`player-watchpoint`) | 선수 카드(`mpv-entry__name`/`photo`)로 대체 |
| 생성 예정 시각(`generation_due_at`) | 없음 안내(`stored-document-absent`)의 구간별 문구로 대체 |
| 모의 payload 거부(`is_mock`) | 서버 책임으로 이동. 프론트는 **계약 위반 응답을 성공으로 그리지 않음**을 단언하는 검사로 대체 |
| 문서 있음/없음/오류 구분, 첫 진입, 전환, 배당이 선택 팀을 따름, 방송 권한 | 유지 |

skip·무조건 성공·검사 삭제는 쓰지 않았다. 검사 수는 13 → 14로 늘었다(계약 위반 검사 추가).

이 e2e는 **합성 응답**만 쓴다. 실제 승인된 저장 문서의 실화면 성공을 뜻하지 않는다.
이름과 이 절에 그 구분을 적었다. 실제 승인POST·생성·수집·모델·DB쓰기·기존 운영자료
변경은 없었다.

### 명령별 결과

| 명령 | 결과 |
|---|---|
| `.venv/bin/python -m pytest tests/unit/test_home_preview_document.py -q` | **14 passed** (13 + 구성본 대체 방지 1) |
| `npm run test:unit -- src/components/home-preview/HomeRecommendedSection.test.ts` (cwd frontend) | **5 passed** (4 + 지연 응답 1) |
| `npm run test:e2e -- e2e/home-preview-live.spec.ts --project=chromium-mock` (cwd frontend) | **실행 불가**. 저장소 설정이 요구하는 `chromium_headless_shell-1223`이 없어 14건 모두 `browserType.launch: Executable doesn't exist`로 실패했다. 브라우저 설치·설정 변경은 하지 않았다 |
| 위와 동일 검사를 이미 설치된 `chromium_headless_shell-1254`로만 지정한 임시 설정 실행 | **14 passed (7.9s)**. 임시 설정 파일은 실행 후 삭제했고 저장소 `playwright.config.ts`는 무변경이다 |

e2e는 `localhost:5173`의 기존 서버를 재사용했고 서버를 중단·재시작하지 않았다.

### 적용 원칙과 달라진 선택

- **Prove It Works.** 새 단위 검사가 수정 전에도 통과하는지 직접 확인했다. 지연 응답
  검사는 가드를 제거하면 실패하고, 구성본 검사는 수정 전 알고리즘으로 `["a1"]`이 나오는
  것을 별도로 재현했다. 그래서 "검사는 있는데 아무것도 잡지 못하는" 상태가 아니다.
- **Test Behavior, Not Implementation.** 지연 응답은 내부 함수가 아니라 화면에 남는
  본문·`data-fixture-id`로 판정한다.
- **Laziness Protocol.** 구성본 수정은 `_chosen_rows` 한 함수, 검사는 각 1건으로 끝냈다.
  참고 지적 3~9는 범위 밖이라 손대지 않았다.

### 남은 항목

- 참고 지적 3~9(화이트리스트 키 불일치, replay, reveal 첫 프레임, 요청별 엔진, 실행 조회
  상한, 옛 preview 메타데이터, `getHomePreview` 잔존)는 조정자 판단 대상으로 남긴다.
- 실제 승인된 문서의 실화면 확인(DOC-PRESENT·SELECT·SCROLL·LAYOUT)은 조정자 담당이며,
  승인 기록이 비어 있는 현재로선 여전히 차단 원인이다.
- e2e가 저장소 기본 설정으로 실행되지 않는 브라우저 버전 불일치는 이번 범위 밖 환경
  문제다. 저장소 설정을 바꾸지 않았으므로 조정자가 필요 시 별도로 정리해야 한다.

`EDITING STOPPED`. 백그라운드 작업 0건.

## HP-FIX e2e 범위 확정 반영 (2026-11-13 02:05)

조정자 메시지(msg_291cf5ce378e)의 범위 결정을 반영했다. `home-preview-l3.spec.ts`는
`HOME_PREVIEW_L3=1`·격리 DB/8017·옛 경기 세트 전용 파일이라 편집·실행 대상에서 제외했고,
opt-in/skip 변경도 하지 않았다. 편집한 e2e는 처음 배정대로 `home-preview-live.spec.ts`
한 파일뿐이다(무변경 확인). 옛 최근 5경기 표·출처 접기·자료 확인 현황 UI는 복원하지 않았다.

다만 "옛 컴포넌트 단언 제거를 정보 전체 생략으로 해석하지 말라"는 지적을 반영해,
DOC-PRESENT 필수 항목이 실제로 단언되는지 다시 확인했다. 선수 이름·선수 사진·매체 문장·
배당 세 칸·부상 카드는 이미 단언하고 있었으나 **팀 로고 단언이 빠져 있어** 추가했다
(`.mpv-team__head img`의 `src`가 서버가 준 로고 주소인지). 사용자 영향은 저장 본문에
팀 로고가 실제로 그려지는지 확인되지 않는 것이므로, 홈이 관리자 저장본과 같은 표시를
하는지 판정하는 근거가 비어 있게 된다.

추가 후 같은 한정 합성 e2e를 다시 실행해 14 passed(6.7s)를 확인했다. 저장소가 요구하는
`chromium_headless_shell-1223`이 없어 이미 설치된 1254 바이너리만 지정한 임시 설정을
쓰고 실행 후 삭제했으며 `playwright.config.ts`는 무변경(mtime 11-12 03:17)이다.

DOC-PRESENT 필수 항목별 단언 현황:

| 항목 | 단언 위치 |
|---|---|
| 선수 이름·이유 | `.mpv-entry__name` |
| 선수 사진 | `.mpv-entry__photo img[src]` |
| 팀 로고 | `.mpv-team__head img[src]` (이번 추가) |
| 부상 내용 | `section_availability` 구조 값 `디아스` |
| 매체 | `.mpv-media__text` |
| 배당 | `.mpv-odds__cell dd` 3칸 + 선택 팀 라벨 |
| 예상 점수 | `.mpv-prediction__score` |
| 없음/오류 구분 | `stored-document-absent` / `stored-document-error` |

`EDITING STOPPED`. 백그라운드 작업 0건.
