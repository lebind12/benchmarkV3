# PF-F 프론트엔드 표시 수정 — 독립 검토 (PF-R-F)

작성: 2026-11-12 KST. 담당: DeepSeek 독립 검토 워커(Orca `dsh-tui`, 실제 세션 모델
`deepseek-ai/deepseek-v4.1-flash-1017`, 사용자 설정 추론 강도 Max 유지).

검토 범위는 [한정 수정 계획](../../superpowers/plans/2026-11-12-preview-feedback-fixes.md)의
**PF-F 하나**다. 근거 문서는 `pf-frontend-report.md`(구현 워커 보고)다.

이 워커는 **읽기 전용**이다. 제품 코드·테스트·`Plans.md`·backend·문서 승인 기록 편집 **0건**,
이 보고서 1개만 새로 작성했다. 새 모델 호출 0, DB 쓰기 0, 서버 제어 0, 브라우저 0,
전체 suite 0, 커밋 0. 하위 워커 0.

## 0. 결론

**차단 항목 없음.** PF-F의 수용 기준 5개는 모두 코드와 실행 증거로 확인됐고,
보고된 `vitest 3파일 28 passed`와 `type-check 0`도 재실행으로 일치했다.
다만 **`npm run type-check`가 실제로는 아무 파일도 검사하지 않는 설정**이라
"오류 0"의 의미가 보고서 문구보다 약하다. 이는 PF-F가 만든 결함이 아니고
이번 4파일 범위 밖(루트 `tsconfig.json`)이며, 아래 §4-1 참고 개선으로만 남긴다.

## 1. 확인한 파일과 읽기 전용 확인

| 파일 | mtime (KST) | 상태 |
|---|---|---|
| `frontend/src/lib/api/previewView.ts` | 11-12 19:39:57 | 읽음 |
| `frontend/src/components/home-preview/MatchPreviewBody.vue` | 11-12 19:46:53 | 읽음 |
| `frontend/src/components/home-preview/MatchPreviewBody.test.ts` | 11-12 19:41:21 | 읽음 (신규) |
| `frontend/src/components/management/PreviewPanel.test.ts` | 11-12 19:46:41 | 읽음 |
| `frontend/src/components/management/PreviewPanel.vue` | 11-12 06:43:15 | 읽음 — **PF-F 창(19:39~19:47) 안에 변경 없음** = 보고의 "변경 없음"과 일치 |

검토 후 네 파일의 mtime은 검토 전과 동일하다(위 값 그대로). 이번 검토 중 저장소에
남긴 파일은 이 보고서뿐이며, 검증용 임시 스크립트는 모두 `/tmp/pff-review/`(저장소 밖)에서
실행했다.

## 2. 수용 기준별 대조

### 2-1. 주목 선수/AI 전망 제목·본문 각 1회

실제 저장본 대표 입력(reader 응답 `section_players` 본문 + R4 구조화 선수 4명,
`section_ai_forecast` 본문·근거 2건·점수 2-0, 배당 사유만 있는 행)을
`toMatchPreviewView` → `MatchPreviewBody` SSR로 그려 측정했다.

| 측정 | 수정 전 코드 | 현재 코드 |
|---|---|---|
| 제목 `주목 선수` | **2** | **1** |
| 제목 `AI 경기 전망` | **2** | **1** |
| 도입 문장 `이번 경기의 주목 선수 4명입니다.` | 1 | **1** |
| 전망 본문 문단 | **2** | **1** |
| 근거 1·2 | 1 / 1 | 1 / 1 |

수정 전 값은 구현 워커가 보고한 `COUNT_INTRO=2 COUNT_FORECAST=2 COUNT_TITLE_PLAYERS=2
COUNT_TITLE_AI=2`와 독립적으로 일치한다. 수정 전 컴포넌트는
`push(id, cardShown, leftoverLines)` 형태로 카드가 그린 뒤에도
`playerIntro`/`forecastLines`를 **같은 제목의 별도 섹션**으로 다시 그렸고
(`MatchPreviewBody.vue` 구버전 129~148행), 현재는 `push(id, cardShown)` 으로
카드가 그린 섹션을 아예 넘기지 않는다(현재 131~146행). 실제 결함이 있었고 그것이 제거됐다.

