<script setup lang="ts">
/**
 * 독자용 근거 목록 (MP-09).
 *
 * 검색 출처와 API 저장 자료를 **다른 종류로** 구분해 보여준다. 검색 출처는 실제 URL을,
 * API 자료는 수집 시각을 표시한다. 내부 ID·스냅샷 참조는 서버가 이미 지웠고 이 컴포넌트도
 * 그런 값을 그리지 않는다.
 *
 * 근거가 없으면 아무것도 그리지 않는다. 빈 카드나 "자료 없음" 문구를 만들지 않는다.
 */
import type { ReaderPreviewSource } from '@/features/match-preview/types'

const props = defineProps<{
  sources: ReaderPreviewSource[]
}>()

function noteFor(source: ReaderPreviewSource): string | null {
  if (source.note) return source.note
  if (source.kind === 'api' && source.observed_at) return `수집 ${source.observed_at.slice(0, 10)}`
  return null
}
</script>

<template>
  <section v-if="props.sources.length" class="sources" data-testid="preview-sources">
    <h3 class="sources__title">근거</h3>
    <ul class="sources__list">
      <li v-for="(source, index) in props.sources" :key="`${source.label}-${index}`" class="sources__item">
        <a
          v-if="source.url"
          class="sources__link"
          :href="source.url"
          rel="noreferrer noopener"
          target="_blank"
          data-testid="preview-source-link"
        >
          {{ source.label }}
        </a>
        <span v-else class="sources__label">{{ source.label }}</span>
        <span v-if="noteFor(source)" class="sources__note">{{ noteFor(source) }}</span>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.sources {
  border-top: var(--rule-hair) solid var(--color-rule);
  padding-top: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.sources__title {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-muted);
}

.sources__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.sources__item {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-2);
  font-size: var(--text-sm);
  min-width: 0;
}

.sources__link {
  color: var(--color-ink);
  text-decoration-color: var(--color-rule-2);
  text-underline-offset: 3px;
  overflow-wrap: anywhere;
}

.sources__link:hover {
  text-decoration-color: var(--color-accent);
}

.sources__label {
  color: var(--color-ink-2);
  overflow-wrap: anywhere;
}

.sources__note {
  color: var(--color-muted);
  font-size: var(--text-sm);
}
</style>
