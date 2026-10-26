<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { Plus, Search, Pencil, Trash2, ArrowRight } from 'lucide-vue-next'
import { useManagementApi, type CatalogLeague, type CollectionTarget, type TargetInput } from '@/lib/api/management'
import ManagementDialog from './ManagementDialog.vue'
import CatalogPanel from './CatalogPanel.vue'
import ResourceLogo from './ResourceLogo.vue'
const catalogPanel = ref<InstanceType<typeof CatalogPanel> | null>(null)
import { dateTime } from './display'
const api = useManagementApi()
const props = defineProps<{ targets: CollectionTarget[]; catalog: CatalogLeague[]; selected: number[] }>()
const emit = defineEmits<{ refresh: []; notify: [message: string]; selection: [ids: number[]]; execute: [] }>()
const query = ref('')
const filter = ref('all')
const editorOpen = ref(false)
const editorPanel = ref<HTMLElement | null>(null)
const editing = ref<number | null>(null)
const error = ref('')
const busy = ref(false)
const removing = ref<CollectionTarget | null>(null)
const form = reactive<TargetInput>({ league_id: 39, season: 2026, is_active: true, include_details: true, include_players: true, include_standings: true, fixture_limit: null })
const limitText = ref('')
const extraCatalog = ref<CatalogLeague[]>([])
const allCatalog = computed(() => [...props.catalog, ...extraCatalog.value.filter(row => !props.catalog.some(item => item.id === row.id))])
const catalogQuery = ref('')
const visibleCatalog = computed(() => allCatalog.value.filter((item) => !catalogQuery.value || `${item.name} ${item.name_en} ${item.id}`.toLowerCase().includes(catalogQuery.value.toLowerCase())))
const league = computed(() => allCatalog.value.find((item) => item.id === form.league_id))
const validSelection = computed(() => !!league.value && league.value.seasons.includes(form.season) && (!!editing.value || visibleCatalog.value.some((item) => item.id === form.league_id)))
watch(catalogQuery, () => {
  if (!editing.value && !visibleCatalog.value.some((item) => item.id === form.league_id)) {
    form.league_id = 0; form.season = 0; form.include_standings = false
  }
})
const rows = computed(() => props.targets.filter((row) => (filter.value === 'all' || (filter.value === 'active') === row.is_active) && `${row.name} ${row.name_en} ${row.league_id} ${row.season}`.toLowerCase().includes(query.value.toLowerCase())))
const selectable = computed(() => rows.value.filter((row) => row.is_active))
const allSelected = computed(() => selectable.value.length > 0 && selectable.value.every((row) => props.selected.includes(row.id)))
function toggle(id: number) { emit('selection', props.selected.includes(id) ? props.selected.filter((value) => value !== id) : [...props.selected, id]) }
function toggleAll() { const ids = selectable.value.map((row) => row.id); emit('selection', allSelected.value ? props.selected.filter((id) => !ids.includes(id)) : [...new Set([...props.selected, ...ids])]) }
async function openEditor(row?: CollectionTarget) {
  if (row && !allCatalog.value.some(item => item.id === row.league_id)) {
    try { const result = await api.catalog({ id: row.league_id }); extraCatalog.value.push(...result.items) }
    catch { emit('notify', '리그 카탈로그를 확인하지 못했습니다. 다시 시도하세요.'); return }
  }
  editing.value = row?.id ?? null
  Object.assign(form, row ? { league_id: row.league_id, season: row.season, is_active: row.is_active, include_details: row.include_details, include_players: row.include_players, include_standings: row.include_standings, fixture_limit: row.fixture_limit } : { league_id: props.catalog[0]?.id ?? 39, season: props.catalog[0]?.seasons[0] ?? 2026, is_active: true, include_details: true, include_players: true, include_standings: true, fixture_limit: null })
  limitText.value = row?.fixture_limit?.toString() ?? ''; catalogQuery.value = ''; error.value = ''; editorOpen.value = true
  await nextTick()
  if (window.innerWidth <= 1100) editorPanel.value?.scrollIntoView({ block: 'start' })
  editorPanel.value?.querySelector<HTMLElement>('input:not(:disabled), select:not(:disabled)')?.focus({ preventScroll: true })
}
function changeLeague() { form.season = league.value?.seasons[0] ?? 2026; form.include_standings = league.value?.standings ?? false }
async function save() {
  error.value = ''
  if (!validSelection.value) { error.value = '검색 결과에서 리그와 허용 시즌을 선택하세요.'; return }
  const rawLimit = String(limitText.value).trim()
  const limit = rawLimit ? Number(rawLimit) : null
  if (limit != null && (!Number.isInteger(limit) || limit < 1)) { error.value = '경기 수 제한은 1 이상의 정수로 입력하거나 비워두세요.'; return }
  busy.value = true
  try { await api.saveTarget({ ...form, fixture_limit: limit }, editing.value ?? undefined); emit('notify', editing.value ? '수집 설정을 저장했습니다.' : '수집 대상을 저장했습니다. 같은 리그·시즌은 기존 설정을 갱신합니다.'); emit('refresh'); editorOpen.value = false }
  catch (err) { error.value = err instanceof Error ? err.message : '설정을 저장하지 못했습니다.' }
  finally { busy.value = false }
}
async function changeActive(row: CollectionTarget) {
  try { await api.toggleTarget(row.id, !row.is_active); if (row.is_active) emit('selection', props.selected.filter((id) => id !== row.id)); emit('notify', `${row.name} ${row.season} 수집을 ${row.is_active ? '비활성화' : '활성화'}했습니다. 기존 데이터는 유지됩니다.`); emit('refresh') }
  catch (err) { emit('notify', err instanceof Error ? err.message : '상태를 바꾸지 못했습니다.') }
}
async function remove() {
  if (!removing.value) return
  try { await api.removeTarget(removing.value.id); emit('selection', props.selected.filter((id) => id !== removing.value!.id)); if (editing.value === removing.value.id) editorOpen.value = false; removing.value = null; emit('notify', '수집 대상에서 제외했습니다. 기존 적재 데이터는 유지됩니다.'); emit('refresh') }
  catch (err) { emit('notify', err instanceof Error ? err.message : '제외하지 못했습니다.') }
}
async function selectCatalog(item: CatalogLeague, season: number) {
  if (!allCatalog.value.some(row => row.id === item.id)) extraCatalog.value.push(item)
  const existing = props.targets.find(row => row.league_id === item.id && row.season === season)
  await openEditor(existing)
  if (!existing) { form.league_id = item.id; form.season = season; form.include_standings = item.standings }
  await nextTick()
  editorPanel.value?.scrollIntoView({ block: 'start', behavior: 'smooth' })
}

