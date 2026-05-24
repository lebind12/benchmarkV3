<script setup lang="ts">
import {
  ArcElement,
  Chart,
  PieController,
  type ChartConfiguration,
  type Color,
  type Plugin,
} from "chart.js";
import { onBeforeUnmount, onMounted, ref, watch } from "vue";

Chart.register(PieController, ArcElement);

const props = withDefaults(
  defineProps<{
    homePct: number;
    awayPct: number;
    homeColor: string;
    awayColor: string;
    trackColor?: string;
  }>(),
  {
    trackColor: "rgba(255, 255, 255, 0.16)",
  },
);

const BOTTOM_ROTATION_DEG = 180;
const DEGREES_PER_PERCENT = 3.6;

type PossessionChartRole = "track" | "home" | "away";
type PieChart = Chart<"pie", number[], string>;

const trackCanvasRef = ref<HTMLCanvasElement | null>(null);
const homeCanvasRef = ref<HTMLCanvasElement | null>(null);
const awayCanvasRef = ref<HTMLCanvasElement | null>(null);
let trackChart: PieChart | null = null;
let homeChart: PieChart | null = null;
let awayChart: PieChart | null = null;

function clampPct(value: number) {
  if (!Number.isFinite(value)) {
    return 0;
  }

  return Math.max(0, Math.min(100, value));
}

function awayRotation(awayPct: number) {
  return BOTTOM_ROTATION_DEG - awayPct * DEGREES_PER_PERCENT;
}

