<script setup lang="ts">
import HomeDashboardCandidate from '@/components/ui-review/HomeDashboardCandidate.vue'
</script>

<template>
  <main class="home-page app-container panel-scroll" data-testid="ui-review-home-page" tabindex="0" aria-label="홈 추천 경기와 프리뷰">
    <HomeDashboardCandidate />
  </main>
</template>

<style scoped>
.home-page {
  height: calc(100dvh - var(--header-height));
  min-height: 0;
  padding-block: 12px;
}
</style>
