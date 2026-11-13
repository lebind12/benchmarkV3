<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ text: string }>()
const parts = computed(() => props.text.split(/(\*\*[^*\n]+\*\*)/g).filter(Boolean).map((part) => ({
  bold: part.startsWith('**') && part.endsWith('**'),
  text: part.startsWith('**') && part.endsWith('**') ? part.slice(2, -2) : part,
})))
</script>

<template>
  <template v-for="(part, index) in parts" :key="index"><strong v-if="part.bold">{{ part.text }}</strong><template v-else>{{ part.text }}</template></template>
</template>
