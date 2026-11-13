# PF-F 관리자 프리뷰 표시 수정 보고

작성: 2026-11-12 KST. 담당: DeepSeek 구현 워커(Orca `dsh-tui`, 실제 모델
`deepseek-ai/deepseek-v4.1-flash-1017`, 사용자 설정 추론 강도 Max 유지). 범위는
[한정 수정 계획](../../superpowers/plans/2026-11-12-preview-feedback-fixes.md)의 PF-F 하나다.
backend·Plans.md·문서 승인 기록은 건드리지 않았다. 새 모델 호출 0, 서버 제어 0, DB 쓰기 0,
브라우저 0, 전체 suite 0, 커밋 0.

## 1. 고친 것

사용자가 관리자 저장본 `6c2ce4c2-68c5-4d9b-8863-ac068e063c58`(fixture 1557474, live,
succeeded)에서 본 중복은 **표시 어댑터와 본문 컴포넌트의 두 경로가 같은 섹션을 두 번 그려서**
생겼다.

| # | 원인 | 수정 |
|---|---|---|
| 1 | `MatchPreviewBody.vue`의 `cardLeftovers`가 카드가 이미 그린 섹션의 "남은 줄"을 **같은 제목의 별도 섹션**으로 한 번 더 그렸다. 주목 선수는 `playerIntro`("이번 경기의 주목 선수 4명입니다.")가, AI 전망은 `forecastLines`(전망 본문)가 여기로 다시 나왔다 | 카드가 그린 섹션은 `cardLeftovers`에서 제외한다. 카드가 아예 없을 때(구조화 값 없음)만 저장 본문을 그 섹션 제목으로 한 번 그린다 |
| 2 | 카드가 그리지 않는 나머지 문장을 담을 자리가 없어서, 중복을 없애면 도입 문장이 사라질 위험이 있었다 | 주목 선수 카드 **안**(제목 아래·팀 2열 위)에 `mpv-lead--intro`로 저장된 도입 문장을 그린다. AI 전망은 이미 카드 안에서 본문·근거·점수를 모두 그리므로 잃는 문장이 없다 |
| 3 | 배당 표가 없을 때 "왜 없는지"를 관리자 화면에서 확인할 수 없었다(본문에 아무 표시도 없음) | `previewView.ts`가 저장된 섹션 행의 `unavailable_reason`을 읽어 `missing`에 `배당 표를 표시하지 않았습니다. <저장된 사유>`로 남긴다. 본문에는 넣지 않고 진단 영역(`preview-missing`)에서만 보인다. 사유가 저장돼 있지 않으면 지어내지 않는다 |

지킨 것: `**이름**` 강조는 계속 `InlineEmphasis`(strong 노드)만 쓴다(`v-html` 없음). 저장된
선수 이름·선정 이유·부상 요약·매체 문장 등 원문 의미는 그대로다. 사진·로고는 서버가 준 URL만
쓰고 내부 ID로 주소를 조립하지 않는다. 배당 값이 없으면 표를 만들지 않고(`—` 채우기·합성값
금지), 값이 있으면 저장된 1X2 세 칸을 그대로 그린다. 섹션 재생성·선택 버전(구성본)·진단
영역은 손대지 않았다.

## 2. 수정 파일

| 파일 | 변경 |
|---|---|
| `frontend/src/lib/api/previewView.ts` | `MISSING_ODDS_PREFIX` 추가, `reasonOf()`로 저장된 미제공 사유를 읽어 `missing`에 반영, `odds` 계산을 지역 변수로 정리(동작 동일) |
| `frontend/src/components/home-preview/MatchPreviewBody.vue` | `cardLeftovers`를 "카드가 없는 섹션만" 으로 축소, 주목 선수 카드에 저장된 도입 문장 표시, `.mpv-lead--intro` 스타일 1규칙 |
| `frontend/src/components/home-preview/MatchPreviewBody.test.ts` | **신규** 검사 3건(아래 §3) |
| `frontend/src/components/management/PreviewPanel.test.ts` | 기존 2건에 단언 추가(중복 부재, 진단의 배당 사유). 검사 개수는 17건 그대로 |
| `frontend/src/components/management/PreviewPanel.vue` | **변경 없음**(같은 표시 모델을 쓰므로 코드 수정 불필요) |

## 3. 추가한 검사와 수용 기준

`frontend/src/components/home-preview/MatchPreviewBody.test.ts`(신규 3건) +
`PreviewPanel.test.ts`의 단언 추가. 실제 저장본의 reader/section-results 응답 모양을 고정
입력으로 옮겼고 서버·DB·모델을 부르지 않는다.

