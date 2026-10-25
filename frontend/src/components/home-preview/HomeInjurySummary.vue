<script setup lang="ts">
import { computed } from 'vue'
import PreviewPlayerPhoto from '@/components/home-preview/PreviewPlayerPhoto.vue'
import type { HomePreview } from '@/lib/api/homePreviewSchema'
const props = defineProps<{ preview: HomePreview | null }>()
const rows = computed(() => props.preview?.facts.injuries.data ?? [])
const selected = computed(() => (props.preview?.analysis.key_absences?.data ?? []).flatMap(pick => {
  const row = rows.value.find(row => row.team_id === pick.team_id && row.player_id === pick.player_id)
  return row ? [{ ...row, explanation: pick.reason }] : []
}))
const teams = computed(() => props.preview ? [props.preview.fixture.home, props.preview.fixture.away] : [])
const teamName = (id: number) => teams.value.find(team => team.external_id === id)?.name ?? ''
const slots = computed(() => [0, 1].flatMap(rank => teams.value.map(team => ({ team, rank, injury: selected.value.filter(row => row.team_id === team.external_id).slice(0, 2)[rank] }))))
const sources = (ids: string[]) => props.preview?.sources.filter(source => ids.includes(source.id)).map(source => source.title.replace('API-Football 부상·출전 정보', 'API-Football')).join(' · ')
function causeDate(row: typeof selected.value[number]) {
  const cause = row.cause?.data
  if (!cause) return '발생 시점 미확인'
  const value = cause.occurred_on ?? cause.occurred_month
  if (!value) return '발생 시점 미확인'
  const parts=value.split('-'); const year=props.preview?.fixture.kickoff_at.slice(0,4)
  return `${parts[0] === year ? '' : parts[0] + '년 '}${Number(parts[1])}월${cause.occurred_on ? ' ' + Number(parts[2]) + '일' : ''} 발생`
}
const fallbackCause = (detail: string) => (({ 'Injury':'부상 · 세부 원인 미확인', 'Muscle Injury':'근육 부상', 'Thigh Injury':'허벅지 부상', 'Knee Injury':'무릎 부상', 'Ankle Injury':'발목 부상', 'Hamstring Injury':'햄스트링 부상', 'Calf Injury':'종아리 부상', 'Red Card':'퇴장 징계', 'Yellow Cards':'경고 누적 징계', 'Illness':'질병' } as Record<string, string>)[detail] ?? detail)
const causeUrl = (ids: string[]) => props.preview?.sources.find(source => ids.includes(source.id) && source.kind === 'web')?.url
function compactRecord(row: typeof selected.value[number]) {
  const record = row.importance_evidence
  if (!record) return row.explanation
  const season = record.seasons.find(season => season.minutes !== null || season.appearances !== null)
  if (season) return `${season.season_year}시즌 ${season.appearances !== null ? `${season.appearances}경기 출전` : ''}${season.appearances === null && season.minutes !== null ? `출전 시간 ${season.minutes}분` : ''}`
  if (record.recent_starts !== null) return `확인된 최근 ${record.lineup_games}경기 중 선발 ${record.recent_starts}회`
  return '부상·출전 상태를 확인한 주요 선수'
}
</script>
<template>
  <section id="preview-injuries" tabindex="-1" class="hp-injuries hp-reveal hp-injury-summary">
    <header class="hp-injury-heading"><h3>주요 부상·출전 변수</h3><p>양팀에서 주목할 결장·출전 변수를 모았습니다.</p></header>
    <p v-if="!preview?.facts.injuries.data" class="hp-unavailable hp-injury-empty">부상·출전 정보가 없습니다.</p>
    <p v-else-if="rows.length === 0" class="hp-inline-note">확인된 결장자가 없습니다.</p>
    <template v-else>
      <p v-if="!selected.length" class="hp-inline-note hp-injury-empty">{{ preview?.analysis.key_absences?.status === 'available' ? '확인된 정보에서 주요 결장자로 선별된 선수가 없습니다.' : '주요 결장자 선별 정보가 아직 없습니다.' }}</p>
      <template v-else>
        <div class="hp-injury-team-headings"><b v-for="(team, side) in teams" :key="team.external_id"><span>{{ side === 0 ? '홈' : '원정' }}</span>{{ team.name }}</b></div>
        <div class="hp-injury-matrix" data-testid="injury-matrix">
          <template v-for="slot in slots" :key="`${slot.team.external_id}:${slot.rank}`">
            <article v-if="slot.injury" class="hp-injury-card" data-testid="key-absence" :data-team-id="slot.team.external_id">
              <div class="hp-injury-player"><div class="hp-injury-identity"><span class="hp-tag" :class="{ 'hp-tag--uncertain': slot.injury.availability === 'doubtful' }">{{ slot.injury.availability === 'out' ? '확정 결장' : '출전 불확실' }}</span>
              <h4>{{ slot.injury.player_name }}</h4><span class="hp-injury-cause">{{ slot.injury.cause?.data?.label ?? fallbackCause(slot.injury.detail) }}</span><small v-if="slot.injury.cause" class="hp-cause-date">{{ causeDate(slot.injury) }}</small></div><PreviewPlayerPhoto :name="slot.injury.player_name" :photo-url="slot.injury.photo_url" /></div>
              <p :title="slot.injury.explanation">{{ compactRecord(slot.injury) }}</p><small>{{ sources(slot.injury.source_ids) }} <a v-if="slot.injury.cause?.data" :href="causeUrl(slot.injury.cause.source_ids) ?? undefined" target="_blank" rel="noopener noreferrer">원인 출처</a></small>
            </article>
            <div v-else class="hp-injury-card hp-injury-card--empty" data-testid="empty-absence"><span>추가 주요 변수 없음</span></div>
          </template>
        </div>
      </template>
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
.hp-injury-summary { display: block; }
.hp-injury-heading { margin-bottom: 22px; }
.hp-injury-team-headings, .hp-injury-matrix { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.hp-injury-team-headings { margin-bottom: 10px; }
.hp-injury-team-headings b { display: flex; align-items: baseline; gap: 8px; font-size: 13px; min-width: 0; overflow-wrap: anywhere; }
.hp-injury-team-headings span { font-size: 10px; font-weight: 400; color: var(--color-muted); }
.hp-injury-matrix { grid-auto-rows: 1fr; }
.hp-injury-card { min-width: 0; padding: 20px; border: 1px solid var(--color-border); border-radius: 12px; display: flex; flex-direction: column; align-items: flex-start; gap: 10px; }
.hp-injury-player { display: flex; justify-content: space-between; gap: 10px; width: 100%; }
.hp-injury-identity { min-width: 0; display: flex; flex-direction: column; align-items: flex-start; gap: 8px; }
.hp-injury-card h4 { font-size: 18px; line-height: 1.4; font-weight: 700; overflow-wrap: anywhere; word-break: keep-all; }
.hp-injury-cause { font-size: 12px; color: var(--color-muted); overflow-wrap: anywhere; }
.hp-injury-card p { margin: 0; line-height: 1.7; }
.hp-injury-card small { margin-top: auto; color: var(--color-muted); font-size: 10px; line-height: 1.6; }
.hp-injury-card--empty { justify-content: center; align-items: center; border-style: dashed; color: var(--color-muted); font-size: 12px; }
.hp-all-injuries { margin-top: 20px; border-top: 1px solid var(--color-border); padding-top: 16px; font-size: 12px; }
summary { cursor: pointer; color: var(--color-muted); }
.hp-all-injuries-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(220px, 100%), 1fr)); gap: 24px; padding-top: 20px; }
@media (max-width: 600px) {
  .hp-injury-matrix, .hp-injury-team-headings { gap: 10px; }
  .hp-injury-card { padding: 14px 12px; gap: 9px; }
  .hp-injury-player { display: grid; grid-template-columns: minmax(0,1fr) 46px; gap: 8px; }
  .hp-injury-identity { display: contents; }
  .hp-injury-identity .hp-tag { grid-column: 1; grid-row: 1; align-self: start; justify-self: start; }
  .hp-injury-player :deep(.hp-player-photo) { grid-column: 2; grid-row: 1; }
  .hp-injury-identity h4 { grid-column: 1 / -1; grid-row: 2; font-size: 15px; }
  .hp-injury-cause { grid-column: 1 / -1; grid-row: 3; }
  .hp-cause-date { grid-column: 1 / -1; grid-row: 4; }
  .hp-injury-card p { font-size: 11px; }
}
</style>
