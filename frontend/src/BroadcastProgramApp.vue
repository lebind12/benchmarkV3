<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  API_FOOTBALL_LIVE_POLL_MS,
  fetchApiFootballBroadcastSnapshot,
  fetchApiFootballFirstLiveFixture,
  shouldUseApiFootballLive,
  type ApiFootballBroadcastCoach,
  type ApiFootballBroadcastEvent,
  type ApiFootballBroadcastLineup,
  type ApiFootballBroadcastLineupPlayer,
  type ApiFootballBroadcastSnapshot,
  type ApiFootballBroadcastStat,
} from "@/lib/api/apiFootballLive";
import { readBroadcastFixtureId } from "@/lib/broadcastQuery";
import ProgramPossessionPieChart from "@/components/broadcast/ProgramPossessionPieChart.vue";

type LeagueSlug =
  | "premier-league"
  | "champions-league"
  | "europa-league"
  | "carabao-cup"
  | "fa-cup"
  | "world-cup-2026";

type Theme = {
  slug: LeagueSlug;
  label: string;
  panel: string;
  panelAlt: string;
  field: string;
  fieldAlt: string;
  line: string;
  text: string;
  muted: string;
  accent: string;
  accentAlt: string;
  dark: string;
};

type BottomView = "lineup" | "attack" | "chance" | "control" | "discipline";

type LineupPlayerView = {
  kind: "player";
  key: string;
  slotIndex: number;
  id?: number;
  number: number;
  name: string;
  longName?: string;
  pos?: string;
  grid?: string;
  isSubstitutedIn: boolean;
};

type LineupCoachView = {
  kind: "coach";
  key: string;
  id?: number;
  name: string;
  longName?: string;
};

type LineupEntryView = LineupPlayerView | LineupCoachView;

type SubstitutionAnimation = {
  id: string;
  teamId?: number;
  slotIndex: number;
  outName: string;
  outNumber?: number;
  inName: string;
  inNumber?: number;
};

type SubstitutionAnimationTimers = {
  apply: number;
  finish: number;
};

type TeamLineupView = {
  teamId?: number;
  name: string;
  code: string;
  shape: string;
  coach: LineupCoachView;
  players: LineupPlayerView[];
};

type StatViewMetric = {
  id: string;
  label: string;
  home: string;
  away: string;
  homePct: number;
  awayPct: number;
  graph: "pie" | "bar" | "discipline";
};

type StatViewConfig = {
  id: Exclude<BottomView, "lineup">;
  eyebrow: string;
  title: string;
  metrics: StatViewMetric[];
};

const SUBSTITUTION_ANIMATION_MS = 8000;
const SUBSTITUTION_LINEUP_APPLY_MS = 3000;
const STAT_COUNT_ANIMATION_MS = 900;

const searchParams = new URLSearchParams(window.location.search);
const requestedFixtureId = readBroadcastFixtureId(searchParams);
const requestedLeague = searchParams.get("league") as LeagueSlug | null;

const themes: Record<LeagueSlug, Theme> = {
  "premier-league": {
    slug: "premier-league",
    label: "프리미어리그",
    panel: "#32105A",
    panelAlt: "#E90052",
    field: "#16223D",
    fieldAlt: "#1D2C4E",
    line: "#04B8D9",
    text: "#FFFFFF",
    muted: "#F2D7FF",
    accent: "#E90052",
    accentAlt: "#04B8D9",
    dark: "#12051F",
  },
  "champions-league": {
    slug: "champions-league",
    label: "UEFA 챔피언스리그",
    panel: "#071542",
    panelAlt: "#315DFF",
    field: "#0B163A",
    fieldAlt: "#11235A",
    line: "#F1F4FF",
    text: "#FFFFFF",
    muted: "#CAD7FF",
    accent: "#315DFF",
    accentAlt: "#F1F4FF",
    dark: "#02081F",
  },
  "europa-league": {
    slug: "europa-league",
    label: "UEFA 유로파리그",
    panel: "#23160A",
    panelAlt: "#FF6A00",
    field: "#24170E",
    fieldAlt: "#3B250F",
    line: "#FFB000",
    text: "#FFFFFF",
    muted: "#FFE3BD",
    accent: "#FF6A00",
    accentAlt: "#FFB000",
    dark: "#120904",
  },
  "carabao-cup": {
    slug: "carabao-cup",
    label: "카라바오컵",
    panel: "#141A32",
    panelAlt: "#DA1E28",
    field: "#171F35",
    fieldAlt: "#252E4A",
    line: "#FFF2E6",
    text: "#FFFFFF",
    muted: "#FFD7D9",
    accent: "#DA1E28",
    accentAlt: "#FFF2E6",
    dark: "#070B17",
  },
  "fa-cup": {
    slug: "fa-cup",
    label: "FA컵",
    panel: "#132D5E",
    panelAlt: "#DB1F35",
    field: "#10233F",
    fieldAlt: "#1B345A",
    line: "#F7F1E3",
    text: "#FFFFFF",
    muted: "#DDE7FF",
    accent: "#DB1F35",
    accentAlt: "#F7F1E3",
    dark: "#071733",
  },
  "world-cup-2026": {
    slug: "world-cup-2026",
    label: "FIFA 월드컵 2026",
    panel: "#111111",
    panelAlt: "#C9972B",
    field: "#151515",
    fieldAlt: "#242424",
    line: "#F5F1E8",
    text: "#FFFFFF",
    muted: "#F6E1A8",
    accent: "#C8102E",
    accentAlt: "#003478",
    dark: "#050505",
  },
};

const selectedLeague =
  requestedLeague && Object.hasOwn(themes, requestedLeague)
    ? requestedLeague
    : "world-cup-2026";

const activeBottomView = ref<BottomView>("lineup");
const liveStatus = ref<"loading" | "ready" | "error">("loading");
const liveError = ref<string | null>(null);
const liveSnapshot = ref<ApiFootballBroadcastSnapshot | null>(null);
const appliedSubstitutionIds = ref<Set<string>>(new Set());
const activeSubstitutionAnimations = ref<SubstitutionAnimation[]>([]);
const statAnimationProgress = ref(1);
const isAdminAllowed = ref(
  typeof localStorage !== "undefined" &&
    localStorage.getItem("mockRole") === "ADMIN",
);

