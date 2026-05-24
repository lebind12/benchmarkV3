<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Search, Shield } from 'lucide-vue-next'
import { generalApi, type LeagueListItem, type TeamListItem } from '@/lib/api/general'
import { leagueName, teamName } from '@/lib/displayNames'

const leagues = ref<LeagueListItem[]>([])
const teams = ref<TeamListItem[]>([])
const selectedLeague = ref('39')
const query = ref('')
const status = ref<'idle' | 'loading' | 'ok' | 'error'>('idle')
const error = ref<string | null>(null)

const selectedLeagueId = computed(() =>
  selectedLeague.value ? Number(selectedLeague.value) : null,
)

async function loadLeagues() {
  leagues.value = (await generalApi.leagues()).items
}

async function loadTeams() {
  status.value = 'loading'
  error.value = null
  try {
    teams.value = (
      await generalApi.teams({
        leagueId: selectedLeagueId.value,
        query: query.value.trim() || null,
        limit: 240,
      })
    ).items
    status.value = 'ok'
  } catch (err) {
    teams.value = []
    error.value = (err as Error).message
    status.value = 'error'
  }
}

onMounted(async () => {
  await loadLeagues()
  await loadTeams()
})

watch(selectedLeague, () => {
  void loadTeams()
})
</script>

<template>
  <main class="page app-container">
    <header class="page__header">
      <div>
        <p class="eyebrow">Clubs</p>
        <h1>팀</h1>
      </div>
      <form class="search" @submit.prevent="loadTeams">
        <Search :size="16" />
        <input v-model="query" type="search" placeholder="팀명 검색" />
        <button type="submit">검색</button>
      </form>
    </header>

    <section class="toolbar" aria-label="팀 필터">
      <label>
        <span>리그</span>
        <select v-model="selectedLeague">
          <option value="">전체</option>
          <option v-for="league in leagues" :key="league.external_id" :value="String(league.external_id)">
            {{ leagueName(league) }}
          </option>
        </select>
      </label>
    </section>

    <div v-if="status === 'loading'" class="state">팀 데이터를 불러오는 중입니다.</div>
    <div v-else-if="status === 'error'" class="state state--error">{{ error }}</div>
    <div v-else-if="teams.length === 0" class="state">조건에 맞는 팀이 없습니다.</div>
    <section v-else class="team-grid">
      <router-link
        v-for="item in teams"
        :key="`${item.team.external_id}-${item.league.external_id}`"
        class="team-card"
        :to="{ name: 'team-detail', params: { slug: item.team.slug } }"
      >
        <img v-if="item.team.logo_url" :src="item.team.logo_url" alt="" />
        <div v-else class="team-card__fallback"><Shield :size="24" /></div>
        <div>
          <strong>{{ teamName(item.team) }}</strong>
          <span>{{ leagueName(item.league) }}</span>
        </div>
        <dl>
          <div>
            <dt>국가</dt>
            <dd>{{ item.country ?? '-' }}</dd>
          </div>
          <div>
            <dt>순위</dt>
            <dd>{{ item.rank ?? '-' }}</dd>
          </div>
          <div>
            <dt>승점</dt>
            <dd>{{ item.points ?? '-' }}</dd>
          </div>
        </dl>
      </router-link>
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
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
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
.search {
  display: flex;
  align-items: center;
  gap: 8px;
  width: min(360px, 100%);
  height: 38px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  padding-inline: 10px 4px;
}
.search input {
  flex: 1;
  min-width: 0;
  border: 0;
  background: transparent;
  color: var(--color-fg);
}
.search button {
  height: 30px;
  border: 1px solid var(--color-border);
  border-radius: 5px;
  background: var(--color-card);
  cursor: pointer;
}
.toolbar {
  margin-bottom: 18px;
}
label {
  display: grid;
  gap: 6px;
  width: 240px;
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
.team-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px;
}
.team-card {
  display: grid;
  grid-template-columns: 52px 1fr;
  gap: 12px;
  min-height: 148px;
  padding: 14px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-card);
  text-decoration: none;
}
.team-card:hover {
  background: var(--color-card-hover);
}
.team-card img,
.team-card__fallback {
  width: 52px;
  height: 52px;
  object-fit: contain;
}
.team-card__fallback {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-muted);
}
.team-card strong {
  display: block;
  margin-bottom: 4px;
  font-size: 15px;
}
.team-card span {
  color: var(--color-muted);
  font-size: 12px;
}
dl {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  margin: 8px 0 0;
}
dt {
  color: var(--color-muted);
  font-size: 11px;
}
dd {
  margin: 2px 0 0;
  font-weight: 600;
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
