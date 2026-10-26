<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { X } from 'lucide-vue-next'
const props = defineProps<{ open: boolean; title: string }>()
const emit = defineEmits<{ close: [] }>()
const panel = ref<HTMLElement | null>(null)
let previous: HTMLElement | null = null
const focusable = () => [...(panel.value?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], [tabindex="0"]') ?? [])].filter((node) => node.getClientRects().length > 0)
function keydown(event: KeyboardEvent) {
  if (!props.open) return
  if (event.key === 'Escape') { event.preventDefault(); emit('close') }
  if (event.key !== 'Tab') return
  const nodes = focusable()
  if (!nodes.length) { event.preventDefault(); panel.value?.focus(); return }
  if (event.shiftKey && (document.activeElement === nodes[0] || document.activeElement === panel.value)) { event.preventDefault(); nodes.at(-1)?.focus() }
  else if (!event.shiftKey && document.activeElement === nodes.at(-1)) { event.preventDefault(); nodes[0].focus() }
}
watch(() => props.open, async (open) => {
  if (open) {
    previous = document.activeElement as HTMLElement | null
    document.addEventListener('keydown', keydown)
    await nextTick()
    panel.value?.focus()
  } else { document.removeEventListener('keydown', keydown); previous?.focus() }
}, { immediate: true })
onBeforeUnmount(() => { document.removeEventListener('keydown', keydown); if (props.open) previous?.focus() })
</script>
<template>
  <Teleport to="body">
    <div v-if="open" class="mm-overlay" @click.self="emit('close')">
      <section ref="panel" class="mm-dialog" role="dialog" aria-modal="true" :aria-label="title" tabindex="-1">
        <header class="mm-panel-head"><h2>{{ title }}</h2><button type="button" class="mm-icon-button" aria-label="닫기" @click="emit('close')"><X :size="19" /></button></header>
        <div class="mm-dialog-body"><slot /></div>
        <footer v-if="$slots.footer" class="mm-dialog-footer"><slot name="footer" /></footer>
      </section>
    </div>
  </Teleport>
</template>