let livePollingTimer: number | undefined;
let statAnimationFrame: number | undefined;
const substitutionAnimationTimers = new Map<
  string,
  SubstitutionAnimationTimers
>();

const theme = computed(() => themes[selectedLeague]);
const themeVars = computed<Record<string, string>>(() => ({
  "--program-panel": theme.value.panel,
  "--program-panel-alt": theme.value.panelAlt,
  "--program-field": theme.value.field,
  "--program-field-alt": theme.value.fieldAlt,
  "--program-line": theme.value.line,
  "--program-text": theme.value.text,
  "--program-muted": theme.value.muted,
  "--program-accent": theme.value.accent,
  "--program-accent-alt": theme.value.accentAlt,
  "--program-dark": theme.value.dark,
}));

const liveStateLabel = computed(() => {
  if (liveStatus.value === "loading")
    return "API-Football 라이브 데이터 로딩 중";
  if (liveStatus.value === "error")
    return liveError.value ?? "API-Football 라이브 데이터 사용 불가";
  return "API-Football 라이브 데이터";
});

const currentLineups = computed<TeamLineupView[]>(() => {
  const snapshot = liveSnapshot.value;
  if (!snapshot) return [];
  return snapshot.lineups
    .slice(0, 2)
    .map((lineup) =>
      applySubstitutionsToLineup(
        lineup,
        snapshot.events,
        appliedSubstitutionIds.value,
      ),
    );
});

const activeStatView = computed<StatViewConfig | null>(() => {
  if (activeBottomView.value === "lineup" || !liveSnapshot.value) return null;

  const snapshot = liveSnapshot.value;
  const statGroups: Record<Exclude<BottomView, "lineup">, StatViewConfig> = {
    attack: {
      id: "attack",
      eyebrow: "ATTACK",
      title: "공격 지표",
      metrics: compactStats(snapshot.stats, ["점유율", "전체슈팅", "유효슈팅"]),
    },
    chance: {
      id: "chance",
      eyebrow: "CHANCE",
      title: "찬스 지표",
      metrics: compactStats(snapshot.stats, [
        "코너킥",
        "오프사이드",
        "전체슈팅",
      ]),
    },
    control: {
      id: "control",
      eyebrow: "CONTROL",
      title: "경기 운영",
      metrics: compactStats(snapshot.stats, ["패스성공률", "점유율"]),
    },
    discipline: {
      id: "discipline",
      eyebrow: "DISCIPLINE",
      title: "징계/수비",
      metrics: compactStats(snapshot.stats, ["파울", "옐로카드", "레드카드"]),
    },
  };

  return statGroups[activeBottomView.value];
});

function playerKey(player: ApiFootballBroadcastLineupPlayer, index: number) {
  return player.id !== undefined ? `player-${player.id}` : `slot-${index}`;
}

function toLineupPlayerView(
  player: ApiFootballBroadcastLineupPlayer,
  index: number,
): LineupPlayerView {
  return {
    kind: "player",
    key: playerKey(player, index),
    slotIndex: index,
    id: player.id,
    number: player.no,
    name: player.name,
    longName: player.longName,
    pos: player.pos,
    grid: player.grid,
    isSubstitutedIn: false,
  };
}

function toLineupCoachView(
  coach: ApiFootballBroadcastCoach | undefined,
  teamId: number | undefined,
): LineupCoachView {
  return {
    kind: "coach",
    key:
      coach?.id !== undefined
        ? `coach-${coach.id}`
        : `coach-${teamId ?? "unknown"}`,
    id: coach?.id,
    name: coach?.name ?? "감독 미정",
    longName: coach?.longName,
  };
}

function applySubstitutionsToLineup(
  lineup: ApiFootballBroadcastLineup,
  events: ApiFootballBroadcastEvent[],
  appliedIds: Set<string>,
): TeamLineupView {
  const players = lineup.players.slice(0, 11).map(toLineupPlayerView);
  const substitutionEvents = events.filter(
    (event) =>
      event.kind === "substitution" &&
      event.teamId === lineup.teamId &&
      appliedIds.has(event.id),
  );

  substitutionEvents.forEach((event) => {
    const outIndex = players.findIndex((player) =>
      event.playerId !== undefined
        ? player.id === event.playerId
        : player.name === event.outPlayer ||
          player.longName === event.outPlayer,
    );
    if (outIndex < 0) return;

    const inId = event.assistId;
    const inNumber =
      event.inPlayerNumber ??
      (inId !== undefined
        ? lineup.substituteNumbers[String(inId)]
        : undefined) ??
      players[outIndex].number;
    players[outIndex] = {
      kind: "player",
      key: inId !== undefined ? `player-${inId}` : `sub-${event.id}`,
      slotIndex: players[outIndex].slotIndex,
      id: inId,
      number: inNumber,
      name:
        event.inPlayerShortName ??
        event.inPlayer ??
        event.assist ??
        "교체 선수",
      longName: event.inPlayer ?? event.assist,
      pos: players[outIndex].pos,
      grid: players[outIndex].grid,
      isSubstitutedIn: true,
    };
  });

  return {
    teamId: lineup.teamId,
    name: lineup.name,
    code: lineup.code,
    shape: lineup.shape,
    coach: toLineupCoachView(lineup.coach, lineup.teamId),
    players,
  };
}

function splitLineupEntries(lineup: TeamLineupView): LineupEntryView[][] {
  return [
    lineup.players.slice(0, 6),
    [...lineup.players.slice(6, 11), lineup.coach],
  ];
}

function findSubstitutionSlot(
  lineup: ApiFootballBroadcastLineup,
  events: ApiFootballBroadcastEvent[],
  event: ApiFootballBroadcastEvent,
) {
  const baseLineup = applySubstitutionsToLineup(
    lineup,
    events,
    appliedSubstitutionIds.value,
  );

  return baseLineup.players.find((player) =>
    event.playerId !== undefined
      ? player.id === event.playerId
      : player.name === event.outPlayer || player.longName === event.outPlayer,
  );
}

