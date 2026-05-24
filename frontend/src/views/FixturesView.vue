<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { CalendarDays, RotateCw } from 'lucide-vue-next'
import FixtureCard from '@/components/home/FixtureCard.vue'
import { generalApi, type LeagueListItem } from '@/lib/api/general'
import type { FixtureSummary, Period } from '@/types/home'
import { leagueName } from '@/lib/displayNames'

const router = useRouter()
const leagues = ref<LeagueListItem[]>([])
const fixtures = ref<FixtureSummary[]>([])
const selectedLeague = ref('')
const period = ref<Period>('week')
const date = ref('')
const status = ref<'idle' | 'loading' | 'ok' | 'error'>('idle')
const error = ref<string | null>(null)

const selectedLeagueId = computed(() =>
  selectedLeague.value ? Number(selectedLeague.value) : null,
)

async function loadLeagues() {
  leagues.value = (await generalApi.leagues()).items
}

async function loadFixtures() {
  status.value = 'loading'
  error.value = null
  try {
    fixtures.value = (
      await generalApi.fixtures({
        leagueId: selectedLeagueId.value,
        period: period.value,
        date: date.value || null,
        limit: 150,
      })
    ).items
    status.value = 'ok'
  } catch (err) {
    fixtures.value = []
    error.value = (err as Error).message
    status.value = 'error'
  }
}

function openFixture(id: number) {
  void router.push({ name: 'fixture-detail', params: { externalId: id } })
}

onMounted(async () => {
  await loadLeagues()
  await loadFixtures()
})

watch([selectedLeague, period], () => {
  void loadFixtures()
})
</script>

<template>
  <main class="page app-container">
    <header class="page__header">
      <div>
        <p class="eyebrow">Matches</p>
        <h1>경기 일정</h1>
      </div>
      <button type="button" class="icon-btn" aria-label="새로고침" @click="loadFixtures">
        <RotateCw :size="17" />
      </button>
    </header>

    <section class="toolbar" aria-label="경기 필터">
      <label>
        <span>리그</span>
        <select v-model="selectedLeague">
          <option value="">전체</option>
          <option v-for="league in leagues" :key="league.external_id" :value="String(league.external_id)">
            {{ leagueName(league) }}
          </option>
        </select>
      </label>
      <div class="segmented" role="group" aria-label="기간">
        <button type="button" :class="{ active: period === 'day' }" @click="period = 'day'">일간</button>
        <button type="button" :class="{ active: period === 'week' }" @click="period = 'week'">주간</button>
        <button type="button" :class="{ active: period === 'month' }" @click="period = 'month'">월간</button>
      </div>
      <label>
        <span>기준일</span>
        <div class="field-with-icon">
          <CalendarDays :size="16" />
          <input v-model="date" type="date" @change="loadFixtures" />
        </div>
      </label>
    </section>

    <section class="content">
      <div v-if="status === 'loading'" class="state">경기 데이터를 불러오는 중입니다.</div>
      <div v-else-if="status === 'error'" class="state state--error">{{ error }}</div>
      <div v-else-if="fixtures.length === 0" class="state">조건에 맞는 경기가 없습니다.</div>
      <div v-else class="fixture-list">
        <FixtureCard
          v-for="fixture in fixtures"
          :key="fixture.external_id"
          :fixture="fixture"
          @open="openFixture"
        />
      </div>
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
.icon-btn {
  width: 36px;
  height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: var(--color-card);
  cursor: pointer;
}
.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: end;
  gap: 12px;
  margin-bottom: 18px;
}
label {
  display: grid;
  gap: 6px;
  min-width: 180px;
  color: var(--color-muted);
  font-size: 12px;
}
select,
input {
  height: 36px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: var(--color-bg);
  color: var(--color-fg);
  padding: 0 10px;
}
.field-with-icon {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 36px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  padding-inline: 10px;
}
.field-with-icon input {
  border: 0;
  padding: 0;
  height: 32px;
}
.segmented {
  display: inline-flex;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  overflow: hidden;
}
.segmented button {
  height: 36px;
  padding: 0 14px;
  border: 0;
  border-right: 1px solid var(--color-border);
  background: var(--color-bg);
  cursor: pointer;
}
.segmented button:last-child {
  border-right: 0;
}
.segmented .active {
  background: var(--color-fg);
  color: var(--color-bg);
}
.content {
  max-width: 980px;
}
.fixture-list {
  display: grid;
  gap: 8px;
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
