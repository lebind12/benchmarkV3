<script setup lang="ts">
import brazilFlagUrl from '@/assets/broadcast/flags/br.svg?url'
import koreaFlagUrl from '@/assets/broadcast/flags/kr.svg?url'

type ScoreVariantKind =
  | 'center-bar'
  | 'compact-corner'
  | 'capsule'
  | 'team-ribbon'
  | 'split-wings'
  | 'worldcup-pod'
  | 'flag-banner'
  | 'extra-time'
  | 'event-attached'
  | 'var-card-attached'

type ScoreVariant = {
  id: string
  title: string
  source: string
  feedback: string
  next: string
  kind: ScoreVariantKind
}

const match = {
  home: '대한민국',
  away: '브라질',
  homeCode: 'KOR',
  awayCode: 'BRA',
  score: '1 : 1',
  clock: '60:22',
  status: 'LIVE',
}

const variants: ScoreVariant[] = [
  {
    id: 'S1',
    title: 'Center Broadcast Bar',
    source: 'UEFA/UCL 상단 중앙바',
    feedback: '가장 안정적인 상시 스코어보드. 캐릭터 세이프존과 충돌이 적다.',
    next: '기본 방송 페이지 후보',
    kind: 'center-bar',
  },
  {
    id: 'S2',
    title: 'Compact Corner Bug',
    source: 'scorebug 기본 원칙',
    feedback: '실제 중계화면 위에 얹기 가장 좋다. 공간 점유율이 낮다.',
    next: '중계화면 직접 노출 모드 후보',
    kind: 'compact-corner',
  },
  {
    id: 'S3',
    title: 'Capsule Clock',
    source: 'OBS/stream scorebug 템플릿',
    feedback: '한 줄 안에서 시간, 팀, 점수가 빠르게 읽힌다. EPL 톤과 잘 맞는다.',
    next: 'Premier League 후보',
    kind: 'capsule',
  },
  {
    id: 'S4',
    title: 'Team Color Ribbon',
    source: '리그별 팀 컬러 리본',
    feedback: '팀/리그 컬러가 강하게 들어와 식별이 빠르다.',
    next: '리그 테마 적용 후보',
    kind: 'team-ribbon',
  },
  {
    id: 'S5',
    title: 'Split Wings',
    source: '국가대항전 대결형 바',
    feedback: '좌우 대결 구도가 가장 명확하다. 점수 중심성이 좋다.',
    next: '월드컵/유로 후보',
    kind: 'split-wings',
  },
  {
    id: 'S6',
    title: 'World Cup Logo Pod',
    source: '월드컵 중앙 로고형 구조',
    feedback: '대회 정체성을 강하게 전달한다. 공식 디자인 복제 없이 구조만 참고한다.',
    next: 'World Cup 2026 후보',
    kind: 'worldcup-pod',
  },
  {
    id: 'S7',
    title: 'Flag Banner',
    source: '국가전 국기 배너',
    feedback: '국가 코드와 컬러가 즉시 보인다. 클럽 경기에는 과할 수 있다.',
    next: '월드컵 후보로 아카이브',
    kind: 'flag-banner',
  },
  {
    id: 'S8',
    title: 'Extra Time Expanded',
    source: '추가시간 확장형 scorebug',
    feedback: '45+3, 90+5 같은 축구 고유 상태를 명확히 보여준다.',
    next: '추가시간/연장 상태 후보',
    kind: 'extra-time',
  },
  {
    id: 'S9',
    title: 'Event Attached',
    source: 'scorebug + 이벤트 확장 슬롯',
    feedback: '골/카드/교체를 scorebug 옆에 붙여 순간 정보로 처리한다.',
    next: '이벤트 toast와 연결 후보',
    kind: 'event-attached',
  },
  {
    id: 'S10',
    title: 'VAR/Card Attached',
    source: '상태 배지 확장형 scorebug',
    feedback: 'VAR CHECK, 카드, 페널티 같은 상태를 본체와 분리해 과밀을 줄인다.',
    next: 'VAR/카드 상황 후보',
    kind: 'var-card-attached',
  },
]