function scheduleSubstitutionAnimations(
  snapshot: ApiFootballBroadcastSnapshot,
) {
  snapshot.events
    .filter((event) => event.kind === "substitution")
    .forEach((event) => {
      if (
        appliedSubstitutionIds.value.has(event.id) ||
        substitutionAnimationTimers.has(event.id)
      ) {
        return;
      }

      const lineup = snapshot.lineups.find(
        (candidate) => candidate.teamId === event.teamId,
      );
      if (!lineup) return;

      const outPlayer = findSubstitutionSlot(lineup, snapshot.events, event);
      if (!outPlayer) return;

      const inId = event.assistId;
      const inNumber =
        event.inPlayerNumber ??
        (inId !== undefined
          ? lineup.substituteNumbers[String(inId)]
          : undefined);
      const animation: SubstitutionAnimation = {
        id: event.id,
        teamId: lineup.teamId,
        slotIndex: outPlayer.slotIndex,
        outName: outPlayer.name,
        outNumber: outPlayer.number,
        inName:
          event.inPlayerShortName ??
          event.inPlayer ??
          event.assist ??
          "교체 선수",
        inNumber,
      };

      activeSubstitutionAnimations.value = [
        ...activeSubstitutionAnimations.value,
        animation,
      ];

      const applyTimer = window.setTimeout(() => {
        appliedSubstitutionIds.value = new Set([
          ...appliedSubstitutionIds.value,
          event.id,
        ]);
      }, SUBSTITUTION_LINEUP_APPLY_MS);

      const finishTimer = window.setTimeout(() => {
        activeSubstitutionAnimations.value =
          activeSubstitutionAnimations.value.filter(
            (item) => item.id !== event.id,
          );
        substitutionAnimationTimers.delete(event.id);
      }, SUBSTITUTION_ANIMATION_MS);
      substitutionAnimationTimers.set(event.id, {
        apply: applyTimer,
        finish: finishTimer,
      });
    });
}

function substitutionAnimationForEntry(
  lineup: TeamLineupView,
  entry: LineupEntryView,
) {
  if (entry.kind !== "player") return undefined;

  return activeSubstitutionAnimations.value.find(
    (animation) =>
      animation.teamId === lineup.teamId &&
      animation.slotIndex === entry.slotIndex,
  );
}

function lineupEntryKey(entry: LineupEntryView) {
  return entry.kind === "player" ? `slot-${entry.slotIndex}` : entry.key;
}

function lineupEntryClass(entry: LineupEntryView) {
  return {
    [`lineup-entry--${entry.kind}`]: true,
    "lineup-player--sub-in": entry.kind === "player" && entry.isSubstitutedIn,
  };
}

function findStat(stats: ApiFootballBroadcastStat[], label: string) {
  return stats.find((stat) => stat.label === label);
}

function compactStats(
  stats: ApiFootballBroadcastStat[],
  labels: string[],
): StatViewMetric[] {
  const seen = new Set<string>();
  return labels.flatMap((label) => {
    if (seen.has(label)) return [];
    const stat = findStat(stats, label);
    if (!stat) return [];
    seen.add(label);
    return [
      {
        id: stat.label,
        label: stat.label,
        home: stat.home,
        away: stat.away,
        homePct: stat.homePct,
        awayPct: stat.awayPct,
        graph: statGraphType(stat.label),
      },
    ];
  });
}

function statGraphType(label: string): StatViewMetric["graph"] {
  if (label === "점유율") return "pie";
  if (label === "옐로카드" || label === "레드카드") return "discipline";
  return "bar";
}

function animatedPercent(value: number) {
  return Math.max(0, Math.min(100, value * statAnimationProgress.value));
}

function animatedStatValue(value: string) {
  const match = value.match(/^(\d+(?:\.\d+)?)(.*)$/);
  if (!match) return value;

  const rawValue = Number(match[1]);
  const suffix = match[2] ?? "";
  const animatedValue = rawValue * statAnimationProgress.value;
  const hasDecimal = match[1].includes(".");
  const formattedValue = hasDecimal
    ? animatedValue.toFixed(1)
    : String(Math.round(animatedValue));
  return `${formattedValue}${suffix}`;
}

function statGraphVars(metric: StatViewMetric) {
  const homePct = animatedPercent(metric.homePct);
  const awayPct = animatedPercent(metric.awayPct);
  return {
    "--stat-home-pct": `${homePct}%`,
    "--stat-away-pct": `${awayPct}%`,
    "--stat-pie-angle": `${homePct * 3.6}deg`,
  };
}

function startStatAnimation() {
  if (statAnimationFrame !== undefined) {
    window.cancelAnimationFrame(statAnimationFrame);
  }

  if (activeBottomView.value === "lineup") {
    statAnimationProgress.value = 1;
    statAnimationFrame = undefined;
    return;
  }

  const startedAt = window.performance.now();
  statAnimationProgress.value = 0;

  const tick = (now: number) => {
    const elapsed = now - startedAt;
    const progress = Math.min(1, elapsed / STAT_COUNT_ANIMATION_MS);
    statAnimationProgress.value = 1 - Math.pow(1 - progress, 3);

    if (progress < 1) {
      statAnimationFrame = window.requestAnimationFrame(tick);
      return;
    }

    statAnimationFrame = undefined;
  };

  statAnimationFrame = window.requestAnimationFrame(tick);
}

function isEditableKeyboardTarget(target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) return false;

  const tagName = target.tagName.toLowerCase();
  return (
    tagName === "input" ||
    tagName === "select" ||
    tagName === "textarea" ||
    target.isContentEditable
  );
}

function setBottomView(nextView: BottomView) {
  if (nextView === "lineup") {
    activeBottomView.value = "lineup";
    return;
  }

  activeBottomView.value =
    activeBottomView.value === nextView ? "lineup" : nextView;
}

function handleBottomViewKeyboard(event: KeyboardEvent) {
  if (isEditableKeyboardTarget(event.target)) return;

  if (event.key === "Escape") {
    event.preventDefault();
    setBottomView("lineup");
    return;
  }

  if (!event.ctrlKey || event.altKey || event.metaKey || event.shiftKey) return;

  const shortcutViews: Partial<Record<string, BottomView>> = {
    z: "lineup",
    x: "attack",
    c: "chance",
    v: "control",
    b: "discipline",
  };
  const nextView = shortcutViews[event.key.toLowerCase()];

  if (!nextView) return;

  event.preventDefault();
  setBottomView(nextView);
}

