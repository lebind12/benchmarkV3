# REL-BUILD 한정 독립 확인

먼저 `/Users/woolee/benchmark/.agents/skills/poteto-mode/SKILL.md` 전문을 직접 읽는다. 읽기 전용 DeepSeek 검토 역할, 실제 모델 deepseek-ai/deepseek-v4.1-flash-1017/max 유지. 하위 워커·새 Run·다른 모델 금지.

사용자 승인된 배포 직전 타입 오류8건과 기존 Vercel 설정을 보완한 4파일만 한 번 확인한다. 기능 전체·과거 검토·전체 회귀를 다시 열지 않는다. 제품·검사·보고서·설정·Plans.md 편집0, 신규 스크립트/검사 작성0이다. 확인 결과는 worker_done 본문으로만 보낸다.

입력: `docs/implementation/match-preview/release-build-brief.md`, 현재 아래 파일, root가 전달한 구현 완료 메시지. 구현자는 EDITING STOPPED·백그라운드0이고 root도 완료 TUI/빈 입력창을 확인했다.

1. `frontend/src/components/management/PreviewPanel.test.ts` sha256 889784073ed8244c05af88c1d67f83cc6351b5de1cb583666ab0f638ea057cd0. available8곳(컴파일 오류6+캐스트 가림2)을 structured 내부에서 행 레벨로 옮겼다. 백엔드 structured_row_from_section_result/SectionResultView의 실제 계약 및 기존 검사 의미와 맞는지만 확인한다. 타입 완화/skip/단언 삭제가 없는지 본다.
2. `frontend/src/features/match-preview/BundleGenerationPanel.test.ts` sha256 ebfd74335e137b2ae84de93468c208cd424b6423b98f726cd46c72ddb0bf679b. 미지원 matcher를 toHaveBeenCalledTimes(1)+toHaveBeenCalledWith로 교체했다. 지정 단위검사 실행 중 관측된 RouterLink 주입 오류를 이 파일의 vi.mock('vue-router')로 해결했다. 생성 호출 횟수·인자와 링크 의미를 보존하는지 확인한다.
3. `frontend/src/lib/api/preview.ts` sha256 16fa082a1fed755bb9205dc3625c97ec819e3ceb8d54e4968d6a38724c93d83f. 미사용 previewRequest import 제거이며 호출 계약이 바뀌지 않았는지 확인한다.
4. `frontend/vercel.json` sha256 5deb4cf4e34a4dad09748b73c035710fe031d9751dd9d53fc01b870c96c61d84. HEAD 바이트 동일, 기존 Koyeb /api 프록시·SPA·Vite/npm run build/dist 복구다. 기존 대상과 일치하는지 확인한다.

검증 근거: 구현자가 지정 `cd frontend && npm run test:unit -- src/components/management/PreviewPanel.test.ts src/features/match-preview/BundleGenerationPanel.test.ts` 최종26/26, `npm run build` exit0을 보고했다. root도 최종 터미널 보고와 파일 SHA를 대조했다. 같은 리비전의 기존 근거를 재사용하고 검사를 재실행하지 않는다. 누락·모순이 보이면 사실과 가장 작은 확인 방법만 보고한다. mutation/원복 실험 금지.

완료 기준: 위4항목 충족·직접 회귀0이면 수용으로 보고한다. 참고 개선은 배포 차단으로 확대하지 않는다. 최종 답에 직접 확인한 경로, 재사용 근거, 남은 차단(없으면없음), EDITING STOPPED·백그라운드0을 적고 한 번 종료한다. root가 커밋·push·배포·운영 실제 홈을 맡는다.
