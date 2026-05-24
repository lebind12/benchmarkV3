# Broadcast Graphics Design Research

작성일: 2026-05-14

상위:
- 도메인/방송 정책: `@AGENTS.md`
- 방송용 화면 요구사항: `@docs/features/broadcast-match-overlay.md`
- 공통 UI 기준: `@docs/spec/ui-standards.md`
- 리그 팔레트: `@docs/spec/league-palette.md`
- 투명도/재질감 트렌드: `@docs/spec/broadcast-transparency-ui-trends-report.md`

본 문서는 축구 방송용 그래픽을 설계할 때 참고할 리서치와 디자인 원칙을 정리한다. 현재 크로마키 기반 스트리밍 오버레이뿐 아니라, 추후 실제 중계화면을 화면에 크게 띄우고 그 위에 방송 그래픽을 얹는 경우에도 사용한다.

외부 레퍼런스는 형태와 원칙을 참고하기 위한 것이다. 특정 방송사/대회 그래픽을 그대로 복제하지 않는다.

---

## 1. 적용 대상

### 1.1 크로마키 방송 오버레이

현재 구현 중인 `/broadcast.html?fixtureId=<id>&league=<slug>` 화면.

- 기준 해상도: 1920x1080
- 배경: OBS 기본 크로마키 녹색 `#00B140`
- 중앙 캐릭터 세이프존 고정
- 우측 상단은 외부 채팅 UI 예약 영역. 웹 UI 배치 금지
- 좌측: 포메이션/라인업
- 상단 중앙: 스코어버그
- 우측 하단: 매치 스탯 보드
- 중앙 하단: 경기 이벤트 팝업 예외 허용
- UI 컴포넌트에는 크로마키 색상 금지. 투명도는 키컬러가 비치지 않는 범위에서 제한적으로 허용

### 1.2 중계화면 직접 노출 모드

추후 실제 경기 중계화면 또는 게임 화면을 크게 띄우고 그 위에 그래픽을 얹는 화면.

- 배경은 크로마키가 아니라 영상 자체
- 그래픽은 경기 장면을 가리지 않는 영역에 배치
- 큰 하단 패널은 이벤트/하프타임/전후반 전환 등 맥락이 있을 때만 사용
- 상시 표시 UI는 작고 강한 정보 위주: 스코어, 시간, 핵심 이벤트, 짧은 스탯
- 전체 스탯/선수 카드/라인업은 일시적 그래픽으로 등장 후 사라지는 방식 권장

---

## 2. 참고 레퍼런스 요약

