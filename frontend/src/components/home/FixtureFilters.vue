<script setup lang="ts">
import { useHomeStore } from '@/stores/home'
import LeagueMark from '@/components/common/LeagueMark.vue'
import { HOME_LEAGUE_TABS } from '@/lib/league-colors'
import type { Period } from '@/types/home'

const home = useHomeStore()

const periodToggles: { v: Period; label: string }[] = [
  { v: 'month', label: '월' },
  { v: 'week', label: '주' },
  { v: 'day', label: '일' },
]
</script>
<template>
  <div class="filters">
    <div class="filters__row" role="tablist" aria-label="리그 필터">
      <button
        v-for="t in HOME_LEAGUE_TABS"
        :key="t.label"
        type="button"
        role="tab"
        :aria-selected="home.fixtures.filter.league_id === t.id"
        :data-league="t.slug || undefined"
        :data-testid="'league-tab-' + (t.id ?? 'all')"
        :class="['tab', { 'tab--active': home.fixtures.filter.league_id === t.id }]"
        @click="home.setLeagueFilter(t.id)"
      >
        <LeagueMark
          v-if="t.id !== null"
          :external-id="t.id"
          :slug="t.slug"
          :logo-url="t.logoUrl"
          :label="t.label"
          size="sm"
        />
        <span class="tab__label">{{ t.label }}</span>
      </button>
    </div>
    <div class="filters__row filters__row--date" aria-label="날짜 선택">
      <button
        type="button"
        class="date-nav"
        aria-label="전날"
        data-testid="date-prev"
        @click="home.shiftFixtureDate(-1)"
      >◀</button>
      <input
        type="date"
        class="date-input"
        data-testid="date-input"
        :value="home.fixtures.filter.date"
        @change="(e) => home.setFixtureDate((e.target as HTMLInputElement).value)"
      />
      <button
        type="button"
        class="date-nav"
        aria-label="다음날"
        data-testid="date-next"
        @click="home.shiftFixtureDate(1)"
      >▶</button>
      <button
        type="button"
        class="date-today"
        data-testid="date-today"
        @click="home.resetFixtureDate()"
      >오늘</button>
    </div>
    <div class="filters__row" role="tablist" aria-label="기간 필터">
      <button
        v-for="p in periodToggles"
        :key="p.v"
        type="button"
        role="tab"
        :aria-selected="home.fixtures.filter.period === p.v"
        :data-testid="'period-' + p.v"
        :class="['toggle', { 'toggle--active': home.fixtures.filter.period === p.v }]"
        @click="home.setPeriod(p.v)"
      >
        {{ p.label }}
      </button>
    </div>
  </div>
</template>
<style scoped>
.filters {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--color-border);
}
.filters__row { display: flex; gap: 6px; flex-wrap: wrap; }
.filters__row:first-child {
  gap: 8px;
}
.tab,
.toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 30px;
  background: transparent;
  border: 1px solid var(--color-border);
  color: var(--color-fg);
  padding: 4px 10px;
  border-radius: 999px;
  cursor: pointer;
  font-size: 12px;
}
.tab {
  gap: 8px;
  min-width: 78px;
  min-height: 36px;
  padding: 6px 13px;
  font-size: 13px;
  font-weight: 700;
}
.tab__label {
  line-height: 1;
  white-space: nowrap;
}
.tab--active {
  background: var(--theme-primary, var(--color-fg));
  color: var(--theme-on-primary, var(--color-bg));
  border-color: transparent;
}
.toggle--active {
  background: var(--color-fg);
  color: var(--color-bg);
}
.toggle {
  min-width: 38px;
}
.filters__row--date {
  align-items: center;
  gap: 4px;
}
.date-nav,
.date-today {
  background: transparent;
  border: 1px solid var(--color-border);
  color: var(--color-fg);
  padding: 4px 8px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}
.date-input {
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  color: var(--color-fg);
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-family: inherit;
}
</style>