| 검사 | 수용 기준 | 실패하면 사용자에게 생기는 일 |
|---|---|---|
| 주목 선수·AI 전망 제목/본문이 각각 한 번, 도입 문장은 주목 선수 카드 안 | PF-F "주목 선수와 AI 전망 제목/본문이 각각 한 번 표시" | 같은 선수·전망을 두 번 읽고 어느 쪽이 저장된 결론인지 알 수 없다 |
| 배당 값이 없으면 표를 만들지 않고 사유만 `missing`(진단)에 남김 | PF-F "배당 자료 미제공 원인은 관리자에서 식별 가능", 합성값 금지 | 배당이 있는 것처럼 보이거나, 왜 없는지 확인할 수 없다 |
| 저장된 1X2 값이 있으면 소스별 세 칸을 그대로 표시 | PF-F "기존 유의미 본문·근거·이미지·배당 표 소비 보존" | 실제 배당이 저장돼 있어도 화면에서 사라진다 |
| 관리자 진단(`preview-missing`)에 `배당 표를 표시하지 않았습니다. <저장 사유>`가 보이고 본문에는 없다 | PF-F "배당 실제 자료 미제공은 관리자에서 이유를 알 수 있게" | 관리자가 자료 부재와 표시 오류를 구분하지 못한다 |

## 4. 실행한 검사와 실제 결과

```
cd frontend && npx vitest run \
  src/components/management/PreviewPanel.test.ts \
  src/features/match-preview/MatchPreview.test.ts \
  src/components/home-preview/MatchPreviewBody.test.ts
→ Test Files 3 passed (3), Tests 28 passed (28)

cd frontend && npm run type-check
→ vue-tsc --noEmit, 오류 0 (exit 0)
```

`PreviewPanel.test.ts` 실행 중 stderr에 `TypeError: Cannot read properties of undefined
(reading 'ok')`가 한 번 찍힌다. 기존 검사 "확인한 그 경기 하나만 생성하고…"가 `readerPreview`
mock을 정하지 않은 채 생성 버튼을 눌러 생기는 **기존 동작**이며(이번 변경 이전과 동일), 검사는
통과한다. 이번 범위의 결함이 아니어서 테스트를 고치지 않았다.

재현 검증은 저장본 대표 입력(`6c2ce4c2…` 모양: 네 섹션 + 값 없는 배당 섹션)으로 했다. 수정 전
코드(`cardLeftovers`가 `playerIntro`/`forecastLines`를 다시 그리던 상태)로 되돌려 측정한 값:

```
COUNT_INTRO=2  COUNT_FORECAST=2  COUNT_TITLE_PLAYERS=2  COUNT_TITLE_AI=2
```

수정 후 같은 입력에서 제목·도입 문장·전망 본문·근거·선수 이름이 모두 **각 1회**다.
`PreviewPanel.test.ts`에 넣은 중복 부재 단언도 수정 전 코드에서 `expected 2 to be 1`로
실패하고 수정 후 통과한다. 즉 이 검사들은 실제 결함을 잡고, 수정이 그 결함을 없앤다.


## 5. 미해결·넘긴 것

- **실제 화면 확인은 root 몫이다.** 브라우저 제어·서버 재기동을 하지 않았다. 위 검사는 고정
  입력 기반이며 실제 `run 6c2ce4c2` 화면 확인이 아니다.
- **배당 실제 자료는 여전히 없다.** 저장본의 `section_odds`는 `available=false`, `odds=[]`,
  사유 "정규시간 1X2 값이 모두 있는 배당 줄이 없어…"다. 이번 수정은 **사유를 관리자 진단에
  보이게** 했을 뿐 실제 배당을 만들지 않는다. 실제 배당을 채우려면 backend의 실제 배당 공급
  경로(PF-B 범위)나 관리자 전용 배당 섹션 실행이 필요하며 root 판단 사항이다.
- **부상 한글명·사진은 PF-B 소유다.** 이번 frontend 수정은 서버가 준 `player`/`photo_url`을
  그대로 그리는 경로만 유지했다. backend 계약 변경은 필요하지 않았다(추가 필드 없이 동작).
- 시간대 표시(`formatMoment`)와 홈/수집 연결은 계획상 이번 범위 밖이라 손대지 않았다.

## 6. 후속: 타입 검사 회귀 한정 수정 (2차)

독립 검토([pf-frontend-review.md](pf-frontend-review.md)) §4-1이 지적한 사실 — `npm run type-check`가
`solution` tsconfig 때문에 **파일 0개를 검사**해 타입 안전 근거가 되지 못한다 — 를 조정자가 확인했고,
그 결과 이번 PF-F가 새로 만든 `MatchPreviewBody.test.ts`의 `structured` 오류 **6건**을 직접 회귀(defect)로
배정했다. 같은 패턴의 다른 오류는 참고로 미루고, 이번에 추가한 6건만 없앴다.

### 6-1. 원인

