<script setup lang="ts">
import { computed } from 'vue'
import type { HomePreview } from '@/lib/api/homePreviewSchema'
const props = defineProps<{ preview: HomePreview | null }>()
const rows = computed(() => props.preview?.facts.injuries.data ?? [])
const selected = computed(() => (props.preview?.analysis.key_absences?.data ?? []).flatMap(pick => {
  const row = rows.value.find(row => row.team_id === pick.team_id && row.player_id === pick.player_id)
  return row ? [{ ...row, explanation: pick.reason }] : []
}))
const teamName = (id: number) => [props.preview?.fixture.home, props.preview?.fixture.away].find(team => team?.external_id === id)?.name ?? ''
const sources = (ids: string[]) => props.preview?.sources.filter(source => ids.includes(source.id)).map(source => source.title).join(' · ')
</script>
<template>
  <section id="preview-injuries" tabindex="-1" class="hp-injuries hp-reveal">
    <div><h3>주요 부상·출전 변수</h3><p>출전 기록을 근거로 팀당 최대 2명을 선별합니다.</p></div>
    <p v-if="!preview?.facts.injuries.data" class="hp-unavailable hp-injury-empty">부상·출전 정보가 없습니다.</p>
    <p v-else-if="rows.length === 0" class="hp-inline-note">확인된 결장자가 없습니다.</p>
    <template v-else>
      <p v-if="!selected.length" class="hp-inline-note hp-injury-empty">{{ preview?.analysis.key_absences?.status === 'available' ? '확인된 기록에서 주요 결장자로 선별된 선수가 없습니다.' : '주요 결장자 선별 정보가 아직 없습니다.' }}</p>
      <article v-for="injury in selected" :key="`${injury.team_id}:${injury.player_id}`" class="hp-injury-item" data-testid="key-absence">
        <small>{{ teamName(injury.team_id) }}</small>
        <span class="hp-tag" :class="{ 'hp-tag--uncertain': injury.availability === 'doubtful' }">{{ injury.availability === 'out' ? '확정 결장' : '출전 불확실' }}</span>
        <b>{{ injury.player_name }}</b><span>{{ injury.detail }}</span><p>{{ injury.explanation }}</p><small>{{ sources(injury.source_ids) }}</small>
      </article>
      <details :key="preview?.fixture.external_id" class="hp-all-injuries" data-testid="all-injuries">
        <summary>전체 부상·출전 정보 {{ rows.length }}명</summary>
        <div class="hp-all-injuries-grid"><article v-for="(injury, i) in rows" :key="`${injury.team_id}:${injury.player_id ?? i}`" class="hp-injury-item">
          <small>{{ teamName(injury.team_id) }}</small><b>{{ injury.player_name }}</b>
          <span>{{ injury.status_conflict ? '출전 상태 확인 필요' : injury.availability === 'out' ? '확정 결장' : '출전 불확실' }} · {{ injury.detail }}</span><small>{{ sources(injury.source_ids) }}</small>
        </article></div>
      </details>
    </template>
  </section>
</template>
<style scoped>
.hp-all-injuries { grid-column: 1 / -1; border-top: 1px solid var(--color-border); padding-top: 16px; font-size: 12px; }
summary { cursor: pointer; color: var(--color-muted); }
.hp-all-injuries-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(220px, 100%), 1fr)); gap: 24px; padding-top: 20px; }
</style>