</script>
<template>
  <CatalogPanel ref="catalogPanel" :targets="targets" @select="selectCatalog" @refreshed="emit('refresh')" />
  <div class="mm-workspace" :class="{ 'mm-workspace--split': editorOpen }">
    <section class="mm-panel" aria-label="수집 대상 목록">
      <header class="mm-panel-head"><div><h2>수집 대상</h2><p>리그와 시즌을 선택하고 필요한 데이터를 수집하세요.</p></div><button class="mm-button mm-button--primary" type="button" @click="catalogPanel?.focusSearch()"><Plus :size="16" />대상 추가</button></header>
      <div class="mm-toolbar"><label class="mm-search"><Search :size="16" /><input v-model="query" aria-label="수집 대상 검색" placeholder="리그명, ID 또는 시즌 검색" /></label><select v-model="filter" aria-label="수집 대상 상태"><option value="all">전체 상태</option><option value="active">활성</option><option value="inactive">비활성</option></select></div>
      <div class="mm-table-wrap"><table class="mm-table mm-target-table"><thead><tr><th class="mm-check"><input type="checkbox" aria-label="표시된 활성 대상 전체 선택" :checked="allSelected" :disabled="!selectable.length" @change="toggleAll" /></th><th>리그 · 시즌</th><th>수집 상태</th><th>수집 범위</th><th>최근 수집</th><th>관리</th></tr></thead><tbody><tr v-for="row in rows" :key="row.id" :data-testid="`target-${row.id}`"><td><input type="checkbox" :aria-label="`${row.name} ${row.season} 선택`" :checked="selected.includes(row.id)" :disabled="!row.is_active" @change="toggle(row.id)" /></td><td><div class="mm-identity"><span class="mm-league-icon"><ResourceLogo :src="row.logo_url" :alt="`${row.name} 리그 로고`" kind="league" /></span><div><strong>{{ row.name }}</strong><small>{{ row.season }} 시즌 · {{ row.country }}</small></div></div></td><td><button type="button" :class="['mm-state-switch', { 'mm-state-switch--active': row.is_active }]" :aria-label="`${row.name} ${row.season} ${row.is_active ? '비활성화' : '활성화'}`" @click="changeActive(row)"><i />{{ row.is_active ? '활성' : '비활성' }}</button><small>{{ row.initial_status }}</small></td><td><div class="mm-tags"><span v-if="row.include_details">경기 상세</span><span v-if="row.include_players">선수</span><span v-if="row.include_standings">순위</span></div><small>{{ row.fixture_limit ? `${row.fixture_limit}경기 제한` : '경기 수 제한 없음' }}</small></td><td class="mm-caption">{{ dateTime(row.last_sync) }}</td><td><div class="mm-row-actions"><button class="mm-icon-button" type="button" :aria-label="`${row.name} ${row.season} 편집`" @click="openEditor(row)"><Pencil :size="16" /></button><button class="mm-icon-button" type="button" :aria-label="`${row.name} ${row.season} 수집 대상 제외`" @click="removing = row"><Trash2 :size="16" /></button></div></td></tr></tbody></table></div>
      <div v-if="!rows.length" class="mm-empty"><Search :size="26" /><h3>{{ targets.length ? '조건에 맞는 수집 대상이 없습니다' : '등록된 수집 대상이 없습니다' }}</h3><p>{{ targets.length ? '검색어나 상태 필터를 바꿔보세요.' : '리그와 시즌을 선택해 첫 수집 대상을 추가하세요.' }}</p><button class="mm-button" type="button" @click="targets.length ? (query = '', filter = 'all') : catalogPanel?.focusSearch()">{{ targets.length ? '필터 초기화' : '대상 추가' }}</button></div>
      <footer class="mm-selection"><span><strong>{{ selected.length }}</strong>개 선택 <span class="mm-caption">/ 전체 {{ targets.length }}개</span></span><button class="mm-button mm-button--primary" type="button" :disabled="!selected.length" @click="emit('execute')">선택 대상 수집<ArrowRight :size="15" /></button></footer>
    </section>
    <aside v-if="editorOpen" ref="editorPanel" class="mm-panel mm-editor" aria-label="수집 대상 편집">
      <header class="mm-panel-head"><div><h2>{{ editing ? '수집 설정 편집' : '새 수집 대상' }}</h2><p>설정은 전체 서비스에 적용됩니다.</p></div><button type="button" class="mm-button mm-button--quiet" @click="editorOpen = false">닫기</button></header>
      <form class="mm-form" @submit.prevent="save">
        <label v-if="!editing">카탈로그 검색<input v-model="catalogQuery" placeholder="리그 이름 또는 ID" aria-label="카탈로그 검색" /></label>
        <label>리그<select v-model.number="form.league_id" aria-label="리그" :disabled="!!editing || !visibleCatalog.length" @change="changeLeague"><option :value="0" disabled>리그를 선택하세요</option><option v-for="item in (editing ? allCatalog : visibleCatalog)" :key="item.id" :value="item.id">{{ item.name }} · {{ item.country }}</option></select></label>
        <p v-if="!editing && !visibleCatalog.length" class="mm-note">일치하는 리그가 없습니다. 검색어를 바꿔 다시 선택하세요.</p>
        <label>시즌<select v-model.number="form.season" aria-label="시즌" :disabled="!!editing || !league"><option :value="0" disabled>리그 선택 후 시즌을 확인하세요</option><option v-for="season in league?.seasons ?? []" :key="season" :value="season">{{ season }}{{ season === league?.seasons[0] ? ' · 현재' : ' · 직전 개최 시즌' }}</option></select></label>
        <p class="mm-note">리그별 최신 두 개최 시즌만 수집할 수 있습니다.</p>
        <fieldset class="mm-option-list"><legend>수집할 데이터</legend><label><input v-model="form.include_details" type="checkbox" />경기 상세 <small>이벤트·라인업·경기 통계</small></label><label><input v-model="form.include_players" type="checkbox" />선수 시즌 통계</label><label><input v-model="form.include_standings" type="checkbox" :disabled="!league?.standings" />순위표 <small v-if="!league?.standings">이 대회는 순위표를 제공하지 않습니다.</small></label></fieldset>
        <label>경기 수 제한<input v-model="limitText" type="number" min="1" step="1" placeholder="제한 없음" aria-label="경기 수 제한" /><small>비워두면 제한을 해제합니다. 제한한 수집은 일부 적재로 표시됩니다.</small></label>
        <label class="mm-check-label"><input v-model="form.is_active" type="checkbox" />정기 수집에 포함</label>
        <p v-if="error" class="mm-error-text" role="alert">{{ error }}</p>
        <button class="mm-button mm-button--primary mm-full" type="submit" :disabled="busy || !validSelection">{{ busy ? '저장 중…' : '수집 설정 저장' }}</button>
      </form>
    </aside>
    <ManagementDialog :open="!!removing" title="수집 대상에서 제외할까요?" @close="removing = null"><p><strong>{{ removing?.name }} {{ removing?.season }}</strong>의 향후 수집을 중단하고 대상 설정을 제외합니다.</p><p class="mm-note">이미 적재한 경기·팀·선수 데이터는 삭제하지 않습니다.</p><template #footer><button class="mm-button" type="button" @click="removing = null">돌아가기</button><button class="mm-button mm-button--danger" type="button" @click="remove">수집 대상 제외</button></template></ManagementDialog>
  </div>
</template>
