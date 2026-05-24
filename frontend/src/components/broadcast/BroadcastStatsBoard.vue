<script setup lang="ts">
import { computed } from 'vue'

type LeagueSlug =
  | 'premier-league'
  | 'champions-league'
  | 'europa-league'
  | 'carabao-cup'
  | 'fa-cup'
  | 'world-cup-2026'

type StatItem = {
  label: string
  home: string
  away: string
  homePct: number
  awayPct: number
}

type BoardVariant = 'ribbon' | 'dial' | 'matrix' | 'timeline' | 'ticket' | 'lower' | 'tower'

const props = defineProps<{
  league: LeagueSlug
  themeLabel: string
  home: string
  away: string
  homeCode: string
  awayCode: string
  homeLogoUrl?: string
  awayLogoUrl?: string
  score: string
  clock: string
  status: string
  stats: StatItem[]
  materialRevision?: boolean
}>()

const boardVariant = computed<BoardVariant>(() => {
  switch (props.league) {
    case 'world-cup-2026':
      return 'ribbon'
    case 'premier-league':
      return 'dial'
    case 'champions-league':
      return 'matrix'
    case 'europa-league':
      return 'timeline'
    case 'carabao-cup':
      return 'ticket'
    case 'fa-cup':
      return 'tower'
    default:
      return 'tower'
  }
})

const possession = computed(() => props.stats[0])
const secondaryStats = computed(() => props.stats.slice(1))
const compactStats = computed(() => secondaryStats.value.slice(0, 3))
const matrixStats = computed(() => props.stats.slice(0, 4))

function widthStyle(value: number) {
  return { width: `${value}%` }
}

function awayOffsetStyle(value: number) {
  return { marginLeft: `${100 - value}%`, width: `${value}%` }
}

</script>

