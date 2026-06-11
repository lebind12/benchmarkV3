<script setup lang="ts">
import {
  ArcElement,
  Chart,
  DoughnutController,
  type ChartConfiguration,
} from "chart.js";
import { onBeforeUnmount, onMounted, ref, watch } from "vue";

Chart.register(DoughnutController, ArcElement);

const props = defineProps<{
  homePct: number;
  awayPct: number;
}>();

type DoughnutChart = Chart<"doughnut", number[], string>;

const homeCanvasRef = ref<HTMLCanvasElement | null>(null);
const awayCanvasRef = ref<HTMLCanvasElement | null>(null);

let homeChart: DoughnutChart | null = null;
let awayChart: DoughnutChart | null = null;

function clampPct(value: number) {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(100, value));
}

function chartData(value: number) {
  const pct = clampPct(value);
  return [pct, 100 - pct];
}

function buildChartConfig(
  value: number,
  color: string,
): ChartConfiguration<"doughnut", number[], string> {
  return {
    type: "doughnut",
    data: {
      labels: ["value", "remaining"],
      datasets: [
        {
          data: chartData(value),
          backgroundColor: [color, "rgba(255, 255, 255, 0.13)"],
          borderWidth: 0,
          hoverBorderWidth: 0,
        },
      ],
    },
    options: {
      animation: false,
      events: [],
      maintainAspectRatio: false,
      responsive: true,
      rotation: 0,
      cutout: "52%",
      plugins: {
        legend: { display: false },
        tooltip: { enabled: false },
      },
    },
  };
}

function createChart(canvas: HTMLCanvasElement, value: number, color: string) {
  if (import.meta.env.MODE === "test") return null;

  try {
    if (!canvas.getContext("2d")) return null;
    return new Chart(canvas, buildChartConfig(value, color));
  } catch {
    return null;
  }
}

function syncChart() {
  if (homeChart) {
    homeChart.data.datasets[0].data = chartData(props.homePct);
    homeChart.update("none");
  }

  if (awayChart) {
    awayChart.data.datasets[0].data = chartData(props.awayPct);
    awayChart.update("none");
  }
}

onMounted(() => {
  if (homeCanvasRef.value) {
    homeChart = createChart(homeCanvasRef.value, props.homePct, "#f5f1e8");
  }

  if (awayCanvasRef.value) {
    awayChart = createChart(awayCanvasRef.value, props.awayPct, "#c8102e");
  }

  syncChart();
});

onBeforeUnmount(() => {
  homeChart?.destroy();
  awayChart?.destroy();
  homeChart = null;
  awayChart = null;
});

watch([() => props.homePct, () => props.awayPct], syncChart);
</script>

<template>
  <div class="program-possession-chart" data-testid="program-possession-chart">
    <canvas
      ref="homeCanvasRef"
      class="program-possession-chart__canvas program-possession-chart__canvas--home"
      aria-hidden="true"
    ></canvas>

    <canvas
      ref="awayCanvasRef"
      class="program-possession-chart__canvas program-possession-chart__canvas--away"
      aria-hidden="true"
    ></canvas>
  </div>
</template>

<style scoped>
.program-possession-chart {
  /*
    --chart-size: 도넛 하나의 크기
    --center-offset: 두 도넛 중심 사이 거리
    center-offset 값이 작을수록 더 많이 겹칩니다.
  */
  --chart-size: 6.5rem;
  --center-offset: 0rem;

  position: relative;
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 4.2rem;
}

.program-possession-chart__canvas {
  position: absolute;
  top: 50%;
  left: 50%;

  width: var(--chart-size) !important;
  height: var(--chart-size) !important;

  min-width: 0;
  min-height: 0;
  pointer-events: none;

  filter: drop-shadow(0 0 0.38rem rgba(0, 0, 0, 0.42));
}

.program-possession-chart__canvas--home {
  transform: translate(calc(-50% - var(--center-offset)), -50%) scaleX(-1);
  z-index: 1;
}

.program-possession-chart__canvas--away {
  transform: translate(calc(-50% + var(--center-offset)), -50%);
  z-index: 2;
}
</style>
