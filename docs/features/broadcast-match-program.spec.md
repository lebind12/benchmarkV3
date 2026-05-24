# Broadcast Match Program Spec

상위 요구사항: `docs/features/broadcast-match-program.md`

## 1. 목표

경기 영상 피드를 화면의 중심에 두고, 축구 정보 그래픽을 방송 패키지처럼 배치하는 STREAMER 전용 페이지를 설계한다.

기존 `broadcast-match-overlay` 와의 차이:

| 항목 | 크로마키 오버레이 | 중계화면 포함 페이지 |
|---|---|---|
| 중심 콘텐츠 | 중앙 캐릭터 세이프존 | 경기 영상 피드 |
| 배경 | OBS chroma green `#00B140` | 영상 또는 영상 placeholder |
| 상시 UI | 좌측 포메이션, 상단 스코어, 우측 하단 스탯 | 좌측 큰 중계화면, 좌측 하단 정보 큐브, 우측 크로마키 채팅/캐릭터 슬롯 |
| 큰 그래픽 | 캐릭터 세이프존 침범 금지 | 중계화면 밖의 하단 정보 영역에만 표시 |
| 목적 | 합성용 정보 오버레이 | 중계 프로그램 화면 구성 |

## 2. 설계 원칙

1. 영상 피드가 1순위다.
   - 중계화면 위에는 어떤 웹 UI 도 올리지 않는다.
   - scorebug, lower-third, 이벤트 팝업, 분석 그래픽이 중계화면의 일부라도 가리면 약관 위반 리스크가 있으므로 금지한다.
   - 경기 정보는 중계화면 밖의 좌측 하단 22% 영역에서만 표시한다.

2. 정보는 레이어로 분리한다.
   - Layer 0: video feed
   - Layer 1: bottom info carousel
   - Layer 2: right chroma chat/character reserve
   - Layer 3: analysis takeover, 단 중계화면 밖의 별도 영역에서만 허용

3. 기본 테마는 월드컵 기준이다.
   - World Cup 2026 의 black/white/gold, 한국 강조 red/blue 를 기본 색상 체계로 둔다.
   - 리그별 차별화는 후속 후보로 확장하되, 이번 mock 의 기준은 월드컵이다.

4. 영상 소스는 MVP 에서 mock 이다.
   - 실제 외부 중계 스트림 임베드는 구현 범위 밖이다.
   - mock 에서는 CSS/이미지/비디오 placeholder 로 경기 화면 영역을 표현한다.

## 3. 레이아웃 후보

### P1. Program Frame — 1차 추천

기존 방송용 페이지의 우측 영역 폭과 상하 구성을 유지하고, 우측을 제외한 좌측 전체를 중계 화면과 하단 정보 큐브로 사용한다. 우측 상단은 채팅, 우측 하단은 캐릭터 합성을 위한 크로마키 공간이다.

```text
┌──────────────────────────────────────────────┬──────────────┐
│              VIDEO ONLY AREA                 │    CHROMA    │
│                                              │   RESERVE    │
│                                              │              │
│                VIDEO FEED                    ├──────────────┤
│                                              │    CHROMA    │
├──────────────────────────────────────────────┤    SLOT      │
│      LARGE STAT / EVENT / INFO CAROUSEL      │              │
└──────────────────────────────────────────────┴──────────────┘
```

영역 비율:

| 영역 | 권장 비율 | 설명 |
|---|---:|---|
| left program area | 78% width | 중계화면 + 하단 정보 큐브 |
| right broadcast area | 22% width | 기존 방송용 페이지 우측 영역과 유사 |
| video feed | left area height 78% | 좌측 폭 78% 를 기준으로 16:9 유지 |
| bottom carousel | left area height 22% | 중계화면 16:9 유지 후 남는 하단 공간 |
| right chat slot | right area height 78% | `#00B140` 크로마키 채팅 합성 영역 |
| right character slot | right area height 22% | `#00B140` 크로마키 캐릭터 합성 영역 |

비율 산식:

- 기준 해상도는 `1920x1080`.
- 우측 기존 방송 영역 폭을 `22%` 로 유지하면 좌측 폭은 `78%` 다.
- 좌측 폭 `1920 * 0.78 = 1497.6px`.
- 16:9 중계화면 높이 `1497.6 * 9 / 16 = 842.4px`.
- 전체 높이 대비 `842.4 / 1080 = 78%`.
- 따라서 좌측 중계화면은 `78% width x 78% height`, 하단 잔여 영역은 `22% height` 로 고정한다.
- 우측도 이 수평 기준선에 맞춰 채팅 `78%`, 캐릭터 `22%` 로 나눈다.

