<script setup lang="ts">
/**
 * 운영 지표 → 실행 검사 연결 (MP-04 공유 라우터 소유).
 *
 * MP-08의 `PreviewMetricsView.vue`는 자기 파일을 소유하므로 여기서 고치지 않는다.
 * 이 얇은 연결 화면이 그 화면을 그대로 띄우고 `select-run` 이벤트만 받아 실행 검사로
 * 이동한다. 지표 화면을 고치지 않고도 "표본 → 그 실행의 시도 원문" 이동이 성립한다.
 *
 * 필터 유지: 지표 화면은 실행을 열 때 **적용 중인 조회 필터**를 함께 넘긴다. 이
 * 화면은 그 값을 실행 목록 경로의 질의로 그대로 옮긴다. 값은 지표 화면이 실제로
 * 보낸 것만 쓰고, 없으면 만들지 않는다. 실행 목록 화면은 같은 질의로 지표 화면에
 * 돌아가는 링크를 만들 수 있어, 실행을 보고 돌아와도 같은 조건이 유지된다.
 */
import { useRouter } from 'vue-router'
import PreviewMetricsView from './PreviewMetricsView.vue'
import { metricsFilterRouteQuery, type MetricsFilterContext } from './metrics'

const router = useRouter()

async function openRun(payload: { runId: string; filters: MetricsFilterContext }) {
  const filters = metricsFilterRouteQuery(payload.filters)
  // 관리 프리뷰 탭이 `previewRun` 질의를 보고 해당 실행을 연다. 필터는 같은
  // 질의에 그대로 실어, 실행을 보고 지표로 돌아갈 때 조건이 남아 있게 한다.
  await router.push({
    name: 'admin',
    query: { tab: 'preview', previewRun: payload.runId, from: 'metrics', ...filters },
  })
}
</script>

<template>
  <PreviewMetricsView @select-run="openRun" />
</template>
