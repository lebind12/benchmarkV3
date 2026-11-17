<script setup lang="ts">
/**
 * 독자용 프리뷰 라우트 연결 (MP-09).
 *
 * 관리자 경로 `/admin/preview/:runId`에서 저장된 S1 종합 결과를 **독자가 읽는 모양**으로
 * 보여준다. 실행 ID는 URL에서만 오고, 없는 실행은 화면이 빈 프리뷰를 꾸미지 않고
 * 사실대로 알린다.
 *
 * 공개 홈 경로가 아니다: 서버가 ADMIN 검사를 하고, 이 경로도 관리자 영역 안에 있다.
 */
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import MatchPreview from '@/features/match-preview/MatchPreview.vue'

const route = useRoute()

const runId = computed<string>(() => {
  const value = route.params.runId
  if (Array.isArray(value)) return value[0] ?? ''
  return typeof value === 'string' ? value : ''
})

const inspectorHref = computed<string>(() =>
  runId.value ? `/admin?tab=preview&previewRun=${encodeURIComponent(runId.value)}` : '/admin?tab=preview',
)
</script>

<template>
  <div class="reader">
    <nav class="reader__nav" aria-label="관리자 이동">
      <RouterLink class="reader__back" to="/admin/sections">섹션 실행</RouterLink>
      <RouterLink class="reader__back" :to="inspectorHref">실행 검사</RouterLink>
    </nav>
    <MatchPreview :run-id="runId" />
  </div>
</template>

<style scoped>
.reader {
  min-height: 100vh;
  background: var(--color-paper);
}

.reader__nav {
  display: flex;
  gap: var(--space-4);
  max-width: var(--measure);
  margin: 0 auto;
  padding: var(--space-4) var(--space-4) 0;
}

.reader__back {
  color: var(--color-muted);
  font-size: var(--text-sm);
  text-decoration: none;
}

.reader__back:hover {
  color: var(--color-ink);
}
</style>
