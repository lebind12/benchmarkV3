<script setup lang="ts">
import { ref, watch } from 'vue'
import { UserRound } from 'lucide-vue-next'
const props = defineProps<{ name: string; photoUrl?: string | null }>()
const failed = ref(false)
watch(() => props.photoUrl, () => { failed.value = false })
</script>
<template>
  <span class="hp-player-photo">
    <img v-if="photoUrl && !failed" :src="photoUrl" :alt="`${name} 선수 사진`" loading="lazy" decoding="async" @error="failed = true" />
    <span v-else class="hp-player-photo__empty" role="img" :aria-label="`${name} 선수 사진 없음`"><UserRound :size="30" :stroke-width="1.4" /></span>
  </span>
</template>
<style scoped>
.hp-player-photo { display: block; width: 76px; height: 88px; flex-shrink: 0; align-self: start; overflow: hidden; border-radius: 10px; background: var(--color-surface, transparent); }
img { display: block; width: 100%; height: 100%; object-fit: contain; object-position: center bottom; }
.hp-player-photo__empty { display: flex; height: 100%; align-items: center; justify-content: center; color: var(--color-muted); opacity: .6; }
@media (max-width: 600px) { .hp-player-photo { width: 46px; height: 62px; border-radius: 8px; } }
</style>
