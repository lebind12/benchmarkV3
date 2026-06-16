<script setup lang="ts">
import {
  BarController,
  BarElement,
  CategoryScale,
  Chart,
  LinearScale,
  type ChartConfiguration,
} from "chart.js";
import { onBeforeUnmount, onMounted, ref, watch } from "vue";

Chart.register(BarController, BarElement, LinearScale, CategoryScale);

const solidCanvasBackground = {
  id: "solidCanvasBackground",
  beforeDraw(chartInstance: MomentumChart) {
    const { ctx, chartArea, scales, width, height } = chartInstance;
    const yScale = scales.y;
    const zeroY =
      yScale && typeof yScale.getPixelForValue === "function"
        ? yScale.getPixelForValue(0)
        : height / 2;
    const top = chartArea?.top ?? 0;
    const bottom = chartArea?.bottom ?? height;
    const left = chartArea?.left ?? 0;
    const right = chartArea?.right ?? width;
    const clampedZeroY = Math.max(top, Math.min(bottom, zeroY));
    ctx.save();
    ctx.globalCompositeOperation = "source-over";
    ctx.fillStyle = "#0b0b0b";
    ctx.fillRect(0, 0, width, height);
    ctx.fillStyle = "rgba(216, 162, 31, 0.12)";
    ctx.fillRect(left, top, right - left, clampedZeroY - top);
    ctx.fillStyle = "rgba(88, 166, 255, 0.12)";
    ctx.fillRect(left, clampedZeroY, right - left, bottom - clampedZeroY);
    ctx.restore();
  },
};

const props = defineProps<{
  points: Array<{
    elapsed?: number | null;
    extra?: number | null;
    minuteKey?: number | null;
    displayMinute?: string | null;
    value: number;
  }>;
}>();

type MomentumChart = Chart<"bar", number[], string>;

const canvasRef = ref<HTMLCanvasElement | null>(null);
let chart: MomentumChart | null = null;

function pointKey(point: {
  elapsed?: number | null;
  extra?: number | null;
  minuteKey?: number | null;
  displayMinute?: string | null;
}, index: number) {
  if (point.minuteKey !== undefined && point.minuteKey !== null) return point.minuteKey;
  if (point.elapsed !== undefined && point.elapsed !== null) {
    return point.elapsed + Math.max(0, point.extra ?? 0);
  }
  return `floating-${index}`;
}

function displayPoints() {
  const pointsByMinute = new Map<number | string, (typeof props.points)[number]>();
  props.points.forEach((point, index) => {
    pointsByMinute.set(pointKey(point, index), point);
  });
  return Array.from(pointsByMinute.entries())
    .sort(([left], [right]) => {
      if (typeof left === "number" && typeof right === "number") return left - right;
      if (typeof left === "number") return -1;
      if (typeof right === "number") return 1;
      return String(left).localeCompare(String(right));
    })
    .map(([, point]) => point);
}

function labels() {
  return displayPoints().map((point, index) => {
    if (point.displayMinute) return point.displayMinute;
    if (point.elapsed !== undefined && point.elapsed !== null) {
      return point.extra && point.extra > 0 ? `${point.elapsed}+${point.extra}'` : `${point.elapsed}'`;
    }
    return `${index + 1}`;
  });
}

function values() {
  return displayPoints().map((point) => Math.max(-100, Math.min(100, point.value)));
}

function barColors() {
  return values().map((value) => (value >= 0 ? "#d8a21f" : "#58a6ff"));
}

function yRange() {
  const maxAbsValue = values().reduce((max, value) => Math.max(max, Math.abs(value)), 0);
  const padded = Math.ceil((maxAbsValue + 5) / 5) * 5;
  return Math.max(10, Math.min(100, padded));
}

function buildChartConfig(): ChartConfiguration<"bar", number[], string> {
  const range = yRange();
  return {
    type: "bar",
    data: {
      labels: labels(),
      datasets: [
        {
          data: values(),
          backgroundColor: barColors(),
          borderColor: barColors(),
          borderWidth: 1,
          borderRadius: 2,
          barPercentage: 0.82,
          categoryPercentage: 0.9,
        },
      ],
    },
    options: {
      animation: false,
      events: [],
      maintainAspectRatio: false,
      responsive: true,
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: "rgba(245, 241, 232, 0.72)", maxTicksLimit: 6 },
        },
        y: {
          min: -range,
          max: range,
          grid: {
            color: (context) =>
              context.tick.value === 0
                ? "rgba(201, 151, 43, 0.92)"
                : "rgba(245, 241, 232, 0.14)",
            lineWidth: (context) => (context.tick.value === 0 ? 2 : 1),
          },
          ticks: {
            color: "rgba(245, 241, 232, 0.68)",
            font: { size: 10, weight: 700 },
            stepSize: range / 2,
            callback: (value) => {
              const numericValue = Number(value);
              const range = yRange();
              return numericValue === 0 || Math.abs(numericValue) === range ? `${numericValue}` : "";
            },
          },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: { enabled: false },
      },
    },
    plugins: [solidCanvasBackground],
  };
}

function syncChart() {
  if (!chart) return;
  const range = yRange();
  chart.data.labels = labels();
  chart.data.datasets[0].data = values();
  chart.data.datasets[0].backgroundColor = barColors();
  chart.data.datasets[0].borderColor = barColors();
  if (chart.options.scales?.y) {
    chart.options.scales.y.min = -range;
    chart.options.scales.y.max = range;
  }
  chart.update("none");
}

onMounted(() => {
  if (import.meta.env.MODE === "test") return;
  try {
    if (!canvasRef.value?.getContext("2d")) return;
    chart = new Chart(canvasRef.value, buildChartConfig());
  } catch {
    chart = null;
  }
});

watch(() => props.points, syncChart, { deep: true });

onBeforeUnmount(() => {
  chart?.destroy();
  chart = null;
});
</script>

<template>
  <div class="momentum-line-chart">
    <canvas ref="canvasRef" aria-label="경기 모멘텀 그래프"></canvas>
  </div>
</template>

<style scoped>
.momentum-line-chart {
  width: 100%;
  height: 100%;
  min-height: 0;
  background: #0b0b0b;
}

.momentum-line-chart canvas {
  display: block;
  background: #0b0b0b;
}
</style>
