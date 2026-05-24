<script setup lang="ts">
import StandingsBlock from './StandingsBlock.vue'
import TopPlayersBlock from './TopPlayersBlock.vue'
</script>
<template>
  <aside class="right" data-testid="right-panel">
    <div class="right__top"><StandingsBlock /></div>
    <div class="right__bot"><TopPlayersBlock /></div>
  </aside>
</template>
<style scoped>
.right {
  display: grid;
  grid-template-rows: minmax(0, 1fr) minmax(0, 1fr);
  height: 100%;
  min-height: 0;
  overflow: hidden;
  border-left: 1px solid var(--color-border);
}
.right__top,
.right__bot {
  min-height: 0;
  overflow: hidden;
}
.right__top { border-bottom: 1px solid var(--color-border); }
</style>
