<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { generalApi, type PlayerDetailPayload, type TeamDetailPayload } from '@/lib/api/general'
import type { NewsMention } from '@/lib/api/news-analysis'
import { articlePieces } from './annotations'

type Detail = { kind: 'team'; data: TeamDetailPayload } | { kind: 'player'; data: PlayerDetailPayload }
type Entry = { state: 'loading' | 'ready' | 'error'; detail?: Detail }
const props = defineProps<{ text: string; mentions: NewsMention[]; loadDetail?: (mention: NewsMention) => Promise<Detail> }>()
const pieces = computed(() => articlePieces(props.text, props.mentions))
const root = ref<HTMLElement | null>(null)
const card = ref<HTMLElement | null>(null)
const active = ref<NewsMention | null>(null)
const entries = reactive(new Map<string, Entry>())
const cardStyle = ref({ left: '8px', top: '8px', maxHeight: '400px' })
const entry = computed(() => active.value?.entity ? entries.get(key(active.value)) : undefined)
const team = computed(() => entry.value?.detail?.kind === 'team' ? entry.value.detail.data : null)
const player = computed(() => entry.value?.detail?.kind === 'player' ? entry.value.detail.data : null)
const latestStats = computed(() => {
  const rows = (player.value?.season_stats ?? []).filter(row => Number.isInteger(row.season) && row.league?.external_id && row.team?.external_id)
  const season = Math.max(...rows.map(row => row.season))
  return rows.filter(row => row.season === season)
})
const name = (item: { name: string; name_ko?: string | null }) => item.name_ko || item.name
const metric = (value: number | null | undefined) => value == null ? '정보 없음' : String(value)
let anchor: HTMLElement | null = null
let closeTimer: ReturnType<typeof setTimeout> | null = null
let suppressFocus = false
let disposed = false
let epoch = 0
const key = (mention: NewsMention) => `${mention.entity_type}:${mention.entity!.id}`
function cancelClose() { if (closeTimer) clearTimeout(closeTimer); closeTimer = null }
function close(restore = false) {
  cancelClose(); active.value = null
  if (restore && anchor?.isConnected) { suppressFocus = true; anchor.focus(); queueMicrotask(() => { suppressFocus = false }) }
}
function scheduleClose() {
  cancelClose()
  closeTimer = setTimeout(() => {
    const focus = document.activeElement
    if (focus && (card.value?.contains(focus) || anchor === focus)) return
    close()
  }, 180)
}
function position() {
  if (!anchor || !card.value) return
  const rect = anchor.getBoundingClientRect()
  const width = card.value.offsetWidth || Math.min(360, innerWidth - 24)
  const height = Math.min(card.value.scrollHeight, innerHeight - 24)
  const left = Math.max(12, Math.min(rect.left, innerWidth - width - 12))
  const top = rect.bottom + 8 + height <= innerHeight - 12 ? rect.bottom + 8 : Math.max(12, rect.top - height - 8)
  cardStyle.value = { left: `${left}px`, top: `${top}px`, maxHeight: `${Math.max(160, innerHeight - 24)}px` }
}
async function fetchDetail(mention: NewsMention, retry = false) {
  const cacheKey = key(mention)
  if (!retry && entries.has(cacheKey)) return
  const snapshot = epoch
  entries.set(cacheKey, { state: 'loading' })
  try {
    const detail = await (props.loadDetail ?? (async (item: NewsMention): Promise<Detail> => {
      const match = item.entity?.detail_path.match(/^\/(teams|players)\/([^/?#]+)$/)
      if (!match || match[1] !== (item.entity_type === 'team' ? 'teams' : 'players')) throw new Error('invalid_detail_path')
      return item.entity_type === 'team'
        ? { kind: 'team', data: await generalApi.team(match[2]!) }
        : { kind: 'player', data: await generalApi.player(match[2]!) }
    }))(mention)
    if (!disposed && snapshot === epoch) entries.set(cacheKey, { state: 'ready', detail })
  } catch { if (!disposed && snapshot === epoch) entries.set(cacheKey, { state: 'error' }) }
  await nextTick(); position()
}
async function open(mention: NewsMention, event: Event) {
  if (suppressFocus || !mention.entity) return
  cancelClose(); anchor = event.currentTarget as HTMLElement; active.value = mention
  void fetchDetail(mention)
  await nextTick(); position()
}
function outside(event: Event) {
  const target = event.target as Node
  if (!anchor?.contains(target) && !card.value?.contains(target)) close()
}
async function enterCard(event: KeyboardEvent) {
  if (!active.value || event.shiftKey || !['Tab', 'ArrowDown'].includes(event.key)) return
  event.preventDefault()
  await nextTick()
  card.value?.querySelector<HTMLElement>('button, a')?.focus()
}
function escape(event: KeyboardEvent) { if (event.key === 'Escape' && active.value) { event.preventDefault(); close(true) } }
function focusOut(event: FocusEvent) {
  const next = event.relatedTarget as Node | null
  if (next && (root.value?.contains(next) || card.value?.contains(next))) return
  scheduleClose()
}
watch(() => [props.text, props.mentions], () => { epoch++; close(); entries.clear() })
onMounted(() => {
  document.addEventListener('pointerdown', outside)
  document.addEventListener('keydown', escape)
  window.addEventListener('resize', position)
  window.addEventListener('scroll', position, true)
})
onBeforeUnmount(() => {
  disposed = true; epoch++; cancelClose()
  document.removeEventListener('pointerdown', outside)
  document.removeEventListener('keydown', escape)
  window.removeEventListener('resize', position)
  window.removeEventListener('scroll', position, true)
})
</script>

<template>
  <div ref="root" class="annotated-article" @focusout="focusOut"><template v-for="piece in pieces" :key="piece.start"><button v-if="piece.mention" class="annotated-name" type="button" aria-haspopup="dialog" :aria-expanded="active?.entity?.id === piece.mention.entity?.id && active?.entity_type === piece.mention.entity_type" :aria-controls="active?.entity?.id === piece.mention.entity?.id ? 'news-entity-card' : undefined" @mouseenter="open(piece.mention, $event)" @mouseleave="scheduleClose" @focus="open(piece.mention, $event)" @click="open(piece.mention, $event)" @keydown="enterCard">{{ piece.text }}</button><template v-else>{{ piece.text }}</template></template></div>
  <Teleport to="body">
    <section v-if="active" id="news-entity-card" ref="card" class="entity-card" :style="cardStyle" role="dialog" aria-labelledby="news-card-title" tabindex="-1" @mouseenter="cancelClose" @mouseleave="scheduleClose" @focusin="cancelClose" @focusout="focusOut">
      <header><div><small>{{ active.entity_type === 'team' ? '팀' : '선수' }}</small><h3 id="news-card-title">{{ active.entity!.name }}</h3></div><button type="button" aria-label="정보 카드 닫기" @click="close(true)">×</button></header>
      <p v-if="entry?.state === 'loading'" role="status">정보를 불러오는 중입니다.</p>
      <div v-else-if="entry?.state === 'error'" role="alert"><p>정보를 불러오지 못했습니다.</p><button class="card-retry" type="button" @click="fetchDetail(active!, true)">정보 다시 불러오기</button></div>
      <template v-else-if="entry?.state === 'ready'">
        <template v-if="team"><dl><div><dt>국가</dt><dd>{{ team.country || '정보 없음' }}</dd></div><div><dt>홈구장</dt><dd>{{ team.venue?.name || '정보 없음' }}</dd></div></dl><h4>최근 경기</h4><p v-if="!team.recent_results?.length">경기 정보 없음</p><ul v-else class="card-fixtures"><li v-for="fixture in team.recent_results.slice(0, 3)" :key="fixture.external_id"><small>{{ name(fixture.league) }} · {{ fixture.kickoff_at?.slice(0, 10) || '날짜 정보 없음' }}</small><span>{{ name(fixture.home) }} {{ metric(fixture.goals_home) }} : {{ metric(fixture.goals_away) }} {{ name(fixture.away) }}</span></li></ul></template>
        <template v-if="player"><dl><div><dt>국적</dt><dd>{{ player.profile.nationality || '정보 없음' }}</dd></div><div><dt>현재 팀</dt><dd>{{ player.current_team ? name(player.current_team) : '정보 없음' }}</dd></div></dl><h4>최신 시즌 기록</h4><p v-if="!latestStats.length">시즌 기록 정보 없음</p><ul v-else class="card-stats"><li v-for="(row, index) in latestStats" :key="index"><strong>{{ row.season }} · {{ name(row.league) }}</strong><small>{{ name(row.team) }}</small><span>출전 {{ metric(row.appearances) }} · 골 {{ metric(row.goals) }} · 도움 {{ metric(row.assists) }}</span></li></ul></template>
      </template>
      <p class="card-context">현재 저장된 자료입니다. 글 작성 당시의 정보와 다를 수 있습니다.</p>
      <RouterLink :to="active.entity!.detail_path" class="card-detail">{{ active.entity_type === 'team' ? '팀' : '선수' }} 상세 보기</RouterLink>
    </section>
  </Teleport>
</template>

<style scoped>
.annotated-article{white-space:pre-wrap;overflow-wrap:anywhere;font-size:15px;line-height:2.1;color:var(--color-fg);padding:22px 0;min-height:180px}.annotated-name{display:inline;border:0;border-bottom:2px solid #2563eb;border-radius:3px;padding:0 2px;margin:0;background:#dbeafe;color:#1e40af;font:inherit;line-height:inherit;text-align:inherit;cursor:pointer}.annotated-name:hover,.annotated-name[aria-expanded=true]{background:#bfdbfe}.annotated-name:focus-visible,.entity-card button:focus-visible,.entity-card a:focus-visible{outline:2px solid #2563eb;outline-offset:3px}.entity-card{position:fixed;z-index:1000;box-sizing:border-box;width:min(360px,calc(100vw - 24px));padding:18px;border:1px solid var(--color-border);border-radius:10px;background:var(--color-bg);color:var(--color-fg);box-shadow:0 8px 30px #0002;overflow-y:auto;font-size:13px;line-height:1.7;overflow-wrap:anywhere}.entity-card header{display:flex;justify-content:space-between;align-items:start;gap:12px}.entity-card header small{font-size:11px;color:var(--color-muted)}.entity-card h3{font-size:18px;font-weight:700;margin:0}.entity-card header button{border:0;background:transparent;color:var(--color-muted);font-size:22px;cursor:pointer;padding:0 6px}.entity-card h4{font-weight:650;font-size:13px;margin:16px 0 8px}.entity-card dl{margin:16px 0}.entity-card dl>div{display:flex;gap:16px;margin:5px 0}.entity-card dt{color:var(--color-muted);min-width:45px}.entity-card dd{margin:0}.card-fixtures,.card-stats{padding:0;margin:0;list-style:none}.card-fixtures li,.card-stats li{display:grid;gap:3px;padding:9px 0;border-bottom:1px solid var(--color-border)}.card-fixtures small,.card-stats small{font-size:11px;color:var(--color-muted)}.card-context{color:var(--color-muted);font-size:11px;border-top:1px solid var(--color-border);padding-top:12px;margin-top:16px}.card-detail{color:#2563eb;text-decoration:underline;text-underline-offset:3px}.card-retry{color:#2563eb;border:1px solid var(--color-border);padding:5px 10px;border-radius:5px;background:var(--color-bg);cursor:pointer}
</style>
