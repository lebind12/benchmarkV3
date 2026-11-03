# v2 revision 2 — 기본 테스트 검색 범위 보완

- news-developer / `news-context-v2`, revision 2
- 기준 제출 SHA: `e678b7684a98081201fe958c8fe21a297d1c0282`
- 요청 근거: `docs/ax/news-context/operator-review-r1.md`의 default test discovery 수정 요청.
- 이번 제출 커밋은 이 보고서와 `frontend/vitest.config.ts` 한 줄 변경만 포함하며, 전체 제출 SHA는 운영자에게 전달한다.

## 변경

`frontend/vitest.config.ts`의 기존 `tests/unit/**/*.spec.ts` include를 유지하고 `src/components/news-analysis/*.test.ts`를 추가했다. 이제 기본 프로젝트 설정으로 뉴스 분석 테스트를 찾는다. 제품 코드, 기존 보고서, 계획/브리프, 다른 작업자의 검증 근거는 수정하지 않았다.

## 자체 실행 근거

frontend에서 `npm run test:unit -- src/components/news-analysis/` 실행: **2 files / 11 tests passed**, exit 0. `news-analysis-annotations.test.ts` 6개, `news-analysis.test.ts` 5개가 발견됐다. `/tmp` config를 지정하지 않았다.

`git diff --check` 통과. 제품 동작은 이전 제출과 같으며 전체 재빌드·브라우저·모델 호출은 반복하지 않았다. 기본 명령 재검증 및 제품 동일성의 독립 확인은 별도 tester가 수행한다. 이 보고서는 승인/머지/배포 완료를 뜻하지 않는다.
