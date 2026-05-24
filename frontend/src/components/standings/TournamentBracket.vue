<script setup lang="ts">
import { computed } from 'vue'
import { CalendarDays, Trophy } from 'lucide-vue-next'
import type { TeamRef } from '@/types/home'
import type { TournamentPayload, TournamentRound } from '@/lib/api/general'
import { shortName, teamName } from '@/lib/displayNames'
import WorldCupTournamentTree from '@/components/standings/WorldCupTournamentTree.vue'

const props = defineProps<{
  tournament: TournamentPayload
  leagueId: number
}>()

type DisplayRound = TournamentRound & { is_template_only: boolean }
const MIN_VISIBLE_TOURNAMENT_ORDER = 984

function roundDisplayOrder(roundLabel: string): number {
  if (roundLabel.includes('예선')) return 100
  const numberedRound = roundLabel.match(/^(\d+)라운드$/)
  if (numberedRound) return 300 + Number(numberedRound[1])
  if (roundLabel === '플레이오프') return 940
  const knockoutRound = roundLabel.match(/^(\d+)강$/)
  if (knockoutRound) return 1000 - Number(knockoutRound[1])
  if (roundLabel === '4강') return 996
  if (roundLabel === '3위 결정전') return 999
  if (roundLabel === '결승') return 1000
  return 500
}

const displayRounds = computed<DisplayRound[]>(() => {
  const roundsByLabel = new Map(props.tournament.rounds.map((round) => [round.round_label, round]))
  const templateRounds = props.tournament.template_rounds
  if (templateRounds.length === 0) {
    return props.tournament.rounds
      .map((round) => ({ ...round, is_template_only: false }))
      .sort((a, b) => a.round_order - b.round_order)
  }

  const base = templateRounds.map((template) => {
    const round = roundsByLabel.get(template.round_label)
    if (round) return { ...round, round_order: roundDisplayOrder(template.round_label), slot_count: template.slot_count, is_template_only: false }
    return {
      round_label: template.round_label,
      rounds: [],
      round_order: roundDisplayOrder(template.round_label),
      slot_count: template.slot_count,
      fixture_count: 0,
      from_template: true,
      fixtures: [],
      is_template_only: true,
    }
  })
  const knownLabels = new Set(base.map((round) => round.round_label))
  const extra = props.tournament.rounds
    .filter((round) => !knownLabels.has(round.round_label))
    .map((round) => ({ ...round, round_order: roundDisplayOrder(round.round_label), is_template_only: false }))
    .sort((a, b) => a.round_order - b.round_order)
  return [...base, ...extra].sort((a, b) => a.round_order - b.round_order)
})
const visibleTournamentRounds = computed(() =>
  displayRounds.value.filter((round) => round.round_order >= MIN_VISIBLE_TOURNAMENT_ORDER),
)
const treeRounds = computed(() => [...visibleTournamentRounds.value].sort((a, b) => b.round_order - a.round_order))
const finalRound = computed(() => visibleTournamentRounds.value.find((round) => round.round_label === '결승') ?? treeRounds.value[0] ?? null)
const finalFixture = computed(() => finalRound.value?.fixtures.at(-1) ?? null)
const totalFixtureCount = computed(() =>
  visibleTournamentRounds.value.reduce((total, round) => total + round.fixture_count, 0),
)

function displayTeam(team: TeamRef | null): string {
  return team ? teamName(team) : 'TBD'
}

function compactTeam(team: TeamRef | null): string {
  return team ? shortName(team) : 'TBD'
}

function teamInitial(team: TeamRef | null): string {
  return displayTeam(team).slice(0, 1)
}

function scoreText(fixture: TournamentRound['fixtures'][number]): string {
  if (fixture.goals_home == null || fixture.goals_away == null) return fixture.status_short
  const regular = `${fixture.goals_home}-${fixture.goals_away}`
  if (fixture.score_pen_home != null && fixture.score_pen_away != null) {
    return `${regular} (PK ${fixture.score_pen_home}-${fixture.score_pen_away})`
  }
  return regular
}

function isFeaturedRound(roundLabel: string): boolean {
  return roundLabel === '결승' || roundLabel === '4강' || roundLabel === '3위 결정전'
}

function winnerName(fixture: TournamentRound['fixtures'][number] | null): string {
  if (!fixture) return 'TBD'
  if (fixture.home_winner === true && fixture.home) return teamName(fixture.home)
  if (fixture.away_winner === true && fixture.away) return teamName(fixture.away)
  return 'TBD'
}

