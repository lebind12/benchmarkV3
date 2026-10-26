<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'
import { Search, RefreshCw, ChevronRight, X } from 'lucide-vue-next'
import { useManagementApi, type CatalogLeague, type CatalogSyncResult, type CollectionTarget } from '@/lib/api/management'
import ManagementDialog from './ManagementDialog.vue'
import ResourceLogo from './ResourceLogo.vue'
import TeamScopeSelect from './TeamScopeSelect.vue'
import { dateTime } from './display'
const api = useManagementApi()
const props = defineProps<{ targets: CollectionTarget[] }>()
const emit = defineEmits<{ select: [league: CatalogLeague, season: number]; refreshed: [] }>()
const query = ref(''), id = ref(''), country = ref(''), kind = ref(''), group = ref('')
const input = ref<HTMLInputElement | null>(null), panel = ref<HTMLElement | null>(null)
const items = ref<CatalogLeague[]>([])
const countries = ref<{value:string;label:string}[]>([])
const updatedAt = ref<string | null>(null)
const total = ref(0), page = ref(1), pageSize = 20
const searching = ref(false), syncing = ref(false), confirm = ref(false), opened = ref(false)
const active = ref(0), error = ref(''), requeried = ref(false)
const result = ref<CatalogSyncResult | null>(null)
const listId = `catalog-suggestions-${useId()}`
const suggestions = computed(() => items.value.slice(0, 6))
const countryOptions = computed(() => [...countries.value].sort((a,b) => Number(/[가-힣]/.test(b.label))-Number(/[가-힣]/.test(a.label)) || a.label.localeCompare(b.label,'ko')).map(item=>({id:item.value,name:item.label,name_en:item.value,aliases:({'South-Korea':['한국','남한'],World:['세계','국제']} as Record<string,string[]>)[item.value] ?? []})))
const registered = (league: CatalogLeague) => props.targets.some(t => t.league_id === league.id)
let generation = 0, timer: ReturnType<typeof setTimeout> | undefined
async function search() {
  clearTimeout(timer)
  const generationId = ++generation
  error.value = ''; searching.value = true; items.value = []; total.value = 0; active.value = 0
  if (id.value.trim() && !/^[1-9]\d*$/.test(id.value.trim())) { error.value = '리그 ID는 1 이상의 숫자로 입력하세요.'; searching.value = false; return false }
  try {
    const data = await api.catalog({ query: id.value.trim() ? '' : query.value.trim(), id: id.value.trim() ? Number(id.value) : undefined, country: country.value, type: kind.value, group: group.value, page:page.value, page_size:pageSize })
    if (generationId !== generation) return false
    items.value = data.items; total.value = data.total; countries.value = data.countries; updatedAt.value = data.updated_at
    return true
  } catch (err) { if (generationId === generation) error.value = err instanceof Error ? err.message : '대회를 불러오지 못했습니다. 다시 검색하세요.'; return false }
  finally { if (generationId === generation) searching.value = false }
}
watch([query, id, country, kind, group], () => {
  generation++; items.value = []; total.value = 0; searching.value = true; page.value = 1; active.value = 0
  clearTimeout(timer); timer = setTimeout(search, 250)
})
function typing() { id.value = ''; opened.value = true }
function changeFilter() { id.value = ''; opened.value = false }
function reset() { query.value = ''; id.value = ''; country.value = ''; kind.value = ''; group.value = ''; page.value = 1; opened.value = false; void nextTick(search) }
function shortcut(value:string) { group.value = group.value === value ? '' : value; query.value = ''; id.value = ''; opened.value = false }
function choose(league:CatalogLeague) { query.value = league.name; id.value = String(league.id); page.value = 1; opened.value = false; void nextTick(search) }
function move(amount:number) { opened.value = true; active.value = Math.max(0,Math.min(suggestions.value.length-1,active.value+amount)); void nextTick(() => document.getElementById(`${listId}-${active.value}`)?.scrollIntoView({block:'nearest'})) }
function submit() { if(opened.value && suggestions.value[active.value]) choose(suggestions.value[active.value]!); else {opened.value=false; void search()} }
function blur(event:FocusEvent) { if (!(event.currentTarget as HTMLElement).contains(event.relatedTarget as Node | null)) opened.value=false }
async function sync() {
  confirm.value = false; syncing.value = true; result.value = null; requeried.value = false; error.value = ''; opened.value = false
  generation++; clearTimeout(timer)
  try { result.value = await api.refreshCatalog(); requeried.value = await search(); emit('refreshed') }
  catch (err) { error.value = err instanceof Error ? err.message : '최신화하지 못했습니다. 기존 카탈로그는 유지됩니다.' }
  finally { syncing.value = false }
}
function focusSearch() { panel.value?.scrollIntoView({ block: 'start', behavior: 'smooth' }); input.value?.focus({ preventScroll: true }); opened.value=true }
function goPage(value:number) {page.value=value; opened.value=false; void search()}
defineExpose({ focusSearch })
onMounted(search)
onBeforeUnmount(() => { generation++; clearTimeout(timer) })
</script>
<template>
  <section ref="panel" class="mm-panel mm-catalog-panel" aria-label="리그 시즌 카탈로그">
    <header class="mm-panel-head"><div><h2>대회 찾아 추가하기</h2><p>한국어 이름으로 찾고, 국가와 시즌을 확인하세요.</p></div><button class="mm-button" type="button" :disabled="syncing || searching" @click="confirm = true"><RefreshCw :size="14" />{{ syncing ? '카탈로그 최신화 중…' : '카탈로그 최신화' }}</button></header>
    <div class="mm-discovery">
      <form @submit.prevent="submit">
        <div class="mm-catalog-search-area" @focusout="blur" @keydown.esc.prevent="opened=false">
          <div class="mm-catalog-search-line"><label class="mm-search"><Search :size="18" /><input ref="input" v-model="query" role="combobox" autocomplete="off" maxlength="120" aria-label="카탈로그 검색어" :aria-expanded="opened && (searching || suggestions.length>0)" :aria-controls="opened && (searching || suggestions.length) ? listId : undefined" :aria-activedescendant="opened && suggestions.length ? `${listId}-${active}` : undefined" aria-autocomplete="list" :disabled="syncing" placeholder="아시안컵, 동아시아, EPL…" @input="typing" @focus="opened=true" @keydown.enter.prevent="submit" @keydown.down.prevent="move(1)" @keydown.up.prevent="move(-1)" /></label><button type="button" class="mm-button mm-button--primary" :disabled="syncing" @click="opened=false; search()">대회 검색</button></div>
          <div v-if="opened && (searching || suggestions.length)" class="mm-catalog-suggestions">
            <div class="mm-between mm-caption"><strong>{{ query.trim() ? '검색어와 일치하는 대회' : '추천 대회' }}</strong><button type="button" class="mm-icon-button" aria-label="추천 닫기" @click="opened=false"><X :size="14" /></button></div>
            <p v-if="searching" role="status" class="mm-caption">대회 찾는 중…</p>
            <div :id="listId" role="listbox" aria-label="대회 검색 추천"><button v-for="(league,index) in suggestions" :id="`${listId}-${index}`" :key="league.id" type="button" role="option" :aria-selected="active===index" :class="['mm-catalog-suggestion',{active:active===index}]" @pointermove="active=index" @mousedown.prevent @click="choose(league)"><ResourceLogo :src="league.logo_url" :alt="`${league.name} 리그 로고`" kind="league" /><span><strong>{{ league.name }}</strong><small>{{ league.name_en }} · {{ league.country_label || league.country }} · {{ league.type === 'Cup' ? '컵대회' : '리그' }}</small></span><span v-if="registered(league)" class="mm-badge">등록됨</span><ChevronRight :size="15" /></button></div>
          </div>
          <p v-if="!searching && !items.length && !error" class="mm-caption">일치하는 대회가 없습니다. 검색어·국가 조건을 바꾸거나 목록을 최신화하세요.</p>
        </div>
        <div class="mm-catalog-filters"><div class="mm-catalog-country"><span>국가·지역</span><TeamScopeSelect v-model="country" label="카탈로그 국가" :options="countryOptions" all-label="전체 국가·국제대회" search-placeholder="국가·지역 이름 검색" :show-logos="false" :disabled="syncing || !countries.length" @update:model-value="changeFilter" /></div><label>대회 종류<select v-model="kind" aria-label="카탈로그 대회 종류" :disabled="syncing" @change="changeFilter"><option value="">전체 종류</option><option value="League">리그</option><option value="Cup">컵대회</option></select></label><button class="mm-button mm-button--quiet" type="button" :disabled="syncing" @click="reset">검색 조건 초기화</button></div>
        <div class="mm-catalog-shortcuts" aria-label="주요 대회 바로가기"><span class="mm-caption">주요 대회</span><button v-for="item in [{id:'national',name:'국가대표 대회'},{id:'asia',name:'아시아 대회'},{id:'club',name:'클럽 컵대회'}]" :key="item.id" type="button" :aria-pressed="group===item.id" :class="['mm-button',{'mm-button--primary':group===item.id}]" :disabled="syncing" @click="shortcut(item.id)">{{ item.name }}</button></div>
        <details class="mm-catalog-advanced"><summary>리그 ID로 찾기</summary><label>리그 ID<input v-model="id" :disabled="syncing" aria-label="카탈로그 리그 ID" inputmode="numeric" placeholder="예: 39" /></label><p class="mm-caption">ID 입력 시 이름보다 우선합니다. 국가·종류 조건은 함께 적용됩니다.</p></details>
      </form>
      <p class="mm-caption">추천은 저장된 카탈로그 기준입니다. 대회 선택 후 지원 시즌을 확인하세요. 목록 최신화는 경기 수집이나 대상 등록을 실행하지 않습니다.</p>
      <p class="mm-caption">마지막 최신화: {{ updatedAt ? dateTime(updatedAt) : '기록 없음' }}</p>
    </div>
    <p v-if="syncing" class="mm-inline-banner" role="status">외부 목록 확인 → 카탈로그 저장 → 검색 결과 다시 조회 중입니다. </p>
    <p v-if="result" class="mm-inline-banner" role="status">카탈로그 최신화 완료 · API {{ result.api_count }}건 확인 · {{ result.synced_count }}건 저장 · DB 총 {{ result.catalog_count }}건 · {{ requeried ? '검색 결과를 다시 조회했습니다.' : '저장은 완료했으나 검색 결과를 다시 조회하지 못했습니다. 대회 검색으로 재시도하세요.' }}</p>
    <p v-if="error" class="mm-error-text mm-catalog-note" role="alert">{{ error }}</p>
    <div class="mm-panel-foot mm-between"><strong>검색 결과 {{ total }}개</strong><span>대회 → 시즌 → 수집 설정</span></div>
    <div v-if="items.length" class="mm-catalog-results"><article v-for="league in items" :key="league.id" class="mm-catalog-row"><div class="mm-identity"><ResourceLogo :src="league.logo_url" :alt="`${league.name} 리그 로고`" kind="league" /><div><strong>{{ league.name }} <span class="mm-badge">{{ league.country_label || league.country }}</span> <span class="mm-badge">{{ league.type === 'Cup' ? '컵대회' : '리그' }}</span></strong><small>{{ league.name_en }} · #{{ league.id }}</small></div></div><div class="mm-catalog-seasons"><button v-for="season in league.seasons" :key="season" class="mm-button" type="button" :aria-label="`${league.name} ${season} 시즌 설정`" :disabled="syncing" @click="emit('select', league, season)">{{ season }}<small>{{ props.targets.some(t => t.league_id === league.id && t.season === season) ? '등록됨 · 설정 편집' : '수집 대상 추가' }}</small></button><span v-if="!league.seasons.length" class="mm-caption">지원 시즌 없음</span></div></article></div>
    <div v-else class="mm-panel-foot" role="status">{{ searching ? '대회 찾는 중…' : '조회 결과가 없습니다. 검색 조건을 바꾸거나 카탈로그를 최신화하세요.' }}</div>
    <div v-if="total>pageSize" class="mm-panel-foot mm-between"><button type="button" class="mm-button" :disabled="page<=1 || searching || syncing" @click="goPage(page-1)">이전 대회 목록</button><span>{{ page }} / {{ Math.ceil(total/pageSize) }}</span><button type="button" class="mm-button" :disabled="page*pageSize>=total || searching || syncing" @click="goPage(page+1)">다음 대회 목록</button></div>
    <ManagementDialog :open="confirm" title="리그·시즌 카탈로그를 최신화할까요?" @close="confirm = false"><p>API-Football에서 전체 리그·시즌 목록을 확인하고 공유 카탈로그에 저장합니다. 완료 후 현재 검색 조건으로 다시 조회합니다.</p><p class="mm-note">경기 데이터 수집은 별도로 실행합니다. 최신화는 전체 서비스가 함께 사용하는 카탈로그를 변경하며 외부 API 호출량을 사용합니다.</p><template #footer><button class="mm-button" type="button" @click="confirm = false">돌아가기</button><button class="mm-button mm-button--primary" type="button" @click="sync">최신화 실행</button></template></ManagementDialog>
  </section>
