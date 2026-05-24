<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { LEAGUE_SHORT_KO, leagueLogoUrl } from '@/lib/league-colors'
import type { LeagueSlug } from '@/types/home'

const props = withDefaults(
  defineProps<{
    externalId?: number | null
    slug?: LeagueSlug | string | null
    logoUrl?: string | null
    label?: string | null
    size?: 'xs' | 'sm' | 'md'
  }>(),
  { size: 'sm' },
)

const failed = ref(false)
const imageSrc = computed(() => props.logoUrl ?? leagueLogoUrl(props.externalId))
const normalizedSlug = computed(() => props.slug ?? null)
const fallback = computed(() => {
  if (props.label) return props.label
  if (props.slug && props.slug in LEAGUE_SHORT_KO) {
    return LEAGUE_SHORT_KO[props.slug as LeagueSlug]
  }
  return 'L'
})

watch(imageSrc, () => {
  failed.value = false
})
</script>

<template>
  <span
    :class="['league-mark', `league-mark--${size}`]"
    :data-league="normalizedSlug || undefined"
    aria-hidden="true"
  >
    <img
      v-if="imageSrc && !failed"
      class="league-mark__img"
      :src="imageSrc"
      alt=""
      loading="lazy"
      decoding="async"
      @error="failed = true"
    />
    <span v-else class="league-mark__fallback">{{ fallback }}</span>
  </span>
</template>

<style scoped>
.league-mark {
  --league-mark-size: 20px;
  display: inline-grid;
  place-items: center;
  width: var(--league-mark-size);
  height: var(--league-mark-size);
  min-width: var(--league-mark-size);
  border: 1px solid rgb(17 24 39 / 0.16);
  border-radius: 999px;
  background: #ffffff;
  box-shadow:
    inset 0 0 0 1px rgb(255 255 255 / 0.72),
    0 1px 2px rgb(0 0 0 / 0.14);
  overflow: hidden;
}

.league-mark--xs {
  --league-mark-size: 18px;
}

.league-mark--md {
  --league-mark-size: 24px;
}

.league-mark__img {
  display: block;
  width: 82%;
  height: 82%;
  object-fit: contain;
}

.league-mark__fallback {
  display: block;
  max-width: 100%;
  padding-inline: 2px;
  color: var(--theme-primary, var(--color-fg));
  font-size: 8px;
  font-weight: 800;
  line-height: 1;
  overflow: hidden;
  text-align: center;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