장점:
- 경기 화면이 충분히 크다.
- 우측 채팅/캐릭터 방송 공간을 크로마키로 유지한다.
- 주요 정보가 좌측 하단에 크게 표시되어 송출 가독성이 좋다.
- stats/event/player/tactic 을 하나의 큐브 또는 vertical scroller 로 묶기 쉽다.
- 중계화면 위에 웹 UI 를 올리지 않아 약관 위반 리스크를 줄인다.

단점:
- 영상이 16:9 원본일 경우 feed column 내부에서 letterbox/crop 정책 결정이 필요하다.
- 하단 정보 큐브가 커지면 영상 16:9가 깨지므로 `22%` 를 기준값으로 유지한다.

### P2. Full-Bleed Broadcast

영상 피드를 전체 배경처럼 깔고, 중계화면 위에는 어떤 UI 도 올리지 않는다. 현재 요구와는 우측 채팅/캐릭터 크로마키 슬롯이 없어 우선순위가 낮다.

```text
┌───────────────────────────────────────────────┐
│                                               │
│                                               │
│                                               │
│                VIDEO FEED                     │
│                                               │
│                                               │
└───────────────────────────────────────────────┘
```

장점:
- 경기 시청 방해가 가장 적고 약관 리스크가 낮다.
- 방송 중계 피드 감성이 강하다.

단점:
- 포메이션/스탯/이벤트 큐를 상시 보여주기 어렵다.
- 사용자 요청의 리그별 UI/테마 차이를 많이 보여주기 어렵다.

### P3. Studio Analysis Frame

영상은 좌측 또는 중앙에 두고, 하단 분석 그래픽 영역을 더 크게 확보한다. 하프타임/경기 전후 분석에 적합하다.

```text
┌────────────────────────────────┬──────────────┐
│           VIDEO FEED            │ CHAT / CHAR  │
│                                │              │
├────────────────────────────────┴──────────────┤
│              WIDE STATS / TACTICS              │
└────────────────────────────────────────────────┘
```

장점:
- 스탯판/전술판/선수 카드 같은 큰 그래픽을 보여주기 좋다.
- 중계 중이 아닌 프리뷰/하프타임/리뷰 화면으로 강하다.

단점:
- 라이브 경기 시청 면적이 줄어든다.
- 경기 중 상시 화면으로 쓰면 답답할 수 있다.

## 4. 1차 구현 추천

1차는 `P1. Program Frame` 으로 진행한다.

이유:
- 사용자가 기존 방송 그래픽 목업에서 만든 스탯/알림 자산을 하단 정보 영역으로 이어갈 수 있다.
- 우측 상단 채팅, 우측 하단 캐릭터 크로마키 공간을 유지할 수 있다.
- 영상 피드를 크게 유지하면서도 하단에 피드백 가능한 정보 큐브 면적이 충분하다.
- 이후 `layout=full` query 로 P2 를 추가하거나, `mode=analysis` 로 P3 를 확장하기 쉽다.

## 5. P1 화면 구조

```text
main.broadcast-program-stage
├─ section.program-left
│  ├─ div.feed-surface
│  │  └─ video/mock visual
│  └─ section.bottom-info-carousel
│     ├─ stat-card
│     ├─ event-card
│     ├─ player-spotlight
│     └─ tactical-info
└─ aside.program-right
   ├─ chat-slot
   └─ character-slot
```

### 5.1 Feed Surface

- 원본 영상 비율은 16:9 로 유지한다.
- `object-fit: cover` 후보와 `contain + frame` 후보를 mock 에서 비교한다.
- 실제 경기 장면 위에는 상시/일시 UI 를 모두 두지 않는다.
- scorebug, lower-third, event toast, analysis overlay 는 feed surface 내부에 배치하지 않는다.

### 5.2 Score / Event Information

점수, 시간, 이벤트 정보는 중계화면 밖의 `Bottom Info Carousel` 에서 처리한다. 별도의 scorebug 는 만들지 않는다.

### 5.3 Right Broadcast Area

기존 방송용 페이지의 우측 영역과 유사하게 유지한다.

| 모듈 | 내용 | 비율 |
|---|---|---:|
| Chat Slot | 외부 방송 채팅 UI 가 들어갈 크로마키 영역 | 78% height |
| Character Slot | 캐릭터가 들어갈 크로마키 영역 | 22% height |

두 슬롯은 모두 `#00B140` 으로 채운다. 웹 UI, placeholder frame, border, gradient 를 내부에 그리지 않는다.

### 5.4 Bottom Info Carousel

중계 화면 하단의 남은 공간에 주요 스탯/이벤트/보조정보를 하나씩 크게 보여준다.