<template>
  <article
    class="stats-card"
    :class="[`stats-card--${boardVariant}`, { 'stats-card--material': materialRevision }]"
    :data-variant="boardVariant"
    data-testid="stats-card"
  >
    <div v-if="stats.length === 0" class="stats-empty" data-testid="stats-empty">
      <span>경기 스탯</span>
      <strong>라이브 스탯 수신 대기</strong>
      <p>{{ homeCode }} / {{ awayCode }}</p>
    </div>

    <template v-else-if="boardVariant === 'ribbon'">
      <div class="ribbon-strips" aria-hidden="true">
        <span></span><span></span><span></span><span></span><span></span>
      </div>
      <header class="ribbon-crest-row">
        <span class="ribbon-country-badge" data-testid="stats-country-badge" :aria-label="homeCode">
          <img v-if="homeLogoUrl" :src="homeLogoUrl" alt="" aria-hidden="true" />
          <b v-else>{{ homeCode }}</b>
        </span>
        <span>경기 스탯</span>
        <span class="ribbon-country-badge" data-testid="stats-country-badge" :aria-label="awayCode">
          <img v-if="awayLogoUrl" :src="awayLogoUrl" alt="" aria-hidden="true" />
          <b v-else>{{ awayCode }}</b>
        </span>
      </header>
      <div class="ribbon-team-row">
        <strong>{{ home }}</strong>
        <i>{{ themeLabel }}</i>
        <strong>{{ away }}</strong>
      </div>
      <div v-if="possession" class="ribbon-possession">
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

    <template v-else-if="boardVariant === 'dial'">
      <header class="dial-header">
        <b>{{ homeCode }}</b>
        <span>{{ themeLabel }}</span>
        <b>{{ awayCode }}</b>
      </header>
      <div v-if="possession" class="dial-core">
        <span
          class="dial-team-crest dial-team-crest--home"
          data-testid="stats-possession-home-logo"
          :aria-label="home"
        >
          <img v-if="homeLogoUrl" :src="homeLogoUrl" alt="" aria-hidden="true" />
          <b v-else>{{ homeCode }}</b>
        </span>
        <div class="dial-ring">
          <strong>{{ possession.home }}</strong>
          <span>점유율</span>
          <strong>{{ possession.away }}</strong>
        </div>
        <span
          class="dial-team-crest dial-team-crest--away"
          data-testid="stats-possession-away-logo"
          :aria-label="away"
        >
          <img v-if="awayLogoUrl" :src="awayLogoUrl" alt="" aria-hidden="true" />
          <b v-else>{{ awayCode }}</b>
        </span>
      </div>
      <div class="dial-stat-cloud">
        <p v-for="stat in secondaryStats" :key="stat.label">
          <span>{{ stat.label }}</span>
          <b>{{ stat.home }} / {{ stat.away }}</b>
        </p>
      </div>
    </template>

    <template v-else-if="boardVariant === 'matrix'">
      <header class="matrix-header">
        <b>{{ homeCode }}</b>
        <strong>경기 흐름</strong>
        <b>{{ awayCode }}</b>
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
      <footer class="matrix-footer">{{ themeLabel }}</footer>
    </template>

    <template v-else-if="boardVariant === 'timeline'">
      <header class="timeline-header">
        <strong>{{ themeLabel }}</strong>
        <span>{{ homeCode }} / {{ awayCode }}</span>
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

    <template v-else-if="boardVariant === 'lower'">
      <header class="lower-score">
        <b>{{ homeCode }}</b>
        <strong>경기 스탯</strong>
        <b>{{ awayCode }}</b>
        <span>{{ themeLabel }}</span>
      </header>
      <div class="lower-stack">
        <div v-for="stat in compactStats" :key="stat.label" class="lower-band">
          <strong>{{ stat.home }}</strong>
          <span>{{ stat.label }}</span>
          <strong>{{ stat.away }}</strong>
        </div>
      </div>
      <footer v-if="possession" class="lower-possession">
        <span>{{ possession.home }}</span>
        <div class="split-meter">
          <span class="home-meter" :style="widthStyle(possession.homePct)"></span>
          <span class="away-meter" :style="widthStyle(possession.awayPct)"></span>
        </div>
        <span>{{ possession.away }}</span>
      </footer>
    </template>

    <template v-else-if="boardVariant === 'ticket'">
      <aside class="ticket-stub">
        <span>경기</span>
        <b>스탯</b>
      </aside>
      <section class="ticket-main">
        <header>
          <b>{{ homeCode }}</b>
          <strong>경기 스탯</strong>
          <b>{{ awayCode }}</b>
        </header>
        <div class="ticket-teams">
          <span>{{ home }}</span>
          <span>{{ away }}</span>
        </div>
        <div class="ticket-stats">
          <p v-for="stat in stats" :key="stat.label">
            <b>{{ stat.home }}</b>
            <span>{{ stat.label }}</span>
            <b>{{ stat.away }}</b>
          </p>
        </div>
      </section>
    </template>

    <template v-else>
      <header class="tower-header">
        <div>
          <b>{{ homeCode }}</b>
          <span>{{ home }}</span>
        </div>
        <strong>{{ themeLabel }}</strong>
        <div>
          <b>{{ awayCode }}</b>
          <span>{{ away }}</span>
        </div>
      </header>
      <div class="tower-body">
        <div v-if="possession" class="tower-feature">
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
  </article>
</template>

<style scoped>
*,
*::before,
*::after {
  box-sizing: border-box;
}

.stats-card {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  overflow: hidden;
  color: var(--text);
  background: var(--panel);
  border: 0.16rem solid var(--border);
  box-shadow: 0.38rem 0.38rem 0 #000000;
  font-weight: 900;
}

.stats-empty {
  width: 100%;
  min-height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.45rem;
  padding: 1rem;
  text-align: center;
}

.stats-empty span {
  color: var(--muted);
  font-size: 0.78rem;
}

.stats-empty strong {
  color: var(--text);
  font-size: 1.1rem;
}

.stats-empty p {
  margin: 0;
  color: var(--accent-alt);
  font-size: 0.8rem;
}

.split-meter {
  display: flex;
  height: 0.72rem;
  overflow: hidden;
  background: var(--dark);
  border: 0.08rem solid var(--border);
  border-radius: 999rem;
}

.home-meter,
.away-meter {
  display: block;
  height: 100%;
}

.home-meter {
  background: var(--accent);
}

.away-meter {
  background: var(--accent-alt);
}

.stats-card--ribbon {
  flex-direction: column;
  border-radius: 1rem 1rem 0.5rem 0.5rem;
  background: #1239A7;
  border-color: #F5F1E8;
}

.stats-card--material {
  position: relative;
  isolation: isolate;
  box-shadow:
    0.42rem 0.42rem 0 #000000,
    0 0 0.75rem rgba(255, 255, 255, 0.1);
}

.stats-card--material::before,
.stats-card--material::after {
  position: absolute;
  inset: 0;
  pointer-events: none;
  content: '';
}

