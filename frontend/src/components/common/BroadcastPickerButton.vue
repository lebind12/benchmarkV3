<script setup lang="ts">
import { computed, ref, useId, watch } from 'vue'
import { MonitorPlay, UsersRound, X } from 'lucide-vue-next'
import { useAuthStore } from '@/stores/auth'
import { BROADCAST_FIXTURE_QUERY_PARAM } from '@/lib/broadcastQuery'

const props = defineProps<{ fixtureId?: number | null; leagueSlug?: string | null; matchLabel?: string }>()
const auth = useAuthStore()
const dialog = ref<HTMLDialogElement | null>(null)
const trigger = ref<HTMLButtonElement | null>(null)
const isOpen = ref(false)
const id = `broadcast-picker-${useId()}`
const validFixture = computed(() => Number.isSafeInteger(props.fixtureId) && Number(props.fixtureId) > 0)
const query = computed(() => {
  if (!validFixture.value) return ''
  const params = new URLSearchParams({ [BROADCAST_FIXTURE_QUERY_PARAM]: String(props.fixtureId) })
  if (props.leagueSlug) params.set('league', props.leagueSlug)
  return params.toString()
})
function open() {
  if (!auth.canOpenBroadcast || !validFixture.value) return
  dialog.value?.showModal()
  isOpen.value = true
}
function close() {
  if (dialog.value?.open) dialog.value.close()
  isOpen.value = false
}
function closed() {
  isOpen.value = false
  trigger.value?.focus()
}
watch([() => props.fixtureId, () => props.leagueSlug, () => auth.canOpenBroadcast], close)
</script>

<template>
  <button v-if="auth.canOpenBroadcast" ref="trigger" type="button" class="broadcast-trigger" data-testid="broadcast-picker-trigger"
    :disabled="!validFixture" :aria-expanded="isOpen" :aria-controls="id" aria-haspopup="dialog"
    :aria-label="`${matchLabel ? `${matchLabel} ` : ''}스트리밍 화면 선택`" @click="open">
    <MonitorPlay :size="16" aria-hidden="true" /><span>스트리밍</span>
  </button>
  <Teleport to="body">
    <dialog v-if="auth.canOpenBroadcast" :id="id" ref="dialog" class="broadcast-picker__dialog" data-testid="broadcast-picker"
      :aria-labelledby="`${id}-title`" @cancel.prevent="close" @close="closed" @click.self="close">
      <section class="broadcast-picker__panel">
        <header class="broadcast-picker__header">
          <div><p>STREAMING</p><h2 :id="`${id}-title`">방송 화면 선택</h2></div>
          <button type="button" aria-label="닫기" data-testid="broadcast-picker-close" autofocus @click="close"><X :size="18" aria-hidden="true" /></button>
        </header>
        <div class="broadcast-picker__options">
          <a class="broadcast-picker__option broadcast-picker__option--program" data-testid="program-link" :href="`/broadcast-program.html?${query}`" target="_blank" rel="noopener noreferrer" @click="close">
            <span class="broadcast-picker__icon" aria-hidden="true"><MonitorPlay :size="22" /></span>
            <span class="broadcast-picker__copy"><strong>TV 중계 화면</strong><em>경기 화면 + 하단 배너</em></span>
          </a>
          <a class="broadcast-picker__option" data-testid="watch-together-link" :href="`/broadcast.html?${query}`" target="_blank" rel="noopener noreferrer" @click="close">
            <span class="broadcast-picker__icon" aria-hidden="true"><UsersRound :size="22" /></span>
            <span class="broadcast-picker__copy"><strong>같이보기 화면</strong><em>캐릭터 중심 방송 레이아웃</em></span>
          </a>
        </div>
      </section>
    </dialog>
  </Teleport>
</template>

<style scoped>
.broadcast-trigger { display: inline-flex; align-items: center; gap: 6px; min-height: 34px; padding: 0 13px; border: 1px solid var(--color-border); border-radius: 999px; background: var(--color-card); color: var(--color-fg); font: inherit; font-size: 12px; font-weight: 750; cursor: pointer; white-space: nowrap; }
.broadcast-trigger:disabled { opacity: .45; cursor: default; }
.broadcast-trigger:focus-visible { outline: 2px solid #2563eb; outline-offset: 3px; }
.broadcast-picker__dialog { width: min(520px, calc(100vw - 32px)); max-height: calc(100dvh - 32px); margin: auto; padding: 0; border: 0; border-radius: 8px; background: var(--color-card); color: var(--color-fg); }
.broadcast-picker__dialog::backdrop { background: rgb(2 6 23 / .45); }
.broadcast-picker__panel {
  width: min(520px, 100%);
  overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--color-primary, #2563eb) 24%, var(--color-border));
  border-radius: 8px;
  color: var(--color-fg);
  background: var(--color-card);
  box-shadow: 0 28px 84px rgba(15, 23, 42, 0.38);
}

.broadcast-picker__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 16px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-bg);
}

.broadcast-picker__header p {
  margin: 0 0 4px;
  color: var(--color-primary, #2563eb);
  font-size: 11px;
  font-weight: 950;
  letter-spacing: 0.12em;
}

.broadcast-picker__header h2 {
  margin: 0;
  font-size: 18px;
  line-height: 1.25;
}

.broadcast-picker__header button {
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  width: 34px;
  height: 34px;
  border: 1px solid var(--color-border);
  border-radius: 999px;
  color: var(--color-fg);
  background: var(--color-card);
  cursor: pointer;
}

.broadcast-picker__header button:hover,
.broadcast-picker__header button:focus-visible {
  border-color: var(--color-primary, #2563eb);
  outline: none;
}

.broadcast-picker__options {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  padding: 16px;
}

.broadcast-picker__option {
  display: grid;
  grid-template-columns: 42px minmax(0, 1fr);
  align-items: center;
  gap: 12px;
  min-height: 92px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 14px;
  color: var(--color-fg);
  background: color-mix(in srgb, var(--color-primary, #2563eb) 5%, var(--color-bg));
  text-decoration: none;
}

.broadcast-picker__option--program {
  background: color-mix(in srgb, #0ea5e9 8%, var(--color-bg));
}

.broadcast-picker__option:hover,
.broadcast-picker__option:focus-visible {
  border-color: var(--color-primary, #2563eb);
  outline: none;
  transform: translateY(-1px);
}

.broadcast-picker__icon {
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  border-radius: 8px;
  color: #fff;
  background: color-mix(in srgb, var(--color-primary, #2563eb) 88%, #111827);
}

.broadcast-picker__copy {
  display: grid;
  gap: 5px;
  min-width: 0;
}

.broadcast-picker__copy strong {
  overflow: hidden;
  font-size: 14px;
  font-weight: 950;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.broadcast-picker__copy em {
  overflow: hidden;
  color: var(--color-muted);
  font-size: 12px;
  font-style: normal;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}


@media (max-width: 540px) { .broadcast-picker__options { grid-template-columns: 1fr; } }
</style>