도입 문장은 버려지지 않고 카드 안 `mpv-lead--intro`로 한 번 그려진다
(`MatchPreviewBody.vue` 212~217행). 측정에서도 1회다.

### 2-2. 의미 있는 도입·근거·점수 및 기존 fallback 보존

- **도입 문장**: `playerIntro`(=`introLines(body, {dropLabels: PLAYER_LABELS})`)가
  `MatchPreviewBody.vue` 213행에서 카드 안에 그려진다. 확인된 유일한 손실 경로는
  §4-2 참고.
- **근거·점수**: `forecast.reasoning`, `forecast.score`, `lean_label` 모두 카드 안에서
  그대로 그려진다(`MatchPreviewBody.vue` 187~205행). SSR 측정에서 `홈 강세가 근거입니다.`
  1회, `2:0` 표시 확인.
- **fallback 보존**: 카드가 **없을 때**(구조화 값 없음)만 `cardLeftovers`가 저장 본문
  전체를 그 섹션 제목으로 한 번 그린다(현재 131~146행). 즉 중복 제거가
  "본문 유실"로 이어지지 않는다. 구조화 값이 일부만 있는 경우 `introLines`가
  카드가 그리지 않은 줄을 남기는 규칙도 그대로다(`previewView.ts` 402~426행).
- **섹션 미선택 시**: reader가 섹션을 고르지 않아도 `pickSections`가 최신 행을 쓰고,
  reader 응답에만 있는 섹션은 `readerOnlySections`가 채운다(`previewView.ts` 431~513행).
  이 경로는 이번 변경에서 손대지 않았다.

### 2-3. 배당 실제값 / 없음 진단 구분

| 상황 | 기대 | 측정 결과 |
|---|---|---|
| 저장 배당 없음(실제 저장본 모양: `available=false`, `odds=[]`, 사유 있음) | 표 0, 사유는 진단에만 | 표 0, `missing`에 `배당 표를 표시하지 않았습니다. <저장 사유>`, 본문에 사유 문장 **없음** |
| 배당 값 있음 | 소스별 1X2 세 칸 그대로 | `['1.35','5.20','8.00']`, `Bet365` 표시 |
| 사유가 저장되지 않음 | 사유를 지어내지 않음 | `missing`에 배당 항목 없음 |

구현은 `MISSING_ODDS_PREFIX` + `reasonOf()`(`previewView.ts` 156, 583~598, 646~657행)로
`unavailable_reason`만 읽고, 값이 없으면 `null`이다. 진단은 관리자 접힌 영역의
`preview-missing`(`PreviewPanel.vue` 551~554행)에서만 보이고, `MatchPreviewBody`는
`missing`을 전혀 읽지 않는다(본문 오염 0). 실제 저장본 `section_odds`의 사유
"정규시간 1X2 값이 모두 있는 배당 줄이 없어 이 선택 섹션을 표시하지 않습니다."가
`missing`에 그대로 들어가는 것을 확인했다. **자료 미제공과 표시 오류가 구분된다.**

### 2-4. 기존 사진·이름 강조·선택 버전/재생성 유지

| 항목 | 확인 |
|---|---|
| 사진 | 서버가 준 `photo_url`만 사용. SSR 측정에서 `players/1100.png` 렌더, 내부 ID(533)로 주소 조립 0. 팀 로고는 로컬 렌더에서 홈만 그려졌는데, 이는 `resolveSides`가 원정 팀 좌우를 확인하지 못해 `side=null`이 되어 로고를 붙이지 않는 **기존 규칙**(`MatchPreviewBody.vue` 83~86행)이며 이번 변경과 무관하다 |
| 이름 강조 | `InlineEmphasis`(strong 노드)만 사용. 네 파일에 `v-html` 0건(grep). `**리그 10경기 9골**`이 `strong` 2개로 렌더되고 원문자 그대로 노출 |
| 선택 버전 | reader가 고른 `version`만 표시. v1/v2를 함께 둔 입력에서 v2 본문만 나오고 v1 문장은 나오지 않음 |
| 재생성·구성본 | `PreviewPanel.vue`의 `SectionRegenerationPanel`·`CompositionPanel`·`preview-reader-sections` 블록은 이번 변경 창에 수정되지 않았다(06:43 이전 mtime) |