| 레퍼런스 | 관찰점 | 우리 화면에 적용할 점 |
|---|---|---|
| [Drexel Designs - Eredivisie Broadcast Graphic Concept](https://dumitrelmiron.artstation.com/projects/A9Eg0W) | 스코어버그, 팀시트, 팀 셰이프, 인게임 스탯, 골/카드 알림, 포스트게임 스탯까지 하나의 패키지로 설계. Alert Zone 을 별도 운영 | 이벤트 팝업, 스탯 보드, 포메이션 필드를 같은 그래픽 패키지처럼 통일. 이벤트는 전용 슬롯에서 강하게 등장 후 정리 |
| [OverlayOn Soccer Scoreboard Overlays](https://overlayon.com/en/overlays/scoreboards/soccer/) | 대회별 템플릿, score/time, live standings, match stats, lineups, events, player spotlight 를 모듈로 분리 | 리그별로 색만 바꾸지 말고 헤더 형태/패턴/아이콘 운용까지 분리. 스탯/라인업/이벤트/선수 카드 모듈 체계화 |
| [OnAir live football graphics](https://onair.guudsuite.com/) | 실시간 데이터로 스코어, 경기 스탯, 라인업을 동적 그래픽으로 전환. 대회별 템플릿 강조 | FE mock 이후 BE endpoint + 캐시로 교체하는 현재 워크플로와 맞음. 데이터 위젯은 템플릿과 분리해서 설계 |
| [LIGR Live Sports Graphics](https://dribbble.com/shots/14484612-LIGR-Live-Sports-Graphics) | 어두운 베이스, 고채도 블루/시안 계열 액센트, 스포츠별 애니메이션 흐름 | UCL/월드컵 계열에서 어두운 베이스 + 강한 액센트 사용 가능. 단일색 테마가 되지 않도록 보조색 필요 |
| [Sports Streaming Overlays / Behance](https://www.behance.net/gallery/102507739/Sports-Streaming-Overlays-Broadcast-Graphics?locale=cs_CZ) | 작은 화면에서도 빠르게 읽히는 scorebug/lower third/stat graphic. 골 그래픽은 화면 한쪽에 붙여 방해를 줄임 | 중앙 세이프존을 침범하지 않는 알림 설계. 정보량보다 순간 가독성 우선 |
| [MotionArray Soccer And Sport Graphics](https://motionarray.com/final-cut-pro-templates/soccer-and-sport-graphics-2541624/) | match info, lineup, substitutions, info panels, ball possession, cards, penalties 등 방송 패키지 구성요소 확인 가능 | MVP 이후 패키지 확장 목록으로 사용. 교체/카드/페널티는 별도 이벤트 템플릿 필요 |
| [UEFA EURO 2024 broadcast article](https://www.uefa.com/news-media/news/028e-1b23c33f3782-f5a4f879bfca-1000--behind-the-scenes-what-it-takes-to-broadcast-the-euro/) | 공식 중계는 메인 피드 외에 파트너별 콘텐츠/그래픽/클립 패키지를 제공 | 우리도 기본 화면 하나가 아니라 상황별 그래픽 패키지로 설계해야 함 |
| [Twenty3 / ITV Sport EURO 2024 graphics](https://www.twenty3.sport/itv-sport-turn-to-twenty3-toolbox-for-uefa-euro-2024/) | 라인업, 매치 스탯, 모멘텀 차트, 피치 시각화를 빠르게 브랜드 그래픽으로 생산 | 추후 momentum/pressure timeline 같은 고급 시각화는 별도 모듈로 확장 가능 |
| [StatBroadcast StatGrfx](https://www.statbroadcast.com/statgrfx.php) | Team stat cards, player cards, snapshots 등 카드 기반 스탯 산출 | 우측 스탯 보드와 선수 상세 팝업을 같은 카드 계열로 확장 가능 |
| [Ease Live / ServusTV interactive overlays](https://digitalmediaworld.tv/disrupt/ease-live-and-servustv-upgrade-the-viewing-experience-for-uefa-euro-2024) | 실시간 스탯, 하이라이트, 폴 등 이벤트 기반 인터랙티브 오버레이 | 방송 송출 화면에는 직접 인터랙션을 넣지 않되, 이벤트 기반 그래픽 트리거 개념 참고 |

---

## 3. 핵심 디자인 원칙

### 3.1 방송 그래픽은 패키지로 보여야 한다

스코어버그, 포메이션, 스탯 보드, 이벤트 팝업, 선수 카드가 각각 다른 웹 컴포넌트처럼 보이면 방송 품질이 낮아진다. 각 리그/대회별로 다음 요소를 하나의 그래픽 패키지로 맞춘다.

- 코너 반경
- 헤더 형태
- 로고/국기 프레임
- 강조선 두께
- 숫자 타이포
- 이벤트 팝업 등장 방향
- 카드/라인업/스탯의 색상 계층

### 3.2 색만 바꾸는 리그 테마는 부족하다

리그별 차별화는 최소한 다음 3단계가 필요하다.

| 단계 | 내용 | MVP 적용 |
|---|---|---|
| 색상 | primary/secondary/accent swap | 필수 |
| 형태 | 헤더 컷, 코너, 프레임, 리본/패턴 | 필수 |
| 모션 | 등장 방향, 전환 속도, 이벤트 강조 방식 | 후속 |

### 3.3 상시 UI와 순간 UI를 분리한다

상시 UI는 경기 시청과 캐릭터 세이프존을 방해하지 않아야 한다.

- 상시 UI: 스코어버그, 좌측 포메이션, 우측 하단 스탯 요약
- 순간 UI: 골/카드/교체/VAR/하프타임/선수 상세/전체 스탯
- 순간 UI는 등장 후 사라져야 하며, 중요한 이벤트 흔적은 작게 남기는 방식만 허용

### 3.4 방송 가독성은 웹 가독성과 다르다

송출 화면에서는 작은 텍스트를 읽기 어렵다. 따라서 스탯 보드는 항목을 많이 보여주는 것보다 핵심 지표를 크게 보여주는 편이 낫다.

권장 우선순위:
1. 점유율
2. 슈팅 / 유효슈팅
3. 코너킥
4. 오프사이드
5. 패스 성공률
6. 옐로/레드 카드

### 3.5 투명도는 크로마키 배경 노출 여부로 판단한다

크로마키 방송에서 문제가 되는 것은 컴포넌트 내부로 배경 키컬러(`#00B140`)가 비쳐 들어와 방송 합성에서 같이 빠지는 경우다. 따라서 투명도 자체를 전면 금지하지 않고, 키컬러 노출 여부를 기준으로 판단한다.

금지:
- UI 컴포넌트 내부의 `#00B140` 또는 유사 키컬러
- 컴포넌트 배경이 비어 있어 크로마키 배경이 그대로 보이는 `transparent` 영역
- 카드/패널/텍스트 정보 영역 전체에 적용해 배경 키컬러가 비치는 `opacity`
- 크로마키 배경 위에 직접 얹는 반투명 패널

허용:
- 불투명한 카드/패널/이미지 위에 얹는 `rgba(...)` 광택, 내부 하이라이트, 그림자
- 이미지/아이콘 자체의 알파 채널
- 정보 영역 뒤에 항상 불투명한 컨테이너가 있는 장식용 반투명 레이어

---

## 4. 우측 스탯 보드 디자인 방향

현재 참고 이미지의 장점은 복잡하지 않지만 방송 그래픽처럼 보인다는 점이다. 우측 스탯 보드는 웹 테이블이 아니라 `MATCH STATS` 방송 카드처럼 보여야 한다.

### 4.1 권장 구조

```text
┌──────────────────────────────┐
│ 리그/대회 패턴 헤더           │
│ 홈 로고/국기   MATCH STATS   원정 로고/국기 │
├──────────────┬───────────────┤
│ 홈 팀명       │ 원정 팀명       │
├──────────────────────────────┤
│ 점유율  61%  █████░░  39%     │
├──────────────────────────────┤
│ 11      전체슈팅         8    │
│  5      유효슈팅         3    │
│  4      코너킥           2    │
│ 83%     패스성공률       69%  │
└──────────────────────────────┘
```

### 4.2 세부 원칙

- 상단 헤더는 리그/대회 정체성 표현 영역으로 사용한다.
- 팀명/로고/국기는 카드 상단에서 크게 보여준다.
- 점유율은 대표 지표로 크게 표현한다.
- 모든 항목에 바 차트를 넣지 않는다. 숫자 중심의 2열 비교가 더 빠르게 읽힌다.
- fixture id, 내부 league slug 등 운영 정보는 방송 화면에 노출하지 않는다.
- 카드 하단은 너무 꽉 채우지 않고 숨 쉴 공간을 둔다.

### 4.3 아카이브 후보: World Cup Ribbon Crest

`broadcast-stats-lab.html` 의 `A. Ribbon Crest` 는 FIFA World Cup 2026 스탯판 후보로 아카이브한다.

채택 이유:
- 국기/리본 패턴이 국가대항전 정체성을 즉시 전달한다.
- 사용자가 제공한 유로/국가대항전 카드 레퍼런스와 가장 잘 맞는다.
- 상단에 이미 별도 스코어보드가 있으므로 스탯 카드 내부에서는 점수판 역할을 하지 않아도 된다.
- 월드컵처럼 대회 자체의 시각 정체성이 중요한 화면에서 가장 빠르게 인지된다.

적용 시 수정 원칙:
- 카드 내부의 스코어 숫자는 제거한다.
- 중앙에는 `MATCH STATS`, `WORLD CUP 2026`, 라운드명, 경기 상태 중 하나만 둔다.
- 팀명/국기/국가코드는 유지하되, 상단 스코어보드와 같은 정보를 반복하지 않는다.
- 점유율은 대표 지표로 크게 두고, 나머지는 숫자 중심 2열 비교로 유지한다.
- 크로마키 오버레이에서는 우측 하단 카드 후보로 사용한다.
- 실제 중계화면 직접 노출 모드에서는 하프타임/풀타임/일시적 스탯 그래픽으로 사용한다.

### 4.4 MVP 적용 매핑

2026-05-14 기준 실제 방송 페이지 우측 스탯판은 다음 구조로 매핑한다.

| 리그/대회 | 적용 구조 | 이유 |
|---|---|---|
| Premier League | Possession Dial | EPL 의 강한 보라/민트/핑크 톤과 원형 점유율 그래픽이 잘 맞음 |
| UEFA Champions League | Stat Matrix | 프리미엄/분석형 톤. 네이비/블루 기반의 정돈된 2x2 카드가 적합 |
| UEFA Europa League | Timeline Lanes | 오렌지/블랙 에너지감과 경기 흐름형 레인이 잘 맞음 |
| Carabao Cup | Ticket Stub | 컵대회/이벤트 감성. 티켓형 구조가 다른 대회와 가장 다름 |
| FA Cup | Broadcast Tower | 클래식 컵대회 톤. 네이비/레드/골드 타워형 카드가 적합 |
| FIFA World Cup 2026 | Ribbon Crest | 국가대항전의 국기/리본/대회 정체성이 가장 빠르게 읽힘 |

구현 위치:
- 실제 적용: `frontend/src/components/broadcast/BroadcastStatsBoard.vue`
- 비교 랩: `/broadcast-stats-lab.html`

---

## 5. 선수 카드 / 선수 상세 팝업 방향

사용자가 제공한 선수 상세 예시는 방송용 player spotlight 의 좋은 기준이다.

### 5.1 권장 구조

- 상단: 리그/대회 패턴 헤더
- 중앙 상단: 선수 사진 또는 실루엣
- 정보 띠: 생년/이름/포지션
- 본문: 핵심 스탯 6~8개
- 하단: 닫기/상태 영역은 방송 송출 화면에서는 숨김 또는 컨트롤 화면 전용

### 5.2 방송 화면 적용

- 경기 중 선수 클릭 상세는 송출 화면에 직접 노출하지 않는다.
- 송출 화면에서는 특정 이벤트 발생 시 5~7초짜리 player spotlight 로만 사용한다.
- 선수 사진이 없을 경우 클럽/국가 실루엣 또는 등번호 그래픽으로 대체한다.

---

## 6. 포메이션 필드 / 선수 마커 방향

### 6.1 필드

- 실제 축구장처럼 보이되 너무 사실적인 잔디 질감은 피한다.
- 필수 요소: 스트라이프, 하프라인, 센터서클, 페널티박스, 골에어리어, 코너 아크
- 좌측 패널 크기가 작으므로 선은 굵고 단순해야 한다.
- 필드 내부 정보가 많아질수록 배경 디테일은 낮춰야 한다.

### 6.2 선수 마커

선수 마커는 한눈에 다음 정보를 읽을 수 있어야 한다.

- 등번호
- 축약 한글 이름
- 평점
- 골 여부 및 멀티골
- 옐로카드
- 레드카드
- 교체 여부

원칙:
- 등번호는 중앙 핵심 정보로 유지한다.
- 평점은 어두운 배경 + 흰 글씨로 별도 칩 처리한다.
- 골/카드/교체 아이콘은 배경 박스 없이 마커 주변에 모은다.
- 아이콘은 너무 멀리 퍼뜨리지 않는다. 마커와 한 덩어리로 보여야 한다.
- 이벤트가 있는 선수를 과하게 키우기보다 아이콘 자체의 명확도를 높인다.

### 6.3 두 팀 단일 전술판

일반 포메이션 패널은 한 팀의 선발 배치를 보여주는 데 집중한다. 반면 두 팀 단일 전술판은 두 팀을 하나의 피치에 올려 전술적 관계를 보여주는 분석 그래픽이다.

용도:
- 킥오프 전 양 팀 포메이션 비교
- 주요 매치업 구도 설명
- 압박/수비 블록/하프스페이스 과부하 설명
- 실제 중계화면 위에 잠깐 띄우는 분석 컷

조사 반영:
- TacticBoard 는 한 피치에 두 팀, 등번호, 선수명, 드로잉 도구, 움직임 시퀀스를 지원한다.
- AthletePath soccer tactics board 는 두 팀 선수 배치, 화살표, 압박/공간 하이라이트, 다양한 피치 타입을 전술 설명의 핵심 요소로 둔다.
- Tactico Pro 는 드래그 앤 드롭 선수 배치, 전술 화살표, 100개 이상 포메이션, set-piece, keyframe animation 을 전술판 기능으로 제시한다.
- Tacbo 는 두 팀 표시 토글, 공 아이콘, 선수 이동, 구역 분석, 포지셔닝/패스 거리/공간 평가를 지원한다.

설계 후보:

| 후보 | 구조 | 적합한 사용 |
|---|---|---|
| Mirror Lineups | 홈/원정 포메이션을 상하로 마주 보게 배치 | 킥오프 전 기본 비교 |
| Phase Split Board | 아래는 홈 공격, 위는 원정 블록처럼 국면을 나눔 | 전술 설명 |
| Matchup Channels | 좌/중/우 채널에 직접 대결 라인을 표시 | 주요 매치업 |
| Overload Map | 특정 구역에 `2v1`, `PRESS`, `SPACE` 같은 분석 태그 표시 | 분석 방송 |
| Compact Dual Board | 좌측 패널에도 들어갈 수 있게 압축한 양 팀 보드 | 실제 오버레이 후보 |
| Camera Dual View | 방송 카메라처럼 원근감을 준 단일 전술판 | 중계화면 직접 노출 |

주의점:
- 두 팀 22명을 모두 올리면 작은 좌측 패널에서는 과밀해진다.
- 크로마키 오버레이의 상시 좌측 패널보다는 프리뷰/분석/일시 그래픽에 더 적합하다.
- 실제 상시 오버레이 후보로 쓰려면 선수 이름 없이 등번호/팀색 중심으로 압축해야 한다.
- 듀얼 전술판도 리그 아이덴티티 레이어를 얹을 수 있지만, 우선순위는 전술 관계 가독성이다.

---

## 7. 이벤트 팝업 방향

현재 요구사항을 유지한다.

- 중앙 하단에서 위로 등장
- 7초 후 아래로 내려감
- 좌측 원형 객체에 팀 로고
- 우측 카드 전체 라운딩
- 상단 박스: 이벤트 제목
- 하단 박스: 이벤트 상세

추가 원칙:
- 골/카드/교체/VAR 는 리그별로 완전히 다른 컴포넌트를 두지 않는다.
- 이벤트 타입별 구조를 먼저 고정하고, 그 위에 리그/대회 테마 스킨을 적용한다.
- 이벤트 팝업은 캐릭터 얼굴/상체 주요 영역을 가리지 않아야 한다.
- 사라진 뒤에도 해당 선수 마커의 작은 아이콘으로 이벤트 흔적은 유지한다.

### 7.1 이벤트 타입 구조와 리그 테마 분리

알림/lower-third 는 `이벤트 종류` 와 `리그/대회 테마` 를 분리한다.

분리 이유:
- 골, 카드, 교체, VAR 은 정보 구조가 서로 다르다.
- 같은 골 이벤트라도 Premier League/UCL/FA Cup 에서 색상, 헤더, 코너, 패턴만 달라져야 운영이 단순하다.
- 리그별로 모든 이벤트 컴포넌트를 따로 만들면 유지보수와 QA 조합이 급격히 늘어난다.

이벤트 타입:

| 이벤트 타입 | 고정 구조 | 테마 적용 위치 |
|---|---|---|
| Goal | 좌측 팀 로고 원형 + 상단 `GOAL` + 하단 득점자/상세 + 우측 현재 스코어 | 원형 테두리, 상단 바, 하단 카드, 숫자 색 |
| Card | 카드 아이콘 + 선수명 + 팀명 + 분/사유 | 카드 플레이트 색, 경고/퇴장 강조선, 리그 패턴 |
| Substitution | OUT/IN 2분할 + 중앙 교체 라벨 | 좌우 패널 모양, 중앙 라벨 프레임 |
| VAR | 상태 단계(`CHECK`, `REVIEW`, `DECISION`) + 판정 텍스트 | 상태별 색면, 헤더 형태, 경계선 |
| Player Spotlight | 등번호/사진 슬롯 + 선수명 + 1~3개 스탯 | 선수 슬롯 프레임, 헤더 패턴 |
| Single Stat | 한 지표명 + 양팀 수치/바 | 지표 바 색, 양팀 칩, 배경 패턴 |

리그 테마 스킨:

| 리그/대회 | 알림 스킨 방향 |
|---|---|
| Premier League | 보라/민트/핑크, 굵은 캡슐, 밝은 숫자 |
| UEFA Champions League | 다크 네이비, 얇은 라이트 라인, 프리미엄 크레스트 탭 |
| UEFA Europa League | 블랙/오렌지, 사선 컷, 빠른 슬래시 헤더 |
| Carabao Cup | 레드/옐로우, 티켓/이벤트형 강한 대비 |
| FA Cup | 네이비/레드/골드, 클래식 금색 라인 프레임 |
| FIFA World Cup 2026 | 국기/리본/블랙-화이트-골드, 국가 코드 강조 |

구현 원칙:
- `eventType` 이 구조를 결정한다.
- `leagueTheme` 이 색상, 패턴, 코너, 헤더 형태를 결정한다.
- 같은 `eventType` 컴포넌트가 모든 리그에서 동작해야 한다.
- QA 는 `이벤트 타입 수 x 리그 테마 수` 조합으로 확인한다.

참고:
- LIGR 는 lower-third 를 Custom/Player/Event 로 나누고, Event lower-third 에서 골, 페널티, 카드, 교체 같은 경기 이벤트를 다룬다.
- WASP3D 는 lower-third 를 단순 이름표가 아니라 경기 맥락과 선수를 설명하는 그래픽으로 설명한다.
- Daktronics insert graphics guide 는 lower-third/player/fullscreen lineup 을 템플릿과 데이터 필드로 분리한다.

---

## 8. 리그별 그래픽 방향

구체 색상은 `@docs/spec/league-palette.md` 를 따른다. 이 문서는 형태/무드 기준만 정의한다.

| 리그/대회 | 디자인 방향 |
|---|---|
| Premier League | 보라 기반, 민트/핑크 포인트. 굵고 현대적인 카드, 약간 장난기 있는 곡선. 단, 전체가 보라 덩어리가 되지 않게 밝은 보조선 필요 |
| UEFA Champions League | 다크 네이비/블루 기반. 별/궤도/빛줄기에서 착안한 상단 패턴. 가장 프리미엄하고 차가운 톤 |
| UEFA Europa League | 오렌지/블랙 기반. 사선, 컷아웃, 에너지감. 스탯 보드는 어두운 본문 + 오렌지 헤더 권장 |
| Carabao Cup | 빨강/노랑 기반. 컵대회 특유의 강한 대비. 너무 광고 배너처럼 보이지 않도록 검정/짙은 남색으로 무게감 보정 |
| FA Cup | 네이비/레드/골드 기반. 클래식한 컵대회 톤. 직선적이고 절제된 프레임, 금색 얇은 라인 사용 |
| FIFA World Cup 2026 | 블랙/화이트/골드 기본. 국가 대항전이므로 로고보다 국기/국가 컬러 중심. 한국 경기에서는 태극기 빨강/파랑을 보조 강조 |

---

## 9. 중계화면 직접 노출 모드의 추가 기준

크로마키 오버레이와 다르게 실제 영상 위에 그래픽을 올리는 경우는 경기 장면을 가리는 문제가 가장 크다.

### 9.1 상시 배치

- 상단 좌측 또는 상단 중앙: 작은 scorebug
- 하단 좌우: 짧은 이벤트/lower-third
- 우측 하단: 일시적 스탯 카드
- 중앙: 원칙적으로 비움

### 9.2 등장 타이밍

| 상황 | 권장 그래픽 |
|---|---|
| 평상시 | scorebug 만 유지 |
| 골 | 5~7초 이벤트 팝업 + 득점자 lower-third |
| 카드 | 4~6초 카드 이벤트 팝업 |
| 교체 | 선수 in/out 그래픽, 좌우 분리 |
| 하프타임 | 전체 스탯 보드 |
| 풀타임 | 결과 + 전체 스탯 + 주요 선수 |
| 선수 집중 | player spotlight 카드 |

### 9.3 피해야 할 것

- 경기 중 중앙 대형 스탯 보드 상시 표시
- 하단 전체 폭을 계속 차지하는 패널
- 작은 글씨가 많은 웹 테이블
- 투명 배경에 얇은 흰 글씨
- 영상 위에서 읽히지 않는 저대비 색상

---

## 10. 구현 체크리스트

방송 그래픽 컴포넌트를 만들거나 수정할 때 다음을 확인한다.

- [ ] 1920x1080 기준으로 중앙 세이프존을 침범하지 않는다.
- [ ] 우측 상단 외부 채팅 예약 영역을 침범하지 않는다.
- [ ] UI 내부에 `#00B140` 또는 유사 키컬러를 사용하지 않는다.
- [ ] 반투명 레이어는 반드시 불투명한 카드/패널/이미지 위에서만 사용한다.
- [ ] 크로마키 배경이 비쳐 보이는 `transparent` 영역이나 패널 전체 `opacity` 를 만들지 않는다.
- [ ] 리그별 차이가 색상뿐 아니라 형태/헤더/패턴에서도 드러난다.
- [ ] 숫자와 팀명이 송출 화면에서 즉시 읽힌다.
- [ ] 이벤트 그래픽은 등장/유지/퇴장 상태가 있다.
- [ ] 선수 이벤트 흔적은 선수 마커에 작게 남는다.
- [ ] 실제 중계화면 모드에서는 경기 장면 중앙을 가리지 않는다.
- [ ] fixture id 같은 내부 정보는 방송 화면에 노출하지 않는다.

---

## 11. 다음 디자인 작업 우선순위

1. 우측 스탯 보드를 방송 카드형으로 재설계한다.
2. 리그별 스탯 보드 헤더 패턴을 분리한다.
3. player spotlight 팝업의 기본 구조를 정의한다.
4. 이벤트 팝업 타입을 골/카드/교체/VAR 로 분화한다.
5. 실제 중계화면 직접 노출 모드용 scorebug/lower-third 레이아웃을 별도 설계한다.

---

## 12. 디자인 랩 아카이브

피드백용 후보 페이지:

| 페이지 | 목적 |
|---|---|
| `/broadcast-stats-lab.html` | 우측 스탯판 후보 10종 |
| `/broadcast-scoreboard-lab.html` | 상단/코너 scorebug 후보 10종. 가로형 그래픽 특성상 1열 세로 스크롤 비교 |
| `/broadcast-formation-lab.html` | 선택된 포메이션 후보 7종에 리그 아이덴티티 레이어를 얹는 매트릭스 비교 + 두 팀 단일 전술판 후보 |
| `/broadcast-alert-lab.html` | 하단 알림/lower-third 후보 10종. 가로형 그래픽 특성상 1열 세로 스크롤 비교 |

스코어보드 랩은 scorebug 의 핵심 원칙인 상시 노출, 낮은 화면 점유율, 즉시 점수/시간 인지, 경기 장면 비침범을 기준으로 분리한다.

스코어보드 추가 조사 반영:
- OBScoreboard/KeepTheScore/LIGR: scorebug 는 점수, 시간, 팀, 경기 상태를 작고 지속적으로 보여주는 상시 그래픽이다.
- OverlayOn/Envato/XPression: scorebug, lower-third, starting lineup, event graphics 는 한 방송 패키지 안에서 같은 형태 언어를 공유한다.
- FootyHeadlines/Premier League/World Cup 자료: 리그별 scorebug 는 색뿐 아니라 팀 컬러 리본, 중앙 로고 pod, 이벤트 확장 슬롯을 통해 대회 정체성을 드러낸다.
- 따라서 후보는 `Center Broadcast Bar`, `Compact Corner Bug`, `Capsule Clock`, `Team Color Ribbon`, `World Cup Logo Pod`, `Event Attached`, `VAR/Card Attached` 등으로 분리한다.

2026-05-14 적용 결정:
- FIFA World Cup 2026 스코어보드는 `S6. World Cup Logo Pod` 를 채택한다.
- 국기/국가 영역은 기존 코드 원형보다 크게 두어 국가대항전임을 먼저 읽히게 한다.
- 국기는 CSS 로 직접 그리지 않고 웹에서 받은 flag asset 을 사용한다. 캔뱃지 느낌은 강한 금속 묘사가 아니라 국기 이미지 위의 가벼운 광택/두께감 정도로 제한한다.
- 스탯창의 국가 뱃지는 같은 flag asset 을 원형 뱃지 안에 넣고, 스코어보드보다 조금 더 카드형 뱃지 느낌을 준다.
- 중앙 점수 pod 아래에는 `추가시간` 영역을 둔다. 추가시간이 없을 때도 슬롯을 유지하고 `+0` 으로 표시해 레이아웃이 흔들리지 않게 한다.
- 월드컵 스코어보드는 블랙/화이트/골드 리본과 한국/브라질 국기 색상 블록을 사용한다. 공식 그래픽 복제가 아니라 구조적 참고에 그친다.
- 방송 overlay 공통 레이아웃은 상단 스코어보드를 absolute layer 로 두고, 좌측 포메이션/우측 컬럼이 1920x1080 전체 높이를 사용한다.
- 우측 상단 외부 채팅 예약 영역은 모든 리그에서 우측 컬럼의 50% 수준으로 고정하고, 스탯 보드는 하단 50% 영역에 배치한다.

2026-05-14 리그별 적용 매핑:
- Premier League: 스코어보드 `S3. Capsule Clock`, 스탯판 `D. Possession Dial`, 포메이션 `F4. Half-Space Map + Top Ribbon`. 필드는 Premier League 보라/핑크/시안 테마로 조정한다.
- UEFA Champions League: 스코어보드 `S1. Center Broadcast Bar`, 스탯판 `J. Broadcast Tower`, 포메이션 `F3. Zone Grid + Side Rail`.
- UEFA Europa League: 스코어보드 `S8. Extra Time Expanded`, 스탯판 `G. Lower Third Stack`, 포메이션 `F3. Zone Grid + Side Rail`. 오렌지/골드/블랙 테마를 전체 컴포넌트에 일관 적용한다.
- Carabao Cup: 컵대회 티켓 감성을 유지하기 위해 스탯판 `F. Ticket Stub` 계열을 유지한다.
- FA Cup: 컵대회/결승 톤을 살리기 위해 스탯판 `J. Broadcast Tower` 계열을 FA Cup 테마 색상으로 유지한다.
- 알림창은 리그 단위 고정 디자인이 아니라 이벤트 성격별 후보를 사용한다. 득점=`A8. Crest Bubble + Ribbon`, 교체=`A4. Split Substitution Bar`, 카드=`A5. Card Plate`, VAR=`A6. VAR Review Strip`, 단일 스탯=`A7. Match Stat Alert` 로 매핑하고, 모든 타입에 현재 리그 테마 색상을 적용한다.
- 목업에서는 알림 이벤트를 순환 표시한다. 8.4초 주기로 다음 이벤트 타입으로 넘어가며, 각 이벤트가 등장/유지/퇴장 애니메이션을 가진다.

포메이션 랩은 이름 리스트형 후보를 제외하고, 선택된 포메이션 구조 7개를 고정한 뒤 리그 아이덴티티 레이어를 어떻게 얹을지 비교한다. 목적은 “새 후보 10개”가 아니라 “같은 포메이션 구조에 어떤 방송 그래픽 부품을 얹으면 리그/대회가 읽히는가”를 판단하는 것이다.

추가 조사 반영:
- WASP3D line-up graphic: 라이브 매치용 포메이션 그래픽은 선수/포메이션을 명확히 보여주는 피치 기반 구조가 핵심이다.
- Tactico / DrawTactics / TacticSlate / FC Tactix: 전술 보드는 full/half/attacking third pitch, zones, arrows, pressing triggers, 2D/3D views, animation/timeline 개념을 제공한다.
- Chyron Formation Tool: 포메이션 도구는 전술 인사이트를 전달하기 위해 피치 배경과 카운터를 사용하고, 여러 preset 을 저장/호출하는 방식이다.
- Coach Paint Pro: 포메이션/전술 도구는 팀 로고, 팀 컬러, 배지, 2D/3D 그래픽을 통합해 팀 정체성을 반영한다.
- Football Lineup Builder/RenderFoot: 포메이션 그래픽은 kit color, pitch pattern, badge/logo, arrows/cards/goals 같은 부품을 조합한다.
- 따라서 후보 대체 시 단순 이름 리스트가 아니라 `Zone Grid`, `Half-Space Map`, `Stadium Perspective` 같은 필드 기반 구조를 우선한다.

2026-05-14 선택 반영:
- 유지: `Classic Pitch`, `Tactical Board`, `Zone Grid`, `Half-Space Map`, `Radar Rings`, `Stadium Perspective`, `Compact Pitch`
- 제거: `Press Map`, `Run Arrows`, `Set Piece Board`
- 보강 방향 변경: 비어 있는 3개 후보를 별도 포메이션으로 채우는 방식은 브레인스토밍에 부적합하다. 대신 선택된 7개 후보 각각에 `Top Ribbon`, `Crest Tab`, `Side Rail`, `Corner Motif`, `Tournament Plate`, `Pattern Band` 같은 아이덴티티 레이어를 얹는 매트릭스로 비교한다.
- FIFA World Cup 2026 포메이션은 `F8. Radar Rings` 에 `Pattern Band` 레이어를 결합한 구조를 먼저 적용한다. 실제 방송 화면에서는 피치 배경을 레이더 링 계열로 바꾸고 카드 상단에 월드컵 패턴밴드를 둔다. 선수 뱃지 컴포넌트 자체는 별도 요청 전까지 건드리지 않는다.

아이덴티티 레이어 후보:

| 레이어 | 설명 | 잘 맞는 포메이션 |
|---|---|---|
| Top Ribbon | 피치 상단에 리그/대회 리본과 라벨을 얇게 배치 | Classic, Compact |
| Crest Tab | 좌우 또는 상단 모서리에 팀/대회 크레스트 탭 배치 | Tactical Board, Crest-heavy themes |
| Side Rail | 좌우 세로 레일에 리그 색/대회 패턴 배치 | Zone Grid, Half-Space |
| Corner Motif | 피치 네 모서리에 컵/별/국기 패턴의 짧은 장식 | Classic, Radar |
| Tournament Plate | 상단 헤더를 대회 플레이트처럼 굵게 구성 | Stadium Perspective, Tactical |
| Pattern Band | 피치 안팎에 리그 패턴 띠를 반복 배치 | World Cup, Cup competitions |

매트릭스 판단 기준:
- 포메이션 자체의 가독성을 해치지 않는가
- 리그/대회가 색만으로가 아니라 형태로도 읽히는가
- 좌측 패널의 작은 크기에서도 구분되는가
- 실제 방송 화면에 적용했을 때 중앙 캐릭터 세이프존을 침범하지 않는가

알림/lower-third 조사 반영:
- LIGR/XPression/StageCG: lower-third 는 선수 정보, 이벤트, 스탯, match status 를 빠르게 호출하는 일시 그래픽이다.
- WASP3D/MotionArray: 교체/카드/골/라인업 같은 축구 이벤트별 전용 그래픽이 따로 존재한다.
- BanyanBoard: player stats lower-third 는 선수 사진/번호/이름/스탯을 하단 가로 영역에 노출한다.
- 따라서 알림은 `Goal`, `Card`, `Substitution`, `VAR`, `Player Spotlight`, `Single Stat` 의 이벤트 구조를 먼저 정의하고, 리그별로 색/프레임/헤더/패턴 스킨을 바꾼다.