.stats-card--material::before {
  z-index: 2;
  background:
    linear-gradient(108deg, rgba(255, 255, 255, 0) 0 27%, rgba(255, 255, 255, 0.08) 37%, rgba(255, 255, 255, 0) 48%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.07), rgba(255, 255, 255, 0) 46%);
  mix-blend-mode: screen;
}

.stats-card--material::after {
  inset: 0.28rem;
  z-index: 2;
  border: 0.08rem solid rgba(255, 255, 255, 0.16);
  border-radius: inherit;
}

.stats-card--material > * {
  position: relative;
  z-index: 1;
}

.ribbon-strips {
  flex: 0 0 10%;
  display: flex;
  background: #F5F1E8;
}

.ribbon-strips span {
  flex: 1;
}

.ribbon-strips span:nth-child(1) {
  background: #C8102E;
}

.ribbon-strips span:nth-child(2) {
  background: #D4AF37;
}

.ribbon-strips span:nth-child(3) {
  background: #000000;
}

.ribbon-strips span:nth-child(4) {
  background: #F5F1E8;
}

.ribbon-strips span:nth-child(5) {
  background: #003478;
}

.ribbon-crest-row {
  flex: 0 0 24%;
  display: flex;
  align-items: center;
  justify-content: space-around;
  padding: 0 8%;
  background: #0B2D92;
}

.stats-card--material .ribbon-crest-row {
  background:
    radial-gradient(circle at 50% -18%, rgba(255, 255, 255, 0.12), rgba(255, 255, 255, 0) 44%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.07), rgba(255, 255, 255, 0) 58%),
    #0B2D92;
}

.ribbon-country-badge {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 4.65rem;
  aspect-ratio: 1;
  overflow: hidden;
  border-radius: 50%;
  background: #F5F1E8;
  border: 0.2rem solid #F5F1E8;
  box-shadow:
    inset 0 0 0 0.16rem #D4AF37,
    0.16rem 0.16rem 0 #000000;
}

.ribbon-country-badge img {
  position: absolute;
  inset: 0;
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.ribbon-country-badge b {
  position: relative;
  z-index: 1;
  color: #071866;
  font-size: 1rem;
}

.stats-card--material .ribbon-country-badge {
  box-shadow:
    inset 0 0 0 0.16rem rgba(212, 175, 55, 0.95),
    inset 0 0.7rem 1rem rgba(255, 255, 255, 0.12),
    inset 0 -0.7rem 1rem rgba(0, 0, 0, 0.14),
    0.16rem 0.16rem 0 #000000,
    0 0 0.55rem rgba(255, 255, 255, 0.1);
}

.stats-card--material .ribbon-country-badge::before {
  position: absolute;
  inset: 0.18rem;
  z-index: 2;
  display: block;
  pointer-events: none;
  border-radius: 50%;
  background: radial-gradient(circle at 32% 20%, rgba(255, 255, 255, 0.22), rgba(255, 255, 255, 0) 42%);
  content: '';
}

.ribbon-country-badge::after {
  position: absolute;
  left: 15%;
  top: 12%;
  width: 48%;
  height: 15%;
  display: block;
  background: rgba(255, 255, 255, 0.42);
  border-radius: 999rem;
  content: '';
  transform: rotate(-18deg);
}

.stats-card--material .ribbon-country-badge::after {
  z-index: 3;
  background: rgba(255, 255, 255, 0.16);
}

.stats-card--material .ribbon-country-badge img {
  z-index: 1;
}

.ribbon-crest-row span {
  font-size: 1rem;
}

.ribbon-team-row,
.ribbon-possession,
.ribbon-stat-list p {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.ribbon-team-row {
  flex: 0 0 14%;
  padding: 0 7%;
  background: #071866;
  border-top: 0.08rem solid #F5F1E8;
  border-bottom: 0.08rem solid #F5F1E8;
  font-size: 0.86rem;
}

.ribbon-team-row i {
  font-style: normal;
  color: #D4AF37;
  font-size: 0.76rem;
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

.stats-card--material .ribbon-possession .split-meter {
  position: relative;
  box-shadow:
    inset 0 0.08rem 0 rgba(255, 255, 255, 0.18),
    inset 0 -0.08rem 0 rgba(0, 0, 0, 0.16);
}

.stats-card--material .ribbon-possession .split-meter::after {
  position: absolute;
  left: 0.18rem;
  right: 0.18rem;
  top: 0.14rem;
  height: 28%;
  pointer-events: none;
  border-radius: 999rem;
  background: rgba(255, 255, 255, 0.14);
  content: '';
}

.ribbon-stat-list {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: space-evenly;
  padding: 0.32rem 9% 0.52rem;
  background: #102E8D;
}

.ribbon-stat-list p {
  margin: 0;
  font-size: 0.9rem;
}

.stats-card--material .ribbon-stat-list p {
  min-height: 1.9rem;
  padding: 0 0.7rem;
  border: 0.06rem solid rgba(255, 255, 255, 0.12);
  border-radius: 0.5rem;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.05), rgba(255, 255, 255, 0) 48%),
    rgba(7, 24, 102, 0.24);
  box-shadow: inset 0 -0.06rem 0 rgba(0, 0, 0, 0.12);
}

.ribbon-stat-list span {
  color: #DCE6FF;
}

.stats-card--dial {
  flex-direction: column;
  border-radius: 2.2rem 2.2rem 0.8rem 0.8rem;
  background: var(--dark);
  border-color: var(--accent-alt);
}

.dial-header {
  flex: 0 0 15%;
  display: flex;
  align-items: center;
  justify-content: space-around;
  background: var(--panel);
  color: #FFFFFF;
}

.dial-header b {
  width: 3rem;
  padding: 0.28rem 0;
  text-align: center;
  background: var(--text);
  color: var(--panel);
  border-radius: 999rem;
}

.dial-header span {
  color: var(--accent-alt);
  font-size: 0.78rem;
}

.dial-core {
  position: relative;
  flex: 0 0 42%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--dark);
}

