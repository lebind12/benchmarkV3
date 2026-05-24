<script setup lang="ts">
type AlertVariantKind =
  | 'alert-zone'
  | 'full-ribbon'
  | 'player-lower'
  | 'substitution'
  | 'card-plate'
  | 'var-strip'
  | 'stat-alert'
  | 'crest-bubble'
  | 'side-tucked'
  | 'sponsor-event'

type AlertVariant = {
  id: string
  title: string
  source: string
  feedback: string
  next: string
  kind: AlertVariantKind
}

const event = {
  teamCode: 'KOR',
  opponentCode: 'BRA',
  minute: "60'",
  player: '이강인',
  assist: '손흥민',
  score: '2 : 1',
  detail: '박스 오른쪽 컷백 이후 왼발 마무리',
}

const variants: AlertVariant[] = [
  {
    id: 'A1',
    title: 'Bottom-left Alert Zone',
    source: 'Eredivisie alert zone',
    feedback: '중앙 캐릭터를 덜 가린다. 모든 이벤트를 한 시스템으로 통합하기 좋다.',
    next: '기본 이벤트 알림 후보',
    kind: 'alert-zone',
  },
  {
    id: 'A2',
    title: 'Full-width Lower Ribbon',
    source: 'match status lower ribbon',
    feedback: '골/하프타임/풀타임처럼 공식 확정 이벤트에 강하다.',
    next: '큰 이벤트 전용 후보',
    kind: 'full-ribbon',
  },
  {
    id: 'A3',
    title: 'Player Event Lower Third',
    source: 'player stats lower third',
    feedback: '득점자/카드/PK 성공처럼 선수 중심 이벤트에 적합하다.',
    next: 'player spotlight 후보',
    kind: 'player-lower',
  },
  {
    id: 'A4',
    title: 'Split Substitution Bar',
    source: 'substitution lowerthird',
    feedback: 'OUT/IN 정보가 즉시 읽힌다. 교체 이벤트 전용으로 좋다.',
    next: '교체 이벤트 후보',
    kind: 'substitution',
  },
  {
    id: 'A5',
    title: 'Card Plate',
    source: 'booking alert graphic',
    feedback: '정보량이 적은 카드 이벤트를 강한 색면으로 처리한다.',
    next: '옐로/레드카드 후보',
    kind: 'card-plate',
  },
  {
    id: 'A6',
    title: 'VAR Review Strip',
    source: 'VAR decision strip',
    feedback: '체크 중/판정 확정 상태를 한 그래픽에서 다룰 수 있다.',
    next: 'VAR 상태 후보',
    kind: 'var-strip',
  },
  {
    id: 'A7',
    title: 'Match Stat Alert',
    source: 'single-stat lower third',
    feedback: '점유율/슈팅 같은 짧은 스탯을 스탯판과 별도로 순간 노출한다.',
    next: '1개 지표 알림 후보',
    kind: 'stat-alert',
  },
  {
    id: 'A8',
    title: 'Crest Bubble + Ribbon',
    source: 'crest bubble alert',
    feedback: '좌측 원형 로고와 우측 리본이 현재 요구사항과 가장 맞다.',
    next: '현재 event toast 개선 후보',
    kind: 'crest-bubble',
  },
  {
    id: 'A9',
    title: 'Side-tucked Mobile Alert',
    source: 'streaming side alert',
    feedback: '방해가 적다. 존재감은 약하지만 중계화면 위에 얹기 좋다.',
    next: '중계화면 직접 노출 후보',
    kind: 'side-tucked',
  },
  {
    id: 'A10',
    title: 'Sponsor-tagged Event',
    source: 'broadcast package sponsor slot',
    feedback: 'post-MVP 후원 슬롯과 연결 가능하다. MVP에서는 라벨만 둔다.',
    next: '스폰서 확장 후보',
    kind: 'sponsor-event',
  },
]
</script>

