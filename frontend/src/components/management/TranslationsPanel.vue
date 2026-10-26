<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { Search, LockKeyhole, Languages, AlertTriangle, History } from 'lucide-vue-next'
import { ManagementApiError, useManagementApi, type EntityType, type TranslationEntry, type TranslationChange, type TranslationAffiliationFilters } from '@/lib/api/management'
import TeamScopeSelect from './TeamScopeSelect.vue'
import { dateTime, entityLabels } from './display'
const api = useManagementApi()
const props = defineProps<{ translations: TranslationEntry[] }>()
const emit = defineEmits<{ refresh: []; notify: [message: string] }>()
const query = ref('')
const type = ref<EntityType | 'all'>('all')
const filter = ref('all')
const leagueId = ref('')
const teamId = ref('')
const scopes = ref<TranslationAffiliationFilters>({ leagues: [], teams: [] })
const scopeLoading = ref(false)
const scopeError = ref('')
let scopeRequestId = 0
async function loadScopes() {
  const id = ++scopeRequestId
  if (type.value !== 'player' && type.value !== 'coach') { scopeLoading.value = false; return }
  scopeLoading.value = true; scopeError.value = ''; scopes.value = {leagues: scopes.value.leagues, teams: []}
  try { const result = await api.translationAffiliationFilters(type.value as 'player' | 'coach', leagueId.value ? Number(leagueId.value) : undefined); if (id === scopeRequestId) scopes.value = result }
  catch (err) { if (id === scopeRequestId) scopeError.value = err instanceof Error ? err.message : '리그·팀 조건을 불러오지 못했습니다.' }
  finally { if (id === scopeRequestId) scopeLoading.value = false }
}
function clearScope() { leagueId.value = ''; teamId.value = '' }
watch(leagueId, () => { teamId.value = '' })
watch(type, clearScope)
watch([type, leagueId], loadScopes)
const selected = ref<TranslationEntry | null>(null)
const editorPanel = ref<HTMLElement | null>(null)
const name = ref('')
const shortName = ref('')
const error = ref('')
const busy = ref(false)
const conflict = ref<TranslationEntry | null>(null)
const changes = ref<TranslationChange[]>([])
const page = ref(1)
const total = ref(props.translations.length)
const pageSize = ref(50)
const listing = ref(false)
const listError = ref('')
const data = ref(props.translations)
let requestId = 0
let timer: ReturnType<typeof setTimeout> | undefined
async function load() {
  const id = ++requestId; listing.value = true; listError.value = ''
  try { const result = await api.translations({ query: query.value, type: type.value, status: filter.value, page: page.value, league_id: ['player','coach'].includes(type.value) && leagueId.value ? Number(leagueId.value) : undefined, team_id: ['player','coach'].includes(type.value) && teamId.value ? Number(teamId.value) : undefined }); if (id !== requestId) return; data.value = result.items; total.value = result.total ?? result.items.length; pageSize.value = result.page_size ?? 50 }
  catch (err) { if (id === requestId) listError.value = err instanceof Error ? err.message : '번역 목록을 조회하지 못했습니다.' }
  finally { if (id === requestId) listing.value = false }
}
watch([query,type,filter,leagueId,teamId], () => { requestId++; data.value = []; listing.value = true; total.value = 0; page.value = 1; clearTimeout(timer); timer = setTimeout(load, 200) })
watch(page, load)
watch(() => props.translations, load)
onBeforeUnmount(() => { clearTimeout(timer); requestId++; scopeRequestId++ })
const rows = computed(() => data.value.filter((row) => (type.value === 'all' || row.type === type.value) && (filter.value === 'all' || (filter.value === 'translated' ? !!row.name_ko?.trim() : !row.name_ko?.trim())) && `${row.original} ${row.name_ko ?? ''} ${row.short_name_ko ?? ''} ${row.context}`.toLowerCase().includes(query.value.toLowerCase())))
async function open(row: TranslationEntry) {
  selected.value = { ...row }; name.value = row.name_ko ?? ''; shortName.value = row.short_name_ko ?? ''; error.value = ''; conflict.value = null; changes.value = []
  await nextTick()
  if (window.innerWidth <= 1100) editorPanel.value?.scrollIntoView({ block: 'start' })
  editorPanel.value?.querySelector<HTMLElement>('input')?.focus({ preventScroll: true })
  try { const result = await api.translationHistory(row); if (selected.value?.id === row.id && selected.value?.type === row.type) changes.value = result.items }
  catch { error.value = '수정 이력을 불러오지 못했습니다. 입력한 내용은 유지됩니다.' }
}
async function save() {
  if (!selected.value || conflict.value) return
  busy.value = true; error.value = ''
  try {
    const row = await api.saveTranslation(selected.value, name.value || null, shortName.value || null)
    selected.value = row; name.value = row.name_ko ?? ''; shortName.value = row.short_name_ko ?? ''
    changes.value = (await api.translationHistory(row)).items
    await load(); emit('notify', '번역을 저장했습니다. 수정 이력과 사람 수정 보호가 반영되었습니다.'); emit('refresh')
  } catch (err) {
    if (err instanceof ManagementApiError && err.status === 409 && err.current) conflict.value = err.current
    else error.value = err instanceof Error ? err.message : '번역을 저장하지 못했습니다.'
  } finally { busy.value = false }
}
function acknowledgeConflict() {
  if (!conflict.value) return
  selected.value = { ...conflict.value }; conflict.value = null
  error.value = '최신 변경을 확인했습니다. 내 입력은 유지됩니다. 내용을 다시 검토한 후 저장하세요.'
  emit('refresh')
}
</script>
<template>
  <div class="mm-workspace" :class="{ 'mm-workspace--split': selected }">
    <section class="mm-panel" aria-label="번역 검수 목록">
      <header class="mm-panel-head"><div><h2>번역 검수</h2><p>원문과 한국어 표기를 비교하고 이름을 다듬으세요.</p></div><Languages :size="20" class="mm-muted" /></header>
      <div class="mm-type-tabs" aria-label="번역 종류"><button type="button" :class="{ selected: type === 'all' }" @click="type = 'all'">전체</button><button v-for="(label, key) in entityLabels" :key="key" type="button" :class="{ selected: type === key }" @click="type = key">{{ label }}</button></div>
      <div class="mm-toolbar"><label class="mm-search"><Search :size="16" /><input v-model="query" aria-label="번역 검색" placeholder="원문, 한국어 이름 또는 소속 검색" /></label><select v-model="filter" aria-label="번역 상태"><option value="all">전체 상태</option><option value="translated">번역</option><option value="untranslated">미번역</option></select></div>
      <section v-if="type === 'player' || type === 'coach'" class="mm-player-scope" :aria-label="`${entityLabels[type]} 소속 조건`">
        <div class="mm-player-scope-controls">
          <label>리그<select v-model="leagueId" :aria-label="`${entityLabels[type]} 리그 조건`" :disabled="scopeLoading || !scopes.leagues.length"><option value="">전체 리그</option><option v-for="league in scopes.leagues" :key="league.id" :value="String(league.id)">{{ league.name }}</option></select></label>
          <div class="mm-scope-team-field"><span>팀</span><TeamScopeSelect :key="type" v-model="teamId" :options="scopes.teams" :label="`${entityLabels[type]} 팀 조건`" :disabled="scopeLoading || !scopes.teams.length" /></div>
          <button class="mm-button mm-button--quiet" type="button" :disabled="!leagueId && !teamId" @click="clearScope">소속 조건 초기화</button>
        </div>
        <p class="mm-caption">{{ type === 'player' ? '수집된 시즌 소속 기준이며 이적 전 팀도 포함됩니다.' : '수집된 팀·감독 소속 기록 기준이며 이전 소속도 포함됩니다.' }} 리그를 바꾸면 팀 조건은 초기화됩니다.</p>
        <p v-if="scopeLoading" class="mm-caption" role="status">리그·팀 조건 조회 중…</p>
        <p v-else-if="scopeError" class="mm-error-text" role="alert">{{ scopeError }}<button class="mm-button" type="button" @click="loadScopes">조건 다시 조회</button></p>
        <p v-else-if="!scopes.leagues.length && !scopes.teams.length" class="mm-caption">수집된 소속 기록이 없습니다. 조건 없이 이름으로 검색할 수 있습니다.</p>
      </section>
      <div class="mm-table-wrap"><table class="mm-table"><thead><tr><th>원문</th><th>한국어 이름</th><th>짧은 이름</th><th>번역 상태</th><th></th></tr></thead><tbody><tr v-for="row in rows" :key="`${row.type}-${row.id}`" :class="{ 'mm-row-selected': selected?.id === row.id && selected.type === row.type }" :data-testid="`translation-${row.id}`"><td><strong>{{ row.original }}</strong><small>{{ entityLabels[row.type] }} · {{ row.context }}</small></td><td>{{ row.name_ko || '미입력' }}<LockKeyhole v-if="row.protected" :size="12" class="mm-inline-icon" aria-label="사람 수정 보호" /></td><td>{{ row.short_name_ko || '미입력' }}</td><td><span :class="['mm-badge', row.name_ko?.trim() ? 'mm-badge--succeeded' : 'mm-badge--pending']">{{ row.name_ko?.trim() ? '번역' : '미번역' }}</span></td><td><button class="mm-button mm-button--quiet" type="button" :aria-label="`${row.original} 번역 편집`" @click="open(row)">편집</button></td></tr></tbody></table></div>
      <p v-if="listing" class="mm-panel-foot" role="status">번역 목록 조회 중…</p><p v-if="listError" class="mm-error-text" role="alert">{{ listError }}<button class="mm-button" type="button" @click="load">다시 조회</button></p><div v-if="!rows.length && !listing && !listError" class="mm-empty"><Languages :size="30" /><h3>조건에 맞는 번역이 없습니다</h3><p>이름이나 종류·번역 상태를 바꿔 확인해 보세요.</p><button class="mm-button" type="button" @click="query = ''; type = 'all'; filter = 'all'; clearScope()">필터 초기화</button></div>
      <footer class="mm-panel-foot">{{ rows.length }}개 표시 / 검색 결과 {{ total }}개 · 한국어 이름이 있으면 번역, 없으면 미번역입니다. 짧은 이름은 선택 사항입니다.</footer><div v-if="total > pageSize" class="mm-panel-foot mm-between"><button class="mm-button" type="button" :disabled="page <= 1 || listing" @click="page--">이전 페이지</button><span>{{ page }} / {{ Math.ceil(total/pageSize) }}</span><button class="mm-button" type="button" :disabled="page*pageSize >= total || listing" @click="page++">다음 페이지</button></div>
    </section>
    <aside v-if="selected" ref="editorPanel" class="mm-panel mm-editor" aria-label="번역 편집">
      <header class="mm-panel-head"><div><h2>한국어 표기 편집</h2><p>{{ entityLabels[selected.type] }} · {{ selected.context }}</p></div><button type="button" class="mm-button mm-button--quiet" @click="selected = null">닫기</button></header>
      <form class="mm-form" @submit.prevent="save"><div class="mm-original"><span>원문</span><strong>{{ selected.original }}</strong></div><label>한국어 이름<input v-model="name" maxlength="80" aria-label="한국어 이름" placeholder="비워두면 원문 표시" /></label><label>한국어 짧은 이름<input v-model="shortName" maxlength="40" aria-label="한국어 짧은 이름" placeholder="비워두면 원문 표시" /></label><p class="mm-note"><LockKeyhole :size="14" />직접 저장한 표기와 의도적으로 비운 값은 이후 자동 번역에서 보호됩니다.</p>
        <section v-if="conflict" class="mm-conflict" role="alert"><h3><AlertTriangle :size="16" />다른 사용자의 수정이 있습니다</h3><p>내 입력을 보존했습니다. {{ conflict.editor }}님의 최신 변경과 비교해 주세요.</p><div class="mm-conflict-grid"><div><strong>서버 최신값</strong><span>{{ conflict.name_ko || '원문 표시' }}</span><small>{{ conflict.short_name_ko || '원문 표시' }}</small></div><div><strong>내 입력</strong><span>{{ name || '원문 표시' }}</span><small>{{ shortName || '원문 표시' }}</small></div></div><button type="button" class="mm-button" @click="acknowledgeConflict">차이를 확인하고 편집 계속</button></section>
        <p v-if="error" class="mm-error-text" role="alert">{{ error }}</p><button class="mm-button mm-button--primary mm-full" type="submit" :disabled="busy || !!conflict">{{ busy ? '저장 중…' : '번역 저장' }}</button><p class="mm-caption">{{ selected.editor }} · {{ dateTime(selected.updated_at) }}</p>
      </form>
      <section class="mm-change-history"><h3><History :size="16" />수정 이력</h3><div v-if="!changes.length" class="mm-caption">아직 기록된 수정 이력이 없습니다.</div><article v-for="change in changes" :key="change.version"><strong>{{ change.editor }} <small>{{ dateTime(change.at) }}</small></strong><p>{{ change.before.name_ko || '원문 표시' }} → {{ change.after.name_ko || '원문 표시' }}</p><p class="mm-caption">짧은 이름: {{ change.before.short_name_ko || '원문 표시' }} → {{ change.after.short_name_ko || '원문 표시' }}</p></article></section>
    </aside>
  </div>
</template>
