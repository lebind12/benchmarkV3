<script setup lang="ts">
import { computed } from 'vue'
import PreviewPlayerPhoto from '@/components/home-preview/PreviewPlayerPhoto.vue'
import type { HomePreview } from '@/lib/api/homePreviewSchema'
const props = defineProps<{ preview: HomePreview | null }>()
const points = computed(() => (props.preview?.analysis.player_watchpoints?.data ?? []).flatMap(pick => {
  const player = props.preview?.facts.player_spotlights?.data?.find(row => row.player_id === pick.player_id && row.team_id === pick.team_id)
  const text = player?.record_notes[pick.focus]
  return player && text ? [{ ...pick, player, text }] : []
}))
const labels = { season_contribution: '주목할 선수', scoring_streak: '득점 흐름', assist_streak: '도움 흐름', involvement_streak: '공격포인트 흐름', recent_contribution: '최근 경기 흐름' }
const recordTime = computed(() => {
  const value = props.preview?.facts.player_spotlights?.as_of
  return value ? new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(value)) : ''
})
const teamName = (id: number) => [props.preview?.fixture.home, props.preview?.fixture.away].find(team => team?.external_id === id)?.name
</script>
<template>
  <section v-if="points.length" id="preview-players" tabindex="-1" class="hp-player-section hp-reveal" data-testid="player-watchpoints">
    <header><h3>눈여겨볼 선수</h3><p>주요 선수와 이어가는 기록을 확인해보세요.</p></header>
    <div class="hp-player-watchpoints">
      <article v-for="point in points" :key="`${point.team_id}:${point.player_id}`" class="hp-player-point" data-testid="player-watchpoint">
        <div class="hp-player-point-head"><div><span>{{ teamName(point.team_id) }}</span><b>{{ point.player.player_name }}</b><small>{{ labels[point.focus] }}</small></div><PreviewPlayerPhoto :name="point.player.player_name" :photo-url="point.player.photo_url" /></div>
        <details :key="`${preview?.fixture.external_id}:${point.player_id}`" class="hp-player-details" data-testid="player-watchpoint-details">
          <summary>선정 이유와 기록 보기</summary>
          <div class="hp-player-details-body"><template v-if="point.reason"><h4>왜 눈여겨볼까요?</h4><p data-testid="player-selection-reason">{{ point.reason }}</p></template><template v-else><h4>선정 근거</h4><p>{{ point.text }}</p></template>
            <h4>확인된 기록</h4><ul><template v-for="(note, focus) in point.player.record_notes" :key="focus"><li v-if="note">{{ note }}</li></template></ul>
            <small v-if="point.focus !== 'season_contribution' || point.player.record_notes.recent_contribution" class="hp-record-scope">최근 팀 경기 기록은 모든 대회 기준입니다.</small><small v-if="recordTime">자료 기준 {{ recordTime }} KST</small>
          </div>
        </details>
      </article>
    </div>
  </section>
</template>
<style scoped>
.hp-player-section { padding: 26px 0; border-top: 1px solid var(--color-border); }
.hp-player-section header { margin-bottom: 20px; }
.hp-player-section header p { margin-top: 8px; color: var(--color-muted); font-size: 12px; }
.hp-player-watchpoints { display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: 14px; align-items: start; }
.hp-player-point { padding: 20px; border: 1px solid var(--color-border); border-radius: 12px; min-width: 0; }
.hp-player-point-head { display: flex; justify-content: space-between; gap: 12px; }
.hp-player-point-head > div { min-width: 0; }
.hp-player-point-head span { color: var(--color-muted); font-size: 11px; }
.hp-player-point b { display: block; font-size: 19px; line-height: 1.4; margin: 8px 0; overflow-wrap: anywhere; word-break: keep-all; }
.hp-player-point small { color: var(--color-muted); font-size: 11px; line-height: 1.8; }
.hp-player-details { margin-top: 16px; border-top: 1px solid var(--color-border); padding-top: 12px; }
.hp-player-details summary { cursor: pointer; font-size: 12px; color: var(--color-muted); line-height: 1.7; }
.hp-player-details summary:focus-visible { outline: 2px solid currentColor; outline-offset: 4px; }
.hp-player-details-body > small { display: block; margin-top: 8px; }
.hp-player-details-body > p { white-space: pre-line; }
.hp-player-details h4 { font-size: 12px; font-weight: 600; margin-top: 16px; }
.hp-player-details ul { margin: 10px 0; padding-left: 16px; }
.hp-player-details li { font-size: 12px; line-height: 1.8; padding-bottom: 6px; }
.hp-player-point p { font-size: 13px; line-height: 1.8; margin: 14px 0 6px; }
@media (max-width:600px) {
  .hp-player-watchpoints { gap: 10px; }
  .hp-player-watchpoints:has(.hp-player-details[open]) { grid-template-columns: minmax(0, 1fr); }
  .hp-player-point { padding: 14px 12px; }
  .hp-player-point-head { display: grid; grid-template-columns: minmax(0,1fr) 46px; gap: 8px; }
  .hp-player-point-head > div { display: contents; }
  .hp-player-point-head span { grid-column: 1; grid-row: 1; word-break: keep-all; }
  .hp-player-point-head :deep(.hp-player-photo) { grid-column: 2; grid-row: 1; }
  .hp-player-point b { grid-column: 1 / -1; grid-row: 2; margin: 0; font-size: 15px; }
  .hp-player-point-head small { grid-column: 1 / -1; grid-row: 3; }
  .hp-player-point p { font-size: 12px; }
}
</style>