function kickoffLabel(value: string | null): string {
  if (!value) return '일정 미정'
  return new Intl.DateTimeFormat('ko-KR', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Asia/Seoul',
  }).format(new Date(value))
}
</script>

<template>
  <WorldCupTournamentTree
    v-if="leagueId === 1"
    :tournament="tournament"
  />

  <section v-else class="tournament" data-testid="standings-tournament">
    <div class="tournament__summary">
      <strong>토너먼트</strong>
      <span>DB에 확정된 fixture만 채웁니다</span>
    </div>

    <header class="tree-crown">
      <span class="tree-crown__icon" aria-hidden="true">
        <Trophy :size="22" />
      </span>
      <span>
        <small>우승</small>
        <strong>{{ winnerName(finalFixture) }}</strong>
      </span>
      <b>{{ totalFixtureCount }}</b>
    </header>

    <div class="tournament-tree">
      <section
        v-for="round in treeRounds"
        :key="round.round_label"
        class="tree-level"
        :class="{
          'tree-level--featured': isFeaturedRound(round.round_label),
          'tree-level--compact': !isFeaturedRound(round.round_label),
        }"
      >
        <header class="tree-level__head">
          <h2>{{ round.round_label }}</h2>
          <span>{{ round.fixture_count }} / {{ round.slot_count }}</span>
        </header>

        <div v-if="round.fixtures.length === 0" class="tree-level__empty">
          <CalendarDays :size="16" />
          <span>TBD</span>
        </div>

        <div v-else class="tree-level__cards">
          <router-link
            v-for="fixture in round.fixtures"
            :key="fixture.external_id"
            class="match"
            :class="{
              'match--featured': isFeaturedRound(round.round_label),
              'match--compact': !isFeaturedRound(round.round_label),
            }"
            :to="{ name: 'fixture-detail', params: { externalId: fixture.external_id } }"
          >
            <template v-if="isFeaturedRound(round.round_label)">
              <span class="match__meta">
                <b>{{ kickoffLabel(fixture.kickoff_at) }}</b>
                <em>{{ scoreText(fixture) }}</em>
              </span>
              <span class="team" :data-winner="fixture.home_winner === true">
                <span class="team__logo">
                  <img v-if="fixture.home?.logo_url" :src="fixture.home.logo_url" alt="" loading="lazy" />
                  <b v-else>{{ teamInitial(fixture.home) }}</b>
                </span>
                <strong>{{ displayTeam(fixture.home) }}</strong>
              </span>
              <span class="team" :data-winner="fixture.away_winner === true">
                <span class="team__logo">
                  <img v-if="fixture.away?.logo_url" :src="fixture.away.logo_url" alt="" loading="lazy" />
                  <b v-else>{{ teamInitial(fixture.away) }}</b>
                </span>
                <strong>{{ displayTeam(fixture.away) }}</strong>
              </span>
            </template>

            <template v-else>
              <span class="match-compact__meta">
                <b>{{ kickoffLabel(fixture.kickoff_at) }}</b>
                <em>{{ scoreText(fixture) }}</em>
              </span>
              <span class="match-compact__teams">
                <strong :data-winner="fixture.home_winner === true" :title="displayTeam(fixture.home)">
                  {{ compactTeam(fixture.home) }}
                </strong>
                <span>v</span>
                <strong :data-winner="fixture.away_winner === true" :title="displayTeam(fixture.away)">
                  {{ compactTeam(fixture.away) }}
                </strong>
              </span>
            </template>
          </router-link>
        </div>
      </section>
    </div>
  </section>
</template>

<style scoped>
.tournament {
  display: grid;
  gap: 14px;
}

.tournament__summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: var(--color-muted);
  font-size: 12px;
}

.tournament__summary strong {
  color: var(--color-fg);
  font-size: 18px;
}

