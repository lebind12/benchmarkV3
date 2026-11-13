# REL-BUILD — 배포를 막는 프론트 타입·라우팅 보완

먼저 `/Users/woolee/benchmark/.agents/skills/poteto-mode/SKILL.md` 전문을 읽고 적용한다. 필요한 TypeScript 원칙만 추가로 읽는다. DeepSeek 구현 역할이며 실제 `deepseek-ai/deepseek-v4.1-flash-1017`·사용자 max 설정을 확인하고 유지한다. 하위 워커·새 조정 Run·다른 모델로 전환하지 않는다.

사용자는 완료된 기능의 커밋·푸시·배포와 운영 홈의 추천 경기/프리뷰 표시를 요청했다. root는 로컬 실제 홈에 맨시티–풀럼 추천, 기존 프리뷰 안내, 승인 저장본문 5섹션이 표시됨을 확인했다. root가 npm run build를 실행했으나 아래 8개 TypeScript 오류로 exit2였다. 이 관측된 배포 차단만 최소 수정한다.

## 소유 파일과 요구

- `frontend/src/components/management/PreviewPanel.test.ts`: 522/771/784/838/870/933행의 SectionStructuredProjection 객체에 실제 타입에 없는 available 필드(6건). 실제 계약과 테스트 의미를 확인해 fixture를 맞춘다. 타입을 느슨하게 하거나 any/무시/검사 제외로 우회하지 않는다.
- `frontend/src/features/match-preview/BundleGenerationPanel.test.ts`: 57행의 현재 Vitest가 지원하지 않는 toHaveBeenCalledExactlyOnceWith. 동일한 횟수+인자 의미를 지원되는 단언으로 유지한다.
- `frontend/src/lib/api/preview.ts`: 16행 previewRequest 선언이 미사용(TS6133). 실제 호출 경로와 보존해야 할 API 계약을 확인해 최소 정리한다.
- `frontend/vercel.json`: HEAD의 기존 운영 API 프록시와 Vite/build/dist 설정이 로컬 통합 과정에서 제거된 상태다. 현재 Vercel 프로젝트 benchmark-v3는 framework Other/root .이고 기존 운영 문서의 VITE_BACKEND_URL은 `/`다. `git show HEAD:frontend/vercel.json`의 확인된 기존 운영 설정을 복구해 `/api/:path*`는 `https://benchmark-v3-lebind12-19f488ae.koyeb.app/api/:path*`, 나머지는 기존 SPA로 유지한다. 로컬 Vite 프록시·홈 렌더·본문·모델·백엔드 코드는 바꾸지 않는다.

## 검증·제외

수정 후 `cd frontend && npm run test:unit -- src/components/management/PreviewPanel.test.ts src/features/match-preview/BundleGenerationPanel.test.ts` 한 번과 `npm run build` 한 번을 실행한다. 빌드가 직접 연결된 누락을 드러내면 원인/최소 수정 범위를 보고하고 무관한 파일로 확대하지 않는다. 새 검사·스크립트·제품 변이 실험·전체 회귀·e2e·브라우저·DB·API·모델·수집·실배포·커밋·push는 하지 않는다.

저장소에는 예전 기획 정리에서 발생한 421개 삭제와 로컬 생성물이 있으므로 일괄복원/스테이징/삭제하지 않는다. 배정 4파일 외 수정 금지이며 필요한 범위 확대는 root에게 보고한다. 제품·프리뷰 내용·승인 정책 변경을 테스트 수리로 숨기지 않는다. 검사가 통과하면 즉시 종료하고 변경 경로/의미, 정확한 명령과 결과, 파일 SHA256, EDITING STOPPED·백그라운드0을 보고한다. 별도 DeepSeek가 수정한 4파일의 한정 독립 확인을 맡는다. Plans.md는 root만 관리한다.
