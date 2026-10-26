<script setup lang="ts">
import { computed, ref, useId, watch } from 'vue'
import { ChevronRight } from 'lucide-vue-next'
import type { CollectionRun } from '@/lib/api/managementTypes'
import { dateTime } from './display'
import { logStatistics, presentLog } from './logPresentation'
const props = defineProps<{ run: CollectionRun }>()
const level = ref('all')
const cause = ref('all')
const expanded = ref<Record<string, boolean>>({})
const uid = useId()
const order = ['run','preparation','catalog','teams','fixtures','standings','players','events','lineups','statistics','fixture_players','details','error','unclassified']
const entries = computed(() => props.run.logs.map((log,index) => ({log,view:presentLog(log),index})))
const statistics = computed(() => logStatistics([props.run]))
const groups = computed(() => {
  const result = new Map<string,{code:string;label:string;total:number;rows:typeof entries.value;errors:number;warnings:number}>()
  for (const row of entries.value) {
    const code = row.view.category
    const group = result.get(code) ?? {code,label:row.view.category_label,total:0,rows:[],errors:0,warnings:0}
    group.total++
    if ((level.value === 'all' || level.value === row.view.level) && (cause.value === 'all' || cause.value === row.view.code)) {
      group.rows.push(row)
      if(row.view.level==='error') group.errors++
      if(row.view.level==='warning') group.warnings++
    }
    result.set(code,group)
  }
  return [...result.values()].filter(group=>group.rows.length).sort((a,b)=>(order.indexOf(a.code)<0?99:order.indexOf(a.code))-(order.indexOf(b.code)<0?99:order.indexOf(b.code))).map(group=>{
    group.rows.sort((a,b)=>{
      const first=Date.parse(a.log.at),second=Date.parse(b.log.at)
      return Number.isFinite(first)&&Number.isFinite(second) ? first-second || a.index-b.index : a.index-b.index
    })
    return group
  })
})
const visibleCount = computed(()=>groups.value.reduce((sum,group)=>sum+group.rows.length,0))
function expandMatches() { if(level.value!=='all') for(const group of groups.value) expanded.value[group.code]=true }
function filterCause(code:string) {
  cause.value = cause.value === code ? 'all' : code
  level.value = 'all'
  if(cause.value!=='all') for(const group of groups.value) expanded.value[group.code]=true
}
watch(()=>props.run.id,()=>{expanded.value={};level.value='all';cause.value='all'})
</script>
<template>
  <section class="mm-log-analysis" aria-label="실패 로그 분석">
    <h3>로그 원인별 통계</h3>
    <div v-if="statistics.groups.length" class="mm-cause-list"><button v-for="group in statistics.groups" :key="group.code" type="button" :class="['mm-cause-button', { selected: cause === group.code }]" @click="filterCause(group.code)"><strong>{{ group.title }}</strong><span>오류 {{ group.errors }} · 재시도·경고 {{ group.warnings }}</span></button></div>
    <p v-else class="mm-caption">분류할 수 있는 오류·경고 로그가 없습니다.</p>
    <p class="mm-caption">{{ run.log_statistics && run.log_statistics_scope !== 'retained' ? '전체 실행에서 누적한 로그 발생 건수입니다.' : '기록된 로그 발생 건수입니다.' }} 같은 요청의 재시도가 포함되며 실패 데이터 건수와 다릅니다. 수준·원인 정보가 없는 원문 {{ statistics.unknown }}건은 원인 통계에서 제외합니다.</p>
    <p v-if="run.log_counts?.dropped" class="mm-note">전체 {{ run.log_counts.total }}건 중 최근 {{ run.log_counts.retained }}건을 보관합니다. 원인 통계에는 생략한 {{ run.log_counts.dropped }}건도 포함합니다.</p>
    <div class="mm-toolbar mm-toolbar--wrap"><h3>종류별 처리 로그</h3><select v-model="level" aria-label="로그 수준" @change="expandMatches"><option value="all">전체 로그</option><option value="error">실패 로그만</option><option value="warning">재시도·경고만</option></select><button v-if="cause !== 'all'" class="mm-button mm-button--quiet" type="button" @click="cause = 'all'">원인 필터 해제</button><button class="mm-button mm-button--quiet" type="button" :disabled="groups.every(group=>!expanded[group.code])" @click="expanded={}">전체 접기</button><span class="mm-caption">{{ groups.length }}개 종류 · {{ visibleCount }}건</span></div>
    <p class="mm-caption">로그가 있는 종류만 표시합니다. 섹션을 펼치면 같은 종류의 로그를 시간순으로 확인할 수 있습니다.</p>
    <div v-if="!groups.length" class="mm-inline-banner">{{ run.logs.length ? '조건에 맞는 로그가 없습니다. 전체 로그를 선택하거나 원인 필터를 해제하세요.' : '아직 수집 로그가 없습니다. 로그가 도착하면 해당 종류의 섹션이 표시됩니다.' }}</div>
    <section v-for="group in groups" :key="group.code" class="mm-log-group" :class="{'mm-log-group--error':group.errors,'mm-log-group--warning':!group.errors && group.warnings}" :data-testid="`log-group-${group.code}`">
      <h4><button type="button" class="mm-log-group-toggle" :aria-expanded="!!expanded[group.code]" :aria-controls="expanded[group.code] ? `${uid}-${group.code}` : undefined" @click="expanded[group.code]=!expanded[group.code]"><ChevronRight :size="16" aria-hidden="true" :class="{'mm-log-chevron-open':expanded[group.code]}" /><strong>{{ group.label }}</strong><span class="mm-log-group-count">{{ group.rows.length }}건<small v-if="group.total!==group.rows.length"> / 전체 {{ group.total }}건</small></span><span v-if="group.errors" class="mm-badge mm-badge--failed">오류 {{ group.errors }}</span><span v-if="group.warnings" class="mm-badge mm-badge--pending">경고 {{ group.warnings }}</span></button></h4>
      <ol v-if="expanded[group.code]" :id="`${uid}-${group.code}`" class="mm-event-list" :aria-label="`${group.label} 로그`"><li v-for="{log,view,index} in group.rows" :key="`${log.at}-${log.message}-${index}`" :class="`mm-event--${view.level}`"><div class="mm-between"><strong>{{ view.title }}</strong><span class="mm-badge">{{ view.level === 'error' ? '오류' : view.level === 'warning' ? '재시도·경고' : '정보' }}</span></div><p class="mm-caption">{{ dateTime(log.at) }}<template v-if="log.target_id !== undefined"> · {{ run.items.find(item => item.target_id === log.target_id)?.name ?? `대상 #${log.target_id}` }} {{ run.items.find(item => item.target_id === log.target_id)?.season }}</template><template v-else-if="view.target"> · {{ view.target }}</template><template v-if="view.stage"> · {{ view.stage }}</template><template v-if="log.attempt"> · 시도 {{ log.attempt }}/{{ log.max_attempts ?? '?' }}</template></p><p v-if="view.action">{{ view.action }}</p><details><summary>원문 보기</summary><pre>{{ log.message }}</pre><small v-if="log.code">이벤트 코드: {{ log.code }}</small></details></li></ol>
    </section>
  </section>
</template>
<style scoped>
.mm-log-group { border:1px solid var(--color-border); border-radius:8px; margin-top:10px; overflow:hidden; }
.mm-log-group h4 { margin:0; font:inherit; }
.mm-log-group-toggle { display:flex; align-items:center; gap:10px; width:100%; padding:14px; border:0; background:var(--color-card); color:var(--color-fg); text-align:left; font:inherit; cursor:pointer; }
.mm-log-group-toggle strong { font-size:13px; }
.mm-log-group-count { margin-left:auto; font-size:12px; white-space:nowrap; color:var(--color-muted); }
.mm-log-group-count small { font-size:11px; }
.mm-log-group--error { border-left:3px solid #dc2626; }
.mm-log-group--warning { border-left:3px solid #d97706; }
.mm-log-chevron-open { transform:rotate(90deg); }
.mm-log-group .mm-event-list { padding:12px; max-height:360px; border-top:1px solid var(--color-border); }
.mm-log-group-toggle:focus-visible { outline:2px solid #2563eb; outline-offset:-3px; }
@media(max-width:600px) { .mm-log-group-toggle { gap:7px; padding:12px; flex-wrap:wrap; } .mm-log-group-toggle .mm-badge { font-size:10px; } }
</style>
