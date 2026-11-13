<script setup lang="ts">
/**
 * 섹션 구조화 표시 (PS-04).
 *
 * 저장된 섹션 결과 payload에 **구조화 값이 있을 때만** 표·목록을 그린다. 없으면 아무것도
 * 그리지 않는다(빈 카드 금지). 본문(`body`)과 근거(`sources`)는 부모가 먼저 보여주고,
 * 이 컴포넌트는 그 아래에서 읽기 좋은 구조만 더한다.
 *
 * 지키는 것:
 *
 * - 선정 선수와 선정 이유를 **분리**해 보여준다(합친 문장을 만들지 않음).
 * - 팀별로 묶되 인원을 잘라내지 않는다. 서버가 상한을 넘겨 주면 그대로 보인다.
 * - 부상 상태 표기를 확정 부상으로 바꾸지 않는다. 모르는 표기는 원문 그대로 쓴다.
 * - 매체 예상 스코어가 없는 기사는 점수 칸을 비워 둔다(만들지 않음).
 * - 배당은 사이트·수집시각·홈/무/원정 소수점만 표로 쓴다. 누락값을 추정하지 않는다.
 * - AI 예측은 외부 매체 전망과 **다른 블록**에 둔다.
 */
import { computed } from 'vue'
import InlineEmphasis from './InlineEmphasis.vue'
import {
  injuryStatusLabel,
  isStructuredEmpty,
  scoreText,
  type StructuredSectionView,
} from './sectionStructured'

const props = defineProps<{
  structured: StructuredSectionView
}>()

const hasPlayers = computed(() => props.structured.players.length > 0)
const hasInjuries = computed(() => props.structured.injuries.length > 0)
const hasMedia = computed(() => props.structured.media.length > 0)
const hasOdds = computed(() => props.structured.odds.length > 0)
const forecast = computed(() => props.structured.forecast)
const nothing = computed(() => isStructuredEmpty(props.structured))

/** 팀 이름별 묶음. 팀이 없는 항목은 별도 그룹으로 두고 팀 이름을 만들지 않는다. */
function groups<T extends { team: string | null }>(rows: readonly T[]) {
  const result: { team: string | null; rows: T[] }[] = []
  for (const row of rows) {
    const found = result.find((group) => group.team === row.team)
    if (found) found.rows.push(row)
    else result.push({ team: row.team, rows: [row] })
  }
  return result
}

const playerGroups = computed(() => groups(props.structured.players))
const injuryGroups = computed(() => groups(props.structured.injuries))

const leanLabel = computed<string | null>(() => {
  const lean = forecast.value?.lean
  if (lean === 'home') return '홈팀 우세'
  if (lean === 'draw') return '무승부'
  if (lean === 'away') return '원정팀 우세'
  return null
})
</script>

