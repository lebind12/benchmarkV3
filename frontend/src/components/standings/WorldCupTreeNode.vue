<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import type { RouteLocationRaw } from 'vue-router'
import type { TeamRef } from '@/types/home'
import type { TournamentFixture } from '@/lib/api/general'
import type { WorldCupSlot, WorldCupTreeMatch } from '@/lib/world-cup-2026-bracket'
import { teamName } from '@/lib/displayNames'

defineOptions({ name: 'WorldCupTreeNode' })

const props = withDefaults(
  defineProps<{
    node: WorldCupTreeMatch
    fixturesByMatchNo: Map<number, TournamentFixture>
    depth?: number
  }>(),
  {
    depth: 0,
  },
)

const fixture = computed(() => props.fixturesByMatchNo.get(props.node.matchNo) ?? null)
const fixtureLink = computed<RouteLocationRaw | undefined>(() =>
  fixture.value
    ? { name: 'fixture-detail', params: { externalId: fixture.value.external_id } }
    : undefined,
)
const isDetailed = computed(() => props.node.roundLabel === '결승' || props.node.roundLabel === '4강' || props.node.roundLabel === '3위 결정전')
const visibleChildren = computed(() => props.node.children.filter((child) => child.roundLabel !== '32강'))

function displayTeam(team: TeamRef | null | undefined): string {
  return team ? teamName(team) : 'TBD'
}

function teamInitial(team: TeamRef | null | undefined): string {
  return displayTeam(team).slice(0, 1)
}

function sideTeam(side: 'home' | 'away'): TeamRef | null | undefined {
  return fixture.value?.[side]
}

function sideWinner(side: 'home' | 'away'): boolean {
  return side === 'home' ? fixture.value?.home_winner === true : fixture.value?.away_winner === true
}

function sourceLabel(slot: WorldCupSlot): string {
  return slot.label
}

function compactTeam(side: 'home' | 'away'): string {
  return displayTeam(sideTeam(side))
}

function scoreText(fixtureValue: TournamentFixture | null): string {
  if (!fixtureValue) return 'TBD'
  if (fixtureValue.goals_home == null || fixtureValue.goals_away == null) {
    return kickoffLabel(fixtureValue.kickoff_at) ?? fixtureValue.status_short
  }

  const regular = `${fixtureValue.goals_home}-${fixtureValue.goals_away}`
  if (fixtureValue.score_pen_home != null && fixtureValue.score_pen_away != null) {
    return `${regular} (PK ${fixtureValue.score_pen_home}-${fixtureValue.score_pen_away})`
  }
  return regular
}

function kickoffLabel(value: string | null): string | null {
  if (!value) return null
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
  <article class="wc-node" :data-depth="depth" :data-detail="isDetailed">
    <component
      :is="fixture ? RouterLink : 'div'"
      class="wc-match"
      :class="{
        'wc-match--link': fixture,
        'wc-match--compact': !isDetailed,
        'wc-match--detailed': isDetailed,
      }"
      :to="fixtureLink"
    >
      <template v-if="isDetailed">
        <span class="wc-match__meta">
          <b>M{{ node.matchNo }}</b>
          <em>{{ node.roundLabel }}</em>
        </span>

        <span class="wc-team" :data-winner="sideWinner('home')">
          <span class="wc-team__main">
            <span class="wc-team__logo">
              <img v-if="sideTeam('home')?.logo_url" :src="sideTeam('home')?.logo_url ?? ''" alt="" loading="lazy" />
              <b v-else>{{ teamInitial(sideTeam('home')) }}</b>
            </span>
            <strong>{{ displayTeam(sideTeam('home')) }}</strong>
          </span>
          <small>{{ sourceLabel(node.home) }}</small>
        </span>

        <span class="wc-team" :data-winner="sideWinner('away')">
          <span class="wc-team__main">
            <span class="wc-team__logo">
              <img v-if="sideTeam('away')?.logo_url" :src="sideTeam('away')?.logo_url ?? ''" alt="" loading="lazy" />
              <b v-else>{{ teamInitial(sideTeam('away')) }}</b>
            </span>
            <strong>{{ displayTeam(sideTeam('away')) }}</strong>
          </span>
          <small>{{ sourceLabel(node.away) }}</small>
        </span>

        <span class="wc-match__status">{{ scoreText(fixture) }}</span>
      </template>

      <template v-else>
        <span class="wc-compact__head">
          <b>M{{ node.matchNo }}</b>
          <em>{{ node.roundLabel }}</em>
        </span>
        <span class="wc-compact__team" :data-winner="sideWinner('home')" :title="`${compactTeam('home')} · ${sourceLabel(node.home)}`">
          <strong>{{ compactTeam('home') }}</strong>
          <small>{{ sourceLabel(node.home) }}</small>
        </span>
        <span class="wc-compact__team" :data-winner="sideWinner('away')" :title="`${compactTeam('away')} · ${sourceLabel(node.away)}`">
          <strong>{{ compactTeam('away') }}</strong>
          <small>{{ sourceLabel(node.away) }}</small>
        </span>
      </template>
    </component>

    <span v-if="visibleChildren.length > 0" class="wc-node__stem" aria-hidden="true" />
    <div v-if="visibleChildren.length > 0" class="wc-node__children">
      <WorldCupTreeNode
        v-for="child in visibleChildren"
        :key="child.matchNo"
        class="wc-node__child"
        :node="child"
        :fixtures-by-match-no="fixturesByMatchNo"
        :depth="depth + 1"
      />
    </div>
  </article>
