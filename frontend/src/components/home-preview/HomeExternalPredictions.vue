<script setup lang="ts">
import { computed } from 'vue'
import type { HomePreview } from '@/lib/api/homePreviewSchema'
const props = defineProps<{ preview: HomePreview | null }>()
const entries = computed(() => (props.preview?.external.predictions.data ?? []).map(item => ({...item, source:props.preview?.sources.find(source => source.id === item.source_id)})))
const articles = computed(() => entries.value.filter(item => item.source?.kind === 'web'))
const algorithms = computed(() => entries.value.filter(item => item.source?.kind !== 'web'))
const count = computed(() => new Set(articles.value.map(item => item.source?.url ? new URL(item.source.url).hostname.replace(/^www\./,'').replace(/^bbc\.co\.uk$/,'bbc.com') : item.source_id)).size)
function when(value: string | null | undefined) { return value ? new Intl.DateTimeFormat('ko-KR',{timeZone:'Asia/Seoul',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(value)) : '' }
</script>
<template>
  <section id="preview-external" tabindex="-1">
    <header class="hp-subhead"><h3>외부 사이트 전망</h3><span data-testid="forecast-coverage">매체 {{ count }}/3곳 확인</span></header>
    <p v-if="count < 3" class="hp-inline-note">{{ count === 0 ? '확인된 매체 전망이 아직 없습니다.' : '확인된 매체 전망만 표시합니다.' }}</p>
    <div v-for="item in articles" :key="item.source_id" class="hp-external" data-testid="media-forecast">
      <a :href="item.source?.url ?? undefined" target="_blank" rel="noopener noreferrer">{{ item.source?.title }}</a><b>{{ item.outlook }}</b><p>{{ item.summary }}</p>
      <small v-if="item.source?.published_at">기사 {{ when(item.source.published_at) }} KST</small><small v-else>확인 {{ when(item.source?.retrieved_at) }} KST</small>
    </div>
    <div v-for="item in algorithms" :key="item.source_id" class="hp-external hp-algorithm-forecast" data-testid="algorithm-forecast">
      <span>API-Football 자체 예측 · 매체 수에 포함하지 않음</span><b>{{ item.outlook }}</b><p>{{ item.summary }}</p><small>자료 {{ when(item.source?.retrieved_at) }} KST</small>
    </div>
  </section>
</template>
