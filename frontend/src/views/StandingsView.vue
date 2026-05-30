<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Trophy } from 'lucide-vue-next'
import { generalApi, type LeagueListItem, type StandingsPayload } from '@/lib/api/general'
import { leagueName, teamName } from '@/lib/displayNames'
import TournamentBracket from '@/components/standings/TournamentBracket.vue'

const DEFAULT_LEAGUE_ID = 39
const route = useRoute()
const leagues = ref<LeagueListItem[]>([])
const selectedLeague = ref(String(routeLeagueId()))
const payload = ref<StandingsPayload | null>(null)
const status = ref<'idle' | 'loading' | 'ok' | 'error'>('idle')
const error = ref<string | null>(null)
const activeTab = ref<'standings' | 'tournament'>(routeTab())

const selectedLeagueId = computed(() => Number(selectedLeague.value || 39))
const visibleGroups = computed(() => payload.value?.groups.filter((group) => group.rows.length > 0) ?? [])
const hasTournament = computed(() => payload.value?.tournament?.has_tournament === true)
const hasNamedGroups = computed(() =>
  visibleGroups.value.some((group) => /^Group [A-L]$/i.test(group.group_name ?? '')),
)
const standingsTabLabel = computed(() => (hasNamedGroups.value ? '조별리그' : '리그 페이즈'))
const availableTabs = computed(() => {
  if (!hasTournament.value) return []
  const tabs: { id: 'standings' | 'tournament'; label: string }[] = []
  if (visibleGroups.value.length > 0) {
    tabs.push({ id: 'standings', label: standingsTabLabel.value })
  }
  tabs.push({ id: 'tournament', label: '토너먼트' })
  return tabs
})
const showStandings = computed(() => availableTabs.value.length === 0 || activeTab.value === 'standings')

function firstQueryValue(value: unknown): string | null {
  if (Array.isArray(value)) return typeof value[0] === 'string' ? value[0] : null
  return typeof value === 'string' ? value : null
}

function routeLeagueId(): number {
  const raw = firstQueryValue(route.query.league_id)
  const parsed = Number(raw)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : DEFAULT_LEAGUE_ID
}

function routeTab(): 'standings' | 'tournament' {
  return firstQueryValue(route.query.tab) === 'tournament' ? 'tournament' : 'standings'
}

async function loadLeagues() {
  leagues.value = (await generalApi.leagues()).items
}

async function loadStandings() {
  status.value = 'loading'
  error.value = null
  try {
    payload.value = await generalApi.standings(selectedLeagueId.value)
    status.value = 'ok'
  } catch (err) {
    payload.value = null
    error.value = (err as Error).message
    status.value = 'error'
  }
}

function goalDiff(row: { goals_for: number; goals_against: number; goal_diff?: number | null }) {
  return row.goal_diff ?? row.goals_for - row.goals_against
}

onMounted(async () => {
  await loadLeagues()
  await loadStandings()
})

watch(selectedLeague, () => {
  void loadStandings()
})

watch(
  () => [route.query.league_id, route.query.tab],
  () => {
    const nextLeague = String(routeLeagueId())
    if (selectedLeague.value !== nextLeague) {
      selectedLeague.value = nextLeague
    }
    activeTab.value = routeTab()
  },
)

watch(availableTabs, (tabs) => {
  if (tabs.length === 0) {
    activeTab.value = 'standings'
    return
  }
  if (!tabs.some((tab) => tab.id === activeTab.value)) {
    activeTab.value = tabs[0].id
  }
})
</script>

