<script setup lang="ts">
type StatItem = {
  label: string
  home: string
  away: string
  homePct: number
  awayPct: number
}

type VariantKind =
  | 'ribbon'
  | 'split'
  | 'rail'
  | 'dial'
  | 'timeline'
  | 'ticket'
  | 'lower'
  | 'matrix'
  | 'monolith'
  | 'tower'

type Variant = {
  id: string
  title: string
  source: string
  feedback: string
  next: string
  kind: VariantKind
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

const stats: StatItem[] = [
  { label: '점유율', home: '61%', away: '39%', homePct: 61, awayPct: 39 },
  { label: '전체슈팅', home: '11', away: '8', homePct: 58, awayPct: 42 },
  { label: '유효슈팅', home: '5', away: '3', homePct: 62, awayPct: 38 },
  { label: '코너킥', home: '4', away: '2', homePct: 66, awayPct: 34 },
  { label: '패스성공률', home: '83%', away: '76%', homePct: 52, awayPct: 48 },
]

const possession = stats[0]
const secondaryStats = stats.slice(1)
const compactStats = secondaryStats.slice(0, 3)
const matrixStats = stats.slice(0, 4)

const variants: Variant[] = [
  {
    id: 'A',
    title: 'Ribbon Crest',
    source: '유로/국가대항전 카드',
    feedback: '월드컵 후보로 아카이브. 국기/리본 정체성이 가장 빠르게 읽힌다.',
    next: '상단 점수판과 중복되는 스코어 표기는 제거하고 스탯 전용으로 사용',
    kind: 'ribbon',
  },
  {
    id: 'B',
    title: 'Split Pill',
    source: '스코어버그 확장형',
    feedback: '좌우 대결 구도가 강하다. 세로 공간을 덜 쓰지만 항목이 많으면 밀도가 높다.',
    next: '하프타임/풀타임보다 경기 중 소형 요약에 적합',
    kind: 'split',
  },
  {
    id: 'C',
    title: 'Side Rail Index',
    source: '방송사 데이터 패널',
    feedback: '팀 정체성을 세로 레일로 고정해 안정적이다. 우측 하단 카드에 잘 맞는다.',
    next: '현재 스탯판의 가장 현실적인 대체안',
    kind: 'rail',
  },
  {
    id: 'D',
    title: 'Possession Dial',
    source: '인터랙티브 스포츠 그래픽',
    feedback: '점유율이 즉시 보인다. 숫자보다 도형이 먼저 읽혀 방송성이 좋다.',
    next: '점유율 중심 경기에는 좋지만 슈팅 우세 표현은 보완 필요',
    kind: 'dial',
  },
  {
    id: 'E',
    title: 'Timeline Lanes',
    source: '모멘텀/경기 흐름 그래픽',
    feedback: '통계가 경기 흐름처럼 보인다. 일반 스탯판과 구조가 가장 다르다.',
    next: '향후 momentum 데이터와 결합하면 가치가 커짐',
    kind: 'timeline',
  },
  {
    id: 'F',
    title: 'Ticket Stub',
    source: '컵대회/매치데이 티켓',
    feedback: 'FA Cup/Carabao 같은 컵대회 감성이 좋다. 진지한 UCL에는 덜 맞는다.',
    next: '컵대회 테마 전용 후보',
    kind: 'ticket',
  },
  {
    id: 'G',
    title: 'Lower Third Stack',
    source: '중계화면 직접 노출용',
    feedback: '영상 위에 잠깐 띄우기 좋다. 우측 고정 카드보다는 이벤트성 스탯에 적합하다.',
    next: '중계화면 크게 띄우는 모드의 하단 그래픽 후보',
    kind: 'lower',
  },
  {
    id: 'H',
    title: 'Stat Matrix',
    source: '프리미엄 분석 카드',
    feedback: '수치 비교가 가장 명확하다. 웹 대시보드 느낌이 생기지 않게 타이포가 중요하다.',
    next: '선수 상세/하프타임 보드와도 호환 가능',
    kind: 'matrix',
  },
  {
    id: 'I',
    title: 'Gold Monolith',
    source: '월드컵/파이널 프리미엄',
    feedback: '가장 절제되고 고급스럽다. 정보량은 적지만 결승/월드컵 톤에 강하다.',
    next: 'World Cup 2026 전용 고급 테마 후보',
    kind: 'monolith',
  },
  {
    id: 'J',
    title: 'Broadcast Tower',
    source: '선수 카드 + 스탯 타워',
    feedback: '첨부 선수카드와 가장 가깝다. 카드 하나로 팀/스탯을 모두 담기 좋다.',
    next: '현재 참고 이미지의 방향을 유지할 경우 1순위',
    kind: 'tower',
  },
]

function widthStyle(value: number) {
  return { width: `${value}%` }
}

function awayOffsetStyle(value: number) {
  return { marginLeft: `${100 - value}%`, width: `${value}%` }
}
</script>

<template>
  <main class="stats-lab-page" data-testid="stats-lab-page">
    <header class="lab-header">
      <div>
        <span class="lab-kicker">Broadcast Stats Board Lab</span>
        <h1>스탯판 디자인 후보 10종</h1>
      </div>
      <p>
        현재 방송 오버레이와 추후 중계화면 직접 노출 모드에서 쓸 수 있도록 구조가 겹치지 않게 분리한 비교용 목업입니다.
      </p>
    </header>

    <section class="variant-grid" data-testid="stats-variant-grid">
      <article
        v-for="variant in variants"
        :key="variant.id"
        class="variant-tile"
        :data-variant="variant.kind"
        data-testid="stats-variant-tile"
      >
        <div class="variant-meta">
          <strong>{{ variant.id }}. {{ variant.title }}</strong>
          <span>{{ variant.source }}</span>
        </div>

        <section :class="['stats-prototype', `stats-prototype--${variant.kind}`]">
          <template v-if="variant.kind === 'ribbon'">
            <div class="ribbon-strips" aria-hidden="true">
              <span></span><span></span><span></span><span></span><span></span>
            </div>
            <div class="ribbon-crest-row">
              <b>{{ match.homeCode }}</b>
              <span>MATCH STATS</span>
              <b>{{ match.awayCode }}</b>
            </div>
            <div class="ribbon-team-row">
              <strong>{{ match.home }}</strong>
              <i>WORLD CUP 2026</i>
              <strong>{{ match.away }}</strong>
            </div>
            <div class="ribbon-possession">
              <strong>{{ possession.home }}</strong>
              <div class="split-meter">
                <span class="home-meter" :style="widthStyle(possession.homePct)"></span>
                <span class="away-meter" :style="widthStyle(possession.awayPct)"></span>
              </div>
              <strong>{{ possession.away }}</strong>
            </div>
            <div class="ribbon-stat-list">
              <p v-for="stat in secondaryStats" :key="stat.label">
                <b>{{ stat.home }}</b>
                <span>{{ stat.label }}</span>
                <b>{{ stat.away }}</b>
              </p>
            </div>
          </template>

          <template v-else-if="variant.kind === 'split'">
            <header class="split-header">
              <span>{{ match.clock }}</span>
              <strong>{{ match.status }}</strong>
            </header>
            <div class="split-body">
              <div class="split-team split-home">
                <b>{{ match.homeCode }}</b>
                <strong>{{ match.home }}</strong>
                <span v-for="stat in compactStats" :key="stat.label">{{ stat.home }}</span>
              </div>
              <div class="split-spine">
                <i>{{ match.score }}</i>
                <span v-for="stat in compactStats" :key="stat.label">{{ stat.label }}</span>
              </div>
              <div class="split-team split-away">
                <b>{{ match.awayCode }}</b>
                <strong>{{ match.away }}</strong>
                <span v-for="stat in compactStats" :key="stat.label">{{ stat.away }}</span>
              </div>
            </div>
            <div class="split-footer">
              <span>{{ possession.home }} 점유</span>
              <span>{{ possession.away }} 점유</span>
            </div>
          </template>

          <template v-else-if="variant.kind === 'rail'">
            <aside class="rail-team rail-home">
              <b>{{ match.homeCode }}</b>
              <strong>{{ match.home }}</strong>
            </aside>
            <div class="rail-stats">
              <header>
                <span>{{ match.clock }}</span>
                <b>TEAM COMPARISON</b>
              </header>
              <p v-for="stat in stats" :key="stat.label">
                <strong>{{ stat.home }}</strong>
                <span>{{ stat.label }}</span>
                <strong>{{ stat.away }}</strong>
              </p>
            </div>
            <aside class="rail-team rail-away">
              <b>{{ match.awayCode }}</b>
              <strong>{{ match.away }}</strong>
            </aside>
          </template>

          <template v-else-if="variant.kind === 'dial'">
            <header class="dial-header">
              <b>{{ match.homeCode }}</b>
              <span>{{ match.clock }}</span>
              <b>{{ match.awayCode }}</b>
            </header>
            <div class="dial-core">
              <div class="dial-ring">
                <strong>{{ possession.home }}</strong>
                <span>점유율</span>
                <strong>{{ possession.away }}</strong>
              </div>
            </div>
            <div class="dial-stat-cloud">
              <p v-for="stat in secondaryStats" :key="stat.label">
                <span>{{ stat.label }}</span>
                <b>{{ stat.home }} / {{ stat.away }}</b>
              </p>
            </div>
          </template>

          <template v-else-if="variant.kind === 'timeline'">
            <header class="timeline-header">
              <strong>{{ match.clock }}</strong>
              <span>{{ match.homeCode }} {{ match.score }} {{ match.awayCode }}</span>
            </header>
            <div class="timeline-lanes">
              <div v-for="stat in stats" :key="stat.label" class="timeline-row">
                <b>{{ stat.home }}</b>
                <div>
                  <span class="timeline-label">{{ stat.label }}</span>
                  <i class="timeline-home" :style="widthStyle(stat.homePct)"></i>
                  <i class="timeline-away" :style="awayOffsetStyle(stat.awayPct)"></i>
                </div>
                <b>{{ stat.away }}</b>
              </div>
            </div>
          </template>

          <template v-else-if="variant.kind === 'ticket'">
            <div class="ticket-stub">
              <span>LIVE</span>
              <b>{{ match.clock }}</b>
            </div>
            <div class="ticket-main">
              <header>
                <b>{{ match.homeCode }}</b>
                <strong>{{ match.score }}</strong>
                <b>{{ match.awayCode }}</b>
              </header>
              <div class="ticket-teams">
                <span>{{ match.home }}</span>
                <span>{{ match.away }}</span>
              </div>
              <div class="ticket-stats">
                <p v-for="stat in stats" :key="stat.label">
                  <b>{{ stat.home }}</b>
                  <span>{{ stat.label }}</span>
                  <b>{{ stat.away }}</b>
                </p>
              </div>
            </div>
          </template>

          <template v-else-if="variant.kind === 'lower'">
            <header class="lower-score">
              <b>{{ match.homeCode }}</b>
              <strong>{{ match.score }}</strong>
              <b>{{ match.awayCode }}</b>
              <span>{{ match.clock }}</span>
            </header>
            <div class="lower-stack">
              <div v-for="stat in compactStats" :key="stat.label" class="lower-band">
                <strong>{{ stat.home }}</strong>
                <span>{{ stat.label }}</span>
                <strong>{{ stat.away }}</strong>
              </div>
            </div>
            <footer class="lower-possession">
              <span>{{ possession.home }}</span>
              <div class="split-meter">
                <span class="home-meter" :style="widthStyle(possession.homePct)"></span>
                <span class="away-meter" :style="widthStyle(possession.awayPct)"></span>
              </div>
              <span>{{ possession.away }}</span>
            </footer>
          </template>

          <template v-else-if="variant.kind === 'matrix'">
            <header class="matrix-header">
              <b>{{ match.homeCode }}</b>
              <strong>MATCH PULSE</strong>
              <b>{{ match.awayCode }}</b>
            </header>
            <div class="matrix-grid">
              <div v-for="stat in matrixStats" :key="stat.label" class="matrix-cell">
                <span>{{ stat.label }}</span>
                <p>
                  <b>{{ stat.home }}</b>
                  <i></i>
                  <b>{{ stat.away }}</b>
                </p>
              </div>
            </div>
          </template>

          <template v-else-if="variant.kind === 'monolith'">
            <header class="monolith-header">
              <span>WORLD STAGE</span>
              <strong>{{ match.homeCode }} {{ match.score }} {{ match.awayCode }}</strong>
            </header>
            <div class="monolith-score">
              <b>{{ possession.home }}</b>
              <span>POSSESSION</span>
              <b>{{ possession.away }}</b>
            </div>
            <div class="monolith-lines">
              <p v-for="stat in secondaryStats" :key="stat.label">
                <strong>{{ stat.home }}</strong>
                <span>{{ stat.label }}</span>
                <strong>{{ stat.away }}</strong>
              </p>
            </div>
          </template>

          <template v-else>
            <header class="tower-header">
              <div>
                <b>{{ match.homeCode }}</b>
                <span>{{ match.home }}</span>
              </div>
              <strong>{{ match.score }}</strong>
              <div>
                <b>{{ match.awayCode }}</b>
                <span>{{ match.away }}</span>
              </div>
            </header>
            <div class="tower-body">
              <div class="tower-feature">
                <span>점유율</span>
                <strong>{{ possession.home }} - {{ possession.away }}</strong>
              </div>
              <p v-for="stat in secondaryStats" :key="stat.label">
                <b>{{ stat.home }}</b>
                <span>{{ stat.label }}</span>
                <b>{{ stat.away }}</b>
              </p>
            </div>
          </template>
        </section>

        <footer class="variant-feedback">
          <span>{{ variant.feedback }}</span>
          <strong>{{ variant.next }}</strong>
        </footer>
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

.stats-lab-page {
  --home: #C8102E;
  --away: #003478;
  --ink: #F8F2DF;
  --paper: #11151F;
  --line: #F4D27A;
  width: 100vw;
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
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
  flex: 0 0 9%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 2%;
  padding: 1.1% 1.4% 0.8%;
  background: #191F2D;
  border-bottom: 0.16rem solid #D7B85D;
}

.lab-kicker {
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

.variant-grid {
  flex: 1 1 auto;
  min-height: 0;
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  grid-template-rows: repeat(2, minmax(0, 1fr));
  gap: 0.72rem;
  padding: 0.72rem;
}

.variant-tile {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 0.42rem;
  padding: 0.52rem;
  background: #202838;
  border: 0.1rem solid #3B465D;
  border-radius: 0.55rem;
  box-shadow: 0.22rem 0.22rem 0 #070910;
}

.variant-meta {
  flex: 0 0 2.55rem;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 0.1rem;
}

.variant-meta strong {
  font-size: 1.08rem;
  line-height: 1;
}

.variant-meta span {
  color: #B8C2D6;
  font-size: 0.73rem;
  font-weight: 800;
}

.stats-prototype {
  flex: 1 1 auto;
  min-height: 0;
  position: relative;
  overflow: hidden;
  color: #FFFFFF;
  background: #07123D;
  border: 0.16rem solid #F4D27A;
  box-shadow: 0.22rem 0.22rem 0 #050609;
}

.variant-feedback {
  flex: 0 0 4.65rem;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 0.3rem;
  padding: 0.48rem;
  background: #121826;
  border: 0.08rem solid #3B465D;
  border-radius: 0.35rem;
}

.variant-feedback span,
.variant-feedback strong {
  display: block;
  font-size: 0.72rem;
  line-height: 1.22;
}

.variant-feedback span {
  color: #D7DDEA;
  font-weight: 700;
}

.variant-feedback strong {
  color: #F4D27A;
  font-weight: 900;
}

.split-meter {
  display: flex;
  height: 0.68rem;
  overflow: hidden;
  background: #061021;
  border: 0.08rem solid #E8EEF7;
  border-radius: 999rem;
}

.home-meter,
.away-meter {
  display: block;
  height: 100%;
}

.home-meter {
  background: var(--home);
}

.away-meter {
  background: var(--away);
}

.stats-prototype--ribbon {
  display: flex;
  flex-direction: column;
  border-radius: 1rem 1rem 0.45rem 0.45rem;
  background: #1239A7;
}

.ribbon-strips {
  flex: 0 0 11%;
  display: flex;
  background: #F8F2DF;
}

.ribbon-strips span {
  flex: 1;
}

.ribbon-strips span:nth-child(1) {
  background: #C8102E;
}

.ribbon-strips span:nth-child(2) {
  background: #F4D27A;
}

.ribbon-strips span:nth-child(3) {
  background: #001C5A;
}

.ribbon-strips span:nth-child(4) {
  background: #F8F2DF;
}

.ribbon-strips span:nth-child(5) {
  background: #003478;
}

.ribbon-crest-row {
  flex: 0 0 25%;
  display: flex;
  align-items: center;
  justify-content: space-around;
  padding: 0 8%;
  background: #0B2D92;
}

.ribbon-crest-row b {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 3.2rem;
  aspect-ratio: 1;
  border-radius: 50%;
  background: #F8F2DF;
  color: #07123D;
  font-size: 1.05rem;
}

.ribbon-crest-row span {
  font-size: 1rem;
  font-weight: 950;
}

.ribbon-team-row,
.ribbon-possession,
.ribbon-stat-list p {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.ribbon-team-row {
  flex: 0 0 13%;
  padding: 0 7%;
  background: #071866;
  border-top: 0.08rem solid #F8F2DF;
  border-bottom: 0.08rem solid #F8F2DF;
  font-size: 0.9rem;
}

.ribbon-team-row i {
  font-style: normal;
  color: #F4D27A;
  font-weight: 950;
}

.ribbon-possession {
  flex: 0 0 17%;
  gap: 0.65rem;
  padding: 0 8%;
  background: #1239A7;
}

.ribbon-possession .split-meter {
  flex: 1;
}

.ribbon-stat-list {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: space-evenly;
  padding: 0.38rem 10% 0.55rem;
  background: #102E8D;
}

.ribbon-stat-list p {
  margin: 0;
  font-size: 0.86rem;
  font-weight: 900;
}

.ribbon-stat-list span {
  color: #DCE6FF;
}

.stats-prototype--split {
  display: flex;
  flex-direction: column;
  border-radius: 999rem 999rem 1rem 1rem;
  background: #081018;
  border-color: #00D5FF;
}

.split-header,
.split-footer {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.8rem;
  background: #142034;
  color: #00D5FF;
  font-size: 0.92rem;
  font-weight: 950;
}

.split-header {
  flex: 0 0 15%;
}

.split-body {
  flex: 1;
  display: flex;
  min-height: 0;
}

.split-team,
.split-spine {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.split-team {
  flex: 1;
  justify-content: space-evenly;
  padding: 0.7rem 0.35rem;
}

.split-home {
  background: #C8102E;
}

.split-away {
  background: #003478;
}

.split-team b {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2.85rem;
  aspect-ratio: 1;
  border-radius: 50%;
  background: #FFFFFF;
  color: #081018;
  font-size: 0.95rem;
}

.split-team strong {
  font-size: 0.85rem;
  text-align: center;
}

.split-team span {
  font-size: 1.25rem;
  font-weight: 950;
}

.split-spine {
  flex: 0 0 34%;
  justify-content: space-evenly;
  background: #F8F2DF;
  color: #081018;
  border-left: 0.08rem solid #081018;
  border-right: 0.08rem solid #081018;
}

.split-spine i {
  font-style: normal;
  font-size: 1.35rem;
  font-weight: 950;
}

.split-spine span {
  font-size: 0.72rem;
  font-weight: 950;
}

.split-footer {
  flex: 0 0 13%;
  justify-content: space-around;
  background: #081018;
}

.stats-prototype--rail {
  display: flex;
  border-radius: 0.3rem;
  background: #101727;
  border-color: #F1F4FF;
}

.rail-team {
  flex: 0 0 20%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  writing-mode: vertical-rl;
  text-orientation: mixed;
}

.rail-team b {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2.2rem;
  height: 2.2rem;
  writing-mode: horizontal-tb;
  border-radius: 0.45rem;
  background: #FFFFFF;
  color: #101727;
}

.rail-home {
  background: #C8102E;
}

.rail-away {
  background: #003478;
}

.rail-stats {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: space-evenly;
  padding: 0.65rem 0.7rem;
}

.rail-stats header,
.rail-stats p {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.rail-stats header {
  color: #F4D27A;
  font-size: 0.74rem;
  font-weight: 950;
}

.rail-stats p {
  margin: 0;
  padding: 0.32rem 0;
  border-bottom: 0.08rem solid #34425F;
  font-size: 0.88rem;
  font-weight: 900;
}

.rail-stats p span {
  color: #D8DEEC;
  font-size: 0.76rem;
}

.stats-prototype--dial {
  display: flex;
  flex-direction: column;
  border-radius: 50% 50% 0.8rem 0.8rem / 13% 13% 0.8rem 0.8rem;
  background: #10162A;
  border-color: #00D5FF;
}

.dial-header {
  flex: 0 0 15%;
  display: flex;
  align-items: center;
  justify-content: space-around;
  background: #001C5A;
  color: #FFFFFF;
  font-weight: 950;
}

.dial-header b {
  width: 3rem;
  padding: 0.3rem 0;
  text-align: center;
  background: #FFFFFF;
  color: #001C5A;
  border-radius: 999rem;
}

.dial-core {
  flex: 0 0 43%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #0C1430;
}

.dial-ring {
  width: 8.2rem;
  aspect-ratio: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: conic-gradient(#C8102E 0deg 220deg, #003478 220deg 360deg);
  color: #FFFFFF;
  border: 0.38rem solid #F8F2DF;
  box-shadow: 0.2rem 0.2rem 0 #050609;
}

.dial-ring strong {
  font-size: 1.4rem;
  line-height: 1;
}

.dial-ring span {
  padding: 0.1rem 0.45rem;
  background: #081018;
  border-radius: 999rem;
  font-size: 0.72rem;
  font-weight: 900;
}

.dial-stat-cloud {
  flex: 1;
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 0.36rem;
  padding: 0.55rem;
}

.dial-stat-cloud p {
  margin: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 0.42rem;
  background: #1B2442;
  border: 0.08rem solid #3B4A7B;
  border-radius: 0.45rem;
}

.dial-stat-cloud span {
  color: #AFC6FF;
  font-size: 0.72rem;
  font-weight: 800;
}

.dial-stat-cloud b {
  font-size: 1rem;
}

.stats-prototype--timeline {
  display: flex;
  flex-direction: column;
  padding: 0.7rem;
  background: #0D111A;
  border-color: #FFFFFF;
}

.timeline-header {
  flex: 0 0 16%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: #FFFFFF;
  border-bottom: 0.12rem solid #FFFFFF;
}

.timeline-header strong {
  font-size: 1.5rem;
}

.timeline-header span {
  color: #F4D27A;
  font-weight: 950;
}

.timeline-lanes {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: space-evenly;
}

.timeline-row {
  display: grid;
  grid-template-columns: 2.4rem 1fr 2.4rem;
  align-items: center;
  gap: 0.45rem;
}

.timeline-row b {
  font-size: 1rem;
  text-align: center;
}

.timeline-row div {
  position: relative;
  height: 2.05rem;
  background: #1D2635;
  border: 0.08rem solid #4C5E79;
  border-radius: 999rem;
  overflow: hidden;
}

.timeline-label {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 3;
  font-size: 0.72rem;
  font-weight: 950;
}

.timeline-home,
.timeline-away {
  position: absolute;
  top: 0;
  height: 50%;
  display: block;
}

.timeline-home {
  left: 0;
  background: #C8102E;
}

.timeline-away {
  bottom: 0;
  top: auto;
  background: #003478;
}

.stats-prototype--ticket {
  display: flex;
  border-radius: 0.75rem;
  background: #F8F2DF;
  border-color: #101727;
  color: #101727;
}

.ticket-stub {
  flex: 0 0 24%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1.3rem;
  background: #D7B85D;
  border-right: 0.16rem dashed #101727;
  writing-mode: vertical-rl;
  font-weight: 950;
}

.ticket-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 0.7rem;
}

.ticket-main header,
.ticket-teams,
.ticket-stats p {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.ticket-main header {
  flex: 0 0 20%;
  color: #FFFFFF;
}

.ticket-main header b,
.ticket-main header strong {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 3rem;
  height: 2.2rem;
  background: #101727;
  border-radius: 0.4rem;
}

.ticket-main header strong {
  min-width: 4rem;
  background: #C8102E;
}

.ticket-teams {
  flex: 0 0 12%;
  color: #101727;
  font-size: 0.72rem;
  font-weight: 950;
  border-bottom: 0.12rem solid #101727;
}

.ticket-stats {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: space-evenly;
}

.ticket-stats p {
  margin: 0;
  color: #101727;
  font-size: 0.82rem;
  font-weight: 950;
}

.ticket-stats span {
  color: #455066;
}

.stats-prototype--lower {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 0.75rem;
  padding: 1rem;
  background: #07123D;
  border-radius: 0.25rem 1.2rem 0.25rem 1.2rem;
  border-color: #00D5FF;
}

.lower-score,
.lower-possession,
.lower-band {
  display: flex;
  align-items: center;
}

.lower-score {
  justify-content: space-between;
  padding: 0.5rem 0.7rem;
  background: #FFFFFF;
  color: #07123D;
  border-radius: 999rem;
  font-weight: 950;
}

.lower-score strong {
  color: #C8102E;
  font-size: 1.45rem;
}

.lower-stack {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
}

.lower-band {
  justify-content: space-between;
  padding: 0.58rem 0.72rem;
  background: #0B2D92;
  border-left: 0.55rem solid #C8102E;
  border-right: 0.55rem solid #003478;
  font-size: 0.92rem;
  font-weight: 950;
}

.lower-band span {
  color: #E3EAFF;
}

.lower-possession {
  gap: 0.55rem;
  font-weight: 950;
}

.lower-possession .split-meter {
  flex: 1;
}

.stats-prototype--matrix {
  display: flex;
  flex-direction: column;
  padding: 0.65rem;
  background: #EDE8D8;
  color: #09101D;
  border-color: #09101D;
}

.matrix-header {
  flex: 0 0 18%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 0.65rem;
  background: #09101D;
  color: #FFFFFF;
  border-radius: 0.5rem 0.5rem 0 0;
}

.matrix-header strong {
  color: #F4D27A;
}

.matrix-grid {
  flex: 1;
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 0.5rem;
  padding-top: 0.55rem;
}

.matrix-cell {
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 0.62rem;
  background: #FFFFFF;
  border: 0.12rem solid #09101D;
  border-radius: 0.45rem;
  box-shadow: 0.16rem 0.16rem 0 #C7B98E;
}

.matrix-cell span {
  color: #4A5260;
  font-size: 0.78rem;
  font-weight: 950;
}

.matrix-cell p {
  margin: 0.35rem 0 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.matrix-cell b {
  font-size: 1.45rem;
}

.matrix-cell i {
  display: block;
  width: 0.28rem;
  height: 2.2rem;
  background: #D7B85D;
  border-radius: 999rem;
}

.stats-prototype--monolith {
  display: flex;
  flex-direction: column;
  padding: 0.8rem;
  background: #050505;
  border-color: #D7B85D;
  border-radius: 0.15rem;
}

.monolith-header {
  flex: 0 0 22%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 0.35rem;
  border-bottom: 0.1rem solid #D7B85D;
}

.monolith-header span {
  color: #D7B85D;
  font-size: 0.7rem;
  font-weight: 950;
}

.monolith-header strong {
  font-size: 1.45rem;
}

.monolith-score {
  flex: 0 0 26%;
  display: grid;
  grid-template-columns: 1fr 1.35fr 1fr;
  align-items: center;
  text-align: center;
  color: #D7B85D;
}

.monolith-score b {
  font-size: 1.6rem;
}

.monolith-score span {
  color: #FFFFFF;
  font-size: 0.72rem;
  font-weight: 950;
}

.monolith-lines {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: space-evenly;
}

.monolith-lines p {
  margin: 0;
  display: grid;
  grid-template-columns: 1fr 1.6fr 1fr;
  gap: 0.45rem;
  align-items: center;
  padding: 0.35rem 0;
  border-top: 0.08rem solid #2E2A1D;
  font-size: 0.86rem;
}

.monolith-lines span {
  color: #E8D99F;
  text-align: center;
  font-weight: 900;
}

.monolith-lines strong:last-child {
  text-align: right;
}

.stats-prototype--tower {
  display: flex;
  flex-direction: column;
  border-radius: 1.05rem;
  background: #06146A;
  border-color: #051141;
}

.tower-header {
  flex: 0 0 34%;
  display: grid;
  grid-template-columns: 1fr 0.82fr 1fr;
  align-items: center;
  gap: 0.35rem;
  padding: 0.65rem;
  background: #0B2D92;
  border-bottom: 0.16rem solid #FFFFFF;
}

.tower-header div {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.35rem;
}

.tower-header b {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 3.2rem;
  aspect-ratio: 1;
  border-radius: 50%;
  background: #FFFFFF;
  color: #06146A;
}

.tower-header span {
  font-size: 0.72rem;
  font-weight: 900;
  text-align: center;
}

.tower-header strong {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 2.8rem;
  background: #06146A;
  border: 0.12rem solid #FFFFFF;
  border-radius: 0.35rem;
  color: #F4D27A;
  font-size: 1.45rem;
}

.tower-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: space-evenly;
  padding: 0.62rem 0.82rem;
  background: #102E8D;
}

.tower-feature {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.2rem;
  padding: 0.46rem;
  background: #06146A;
  border-radius: 0.42rem;
  border: 0.1rem solid #FFFFFF;
}

.tower-feature span {
  color: #AFC6FF;
  font-size: 0.72rem;
  font-weight: 900;
}

.tower-feature strong {
  font-size: 1.22rem;
}

.tower-body p {
  margin: 0;
  display: grid;
  grid-template-columns: 1fr 1.5fr 1fr;
  align-items: center;
  font-size: 0.84rem;
  font-weight: 950;
}

.tower-body p span {
  color: #DCE6FF;
  text-align: center;
}

.tower-body p b:last-child {
  text-align: right;
}
</style>
