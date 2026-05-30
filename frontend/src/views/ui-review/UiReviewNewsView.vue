<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ExternalLink, Newspaper, RefreshCw } from 'lucide-vue-next'
import { generalApi } from '@/lib/api/general'
import type { NewsItem } from '@/types/home'
import { relativeFromNow } from '@/lib/format/datetime'

const news = ref<NewsItem[]>([])
const status = ref<'idle' | 'loading' | 'ok' | 'error'>('idle')
const error = ref<string | null>(null)

const lead = computed(() => news.value[0] ?? null)
const sideItems = computed(() => news.value.slice(1, 12))
const gridItems = computed(() => news.value.slice(12, 40))
const sourceCount = computed(() => new Set(news.value.map((item) => item.source)).size)

function title(item: NewsItem): string {
  return item.title_ko ?? item.title
}

function summary(item: NewsItem): string {
  return item.summary_ko ?? item.title
}

async function loadNews() {
  status.value = 'loading'
  error.value = null
  try {
    news.value = (await generalApi.news(40)).items
    status.value = 'ok'
  } catch (err) {
    news.value = []
    error.value = (err as Error).message
    status.value = 'error'
  }
}

onMounted(() => {
  void loadNews()
})
</script>

<template>
  <main class="news-page app-container" data-testid="ui-review-news-page">
    <header class="page-head">
      <div>
        <span class="eyebrow">뉴스룸</span>
        <h1>주요 기사와 최신 뉴스를 분리한 편집형 화면</h1>
        <p>{{ news.length }}개 기사 · {{ sourceCount }}개 출처</p>
      </div>
      <button type="button" class="reload" @click="loadNews">
        <RefreshCw :size="15" aria-hidden="true" />
        새로고침
      </button>
    </header>

    <div v-if="status === 'loading'" class="state">뉴스를 불러오는 중입니다.</div>
    <div v-else-if="status === 'error'" class="state state--error">{{ error }}</div>
    <div v-else-if="news.length === 0" class="state">적재된 뉴스가 없습니다.</div>

    <section v-else class="news-layout" aria-label="뉴스 후보 레이아웃">
      <article v-if="lead" class="lead-card">
        <div v-if="lead.thumbnail_url" class="lead-media">
          <img :src="lead.thumbnail_url" alt="" />
        </div>
        <div v-else class="lead-media lead-media--fallback">
          <Newspaper :size="42" aria-hidden="true" />
          <span>{{ lead.source }}</span>
        </div>
        <div class="lead-copy">
          <span>{{ lead.source }} · {{ relativeFromNow(lead.published_at) }}</span>
          <h2>{{ title(lead) }}</h2>
          <p>{{ summary(lead) }}</p>
          <a :href="lead.url" target="_blank" rel="noreferrer">
            원문 보기
            <ExternalLink :size="14" aria-hidden="true" />
          </a>
        </div>
      </article>

      <aside class="latest-panel">
        <header class="panel-head">
          <strong>최신 기사</strong>
          <span>{{ sideItems.length }}개</span>
        </header>
        <div class="latest-list">
          <a
            v-for="item in sideItems"
            :key="item.id"
            :href="item.url"
            target="_blank"
            rel="noreferrer"
            class="latest-row"
          >
            <span>{{ item.source }} · {{ relativeFromNow(item.published_at) }}</span>
            <strong>{{ title(item) }}</strong>
          </a>
        </div>
      </aside>

      <section class="grid-panel">
        <header class="panel-head">
          <strong>브리핑</strong>
          <span>compact cards</span>
        </header>
        <div class="brief-grid">
          <article v-for="item in gridItems" :key="item.id" class="brief-card">
            <span>{{ item.source }}</span>
            <h3>{{ title(item) }}</h3>
            <p>{{ summary(item) }}</p>
            <a :href="item.url" target="_blank" rel="noreferrer">원문</a>
          </article>
        </div>
      </section>
    </section>
  </main>
</template>