표현 방식 후보:

| 방식 | 설명 | 추천 |
|---|---|---|
| Cube Flip | 카드 4면을 X/Y 축으로 회전. 스탯/이벤트/선수/전술을 면으로 구분 | 리그별 그래픽 패키지감이 강함 |
| Vertical Scroller | 위/아래로 한 장씩 밀어 올리는 방송 ticker 방식 | 가독성과 구현 안정성이 좋음 |
| Hybrid Flip Strip | 큰 숫자만 flip, 설명은 vertical scroll | 후속 |

1차 구현은 `Vertical Scroller` 를 기본으로 한다. Cube 방식은 후속 후보로 남긴다.

순환 항목:

| 항목 | 예시 |
|---|---|
| Possession | `점유율 61% - 39%` |
| Shots | `전체슈팅 11 - 8`, `유효슈팅 5 - 3` |
| Event | `63:10 선수 교체`, `67:44 경고` |
| Player Spotlight | `흥민 2골 / 평점 8.2` |
| Tactical Info | `왼쪽 하프스페이스 공격 집중`, `최근 10분 점유율 우세` |

순서 규칙:
- 캐러셀은 7초마다 한 장씩 위로 올라가는 vertical infinite carousel 로 동작한다.
- 캐러셀 큐의 0번째 항목을 현재 표시 카드로 간주한다.
- 전환 시 0번째 카드가 위로 사라지고 1번째 카드가 현재 카드가 된다. 전환 종료 후 큐를 왼쪽으로 회전시켜 순환을 계속한다.
- 새 경기 이벤트를 발견하면 현재 큐의 2번째 위치, 즉 index `1` 에 삽입한다.
- 따라서 최신 이벤트는 현재 표시 중인 카드 바로 다음에 등장한다.
- 새 이벤트 삽입 후에도 나머지 큐의 상대 순서는 유지하며, 순환은 끊기지 않는다.

월드컵 하단 캐러셀 1차 채택:
- 월드컵용 배너: W03 Host Cities Map Strip
- 스탯 카드: W01 Trophy Seal Band
- 골 이벤트: W08 Match Ball Orbit
- 현재 최고 평점 플레이어: W04 Gold Medal Plate
- 카드/파울/오프사이드 등 단순 경기 이벤트: W14 Goal Net Mesh 를 변형한 Event Mesh Plate

## 6. 리그별 적용 방향

| 리그 | 기준 | Bottom Carousel |
|---|---|---|
| World Cup 2026 | 기본 채택 | black/white/gold + Korea red/blue ribbon |
| Premier League | 후속 | purple/cyan/magenta |
| Champions League | 후속 | dark blue/light streak |
| Europa League | 후속 | orange/black angled band |
| Carabao Cup | 후속 | red/yellow ticket/stamp |
| FA Cup | 후속 | navy/red/gold plate |

## 7. 데이터 의존성

초기 mock 은 기존 방송 overlay mock data 를 재사용한다. 방송용 live mode 에서는 FE handler 가 API-Football 을 직접 호출한다.

관련 명세: `docs/spec/broadcast-api-football-live-fe.md`

현재 정책:
- FastAPI 백엔드 endpoint 를 사용하지 않는다.
- `/api/v1/...` 경로를 호출하지 않는다.
- `fixture` query 가 있으면 해당 API-Football fixture id 를 사용한다.
- `fixture` query 가 없으면 `/fixtures?live=all` 의 첫 live fixture 를 사용한다.
- polling 기본 주기는 10초다.

새 endpoint 후보는 영상 소스 정책 확정 후 판단한다. 단, 현재 방송용 live 데이터 구현 범위에는 포함하지 않는다:

- `GET /api/v1/broadcast/fixtures/{external_id}/program-config`

`program-config` 가 필요해지는 경우:
- 영상 소스 URL/타입을 서버가 내려줘야 함
- 방송 장면 모드(live, analysis, halftime)를 서버가 관리해야 함
- OBS/제어 패널과 연동해야 함

## 8. 사용자 확인 필요

1. 이 화면에서 실제 영상 피드는 웹페이지 내부 `<video>` 로 재생하는가, 아니면 OBS 에서 영상과 웹 그래픽을 따로 합성하는가?
2. 1차 피드백은 P1/P2/P3 중 어느 방향을 기준으로 볼 것인가?
3. 하단 정보 영역은 vertical scroller 를 1차로 볼 것인가, cube flip 도 동시에 비교할 것인가?
4. 하프타임/경기 전후 분석 화면을 같은 페이지의 `mode=analysis` 로 볼 것인가, 별도 페이지로 둘 것인가?