`SectionResultView` 타입에 `structured`가 없는데 테스트 픽스처가 `Partial<SectionResultView>`로
넘기고 있었다. 서버는 실제로 각 섹션 결과 행에 `structured`(및 표시 가능 여부 `available`)를 덧붙이므로
(`app/preview/section_structured.py` `structured_row_from_section_result`), 빠진 것은 **타입 쪽**이다.
그래서 `any`/`as`/`ts-ignore`로 숨기지 않고 **실제 응답 계약을 타입으로 표현**했다.

### 6-2. 수정 (2개 파일)

| 파일 | 변경 |
|---|---|
| `frontend/src/features/match-preview/types.ts` | `SectionStructuredPlayerRow`·`InjuryRow`·`MediaRow`·`OddsRow`·`ForecastRow`·`SectionStructuredProjection` 추가. `SectionResultView`에 선택 필드 `structured?: SectionStructuredProjection`, `available?: boolean` 추가. 키 이름은 서버 출력과 기존 파서(`sectionStructured.ts`) 입력의 합집합만 적었다(선수 `player`/`reason` + 저장 payload 표기 `selected_player`/`selection_reason` 등) |
| `frontend/src/components/home-preview/MatchPreviewBody.test.ts` | 픽스처를 **실제 응답 모양**으로 정렬: `available`을 행 최상위로, 구조 값은 `structured: { players/injuries/media/odds/forecast }`로. 선수 키를 서버가 내는 `player`/`reason`으로, 배당 시각을 `observedAt`으로. 읽지 않는 `detail`은 캐스팅(`as unknown as RunDetail`) 대신 `null` |

`PreviewPanel.test.ts`의 같은 패턴 오류 6건과 `BundleGenerationPanel.test.ts`·`preview.ts` 오류는
이번 소유 범위 밖이라 **고치지 않았다**(조정자 지시대로 참고로 구분). `types.ts`의 다른 부분,
제품 컴포넌트, `tsconfig`·`package.json`은 건드리지 않았다.

### 6-3. 명령과 실제 결과

```
# 1) 이번 변경의 영향 검사 (기존 3파일)
cd frontend && npx vitest run \
  src/components/management/PreviewPanel.test.ts \
  src/features/match-preview/MatchPreview.test.ts \
  src/components/home-preview/MatchPreviewBody.test.ts
→ Test Files 3 passed (3) / Tests 28 passed (28)

# 2) 명시 프로젝트 타입 검사 (1회)
cd frontend && npx vue-tsc -p tsconfig.app.json --noEmit
→ exit 2, 오류 8건 (수정 전 17건)
```

파일별 전후 비교(같은 명령, 같은 설정):

| 파일 | 수정 전 | 수정 후 | 성격 |
|---|---|---|---|
| `src/components/home-preview/MatchPreviewBody.test.ts` | **6** | **0** | **이번 PF-F가 만든 직접 회귀 — 전부 해소**(지시받은 항목) |
| `src/components/management/PreviewPanel.test.ts` | 9 | 6 | 같은 패턴이지만 다른 파일·PF-F 소유 아님. `structured: {}` 3건은 이번 타입 추가로 함께 해소됐고, `available`을 `structured` **안에** 둔 6건(508·757·770·824·856·919)이 남는다 |
| `src/features/match-preview/BundleGenerationPanel.test.ts`(57) | 1 | 1 | `toHaveBeenCalledExactlyOnceWith` matcher 부재. 이번 변경 이전부터 존재 |
| `src/lib/api/preview.ts`(16) | 1 | 1 | `previewRequest` 미사용 import. 이번 변경 이전부터 존재 |
| **합계** | **17** | **8** | |

남은 6건(PreviewPanel)은 같은 원인이고 서버 계약과 맞지 않는 표기(`available`이 `structured`
안에 있음)라, 그 파일을 소유자가 손볼 때 `available`을 행 최상위로 옮기면 사라진다. 이번
지시("다른 제품/검사 편집 금지")에 따라 **고치지 않고 구분해 보고**한다.

`npm run type-check`(exit 0)는 파일 0개 검사이므로 **타입 안전 근거로 쓰지 않는다**. 위
`vue-tsc -p tsconfig.app.json` 결과만 근거다.

### 6-4. 타입을 붙이면서 확인한 계약 불일치 (수정하지 않음)

타입을 서버 출력과 맞추는 과정에서 **기존** 파서 표기 불일치 하나를 확인했다. 범위 밖이라
고치지 않고 기록만 한다.

- 서버 `_odds`는 배당 시각을 `observedAt`(camel)으로 내는데, 화면 `parseOdds`는
  `observed_at`(snake)만 읽는다(`sectionStructured.ts` 267행). 그래서 실제 응답에서는 배당
  출처 시각이 `null`이 된다. 값 자체(1X2 배당)는 정상 표시되고, 이번 저장본은 `odds=[]`라
  사용자 화면에는 드러나지 않는다.
