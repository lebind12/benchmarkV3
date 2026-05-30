<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'
import { useHomeStore } from '@/stores/home'
import HomeDashboardCandidate from '@/components/ui-review/HomeDashboardCandidate.vue'

const home = useHomeStore()

onMounted(() => {
  home.fixtures.filter.period = 'week'
  home.bootstrap()
})

onBeforeUnmount(() => {
  home.teardown()
})
</script>

<template>
  <main class="candidate-page app-container" data-testid="ui-review-home-page">
    <HomeDashboardCandidate />
  </main>
</template>

<style scoped>
.candidate-page {
  height: calc(100vh - var(--header-height));
  min-height: 0;
  overflow: hidden;
  padding-block: 12px;
}
</style>