function flagForCode(code: string) {
  return code === 'BRA' ? brazilFlagUrl : koreaFlagUrl
}
</script>

<template>
  <main class="score-lab-page" data-testid="scoreboard-lab-page">
    <header class="lab-header">
      <div>
        <span>Broadcast Scoreboard Lab</span>
        <h1>스코어보드 디자인 후보 10종</h1>
      </div>
      <p>가로형 scorebug 특성에 맞춰 후보 하나가 한 줄을 크게 쓰고, 세로 스크롤로 비교합니다.</p>
    </header>

    <section class="variant-list" data-testid="scoreboard-variant-list">
      <article
        v-for="variant in variants"
        :key="variant.id"
        class="variant-row"
        :data-variant="variant.kind"
        data-testid="scoreboard-variant-tile"
      >
        <aside class="variant-meta">
          <strong>{{ variant.id }}. {{ variant.title }}</strong>
          <span>{{ variant.source }}</span>
          <p>{{ variant.feedback }}</p>
          <b>{{ variant.next }}</b>
        </aside>

        <section :class="['score-prototype', `score-prototype--${variant.kind}`]">
          <template v-if="variant.kind === 'center-bar'">
            <div class="center-team">
              <span class="crest">{{ match.homeCode }}</span>
              <strong>{{ match.home }}</strong>
            </div>
            <div class="center-score">
              <span>{{ match.status }}</span>
              <strong>{{ match.score }}</strong>
              <i>{{ match.clock }}</i>
            </div>
            <div class="center-team center-away">
              <strong>{{ match.away }}</strong>
              <span class="crest">{{ match.awayCode }}</span>
            </div>
          </template>

          <template v-else-if="variant.kind === 'compact-corner'">
            <div class="corner-bug">
              <header>{{ match.status }}</header>
              <p><b>{{ match.homeCode }}</b><strong>1</strong></p>
              <p><b>{{ match.awayCode }}</b><strong>1</strong></p>
              <footer>{{ match.clock }}</footer>
            </div>
          </template>

          <template v-else-if="variant.kind === 'capsule'">
            <div class="capsule-score">
              <span>{{ match.clock }}</span>
              <b>{{ match.homeCode }}</b>
              <strong>{{ match.score }}</strong>
              <b>{{ match.awayCode }}</b>
              <i>{{ match.status }}</i>
            </div>
          </template>

          <template v-else-if="variant.kind === 'team-ribbon'">
            <div class="ribbon-team ribbon-home">
              <span>HOME</span>
              <strong>{{ match.home }}</strong>
            </div>
            <div class="ribbon-core">
              <i>{{ match.clock }}</i>
              <strong>{{ match.score }}</strong>
              <span>GROUP B</span>
            </div>
            <div class="ribbon-team ribbon-away">
              <span>AWAY</span>
              <strong>{{ match.away }}</strong>
            </div>
          </template>

          <template v-else-if="variant.kind === 'split-wings'">
            <div class="wing wing-home">{{ match.homeCode }}</div>
            <div class="wing-score">
              <strong>{{ match.score }}</strong>
              <span>{{ match.clock }}</span>
            </div>
            <div class="wing wing-away">{{ match.awayCode }}</div>
          </template>

          <template v-else-if="variant.kind === 'worldcup-pod'">
            <div class="cup-strips"><span></span><span></span><span></span><span></span><span></span></div>
            <div class="cup-board" data-testid="s6-worldcup-scoreboard">
              <div class="cup-team cup-team-home">
                <span class="cup-flag" :aria-label="match.homeCode">
                  <img :src="flagForCode(match.homeCode)" alt="" />
                </span>
              </div>
              <div class="cup-core">
                <span>WORLD CUP 2026</span>
                <strong>{{ match.score }}</strong>
                <i>{{ match.clock }}</i>
              </div>
              <div class="cup-team cup-team-away">
                <span class="cup-flag" :aria-label="match.awayCode">
                  <img :src="flagForCode(match.awayCode)" alt="" />
                </span>
              </div>
              <div class="cup-added-time">
                <span>ADDED TIME</span>
                <strong>+0</strong>
              </div>
            </div>
          </template>

          <template v-else-if="variant.kind === 'flag-banner'">
            <div class="flag-block flag-home"><i></i>{{ match.homeCode }}</div>
            <strong>{{ match.score }}</strong>
            <div class="flag-block flag-away"><i></i>{{ match.awayCode }}</div>
            <span>{{ match.clock }}</span>
          </template>

          <template v-else-if="variant.kind === 'extra-time'">
            <div class="extra-main">
              <b>{{ match.homeCode }}</b>
              <strong>{{ match.score }}</strong>
              <b>{{ match.awayCode }}</b>
            </div>
            <div class="extra-clock">
              <span>90:00</span>
              <strong>+5</strong>
            </div>
            <i>ADDED TIME</i>
          </template>

          <template v-else-if="variant.kind === 'event-attached'">
            <div class="attached-score">
              <b>{{ match.homeCode }}</b>
              <strong>{{ match.score }}</strong>
              <b>{{ match.awayCode }}</b>
              <span>{{ match.clock }}</span>
            </div>
            <div class="attached-event">
              <i>GOAL</i>
              <strong>이강인</strong>
              <span>60'</span>
            </div>
          </template>

          <template v-else>
            <div class="var-score">
              <b>{{ match.homeCode }}</b>
              <strong>{{ match.score }}</strong>
              <b>{{ match.awayCode }}</b>
            </div>
            <div class="var-state">
              <span>VAR CHECK</span>
              <strong>PENALTY REVIEW</strong>
            </div>
            <div class="card-stack">
              <i>YC</i>
              <i>RC</i>
            </div>
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

