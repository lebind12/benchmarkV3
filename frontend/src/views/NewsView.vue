<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ExternalLink } from 'lucide-vue-next'
import { generalApi } from '@/lib/api/general'
import type { NewsItem } from '@/types/home'
import { relativeFromNow } from '@/lib/format/datetime'

const news = ref<NewsItem[]>([])
const status = ref<'idle' | 'loading' | 'ok' | 'error'>('idle')
const error = ref<string | null>(null)

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
  <main class="page app-container">
    <header class="page__header">
      <div>
        <p class="eyebrow">News</p>
        <h1>뉴스</h1>
      </div>
      <button type="button" class="reload" @click="loadNews">새로고침</button>
    </header>

    <div v-if="status === 'loading'" class="state">뉴스를 불러오는 중입니다.</div>
    <div v-else-if="status === 'error'" class="state state--error">{{ error }}</div>
    <div v-else-if="news.length === 0" class="state">적재된 뉴스가 없습니다.</div>
    <section v-else class="news-list">
      <article
        v-for="item in news"
        :key="item.id"
        class="news-card"
        :class="{ 'news-card--text-only': !item.thumbnail_url }"
      >
        <img v-if="item.thumbnail_url" :src="item.thumbnail_url" alt="" />
        <div>
          <span>{{ item.source }} · {{ relativeFromNow(item.published_at) }}</span>
          <h2>{{ item.title_ko ?? item.title }}</h2>
          <p>{{ item.summary_ko ?? item.title }}</p>
          <a :href="item.url" target="_blank" rel="noreferrer">
            원문
            <ExternalLink :size="14" />
          </a>
        </div>
      </article>
    </section>
  </main>
</template>

<style scoped>
.page {
  height: calc(100vh - var(--header-height));
  overflow-y: auto;
  padding-block: 24px 48px;
}
.page__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
}
.eyebrow {
  margin: 0 0 4px;
  color: var(--color-muted);
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0;
}
h1 {
  margin: 0;
  font-size: 28px;
}
.reload {
  height: 36px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: var(--color-card);
  cursor: pointer;
}
.news-list {
  display: grid;
  gap: 12px;
}
.news-card {
  display: grid;
  grid-template-columns: 180px 1fr;
  gap: 16px;
  padding: 14px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-card);
}
.news-card--text-only {
  grid-template-columns: minmax(0, 1fr);
}
.news-card > div {
  min-width: 0;
}
.news-card img {
  width: 100%;
  height: 112px;
  object-fit: cover;
  border-radius: 6px;
}
.news-card span {
  color: var(--color-muted);
  font-size: 12px;
}
h2 {
  margin: 4px 0 8px;
  font-size: 17px;
}
p {
  margin: 0 0 12px;
  color: var(--color-muted);
  line-height: 1.45;
}
a {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  text-decoration: none;
  font-weight: 600;
}
.state {
  padding: 28px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-card);
  color: var(--color-muted);
}
.state--error {
  color: #b91c1c;
}
@media (max-width: 760px) {
  .news-card {
    grid-template-columns: 1fr;
  }
}
</style>
