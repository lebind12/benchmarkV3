<script setup lang="ts">
import { ref, watch } from 'vue'
import { Shield, Trophy } from 'lucide-vue-next'
const props = defineProps<{ src?: string | null; alt: string; kind?: 'team' | 'league' }>()
const failed = ref(false)
watch(() => props.src, () => { failed.value = false })
</script>
<template>
  <span class="mm-resource-logo"><img v-if="src && !failed" :src="src" :alt="alt" loading="lazy" @error="failed = true" /><span v-else class="mm-resource-fallback" role="img" :aria-label="`${alt} 없음`"><Trophy v-if="kind === 'league'" :size="20" aria-hidden="true" /><Shield v-else :size="20" aria-hidden="true" /></span></span>
</template>
<style scoped>
.mm-resource-logo { width: 30px; height: 30px; display: inline-flex; align-items: center; justify-content: center; flex: 0 0 30px; }
.mm-resource-logo img { width: 100%; height: 100%; object-fit: contain; }
.mm-resource-fallback { color: var(--color-muted); display: inline-flex; align-items: center; justify-content: center; }
</style>