<template>
  <main class="alert-lab-page" data-testid="alert-lab-page">
    <header class="lab-header">
      <div>
        <span>Broadcast Alert Lab</span>
        <h1>하단 알림 디자인 후보 10종</h1>
      </div>
      <p>골, 카드, 교체, VAR, 선수 spotlight, 단일 스탯 알림을 가로형 lower-third로 비교합니다.</p>
    </header>

    <section class="variant-list" data-testid="alert-variant-list">
      <article
        v-for="variant in variants"
        :key="variant.id"
        class="variant-row"
        :data-variant="variant.kind"
        data-testid="alert-variant-tile"
      >
        <aside class="variant-meta">
          <strong>{{ variant.id }}. {{ variant.title }}</strong>
          <span>{{ variant.source }}</span>
          <p>{{ variant.feedback }}</p>
          <b>{{ variant.next }}</b>
        </aside>

        <section :class="['alert-prototype', `alert-prototype--${variant.kind}`]">
          <template v-if="variant.kind === 'alert-zone'">
            <div class="zone-tag">{{ event.minute }}</div>
            <div class="zone-main">
              <span>GOAL</span>
              <strong>{{ event.player }}</strong>
              <i>{{ event.detail }}</i>
            </div>
            <div class="zone-score">{{ event.score }}</div>
          </template>

          <template v-else-if="variant.kind === 'full-ribbon'">
            <b>{{ event.teamCode }}</b>
            <strong>GOAL</strong>
            <span>{{ event.player }} · {{ event.minute }}</span>
            <i>{{ event.score }}</i>
          </template>

          <template v-else-if="variant.kind === 'player-lower'">
            <div class="player-portrait">10</div>
            <div class="player-copy">
              <span>GOAL SCORER</span>
              <strong>{{ event.player }}</strong>
              <i>Assist {{ event.assist }}</i>
            </div>
            <b>{{ event.teamCode }}</b>
          </template>

          <template v-else-if="variant.kind === 'substitution'">
            <div class="sub-out"><span>OUT</span><strong>황희찬</strong></div>
            <div class="sub-core">SUBSTITUTION</div>
            <div class="sub-in"><span>IN</span><strong>이재성</strong></div>
          </template>

          <template v-else-if="variant.kind === 'card-plate'">
            <div class="card-icon">YC</div>
            <div>
              <span>YELLOW CARD</span>
              <strong>김민재</strong>
              <i>{{ event.minute }} · {{ event.teamCode }}</i>
            </div>
          </template>

          <template v-else-if="variant.kind === 'var-strip'">
            <span>VAR CHECK</span>
            <strong>PENALTY REVIEW</strong>
            <i>Checking possible handball</i>
            <b>LIVE</b>
          </template>

          <template v-else-if="variant.kind === 'stat-alert'">
            <b>{{ event.teamCode }}</b>
            <div class="stat-copy">
              <span>점유율</span>
              <strong>61% - 39%</strong>
              <i>최근 10분 기준</i>
            </div>
            <b>{{ event.opponentCode }}</b>
          </template>

          <template v-else-if="variant.kind === 'crest-bubble'">
            <div class="bubble">{{ event.teamCode }}</div>
            <div class="bubble-card">
              <header><span>{{ event.minute }}</span><strong>득점</strong></header>
              <p>{{ event.player }} · {{ event.detail }}</p>
            </div>
          </template>

          <template v-else-if="variant.kind === 'side-tucked'">
            <aside>{{ event.teamCode }}</aside>
            <div>
              <strong>GOAL</strong>
              <span>{{ event.player }}</span>
            </div>
          </template>

          <template v-else>
            <div class="sponsor-main">
              <span>GOAL</span>
              <strong>{{ event.player }}</strong>
              <i>{{ event.score }}</i>
            </div>
            <div class="sponsor-slot">PRESENTED BY</div>
          </template>
        </section>
      </article>
    </section>
  </main>
</template>

<style scoped>
*,
*::before,
*::after {
  box-sizing: border-box;
}

.alert-lab-page {
  width: 100vw;
  height: 100vh;
  overflow-y: auto;
  overflow-x: hidden;
  background: #11151F;
  color: #F7F4EC;
  font-family:
    'Avenir Next Condensed',
    'DIN Condensed',
    'Pretendard',
    system-ui,
    sans-serif;
  letter-spacing: 0;
}

.lab-header {
  position: sticky;
  top: 0;
  z-index: 10;
  min-height: 6.1rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 2%;
  padding: 1.1rem 1.5rem 0.9rem;
  background: #191F2D;
  border-bottom: 0.16rem solid #D7B85D;
}

.lab-header span {
  display: block;
  color: #D7B85D;
  font-size: 0.86rem;
  font-weight: 900;
}

.lab-header h1,
.lab-header p {
  margin: 0;
}

.lab-header h1 {
  font-size: 2.1rem;
  line-height: 1;
}

.lab-header p {
  max-width: 48%;
  color: #D8DEEC;
  font-size: 1rem;
  font-weight: 700;
  line-height: 1.35;
  text-align: right;
}

.variant-list {
  display: flex;
  flex-direction: column;
  gap: 0.95rem;
  padding: 0.95rem;
}

