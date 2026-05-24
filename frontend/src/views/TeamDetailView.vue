<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Building2, Users } from 'lucide-vue-next'
import FixtureCard from '@/components/home/FixtureCard.vue'
import { generalApi, type TeamDetailPayload } from '@/lib/api/general'
import { leagueName, playerName, teamName } from '@/lib/displayNames'

const route = useRoute()
const router = useRouter()
const payload = ref<TeamDetailPayload | null>(null)
const status = ref<'idle' | 'loading' | 'ok' | 'error'>('idle')
const error = ref<string | null>(null)

async function loadTeam(slug: string) {
  status.value = 'loading'
  error.value = null
  try {
    payload.value = await generalApi.team(slug)
    status.value = 'ok'
  } catch (err) {
    payload.value = null
    error.value = (err as Error).message
    status.value = 'error'
  }
}

function openFixture(id: number) {
  void router.push({ name: 'fixture-detail', params: { externalId: id } })
}

onMounted(() => {
  void loadTeam(String(route.params.slug))
})

watch(
  () => route.params.slug,
  (slug) => {
    if (slug) void loadTeam(String(slug))
  },
)
</script>

<template>
  <main class="page app-container">
    <div v-if="status === 'loading'" class="state">팀 정보를 불러오는 중입니다.</div>
    <div v-else-if="status === 'error'" class="state state--error">{{ error }}</div>
    <template v-else-if="payload">
      <header class="hero">
        <img v-if="payload.team.logo_url" :src="payload.team.logo_url" alt="" />
        <div>
          <p class="eyebrow">Team</p>
          <h1>{{ teamName(payload.team) }}</h1>
          <p>{{ payload.country ?? '-' }} · {{ payload.founded ?? '-' }}</p>
        </div>
      </header>

      <section class="summary-grid">
        <article class="summary">
          <Building2 :size="18" />
          <div>
            <span>홈구장</span>
            <strong>{{ payload.venue?.name ?? '-' }}</strong>
            <small>{{ payload.venue?.city ?? '' }}</small>
          </div>
        </article>
        <article class="summary">
          <Users :size="18" />
          <div>
            <span>선수단</span>
            <strong>{{ payload.squad.length }}명</strong>
            <small>{{ payload.leagues.map((item) => leagueName(item.league)).join(', ') }}</small>
          </div>
        </article>
        <article class="summary">
          <Users :size="18" />
          <div>
            <span>감독</span>
            <strong>{{ payload.coach ? playerName(payload.coach.coach) : '-' }}</strong>
            <small>{{ payload.coach?.league ? leagueName(payload.coach.league) : '' }}</small>
          </div>
        </article>
      </section>

      <section class="columns">
        <article class="panel">
          <h2>최근/예정 경기</h2>
          <div v-if="payload.fixtures.length === 0" class="empty">경기 데이터가 없습니다.</div>
          <FixtureCard
            v-for="fixture in payload.fixtures"
            :key="fixture.external_id"
            :fixture="fixture"
            @open="openFixture"
          />
        </article>

        <article class="panel">
          <h2>스쿼드</h2>
          <table>
            <thead>
              <tr>
                <th class="player-col">선수</th>
                <th>포지션</th>
                <th>출전</th>
                <th>G</th>
                <th>A</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in payload.squad" :key="row.player.external_id">
                <td class="player-cell">
                  <img v-if="row.player.photo_url" :src="row.player.photo_url" alt="" />
                  <router-link :to="{ name: 'player-detail', params: { slug: row.player.slug } }">
                    {{ playerName(row.player) }}
                  </router-link>
                </td>
                <td>{{ row.position ?? '-' }}</td>
                <td>{{ row.appearances ?? '-' }}</td>
                <td>{{ row.goals ?? 0 }}</td>
                <td>{{ row.assists ?? 0 }}</td>
              </tr>
            </tbody>
          </table>
        </article>
      </section>
    </template>
  </main>
</template>

<style scoped>
.page {
  height: calc(100vh - var(--header-height));
  overflow-y: auto;
  padding-block: 24px 48px;
}
.hero {
  display: flex;
  align-items: center;
  gap: 18px;
  margin-bottom: 18px;
}
.hero img {
  width: 72px;
  height: 72px;
  object-fit: contain;
}
.eyebrow {
  margin: 0 0 4px;
  color: var(--color-muted);
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0;
}
h1 {
  margin: 0 0 6px;
  font-size: 30px;
}
.hero p:last-child {
  margin: 0;
  color: var(--color-muted);
}
.summary-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 18px;
}
.summary {
  display: flex;
  gap: 10px;
  padding: 14px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-card);
}
.summary span,
.summary small {
  display: block;
  color: var(--color-muted);
  font-size: 12px;
}
.summary strong {
  display: block;
  margin: 3px 0;
}
.columns {
  display: grid;
  grid-template-columns: minmax(320px, 0.9fr) minmax(420px, 1.1fr);
  gap: 18px;
  align-items: start;
}
.panel {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-bg);
  padding: 14px;
}
h2 {
  margin: 0 0 12px;
  font-size: 17px;
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
th,
td {
  padding: 9px 8px;
  border-bottom: 1px solid var(--color-border);
  text-align: center;
}
th {
  color: var(--color-muted);
  font-weight: 600;
}
.player-col,
.player-cell {
  text-align: left;
}
.player-cell {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}
.player-cell img {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  object-fit: cover;
}
.player-cell a {
  text-decoration: none;
}
.empty,
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
@media (max-width: 900px) {
  .summary-grid,
  .columns {
    grid-template-columns: 1fr;
  }
}
</style>
