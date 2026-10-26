<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'
import { ChevronDown, Search, Check } from 'lucide-vue-next'
import type { TranslationScopeOption } from '@/lib/api/managementTypes'
import ResourceLogo from './ResourceLogo.vue'
const props = withDefaults(defineProps<{ modelValue: string; options: (Omit<TranslationScopeOption,'id'> & {id:string | number; aliases?:string[]})[]; label: string; disabled?: boolean; allLabel?: string; searchPlaceholder?: string; showLogos?: boolean }>(), {showLogos:true})
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const uid = useId()
const listId = `team-scope-${uid}`
const root = ref<HTMLElement | null>(null)
const trigger = ref<HTMLButtonElement | null>(null)
const popup = ref<HTMLElement | null>(null)
const search = ref<HTMLInputElement | null>(null)
const opened = ref(false)
const query = ref('')
const active = ref(0)
const position = ref<Record<string, string>>({})
const selected = computed(() => props.options.find(item => String(item.id) === props.modelValue))
const choices = computed(() => [{ value: '', name: props.allLabel ?? '전체 팀', name_en: '', logo_url: null, aliases: [] as string[] }, ...props.options.map(item => ({ ...item, value: String(item.id) }))].filter(item => !query.value.trim() || `${item.name} ${item.name_en} ${(item.aliases ?? []).join(' ')}`.toLowerCase().replace(/[\s_-]+/g,'').includes(query.value.trim().toLowerCase().replace(/[\s_-]+/g,''))))
const optionId = (index: number) => `${listId}-${index}`
function inside(target: EventTarget | null) { return target instanceof Node && (root.value?.contains(target) || popup.value?.contains(target)) }
function place() {
  const rect = trigger.value!.getBoundingClientRect()
  const width = Math.min(Math.max(rect.width, 260), window.innerWidth - 24)
  const below = window.innerHeight - rect.bottom - 12
  const above = rect.top - 12
  const upwards = below < 260 && above > below
  position.value = { width: `${width}px`, left: `${Math.max(12, Math.min(rect.left, window.innerWidth-width-12))}px`, maxHeight: `${Math.min(360, upwards ? above : below)}px`, ...(upwards ? { bottom: `${window.innerHeight-rect.top+6}px` } : { top: `${rect.bottom+6}px` }) }
}
async function open() {
  if (props.disabled) return
  if (opened.value) { close(); return }
  query.value = ''; opened.value = true
  place()
  active.value = Math.max(0, choices.value.findIndex(item => item.value === props.modelValue))
  await nextTick(); search.value?.focus({ preventScroll: true })
}
function close(restore = false) { opened.value = false; if (restore) void nextTick(() => trigger.value?.focus({preventScroll:true})) }
function choose(value: string) { emit('update:modelValue', value); close(true) }
function move(amount: number) { active.value = Math.max(0, Math.min(choices.value.length-1, active.value+amount)); void nextTick(() => document.getElementById(optionId(active.value))?.scrollIntoView({block:'nearest'})) }
function pointer(event: PointerEvent) { if (!inside(event.target)) close() }
function focusOut(event: FocusEvent) { if (!inside(event.relatedTarget)) close() }
function scroll(event: Event) {
  // Native selects and unrelated result containers can emit scroll events too.
  // Keep the menu anchored if result loading changes the page's scroll offset.
  if (opened.value && event.target instanceof Node && root.value && event.target.contains(root.value)) {
    const rect = trigger.value!.getBoundingClientRect()
    if (rect.bottom < 0 || rect.top > window.innerHeight) close()
    else place()
  }
}
function resize() { close() }
watch(query, () => { active.value = 0 })
watch(() => props.disabled, (value) => { if (value) close() })
onMounted(() => { document.addEventListener('pointerdown', pointer); window.addEventListener('scroll',scroll,true); window.addEventListener('resize',resize) })
onBeforeUnmount(() => { document.removeEventListener('pointerdown',pointer); window.removeEventListener('scroll',scroll,true); window.removeEventListener('resize',resize) })
</script>
<template>
  <div ref="root" class="mm-team-select" @focusout="focusOut">
    <button ref="trigger" type="button" class="mm-team-trigger" :aria-label="`${label}: ${selected?.name ?? (allLabel ?? '전체 팀')}`" aria-haspopup="listbox" :aria-controls="opened ? listId : undefined" :aria-expanded="opened" :disabled="disabled" @click="open" @keydown.down.prevent="open" @keydown.up.prevent="open" @keydown.esc.prevent="close(true)">
      <ResourceLogo v-if="selected && showLogos !== false" :src="selected.logo_url" :alt="`${selected.name} 팀 로고`" /><span>{{ selected?.name ?? (allLabel ?? '전체 팀') }}</span><ChevronDown :size="15" aria-hidden="true" />
    </button>
    <Teleport to="body"><div v-if="opened" ref="popup" class="mm-team-menu" :style="position" @focusout="focusOut" @keydown.esc.prevent.stop="close(true)">
      <label class="mm-team-search"><Search :size="15" aria-hidden="true" /><input ref="search" v-model="query" role="combobox" :aria-label="`${label} 이름 검색`" :aria-controls="listId" aria-expanded="true" aria-autocomplete="list" :aria-activedescendant="choices.length ? optionId(active) : undefined" :placeholder="searchPlaceholder ?? '팀 이름 검색'" @keydown.down.prevent="move(1)" @keydown.up.prevent="move(-1)" @keydown.enter.prevent="choices[active] && choose(choices[active].value)" /></label>
      <div :id="listId" class="mm-team-options" role="listbox" :aria-label="`${label} 목록`"><button v-for="(item,index) in choices" :id="optionId(index)" :key="item.value" type="button" role="option" tabindex="-1" :aria-selected="modelValue === item.value" :class="{ active: index === active }" @pointermove="active = index" @mousedown.prevent @click="choose(item.value)"><ResourceLogo v-if="item.value && showLogos !== false" :src="item.logo_url" :alt="`${item.name} 팀 로고`" /><span><strong>{{ item.name }}</strong><small v-if="item.name_en && item.name_en !== item.name">{{ item.name_en }}</small></span><Check v-if="modelValue === item.value" :size="15" aria-hidden="true" /></button><p v-if="!choices.length" class="mm-team-empty">일치하는 항목이 없습니다.</p></div>
    </div></Teleport>
  </div>
