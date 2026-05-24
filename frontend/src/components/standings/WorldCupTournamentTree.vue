<script setup lang="ts">
import { computed } from 'vue'
import { Medal, Trophy } from 'lucide-vue-next'
import type { TournamentFixture, TournamentPayload } from '@/lib/api/general'
import { teamName } from '@/lib/displayNames'
import {
  WORLD_CUP_2026_FINAL_MATCH_NO,
  WORLD_CUP_2026_THIRD_PLACE_MATCH,
  WORLD_CUP_2026_TREE,
} from '@/lib/world-cup-2026-bracket'
import WorldCupTreeNode from '@/components/standings/WorldCupTreeNode.vue'

const props = defineProps<{
  tournament: TournamentPayload
}>()

const fixturesByMatchNo = computed(() => {
  const pairs = props.tournament.rounds.flatMap((round) =>
    round.fixtures
      .filter((fixture) => fixture.match_no != null)
      .map((fixture) => [fixture.match_no as number, fixture] as const),
  )
  return new Map<number, TournamentFixture>(pairs)
})

const finalFixture = computed(() => fixturesByMatchNo.value.get(WORLD_CUP_2026_FINAL_MATCH_NO) ?? null)
const registeredFixtureCount = computed(() =>
  [...fixturesByMatchNo.value.keys()].filter((matchNo) => matchNo >= 89 && matchNo <= 104).length,
)

function championName(fixture: TournamentFixture | null): string {
  if (!fixture) return 'TBD'
  if (fixture.home_winner === true && fixture.home) return teamName(fixture.home)
  if (fixture.away_winner === true && fixture.away) return teamName(fixture.away)
  return 'TBD'
}
</script>

<template>
  <section class="world-cup" data-testid="world-cup-tournament-tree">
    <header class="world-cup__header">
      <div class="world-cup__trophy" aria-hidden="true">
        <Trophy :size="28" stroke-width="2.4" />
      </div>
      <div class="world-cup__title">
        <span>2026 FIFA World Cup</span>
        <h2>우승</h2>
      </div>
      <strong class="world-cup__champion">{{ championName(finalFixture) }}</strong>
      <small>{{ registeredFixtureCount }} / 16</small>
    </header>

    <div class="world-cup__scroll">
      <div class="world-cup__canvas">
        <span class="world-cup__stem" aria-hidden="true" />
        <WorldCupTreeNode :node="WORLD_CUP_2026_TREE" :fixtures-by-match-no="fixturesByMatchNo" />
      </div>
    </div>

    <aside class="world-cup__bronze">
      <span class="world-cup__bronze-icon" aria-hidden="true">
        <Medal :size="16" />
      </span>
      <strong>3위 결정전</strong>
      <WorldCupTreeNode
        class="world-cup__bronze-match"
        :node="WORLD_CUP_2026_THIRD_PLACE_MATCH"
        :fixtures-by-match-no="fixturesByMatchNo"
      />
    </aside>
  </section>
</template>

<style scoped>
.world-cup {
  display: grid;
  gap: 16px;
}

.world-cup__header {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) minmax(110px, auto) auto;
  align-items: center;
  gap: 12px;
  padding: 14px;
  border: 1px solid color-mix(in srgb, #d5a11e 34%, var(--color-border));
  border-radius: 8px;
  background:
    linear-gradient(135deg, rgb(213 161 30 / 0.16), transparent 38%),
    linear-gradient(180deg, color-mix(in srgb, var(--theme-primary, #0f766e) 8%, transparent), transparent),
    var(--color-card);
}

.world-cup__trophy {
  display: inline-grid;
  place-items: center;
  width: 48px;
  height: 48px;
  border: 1px solid rgb(213 161 30 / 0.42);
  border-radius: 999px;
  background: #ffffff;
  color: #b7791f;
  box-shadow: inset 0 0 0 6px rgb(213 161 30 / 0.12);
}

.world-cup__title {
  min-width: 0;
}

.world-cup__title span {
  color: var(--color-muted);
  font-size: 11px;
  font-weight: 900;
  text-transform: uppercase;
}

.world-cup__title h2 {
  margin: 2px 0 0;
  font-size: 24px;
}

.world-cup__champion {
  min-width: 0;
  overflow: hidden;
  font-size: 20px;
  text-align: right;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.world-cup__header small {
  display: inline-grid;
  place-items: center;
  min-width: 46px;
  height: 28px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--theme-primary, #0f766e) 14%, var(--color-bg));
  color: var(--color-muted);
  font-size: 11px;
  font-weight: 900;
  font-variant-numeric: tabular-nums;
}

.world-cup__scroll {
  overflow-x: auto;
  padding: 6px 2px 14px;
}

.world-cup__canvas {
  display: flex;
  width: max-content;
  min-width: 100%;
  flex-direction: column;
  align-items: center;
}

.world-cup__stem {
  width: 1px;
  height: 18px;
  background: color-mix(in srgb, var(--theme-primary, #0f766e) 42%, var(--color-border));
}

.world-cup__bronze {
  display: grid;
  grid-template-columns: auto 120px minmax(0, auto);
  align-items: start;
  justify-content: start;
  gap: 10px;
  padding: 12px;
  border: 1px dashed color-mix(in srgb, #d5a11e 36%, var(--color-border));
  border-radius: 8px;
  background: color-mix(in srgb, #d5a11e 7%, var(--color-card));
}

.world-cup__bronze-icon {
  display: inline-grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 999px;
  background: #ffffff;
  color: #b7791f;
}

.world-cup__bronze strong {
  padding-top: 5px;
  font-size: 13px;
}

.world-cup__bronze-match {
  align-items: start;
}

@media (max-width: 720px) {
  .world-cup__header {
    grid-template-columns: auto minmax(0, 1fr);
  }

  .world-cup__champion {
    grid-column: 1 / -1;
    text-align: left;
  }

  .world-cup__header small {
    grid-column: 1 / -1;
    width: fit-content;
  }

  .world-cup__bronze {
    grid-template-columns: auto minmax(0, 1fr);
  }

  .world-cup__bronze-match {
    grid-column: 1 / -1;
  }
}
</style>