.dial-team-crest {
  position: absolute;
  bottom: 0.52rem;
  z-index: 2;
  width: 3.5rem;
  aspect-ratio: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border: 0.16rem solid var(--border);
  border-radius: 50%;
  background: #FFFFFF;
  box-shadow:
    0.14rem 0.14rem 0 #000000,
    inset 0 0 0 0.08rem rgba(18, 5, 31, 0.12);
}

.dial-team-crest--home {
  left: 1.05rem;
}

.dial-team-crest--away {
  right: 1.05rem;
}

.dial-team-crest img {
  display: block;
  width: 76%;
  height: 76%;
  object-fit: contain;
}

.dial-team-crest b {
  color: var(--panel);
  font-size: 0.72rem;
  line-height: 1;
}

.dial-ring {
  width: 8.2rem;
  aspect-ratio: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: conic-gradient(var(--accent) 0deg 220deg, var(--accent-alt) 220deg 360deg);
  border: 0.38rem solid var(--text);
  box-shadow: 0.2rem 0.2rem 0 #000000;
}

.dial-ring strong {
  font-size: 1.4rem;
  line-height: 1;
}

.dial-ring span {
  padding: 0.12rem 0.5rem;
  background: var(--dark);
  border-radius: 999rem;
  font-size: 0.72rem;
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
  background: var(--panel);
  border: 0.08rem solid var(--accent-alt);
  border-radius: 0.45rem;
}

.dial-stat-cloud span {
  color: var(--muted);
  font-size: 0.72rem;
}

.dial-stat-cloud b {
  font-size: 1rem;
}

.stats-card--matrix {
  flex-direction: column;
  padding: 0.65rem;
  background: #E9EEFF;
  color: #010056;
  border-color: #F1F4FF;
  border-radius: 0.6rem;
}

.matrix-header {
  flex: 0 0 18%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 0.65rem;
  background: #010056;
  color: #FFFFFF;
  border-radius: 0.45rem 0.45rem 0 0;
}

.matrix-header strong {
  color: #8CB2FF;
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
  border: 0.12rem solid #010056;
  border-radius: 0.45rem;
  box-shadow: 0.16rem 0.16rem 0 #315DFF;
}

.matrix-cell span {
  color: #315DFF;
  font-size: 0.78rem;
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
  background: #9A00FF;
  border-radius: 999rem;
}

.matrix-footer {
  flex: 0 0 10%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #315DFF;
  font-size: 0.72rem;
}

.stats-card--timeline {
  flex-direction: column;
  padding: 0.7rem;
  background: #1A1A1A;
  border-color: #FFB000;
  border-radius: 0.2rem;
}

.timeline-header {
  flex: 0 0 16%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: #FFFFFF;
  border-bottom: 0.12rem solid #FF6A00;
}

