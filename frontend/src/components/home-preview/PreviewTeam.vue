<script setup lang="ts">
import { ref } from 'vue'
import type { Team } from '@/mocks/home-preview/data'
defineProps<{ team: Team; noLogo?: boolean; side: string }>()
const broken = ref(false)
</script>
<template>
  <div :class="['hp-team', `hp-team--${side}`]" :style="{ '--team-color': team.color }">
    <div class="hp-team__crest">
      <img v-if="!noLogo && !broken" :src="`https://media.api-sports.io/football/teams/${team.id}.png`" :alt="`${team.name} 엠블럼`" @error="broken = true" />
      <span v-else class="hp-team__fallback" aria-label="엠블럼 없음">{{ team.name.slice(0, 2) }}</span>
    </div>
    <span class="hp-team__side">{{ side === 'home' ? '홈' : '원정' }}</span>
    <h2>{{ team.name }}</h2>
    <p>{{ team.english }}</p>
  </div>
</template>
