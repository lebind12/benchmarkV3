# 관리 목업 — 로컬 검증 및 평가 안내

상태: 네 탭의 로컬 목업 구현·L1/L2·빌드 완료. 사용자 화면 평가 대기. BE/실 인증/실 DB 연동·운영 적용·배포는 진행하지 않았다.

## 실행과 격리

- 기본 평가 URL: `http://127.0.0.1:5173/admin/mock`(사용자의 기존 서버에서 실제 동작 확인). 별도 테스트/평가 서버 `http://127.0.0.1:5186/admin/mock`도 실행 중이다.
- 직접 링크: `?tab=targets`, `?tab=execution`, `?tab=history`, `?tab=translations`.
- 기존 5173 서버는 종료/재시작하지 않았다. 별도 프론트 5186을 `VITE_USE_MOCK=false`로 실행했다.
- 페이지가 필요한 관리 MSW만 시작한다. 모든 데이터 요청은 상대 경로 `/api/_mock/management/*`, 샘플 저장 key는 `benchmark:management-mock:v1`이다. 실제 관리 API/DB/외부 API로 fallback하지 않는다.
- 기존 `/admin` 권한/실 API 구현과 기존 authUser/mockRole은 유지했다. 헤더의 개발용 `관리 목업`으로 진입할 수 있다.
- 기본 production build에는 mock route/진입 링크와 AdminMockView chunk가 포함되지 않는다. 명시적 mock 모드는 별도다.

재실행이 필요할 때:

```bash
cd /Users/woolee/benchmark/frontend
VITE_USE_MOCK=false npm run dev -- --host 127.0.0.1 --port 5186 --strictPort
```

## 사용자 평가 순서

1. **수집 대상**: 유로파리그 2026의 편집을 열면 기존 10경기 제한이 채워진다. 비우고 저장하거나 옵션·활성 상태를 변경해 본다. 대상 추가에서 리그/허용 시즌을 선택하고 같은 리그·시즌 재저장도 확인한다. 제외 확인창에는 기존 데이터가 보존됨을 표시한다.
2. **수집 실행**: 활성 대상 체크 → `선택 대상 수집` → 갱신/최초 수집 → 확인 → 샘플 실행. 약 30초간 진행하며 취소할 수 있다. 도중 새로고침하면 같은 샘플 작업이 복원된다. 저장/실패/미처리 수를 나눠 표시한다.
3. **실행 이력**: 상태·이름·날짜로 필터하고 `상세 보기`에서 대상별 결과와 로그를 확인한다. 부분 실패의 재실행은 실패·미처리 대상만 실행 화면에 선택하며 확인 전 새 작업을 시작하지 않는다.
4. **번역 검수**: 리그/팀/선수/감독과 검수/누락 상태로 검색 → 원문과 한국어 두 필드 편집 → 저장/검수 → 변경 이력 확인. 비워 저장한 값은 원문 fallback과 사람 수정 보호로 표시한다.
5. **상황 평가**: 탭 위 `화면 상태 살펴보기`에서 빈 목록·조회 실패·저장 실패·부분 실패·작업 중단·번역 충돌을 적용한다. 번역 충돌은 편집 후 저장할 때 최신값과 내 입력을 비교하게 한다. `차이를 확인하고 편집 계속` 뒤 명시적으로 다시 저장해야 한다.
6. `샘플 초기화`는 이 목업의 변경만 되돌린다. 실제 로그인/서비스 데이터는 변경하지 않는다.

## 실행한 검증

아래는 실제 도구 실행 결과의 요약이다.

| 검사 | 결과 | 범위 |
|---|---|---|
| targeted Vitest | 28 PASS / 4 files | 신규 mock 동작 22개 + 기존 헤더/로그인/가입 6개 회귀 |
| Playwright | 10 PASS | 네 탭/격리·대상/null/upsert·취소/복원·이력 retry·번역/NULL/409·오류 복구·키보드 focus trap/ESC·mobile/dark |
| `npm run build` | PASS | vue-tsc + Vite production build. 평가 화면 기본 production chunk 제외 |
| 실제 브라우저 캡처 | 15 화면 확인 | 1440px desktop 4탭, 390px mobile 4탭, dark 2탭 + 편집/진행/이력/충돌 desktop 4개와 mobile 편집 1개. document/body 가로 넘침 없음, 정상 경로 pageerror/비목업 API 요청 없음 |