.tree-crown {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border: 1px solid color-mix(in srgb, #d5a11e 34%, var(--color-border));
  border-radius: 8px;
  background:
    linear-gradient(135deg, rgb(213 161 30 / 0.13), transparent 42%),
    var(--color-card);
}

.tree-crown__icon {
  display: inline-grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border: 1px solid rgb(213 161 30 / 0.38);
  border-radius: 999px;
  background: #ffffff;
  color: #b7791f;
}

.tree-crown span {
  display: grid;
  min-width: 0;
}

.tree-crown small {
  color: var(--color-muted);
  font-size: 11px;
  font-weight: 900;
}

.tree-crown strong {
  min-width: 0;
  overflow: hidden;
  font-size: 20px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tree-crown b {
  display: inline-grid;
  place-items: center;
  min-width: 36px;
  height: 28px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--theme-primary, var(--color-fg)) 14%, var(--color-bg));
  color: var(--color-muted);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

.tournament-tree {
  display: grid;
  gap: 12px;
  position: relative;
}

.tournament-tree::before {
  content: '';
  position: absolute;
  top: 0;
  bottom: 0;
  left: 50%;
  width: 1px;
  background: color-mix(in srgb, var(--theme-primary, var(--color-fg)) 24%, var(--color-border));
}

.tree-level {
  display: grid;
  position: relative;
  gap: 8px;
  padding: 10px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-card);
}

.tree-level::before {
  content: '';
  position: absolute;
  top: -13px;
  left: 50%;
  width: 1px;
  height: 13px;
  background: color-mix(in srgb, var(--theme-primary, var(--color-fg)) 36%, var(--color-border));
}

.tree-level:first-child::before {
  display: none;
}

.tree-level--featured {
  border-color: color-mix(in srgb, var(--theme-primary, var(--color-fg)) 24%, var(--color-border));
}

.tree-level__head {
  display: flex;
  position: relative;
  z-index: 1;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.tree-level__head h2 {
  margin: 0;
  font-size: 14px;
}

.tree-level__head span {
  display: inline-grid;
  place-items: center;
  min-width: 34px;
  height: 22px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--theme-primary, var(--color-fg)) 10%, var(--color-bg));
  color: var(--color-muted);
  font-size: 10px;
  font-weight: 900;
}

.tree-level__empty {
  display: grid;
  place-items: center;
  gap: 6px;
  min-height: 62px;
  color: var(--color-muted);
  font-size: 12px;
}

.tree-level__cards {
  display: flex;
  position: relative;
  z-index: 1;
  flex-wrap: wrap;
  justify-content: center;
  gap: 6px;
  min-width: 0;
}

.tree-level--compact .tree-level__cards {
  max-height: 260px;
  overflow-y: auto;
  padding-right: 2px;
}

.tree-level--featured .tree-level__cards {
  gap: 8px;
}

.match {
  display: grid;
  border: 1px solid var(--color-border);
  background: var(--color-bg);
  color: inherit;
  text-decoration: none;
}

.match--featured {
  width: 220px;
  gap: 6px;
  min-height: 86px;
  padding: 8px;
  border-radius: 7px;
}

.match--compact {
  width: 136px;
  gap: 4px;
  padding: 5px;
  border-radius: 6px;
}

.match:hover {
  background: var(--color-card-hover);
}

.match__meta {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  color: var(--color-muted);
  font-size: 10px;
}

.match__meta em {
  font-style: normal;
  font-weight: 800;
}

.match-compact__meta {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 6px;
  min-width: 0;
  color: var(--color-muted);
  font-size: 9px;
  line-height: 1.05;
}

.match-compact__meta b,
.match-compact__meta em {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.match-compact__meta em {
  color: var(--color-fg);
  font-style: normal;
  font-weight: 900;
}

.match-compact__teams {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  align-items: center;
  gap: 4px;
  min-width: 0;
}

.match-compact__teams strong {
  min-width: 0;
  overflow: hidden;
  color: var(--color-muted);
  font-size: 10px;
  line-height: 1.1;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.match-compact__teams strong:last-child {
  text-align: right;
}

.match-compact__teams strong[data-winner='true'] {
  color: var(--color-fg);
  font-weight: 900;
}

.match-compact__teams span {
  color: color-mix(in srgb, var(--theme-primary, var(--color-fg)) 66%, var(--color-muted));
  font-size: 9px;
  font-weight: 900;
}

.team {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr);
  align-items: center;
  gap: 7px;
  min-width: 0;
  color: var(--color-muted);
}

.team__logo {
  display: inline-grid;
  place-items: center;
  width: 18px;
  height: 18px;
  border: 1px solid rgb(17 24 39 / 0.14);
  border-radius: 999px;
  background: #ffffff;
  overflow: hidden;
}

.team__logo img {
  display: block;
  width: 82%;
  height: 82%;
  object-fit: contain;
}

.team__logo b {
  color: #111827;
  font-size: 9px;
  line-height: 1;
}

.team strong {
  min-width: 0;
  overflow: hidden;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.team[data-winner='true'] {
  color: var(--color-fg);
}

.team[data-winner='true'] strong {
  font-weight: 900;
}
</style>