</template>

<style scoped>
.wc-node {
  --wc-card-w: 86px;
  --wc-detail-w: 176px;
  display: flex;
  position: relative;
  flex: 0 0 auto;
  flex-direction: column;
  align-items: center;
}

.wc-node[data-detail='true'] {
  --wc-card-w: var(--wc-detail-w);
}

.wc-match {
  display: grid;
  width: var(--wc-card-w);
  border: 1px solid color-mix(in srgb, var(--theme-primary, #0f766e) 22%, var(--color-border));
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--theme-primary, #0f766e) 8%, transparent), transparent 56%),
    var(--color-card);
  color: inherit;
  text-decoration: none;
}

.wc-match--detailed {
  gap: 7px;
  min-height: 106px;
  padding: 9px;
  border-radius: 8px;
  box-shadow: 0 8px 18px rgb(15 23 42 / 0.08);
}

.wc-match--compact {
  gap: 4px;
  min-height: 58px;
  padding: 5px;
  border-radius: 7px;
  background: var(--color-card);
}

.wc-match--link:hover {
  border-color: color-mix(in srgb, var(--theme-primary, #0f766e) 44%, var(--color-border));
  background: var(--color-card-hover);
}

.wc-match__meta,
.wc-match__status {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-width: 0;
  color: var(--color-muted);
  font-size: 10px;
}

.wc-match__meta b {
  color: var(--color-fg);
  font-variant-numeric: tabular-nums;
}

.wc-match__meta em,
.wc-match__status {
  overflow: hidden;
  font-style: normal;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.wc-team {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  min-width: 0;
  color: var(--color-muted);
}

.wc-team__main {
  display: grid;
  grid-template-columns: 20px minmax(0, 1fr);
  align-items: center;
  gap: 7px;
  min-width: 0;
}

.wc-team__logo {
  display: inline-grid;
  place-items: center;
  width: 20px;
  height: 20px;
  border: 1px solid rgb(17 24 39 / 0.14);
  border-radius: 999px;
  background: #ffffff;
  overflow: hidden;
}

.wc-team__logo img {
  display: block;
  width: 82%;
  height: 82%;
  object-fit: contain;
}

.wc-team__logo b {
  color: #111827;
  font-size: 9px;
  line-height: 1;
}

.wc-team strong {
  min-width: 0;
  overflow: hidden;
  font-size: 12px;
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.wc-team small {
  max-width: 62px;
  overflow: hidden;
  color: color-mix(in srgb, var(--theme-primary, #0f766e) 72%, var(--color-muted));
  font-size: 10px;
  font-weight: 900;
  line-height: 1;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.wc-team[data-winner='true'] {
  color: var(--color-fg);
}

.wc-team[data-winner='true'] strong {
  font-weight: 900;
}

.wc-compact__head {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  gap: 5px;
  min-width: 0;
  color: var(--color-muted);
  font-size: 8.5px;
  line-height: 1;
}

.wc-compact__head b {
  color: var(--color-fg);
  font-variant-numeric: tabular-nums;
}

.wc-compact__head em {
  overflow: hidden;
  font-style: normal;
  font-weight: 900;
  text-align: right;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.wc-compact__team {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 1px;
  min-width: 0;
  padding: 2px 3px;
  border-radius: 5px;
  background: color-mix(in srgb, var(--theme-primary, #0f766e) 6%, transparent);
}

.wc-compact__team strong,
.wc-compact__team small {
  min-width: 0;
  overflow: hidden;
  line-height: 1.05;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.wc-compact__team strong {
  color: var(--color-muted);
  font-size: 9px;
  font-weight: 900;
}

.wc-compact__team small {
  color: color-mix(in srgb, var(--theme-primary, #0f766e) 72%, var(--color-muted));
  font-size: 8.5px;
  font-weight: 900;
}

.wc-compact__team[data-winner='true'] strong {
  color: var(--color-fg);
}

.wc-node__stem {
  width: 1px;
  height: 12px;
  background: color-mix(in srgb, var(--theme-primary, #0f766e) 42%, var(--color-border));
}

.wc-node__children {
  display: flex;
  position: relative;
  align-items: flex-start;
  gap: 6px;
  padding-top: 12px;
}

.wc-node[data-depth='0'] > .wc-node__children {
  gap: 12px;
}

.wc-node[data-depth='1'] > .wc-node__children {
  gap: 8px;
}

.wc-node__children::before {
  content: '';
  position: absolute;
  top: 0;
  right: calc(var(--wc-card-w) / 2);
  left: calc(var(--wc-card-w) / 2);
  height: 1px;
  background: color-mix(in srgb, var(--theme-primary, #0f766e) 42%, var(--color-border));
}

.wc-node__child::before {
  content: '';
  position: absolute;
  top: -12px;
  left: 50%;
  width: 1px;
  height: 12px;
  background: color-mix(in srgb, var(--theme-primary, #0f766e) 42%, var(--color-border));
}

@media (max-width: 720px) {
  .wc-node {
    --wc-card-w: 78px;
    --wc-detail-w: 162px;
  }

  .wc-node__children {
    gap: 4px;
  }
}
</style>