<template>
  <div v-if="!nothing" class="structured" data-testid="section-structured">
    <section v-if="hasPlayers" class="structured__block" data-testid="structured-players">
      <h4 class="structured__title">주목 선수</h4>
      <div v-for="group in playerGroups" :key="group.team ?? '__no_team__'" class="structured__group">
        <p v-if="group.team" class="structured__team" data-testid="structured-players-team">
          {{ group.team }}
        </p>
        <dl class="structured__players">
          <div
            v-for="(player, index) in group.rows"
            :key="`${player.player}-${index}`"
            class="structured__player"
            data-testid="structured-player"
          >
            <dt class="structured__player-name">{{ player.player }}</dt>
            <dd class="structured__player-reason">{{ player.reason }}</dd>
          </div>
        </dl>
      </div>
    </section>

    <section v-if="hasInjuries" class="structured__block" data-testid="structured-injuries">
      <h4 class="structured__title">부상·결장</h4>
      <div v-for="group in injuryGroups" :key="group.team ?? '__no_team__'" class="structured__group">
        <p v-if="group.team" class="structured__team" data-testid="structured-injuries-team">
          {{ group.team }}
        </p>
        <ul class="structured__injuries">
          <li
            v-for="(injury, index) in group.rows"
            :key="`${injury.player}-${index}`"
            class="structured__injury"
            data-testid="structured-injury"
          >
            <span class="structured__player-name">{{ injury.player }}</span>
            <span class="structured__status" data-testid="structured-injury-status">
              {{ injuryStatusLabel(injury.status) }}
            </span>
            <span v-if="injury.summary" class="structured__summary">{{ injury.summary }}</span>
          </li>
        </ul>
      </div>
    </section>

    <section v-if="hasMedia" class="structured__block" data-testid="structured-media">
      <h4 class="structured__title">외부 매체 전망</h4>
      <ul class="structured__media">
        <li
          v-for="(row, index) in structured.media"
          :key="`${row.publisher}-${index}`"
          class="structured__media-row"
          data-testid="structured-media-row"
        >
          <p class="structured__media-head">
            <span class="structured__publisher">{{ row.publisher }}</span>
            <span v-if="scoreText(row.predictedScore)" class="structured__score measured">
              예상 {{ scoreText(row.predictedScore) }}
            </span>
            <span v-if="row.publishedAt" class="structured__stamp measured">{{ row.publishedAt }}</span>
          </p>
          <p class="structured__statement">{{ row.statement }}</p>
          <a
            v-if="row.url"
            class="structured__link"
            :href="row.url"
            rel="noreferrer noopener"
            target="_blank"
          >기사 열기</a>
        </li>
      </ul>
    </section>

    <section v-if="hasOdds" class="structured__block" data-testid="structured-odds">
      <h4 class="structured__title">배당 (정규시간 1X2)</h4>
      <table class="structured__odds">
        <caption class="visually-hidden">사이트별 정규시간 홈승·무승부·원정승 배당</caption>
        <thead>
          <tr>
            <th scope="col">사이트</th>
            <th scope="col">홈</th>
            <th scope="col">무</th>
            <th scope="col">원정</th>
            <th scope="col">수집 시각</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, index) in structured.odds" :key="`${row.bookmaker}-${index}`" data-testid="structured-odds-row">
            <th scope="row">{{ row.bookmaker }}</th>
            <!-- 값이 없으면 빈 칸이다. 추정값을 채우지 않는다. -->
            <td class="measured">{{ row.home ?? '—' }}</td>
            <td class="measured">{{ row.draw ?? '—' }}</td>
            <td class="measured">{{ row.away ?? '—' }}</td>
            <td class="structured__stamp">{{ row.observedAt ?? '—' }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section v-if="forecast" class="structured__block" data-testid="structured-forecast">
      <h4 class="structured__title">AI 예상</h4>
      <p class="structured__forecast-lead">
        <span v-if="leanLabel">{{ leanLabel }}</span>
        <span v-if="scoreText(forecast.score)" class="structured__score measured">
          예상 스코어 {{ scoreText(forecast.score) }}
        </span>
      </p>
      <ul v-if="forecast.reasoning.length" class="structured__reasoning" data-testid="structured-reasoning">
        <li v-for="(reason, index) in forecast.reasoning" :key="index"><InlineEmphasis :text="reason" /></li>
      </ul>
      <p v-if="forecast.note" class="structured__summary"><InlineEmphasis :text="forecast.note" /></p>
    </section>
  </div>
</template>

<style scoped>
.structured {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  border-top: var(--rule-hair) solid var(--color-rule);
  padding-top: var(--space-4);
}

.structured__block {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.structured__title {
  margin: 0;
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-muted);
}

.structured__group {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.structured__team {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--color-ink-2);
}

.structured__players {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.structured__player {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.structured__player-name {
  font-weight: 500;
  color: var(--color-ink);
}

.structured__player-reason,
.structured__statement,
.structured__summary {
  margin: 0;
  color: var(--color-ink-2);
  line-height: 1.6;
}

.structured__injuries,
.structured__media,
.structured__reasoning {
  margin: 0;
  padding-left: 1.1rem;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.structured__injury {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: baseline;
}

.structured__status {
  font-size: var(--text-sm);
  color: var(--color-accent);
}

.structured__media-row {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.structured__media-head {
  margin: 0;
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: baseline;
}

.structured__publisher {
  font-weight: 500;
  color: var(--color-ink);
}

.structured__score {
  color: var(--color-accent);
}

.structured__stamp {
  font-size: var(--text-sm);
  color: var(--color-muted);
}

.structured__link {
  font-size: var(--text-sm);
  color: var(--color-cool);
}

.structured__odds {
  width: 100%;
  border-collapse: collapse;
}

.structured__odds th,
.structured__odds td {
  text-align: left;
  padding: var(--space-1) var(--space-2);
  border-bottom: var(--rule-hair) solid var(--color-rule);
}

.structured__forecast-lead {
  margin: 0;
  display: flex;
  gap: var(--space-3);
  align-items: baseline;
}

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
</style>