async function refreshApiFootballLive() {
  if (!shouldUseApiFootballLive()) {
    liveStatus.value = "error";
    liveError.value = "API-Football 라이브 모드가 설정되지 않았습니다";
    return;
  }

  try {
    liveStatus.value = liveSnapshot.value ? "ready" : "loading";
    liveError.value = null;
    liveSnapshot.value =
      requestedFixtureId !== null
        ? await fetchApiFootballBroadcastSnapshot(requestedFixtureId)
        : await fetchApiFootballFirstLiveFixture();
    scheduleSubstitutionAnimations(liveSnapshot.value);
    liveStatus.value = "ready";
  } catch (error) {
    liveStatus.value = "error";
    liveError.value = (error as Error).message;
    console.error(
      "Failed to refresh API-Football broadcast program data",
      error,
    );
  }
}

onMounted(() => {
  if (!isAdminAllowed.value) return;

  window.addEventListener("keydown", handleBottomViewKeyboard);
  void refreshApiFootballLive();

  if (shouldUseApiFootballLive()) {
    livePollingTimer = window.setInterval(() => {
      void refreshApiFootballLive();
    }, API_FOOTBALL_LIVE_POLL_MS);
  }
});

watch(
  () => activeBottomView.value,
  () => startStatAnimation(),
);

onBeforeUnmount(() => {
  window.removeEventListener("keydown", handleBottomViewKeyboard);
  if (livePollingTimer !== undefined) {
    window.clearInterval(livePollingTimer);
  }
  if (statAnimationFrame !== undefined) {
    window.cancelAnimationFrame(statAnimationFrame);
  }
  substitutionAnimationTimers.forEach((timers) => {
    window.clearTimeout(timers.apply);
    window.clearTimeout(timers.finish);
  });
  substitutionAnimationTimers.clear();
});
</script>

