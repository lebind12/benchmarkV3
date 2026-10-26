<script setup lang="ts">
import { computed } from 'vue'
import type { HomePreview } from '@/lib/api/homePreviewSchema'
const props = defineProps<{ preview: HomePreview | null }>()
const entries = computed(() => (props.preview?.external.predictions.data ?? []).map(item => ({...item, source:props.preview?.sources.find(source => source.id === item.source_id)})))
const articles = computed(() => entries.value.slice(0, 3).filter(item => item.source?.kind === 'web'))
const algorithms = computed(() => entries.value.slice(0, 3).filter(item => {
  if (item.source?.kind !== 'api' || !item.source.url) return false
  const url = new URL(item.source.url)
  return url.hostname === 'v3.football.api-sports.io' && url.pathname === '/predictions'
}))
const webCount = computed(() => new Set(articles.value.map(item => item.source?.url ? new URL(item.source.url).hostname.replace(/^www\./,'').replace(/^bbc\.co\.uk$/,'bbc.com') : item.source_id)).size)
const count = computed(() => webCount.value + (algorithms.value.length ? 1 : 0))
function when(value: string | null | undefined) { return value ? new Intl.DateTimeFormat('ko-KR',{timeZone:'Asia/Seoul',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(value)) : '' }
</script>
<template>
  <section id="preview-external" tabindex="-1">
    <header class="hp-subhead"><h3>외부 사이트 전망</h3><span data-testid="forecast-coverage">전망 {{ count }}/3개 확인</span></header>
    <p v-if="count < 3" class="hp-inline-note">{{ count === 0 ? '확인된 매체 전망이 아직 없습니다.' : '확인된 매체 전망만 표시합니다.' }}</p>
    <div v-for="item in articles" :key="item.source_id" class="hp-external" data-testid="media-forecast">
      <span>{{ item.source?.title.split(' | ')[0] }}</span><b>{{ item.outlook }}</b><p>{{ item.summary }}</p>
      <details><summary>출처와 자료 시점</summary><a :href="item.source?.url ?? undefined" target="_blank" rel="noopener noreferrer">{{ item.source?.title }}</a><small v-if="item.source?.published_at">기사 {{ when(item.source.published_at) }} KST</small><small v-else>확인 {{ when(item.source?.retrieved_at) }} KST</small></details>
    </div>
    <div v-for="item in algorithms" :key="item.source_id" class="hp-external hp-algorithm-forecast" data-testid="algorithm-forecast">
      <span>API-Football 자체 예측</span><b>{{ item.outlook }}</b><p>{{ item.summary }}</p><details><summary>자료 시점</summary><small>{{ when(item.source?.retrieved_at) }} KST</small></details>
    </div>
  </section>
</template>