.timeline-header strong {
  color: #FFB000;
  font-size: 1.5rem;
}

.timeline-header span {
  color: #FFFFFF;
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
  background: #3C2A20;
  border: 0.08rem solid #FFB000;
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
  color: #FFFFFF;
  font-size: 0.72rem;
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
  background: #FF6A00;
}

.timeline-away {
  top: auto;
  bottom: 0;
  background: #FFB000;
}

.stats-card--ticket {
  border-radius: 0.75rem;
  background: var(--muted);
  border-color: var(--dark);
  color: var(--dark);
}

.ticket-stub {
  flex: 0 0 24%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1.3rem;
  background: var(--accent);
  border-right: 0.16rem dashed var(--dark);
  writing-mode: vertical-rl;
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
  background: var(--dark);
  border-radius: 0.4rem;
}

.ticket-main header strong {
  min-width: 5.4rem;
  background: var(--accent);
  font-size: 0.78rem;
}

.ticket-teams {
  flex: 0 0 12%;
  font-size: 0.72rem;
  border-bottom: 0.12rem solid var(--dark);
}

.ticket-stats {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: space-evenly;
}

.ticket-stats p {
  margin: 0;
  font-size: 0.86rem;
}

.ticket-stats span {
  color: var(--panel);
}

.stats-card--lower {
  flex-direction: column;
  border-radius: 0.75rem;
  background: var(--dark);
  border-color: var(--accent-alt);
}

.lower-score {
  flex: 0 0 23%;
  display: grid;
  grid-template-columns: 1fr 1.2fr 1fr 0.9fr;
  align-items: center;
  min-height: 0;
  background: var(--accent);
  color: var(--text);
}

.lower-score b,
.lower-score strong,
.lower-score span {
  min-height: 100%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.lower-score strong {
  background: var(--panel);
  border-left: 0.08rem solid var(--border);
  border-right: 0.08rem solid var(--border);
  font-size: 1.35rem;
}

.lower-score span {
  background: var(--accent-alt);
  color: var(--dark);
  font-size: 0.82rem;
}

.lower-stack {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 0.45rem;
  padding: 0.72rem;
  background:
    linear-gradient(110deg, rgba(255, 255, 255, 0.08), rgba(255, 255, 255, 0) 42%),
    var(--panel);
}

.lower-band {
  min-height: 2.55rem;
  display: grid;
  grid-template-columns: 1fr 1.7fr 1fr;
  align-items: center;
  padding: 0 0.7rem;
  border: 0.08rem solid var(--border);
  border-radius: 0.42rem;
  background: var(--dark);
}

.lower-band strong:last-child {
  text-align: right;
}

.lower-band span {
  color: var(--muted);
  text-align: center;
  font-size: 0.82rem;
}

.lower-possession {
  flex: 0 0 18%;
  display: grid;
  grid-template-columns: 3rem 1fr 3rem;
  align-items: center;
  gap: 0.55rem;
  padding: 0 0.75rem;
  background: var(--dark);
}

.lower-possession span {
  font-size: 0.86rem;
  text-align: center;
}

.stats-card--tower {
  flex-direction: column;
  border-radius: 1.05rem;
  background: var(--panel);
  border-color: var(--border);
}

.tower-header {
  flex: 0 0 34%;
  display: grid;
  grid-template-columns: 1fr 0.9fr 1fr;
  align-items: center;
  gap: 0.35rem;
  padding: 0.65rem;
  background: var(--dark);
  border-bottom: 0.16rem solid var(--accent-alt);
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
  background: var(--border);
  color: var(--dark);
}

.tower-header span {
  font-size: 0.72rem;
  text-align: center;
}

.tower-header strong {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 2.8rem;
  padding: 0 0.35rem;
  background: var(--panel);
  border: 0.12rem solid var(--accent-alt);
  border-radius: 0.35rem;
  color: var(--text);
  font-size: 0.68rem;
  text-align: center;
}

.tower-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: space-evenly;
  padding: 0.62rem 0.82rem;
  background: var(--panel);
}

.tower-feature {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.2rem;
  padding: 0.46rem;
  background: var(--dark);
  border: 0.1rem solid var(--border);
  border-radius: 0.42rem;
}

.tower-feature span {
  color: var(--accent-alt);
  font-size: 0.72rem;
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
}

.tower-body p span {
  color: var(--muted);
  text-align: center;
}

.tower-body p b:last-child {
  text-align: right;
}
</style>
