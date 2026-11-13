# 관리자 프리뷰 사용자 피드백 수정 계획

작성: GPT 조정자. 사용자 직접 수정 요청에 따른 기존 BI-02/03 표시 및 데이터 연결 보완이다. 구현·검토는 AGENTS.md에 따라 실제 DeepSeek 세션만 사용한다.

## 목표와 근거

현재 관리자 저장본 `6c2ce4c2-68c5-4d9b-8863-ac068e063c58`(fixture1557474, live, succeeded)을 원래 확정 디자인에 맞게 표시한다. 사용자 지적은 부상·결장 영문/사진 부재, 배당 부재, 하단 주목 선수와 AI 경기 전망 중복이다. 관련 정본은 `docs/superpowers/specs/2026-11-12-benchmark-preview-integration.md`와 `docs/implementation/match-preview/home-preview-mock-report.md` v4/v5다.

실제 조회 근거: 부상 Marc Guéhi/Antoine Semenyo/Tom Cairney의 player_id·external_player_id·photo_url 및 team_id가 모두 null이다. 본문에는 한글 표기가 있으므로 읽기 표시 단계의 이름/ID 연결을 추적한다. 배당 section_odds는 available=false, odds=[], 공개 표에서 정규시간1X2 확인 불가로 저장됐다. 화면만 고쳐 실제 배당을 만들어낼 수 없다. MatchPreviewBody에는 카드 이후 section_players/section_ai_forecast 본문을 추가하는 경로가 있다.

## 설계·공통 제한

- 21:32 사용자 추가 확정: 6시간이 지났어도 조회 당시 해당 경기의 최신 실제 배당을 표시한다. 같은 업체에 여러 갱신본이 있으면 가장 최근 것을 선택하고 원본 갱신 시각을 보존한다. 기존 6시간 제외 기준을 현재 수용 기준으로 적용하지 않는다. 관리자 배당 섹션만 1회 실행하여 새 preview_dev 결과로 검증하며, 전체 모델 생성·과거 실행 덮어쓰기·자동 승인 없이 처리한다. 서버 재기동과 이 섹션 실행은 root가 인계 후 수행한다.
- 기존 LangGraph와 저장 결과/reader 계약을 재사용한다. API 출력에서 이름·사진을 같은 경기 범위의 기존 선수 자료 및 검증된 한글 이름으로 연결한다. 문자열을 선수 ID로 추정하거나 이번 세 선수만 하드코딩하지 않는다. 실제 매칭 불가는 사진 없음으로 남긴다.
- 본문은 AI 전망·근거/스코어 → 주목 선수 → 부상·결장 → 매체/배당 순서를 유지한다. 각각 한 번 표시하고 의미 있는 잔여 문장은 해당 섹션 안에 둔다. 원문/버전/진단/재생성 기능은 접힌 관리자 영역에 보존한다.
- 배당은 외부 사이트 실제 1X2 우선, API-Football `/odds`로 서로 다른 북메이커를 보완해 최대3행이라는 기존 기획과 대조한다. `/predictions`와 합성 목업값은 사용하지 않는다. 실제 자료 없음을 연결 성공이나 실제 배당 표시로 보고하지 않는다.
- 기존 계정·경기·저장 결과 변경/삭제, 새 모델 호출, 전체 생성, 자동 수집, 마이그레이션, 서버 제어, 배포 금지. 실제 provider 읽기는 현재 경기1건의 기존 자격 설정을 통한 제한된 확인만 허용하며 키/비밀값을 출력하지 않는다. GET 본문 조회에 외부 배당 호출을 끼워 넣지 않는다.
- 원래 DB 설정과 public 무변경을 보존한다. 합성 단위 검사는 로컬에서만 실행한다. 전체 suite·범용 환경 조합·품질 평가 확장·커밋 금지. 기존 diff와 삭제 상태 보존. Plans.md는 root만 수정한다.

## 병렬 작업과 수용 기준

| ID | 소유권 | 수용 기준 | 검증 |
|---|---|---|---|
| PF-B | backend: app/preview/section_preview.py, section_structured.py, display_names.py, localized_names.py, modules/bundle_sections.py, 기존 sources/retrieval/discovery의 필요한 연결 및 대응 tests/preview 파일. frontend 편집 금지 | 부상 표시의 검증된 한글명/외부 선수ID/사진 연결. 배당 누락 위치와 실제 공급 여부를 분리하고 기존 기획의 실제 배당 경로 연결. 기존 저장본 읽기는 원문 변경 없이 개선. 필요한 API 추가 필드는 nullable로 조정자에게 전달 | 변경된 이름/사진 투영 및 배당 추출·fallback의 대표 동작만 기존 해당 pytest 파일에서 선택 실행. DB 테스트면 local 대상 검증 선행. 현재 경기의 실제 자료 가용성 보고 |
| PF-F | frontend/src/lib/api/previewView.ts, frontend/src/components/home-preview/MatchPreviewBody.vue, frontend/src/components/management/PreviewPanel.vue 및 관련 frontend 테스트만 | 주목 선수와 AI 전망 제목/본문이 각각 한 번 표시. 기존 유의미 본문·근거·이미지·배당 표 소비 보존. 배당 자료 미제공 원인은 관리자에서 식별 가능. 원래 디자인 유지 | PreviewPanel 및 영향 있는 MatchPreview/view 테스트만 vitest로 실행, npm run type-check. 현재 저장본 대표 입력으로 중복 부재 검증 |
| PF-R | 별도 DeepSeek 읽기 전용, PF-B/F 변경만 | 요구사항 위반/현재 범위 결함/참고 개선 구분. 원문·운영 데이터 무변경, 식별자 안전성, 본문 유실/중복, 실제 배당과 결측 구분 | 단위별1회 한정 검토. 재실행은 증거 부족 또는 지적 수정 경로만 |
| PF-UI | GPT 조정자 | 원래5173 관리자 동일 run에서 한글명·실제 사진·중복 제거와 배당 실제 가용성 확인 | 워커 편집 종료 인계 후 필요한 backend만 기존 런처로 재기동. GET·실제 화면 확인. 새 생성0 |

PF-B와 PF-F는 독립 파일로 병렬 실행한다. 계약 변경은 root를 통해 전달한다. 구현자는 수정 파일/검사 명령·실제 결과/미해결·편집 종료를 보고한다. 배당이 현재 자료에서 실제로 제공되지 않으면 그 증거와 최소 다음 단계(필요 시 관리자 전용 배당 섹션 실행)를 root에 보고하고 임의 전체 재생성을 하지 않는다. 결과 의미 변경은 버전 보존과 사용자 확인 대상이며 표시 수정만으로 워크플로우 승인 기록을 바꾸지 않는다.

완료 조건은 현재 피드백의 원인 수정·한정 검토·실제 화면 확인이다. 자료 없는 배당이나 식별 불가능한 사진을 성공으로 표시하지 않는다. 시간대 표시 수정과 홈/수집 후속 연결은 이번 범위 밖이다.