</template>
<style scoped>
.mm-team-select { min-width: 0; }
.mm-team-trigger { width: 100%; min-height: 38px; display: flex; align-items: center; gap: 9px; padding: 6px 10px; border: 1px solid var(--color-border); border-radius: 6px; background: var(--color-bg); color: var(--color-fg); font: inherit; text-align: left; cursor: pointer; }
.mm-team-trigger>span { flex: 1; }
.mm-team-trigger .mm-resource-logo { flex: 0 0 26px; width: 26px; height: 26px; }
.mm-team-menu { position: fixed; z-index: 1200; display: flex; flex-direction: column; overflow: hidden; border: 1px solid var(--color-border); border-radius: 8px; background: var(--color-card); color: var(--color-fg); box-shadow: 0 8px 24px #0002; font: 13px Pretendard, sans-serif; }
.mm-team-menu, .mm-team-menu * { box-sizing: border-box; }
.mm-team-search { flex: 0 0 auto; display: flex; align-items: center; gap: 8px; padding: 10px; border-bottom: 1px solid var(--color-border); }
.mm-team-search input { width: 100%; min-width: 0; padding: 6px; background: var(--color-bg); color: var(--color-fg); border: 1px solid var(--color-border); border-radius: 4px; font: inherit; }
.mm-team-options { overflow-y: auto; min-height: 0; padding: 4px; }
.mm-team-options button { display: flex; align-items: center; gap: 10px; width: 100%; min-height: 44px; padding: 8px; color: var(--color-fg); background: transparent; border: 0; border-radius: 5px; text-align: left; font: inherit; cursor: pointer; }
.mm-team-options button.active { background: var(--color-bg); outline: 1px solid var(--color-border); }
.mm-team-options button>span { flex: 1; }
.mm-team-options button>.mm-resource-logo { flex: 0 0 28px; width: 28px; height: 28px; }
.mm-team-options strong { font-weight: 500; }
.mm-team-options small { display: block; margin-top: 3px; color: var(--color-muted); font-size: 11px; }
.mm-team-empty { padding: 12px; color: var(--color-muted); }
.mm-team-trigger:focus-visible, .mm-team-search input:focus-visible { outline: 2px solid #2563eb; outline-offset: 2px; }
</style>