.variant-row {
  min-height: 14.3rem;
  display: grid;
  grid-template-columns: 20rem minmax(0, 1fr);
  gap: 0.9rem;
  padding: 0.75rem;
  background: #202838;
  border: 0.1rem solid #3B465D;
  border-radius: 0.65rem;
  box-shadow: 0.22rem 0.22rem 0 #070910;
}

.variant-meta {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 0.45rem;
  padding: 0.75rem;
  background: #121826;
  border: 0.08rem solid #3B465D;
  border-radius: 0.45rem;
}

.variant-meta strong {
  font-size: 1.28rem;
  line-height: 1;
}

.variant-meta span {
  color: #B8C2D6;
  font-size: 0.82rem;
  font-weight: 800;
}

.variant-meta p {
  margin: 0;
  color: #D7DDEA;
  font-size: 0.88rem;
  font-weight: 700;
  line-height: 1.35;
}

.variant-meta b {
  color: #F4D27A;
  font-size: 0.86rem;
}

.alert-prototype {
  min-width: 0;
  min-height: 12.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  color: #FFFFFF;
  background: #07123D;
  border: 0.16rem solid #F4D27A;
  border-radius: 0.55rem;
  box-shadow: 0.22rem 0.22rem 0 #050609;
  font-weight: 950;
}

.alert-prototype--alert-zone {
  justify-content: flex-start;
  gap: 0.5rem;
  padding-left: 5%;
  background: #101727;
  border-color: #F1F4FF;
}

.zone-tag,
.zone-score {
  min-width: 6.5rem;
  min-height: 5.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #C8102E;
  border-radius: 0.9rem 0 0 0.9rem;
  font-size: 1.6rem;
}

.zone-main {
  min-width: 34rem;
  min-height: 5.5rem;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 0.12rem;
  padding: 0 1.2rem;
  background: #010056;
  border-top: 0.1rem solid #F1F4FF;
  border-bottom: 0.1rem solid #F1F4FF;
}

.zone-main span {
  color: #D4AF37;
}

.zone-main strong {
  font-size: 1.7rem;
}

.zone-main i {
  color: #D8DEEC;
  font-size: 0.86rem;
  font-style: normal;
}

.zone-score {
  border-radius: 0 0.9rem 0.9rem 0;
  background: #003478;
}

.alert-prototype--full-ribbon {
  display: grid;
  grid-template-columns: 0.6fr 1fr 1.8fr 0.7fr;
  padding: 3.5rem 7%;
  background: #050505;
  border-color: #D4AF37;
}

.alert-prototype--full-ribbon b,
.alert-prototype--full-ribbon strong,
.alert-prototype--full-ribbon span,
.alert-prototype--full-ribbon i {
  min-height: 5.4rem;
  display: flex;
  align-items: center;
  justify-content: center;
  font-style: normal;
}