function hexToRgb(color: string) {
  const normalized = color.trim();
  const shortMatch = normalized.match(/^#([0-9a-f]{3})$/i);
  const longMatch = normalized.match(/^#([0-9a-f]{6})$/i);

  if (shortMatch) {
    const [r, g, b] = shortMatch[1].split("").map((part) => {
      const value = `${part}${part}`;
      return Number.parseInt(value, 16);
    });
    return { r, g, b };
  }

  if (!longMatch) {
    return null;
  }

  const value = longMatch[1];
  return {
    r: Number.parseInt(value.slice(0, 2), 16),
    g: Number.parseInt(value.slice(2, 4), 16),
    b: Number.parseInt(value.slice(4, 6), 16),
  };
}

function mixColor(color: string, target: string, amount: number) {
  const sourceRgb = hexToRgb(color);
  const targetRgb = hexToRgb(target);

  if (!sourceRgb || !targetRgb) {
    return color;
  }

  const ratio = Math.max(0, Math.min(1, amount));
  const channel = (source: number, targetValue: number) =>
    Math.round(source + (targetValue - source) * ratio);

  return `rgb(${channel(sourceRgb.r, targetRgb.r)}, ${channel(
    sourceRgb.g,
    targetRgb.g,
  )}, ${channel(sourceRgb.b, targetRgb.b)})`;
}

function createSliceGradient(
  chart: PieChart,
  role: PossessionChartRole,
): Color {
  const { ctx } = chart;
  const width = chart.width;
  const height = chart.height;
  const baseColor =
    role === "home"
      ? props.homeColor
      : role === "away"
        ? props.awayColor
        : props.trackColor;

  if (
    !ctx ||
    typeof ctx.createRadialGradient !== "function" ||
    !Number.isFinite(width) ||
    !Number.isFinite(height) ||
    width <= 0 ||
    height <= 0
  ) {
    return baseColor;
  }

  const radius = Math.max(Math.min(width, height) / 2, 1);
  const centerX =
    width / 2 + (role === "away" ? radius * 0.16 : -radius * 0.16);
  const centerY = height / 2 - radius * 0.28;
  const gradient = ctx.createRadialGradient(
    centerX,
    centerY,
    radius * 0.04,
    width / 2,
    height / 2,
    radius * 0.72,
  );

  if (role === "track") {
    gradient.addColorStop(0, "rgba(255, 255, 255, 0.22)");
    gradient.addColorStop(0.58, props.trackColor);
    gradient.addColorStop(1, "rgba(0, 0, 0, 0.34)");
    return gradient;
  }

  gradient.addColorStop(0, mixColor(baseColor, "#ffffff", 0.46));
  gradient.addColorStop(0.5, baseColor);
  gradient.addColorStop(1, mixColor(baseColor, "#000000", 0.34));
  return gradient;
}

function drawSeparator(
  ctx: CanvasRenderingContext2D,
  centerX: number,
  centerY: number,
  radius: number,
  angleRadians: number,
) {
  ctx.save();
  ctx.beginPath();
  ctx.moveTo(
    centerX + Math.cos(angleRadians) * radius * 0.04,
    centerY + Math.sin(angleRadians) * radius * 0.04,
  );
  ctx.lineTo(
    centerX + Math.cos(angleRadians) * radius * 0.98,
    centerY + Math.sin(angleRadians) * radius * 0.98,
  );
  ctx.strokeStyle = "rgba(255, 255, 255, 0.72)";
  ctx.lineWidth = Math.max(1.4, radius * 0.018);
  ctx.shadowColor = "rgba(0, 0, 0, 0.48)";
  ctx.shadowBlur = radius * 0.03;
  ctx.stroke();
  ctx.restore();
}

const possessionPieDecorationPlugin: Plugin<"pie"> = {
  id: "possessionPieDecoration",
  afterDraw(chart) {
    const { ctx } = chart;
    const radius = Math.min(chart.width, chart.height) / 2;
    const centerX = chart.width / 2;
    const centerY = chart.height / 2;

    if (radius <= 0) {
      return;
    }

    ctx.save();
    ctx.beginPath();
    ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
    ctx.clip();

    const gloss = ctx.createRadialGradient(
      centerX - radius * 0.42,
      centerY - radius * 0.54,
      radius * 0.04,
      centerX - radius * 0.18,
      centerY - radius * 0.24,
      radius * 1.08,
    );
    gloss.addColorStop(0, "rgba(255, 255, 255, 0.34)");
    gloss.addColorStop(0.34, "rgba(255, 255, 255, 0.12)");
    gloss.addColorStop(0.72, "rgba(255, 255, 255, 0)");
    ctx.globalCompositeOperation = "screen";
    ctx.fillStyle = gloss;
    ctx.fillRect(0, 0, chart.width, chart.height);

    const shade = ctx.createRadialGradient(
      centerX,
      centerY,
      radius * 0.2,
      centerX,
      centerY,
      radius,
    );
    shade.addColorStop(0, "rgba(0, 0, 0, 0)");
    shade.addColorStop(0.72, "rgba(0, 0, 0, 0)");
    shade.addColorStop(1, "rgba(0, 0, 0, 0.2)");
    ctx.globalCompositeOperation = "multiply";
    ctx.fillStyle = shade;
    ctx.fillRect(0, 0, chart.width, chart.height);
    ctx.restore();

    const awayBoundaryAngle =
      ((90 - clampPct(props.awayPct) * DEGREES_PER_PERCENT) * Math.PI) / 180;
    drawSeparator(ctx, centerX, centerY, radius, Math.PI / 2);
    drawSeparator(ctx, centerX, centerY, radius, awayBoundaryAngle);
  },
};

function roleData(role: PossessionChartRole) {
  if (role === "track") {
    return [100];
  }

  const value =
    role === "home" ? clampPct(props.homePct) : clampPct(props.awayPct);
  return [value, 100 - value];
}

function roleColors(role: PossessionChartRole, chart?: PieChart): Color[] {
  if (role === "track") {
    return [chart ? createSliceGradient(chart, role) : props.trackColor];
  }

  const color = role === "home" ? props.homeColor : props.awayColor;
  return [chart ? createSliceGradient(chart, role) : color, "rgba(0, 0, 0, 0)"];
}

function roleRotation(role: PossessionChartRole) {
  if (role === "away") {
    return awayRotation(clampPct(props.awayPct));
  }

  return BOTTOM_ROTATION_DEG;
}

function buildChartConfig(
  role: PossessionChartRole,
): ChartConfiguration<"pie", number[], string> {
  return {
    type: "pie",
    data: {
      labels: [role, `${role}-remaining`],
      datasets: [
        {
          data: roleData(role),
          backgroundColor: roleColors(role),
          borderWidth: 0,
          hoverBorderWidth: 0,
        },
      ],
    },
    options: {
      animation: false,
      circumference: 360,
      events: [],
      maintainAspectRatio: false,
      rotation: roleRotation(role),
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: { enabled: false },
      },
    },
    plugins: role === "away" ? [possessionPieDecorationPlugin] : [],
  };
}

function syncOneChart(chart: PieChart | null, role: PossessionChartRole) {
  if (!chart) {
    return;
  }

  const dataset = chart.data.datasets[0];
  dataset.data = roleData(role);
  dataset.backgroundColor = roleColors(role, chart);
  chart.options.rotation = roleRotation(role);

  chart.update("none");
}

function syncChart() {
  syncOneChart(trackChart, "track");
  syncOneChart(homeChart, "home");
  syncOneChart(awayChart, "away");
}

onMounted(() => {
  if (trackCanvasRef.value) {
    trackChart = new Chart(trackCanvasRef.value, buildChartConfig("track"));
  }

  if (homeCanvasRef.value) {
    homeChart = new Chart(homeCanvasRef.value, buildChartConfig("home"));
  }

  if (awayCanvasRef.value) {
    awayChart = new Chart(awayCanvasRef.value, buildChartConfig("away"));
  }

  syncChart();
});

onBeforeUnmount(() => {
  trackChart?.destroy();
  homeChart?.destroy();
  awayChart?.destroy();
  trackChart = null;
  homeChart = null;
  awayChart = null;
});

watch(
  () => [
    props.homePct,
    props.awayPct,
    props.homeColor,
    props.awayColor,
    props.trackColor,
  ],
  syncChart,
);
</script>

<template>
  <div class="possession-pie-chart">
    <canvas ref="trackCanvasRef" class="possession-pie-layer" />
    <canvas ref="homeCanvasRef" class="possession-pie-layer" />
    <canvas ref="awayCanvasRef" class="possession-pie-layer" />
  </div>
</template>

<style scoped>
.possession-pie-chart {
  position: relative;
  width: 100%;
  height: 100%;
  border-radius: 50%;
  filter: drop-shadow(0 0 1.4rem rgba(0, 52, 120, 0.58));
  overflow: hidden;
}

.possession-pie-layer {
  position: absolute;
  inset: 0;
  display: block;
  width: 100%;
  height: 100%;
}
</style>