## 3. 보고된 검증 근거 대조

보고서 §4의 명령을 **그대로** 재실행했다.

```
cd frontend && npx vitest run \
  src/components/management/PreviewPanel.test.ts \
  src/features/match-preview/MatchPreview.test.ts \
  src/components/home-preview/MatchPreviewBody.test.ts

 ✓ MatchPreviewBody.test.ts (3 tests)
 ✓ MatchPreview.test.ts (8 tests)
 ✓ PreviewPanel.test.ts (17 tests)
 Test Files 3 passed (3) / Tests 28 passed (28)
```

파일별 건수도 보고와 일치한다(3 + 8 + 17 = 28). `PreviewPanel.test.ts`의 기존 17건은
늘지 않았고(보고의 "검사 개수 17건 그대로" 확인), 신규 3건은 `MatchPreviewBody.test.ts`에만 있다.

```
cd frontend && npm run type-check   →  vue-tsc --noEmit, exit 0
```

exit 0은 재현된다. 다만 아래 §4-1 때문에 이 0은 "검사한 파일이 없어서 0"이다.

`PreviewPanel.test.ts` 실행 중 stderr의 `TypeError: Cannot read properties of undefined
(reading 'ok')`도 재현됐고, 발생 위치는 보고대로 `preview.ts:77` ← `PreviewPanel.vue:308`
← `generate()`이며 `readerPreview` mock 미설정 검사에서 나온다. **PF-F 변경 이전부터
있던 동작**이고 검사는 통과한다. 보고의 설명과 일치한다.

## 4. 지적 사항

### 4-1. [참고 개선 · 차단 아님 · PF-F 범위 밖] `npm run type-check`가 파일을 0개 검사한다

`frontend/tsconfig.json`이 solution 스타일(`"files": []` + `references`)로 바뀌어 있고
`npm run type-check`는 `vue-tsc --noEmit`(프로젝트 미지정)이다. 실측:

```
npx vue-tsc --noEmit --listFilesOnly  → 0줄 (검사 대상 파일 0개)
npx tsc -p tsconfig.json --listFilesOnly → 0줄
```

즉 보고서의 "type-check 오류 0"은 **타입 오류가 없다는 증거가 아니라 검사가 실행되지
않았다는 뜻**이다. 실제로 프로젝트를 지정하면 오류가 나온다:

```
npx vue-tsc -p tsconfig.app.json --noEmit   → exit 2, 아래 오류
  MatchPreviewBody.test.ts(74,87,97,112,124,134): 'structured' does not exist in Partial<SectionResultView>
  PreviewPanel.test.ts(425,461,507,664,756,769,823,855,918): 같은 오류
  BundleGenerationPanel.test.ts(57): toHaveBeenCalledExactlyOnceWith 미지원
  lib/api/preview.ts(16): 'previewRequest' 미사용
npx vue-tsc -b   →  exit 2 (같은 오류, build 게이트도 실패)
```

원인은 `SectionResultView` 타입에 `structured`가 없는데 테스트가 `as Partial<SectionResultView>`
로 넘기기 때문이다(`types.ts` 364~390행). 이 관용 타입 부재는 **PF-F 이전부터** 있었고,
`BundleGenerationPanel.test.ts`·`preview.ts` 오류도 PF-F 소유 파일이 아니다.
PF-F가 만든 것은 `MatchPreviewBody.test.ts`의 6건뿐이며, 이는 같은 기존 패턴을 따른 결과다.

- 이번 PF-F의 수용 기준("PreviewPanel 및 영향 있는 테스트만 vitest 실행, npm run type-check")은
  보고된 명령을 그대로 실행해 통과했다는 점에서 충족이다.
- 그러나 **타입 안전망이 사실상 꺼져 있다**는 사실은 조정자가 알아야 한다. `tsconfig.json`은
  PF-F 소유가 아니고 이번 계획 범위도 아니므로 차단하지 않고 후속 후보로만 남긴다.
- 부수 확인: 계획에 적힌 명령을 문자 그대로 따르면 이 결함을 잡을 수 없다. 계획의 검증
  문구를 다음에 손볼 때 `vue-tsc -p tsconfig.app.json` 또는 `vue-tsc -b`로 바꾸는 편이 좋다.