<template>
  <main class="page app-container">
    <header class="page__header">
      <div>
        <p class="eyebrow">Table</p>
        <h1>리그 순위</h1>
      </div>
      <label class="league-picker">
        <span>리그</span>
        <select v-model="selectedLeague">
          <option v-for="league in leagues" :key="league.external_id" :value="String(league.external_id)">
            {{ leagueName(league) }}
          </option>
        </select>
      </label>
    </header>

    <div v-if="status === 'loading'" class="state">순위 데이터를 불러오는 중입니다.</div>
    <div v-else-if="status === 'error'" class="state state--error">{{ error }}</div>
    <div v-else-if="!payload" class="state">순위 데이터가 없습니다.</div>
    <section v-else class="standings">
      <div class="headline">
        <Trophy :size="18" />
        <strong>{{ leagueName(payload.league) }}</strong>
        <span>{{ payload.season }} 시즌</span>
      </div>

      <div v-if="availableTabs.length > 0" class="phase-tabs" role="tablist" aria-label="대회 단계">
        <button
          v-for="tab in availableTabs"
          :key="tab.id"
          type="button"
          role="tab"
          :aria-selected="activeTab === tab.id"
          :class="{ 'phase-tabs__tab--active': activeTab === tab.id }"
          class="phase-tabs__tab"
          @click="activeTab = tab.id"
        >
          {{ tab.label }}
        </button>
      </div>

      <div v-if="showStandings" class="standings-body">
        <div v-if="visibleGroups.length === 0" class="state">순위 데이터가 없습니다.</div>
        <template v-else>
          <article v-for="group in visibleGroups" :key="group.group_name ?? 'league'" class="table-wrap">
            <h2 v-if="group.group_name">{{ group.group_name }}</h2>
            <table>
              <thead>
                <tr>
                  <th>순위</th>
                  <th class="team-col">팀</th>
                  <th>경기</th>
                  <th>승</th>
                  <th>무</th>
                  <th>패</th>
                  <th>득실</th>
                  <th>승점</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in group.rows" :key="row.team.external_id">
                  <td>{{ row.rank }}</td>
                  <td class="team-cell">
                    <img v-if="row.team.logo_url" :src="row.team.logo_url" alt="" />
                    <router-link :to="{ name: 'team-detail', params: { slug: row.team.slug } }">
                      {{ teamName(row.team) }}
                    </router-link>
                  </td>
                  <td>{{ row.played }}</td>
                  <td>{{ row.win }}</td>
                  <td>{{ row.draw }}</td>
                  <td>{{ row.loss }}</td>
                  <td>{{ goalDiff(row) }}</td>
                  <td class="points">{{ row.points }}</td>
                </tr>
              </tbody>
            </table>
          </article>
        </template>
      </div>
      <TournamentBracket
        v-else-if="payload.tournament"
        :tournament="payload.tournament"
        :league-id="selectedLeagueId"
      />
    </section>
  </main>
</template>

<style scoped>
.page {
  height: calc(100vh - var(--header-height));
  overflow-y: auto;
  padding-block: 24px 48px;
}
.page__header {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
}
.eyebrow {
  margin: 0 0 4px;
  color: var(--color-muted);
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0;
}
h1 {
  margin: 0;
  font-size: 28px;
}
.league-picker {
  display: grid;
  gap: 6px;
  min-width: 220px;
  color: var(--color-muted);
  font-size: 12px;
}
select {
  height: 36px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: var(--color-bg);
  color: var(--color-fg);
  padding-inline: 10px;
}
.headline {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
  color: var(--color-muted);
}
.headline strong {
  color: var(--color-fg);
}
.standings {
  display: grid;
  gap: 18px;
}
.phase-tabs {
  display: inline-flex;
  width: fit-content;
  max-width: 100%;
  gap: 4px;
  padding: 4px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-card);
}
.phase-tabs__tab {
  min-width: 88px;
  height: 32px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--color-muted);
  cursor: pointer;
  font-size: 13px;
  font-weight: 800;
}
.phase-tabs__tab--active {
  background: var(--color-fg);
  color: var(--color-bg);
}
.standings-body {
  display: grid;
  gap: 18px;
}
.table-wrap {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  overflow: hidden;
  background: var(--color-card);
}
h2 {
  margin: 0;
  padding: 12px 14px;
  border-bottom: 1px solid var(--color-border);
  font-size: 15px;
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
th,
td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--color-border);
  text-align: center;
}
th {
  color: var(--color-muted);
  font-weight: 600;
}
tr:last-child td {
  border-bottom: 0;
}
.team-col,
.team-cell {
  text-align: left;
}
.team-cell {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 600;
}
.team-cell img {
  width: 24px;
  height: 24px;
  object-fit: contain;
}
.team-cell a {
  text-decoration: none;
}
.points {
  font-weight: 700;
}
.state {
  padding: 28px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-card);
  color: var(--color-muted);
}
.state--error {
  color: #b91c1c;
}
</style>