<template>
  <main
    v-if="isAdminAllowed"
    class="program-stage"
    :data-league="theme.slug"
    :data-active-bottom-view="activeBottomView"
    :style="themeVars"
    data-testid="program-stage"
  >
    <section class="program-left" data-testid="program-left">
      <section class="feed-surface" data-testid="program-feed-surface">
        <div class="feed-visual" aria-hidden="true">
          <div class="feed-grid">
            <span class="feed-halfway"></span>
            <span class="feed-circle"></span>
            <span class="feed-box feed-box-left"></span>
            <span class="feed-box feed-box-right"></span>
            <span class="feed-runner feed-runner-a"></span>
            <span class="feed-runner feed-runner-b"></span>
            <span class="feed-runner feed-runner-c"></span>
            <span class="feed-ball"></span>
          </div>
        </div>
      </section>

      <section
        class="bottom-program-panel"
        data-testid="program-bottom-panel"
        :data-active-bottom-view="activeBottomView"
        aria-live="polite"
      >
        <Transition name="bottom-view">
          <div
            v-if="!liveSnapshot"
            key="live-empty"
            class="program-live-state"
            data-testid="program-live-empty"
          >
            <span>라이브 데이터</span>
            <strong>{{ liveStateLabel }}</strong>
          </div>

          <div
            v-else-if="activeBottomView === 'lineup'"
            key="lineup"
            class="lineup-board"
            data-testid="program-lineup-view"
          >
            <article
              v-for="lineup in currentLineups"
              :key="lineup.teamId ?? lineup.code"
              class="lineup-team"
              data-testid="program-lineup-team"
            >
              <header class="lineup-team-header">
                <span>{{ lineup.code }}</span>
                <strong>{{ lineup.name }}</strong>
                <b>{{ lineup.shape }}</b>
              </header>
              <div class="lineup-mini-columns">
                <ol
                  v-for="(column, columnIndex) in splitLineupEntries(lineup)"
                  :key="columnIndex"
                  class="lineup-list"
                >
                  <li
                    v-for="entry in column"
                    :key="lineupEntryKey(entry)"
                    class="lineup-entry"
                    :class="lineupEntryClass(entry)"
                    :data-testid="
                      entry.kind === 'coach'
                        ? 'program-lineup-coach'
                        : 'program-lineup-player'
                    "
                    :data-sub-in="
                      entry.kind === 'player' && entry.isSubstitutedIn
                        ? 'true'
                        : undefined
                    "
                  >
                    <span class="lineup-entry-icon" aria-hidden="true">
                      <svg viewBox="0 0 32 32" focusable="false">
                        <path
                          v-if="entry.kind === 'player'"
                          d="M10 4 6 7 3 15l5 2 2-4v15h12V13l2 4 5-2-3-8-4-3-4 3h-4l-4-3Z"
                        />
                        <path
                          v-else
                          d="M16 4a5 5 0 0 1 5 5 5 5 0 0 1-2.6 4.4L22 16h4v12H6V16h4l3.6-2.6A5 5 0 0 1 11 9a5 5 0 0 1 5-5Zm-5.6 15L9 20.5V25h14v-4.5L21.6 19H19l-3 3-3-3h-2.6Z"
                        />
                      </svg>
                    </span>
                    <b>{{ entry.kind === "coach" ? "감독" : entry.number }}</b>
                    <strong>{{ entry.name }}</strong>
                    <i v-if="entry.kind === 'player' && entry.isSubstitutedIn"
                      >IN</i
                    >
                    <div
                      v-if="substitutionAnimationForEntry(lineup, entry)"
                      class="lineup-substitution-animation"
                      data-testid="program-lineup-substitution-animation"
                    >
                      <span class="substitution-out">
                        <b>{{
                          substitutionAnimationForEntry(lineup, entry)
                            ?.outNumber
                        }}</b>
                        <strong>{{
                          substitutionAnimationForEntry(lineup, entry)?.outName
                        }}</strong>
                        <i>OUT</i>
                      </span>
                      <span class="substitution-in">
                        <b>{{
                          substitutionAnimationForEntry(lineup, entry)?.inNumber
                        }}</b>
                        <strong>{{
                          substitutionAnimationForEntry(lineup, entry)?.inName
                        }}</strong>
                        <i>IN</i>
                      </span>
                    </div>
                  </li>
                </ol>
              </div>
            </article>
          </div>

          <div
            v-else
            :key="`stats-${activeStatView?.id}`"
            class="stats-board"
            data-testid="program-stats-view"
            :data-stats-view="activeStatView?.id"
          >
            <header class="stats-header">
              <span>{{ activeStatView?.eyebrow }}</span>
              <strong>{{ activeStatView?.title }}</strong>
              <b>{{ liveSnapshot.homeCode }} / {{ liveSnapshot.awayCode }}</b>
            </header>
            <div v-if="activeStatView?.metrics.length" class="stats-grid">
              <article
                v-for="metric in activeStatView.metrics"
                :key="metric.id"
                class="stat-metric"
                data-testid="program-stat-metric"
                :data-graph="metric.graph"
                :style="statGraphVars(metric)"
              >
                <span>{{ metric.label }}</span>
                <div
                  v-if="metric.graph === 'pie'"
                  class="stat-graph stat-graph--pie"
                  aria-hidden="true"
                >
                  <span
                    class="stat-team-badge stat-team-badge--home"
                    data-testid="program-stat-home-badge"
                  >
                    <img
                      v-if="liveSnapshot.homeLogoUrl"
                      :src="liveSnapshot.homeLogoUrl"
                      alt=""
                    />
                    <b v-else>{{ liveSnapshot.homeCode }}</b>
                  </span>
                  <ProgramPossessionPieChart
                    :home-pct="animatedPercent(metric.homePct)"
                    :away-pct="animatedPercent(metric.awayPct)"
                  />
                  <span
                    class="stat-team-badge stat-team-badge--away"
                    data-testid="program-stat-away-badge"
                  >
                    <img
                      v-if="liveSnapshot.awayLogoUrl"
                      :src="liveSnapshot.awayLogoUrl"
                      alt=""
                    />
                    <b v-else>{{ liveSnapshot.awayCode }}</b>
                  </span>
                </div>
                <div
                  v-else-if="metric.graph === 'discipline'"
                  class="stat-graph stat-graph--discipline"
                  aria-hidden="true"
                >
                  <span
                    class="stat-team-badge stat-team-badge--home"
                    data-testid="program-stat-home-badge"
                  >
                    <img
                      v-if="liveSnapshot.homeLogoUrl"
                      :src="liveSnapshot.homeLogoUrl"
                      alt=""
                    />
                    <b v-else>{{ liveSnapshot.homeCode }}</b>
                  </span>
                  <i></i>
                  <b></b>
                  <i></i>
                  <span
                    class="stat-team-badge stat-team-badge--away"
                    data-testid="program-stat-away-badge"
                  >
                    <img
                      v-if="liveSnapshot.awayLogoUrl"
                      :src="liveSnapshot.awayLogoUrl"
                      alt=""
                    />
                    <b v-else>{{ liveSnapshot.awayCode }}</b>
                  </span>
                </div>
                <div
                  v-else
                  class="stat-graph stat-graph--bar"
                  aria-hidden="true"
                >
                  <span
                    class="stat-team-badge stat-team-badge--home"
                    data-testid="program-stat-home-badge"
                  >
                    <img
                      v-if="liveSnapshot.homeLogoUrl"
                      :src="liveSnapshot.homeLogoUrl"
                      alt=""
                    />
                    <b v-else>{{ liveSnapshot.homeCode }}</b>
                  </span>
                  <div>
                    <i></i>
                    <i></i>
                  </div>
                  <span
                    class="stat-team-badge stat-team-badge--away"
                    data-testid="program-stat-away-badge"
                  >
                    <img
                      v-if="liveSnapshot.awayLogoUrl"
                      :src="liveSnapshot.awayLogoUrl"
                      alt=""
                    />
                    <b v-else>{{ liveSnapshot.awayCode }}</b>
                  </span>
                </div>
                <div class="stat-score">
                  <b>{{ animatedStatValue(metric.home) }}</b>
                  <strong>{{ metric.label }}</strong>
                  <b>{{ animatedStatValue(metric.away) }}</b>
                </div>
              </article>
            </div>
            <div v-else class="stats-empty" data-testid="program-stats-empty">
              <span>표시할 스탯이 없습니다</span>
            </div>
          </div>
        </Transition>
      </section>
    </section>

    <aside class="program-right" data-testid="program-right">
      <section
        class="chat-slot"
        data-testid="program-chat-slot"
        aria-label="외부 방송 채팅 크로마키 영역"
      ></section>
      <section
        class="character-slot"
        data-testid="program-character-slot"
        aria-label="캐릭터 크로마키 영역"
      ></section>
    </aside>
  </main>

  <main
    v-else
    class="program-stage program-stage--locked"
    data-testid="program-locked"
  >
    <section class="program-locked-panel">
      <strong>권한이 필요합니다</strong>
      <span>방송용 페이지는 ADMIN 전용입니다.</span>
    </section>
  </main>
</template>

<style scoped>
*,
*::before,
*::after {
  box-sizing: border-box;
}