### 4-2. [참고 개선 · 차단 아님] 카드가 그리는 섹션의 나머지 저장 문장이 화면에 남지 않는다

현재 `cardLeftovers`는 카드가 그린 섹션을 **전부** 건너뛴다(`MatchPreviewBody.vue` 131~146행).
그래서 카드가 그리지 않는 문장이 저장 본문에 있으면 본문 화면에서는 사라진다. 실제 저장본
본문으로 측정한 결과:

```
확인된 부상·결장 상황만 정리했습니다.            → 0회
이 서비스의 판단과는 별개입니다.                 → 0회
수집한 기사에서 확인한 외부 매체의 이 경기 전망입니다. → 0회
```

- 부상: `section_availability` 구조화 값이 있으면 카드가 선수·상태·요약을 그리지만,
  본문의 `### 팀` 구획과 "확인된 부상·결장 상황만 정리했습니다." 도입 줄은 어디에도 안 나온다.
- 매체: `section_outlook` 카드가 발행사·문장은 그리지만 "이 서비스의 판단과는 별개입니다."
  라는 **성격 구분 문장**은 사라진다.

이것은 PF-F가 만든 회귀가 아니다. 수정 전 코드에서도 `push('section_availability', …, [])`처럼
카드가 그린 섹션에는 빈 배열을 넘겨 같은 문장이 나오지 않았다(구버전 144~146행). 즉 이번
변경은 부상·매체의 손실을 **새로 만들지 않았고**, 주목 선수·AI 전망의 도입 문장만 카드 안으로
옮겨 살렸다.

- 계획의 PF-F 기준은 "주목 선수와 AI 전망 … 각각 한 번"이고, 부상·매체 도입 문장은 명시
  대상이 아니다. 그래서 차단하지 않는다.
- 다만 "각각 한 번 표시"를 만족시키면서 해당 섹션의 의미 있는 문장을 모두 남기려면,
  주목 선수에 적용한 방식(카드 안 도입 줄)을 부상·매체에도 같은 규칙으로 넓히는 것이
  자연스럽다. 사용자에게 보이는 결과: 부상 섹션에서 "확인된 부상·결장 상황만"이라는
  자료 범위 문장과, 매체 섹션에서 "우리 판단과 별개"라는 구분 문장을 다시 읽을 수 있다.
  필요하면 후속 후보로 분리하는 편이 좋다.

### 4-3. [참고 개선 · 차단 아님] 값 없는 배당 행이 오면 `—` 세 칸짜리 표가 그려진다

`toOddsRows`는 `structured.odds`에 행이 하나라도 있으면 표를 만든다(`previewView.ts` 542~556행).
`parseOdds`는 북메이커 이름만 있어도 행을 만든다(`sectionStructured.ts` `parseOdds`).
그래서 reader가 배당 섹션을 **선택한** 경우(본문이 비어 있지 않은 경우)에 한해
`['—','—','—']` 표가 나올 수 있다. 실측:

```
ODDS_TABLE_COUNT = 1, ODDS_CELLS = ["—","—","—"], MISSING = [사진 안내만]
```

현재 실제 저장본은 `odds=[]`이고 reader 목록에도 배당이 없어 이 경로를 타지 않는다.
backend도 세 값이 다 있는 줄만 `rows`에 넣으므로(`bundle_sections.py` `_odds_section`)
현재 계약에서는 도달하기 어렵다. 그리고 이 동작은 PF-F 이전부터 동일하다(이번 변경은
`odds` 계산을 지역 변수로 옮긴 것뿐). "합성값 금지"는 지켜지고 있으나, **"값이 없으면 표를
만들지 않는다"**를 더 엄격히 적용하려면 셋 다 `null`인 행은 거르는 편이 낫다.

### 4-4. [관찰] 사진 없는 선수는 이름이 사진 자리에 한 번 더 그려진다

`MatchPreviewBody.vue` 250·297행이 사진 대체로 선수 이름을 `role="img"` 안에 그린다.
SSR 측정에서 선수 이름이 2회(카드 제목 1 + 사진 자리 1) 나온다. 화면 설계상 의도된
placeholder이고 중복 섹션 문제와는 별개다. 이번 변경과 무관하며 조치 불필요.
(확정 목업의 `PreviewPlayerPhoto.vue`는 아이콘 placeholder를 쓴다. 디자인 통일 관점의
차이는 있으나 PF-F 판단 범위 밖이다.)

