<script setup lang="ts">
import type { FixtureSummary } from '@/types/home'
import { kstTime } from '@/lib/format/datetime'
import LeagueMark from '@/components/common/LeagueMark.vue'
import { LEAGUE_SHORT_KO, leagueLogoUrl } from '@/lib/league-colors'

const props = defineProps<{ fixture: FixtureSummary }>()
defineEmits<{ (e: 'open', id: number): void }>()

function leagueShort(): string {
  return props.fixture.league.short_name_ko ?? LEAGUE_SHORT_KO[props.fixture.league.slug] ?? props.fixture.league.name
}
function leagueLogo(): string | null {
  return props.fixture.league.logo_url ?? leagueLogoUrl(props.fixture.league.external_id)
}
function teamName(t: FixtureSummary['home']): string {
  return t.name_ko ?? t.name
}
function centerLabel(fx: FixtureSummary): string {
  if (fx.status_short === 'NS' || fx.status_short === 'PST') return kstTime(fx.kickoff_at)
  if (fx.goals_home != null && fx.goals_away != null) return `${fx.goals_home} - ${fx.goals_away}`
  return kstTime(fx.kickoff_at)
}
</script>
<template>
  <button
    type="button"
    class="fx"
    :data-league="fixture.league.slug"
    :data-testid="'fixture-card-' + fixture.external_id"
    @click="$emit('open', fixture.external_id)"
  >
    <span class="fx__badge" :data-testid="'fixture-badge-' + fixture.external_id">
      <LeagueMark
        :external-id="fixture.league.external_id"
        :slug="fixture.league.slug"
        :logo-url="leagueLogo()"
        :label="leagueShort()"
        size="xs"
      />
      <span class="fx__badge-text">{{ leagueShort() }}</span>
    </span>
    <span class="fx__team fx__home">{{ teamName(fixture.home) }}</span>
    <span class="fx__center">{{ centerLabel(fixture) }}</span>
    <span class="fx__team fx__away">{{ teamName(fixture.away) }}</span>
    <span class="fx__status">{{ fixture.status_short }}</span>
  </button>
</template>
<style scoped>
.fx {
  display: grid;
  grid-template-columns: minmax(86px, 100px) minmax(0, 1fr) 78px minmax(0, 1fr) 42px;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 10px 12px;
  margin-bottom: 8px;
  background: var(--color-card);
  border: 1px solid var(--color-border);
  border-left: 4px solid var(--theme-primary, var(--color-border));
  border-radius: 8px;
  cursor: pointer;
  color: inherit;
  text-align: left;
}
.fx:hover { background: var(--color-card-hover); }
.fx__badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
  padding: 2px 6px 2px 3px;
  border-radius: 4px;
  font-size: 11px;
  background: var(--theme-primary, var(--color-muted));
  color: var(--theme-on-primary, #fff);
}
.fx__badge-text {
  min-width: 0;
  overflow: hidden;
  line-height: 1;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.fx__team {
  min-width: 0;
  overflow: hidden;
  font-size: 13px;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.fx__home { text-align: right; }
.fx__away { text-align: left; }
.fx__center {
  min-width: 0;
  text-align: center;
  font-weight: 700;
  font-size: 14px;
  white-space: nowrap;
}
.fx__status {
  min-width: 0;
  font-size: 11px;
  color: var(--color-muted);
  text-align: right;
}
</style>
