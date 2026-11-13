# HP-FIX — 구성본 선택 보존과 직접 검사 보완

작업 전 `/Users/woolee/benchmark/.agents/skills/poteto-mode/SKILL.md` 전문을 읽고 적용한다. 같은 세션에서 읽었고 미변경이면 읽기 기록과 파일 해시 확인으로 재사용한다. 실제 DeepSeek `deepseek-ai/deepseek-v4.1-flash-1017`, 기존 max 유지. 당신은 원 HP-IMPL 구현자이며 편집 종료와 백그라운드0 인계가 확인됐다. 이 작업은 새 검토 지적 수정이며, 실패한 후속 Dispatch의 재전송이나 재구현이 아니다. 이번 새 Task/Dispatch만 사용한다.

읽을 근거: `docs/implementation/match-preview/home-stored-preview-review.md` 지적1·2, 기존 acceptance 및 최신 구현 보고. 전체 배경 재조사 없이 아래 범위만 수행한다.

## 결정과 수정 범위

1. 구성본 선택은 정본이다. 고른 섹션 행이 미승인·본문 없음 등으로 공개 불가여도 같은 워크플로우의 다른 행으로 대체하지 않는다. 해당 섹션을 제외한다. 기존 문서 선택·승인 정책·무쓰기 GET은 유지한다. 설계를 바꿔 대체를 허용하는 방안은 채택하지 않는다.
2. 경기 전환 중 앞 경기의 늦은 응답이 새 경기 제목·본문을 덮지 않는 대표 단위 검사1건을 추가한다. 현재 순번/경기ID 가드가 이를 만족하면 제품 프론트 코드는 고치지 않는다.
3. 구현자가 발견한 기존 `frontend/e2e/home-preview-live.spec.ts`는 옛 `/prematch`를 mock하고 사라진 `.hp-lead` 등에 의존한다. 현재 홈을 검증하도록 기존 파일의 계약과 선택자를 `/document`·저장본문·단일 없음 안내로 갱신한다. 첫 진입·선택 전환·없음/오류·기존 스크롤 컨테이너/좁은폭·방송 권한의 유효한 요구는 유지하고, 제거된 옛 UI 요구는 어떤 사용자 요구로 대체했는지 보고한다. 실패를 숨기는 skip/무조건 성공/검사 삭제는 금지한다. 옛 소스/선수 아코디언처럼 이번 설계에서 제거된 UI의 전용 기대값은 현재 저장본문의 대응 동작으로 교체하거나 명시적 사유를 남긴다. 이 브라우저 검사는 합성 응답임을 이름·보고에 표시하고 실제 승인된 문서의 실화면 성공으로 표현하지 않는다.

파일 소유권은 다음으로 한정한다.

- `app/services/home_preview_document.py`의 구성본 행 선택 함수
- `tests/unit/test_home_preview_document.py`의 위 선택 경계 대표 검사1건
- `frontend/src/components/home-preview/HomeRecommendedSection.test.ts`의 지연 응답 대표 검사1건
- `frontend/e2e/home-preview-live.spec.ts`의 변경 계약에 직접 영향받은 검사
- 기존 `docs/implementation/match-preview/home-stored-preview-report.md`에 이번 결과만 추가

그 외 제품 파일, 공통 본문/CSS, 관리자/인증, 승인/저장, 설정, Plans.md는 편집하지 않는다. e2e 갱신에 제품 결함이 드러나면 임의로 범위를 넓히지 말고 관측과 최소 범위를 보고한다. 참고 지적3~9는 현재 수정에 넣지 않는다. 첫 프레임 실제 깜빡임은 추후 실제 화면에서 판단한다.

01:56 조정 결정: 추가 검토가 지목한 `home-preview-l3.spec.ts`는 `HOME_PREVIEW_L3=1`·별도 격리 DB/8017·옛 준비 경기 세트 전용이다. 현재 지원 경로의 완료 조건으로 확대하지 않고 편집/실행 대상에서 제외한다. 기존 opt-in/skip 조건을 바꾸거나 새 환경을 만들지 않는다. 이번 e2e 소유·실행 파일은 `home-preview-live.spec.ts` 하나 그대로다. 옛 최근5경기표·출처접기·data-gap 전용 UI의 복원은 이번 설계에 추가하지 않는다. 단 DOC-PRESENT의 선수/부상 본문과 사진·팀로고·매체·배당은 기존 MatchPreviewBody의 대응 표시로 계속 확인해야 한다. 옛 컴포넌트 제거를 그 정보 전체의 생략으로 해석하지 않는다.

## 검증과 종료

- backend: `.venv/bin/python -m pytest tests/unit/test_home_preview_document.py -q` 한 번.
- frontend: `npm run test:unit -- src/components/home-preview/HomeRecommendedSection.test.ts` (cwd frontend) 한 번.
- e2e: `npm run test:e2e -- e2e/home-preview-live.spec.ts --project=chromium-mock` (cwd frontend), 이 파일만 실행한다. 기존 localhost:5173 서버를 재사용한다. 기존 설정을 변경하거나 서버를 중단/재시작하지 않는다. 브라우저 바이너리/서버 조건이 없으면 설치·환경 확대 없이 그 사실을 보고한다. 이 한정 합성 e2e 실행은 이번 지시로 허용한다.
- 브라우저 검사는 필요한 API를 합성 응답으로 차단하고, 실제 승인POST·생성·수집·모델·DB쓰기를 하지 않는다. 기존 운영 자료를 변경해 조건을 만들지 않는다.
- 타입검사는 바뀐 TS 검사에서 구체적 타입 문제가 있을 때만 변경 경로를 확인한다. 기존8오류·publication 실패·다른4파일·전체 회귀/빌드·stash 비교를 반복하지 않는다.
- 구성본 공개불가 선택이 다른 본문으로 바뀌지 않고, 늦은 응답에도 선택 경기 본문이 유지되며, 갱신된 기존 e2e가 현재 계약으로 통과하면 종료한다. 같은 문제 두 번 수정/검증 실패 시 원인과 최소 해결 범위를 보고한다.
- 완료 시 변경 파일·각 명령의 개별 결과·실제/합성 구분·적용 원칙·남은 항목과 `EDITING STOPPED`, 백그라운드0을 남긴다. 공통 진행 문서·오케스트레이션 기록 복구·추가 작업은 하지 않는다.
