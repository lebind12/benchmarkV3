# BI-03 한정 수정 — 독립 검토 B-1 / D-1 / D-2

DeepSeek 구현 세션만 사용, 실제 deepseek-ai/deepseek-v4.1-flash-1017 / Max 유지. 기존 C는 실제 idle·EDITING STOPPED 확인됐고 아래 frontend 경계의 소유권을 당신에게 넘긴다. 다른 워커는 backend만 편집한다. 하위워커/모델변경 금지.

입력: docs/implementation/match-preview/bi-integration-review.md 의 B-1, D-1, D-2 및 해당 수정 확인 항목만. 다른 기능·새 디자인·기존 전체 검토를 시작하지 않는다. 사용자 목표는 원래 /admin의 프리뷰 탭에서 실제 생성·저장된 본문을 확인하는 것이다. 품질 판정/성공률/새 자동 생성 게이트를 만들지 않는다.

소유 파일:

- frontend/src/features/match-preview/SectionRegenerationPanel.vue, CompositionPanel.vue 및 각각 기존 테스트
- frontend/src/lib/api/preview.ts, previewView.ts
- frontend/src/components/management/PreviewPanel.vue 및 기존 PreviewPanel.test.ts
- 해당 요청/응답 타입이 꼭 필요한 기존 frontend 타입 파일

수정 요구:

1. B-1: 재생성 및 마지막 AI 버튼은 실제 생성 의도이므로 요청 mode를 명시한다. 현재 누락으로 서버 mock 기본값에 들어가 reuse는422, refresh는 모의 본문이 저장된다. 서버 기본값을 바꾸거나 mock UI 자체를 삭제하지 않는다. 기존 test의 mode undefined 단언은 실제 사용자 의도에 맞춰 바로잡는다. POST는 사용자의 클릭 때만 한 번이며 GET/새로고침은 모델호출0.
2. D-1: /section-results 실패를 자료 없음으로 위장하지 않는다. API 조회 실패 사유를 보존해 화면에서 조회 오류로 표시하고, 다른 읽힌 본문은 계속 보여준다. 실제 빈 목록과 실패를 구분. 새 진단 엔진·재생성 자동호출 없음.
3. D-2: 구성본이 고른 다른 run의 섹션이 현재 run의 /section-results에 없더라도 reader가 준 선택 본문·근거를 표시한다. 기존 reader 선택을 우선하고 같은 섹션의 임의 최신 버전/다른 경기 결과로 대체하지 않는다. 기존 구조 자료가 없으면 독자 본문 블록으로 표시하며 정보·선수·배당을 추정해 채우지 않는다. backend API/저장 schema는 편집하지 않는다.

현재 디자인(전망/근거/점수, 팀별 선수/부상, 매체+배당 패널), nullable 이미지·실패 fallback, 강조의 strong/text-only, 모듈 선택·기존 본문 보존은 그대로 유지한다. B 이미지 필드는 현재 backend에 실제 존재하므로 "없다"는 옛 보고를 현재 상태로 간주하지 않는다.

검증: 위 세 동작의 기존 테스트에 필요한 대표 사례만 추가/수정. 영향 패널/어댑터 직접 검사와 type-check 각1회. 테스트 수나 mutation/커버리지 목표 없음. 전체 frontend suite·빌드·신규검증script·HTTP·DB·실모델·서버전환0. backend/out/Plans/비밀파일 변경0, commit/stage0.

완료: 변경 파일·실제 요청 필드와 선택 본문 표시 근거·검사 결과·남은 제한 보고1회 + EDITING STOPPED. 완료 등록이 거부되면 status1회로 인계하고 재전송/메일 탐색 루프 금지.
