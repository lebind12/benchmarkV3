# HP-REVIEW — 홈 최신 저장 프리뷰 한정 독립 검토

작업 전 `/Users/woolee/benchmark/.agents/skills/poteto-mode/SKILL.md` 전문을 읽고 적용한다. 실제 DeepSeek flash-1017 Max 유지. 당신은 구현자와 다른 세션의 읽기 전용 검토자다. 제품·검사·도구 코드 수정과 추가 워커 생성은 금지한다. 보고서 `docs/implementation/match-preview/home-stored-preview-review.md`만 작성한다.

입력: `docs/superpowers/plans/2026-11-13-home-stored-preview.md`, `2026-11-13-home-stored-preview-acceptance.md`, 연결 설계, `docs/implementation/match-preview/home-stored-preview-report.md`.

구현자 EDITING STOPPED 보고 및 제품 편집 종료 인계가 있다. Orca 자동후속 등록은 timeout/식별자 불일치로 실패했지만 실제 산출물은 저장되어 있다. 조정기록 실패와 제품 판정을 구분하고 Orca 메타데이터를 고치려 하지 않는다.

## 읽을 변경 파일과 수용 기준

- `app/services/home_preview_document.py`, `app/api/v1/home_preview.py`: 해당 외부 경기의 최신 문서 저장시각, 구성본의 정확한 선택 결과(타 실행 포함), 본문 없는 실행 건너뛰기, 실제/승인된 버전만 공개, GET 무쓰기·외부 무호출·공개 화이트리스트.
- `frontend/src/lib/api/homePreviewDocument.ts`, `homePreview.ts`, `frontend/src/components/home-preview/HomeRecommendedSection.vue`, `frontend/src/styles/home-preview.css`: 공개 응답 경계와 기존 MatchPreviewBody 연결, 첫 진입 자동 표시, 경기 전환 stale 응답 방지, 문서 없음/조회중/오류 구분. 없음은 메시지만, 0<남은시간<=6h 미생성 안내, 과거/6h초과 일반 안내. 문서 있음 우선. 섹션별 reveal와 되흐림 방지, 공통 관리자/본문 디자인 보존.
- 직접 검사 `tests/unit/test_home_preview_document.py`, `frontend/tests/unit/home-preview/storedDocument.spec.ts`, `frontend/src/components/home-preview/HomeRecommendedSection.test.ts`. 관련 기존 `MatchPreviewBody.test.ts`, `recommendations.spec.ts`는 실행 근거 대조용이다.

조정자 수용한 구현 선택: 새 `/document` 공개 경로가 홈의 문서 단일 소스다. 기존 `/prematch`와 추천 응답 preview 메타데이터는 남아 있다. 홈 소비자가 옛 preview 메타데이터를 읽지 않는다는 보고가 사실인지 확인한다. 실제 사용자 표시나 현재 필수 계약에 영향이 없으면 이 옛 메타데이터 연결은 참고 후속으로 분리하고 이번 범위를 확대하지 않는다.

조정자 실제 읽기 근거: 기존 로그인 프론트에서 approvals GET 성공, `approved=[]`, 전 workflow active/pinned=null. 현재 실제 저장본이 있어도 기본 공개 후보가 없는 상태다. 이 정책 조건을 구현 오류로 감추거나 승인POST/DB변경으로 우회하지 않는다. 조정자가 실제 홈의 없음·오류·새 경로 응답을 확인하며 문서 있음의 실화면 검증은 승인 조건과 분리해 보고한다.

## 검사 범위와 종료

- 최신 구현 보고의 backend13pass, frontend 직접4파일26pass, vue-tsc 기존8/신규0 근거를 우선 대조한다. 기존 광범위 테스트나 합산47 주장을 완료 근거로 쓰지 않는다.
- 전체 회귀·전체 빌드·stash/복원·새 테스트/재현 코드·새 DB·외부 API·모델·승인POST·브라우저·서버 재시작은 금지한다. root가 실제 화면을 맡는다.
- 구체적 증거 누락/모순이 있으면 해당 직접 검사 한 번만 허용한다. 새 버그 입증에 코드를 작성해야 한다면 직접 작성하지 말고 최소 사례를 조정자에게 보고한다.
- 지적은 현재 요구 위반·재현된 결함·참고 개선으로 구분하고 위치/영향/최소 수정 범위를 적는다. 코드 서식/미래 확장/지원하지 않는 조합을 차단 항목으로 만들지 않는다.
- 독립 검토는 1회. 완료 보고에 실제 모델·스킬 읽기 근거·핵심 판정·재사용/실행 근거·남은 실제 확인을 적는다. 보고서 저장 후 worker_done 한 번으로 종료하고 idle로 돌아간다.