```bash
npm run test:unit -- tests/unit/lib/managementMock.spec.ts tests/unit/components/common/AppHeader.spec.ts tests/unit/views/LoginView.spec.ts tests/unit/views/SignupView.spec.ts
./node_modules/.bin/playwright test -c playwright.management.config.ts
npm run build
```

추가 근거는 로컬 `out/management-mock/visual-qa.json`, 기존 5173 서버의 실제 조작을 확인한 `interaction-qa.json`, 같은 폴더의 desktop/mobile/dark 캡처에 있다. out은 gitignored 로컬 산출물이다. backend 인증·실제 DB 복원·실 번역 보호를 이 테스트로 통과했다고 해석하지 않는다.

테스트 중 발견한 숫자형 input의 Vue 자동 변환에 따른 limit 처리 오류와 select의 접근성 이름을 수정했다. 이후 E2E 전체에서 pageerror 0을 확인한다. 모달의 포커스 가두기/복귀와 좁은 화면에서 편집 패널 이동도 검증했다.

## 현재 workflow 상태

`IMPL_IN_PROGRESS`를 유지한다. 로컬 구현/검증은 완료했지만 미커밋/미push 결과를 `IMPL_PUSHED`나 `MERGED`로 기록하지 않는다. 로컬 독립 코드 검토와 사용자 평가를 기록하고, 평가 이후 실제 API 계약/BE 착수 범위를 정한다.

독립 로컬 코드 재검토: **APPROVE**, 추가 critical/major 없음. 최초 수집의 미포함 영역 완료 표시와 카탈로그 검색 후 숨은 선택 문제를 수정하고 unit/E2E 회귀로 검증했다. 상세는 [local review](streamer-management-mock.local-review.md).

## 2026-10-25 피드백 반영 검증

- URL: http://127.0.0.1:5173/admin/mock (기존 실행 중인 Vite 유지).
- 번역 검수에서 전체/번역/미번역 필터를 확인한다. 이름이 있고 짧은 이름이 없는 토트넘은 `번역`이다. 별도 검수 완료 체크는 없다.
- 수집 대상 상단 카탈로그에서 World Cup DB 조회 → 최신화 확인/진행/결과 → 2022 시즌 설정을 확인한다. 최신화 확인/저장/전체 건수는 고정 샘플 7개이며 외부 API를 호출하거나 경기 데이터를 수집하지 않는다.
- 실행 이력의 실패 결과 `실패 로그 보기` → 오류 기본 필터 → 한국어 원인/단계/대상/시도 → 원문 펼침 → 원인별 버튼 필터를 확인한다. 이력 통계는 검색·기간·결과 필터에 연동한다.
- 명령: `npm run test:unit -- tests/unit/lib/managementMock.spec.ts tests/unit/lib/managementLogPresentation.spec.ts tests/unit/components/common/AppHeader.spec.ts tests/unit/views/LoginView.spec.ts tests/unit/views/SignupView.spec.ts` → 33개/5파일 PASS.
- `./node_modules/.bin/playwright test --config playwright.management.config.ts` → 13개 PASS.
- `npm run build` → vue-tsc/Vite PASS.
- 실제 5173 화면 6개 캡처: `out/management-mock/feedback-{desktop,mobile,dark}-{catalog,failure}.png`. `feedback-qa.json`의 pageerror, 비목업 API 요청, 문서 가로 넘침은 모두 0.
- 백엔드/DB/운영 환경 변경 없음. 실제 과거 로그의 완전한 한국어 대응/원인 집계는 미구현이다. 현재는 FE 응답 요구를 샘플로 검증한 상태다.
