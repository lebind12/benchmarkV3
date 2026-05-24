<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { hasHomeStandings, useHomeStore } from '@/stores/home'
import PanelScroll from '@/components/common/PanelScroll.vue'
import SkeletonCard from '@/components/common/SkeletonCard.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import { HOME_COMPETITION_OPTIONS, slugFromId } from '@/lib/league-colors'

const home = useHomeStore()
const router = useRouter()

const leagues = HOME_COMPETITION_OPTIONS
const slug = computed(() => slugFromId(home.standings.league_id))
const selectedLeague = computed(() => leagues.find((league) => league.id === home.standings.league_id))
const showStandingsTable = computed(() => hasHomeStandings(home.standings.league_id))
const groupedRows = computed(() => {
  const rows = home.standings.data.value ?? []
  const groups = new Map<string, typeof rows>()
  for (const row of rows) {
    const key = row.group_name ?? ''
    groups.set(key, [...(groups.get(key) ?? []), row])
  }
  return [...groups.entries()].map(([groupName, rows]) => ({
    groupName: groupName || null,
    rows,
  }))
})
const hasNamedGroups = computed(() =>
  groupedRows.value.some((group) => /^Group [A-L]$/i.test(group.groupName ?? '')),
)

function go(slug: string) { router.push(`/teams/${slug}`) }
function onChange(e: Event) {
  const v = Number((e.target as HTMLSelectElement).value)
  home.setStandingsLeague(v)
}
</script>
<template>
  <section class="block" :data-league="slug" data-testid="standings-block">
    <div class="block__head">
      <strong>순위</strong>
      <select
        class="block__select"
        :value="home.standings.league_id"
        data-testid="standings-league-select"
        @change="onChange"
      >
        <option v-for="l in leagues" :key="l.id" :value="l.id">{{ l.label }}</option>
      </select>
    </div>
    <div class="block__body">
      <PanelScroll class="standings-scroll">
        <div v-if="!showStandingsTable" class="cup-state" data-testid="standings-cup-state">
          <span class="cup-state__label">{{ selectedLeague?.label }}</span>
          <strong>순위표 없음</strong>
          <p>토너먼트 컵 대회는 리그식 승점 순위를 표시하지 않습니다.</p>
        </div>
        <template v-else-if="home.standings.data.status === 'loading'">
          <SkeletonCard v-for="i in 8" :key="i" :height="32" />
        </template>
        <ErrorState v-else-if="home.standings.data.status === 'error'" @retry="home.fetchStandings()" />
        <EmptyState
          v-else-if="!home.standings.data.value || home.standings.data.value.length === 0"
          message="현재 진행 중인 시즌 없음"
        />
        <div v-else-if="hasNamedGroups" class="grouped-standings">
          <section v-for="group in groupedRows" :key="group.groupName ?? 'league'" class="standing-group">
            <h3>{{ group.groupName }}</h3>
            <table class="tbl">
              <thead><tr><th>#</th><th>팀</th><th>점</th><th>승무패</th></tr></thead>
              <tbody>
                <tr
                  v-for="row in group.rows"
                  :key="row.team.external_id"
                  tabindex="0"
                  :data-testid="'standings-row-' + row.team.slug"
                  @click="go(row.team.slug)"
                  @keydown.enter="go(row.team.slug)"
                >
                  <td>{{ row.rank }}</td>
                  <td>{{ row.team.short_name_ko ?? row.team.name_ko ?? row.team.name }}</td>
                  <td>{{ row.points }}</td>
                  <td>{{ row.win }}-{{ row.draw }}-{{ row.loss }}</td>
                </tr>
              </tbody>
            </table>
          </section>
        </div>
        <table v-else class="tbl">
          <thead><tr><th>#</th><th>팀</th><th>점</th><th>승무패</th></tr></thead>
          <tbody>
            <tr
              v-for="row in home.standings.data.value"
              :key="row.team.external_id"
              tabindex="0"
              :data-testid="'standings-row-' + row.team.slug"
              @click="go(row.team.slug)"
              @keydown.enter="go(row.team.slug)"
            >
              <td>{{ row.rank }}</td>
              <td>{{ row.team.short_name_ko ?? row.team.name_ko ?? row.team.name }}</td>
              <td>{{ row.points }}</td>
              <td>{{ row.win }}-{{ row.draw }}-{{ row.loss }}</td>
            </tr>
          </tbody>
        </table>
      </PanelScroll>
    </div>
  </section>
</template>
<style scoped>
.block {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}
.block__head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  border-bottom: 1px solid var(--color-border);
  background: var(--theme-primary, transparent);
  color: var(--theme-on-primary, var(--color-fg));
}
.block__select {
  background: var(--color-bg);
  color: var(--color-fg);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  padding: 2px 6px;
}
.block__body {
  flex: 1 1 auto;
  min-height: 0;
  overflow: hidden;
  padding: 4px 8px;
  box-sizing: border-box;
}
.standings-scroll {
  height: 100%;
  min-height: 0;
  overflow: hidden;
}
.standings-scroll :deep(.panel-scroll) {
  height: 100%;
  max-height: 100%;
  overflow-y: auto;
  overflow-x: hidden;
}
.cup-state {
  display: grid;
  align-content: center;
  min-height: 100%;
  gap: 6px;
  padding: 18px 8px;
  color: var(--color-muted);
}
.cup-state__label {
  width: fit-content;
  border: 1px solid var(--color-border);
  border-radius: 999px;
  padding: 2px 8px;
  color: var(--color-fg);
  font-size: 11px;
}
.cup-state strong {
  color: var(--color-fg);
  font-size: 15px;
}
.cup-state p {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
}
.grouped-standings {
  display: grid;
  gap: 10px;
}
.standing-group {
  min-width: 0;
}
.standing-group h3 {
  margin: 4px 0 2px;
  color: var(--color-fg);
  font-size: 12px;
  font-weight: 800;
}
.tbl { width: 100%; border-collapse: collapse; font-size: 12px; }
.tbl th { text-align: left; color: var(--color-muted); font-weight: 500; padding: 4px 6px; position: sticky; top: 0; background: var(--color-bg); }
.tbl td { padding: 4px 6px; border-top: 1px solid var(--color-border); cursor: pointer; }
.tbl tr:hover td { background: var(--color-card-hover); }
</style>
