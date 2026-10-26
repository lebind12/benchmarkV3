# 운영 홈: 마지막 수집 프리뷰와 생성 시각

2026-10-26 사용자 후속 결정. 과거 24시간/최대4회와 API 예측 제외 웹매체3곳 정책을 대체한다. 추천 우선순위 자체와 일반 페이지 DB전용 원칙은 유지한다.

- 대상: 활성 리그·최신2시즌의 추천 우선순위 해당 NS 경기. `0 < kickoff-now <= 6h`. 정기 KST00/06/12/18 수집 성공 후 실행한다. 수집 완료가 킥오프를 넘으면 생성하지 않는다.
- 경기당1회. attempt의 슬롯은 킥오프 직전 정기수집 시작시각으로 고정한다. 정각 킥오프는 이전 슬롯이다. 수동 수집도 같은6시간 창/중복제한을 적용한다. 일정·대진 identity가 달라지면 새 입력으로 생성하고 이전 대진 프리뷰를 노출하지 않는다.
- 실패는 기존 bounded 모델 재시도(단계 최대3회, 전체6회)와 명시적 재개를 사용한다. 일반 조회나 다음 수집이 성공본을 다시 생성하지 않는다. 사이클 상한 이후 후보는 deferred로 기록한다.
- 범용 운영 프롬프트: `docs/features/home-preview-production-prompt.md`. API-Football 사실·배당·자체 예측과 DB 기록·번역·사진 및 전체 저장 스키마를 입력한다. Google 검색과 전체JSON 반환을 한 요청에서 수행한다. 원인 검색은 최종 주요 결장자 팀당최대2명만. JSON/출처 검증 실패 시 최대3회 모델 응답을 요청하며 전체ModelRun 예산도 지킨다.
- 서버는 날짜·원인을 자연어에서 정규식으로 추출/이동하지 않는다. 응답 전체를 검증하고 그대로 저장하며 원문/입력/grounding/확인원문을 비공개snapshot에 보존한다. checkpoint 재개도 원문 이력을 보존한다. Google 근거 URL과 실제 리디렉션 도착 문서를 대조한다. 새 운영 검색의 실제 기사 coverage는 별도 인수 대상이다.
- 전망은 총3개. API-Football `/predictions`는1개로 포함하고 독립 웹매체2곳을 더한다. API 자료가 없으면 웹3곳을 목표로 한다. 중복 매체/API는 중복 계산하지 않는다. 부족하면 있는 자료만 partial/missing으로 저장한다. `web_source_count`는 실제웹수, `total_source_count`는API포함 수다.
- 공개 GET은 DB전용이며 `generation_due_at`을 추가한다. `/`는 추천 경기·프리뷰만 표시한다. 기존 순위·스탯·뉴스·일정 대시보드는 제거한다. 생성 예정 시각은 수집 시작 기준이며 완료 후 공개된다. 생성본이 있으면 실제 생성 시각을 표시한다.
- 출처·자료시점 및 자료부족 상태는 접은 세부정보에서 확인한다. 운영 홈 맨위 경고문은 없다. 경기 상세 이동·주요 결장2x2·선수얼굴/접는 선정이유는 유지한다.

## 구현·검증 범위

메인 전용 `/Users/woolee/benchmark-main`, `feat/home-preview-json`에서만 수정했다. 공용 관리·AX checkout은 수정하지 않았다. 로컬Postgres55441의 무작위 격리schema와 E2E5192를 사용한다. API8017/8018 및 FE5191/5193 기존서버는 재시작하지 않았다.

운영 활성화에는 기존 `HOME_PREVIEW_ENABLED`, 메인 전용 Google project/인증, 검색설정 및 성공 daily-sync 공통 hook이 필요하다. Google project 또는 검색설정이 없으면 호출/attempt소비 전에 not_configured로 종료한다. AX 모델/인증을 복사하지 않는다. 기존 default OFF 유지. 새 물리DB컬럼은 없으며 JSON스키마와 FE/BEvalidator를 동기화했다. 이번 작업은 배포/서비스재시작/운영환경변수변경/운영DB쓰기 허가가 아니다.

검증: BE 단위127개 통과. 격리Postgres 통합30개 통과(기존24+직접JSON checkpoint 재개·6시간 후보2+기존 직접저장4). FE 단위33개와 production build 통과. 원격 API/유료 모델 새 호출은 하지 않았으며 synthetic provider와 로컬DB로 저장·재개를 검증했다. 브라우저의 real-home 테스트도 응답 fixture로 계약과 표시를 검증한다. 기존 실제 모델3연속 성공 증거는 이전 실험 기록에 별도 보존했다.

최종 브라우저 회귀18개 통과: 생성완료 시각/생성전 예정시각(KST)/접는출처/이전dashboard부재/모바일·다크·모션감소·기존프리뷰 표시 포함.

2026-10-26 후속 사용자 승인으로 관리278d152와 로컬 main 통합 및 필요한 운영DB migration 적용을 진행했다. 종전 ‘운영DB 미적용’은 당시 상태다. 현재 적용·검증은 `docs/features/home-preview-merge.verification.md`와 운영DB 검증JSON을 따른다. 배포/원격push/재시작/운영환경변수 변경은 하지 않는다.
