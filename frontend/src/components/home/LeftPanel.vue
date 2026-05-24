<script setup lang="ts">
import CubeCarousel from "./CubeCarousel.vue";
import brandMark from "@/assets/generated/bench-mark-brand-imagegen-10.png";
</script>
<template>
  <section class="left" data-testid="left-panel">
    <div class="left__logo" data-testid="left-logo">
      <img
        class="left__brand"
        :src="brandMark"
        alt="벤치마크 - 이글콥 벤치단 축구 사이트"
      />
    </div>
    <div class="left__cube" data-testid="left-cube"><CubeCarousel /></div>
  </section>
</template>
<style scoped>
.left {
  display: flex;
  flex-direction: column;
  height: 100%;
  border-right: 1px solid var(--color-border);
  overflow: hidden;
  min-width: 0;
}
.left__logo {
  flex: 0 0 30%;
  display: flex;
  align-items: center;
  justify-content: center;
  border-bottom: 1px solid var(--color-border);
  padding: 12px;
  box-sizing: border-box;
}
.left__brand {
  display: block;
  width: min(96%, 360px);
  max-height: 86%;
  object-fit: contain;
  filter: drop-shadow(0 14px 24px rgb(0 0 0 / 0.28));
}
.left__cube {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
</style>