</template>
<style scoped>
.mm-discovery { padding: 20px; }
.mm-catalog-panel { overflow:visible; }
.mm-catalog-search-area { position:relative; }
.mm-catalog-search-line { display:flex; gap:8px; }
.mm-catalog-search-line .mm-search { flex:1; min-width:0; }
.mm-catalog-search-line input { width:100%; }
.mm-catalog-suggestions { position:absolute; top:calc(100% + 6px); left:0; right:0; z-index:40; max-height:360px; overflow-y:auto; border:1px solid var(--color-border); border-radius:8px; padding:8px; background:var(--color-bg); box-shadow:0 12px 28px #0002; }
.mm-catalog-suggestion { display:flex; align-items:center; gap:12px; width:100%; border:0; border-radius:5px; background:transparent; color:var(--color-fg); padding:10px; text-align:left; font:inherit; cursor:pointer; }
.mm-catalog-suggestion>span:nth-child(2) { flex:1; min-width:0; }
.mm-catalog-suggestion strong { font-size:13px; }
.mm-catalog-suggestion small { display:block; margin-top:4px; font-size:11px; color:var(--color-muted); overflow-wrap:anywhere; }
.mm-catalog-suggestion.active { background:var(--color-card); box-shadow:inset 3px 0 #2563eb; }
.mm-catalog-filters { display:flex; align-items:end; gap:12px; margin-top:16px; flex-wrap:wrap; }
.mm-catalog-country { display:grid; gap:6px; font-size:12px; flex:1; min-width:150px; }
.mm-catalog-filters label { display:grid; gap:6px; font-size:12px; flex:1; min-width:150px; }
.mm-catalog-filters select,.mm-catalog-advanced input { min-height:38px; padding:8px; background:var(--color-bg); color:var(--color-fg); border:1px solid var(--color-border); border-radius:6px; font:inherit; }
.mm-catalog-shortcuts { display:flex; gap:8px; flex-wrap:wrap; align-items:center; margin-top:16px; }
.mm-catalog-shortcuts .mm-button { font-size:12px; }
.mm-catalog-advanced { margin-block:16px; font-size:12px; color:var(--color-muted); }
.mm-catalog-advanced summary { cursor:pointer; }
.mm-catalog-advanced label { display:flex; gap:10px; align-items:center; margin-top:10px; }
.mm-catalog-advanced input { width:130px; }
@media(max-width:600px) { .mm-discovery { padding:14px; } .mm-catalog-country { display:grid; gap:6px; font-size:12px; flex:1; min-width:150px; }
.mm-catalog-filters label { min-width:130px; } .mm-catalog-suggestion { gap:8px; padding:8px 4px; } }
</style>
