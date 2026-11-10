# R4 선수 패널 연결·본문 줄바꿈 수정 보고

작성: 2026-11-11 05:02 KST. 작성자: DeepSeek 구현 워커
(`hive` / `deepseek-ai/deepseek-v4.1-flash-1017`, 추론 강도 `max`, 프로필 `dsh-tui`). 하위 워커 없음.
상태: **화면 연결·줄바꿈 표시 수정 완료. 편집 종료(§6).**

## 1. 한 줄 결과

사용자가 요구한 두 화면 결함을 고쳤습니다. **R4 선수 패널이 실행 검사 화면에 실제로
마운트**되고, **섹션 본문에서 '선정 선수'와 '선정 이유'가 서로 다른 줄로** 보입니다.
백엔드·DB·모델을 건드리지 않았고, 유료 호출은 0회입니다.

## 2. 관측된 결함과 원인

| # | 관측 | 원인(코드로 확인) |
|---|---|---|
| 1 | R4 선수 선택이 화면에 없음 | `PlayersPanel.vue`는 존재하지만 `RunInspector.vue`에 **import/mount가 없었다**. R1/R2/R3 패널만 붙어 있었다 |
| 2 | 선수 이름과 이유가 한 줄로 붙음 | R4 본문은 `선정 선수:`/`선정 이유:`를 **한 줄 줄바꿈(`\n`)** 으로 쓰는데, 두 화면 모두 `body.split('\n\n')`로 문단만 나누고 문단 요소에 `white-space` 보존 규칙이 없어 DOM이 줄바꿈을 공백으로 접었다 |

즉 데이터는 맞았고 **표시 계층**이 틀렸습니다. 본문 문자열을 바꾸거나 R4 조립을 고치지
않았습니다.

## 3. 정확한 변경 (소유 파일 2개 + 전용 검사 1개)

| 파일 | 변경 |
|---|---|
| `frontend/src/features/match-preview/RunInspector.vue` | `PlayersPanel` import 추가, `activeModule.module_id === 'R4'`일 때 마운트(기존 R2/R3와 같은 방식으로 저장 payload 전달), `.section-result__body p { white-space: pre-line }` 추가 |
| `frontend/src/features/match-preview/SectionRunView.vue` | `.body p { white-space: pre-line }` 추가 |
| `frontend/src/features/match-preview/R4PanelAndBody.test.ts` | 전용 화면 검사 2건(신규) |

- 패널은 **저장된 payload를 그대로** 받습니다(`activeModuleBody`). 새 변환·새 호출 없음.
- 본문 파싱을 새로 하지 않았습니다. 산문을 정규식으로 쪼개 이름·이유를 뽑는 방식은
  쓰지 않았고, R4가 이미 내는 `selected_player`/`selection_reason` 구조 필드를 그대로 씁니다.
- AI 선정 문구·검증 정책·프롬프트·backend 코드는 **변경 없음**.

## 4. 검사 (실행한 것만)

```sh
# 이번 변경의 전용 화면 검사
npm --prefix frontend exec vitest run src/features/match-preview/R4PanelAndBody.test.ts
#   2 passed

# 영향 받는 기존 화면 검사
npm --prefix frontend exec vitest run \
  src/features/match-preview/RunInspector.test.ts \
  src/features/match-preview/SectionRunView.test.ts
#   14 passed

# 타입 검사 1회
npm --prefix frontend run type-check      # clean (exit 0)
```

합계 16 passed. 새로 만든 검사 2건이 확인하는 것:

1. **패널 도달**: R4 모듈이 선택된 실행 상세에서 `[data-testid="players-panel"]`가 실제로
   존재하고, `선정 선수`/`선정 이유` 라벨과 DB 한국어 이름(`엘링 홀란드`)이 보이며,
   모의·재사용 경로가 화면에 표시된다.
2. **줄바꿈 보존**: R4 본문에서 두 라벨이 **같은 문단 안의 서로 다른 줄**로 남아 있고
   (텍스트에 `\n`이 살아 있고 2줄 이상), 두 화면의 문단 규칙에 `white-space: pre-line`이
   적용돼 있다.

## 5. 한계 (정직하게)

- **CSS 규칙은 소스로 확인했습니다.** SFC의 scoped style은 jsdom에 주입되지 않아 계산된
  스타일을 읽을 수 없습니다. 그래서 첫 시도에서 계산 스타일을 검사하려던 단정은
  **틀린 검사**였고, 데이터(줄바꿈 보존) + 규칙 존재(소스)로 바꿨습니다. 실제 브라우저
  픽셀 확인은 이 작업에서 하지 않았습니다.
- **실제 브라우저 로그인 미확인.** 조정자가 재시작한 백엔드는 health ok지만, 로그인 화면까지만
  확인됐고 실제 자격 증명 입력은 이 작업에서 하지 않았습니다(운영 계정 조작 금지). 그래서
  "운영 화면에서 눈으로 확인됨"이라고 주장하지 않습니다.
- **렌더 증거 입력은 합성 payload입니다.** `origin: 'reused_r1_selection'`, `mode: 'mock'`
  라벨을 그대로 두어 실제 R4 live 생성 증거로 읽히지 않게 했습니다. 오프라인 예시 JSON과 같은
  성격입니다.
- **R4 실제 모델 생성은 여전히 미검증**입니다(유료 호출 0회). 이 작업은 표시 계층만 다룹니다.

## 6. 소유·경계·편집 종료

- 수정한 파일: `RunInspector.vue`, `SectionRunView.vue`, 신규 `R4PanelAndBody.test.ts`,
  이 보고서와 증거(`evidence/r4-ui/`). 그 외 파일은 건드리지 않았습니다.
- `PlayersPanel.vue`·`players.ts`(R4 소유)와 `localized_names.py`(names 소유)는 읽기만 했고
  수정하지 않았습니다. 두 담당은 이미 FINAL EDITING STOPPED입니다.
- backend/frontend 프로세스는 재시작·종료하지 않았습니다(루트 소유). 스키마·DB 쓰기·승인 행
  없음. raw/history/approvals/legacy 삭제/dirty Plans·정책/env/dist 그대로입니다.
- 스테이징은 이번 소유 경로만 지정했습니다(`git add -A` 사용 안 함).
- **편집을 여기서 멈춥니다.** 추가 지시는 조정자가 새 작업으로 배정해야 합니다.

증거: [evidence/r4-ui/01-render-checks.txt](evidence/r4-ui/01-render-checks.txt)
