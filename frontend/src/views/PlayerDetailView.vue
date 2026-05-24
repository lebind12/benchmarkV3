<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Activity, Ruler } from 'lucide-vue-next'
import { generalApi, type PlayerDetailPayload } from '@/lib/api/general'
import { leagueName, playerName, teamName } from '@/lib/displayNames'

const route = useRoute()
const payload = ref<PlayerDetailPayload | null>(null)
const status = ref<'idle' | 'loading' | 'ok' | 'error'>('idle')
const error = ref<string | null>(null)

async function loadPlayer(slug: string) {
  status.value = 'loading'
  error.value = null
  try {
    payload.value = await generalApi.player(slug)
    status.value = 'ok'
  } catch (err) {
    payload.value = null
    error.value = (err as Error).message
    status.value = 'error'
  }
}

onMounted(() => {
  void loadPlayer(String(route.params.slug))
})

watch(
  () => route.params.slug,
  (slug) => {
    if (slug) void loadPlayer(String(slug))
  },
)
</script>

<template>
  <main class="page app-container">
    <div v-if="status === 'loading'" class="state">선수 정보를 불러오는 중입니다.</div>
    <div v-else-if="status === 'error'" class="state state--error">{{ error }}</div>
    <template v-else-if="payload">
      <header class="hero">
        <img v-if="payload.player.photo_url" :src="payload.player.photo_url" alt="" />
        <div class="photo-fallback" v-else>{{ playerName(payload.player).slice(0, 1) }}</div>
        <div>
          <p class="eyebrow">Player</p>
          <h1>{{ playerName(payload.player) }}</h1>
          <p>
            <router-link
              v-if="payload.current_team"
              :to="{ name: 'team-detail', params: { slug: payload.current_team.slug } }"
            >
              {{ teamName(payload.current_team) }}
            </router-link>
            <span v-else>소속팀 미등록</span>
            · {{ payload.profile.nationality ?? '-' }}
          </p>
        </div>
      </header>

      <section class="summary-grid">
        <article class="summary">
          <Activity :size="18" />
          <div>
            <span>프로필</span>
            <strong>{{ payload.profile.age ?? '-' }}세</strong>
            <small>{{ payload.profile.birth_date ?? '-' }}</small>
          </div>
        </article>
        <article class="summary">
          <Ruler :size="18" />
          <div>
            <span>신체</span>
            <strong>{{ payload.profile.height_cm ?? '-' }}cm</strong>
            <small>{{ payload.profile.weight_kg ?? '-' }}kg</small>
          </div>
        </article>
      </section>

      <section class="panel">
        <h2>시즌 기록</h2>
        <table>
          <thead>
            <tr>
              <th>시즌</th>
              <th>리그</th>
              <th>팀</th>
              <th>포지션</th>
              <th>출전</th>
              <th>분</th>
              <th>G</th>
              <th>A</th>
              <th>평점</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in payload.season_stats" :key="`${row.season}-${row.league.external_id}-${row.team.external_id}`">
              <td>{{ row.season }}</td>
              <td>{{ leagueName(row.league) }}</td>
              <td>
                <router-link :to="{ name: 'team-detail', params: { slug: row.team.slug } }">
                  {{ teamName(row.team) }}
                </router-link>
              </td>
              <td>{{ row.position ?? '-' }}</td>
              <td>{{ row.appearances ?? '-' }}</td>
              <td>{{ row.minutes ?? '-' }}</td>
              <td>{{ row.goals ?? 0 }}</td>
              <td>{{ row.assists ?? 0 }}</td>
              <td>{{ row.rating?.toFixed(2) ?? '-' }}</td>
            </tr>
          </tbody>
        </table>
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
.hero img,
.photo-fallback {
  width: 80px;
  height: 80px;
  border-radius: 50%;
}
.hero img {
  object-fit: cover;
}
.photo-fallback {
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-card);
  border: 1px solid var(--color-border);
  font-size: 28px;
  font-weight: 700;
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
a {
  text-decoration: none;
}
.summary-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
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
.panel {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-card);
  overflow: hidden;
}
h2 {
  margin: 0;
  padding: 14px;
  border-bottom: 1px solid var(--color-border);
  font-size: 17px;
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
@media (max-width: 760px) {
  .summary-grid {
    grid-template-columns: 1fr;
  }
}
</style>
