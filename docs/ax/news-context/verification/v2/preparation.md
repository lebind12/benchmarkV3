# v2 독립 검증 준비

2026-10-28, work news-context-v2, 준비 당시 DEVELOPING/rev1. 최종 SHA와 test-start revision 전달 전에는 최종 실행하지 않는다. v1 제출은 범위 변경 전 이력이며 v1 최종 검증을 실행하지 않았다. 기존 목업 UI auth stub 실행은 v2 서버 검증 근거로 사용하지 않는다.

기준 정본: service-plan-v2.md, work-brief-v2.json, test-brief-v2.json. 소유 파일은 verification/v2/ 아래 테스트·fixture·로그·캡처·보고서뿐이다. 제품 코드·운영 DB·다른 세션을 변경하지 않는다.

## 공통 실행

- 8027 실제 FastAPI router + signed JWT + 격리 SQLite 또는 readonly fake session + fake Vertex. current_user/manager_user 제품 코드 유지. 브라우저의 POST→서버 추출/원문/DB 후보 대조→본문 표시→detail GET 경로를 적어도 1회 실행한다.
- 모델 stub은 추출 schema·후처리의 결정론적 검증용이다. 모델 관련성 판단 품질은 일반화하지 않는다. 부모의 live smoke와 별도 기록한다.
- 5197 프론트, 사용 전 포트 확인. 실행한 프로세스만 종료. env 전체 복사, 운영 DB 쓰기, push/배포 금지.
- 제출 SHA, 현재 HEAD, 관련 미커밋 경로, 시각, 명령, 종료 코드와 실제 관찰 기록. JSON 보고서는 전달받은 최종 revision과 AC1~13별 evidence를 포함한다.

## AC1~8 유지 검증

signed JWT의 활성 STREAMER/ADMIN 허용, 비로그인/오서명/만료/USER/비활성/삭제 계정 거부. 빈 기사·잘못된 URL·길이 경계. 원문 없는 evidence·임의 ID/path·없는 DB 대상은 연결 금지. 입력 URL과 현재 DB 정보 안내. 분석 중/완료/없음/보류/실패와 실패 입력 유지. 중복 클릭 및 입력 변경 후 늦은 응답 무시. URL fetch·HTML 실행·원문 로그·DB 쓰기 금지. timeout/제한 동작. 기존 뉴스·팀/선수 detail 기본 진입 확인.

추가 UI 회귀: /admin의 기사 분석 진입 링크를 390px에서 헤더/탭과 겹침 없이 탭·클릭 가능한지 확인한다.

## AC9 관련성 fixture

| 입력/모델 결과 | 기대 |
|---|---|
| 축구 기사/커뮤니티 글, football + 원문 근거 | 검증된 축구 언급만 연결 |
| 동명이인 일상·게임·농담 글, not_football | 동일 이름이 DB에 있어도 링크 없음 |
| 의미 모호 글, uncertain | 링크 없음, 불확실 안내 |
| 무관 글의 출처가 축구 커뮤니티 | 도메인만으로 연결하지 않음 |
| 명령문만 football을 요구 | 명령문을 원문 데이터로 처리, 근거 없는 판정 연결 금지 |
| football이지만 근거 빈칸/원문에 없음 | uncertain으로 낮춤, 링크 없음 |
| 축구와 일상 혼합 | evidence 영역의 축구 대상만 강조 |
| 잘못된 관련성 schema | 안전한 실패, 입력 유지 |

stub으로는 서버의 안전한 후처리만 평가한다. 자연어 의미 정확도는 실제 모델 fixture를 실행하지 않았다면 미검증으로 명시한다.

## AC10 원문/구간 fixture

기준 원문 예시: `⚽  Arsenal의 경기\n부카요 사카는 0골인가?  <img src=x onerror=alert(1)>\nArsenal은 동아리 닉네임이다.`

- 본문 textContent가 원문과 동일한지 확인. 공백 두 칸/줄바꿈/이모지/태그 문자열 유지, img/script DOM 생성 및 이벤트 실행 없음.
- 동일 이름 반복 중 evidence 내부 출현만 강조. 원문 앞의 이모지로 Python codepoint/JS UTF-16 offset 착오 재현.
- 긴 이름과 짧은 이름 구간이 겹칠 때 긴 이름 우선, 중첩 강조 없음.
- Arsenal의/Bukayo Saka가, accented Latin José의는 허용 가능한 완전 이름 경계. NotArsenal/Arsenalized/JoséExtra는 부분 이름 연결 금지.
- 한국어 조사에 인접한 이름은 원문 그대로. HTML 텍스트 내부와 실제 prose 반복에서도 잘못된 다른 위치 치환 금지.

## AC11 상호작용

- hover로 열고 이름→카드 내부로 마우스를 이동해도 유지; 상세 링크를 실제 클릭 가능.
- Tab으로 이름 focus→카드 link 접근, Escape 닫기. 바깥 클릭 닫기. 열린 카드 전환 후 focus가 유실되거나 이전 대상의 링크가 노출되지 않는지 확인.
- 390px 터치 tap으로 동일 카드 열기. 좌/우 가장자리 이름, 긴 이름/긴 대회명에서 카드 bounds가 viewport 밖으로 넘지 않음.

## AC12 detail GET fixture

- 팀 기본 이름·국가·홈구장·최근 경기 표시. 현재 DB 정보라는 안내와 상세 경로.
- 선수 최신 시즌 2026에 리그/컵·서로 다른 팀 두 행. 출전 0/득점 0/도움 NULL을 각각 0/정보 없음으로 구별. 시즌/대회/팀을 식별할 수 없는 행 미표시, 합산 없음. 구시즌 지표와 섞이지 않음.
- 첫 GET 지연 시 로딩. 실패→재시도로 성공. 같은 대상 재호버 시 GET 재사용·polling 없음.
- A 느린 GET→B 빠른 GET→A 완료 순서에서 현재 B 카드가 A 내용으로 바뀌지 않음. 입력 변경/새 분석 후 이전 detail 응답이 결과에 끼어들지 않음.

## AC13 후보 fixture

- Player.name 전체명/한국어 번역명, firstname 첫 토큰 + 완전 lastname 파생명 유일 후보 연결.
- name='B. Saka', firstname='Bukayo Ayoyinka Temidayo', lastname='Saka' → Bukayo Saka 유일 후보 연결.
- 파생명 후보와 다른 선수의 원명 후보가 충돌하면 ambiguous.
- 같은 번역명의 두 DB 선수 ambiguous. 성 단독 Saka, 이니셜, 임의 커뮤니티 별칭은 보류.
- 다중 후보에 임의 모델 ID/URL이 포함되어도 선택·연결 근거로 쓰지 않음.