.alert-prototype--full-ribbon b { background: #C8102E; }
.alert-prototype--full-ribbon strong { background: #F5F1E8; color: #000000; font-size: 2rem; }
.alert-prototype--full-ribbon span { background: #071866; }
.alert-prototype--full-ribbon i { background: #D4AF37; color: #000000; }

.alert-prototype--player-lower {
  gap: 0.7rem;
  background: #132D5E;
  border-color: #F7F1E3;
}

.player-portrait,
.alert-prototype--player-lower b {
  width: 6.6rem;
  aspect-ratio: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: #F7F1E3;
  color: #132D5E;
  font-size: 2rem;
}

.player-copy {
  min-width: 38rem;
  min-height: 6.4rem;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 0 1.3rem;
  background: #011E41;
  border: 0.12rem solid #D4AF37;
  border-radius: 0.55rem;
}

.player-copy span,
.player-copy i {
  color: #D4AF37;
  font-size: 0.82rem;
  font-style: normal;
}

.player-copy strong {
  font-size: 2.2rem;
}

.alert-prototype--substitution {
  display: grid;
  grid-template-columns: 1fr 0.8fr 1fr;
  padding: 3rem 8%;
  background: #111111;
  border-color: #F5F1E8;
}

.sub-out,
.sub-in,
.sub-core {
  min-height: 6rem;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.sub-out { background: #D71920; }
.sub-in { background: #003478; }
.sub-core { background: #F5F1E8; color: #111111; }
.sub-out span,
.sub-in span { font-size: 0.82rem; }
.sub-out strong,
.sub-in strong { font-size: 1.6rem; }

.alert-prototype--card-plate {
  gap: 1rem;
  background: #1A1A1A;
  border-color: #FFCC00;
}

.card-icon {
  width: 5.2rem;
  height: 7rem;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #FFCC00;
  border-radius: 0.35rem;
  color: #111111;
  font-size: 1.6rem;
}

.alert-prototype--card-plate div:last-child {
  min-width: 32rem;
  min-height: 6.2rem;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 0 1.2rem;
  background: #050505;
  border: 0.1rem solid #FFCC00;
}

.alert-prototype--card-plate span,
.alert-prototype--card-plate i {
  color: #FFCC00;
  font-style: normal;
}

.alert-prototype--card-plate strong {
  font-size: 2rem;
}

.alert-prototype--var-strip {
  gap: 0.5rem;
  background: #050505;
  border-color: #F5F1E8;
}

.alert-prototype--var-strip span,
.alert-prototype--var-strip strong,
.alert-prototype--var-strip i,
.alert-prototype--var-strip b {
  min-height: 5.7rem;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 1.3rem;
  font-style: normal;
}

.alert-prototype--var-strip span { background: #D4AF37; color: #000000; }
.alert-prototype--var-strip strong { min-width: 24rem; background: #111111; border: 0.1rem solid #D4AF37; }
.alert-prototype--var-strip i { min-width: 22rem; background: #202020; color: #D8DEEC; }
.alert-prototype--var-strip b { background: #C8102E; }

.alert-prototype--stat-alert {
  gap: 0.7rem;
  background: #3D195B;
  border-color: #04F5FF;
}

.alert-prototype--stat-alert b {
  width: 5rem;
  height: 5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: #FFFFFF;
  color: #3D195B;
}

.stat-copy {
  min-width: 34rem;
  min-height: 6rem;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 0 1.2rem;
  background: #32105A;
  border: 0.12rem solid #04F5FF;
  border-radius: 999rem;
  text-align: center;
}

.stat-copy span,
.stat-copy i {
  color: #F2D7FF;
  font-style: normal;
}

.stat-copy strong {
  color: #04F5FF;
  font-size: 2.3rem;
}

.alert-prototype--crest-bubble {
  justify-content: flex-start;
  padding-left: 12%;
  background: #071866;
  border-color: #F5F1E8;
}

.bubble {
  width: 7.3rem;
  aspect-ratio: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: #F5F1E8;
  border: 0.28rem solid #D4AF37;
  color: #071866;
  z-index: 2;
}

.bubble-card {
  min-width: 44rem;
  min-height: 6.7rem;
  margin-left: -1.6rem;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 0.16rem solid #F5F1E8;
  border-radius: 0 1rem 1rem 0;
  background: #0B2D92;
}

.bubble-card header {
  flex: 0 0 42%;
  display: flex;
  align-items: center;
  gap: 1rem;
  padding-left: 3rem;
  background: #C8102E;
}

.bubble-card p {
  margin: 0;
  flex: 1;
  display: flex;
  align-items: center;
  padding-left: 3rem;
}

.alert-prototype--side-tucked {
  justify-content: flex-start;
  padding-left: 5%;
  background: #0B1230;
  border-color: #8CB2FF;
}

.alert-prototype--side-tucked aside {
  width: 5.8rem;
  height: 5.8rem;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #315DFF;
  border-radius: 0.7rem 0 0 0.7rem;
}

.alert-prototype--side-tucked div {
  min-width: 18rem;
  height: 5.8rem;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 0 1rem;
  background: #010056;
  border-radius: 0 0.7rem 0.7rem 0;
}

.alert-prototype--side-tucked strong {
  color: #8CB2FF;
  font-size: 1.7rem;
}

.alert-prototype--sponsor-event {
  gap: 0.55rem;
  background: #011E41;
  border-color: #D4AF37;
}

.sponsor-main,
.sponsor-slot {
  min-height: 6rem;
  display: flex;
  align-items: center;
  justify-content: center;
}

.sponsor-main {
  min-width: 38rem;
  gap: 1.2rem;
  background: #132D5E;
  border: 0.12rem solid #F7F1E3;
  border-radius: 0.6rem 0 0 0.6rem;
}

.sponsor-main span {
  color: #D4AF37;
}

.sponsor-main strong {
  font-size: 2rem;
}

.sponsor-main i {
  font-style: normal;
}

.sponsor-slot {
  min-width: 12rem;
  background: #D4AF37;
  color: #011E41;
  border-radius: 0 0.6rem 0.6rem 0;
}
</style>