.score-lab-page {
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
  min-height: 13.4rem;
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

.score-prototype {
  min-width: 0;
  min-height: 11.8rem;
  position: relative;
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

.score-prototype--center-bar {
  align-items: stretch;
  padding: 3.25rem 7%;
  background: #0B1230;
}

.center-team,
.center-score {
  display: flex;
  align-items: center;
  justify-content: center;
}

.center-team {
  flex: 1;
  gap: 1rem;
  background: #010056;
  border: 0.1rem solid #F1F4FF;
  font-size: 1.55rem;
}

.center-away {
  text-align: right;
}

.crest {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 3.7rem;
  aspect-ratio: 1;
  border-radius: 50%;
  background: #F1F4FF;
  color: #010056;
}

.center-score {
  flex: 0 0 28%;
  flex-direction: column;
  background: #315DFF;
  border-top: 0.1rem solid #F1F4FF;
  border-bottom: 0.1rem solid #F1F4FF;
}

.center-score strong {
  font-size: 3.1rem;
  line-height: 1;
}

.center-score span,
.center-score i {
  color: #E8EEFF;
  font-size: 0.82rem;
  font-style: normal;
}

.score-prototype--compact-corner {
  justify-content: flex-start;
  padding-left: 7%;
  background: #111111;
  border-color: #D4AF37;
}

.corner-bug {
  width: 18rem;
  height: 9.4rem;
  display: flex;
  flex-direction: column;
  border: 0.14rem solid #D4AF37;
  border-radius: 0.5rem;
  background: #050505;
}

.corner-bug header,
.corner-bug footer {
  flex: 0 0 22%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #D4AF37;
}

.corner-bug p {
  flex: 1;
  margin: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 1rem;
  border-top: 0.08rem solid #3B3422;
}

.corner-bug strong {
  font-size: 1.7rem;
}

.score-prototype--capsule {
  background: #200D35;
  border-color: #04F5FF;
}

.capsule-score {
  width: 78%;
  min-height: 5.8rem;
  display: grid;
  grid-template-columns: 1fr 0.85fr 1.3fr 0.85fr 0.8fr;
  align-items: center;
  justify-items: center;
  background: #3D195B;
  border: 0.16rem solid #04F5FF;
  border-radius: 999rem;
  box-shadow: 0.3rem 0.3rem 0 #000000;
}

.capsule-score b {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 4.2rem;
  height: 3rem;
  border-radius: 999rem;
  background: #FFFFFF;
  color: #3D195B;
}

.capsule-score strong {
  color: #04F5FF;
  font-size: 3rem;
}

.capsule-score i,
.capsule-score span {
  color: #F2D7FF;
  font-style: normal;
}

.score-prototype--team-ribbon {
  display: grid;
  grid-template-columns: 1fr 0.45fr 1fr;
  padding: 3rem 6%;
  background: #121826;
  border-color: #04F5FF;
}

.ribbon-team,
.ribbon-core {
  height: 5.8rem;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.32rem;
}

.ribbon-home {
  background: #C8102E;
}

.ribbon-away {
  background: #003478;
}

.ribbon-team span,
.ribbon-core span,
.ribbon-core i {
  font-size: 0.76rem;
  font-style: normal;
}

.ribbon-team strong {
  font-size: 1.55rem;
}

.ribbon-core {
  background: #F5F1E8;
  color: #111111;
}

.ribbon-core strong {
  font-size: 2.6rem;
}

.score-prototype--split-wings {
  display: grid;
  grid-template-columns: 1fr 0.42fr 1fr;
  padding: 3rem 7%;
  background: #000000;
  border-color: #F5F1E8;
}

.wing,
.wing-score {
  height: 5.9rem;
  display: flex;
  align-items: center;
  justify-content: center;
}

.wing {
  font-size: 2rem;
}

.wing-home {
  background: #C8102E;
}

.wing-away {
  background: #003478;
}

.wing-score {
  flex-direction: column;
  background: #F5F1E8;
  color: #000000;
}

.wing-score strong {
  font-size: 2.7rem;
}

.wing-score span {
  color: #C8102E;
}

.score-prototype--worldcup-pod {
  flex-direction: column;
  background: #071866;
  border-color: #F5F1E8;
}

.cup-strips {
  width: 76%;
  height: 1rem;
  display: flex;
}

.cup-strips span {
  flex: 1;
}

.cup-strips span:nth-child(1) { background: #C8102E; }
.cup-strips span:nth-child(2) { background: #D4AF37; }
.cup-strips span:nth-child(3) { background: #000000; }
.cup-strips span:nth-child(4) { background: #F5F1E8; }
.cup-strips span:nth-child(5) { background: #003478; }

.cup-board {
  width: 76%;
  min-height: 8.4rem;
  display: grid;
  grid-template-columns: 1.3fr 1.08fr 1.3fr;
  grid-template-rows: 5.9rem 2.1rem;
  align-items: center;
  justify-items: center;
  background: #0B2D92;
  border: 0.12rem solid #F5F1E8;
}

.cup-team {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.9rem;
  background: #071866;
}

.cup-team b {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 4rem;
  aspect-ratio: 1;
  border-radius: 50%;
  background: #F5F1E8;
  border: 0.14rem solid #D4AF37;
  color: #071866;
}

.cup-team-home {
  grid-column: 1;
  grid-row: 1 / 3;
}

.cup-team-away {
  grid-column: 3;
  grid-row: 1 / 3;
}

.cup-flag {
  position: relative;
  width: 7.3rem;
  height: 3.75rem;
  display: block;
  overflow: hidden;
  background: #F5F1E8;
  border: 0.14rem solid #D4AF37;
  box-shadow: 0.18rem 0.18rem 0 #000000;
}

.cup-flag img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.cup-flag::after {
  position: absolute;
  left: 12%;
  top: 12%;
  width: 46%;
  height: 16%;
  display: block;
  background: rgba(255, 255, 255, 0.42);
  border-radius: 999rem;
  content: '';
  transform: rotate(-18deg);
}

.cup-core {
  grid-column: 2;
  grid-row: 1;
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: #F5F1E8;
  color: #000000;
}

.cup-core span,
.cup-core i {
  color: #C8102E;
  font-size: 0.78rem;
  font-style: normal;
}

.cup-core strong {
  color: #000000;
  font-size: 3rem;
}

.cup-added-time {
  grid-column: 2;
  grid-row: 2;
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  background: #D4AF37;
  border-top: 0.12rem solid #000000;
  color: #000000;
}

.cup-added-time span {
  font-size: 0.7rem;
}

.cup-added-time strong {
  font-size: 1.65rem;
}

.score-prototype--flag-banner {
  display: grid;
  grid-template-columns: 1fr 0.34fr 1fr 0.48fr;
  padding: 3.2rem 8%;
  background: #000000;
  border-color: #F5F1E8;
}

.flag-block,
.score-prototype--flag-banner strong,
.score-prototype--flag-banner span {
  min-height: 5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.7rem;
}

.flag-block i {
  display: block;
  width: 3.5rem;
  height: 2.15rem;
  border: 0.08rem solid #F5F1E8;
}

.flag-home i { background: #C8102E; }
.flag-away i { background: #003478; }

.score-prototype--flag-banner strong {
  background: #F5F1E8;
  color: #000000;
  font-size: 2.2rem;
}

.score-prototype--flag-banner span {
  color: #D4AF37;
}

.score-prototype--extra-time {
  gap: 0.8rem;
  background: #23160A;
  border-color: #FFB000;
}

.extra-main,
.extra-clock,
.score-prototype--extra-time i {
  min-height: 4.8rem;
  display: flex;
  align-items: center;
  justify-content: center;
}

.extra-main {
  min-width: 34rem;
  gap: 1.25rem;
  background: #120904;
  border: 0.12rem solid #FFB000;
  border-radius: 0.45rem;
}

.extra-main strong {
  color: #FFB000;
  font-size: 2.6rem;
}

.extra-clock {
  flex-direction: column;
  min-width: 8rem;
  background: #FF6A00;
  border-radius: 0.45rem;
}

.extra-clock strong {
  font-size: 2rem;
}

.score-prototype--extra-time i {
  min-width: 11rem;
  color: #FFB000;
  font-style: normal;
}

.score-prototype--event-attached {
  gap: 0.55rem;
  background: #101727;
  border-color: #F1F4FF;
}

.attached-score,
.attached-event {
  min-height: 5.4rem;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.95rem;
  border: 0.1rem solid #F1F4FF;
}

.attached-score {
  min-width: 34rem;
  background: #010056;
}

.attached-score strong {
  color: #8CB2FF;
  font-size: 2.6rem;
}

.attached-score span {
  color: #D8DEEC;
}

.attached-event {
  min-width: 22rem;
  background: #C8102E;
  border-radius: 0 0.9rem 0.9rem 0;
}

.attached-event i {
  padding: 0.45rem 0.7rem;
  background: #F5F1E8;
  border-radius: 999rem;
  color: #C8102E;
  font-style: normal;
}

.score-prototype--var-card-attached {
  gap: 0.55rem;
  background: #111111;
  border-color: #D4AF37;
}

.var-score,
.var-state,
.card-stack {
  min-height: 5.3rem;
  display: flex;
  align-items: center;
  justify-content: center;
}

.var-score {
  min-width: 26rem;
  gap: 1rem;
  background: #050505;
  border: 0.1rem solid #F5F1E8;
}

.var-score strong {
  color: #D4AF37;
  font-size: 2.4rem;
}

.var-state {
  min-width: 25rem;
  flex-direction: column;
  background: #D4AF37;
  color: #000000;
}

.var-state span {
  font-size: 0.82rem;
}

.card-stack {
  gap: 0.35rem;
}

.card-stack i {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 3.1rem;
  height: 4.2rem;
  background: #FFCC00;
  color: #111111;
  font-style: normal;
  border-radius: 0.25rem;
}

.card-stack i:last-child {
  background: #D71920;
  color: #FFFFFF;
}
</style>