<style scoped>
.news-page {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 12px;
  height: calc(100vh - var(--header-height));
  min-height: 0;
  overflow: hidden;
  padding-block: 16px;
}

.page-head,
.lead-card,
.latest-panel,
.grid-panel,
.state {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-card);
}

.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px;
}

.eyebrow {
  display: block;
  margin-bottom: 4px;
  color: var(--color-muted);
  font-size: 11px;
  font-weight: 900;
  text-transform: uppercase;
}

h1 {
  margin: 0;
  color: var(--color-fg);
  font-size: 22px;
}

.page-head p {
  margin: 6px 0 0;
  color: var(--color-muted);
  font-size: 12px;
}

.reload {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 36px;
  border: 1px solid var(--color-border);
  border-radius: 999px;
  padding: 0 12px;
  color: var(--color-fg);
  background: var(--color-bg);
  cursor: pointer;
}

.news-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(320px, 0.8fr);
  grid-template-rows: minmax(230px, 0.9fr) minmax(0, 1fr);
  gap: 12px;
  min-height: 0;
  overflow: hidden;
}

.lead-card {
  display: grid;
  grid-template-columns: minmax(300px, 0.86fr) minmax(0, 1fr);
  grid-column: 1 / 3;
  min-height: 0;
  overflow: hidden;
}

.lead-media {
  min-height: 0;
  background: var(--color-bg);
}

.lead-media img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.lead-media--fallback {
  display: grid;
  place-items: center;
  align-content: center;
  gap: 12px;
  color: var(--color-muted);
  background:
    linear-gradient(135deg, rgb(56 189 248 / 0.18), transparent 58%),
    var(--color-bg);
}

.lead-media--fallback span {
  font-weight: 900;
}

.lead-copy {
  display: grid;
  align-content: center;
  gap: 10px;
  min-width: 0;
  min-height: 0;
  padding: 22px;
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-width: none;
}

.lead-copy::-webkit-scrollbar,
.latest-list::-webkit-scrollbar,
.brief-grid::-webkit-scrollbar {
  display: none;
}

.lead-copy span,
.latest-row span,
.brief-card span,
.panel-head span {
  color: var(--color-muted);
  font-size: 11px;
  font-weight: 800;
}

.lead-copy h2 {
  margin: 0;
  color: var(--color-fg);
  font-size: 28px;
  line-height: 1.2;
}

.lead-copy p {
  margin: 0;
  color: var(--color-muted);
  line-height: 1.55;
}

a {
  color: var(--color-fg);
  text-decoration: none;
}

.lead-copy a {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  width: fit-content;
  font-weight: 900;
}

.latest-panel,
.grid-panel {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  min-height: 0;
  overflow: hidden;
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 42px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-bg);
}

.panel-head strong {
  color: var(--color-fg);
  font-size: 13px;
}

.latest-list {
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-width: none;
}

.latest-row {
  display: grid;
  gap: 4px;
  border-bottom: 1px solid var(--color-border);
  padding: 12px;
}

.latest-row strong {
  overflow: hidden;
  color: var(--color-fg);
  font-size: 13px;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.brief-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  min-height: 0;
  overflow: auto;
  padding: 12px;
  scrollbar-width: none;
}

.brief-card {
  display: grid;
  align-content: start;
  gap: 7px;
  min-height: 148px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 11px;
  background: var(--color-bg);
}

.brief-card h3 {
  display: -webkit-box;
  margin: 0;
  overflow: hidden;
  color: var(--color-fg);
  font-size: 14px;
  line-height: 1.35;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.brief-card p {
  display: -webkit-box;
  margin: 0;
  overflow: hidden;
  color: var(--color-muted);
  font-size: 12px;
  line-height: 1.45;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
}

.brief-card a {
  margin-top: auto;
  color: var(--color-fg);
  font-size: 12px;
  font-weight: 900;
}

.state {
  display: grid;
  place-items: center;
  color: var(--color-muted);
}

.state--error {
  color: #b91c1c;
}
</style>