.program-stage {
  width: 100vw;
  height: 100vh;
  display: flex;
  overflow: hidden;
  background:
    radial-gradient(
      circle at 23% 18%,
      color-mix(in srgb, var(--program-accent) 18%, transparent),
      transparent 28%
    ),
    linear-gradient(135deg, #05070d 0%, #0b1020 54%, var(--program-dark) 100%);
  color: var(--program-text);
  font-family:
    "Avenir Next Condensed", "DIN Condensed", "Pretendard", system-ui,
    sans-serif;
  letter-spacing: 0;
}

.program-stage--locked {
  align-items: center;
  justify-content: center;
  background: #101318;
  color: #f8fafc;
}

.program-locked-panel {
  display: grid;
  gap: 0.5rem;
  min-width: 18rem;
  padding: 1.4rem 1.6rem;
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 0.5rem;
  background: rgba(12, 16, 22, 0.92);
  text-align: center;
}

.program-locked-panel strong {
  font-size: 1.25rem;
}

.program-locked-panel span {
  color: rgba(248, 250, 252, 0.72);
}

.program-left {
  flex: 0 0 78%;
  min-width: 0;
  height: 100%;
  display: grid;
  grid-template-rows: 78% 22%;
  overflow: hidden;
}

.program-right {
  flex: 0 0 22%;
  min-width: 0;
  height: 100%;
  display: grid;
  grid-template-rows: 78% 22%;
  background: #00b140;
}

.feed-surface {
  position: relative;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  background: var(--program-field);
  border-right: 0.12rem solid
    color-mix(in srgb, var(--program-line) 42%, #000000);
  border-bottom: 0.16rem solid var(--program-accent-alt);
}

.feed-visual {
  position: absolute;
  inset: 1.1%;
  overflow: hidden;
  background:
    linear-gradient(
      90deg,
      color-mix(in srgb, var(--program-field-alt) 88%, #000000) 0 12.5%,
      var(--program-field) 12.5% 25%,
      color-mix(in srgb, var(--program-field-alt) 88%, #000000) 25% 37.5%,
      var(--program-field) 37.5% 50%,
      color-mix(in srgb, var(--program-field-alt) 88%, #000000) 50% 62.5%,
      var(--program-field) 62.5% 75%,
      color-mix(in srgb, var(--program-field-alt) 88%, #000000) 75% 87.5%,
      var(--program-field) 87.5%
    ),
    radial-gradient(
      circle at 62% 52%,
      color-mix(in srgb, var(--program-accent) 18%, transparent),
      transparent 24%
    );
  border: 0.1rem solid color-mix(in srgb, var(--program-line) 55%, #ffffff);
  box-shadow:
    inset 0 0 0 0.28rem rgba(255, 255, 255, 0.05),
    inset 0 -4rem 6rem rgba(0, 0, 0, 0.25);
}

.feed-grid {
  position: absolute;
  inset: 4%;
  border: 0.12rem solid color-mix(in srgb, var(--program-line) 62%, #ffffff);
}

.feed-grid > span {
  position: absolute;
  display: block;
}

.feed-halfway {
  left: 50%;
  top: 0;
  bottom: 0;
  width: 0.12rem;
  background: color-mix(in srgb, var(--program-line) 62%, #ffffff);
}

.feed-circle {
  left: 50%;
  top: 50%;
  width: 18%;
  aspect-ratio: 1;
  border: 0.12rem solid color-mix(in srgb, var(--program-line) 62%, #ffffff);
  border-radius: 50%;
  transform: translate(-50%, -50%);
}

.feed-box {
  top: 28%;
  width: 13%;
  height: 44%;
  border: 0.12rem solid color-mix(in srgb, var(--program-line) 62%, #ffffff);
}

.feed-box-left {
  left: 0;
  border-left: 0;
}

.feed-box-right {
  right: 0;
  border-right: 0;
}

.feed-runner {
  width: 1.6rem;
  aspect-ratio: 1;
  border: 0.18rem solid #ffffff;
  border-radius: 50%;
  background: var(--program-accent);
  box-shadow: 0.16rem 0.16rem 0 #000000;
}

.feed-runner-a {
  left: 61%;
  top: 39%;
}

.feed-runner-b {
  left: 53%;
  top: 56%;
  background: var(--program-accent-alt);
}

.feed-runner-c {
  left: 72%;
  top: 50%;
  background: var(--program-panel-alt);
}

.feed-ball {
  left: 66%;
  top: 48%;
  width: 0.85rem;
  aspect-ratio: 1;
  border-radius: 50%;
  background: #ffffff;
  box-shadow: 0 0 0 0.14rem #000000;
}

.bottom-program-panel {
  position: relative;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  padding: 0.86rem 1.05rem 0.8rem;
  background: linear-gradient(
    90deg,
    #050505 0%,
    #111111 34%,
    #051b41 74%,
    #030915 100%
  );
  border-top: 0.18rem solid #c9972b;
  border-right: 0.12rem solid #c9972b;
  box-shadow:
    inset 0 1rem 2.4rem rgba(255, 255, 255, 0.05),
    inset 0 -1.6rem 3rem rgba(0, 0, 0, 0.45);
  isolation: isolate;
}

.bottom-program-panel::before {
  content: "";
  position: absolute;
  z-index: 1;
  top: 0;
  left: 0;
  right: 0;
  height: 0.48rem;
  background: linear-gradient(
    90deg,
    #c8102e 0 16%,
    #f5f1e8 16% 30%,
    #c9972b 30% 56%,
    #003478 56% 80%,
    #c8102e 80% 100%
  );
}

.program-live-state,
.lineup-board,
.stats-board {
  position: relative;
  z-index: 2;
  height: 100%;
}

.bottom-view-enter-active {
  z-index: 4;
  transition:
    opacity 240ms ease,
    transform 240ms cubic-bezier(0.2, 0.78, 0.22, 1);
}

.bottom-view-leave-active {
  position: absolute;
  z-index: 3;
  inset: 0;
  pointer-events: none;
  transition:
    opacity 180ms ease,
    transform 180ms cubic-bezier(0.2, 0.78, 0.22, 1);
}

.bottom-view-enter-from {
  opacity: 0;
  transform: translateY(16%);
}

.bottom-view-leave-to {
  opacity: 0.28;
  transform: translateY(4%);
}

.program-live-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.55rem;
  text-align: center;
}

.program-live-state span {
  color: var(--program-muted);
  font-size: 0.8rem;
  font-weight: 900;
}

.program-live-state strong {
  max-width: 72%;
  color: var(--program-text);
  font-size: 1.2rem;
  line-height: 1.2;
}

.lineup-board {
  min-height: 0;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
}

.lineup-team {
  min-width: 0;
  min-height: 0;
  display: grid;
  grid-template-rows: auto 1fr;
  gap: 0.45rem;
  padding: 0.3rem 0.78rem 0.42rem;
  border: 0.08rem solid rgba(245, 241, 232, 0.24);
  background: rgba(245, 241, 232, 0.06);
}

.lineup-team-header {
  min-width: 0;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 0.62rem;
}

.lineup-team-header span,
.lineup-team-header b {
  color: #c9972b;
  font-size: clamp(0.72rem, 0.78vw, 0.98rem);
  font-weight: 950;
  white-space: nowrap;
}

.lineup-team-header strong {
  min-width: 0;
  overflow: hidden;
  color: #ffffff;
  font-size: clamp(0.88rem, 1vw, 1.28rem);
  font-weight: 950;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.lineup-mini-columns {
  min-height: 0;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.48rem;
}

.lineup-list {
  min-width: 0;
  min-height: 0;
  display: grid;
  grid-template-rows: repeat(6, minmax(0, 1fr));
  gap: 0.18rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.lineup-entry {
  position: relative;
  z-index: 0;
  min-width: 0;
  min-height: 0;
  display: grid;
  grid-template-columns: 1.42rem 2.8ch minmax(0, 1fr) auto;
  align-items: center;
  gap: 0.34rem;
  padding: 0 0.34rem;
  background: rgba(0, 0, 0, 0.24);
  border-left: 0.16rem solid rgba(245, 241, 232, 0.36);
  overflow: hidden;
  isolation: isolate;
  contain: paint;
}

.lineup-player--sub-in,
.lineup-entry[data-sub-in="true"] {
  border-left-color: #c9972b;
  background: rgba(201, 151, 43, 0.16);
}

.lineup-entry--coach {
  grid-template-columns: 1.42rem 4ch minmax(0, 1fr) auto;
  border-left-color: rgba(245, 241, 232, 0.62);
  background: rgba(245, 241, 232, 0.12);
}

.lineup-entry-icon {
  position: relative;
  z-index: 1;
  width: 1.18rem;
  height: 1.18rem;
  display: grid;
  place-items: center;
}

.lineup-entry-icon svg {
  width: 100%;
  height: 100%;
  display: block;
  fill: #f5f1e8;
}

.lineup-entry--coach .lineup-entry-icon svg {
  fill: #c9972b;
}

.lineup-entry b {
  position: relative;
  z-index: 1;
  color: #c9972b;
  font-size: clamp(0.74rem, 0.78vw, 1rem);
  font-weight: 950;
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.lineup-entry--coach b {
  font-size: clamp(0.62rem, 0.68vw, 0.82rem);
  white-space: nowrap;
}

.lineup-entry strong {
  position: relative;
  z-index: 1;
  min-width: 0;
  overflow: hidden;
  color: #ffffff;
  font-size: clamp(0.78rem, 0.88vw, 1.08rem);
  font-weight: 900;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.lineup-entry--coach strong {
  color: #f6e1a8;
}

.lineup-entry i {
  position: relative;
  z-index: 1;
  color: #f6e1a8;
  font-size: 0.62rem;
  font-style: normal;
  font-weight: 950;
}

.lineup-substitution-animation {
  position: absolute;
  z-index: 20;
  inset: 0;
  display: block;
  border-left: 0.16rem solid #c9972b;
  box-shadow:
    inset 0 0 0 0.08rem rgba(245, 241, 232, 0.18),
    0 0 1.2rem rgba(201, 151, 43, 0.35);
  overflow: hidden;
  pointer-events: none;
  transform: translateZ(0);
}

.lineup-substitution-animation span {
  position: absolute;
  inset: 0;
  min-width: 0;
  display: grid;
  grid-template-columns: 2.8ch minmax(0, 1fr) auto;
  align-items: center;
  gap: 0.32rem;
  padding: 0 0.42rem;
}

.lineup-substitution-animation b {
  color: #f5f1e8;
  font-size: clamp(0.68rem, 0.72vw, 0.92rem);
  font-weight: 950;
  text-align: right;
}

.lineup-substitution-animation strong {
  min-width: 0;
  overflow: hidden;
  color: #ffffff;
  font-size: clamp(0.72rem, 0.82vw, 1.02rem);
  font-weight: 950;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.lineup-substitution-animation i {
  font-size: 0.58rem;
  font-style: normal;
  font-weight: 950;
}

.substitution-out {
  z-index: 30;
  background:
    linear-gradient(90deg, rgba(200, 16, 46, 0.84), rgba(5, 5, 5, 0.96)),
    #050505;
  animation: substitution-out 8000ms cubic-bezier(0.2, 0.78, 0.22, 1) forwards;
}

.substitution-out > * {
  animation: substitution-out-person 8000ms cubic-bezier(0.2, 0.78, 0.22, 1)
    forwards;
}

.substitution-out i {
  color: #ffced6;
}

.substitution-in {
  z-index: 40;
  background:
    linear-gradient(90deg, rgba(201, 151, 43, 0.84), rgba(5, 5, 5, 0.96)),
    #050505;
  animation: substitution-in 8000ms cubic-bezier(0.2, 0.78, 0.22, 1) forwards;
}

.substitution-in > * {
  animation: substitution-in-person 8000ms cubic-bezier(0.2, 0.78, 0.22, 1)
    forwards;
}

.substitution-in i {
  color: #f6e1a8;
}

@keyframes substitution-out {
  0% {
    opacity: 1;
    transform: translateY(-100%);
  }

  3.75% {
    opacity: 1;
    transform: translateY(0);
  }

  50% {
    opacity: 1;
    transform: translateY(0);
  }

  55% {
    opacity: 1;
    transform: translateY(-100%);
  }

  100% {
    opacity: 0;
    transform: translateY(-100%);
  }
}

@keyframes substitution-out-person {
  0%,
  3% {
    opacity: 0;
    transform: translateX(42%);
  }

  8% {
    opacity: 1;
    transform: translateX(0);
  }

  42% {
    opacity: 1;
    transform: translateX(0);
  }

  50%,
  100% {
    opacity: 0;
    transform: translateX(-10%);
  }
}

@keyframes substitution-in {
  0%,
  37.5% {
    opacity: 0;
    transform: translateY(100%);
  }

  41.25% {
    opacity: 1;
    transform: translateY(0);
  }

  95% {
    opacity: 1;
    transform: translateY(0);
  }

  100% {
    opacity: 1;
    transform: translateY(100%);
  }
}

@keyframes substitution-in-person {
  0%,
  42% {
    opacity: 0;
    transform: translateX(-42%);
  }

  48% {
    opacity: 1;
    transform: translateX(0);
  }

  95%,
  100% {
    opacity: 1;
    transform: translateX(0);
  }
}

.stats-board {
  display: grid;
  grid-template-columns: 18rem 1fr;
  align-items: stretch;
  gap: 1rem;
}

.stats-header {
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 0.18rem;
}

.stats-header span {
  color: #c9972b;
  font-size: 0.98rem;
  font-weight: 950;
}

.stats-header strong {
  color: #ffffff;
  font-size: clamp(1.55rem, 2.1vw, 2.9rem);
  font-weight: 950;
  line-height: 0.98;
}

.stats-header b {
  color: #f6e1a8;
  font-size: 0.95rem;
  font-weight: 950;
}

.stats-grid {
  min-width: 0;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.75rem;
}

.stat-metric {
  position: relative;
  min-width: 0;
  display: grid;
  grid-template-rows: auto minmax(3.2rem, 1fr) auto;
  gap: 0.48rem;
  padding: 0.64rem 0.74rem;
  overflow: hidden;
  background:
    linear-gradient(135deg, rgba(245, 241, 232, 0.12), rgba(5, 5, 5, 0.12)),
    rgba(245, 241, 232, 0.08);
  border: 0.08rem solid rgba(245, 241, 232, 0.2);
  animation: stat-card-in 620ms cubic-bezier(0.2, 0.78, 0.22, 1) both;
}

.stat-metric:nth-child(2) {
  animation-delay: 80ms;
}

.stat-metric:nth-child(3) {
  animation-delay: 160ms;
}

.stat-metric::before {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(
    100deg,
    transparent 0 32%,
    rgba(255, 255, 255, 0.2) 46%,
    transparent 62% 100%
  );
  opacity: 0;
  transform: translateX(-100%);
  animation: stat-card-sheen 920ms ease-out both;
  animation-delay: 140ms;
}

.stat-metric > span {
  position: relative;
  z-index: 1;
  color: #c9972b;
  font-size: 0.86rem;
  font-weight: 950;
  text-align: center;
}

.stat-graph {
  position: relative;
  z-index: 1;
  min-width: 0;
  min-height: 0;
  align-self: stretch;
}

.stat-graph--bar {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  grid-template-rows: 2.9rem minmax(0, 1fr);
  align-items: stretch;
  column-gap: 0.78rem;
  row-gap: 0.42rem;
}

.stat-graph--bar > div {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  align-items: end;
  gap: 0.78rem;
}

.stat-graph--bar i {
  display: flex;
  align-items: end;
  align-self: end;
  height: 100%;
  min-height: 4.2rem;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.12);
  box-shadow: inset 0 0 0 0.05rem rgba(255, 255, 255, 0.18);
}

.stat-graph--bar i::before {
  content: "";
  display: block;
  width: 100%;
}

.stat-graph--bar i:first-child::before {
  height: var(--stat-home-pct);
  background: #f5f1e8;
}

.stat-graph--bar i:last-child::before {
  height: var(--stat-away-pct);
  background: #c8102e;
}

.stat-graph--pie {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.52fr) minmax(0, 1fr);
  grid-template-rows: minmax(0, 1fr);
  align-items: center;
  gap: 0.58rem;
}

.stat-graph--discipline {
  display: grid;
  grid-template-columns: 1fr 0.28rem 1fr;
  grid-template-rows: 2.9rem minmax(0, 1fr);
  align-items: end;
  column-gap: 0.68rem;
  row-gap: 0.42rem;
  padding: 0 0.1rem;
}

.stat-graph--discipline i {
  align-self: end;
  min-height: 0.32rem;
  display: block;
  width: 100%;
  box-shadow: inset 0 0 0 0.06rem rgba(255, 255, 255, 0.22);
}

.stat-graph--discipline i:first-of-type {
  grid-column: 1;
  grid-row: 2;
  height: var(--stat-home-pct);
  background: #f5f1e8;
}

.stat-graph--discipline i:last-of-type {
  grid-column: 3;
  grid-row: 2;
  height: var(--stat-away-pct);
  background: #c8102e;
}

.stat-graph--discipline > b {
  grid-column: 2;
  grid-row: 2;
  width: 100%;
  height: 92%;
  background: rgba(201, 151, 43, 0.56);
}

.stat-team-badge {
  width: 2.9rem;
  aspect-ratio: 1;
  display: grid;
  place-items: center;
  overflow: hidden;
  border-radius: 50%;
  background: rgba(5, 5, 5, 0.58);
  box-shadow:
    inset 0 0 0 0.07rem rgba(245, 241, 232, 0.28),
    0 0 0.62rem rgba(0, 0, 0, 0.34);
}

.stat-team-badge img {
  width: 76%;
  height: 76%;
  object-fit: contain;
}

.stat-team-badge b {
  color: #f5f1e8;
  font-size: 0.72rem;
  font-weight: 950;
  letter-spacing: 0;
}

.stat-team-badge--home {
  justify-self: center;
  grid-column: 1;
  grid-row: 1;
}

.stat-team-badge--away {
  justify-self: center;
  grid-column: -2;
  grid-row: 1;
}

.stat-graph--pie .stat-team-badge {
  width: 3.35rem;
}

.stat-graph--pie .program-possession-chart {
  grid-column: 2;
  grid-row: 1;
  height: 100%;
}

.stat-score {
  position: relative;
  z-index: 1;
  min-width: 0;
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: 0.46rem;
}

.stat-score b {
  color: #ffffff;
  font-size: clamp(1.8rem, 2.3vw, 3.15rem);
  font-weight: 950;
  line-height: 0.95;
  text-align: center;
}

.stat-score strong {
  color: rgba(245, 241, 232, 0.72);
  font-size: 0.68rem;
  font-weight: 950;
  white-space: nowrap;
}

.stats-empty {
  display: grid;
  place-items: center;
  color: #f6e1a8;
  font-weight: 950;
}

@keyframes stat-card-in {
  0% {
    opacity: 0;
    transform: translateY(18%) scale(0.96);
  }

  100% {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

@keyframes stat-card-sheen {
  0% {
    opacity: 0;
    transform: translateX(-100%);
  }

  35% {
    opacity: 0.8;
  }

  100% {
    opacity: 0;
    transform: translateX(120%);
  }
}

.chat-slot {
  height: 100%;
  min-height: 0;
  background: #00b140;
}

.character-slot {
  height: 100%;
  min-height: 0;
  background: #00b140;
}
</style>