- 이번에 추가한 `SectionStructuredOddsRow`는 **서버가 내는 이름**을 정본으로 적고
  (`observedAt`), 파서가 읽는 `observed_at`도 함께 적어 사실을 숨기지 않았다.
- 실패 시 사용자 영향: 배당 표에 "관측 시각"이 비어 보인다(값·출처는 그대로). 후속 후보.

### 6-5. 남은 것

- `PreviewPanel.test.ts`의 동일 패턴 6건은 위 표대로 후속 후보로 남긴다(소유권·지시 범위 밖).
- 위 6-4의 `observed_at`/`observedAt` 불일치도 후속 후보다(제품 파서 수정은 이번 소유 범위 밖).
- 이번 타입 보완은 **타입만** 바꾼다(런타임 동작·출력·검사 기대값 변화 0). 새 모델·DB·브라우저 호출 0.

## 7. 후속: 배당 관측 시각 보존 (3차)

조정자가 보고서 §6-4의 `observedAt` 미소비를 **이번 배당 연결 수용 기준**(실제값·출처·관측 시각
보존)에 직접 해당하는 결함으로 판정했다. 소유 범위를 `sectionStructured.ts`의 `parseOdds` 시각
입력과 기존 `MatchPreviewBody.test.ts`의 대표 검사로 한정해 고쳤다.

### 7-1. 원인과 수정

- `parseOdds`가 `observed_at`/`collected_at`/`capture_time`/`time`만 읽었고, 서버 정본 키
  `observedAt`(`app/preview/section_structured.py` `_odds`)은 읽지 않았다. 그래서 실제 응답에서
  `structured.odds[].observedAt`이 `null`이 되어 화면 `observed_at` 출력이 비었다.
- 수정은 **키 목록 하나**다. `observedAt`을 **먼저** 읽고 기존 snake-case 표기를 그대로 뒤에
  유지한다. 새 파서·새 필드·다른 필드 정리 없음.
- 아래 흐름은 손대지 않았다: `parseOdds` → `StructuredSectionView.odds` →
  `toOddsRows`(`observed_at`) → `MatchPreviewBody`의 `.mpv-odds__source`.

### 7-2. 검사 (해당 파일 1개만)

`frontend/src/components/home-preview/MatchPreviewBody.test.ts`의 기존 대표 배당 검사를 확장하고
저장 표기 보존 검사 1건을 더했다.

| 검사 | 수용 기준 | 실패하면 사용자에게 생기는 일 |
|---|---|---|
| 서버 `observedAt` 값이 화면 관측 시각으로 표시된다 | 실제 배당은 출처·관측 시각을 함께 보존 | 실제 배당 표에 갱신 시각이 사라져 현재성 판단 불가 |
| 저장 payload 표기(`observed_at`)도 계속 읽는다 | 기존 저장본 표시 보존 | 예전 저장본에서 시각이 갑자기 사라진다 |

```
cd frontend && npx vitest run src/components/home-preview/MatchPreviewBody.test.ts
→ 수정 전: Tests 1 failed | 3 passed (4)   # .mpv-odds__source 없음
→ 수정 후: Tests 4 passed (4)
```

기존 3파일 28검사는 조정자 지시대로 재반복하지 않았다(이번 변경은 배당 시각 입력 1곳).

### 7-3. 타입 상태 (변경 없음)

```
cd frontend && npx vue-tsc -p tsconfig.app.json --noEmit  → exit 2, 오류 8건
```

`sectionStructured.ts`·`MatchPreviewBody.test.ts` 오류는 **0건**이다. 남은 8건은 §6-3과 동일한
기존 오류(PreviewPanel.test.ts 6, BundleGenerationPanel.test.ts 1, preview.ts 1)이며 지시대로
이번 범위에서 고치지 않는다. `tsconfig`·`package.json` 변경 0.

## 8. 편집 종료

이 보고서 작성 시점으로 PF-F 소유 파일 편집을 멈추고, frontend 추가 개선을 더 만들지 않는다.

- 1차: `previewView.ts`·`MatchPreviewBody.vue`(중복 표시·배당 사유) + 신규 검사
- 2차: `types.ts`(구조 값 계약 타입)·`MatchPreviewBody.test.ts`(픽스처 정렬)
- 3차: `sectionStructured.ts`(`parseOdds` 시각 키 1곳)·`MatchPreviewBody.test.ts`(대표 검사 확장)

`PreviewPanel.vue`·`PreviewPanel.test.ts`는 읽기만 했고, `tsconfig`·`package.json`은 건드리지 않았다.
stage/commit 0, 하위 워커 0, 전체 빌드·전체 suite·브라우저·모델·DB·서버 변경 0.