## 5. 계획·범위 준수 확인

| 확인 | 결과 |
|---|---|
| PF-F 소유 4파일만 수정됐는가 | PF-F 편집 창(19:39~19:47) 안에서 바뀐 프론트엔드 파일은 정확히 그 4개. `PreviewPanel.vue`·`CompositionPanel.vue`·`SectionRegenerationPanel.vue`·`sectionStructured.ts`는 변경 없음 |
| backend를 건드렸는가 | 같은 창에 `app/preview/section_structured.py`, `sources/provider_odds.py`, `app/api/v1/preview_admin.py`가 바뀌었으나 **PF-B의 동시 작업**이다. PF-F 보고도 backend 무변경을 명시하며, 이 검토는 그 변경을 **평가하지 않았다** |
| `Plans.md`·승인 기록 | PF-F 창에 변경 없음(Plans.md 20:08은 조정자 갱신). 이 검토 워커도 편집 0 |
| 새 모델 호출·DB 쓰기·서버 제어 | PF-F 보고 0, 이 검토도 0. 검증은 모두 고정 입력 기반 |
| 식별자 안전성 | 내부 `player_id`(533)로 사진 URL 조립 0, `http(s)`만 통과, 팀 좌우는 확인된 ID/라벨만 사용. 기존 테스트 3건이 이를 계속 검사한다 |

## 6. 미완·확인하지 못한 것

- **실제 화면 확인은 아직 없다.** 이 검토는 SSR/고정 입력 렌더와 저장본 대표 입력의 값
  대조까지다. 브라우저는 root 소유이고 현재 로그아웃 관측 상태라 관리자 화면을 직접 열지
  않았다. 따라서 "원래 디자인 유지"(계획 PF-F 기준)와 실제 배당 가용성은 **PF-UI 확인 대상**으로
  남는다.
- **실제 배당 값은 여전히 없다.** 저장본 `section_odds`는 `available=false`, `odds=[]`,
  사유 "정규시간 1X2 값이 모두 있는 배당 줄이 없어…"다. PF-F는 사유를 진단에 보이게 했을 뿐
  실제 배당을 만들지 않는다. 채우려면 PF-B의 실제 공급 경로나 관리자 전용 배당 섹션 실행이
  필요하고, 이는 root 판단 사항이다.
- **부상 한글명·사진 연결은 PF-B 소유**다. 이 검토는 그 변경을 평가하지 않았다.
- 전체 suite·미지원 환경·범용 강화·브라우저 자동화는 범위 밖이라 실행하지 않았다.

## 7. 실행한 명령

```
# 1. 보고된 검증 재현
cd frontend && npx vitest run \
  src/components/management/PreviewPanel.test.ts \
  src/features/match-preview/MatchPreview.test.ts \
  src/components/home-preview/MatchPreviewBody.test.ts
→ Test Files 3 passed (3) / Tests 28 passed (28)

cd frontend && npm run type-check
→ vue-tsc --noEmit, exit 0   (단, 검사 대상 파일 0개 — §4-1)

# 2. type-check 실효성 확인
cd frontend && npx vue-tsc --noEmit --listFilesOnly       → 0줄
cd frontend && npx vue-tsc -p tsconfig.app.json --noEmit  → exit 2, 오류 17건
cd frontend && npx vue-tsc -b                             → exit 2

# 3. 저장본 대표 입력 렌더 측정 (저장소 밖 /tmp/pff-review/)
cd frontend && npx vite-node /tmp/pff-review/render.ts      # 제목/문장 횟수
cd frontend && npx vite-node /tmp/pff-review/preserve.ts    # 사진·강조·버전·배당
cd frontend && npx vite-node /tmp/pff-review/oddsprobe.ts   # 값 없는 배당 행
```

입력 값은 `docs/implementation/match-preview/evidence/ps05-live/reader-preview-9c079eea.json`
(섹션 본문)과 `evidence/ps05-live/live-20261111T105521Z-9c079eea….json`(배당 사유)에서
그대로 옮겼다. 저장소 밖 임시 스크립트만 썼고 제품 파일은 수정하지 않았다.
