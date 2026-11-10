# 원문 응답 읽기 좋게 정렬 보기 보고

작성: 2026-11-11 06:49 KST. 담당: DeepSeek 구현 워커
(`hive` / `deepseek-ai/deepseek-v4.1-flash-1017`, `max`, 프로필 `dsh-tui`). 하위 워커 없음.
상태: **수정·검증 완료. 편집 종료(§6).**

## 1. 한 줄 결과

사용자가 본 압축 JSON은 **표시 버그**였습니다. `artifact.body`는 이미 직렬화된 JSON
**문자열**인데, 표시 함수가 문자열을 그대로 돌려주고 있었습니다. 이제 표시 경계에서
파싱해 **2칸 들여쓰기**로 보여 주고, 모델이 만든 중첩 JSON은 **별도 라벨로 따로** 펼쳐
볼 수 있습니다. 저장된 원문·필드·타입은 그대로입니다.

## 2. 정확한 변경

| 파일 | 변경 |
|---|---|
| `frontend/src/features/match-preview/panels/players.ts` | `prettyJsonText(value)`, `parseNestedModelJson(value)` 추가 (기존 공유 파일, 새 의존성 없음) |
| `frontend/src/features/match-preview/ModuleResultPanel.vue` | `artifactText`가 `prettyJsonText`를 쓰도록 수정, `modelJsonParts()` 추가, 응답 탭에 정렬 보기 + 별도 모델 JSON 접이식, `.code--readable` 레이아웃 |

- **새 JSON 뷰어 프레임워크·의존성 없음.** 기존 `<pre>`를 그대로 씁니다.
- `v-html` 쓰지 않습니다. 모든 API 내용은 텍스트로만 다룹니다.

## 3. 지킨 규칙

| 규칙 | 처리 |
|---|---|
| 직렬화 JSON을 표시 경계에서 파싱 | `body`가 `{`/`[`로 시작할 때만 파싱, 실패하면 **원문 그대로** |
| 평문·비JSON | 파싱 시도 없이 원문 유지 |
| 만료·없는 artifact | 이전과 동일하게 사유 문구 표시 |
| 필드 누락·요약 대체 | 하지 않음. 루트 필드 7개 전부 보존 |
| `content.parts[].text` 타입 | **전체 원문 보기에서는 문자열 그대로**(객체로 바꾸지 않음) |
| 중첩 모델 JSON | 별도 접이식에서만 파싱. 유효 JSON일 때만 표시 |
| 라벨 구분 | `Google API 전체 응답 (정렬 보기 · 비밀값 제거 · 메타데이터 포함)` vs `모델이 생성한 JSON (전체 응답 안의 텍스트를 따로 정렬)` |
| 따옴표 이중 이스케이프 | 없음(`JSON.parse` → `stringify` 왕복, 확인함) |
| 저장 바이트 | 무변경 |

검색 메타데이터는 들여쓰기된 원문에서 `candidates[].grounding_metadata`로 바로 찾을 수
있습니다. 별도 대시보드·스키마 뷰는 만들지 않았습니다.

## 4. 검증 (실제 내보내기 예시 사용, 유료 호출 0회)

저장된 두 실행의 실제 artifact를 **읽기 전용**으로 써서 오프라인 렌더를 확인했습니다
(근거: `evidence/readable-response/01-offline-render.json`).

| 예시 | 출력 줄 | 들여쓰기 | 왕복 무손실 | 루트 필드 | candidates | grounding | `parts[].text` 타입 | 중첩 JSON |
|---|---|---|---|---|---|---|---|---|
| `previous-success-full-response.json` | 229 | 예 | **예** | 7/7 | 1 | queries 14 | `string` | 파싱됨(42줄) |
| `latest-full-response.json` | 70 | 예 | **예** | 7/7 | 1 | queries 8 (chunks/supports 0) | `string` | 파싱됨(64줄) |

추가 확인(같은 오프라인):

- 평문 `경기 본문입니다.` → 그대로
- 깨진 JSON `{not valid` → 그대로(빈 문자열로 만들지 않음)
- 빈 값·`null` → `—`
- `{"a":"he said \"hi\""}` → 이스케이프가 늘지 않고 그대로 보존

```sh
npm --prefix frontend run type-check                          # clean (exit 0)
npx vitest run RunInspector.test.ts R4PanelAndBody.test.ts    # 12 passed
```

새 테스트 스위트는 만들지 않았습니다(지시대로 `JSON.stringify`를 그대로 반복하는 저가치
검사는 추가하지 않음).

## 5. 한계

- **실제 브라우저 픽셀 확인은 하지 않았습니다.** 검증은 실제 artifact 데이터 + 타입 검사 +
  기존 렌더 검사 + 오프라인 포맷 확인입니다. 계정 로그인이 필요해 이 작업에서 열지
  않았습니다.
- **Vite가 자동 반영**하므로 backend 재시작은 필요 없습니다. 서버는 건드리지 않았습니다.
- 저장된 본문·원문·버전·승인(0)은 그대로입니다. 이 작업은 보기 방식만 바꿉니다.

## 6. 편집 종료

변경 파일: `panels/players.ts`, `ModuleResultPanel.vue`, 이 보고서, 증거 1건.
`Plans.md`·정책·환경·dist·808 삭제 무변경, `git add -A` 미사용.

여기서 편집을 멈춥니다.
