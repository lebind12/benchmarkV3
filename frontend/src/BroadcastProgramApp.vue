<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  API_FOOTBALL_LIVE_POLL_MS,
  fetchApiFootballAiReview,
  fetchApiFootballBroadcastSnapshot,
  fetchApiFootballFirstLiveFixture,
  shouldUseApiFootballLive,
  type ApiFootballAiReviewResponse,
  type ApiFootballBroadcastCoach,
  type ApiFootballBroadcastEvent,
  type ApiFootballBroadcastLineup,
  type ApiFootballBroadcastLineupPlayer,
  type ApiFootballBroadcastSnapshot,
  type ApiFootballBroadcastStat,
} from "@/lib/api/apiFootballLive";
import { readBroadcastFixtureId } from "@/lib/broadcastQuery";
import ProgramMomentumLineChart from "@/components/broadcast/ProgramMomentumLineChart.vue";
import ProgramPossessionPieChart from "@/components/broadcast/ProgramPossessionPieChart.vue";
import goalSoccerBallUrl from "@/assets/broadcast/goal-soccer-ball.svg?url";

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

type BottomView = "lineup" | "attack" | "chance" | "control" | "discipline" | "group";

type BottomViewTab = {
  id: BottomView;
  label: string;
  shortLabel: string;
};

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
  rating?: string;
  photoUrl?: string;
  minutes?: number;
  shotsTotal?: number;
  shotsOnGoal?: number;
  passesTotal?: number;
  passesAccurate?: number;
  passesAccuracyPct?: number;
  keyPasses?: number;
  foulsCommitted?: number;
  statGoals?: number;
  statAssists?: number;
  saves?: number;
  goalsConceded?: number;
  tacklesTotal?: number;
  blocks?: number;
  interceptions?: number;
  duelsTotal?: number;
  duelsWon?: number;
  dribblesAttempts?: number;
  dribblesSuccess?: number;
  statYellowCards?: number;
  statRedCards?: number;
  eventSummary?: {
    goals: number;
    yellowCards: number;
    redCards: number;
    cardLabel: string;
  };
  isSubstitutedIn: boolean;
};

type SelectedLineupPlayerView = LineupPlayerView & {
  teamName: string;
  teamCode: string;
  teamId?: number;
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

type GroupStandingsRowView = {
  teamId?: number;
  teamName: string;
  teamCode: string;
  rank: number;
  played: number;
  win: number;
  draw: number;
  loss: number;
  goalsFor: number;
  goalsAgainst: number;
  goalDiff: number;
  points: number;
};

const SUBSTITUTION_ANIMATION_MS = 8000;
const SUBSTITUTION_LINEUP_APPLY_MS = 3000;
const STAT_COUNT_ANIMATION_MS = 900;
const bottomViewTabs: BottomViewTab[] = [
  { id: "lineup", label: "라인업", shortLabel: "라인업" },
  { id: "attack", label: "공격", shortLabel: "공격" },
  { id: "chance", label: "찬스", shortLabel: "찬스" },
  { id: "control", label: "운영", shortLabel: "운영" },
  { id: "discipline", label: "징계", shortLabel: "징계" },
  { id: "group", label: "조상황", shortLabel: "조 상황" },
];
type BottomViewTransitionDirection = "next" | "prev";

const bottomViewTransitionDirection = ref<BottomViewTransitionDirection>("next");

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
const selectedLineupPlayer = ref<SelectedLineupPlayerView | null>(null);
const isMomentumPanelOpen = ref(false);
const isAiReviewPanelOpen = ref(false);
const aiReviewStatus = ref<"idle" | "loading" | "ready" | "error">("idle");
const aiReviewResult = ref<ApiFootballAiReviewResponse | null>(null);
const aiReviewError = ref("");
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
  const playerStatLookup = buildLineupPlayerStatLookup(snapshot);

  const lineups = snapshot.lineups
    .slice(0, 2)
    .map((lineup) =>
      applySubstitutionsToLineup(
        lineup,
        snapshot.events,
        appliedSubstitutionIds.value,
        playerStatLookup,
      ),
    );

  const homeId = snapshot.homeId;
  const awayId = snapshot.awayId;
  const homeCode = snapshot.homeCode;
  const awayCode = snapshot.awayCode;
  const homeName = snapshot.home;
  const awayName = snapshot.away;

  const normalize = (value?: string | number | null) =>
    String(value ?? "")
      .trim()
      .toLowerCase();

  const isTeamMatch = (
    lineup: TeamLineupView,
    teamId?: number | null,
    teamCode?: string | null,
    teamName?: string | null,
  ) => {
    if (
      lineup.teamId !== undefined &&
      teamId !== undefined &&
      teamId !== null &&
      lineup.teamId === teamId
    )
      return true;

    const lineupCode = normalize(lineup.code);
    const lineupName = normalize(lineup.name);
    const normalizedCode = normalize(teamCode);
    const normalizedName = normalize(teamName);

    if (normalizedCode && lineupCode === normalizedCode) return true;
    if (normalizedName && lineupName === normalizedName) return true;
    if (normalizedCode && normalizedName) {
      if (lineupCode && lineupName) {
        if (
          lineupCode.includes(normalizedCode) ||
          lineupName.includes(normalizedName) ||
          normalizedName.includes(lineupName)
        ) {
          return true;
        }
      }
      if (normalizedCode.length > 3 && normalizedName.length > 0) {
        if (normalizedName.includes(normalizedCode)) return true;
      }
    }
    return false;
  };

  const homeLineup = lineups.find((lineup) =>
    isTeamMatch(lineup, homeId, homeCode, homeName),
  );
  const awayLineup = lineups.find(
    (lineup) =>
      lineup !== homeLineup &&
      isTeamMatch(lineup, awayId, awayCode, awayName),
  );

  const assigned = new Set<TeamLineupView>();
  const ordered: TeamLineupView[] = [];
  if (homeLineup) {
    ordered.push(homeLineup);
    assigned.add(homeLineup);
  }
  if (awayLineup) {
    ordered.push(awayLineup);
    assigned.add(awayLineup);
  }
  lineups
    .filter((lineup) => !assigned.has(lineup))
    .forEach((lineup) => ordered.push(lineup));

  if (ordered.length < 2 && lineups.length === 2) {
    lineups
      .filter((lineup) => !assigned.has(lineup))
      .forEach((lineup) => {
        if (ordered.length < 2) {
          ordered.push(lineup);
          assigned.add(lineup);
        }
      });
  }

  return ordered;
});

const activeStatView = computed<StatViewConfig | null>(() => {
  if (activeBottomView.value === "lineup" || !liveSnapshot.value) return null;

  const snapshot = liveSnapshot.value;
  const backendProgramStats = snapshot.programStats?.[activeBottomView.value];
  if (backendProgramStats) {
    return {
      id: activeBottomView.value,
      eyebrow: activeBottomView.value.toUpperCase(),
      title: {
        attack: "공격 지표",
        chance: "찬스 지표",
        control: "경기 운영",
        discipline: "징계 지표",
        group: "조 상황",
      }[activeBottomView.value],
      metrics: backendProgramStats.map((metric) => ({
        ...metric,
        id: metric.id ?? metric.label,
        graph: statGraphType(metric.label),
      })),
    };
  }

  const statGroups: Record<Exclude<BottomView, "lineup">, StatViewConfig> = {
    attack: {
      id: "attack",
      eyebrow: "ATTACK",
      title: "공격 지표",
      metrics: compactStats(snapshot.stats, ["xG", "유효슈팅", "슈팅정확도"]),
    },
    chance: {
      id: "chance",
      eyebrow: "CHANCE",
      title: "찬스 지표",
      metrics: compactStats(snapshot.stats, ["전체슈팅", "박스안슈팅", "코너킥"]),
    },
    control: {
      id: "control",
      eyebrow: "CONTROL",
      title: "경기 운영",
      metrics: compactStats(snapshot.stats, ["점유율", "패스성공률", "오프사이드"]),
    },
    discipline: {
      id: "discipline",
      eyebrow: "DISCIPLINE",
      title: "징계 지표",
      metrics: compactStats(snapshot.stats, ["파울", "옐로카드", "레드카드"]),
    },
    group: {
      id: "group",
      eyebrow: "GROUP",
      title: "조 상황",
      metrics: [],
    },
  };

  return statGroups[activeBottomView.value];
});

const groupStandingsRows = computed<GroupStandingsRowView[]>(() => {
  const rows = liveSnapshot.value?.standings?.rows;
  if (!Array.isArray(rows) || rows.length === 0) return [];

  return rows
    .map((row) => {
      const raw = row as Record<string, unknown>;

      const rank = Number(raw.rank);
      const played = Number(raw.played);
      const win = Number(raw.win);
      const draw = Number(raw.draw);
      const loss = Number(raw.loss);
      const goalsFor = Number(
        (raw.goals_for as string | number | undefined) ??
          (raw.goalsFor as string | number | undefined),
      );
      const goalsAgainst = Number(
        (raw.goals_against as string | number | undefined) ??
          (raw.goalsAgainst as string | number | undefined),
      );
      const goalDiff = Number(
        (raw.goal_diff as string | number | undefined) ??
          (raw.goalDiff as string | number | undefined),
      );
      const points = Number(raw.points);
      const teamId = Number(raw.team_id ?? raw.teamId);

      return {
        teamId: Number.isFinite(teamId) ? teamId : undefined,
        teamName: ((raw.team_code ?? raw.teamCode ?? "-") as string),
        teamCode: ((raw.team_code ?? raw.teamCode ?? "-") as string),
        rank: Number.isFinite(rank) ? rank : 0,
        played: Number.isFinite(played) ? played : 0,
        win: Number.isFinite(win) ? win : 0,
        draw: Number.isFinite(draw) ? draw : 0,
        loss: Number.isFinite(loss) ? loss : 0,
        goalsFor: Number.isFinite(goalsFor) ? goalsFor : 0,
        goalsAgainst: Number.isFinite(goalsAgainst) ? goalsAgainst : 0,
        goalDiff: Number.isFinite(goalDiff) ? goalDiff : 0,
        points: Number.isFinite(points) ? points : 0,
      };
    })
    .filter((row) => row.teamName || row.teamCode);
});

const momentumView = computed(() => {
  const snapshot = liveSnapshot.value;
  const momentum = snapshot?.momentum;
  const kickoffTime = snapshot?.kickoffAt ? Date.parse(snapshot.kickoffAt) : Number.NaN;
  const isFutureFixture = Number.isFinite(kickoffTime) && kickoffTime > Date.now();
  if (!snapshot || !momentum) {
    return {
      available: false,
      home: 50,
      away: 50,
      title: "",
      detail: "",
      homeLabel: snapshot?.homeCode ?? "HOME",
      awayLabel: snapshot?.awayCode ?? "AWAY",
      trend: "unavailable",
      history: [],
      emptyMessage: "아직 이 경기의 모멘텀 데이터가 없습니다",
    };
  }

  if (!momentum.available) {
    const detail = momentum.reasons[0] ?? "아직 이 경기의 모멘텀 데이터가 없습니다";
    const noMomentumData = detail.includes("모멘텀 데이터");
    return {
      available: false,
      home: 50,
      away: 50,
      title: isFutureFixture ? "" : noMomentumData ? "모멘텀 데이터 없음" : "중계되지 않은 경기",
      detail: isFutureFixture ? "" : detail,
      homeLabel: snapshot.homeCode,
      awayLabel: snapshot.awayCode,
      trend: "unavailable",
      history: [],
      emptyMessage: isFutureFixture ? "" : detail,
    };
  }

  const trendLabel =
    momentum.trend === "home"
      ? `${snapshot.homeCode} 흐름`
      : momentum.trend === "away"
        ? `${snapshot.awayCode} 흐름`
        : "균형 흐름";
  return {
    available: true,
    home: momentum.home,
    away: momentum.away,
    title: trendLabel,
    detail: momentum.reasons.slice(0, 2).join(" · ") || "최근 2분 변화량 기준",
    homeLabel: snapshot.homeCode,
    awayLabel: snapshot.awayCode,
    trend: momentum.trend,
    history: momentum.history ?? [],
    emptyMessage: "",
  };
});

const momentumChartPoints = computed(() =>
  momentumView.value.history.length
    ? momentumView.value.history
    : [{ elapsed: null, value: 0 }],
);

const aiReviewHydration = computed(() => {
  const history = liveSnapshot.value?.momentum?.history ?? [];
  const maxMinute = history.reduce((max, point) => {
    const minute =
      typeof point.minuteKey === "number"
        ? point.minuteKey
        : typeof point.elapsed === "number"
          ? point.elapsed + (typeof point.extra === "number" ? Math.max(0, point.extra) : 0)
          : null;
    return typeof minute === "number" ? Math.max(max, minute) : max;
  }, 0);
  return {
    ready: maxMinute >= 23,
    maxMinute,
    message:
      maxMinute >= 23
        ? "AI 경기리뷰 생성 가능"
        : `23분 모멘텀 데이터 수집 후 활성화 (${maxMinute || 0}/23)`,
  };
});

const aiReviewButtonDisabled = computed(
  () => !liveSnapshot.value || !aiReviewHydration.value.ready || aiReviewStatus.value === "loading",
);

const aiReviewBasisLabel = computed(() => {
  const basis = aiReviewResult.value?.reviewBasis;
  if (!basis) return "";
  const matchClock =
    basis.matchClockLabel ||
    (basis.clock ? `경기시각 ${basis.clock} 기준` : typeof basis.minute === "number" ? `${basis.minute}분 기준` : "");
  const phase = basis.phaseLabel || basis.status || "";
  const cacheLabel = aiReviewResult.value?.cached ? "캐시" : "생성";
  const parts = [matchClock, phase, cacheLabel].filter(Boolean);
  return parts.join(" · ");
});

async function requestAiReview(forceRefresh = false) {
  const fixtureId = liveSnapshot.value?.fixtureId;
  if (!fixtureId || aiReviewButtonDisabled.value) return;
  isMomentumPanelOpen.value = false;
  isAiReviewPanelOpen.value = true;
  aiReviewStatus.value = "loading";
  aiReviewError.value = "";
  try {
    const result = await fetchApiFootballAiReview(fixtureId, { forceRefresh });
    aiReviewResult.value = result;
    aiReviewStatus.value = result.available ? "ready" : "error";
    aiReviewError.value = result.available ? "" : result.message ?? "AI 경기리뷰를 아직 생성할 수 없습니다.";
  } catch (error) {
    aiReviewStatus.value = "error";
    aiReviewError.value = (error as Error).message;
  }
}

function isUsableStandingsPayload(
  standings: NonNullable<ApiFootballBroadcastSnapshot["standings"]> | null | undefined,
): standings is NonNullable<ApiFootballBroadcastSnapshot["standings"]> {
  const rows = standings?.rows;
  if (!Array.isArray(rows) || rows.length === 0) return false;

  return rows.some((row) => {
    const played = Number(row.played);
    const win = Number(row.win);
    const draw = Number(row.draw);
    const loss = Number(row.loss);
    const goalsFor = Number(row.goals_for);
    const goalsAgainst = Number(row.goals_against);
    const points = Number(row.points);

    return [played, win, draw, loss, goalsFor, goalsAgainst, points].some(
      (value) => Number.isFinite(value) && value > 0,
    );
  });
}

function stableStandingsPayload(
  next: ApiFootballBroadcastSnapshot["standings"] | null | undefined,
  previous: ApiFootballBroadcastSnapshot["standings"] | null | undefined,
) {
  if (isUsableStandingsPayload(next)) return next;
  return previous ?? next ?? undefined;
}

function normalizePlayerLookupValue(value?: string) {
  return value?.trim().toLowerCase();
}

function buildLineupPlayerStatLookup(snapshot: ApiFootballBroadcastSnapshot | null) {
  const map = new Map<number, Partial<ApiFootballBroadcastLineupPlayer>>();
  if (!snapshot?.playerStats) return map;

  Object.entries(snapshot.playerStats).forEach(([rawId, entry]) => {
    const parsedId = Number.parseInt(rawId, 10);
    if (Number.isSafeInteger(parsedId)) {
      map.set(parsedId, entry);
    }
  });

  return map;
}

function lineupPlayerLookupKeys(player: LineupPlayerView) {
  const keys = new Set<string>();

  if (player.id !== undefined) {
    keys.add(`id:${player.id}`);
    return keys;
  }

  const playerName = normalizePlayerLookupValue(player.name);
  const playerLongName = normalizePlayerLookupValue(player.longName);
  if (playerName) keys.add(`name:${playerName}`);
  if (playerLongName) keys.add(`name:${playerLongName}`);
  return keys;
}

function eventLookupKeys(event: ApiFootballBroadcastEvent) {
  const keys = new Set<string>();
  const playerName = normalizePlayerLookupValue(event.player);
  const assistName = normalizePlayerLookupValue(event.assist);
  const inName = normalizePlayerLookupValue(event.inPlayer);
  const outName = normalizePlayerLookupValue(event.outPlayer);

  if (event.playerId !== undefined) keys.add(`id:${event.playerId}`);
  if (event.assistId !== undefined) keys.add(`id:${event.assistId}`);
  if (playerName) keys.add(`name:${playerName}`);
  if (assistName) keys.add(`name:${assistName}`);
  if (inName) keys.add(`name:${inName}`);
  if (outName) keys.add(`name:${outName}`);

  return keys;
}

function eventScorerLookupKeys(event: ApiFootballBroadcastEvent) {
  const keys = new Set<string>();
  const playerName = normalizePlayerLookupValue(event.player);

  if (event.playerId !== undefined) keys.add(`id:${event.playerId}`);
  if (playerName) keys.add(`name:${playerName}`);

  return keys;
}

const lineupPlayerEventSummary = computed<Map<string, { goals: number; yellowCards: number; redCards: number }>>(() => {
  const snapshot = liveSnapshot.value;
  const result = new Map<string, { goals: number; yellowCards: number; redCards: number }>();

  if (!snapshot) return result;

  snapshot.events.forEach((event) => {
    const isGoal = event.kind === "goal";
    const isYellowCard = event.kind === "yellow-card";
    const isRedCard =
      event.kind === "red-card" ||
      (event.kind === "card" && event.detail === "Red Card");

    if (!isGoal && !isYellowCard && !isRedCard) return;

    const keys = isGoal ? eventScorerLookupKeys(event) : eventLookupKeys(event);
    keys.forEach((key) => {
      const existing = result.get(key);
      if (existing) {
        if (isGoal) existing.goals += 1;
        if (isYellowCard) existing.yellowCards += 1;
        if (isRedCard) existing.redCards += 1;
        return;
      }

      result.set(key, {
        goals: isGoal ? 1 : 0,
        yellowCards: isYellowCard ? 1 : 0,
        redCards: isRedCard ? 1 : 0,
      });
    });
  });

  return result;
});

function getPlayerGoalCount(entry: LineupPlayerView) {
  if (entry.eventSummary) return entry.eventSummary.goals;
  if (entry.statGoals !== undefined && entry.statGoals > 0) return entry.statGoals;

  const keys = lineupPlayerLookupKeys(entry);
  for (const key of keys) {
    const summary = lineupPlayerEventSummary.value.get(key);
    if (summary) return summary.goals;
  }
  return 0;
}

function getPlayerYellowCardCount(entry: LineupPlayerView) {
  if (entry.eventSummary) return entry.eventSummary.yellowCards;
  const keys = lineupPlayerLookupKeys(entry);
  for (const key of keys) {
    const summary = lineupPlayerEventSummary.value.get(key);
    if (summary) return summary.yellowCards;
  }
  return 0;
}

function playerCardLabel(entry: LineupPlayerView) {
  if (entry.eventSummary) return entry.eventSummary.cardLabel;
  if (getPlayerRedCardCount(entry) > 0) return "RED";
  if (getPlayerYellowCardCount(entry) > 0) return "YEL";
  return "";
}

function getPlayerRedCardCount(entry: LineupPlayerView) {
  if (entry.eventSummary) return entry.eventSummary.redCards;
  const keys = lineupPlayerLookupKeys(entry);
  for (const key of keys) {
    const summary = lineupPlayerEventSummary.value.get(key);
    if (summary) return summary.redCards;
  }
  return 0;
}

const selectedLineupPlayerSummary = computed(() => {
  const player = selectedLineupPlayer.value;
  const snapshot = liveSnapshot.value;
  if (!player || !snapshot) return null;

  const summary = {
    goals: 0,
    assists: 0,
    yellowCards: 0,
    redCards: 0,
    substitutions: 0,
    minutes: player.minutes,
    shotsTotal: player.shotsTotal,
    shotsOnGoal: player.shotsOnGoal,
    passes: player.passesTotal,
    passesAccurate: player.passesAccurate,
    passesAccuracyPct: player.passesAccuracyPct,
    keyPasses: player.keyPasses,
    fouls: player.foulsCommitted,
    statGoals: player.statGoals,
    statAssists: player.statAssists,
    saves: player.saves,
    goalsConceded: player.goalsConceded,
    tacklesTotal: player.tacklesTotal,
    blocks: player.blocks,
    interceptions: player.interceptions,
    duelsTotal: player.duelsTotal,
    duelsWon: player.duelsWon,
    dribblesAttempts: player.dribblesAttempts,
    dribblesSuccess: player.dribblesSuccess,
  };

  snapshot.events.forEach((event) => {
    const playerKeys = lineupPlayerLookupKeys(player);
    const eventKeys = eventLookupKeys(event);
    const isPlayer = [...playerKeys].some((key) => eventKeys.has(key));

    if (!isPlayer) return;

    if (event.kind === "goal" || event.kind === "own-goal") {
      summary.goals += Number(event.playerId !== undefined ? player.id === event.playerId : event.player === player.name);
      summary.assists += Number(event.assistId !== undefined ? player.id === event.assistId : event.assist === player.name);
    }

    if (event.kind === "yellow-card") summary.yellowCards += 1;
    if (
      event.kind === "red-card" ||
      (event.kind === "card" && event.detail === "Red Card")
    ) {
      summary.redCards += 1;
    }
    if (event.kind === "substitution") summary.substitutions += 1;
  });

  if (summary.statGoals !== undefined) summary.goals = summary.statGoals;
  if (summary.statAssists !== undefined) summary.assists = summary.statAssists;

  return summary;
});

function formatStatValue(value?: number | null, unit?: string): string {
  if (value === undefined || value === null) return unit ? `0${unit}` : "0";
  return unit ? `${value}${unit}` : String(value);
}

function formatShotsLabel(shots?: number | null, shotsOnGoal?: number | null): string {
  const value = formatStatValue(shots);
  const onTarget = formatStatValue(shotsOnGoal);
  return `${value}/${onTarget}`;
}

function formatPassValue(accurate?: number | null, total?: number | null): string {
  return `${formatStatValue(accurate)}/${formatStatValue(total)}`;
}

function formatCardPair(yellow?: number | null, red?: number | null): string {
  return `${formatStatValue(yellow)}/${formatStatValue(red)}`;
}

function formatPairValue(left?: number | null, right?: number | null): string {
  return `${formatStatValue(left)}/${formatStatValue(right)}`;
}

function formatPercentValue(value?: number | null): string {
  return formatStatValue(value, "%");
}

const selectedLineupPlayerStats = computed(() => {
  const player = selectedLineupPlayer.value;
  const summary = selectedLineupPlayerSummary.value;
  if (!player || !summary) return [];

  const common = [
    { label: "출전시간", value: formatStatValue(summary.minutes, "'") },
    { label: "평점", value: player.rating ? formatRatingValue(player.rating) : "0" },
  ];
  const cards = { label: "카드", value: formatCardPair(summary.yellowCards, summary.redCards) };
  const pos = (player.pos ?? "").toUpperCase();

  if (pos === "G") {
    return [
      ...common,
      { label: "세이브", value: formatStatValue(summary.saves) },
      { label: "실점", value: formatStatValue(summary.goalsConceded) },
      { label: "패스", value: formatPassValue(summary.passesAccurate, summary.passes) },
      { label: "패스성공률", value: formatPercentValue(summary.passesAccuracyPct) },
      cards,
    ];
  }

  if (pos === "D") {
    return [
      ...common,
      { label: "태클", value: formatStatValue(summary.tacklesTotal) },
      { label: "인터셉트", value: formatStatValue(summary.interceptions) },
      { label: "블록", value: formatStatValue(summary.blocks) },
      { label: "경합", value: formatPairValue(summary.duelsWon, summary.duelsTotal) },
      { label: "패스성공률", value: formatPercentValue(summary.passesAccuracyPct) },
      cards,
    ];
  }

  if (pos === "M") {
    return [
      ...common,
      { label: "패스", value: formatPassValue(summary.passesAccurate, summary.passes) },
      { label: "패스성공률", value: formatPercentValue(summary.passesAccuracyPct) },
      { label: "키패스", value: formatStatValue(summary.keyPasses) },
      { label: "경합", value: formatPairValue(summary.duelsWon, summary.duelsTotal) },
      { label: "슈팅(유효)", value: formatShotsLabel(summary.shotsTotal, summary.shotsOnGoal) },
      cards,
    ];
  }

  return [
    ...common,
    { label: "득점", value: formatStatValue(summary.goals) },
    { label: "어시스트", value: formatStatValue(summary.assists) },
    { label: "슈팅(유효)", value: formatShotsLabel(summary.shotsTotal, summary.shotsOnGoal) },
    { label: "드리블", value: formatPairValue(summary.dribblesSuccess, summary.dribblesAttempts) },
    { label: "패스성공률", value: formatPercentValue(summary.passesAccuracyPct) },
    cards,
  ];
});

const selectedLineupPlayerDisplay = computed(() => {
  const player = selectedLineupPlayer.value;
  if (!player) return null;

  const fullName = (player.longName ?? player.name ?? "").trim();
  const shortName = (player.name ?? player.longName ?? "").trim();
  const teamShortName = (player.teamCode ?? player.teamName ?? "").trim();

  return {
    fullName: fullName || shortName || "-",
    shortName: shortName || fullName || "-",
    teamShortName: teamShortName || "-",
  };
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
    rating: player.rating,
    photoUrl: player.photoUrl,
    minutes: player.minutes,
    shotsTotal: player.shotsTotal,
    shotsOnGoal: player.shotsOnGoal,
    passesTotal: player.passesTotal,
    passesAccurate: player.passesAccurate,
    passesAccuracyPct: player.passesAccuracyPct,
    keyPasses: player.keyPasses,
    foulsCommitted: player.foulsCommitted,
    statGoals: player.statGoals,
    statAssists: player.statAssists,
    saves: player.saves,
    goalsConceded: player.goalsConceded,
    tacklesTotal: player.tacklesTotal,
    blocks: player.blocks,
    interceptions: player.interceptions,
    duelsTotal: player.duelsTotal,
    duelsWon: player.duelsWon,
    dribblesAttempts: player.dribblesAttempts,
    dribblesSuccess: player.dribblesSuccess,
    statYellowCards: player.statYellowCards,
    statRedCards: player.statRedCards,
    eventSummary: player.eventSummary,
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
  playerStats = new Map<number, Partial<ApiFootballBroadcastLineupPlayer>>(),
): TeamLineupView {
  const players = lineup.players.slice(0, 11).map(toLineupPlayerView);
  const substitutionEvents = events.filter(
    (event) =>
      event.kind === "substitution" &&
      event.teamId === lineup.teamId &&
      appliedIds.has(event.id),
  );

  substitutionEvents.forEach((event) => {
    const outPlayer =
      findDirectSubstitutionOutPlayer(players, event) ??
      findMinuteFallbackSubstitutionOutPlayer(players, events, event);
    const outIndex = outPlayer
      ? players.findIndex((player) => player.slotIndex === outPlayer.slotIndex)
      : -1;
    if (outIndex < 0) return;

    const inId = event.assistId;
    const inNumber =
      event.inPlayerNumber ??
      (inId !== undefined
        ? lineup.substituteNumbers[String(inId)]
        : undefined) ??
      players[outIndex].number;
    const inPlayer = inId !== undefined
      ? lineup.players.find((candidate) => candidate.id === inId) ?? playerStats.get(inId)
      : undefined;

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
        inPlayer?.name ??
        "교체 선수",
      longName:
        event.inPlayer ??
        event.assist ??
        inPlayer?.longName,
      pos: players[outIndex].pos,
      grid: players[outIndex].grid,
      rating: inPlayer?.rating,
      photoUrl: inPlayer?.photoUrl,
      minutes: inPlayer?.minutes,
      shotsTotal: inPlayer?.shotsTotal,
      shotsOnGoal: inPlayer?.shotsOnGoal,
      passesTotal: inPlayer?.passesTotal,
      passesAccurate: inPlayer?.passesAccurate,
      passesAccuracyPct: inPlayer?.passesAccuracyPct,
      keyPasses: inPlayer?.keyPasses,
      foulsCommitted: inPlayer?.foulsCommitted,
      statGoals: inPlayer?.statGoals,
      statAssists: inPlayer?.statAssists,
      saves: inPlayer?.saves,
      goalsConceded: inPlayer?.goalsConceded,
      tacklesTotal: inPlayer?.tacklesTotal,
      blocks: inPlayer?.blocks,
      interceptions: inPlayer?.interceptions,
      duelsTotal: inPlayer?.duelsTotal,
      duelsWon: inPlayer?.duelsWon,
      dribblesAttempts: inPlayer?.dribblesAttempts,
      dribblesSuccess: inPlayer?.dribblesSuccess,
      statYellowCards: inPlayer?.statYellowCards,
      statRedCards: inPlayer?.statRedCards,
      eventSummary: inPlayer?.eventSummary,
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

function eventElapsedMinute(event: ApiFootballBroadcastEvent) {
  const match = event.minute.match(/^(\d+)/);
  return match ? Number(match[1]) : undefined;
}

function findDirectSubstitutionOutPlayer(
  players: LineupPlayerView[],
  event: ApiFootballBroadcastEvent,
) {
  return players.find((player) =>
    event.playerId !== undefined
      ? player.id === event.playerId
      : player.name === event.outPlayer || player.longName === event.outPlayer,
  );
}

function findMinuteFallbackSubstitutionOutPlayer(
  players: LineupPlayerView[],
  events: ApiFootballBroadcastEvent[],
  event: ApiFootballBroadcastEvent,
) {
  const minute = eventElapsedMinute(event);
  if (minute === undefined) return undefined;

  const occupiedSlots = new Set<number>();
  events
    .filter(
      (candidate) =>
        candidate.id !== event.id &&
        candidate.kind === "substitution" &&
        candidate.teamId === event.teamId &&
        eventElapsedMinute(candidate) === minute,
    )
    .forEach((candidate) => {
      const matched = findDirectSubstitutionOutPlayer(players, candidate);
      if (matched) occupiedSlots.add(matched.slotIndex);
    });

  const minuteCandidates = players.filter(
    (player) =>
      player.minutes !== undefined &&
      Math.trunc(player.minutes) === minute &&
      !occupiedSlots.has(player.slotIndex),
  );

  return minuteCandidates.length === 1 ? minuteCandidates[0] : undefined;
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
  const playerStatsLookup = buildLineupPlayerStatLookup(liveSnapshot.value);
  const baseLineup = applySubstitutionsToLineup(
    lineup,
    events,
    appliedSubstitutionIds.value,
    playerStatsLookup,
  );

  const directMatch = findDirectSubstitutionOutPlayer(baseLineup.players, event);
  if (directMatch) return directMatch;

  return findMinuteFallbackSubstitutionOutPlayer(
    baseLineup.players,
    events,
    event,
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
    "lineup-player--sent-off":
      entry.kind === "player" && getPlayerRedCardCount(entry) > 0,
  };
}

function isLineupPlayerEntry(
  entry: LineupEntryView,
): entry is LineupPlayerView {
  return entry.kind === "player";
}

function openLineupPlayerProfile(
  entry: LineupPlayerView,
  lineup: TeamLineupView,
) {
  selectedLineupPlayer.value = {
    ...entry,
    teamName: lineup.name,
    teamCode: lineup.code,
    teamId: lineup.teamId,
  };
}

function closeLineupPlayerProfile() {
  selectedLineupPlayer.value = null;
}

function formatRatingValue(rating?: string): string {
  if (typeof rating !== "string") return "";
  const parsed = Number.parseFloat(rating);
  return Number.isFinite(parsed) ? parsed.toFixed(1) : "";
}

function ratingColorStyle(rating?: string) {
  const parsed = Number.parseFloat(rating ?? "");
  if (!Number.isFinite(parsed)) return {};

  const clamped = Math.min(10, Math.max(0, parsed));
  const low = { r: 190, g: 12, b: 12 };
  const high = { r: 12, g: 60, b: 215 };
  const t =
    clamped <= 6
      ? 0
      : clamped >= 8
      ? 1
      : (clamped - 6) / 2;
  const mid = {
    r: Math.round(low.r + (high.r - low.r) * t),
    g: Math.round(low.g + (high.g - low.g) * t),
    b: Math.round(low.b + (high.b - low.b) * t),
  };

  const start = `rgb(${Math.max(22, Math.round(mid.r * 0.76))}, ${Math.max(10, Math.round(mid.g * 0.78))}, ${Math.max(18, Math.round(mid.b * 0.76))})`;
  const end = `rgb(${mid.r}, ${mid.g}, ${mid.b})`;
  const border = `rgb(${Math.min(255, mid.r + 18)}, ${Math.min(255, mid.g + 18)}, ${Math.min(255, mid.b + 18)})`;

  return {
    backgroundImage: `linear-gradient(128deg, ${start} 0%, ${end} 100%)`,
    borderColor: border,
    boxShadow:
      `0 0.12rem 0.32rem rgba(0, 0, 0, 0.42), inset 0 0 0 0.06rem ${border}`,
    backgroundColor: end,
    color: "#ffffff",
  };
}

function ratingClass(rating?: string) {
  const parsed = Number.parseFloat(rating ?? "");
  if (!Number.isFinite(parsed)) return "rating-neutral";
  if (parsed <= 6) return "rating-low";
  if (parsed >= 8) return "rating-high";
  return "rating-mid";
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
    const stat = statMetricForLabel(stats, label);
    if (!stat) return [];
    seen.add(label);
    return [stat];
  });
}

function statMetricForLabel(
  stats: ApiFootballBroadcastStat[],
  label: string,
): StatViewMetric | null {
  if (label === "슈팅정확도") return shootingAccuracyMetric(stats);

  const stat = findStat(stats, label);
  if (!stat) return null;

  return {
    id: stat.label,
    label: stat.label,
    home: stat.home,
    away: stat.away,
    homePct: stat.homePct,
    awayPct: stat.awayPct,
    graph: statGraphType(stat.label),
  };
}

function numericStatValue(
  stats: ApiFootballBroadcastStat[],
  label: string,
  side: "home" | "away",
): number | null {
  const stat = findStat(stats, label);
  if (!stat) return null;

  const parsed = Number.parseFloat(stat[side].replace("%", ""));
  return Number.isFinite(parsed) ? parsed : null;
}

function metricPctPair(home: number, away: number) {
  const homeValue = Math.max(0, home);
  const awayValue = Math.max(0, away);
  const total = homeValue + awayValue;
  if (total <= 0) return { homePct: 50, awayPct: 50 };

  return {
    homePct: (homeValue / total) * 100,
    awayPct: (awayValue / total) * 100,
  };
}

function shootingAccuracyMetric(
  stats: ApiFootballBroadcastStat[],
): StatViewMetric | null {
  const homeShots = numericStatValue(stats, "전체슈팅", "home");
  const awayShots = numericStatValue(stats, "전체슈팅", "away");
  const homeOnTarget = numericStatValue(stats, "유효슈팅", "home");
  const awayOnTarget = numericStatValue(stats, "유효슈팅", "away");
  if (
    homeShots === null ||
    awayShots === null ||
    homeOnTarget === null ||
    awayOnTarget === null
  )
    return null;

  const homeAccuracy = homeShots > 0 ? (homeOnTarget / homeShots) * 100 : 0;
  const awayAccuracy = awayShots > 0 ? (awayOnTarget / awayShots) * 100 : 0;
  const pct = metricPctPair(homeAccuracy, awayAccuracy);

  return {
    id: "shooting-accuracy",
    label: "슈팅정확도",
    home: `${Math.round(homeAccuracy)}%`,
    away: `${Math.round(awayAccuracy)}%`,
    homePct: pct.homePct,
    awayPct: pct.awayPct,
    graph: "bar",
  };
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
  if (nextView === activeBottomView.value) return;
  isMomentumPanelOpen.value = false;
  isAiReviewPanelOpen.value = false;

  const currentIndex = bottomViewTabs.findIndex(
    (tab) => tab.id === activeBottomView.value,
  );
  const nextIndex = bottomViewTabs.findIndex((tab) => tab.id === nextView);
  if (currentIndex === -1 || nextIndex === -1) {
    activeBottomView.value = nextView;
    return;
  }

  bottomViewTransitionDirection.value =
    nextIndex > currentIndex ? "next" : "prev";
  activeBottomView.value = nextView;
}

watch(
  () => liveSnapshot.value?.fixtureId,
  () => {
    isAiReviewPanelOpen.value = false;
    aiReviewStatus.value = "idle";
    aiReviewResult.value = null;
    aiReviewError.value = "";
  },
);

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
    g: "group",
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
    const snapshot =
      requestedFixtureId !== null
        ? await fetchApiFootballBroadcastSnapshot(requestedFixtureId)
        : await fetchApiFootballFirstLiveFixture();
    const previousStandings = liveSnapshot.value?.standings;
    liveSnapshot.value = {
      ...snapshot,
      standings: stableStandingsPayload(
        snapshot.standings,
        previousStandings,
      ),
    };
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
      <section class="feed-surface" data-testid="program-feed-surface"></section>

      <section
        class="bottom-program-panel"
        data-testid="program-bottom-panel"
        :data-active-bottom-view="activeBottomView"
        aria-live="polite"
      >
        <div
          v-if="!liveSnapshot"
          class="program-live-state"
          data-testid="program-live-empty"
        >
          <span>라이브 데이터</span>
          <strong>{{ liveStateLabel }}</strong>
        </div>

        <div
          v-else
          class="bottom-content-grid"
          :data-transition-direction="bottomViewTransitionDirection"
        >
          <Transition name="bottom-view" mode="out-in">
            <div
              v-if="activeBottomView === 'lineup'"
              key="lineup"
              class="lineup-board"
              data-testid="program-lineup-view"
            >
              <Transition name="bottom-view" mode="out-in">
                <template v-if="selectedLineupPlayer">
                  <aside
                    :key="selectedLineupPlayer?.key ?? 'lineup-player-panel'"
                    id="broadcast-player-detail-panel"
                    class="player-detail-panel player-panel-state"
                  >
                    <header class="player-detail-header">
                      <button
                        type="button"
                        class="player-detail-close"
                        @click="closeLineupPlayerProfile"
                        aria-label="선수 상세 닫기"
                      >
                        닫기
                      </button>
                    </header>
                    <div class="player-detail-content">
                      <section class="player-detail-profile">
                        <div class="player-detail-media">
                          <div class="player-detail-identity">
                            <div class="player-detail-photo-wrap">
                              <img
                                v-if="selectedLineupPlayer.photoUrl"
                                class="player-detail-photo"
                                :src="selectedLineupPlayer.photoUrl"
                                :alt="`${selectedLineupPlayerDisplay?.fullName} 사진`"
                              />
                              <span v-else class="player-detail-photo-empty">
                                {{ selectedLineupPlayer.number }}
                              </span>
                            </div>
                            <span class="player-detail-number-plate">
                              {{ selectedLineupPlayer.number }}
                            </span>
                            <span
                              v-if="selectedLineupPlayer.rating"
                              :class="`lineup-player-rating-text lineup-player-rating-text--${ratingClass(selectedLineupPlayer.rating)}`"
                            >
                              {{ formatRatingValue(selectedLineupPlayer.rating) }}
                            </span>
                            <span v-else class="lineup-player-rating-text lineup-player-rating-text--rating-neutral">
                              0
                            </span>
                          </div>
                          <div class="player-detail-name-block">
                            <p class="player-detail-shortname">
                              {{ selectedLineupPlayerDisplay?.shortName }}
                            </p>
                            <p class="player-detail-fullname">
                              {{ selectedLineupPlayerDisplay?.fullName }}
                            </p>
                            <p class="player-detail-team">
                              {{ selectedLineupPlayerDisplay?.teamShortName }}
                            </p>
                          </div>
                        </div>
                      </section>
                      <section class="player-detail-stats">
                        <dl>
                          <div
                            v-for="stat in selectedLineupPlayerStats"
                            :key="stat.label"
                          >
                            <dt>{{ stat.label }}</dt>
                            <dd>{{ stat.value }}</dd>
                          </div>
                        </dl>
                      </section>
                    </div>
                  </aside>
                </template>
                <template v-else>
                  <div
                    key="lineup-boards"
                    class="lineup-board-content player-panel-state"
                  >
                    <article
                      v-for="(lineup, lineupIndex) in currentLineups.slice(0, 2)"
                      :key="lineup.teamId ?? lineup.code"
                      class="lineup-team"
                      :class="[
                        lineupIndex === 0 ? 'lineup-team-home' : 'lineup-team-away',
                      ]"
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
                            :tabindex="entry.kind === 'player' ? 0 : -1"
                            role="button"
                            :aria-label="
                              entry.kind === 'player'
                                ? `${entry.number}번 ${entry.name} 정보`
                                : '감독'
                            "
                            aria-expanded="false"
                            @click="
                              entry.kind === 'player'
                                ? openLineupPlayerProfile(entry, lineup)
                                : undefined
                            "
                            @keydown="
                              (event: KeyboardEvent) => {
                                if (
                                  entry.kind === 'player' &&
                                  (event.key === 'Enter' || event.key === ' ')
                                ) {
                                  event.preventDefault()
                                  openLineupPlayerProfile(entry, lineup)
                                }
                              }
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
                            <span
                              v-if="isLineupPlayerEntry(entry)"
                              class="lineup-entry-meta"
                            >
                              <span
                                class="lineup-entry-meta-cell lineup-entry-goal-cell"
                              >
                                <span
                                  v-if="getPlayerGoalCount(entry) > 0"
                                  class="lineup-entry-goal"
                                  :data-goals="getPlayerGoalCount(entry)"
                                >
                                  <img :src="goalSoccerBallUrl" alt="" aria-hidden="true" />
                                  <b v-if="getPlayerGoalCount(entry) > 1">{{ getPlayerGoalCount(entry) }}</b>
                                </span>
                                <span v-else class="lineup-entry-meta-empty" aria-hidden="true">
                                  -
                                </span>
                              </span>
                              <span
                                class="lineup-entry-meta-cell lineup-entry-card-cell"
                              >
                                <span
                                  v-if="playerCardLabel(entry)"
                                  class="lineup-entry-card"
                                  :data-card="playerCardLabel(entry)"
                                >
                                  {{ playerCardLabel(entry) }}
                                </span>
                                <span v-else class="lineup-entry-meta-empty" aria-hidden="true">
                                  -
                                </span>
                              </span>
                              <span
                                class="lineup-entry-meta-cell lineup-entry-rating-cell"
                              >
                                <span
                                  v-if="entry.rating"
                                  class="lineup-entry-rating"
                                  :style="ratingColorStyle(entry.rating)"
                                  :class="
                                    `lineup-entry-rating--${ratingClass(entry.rating)}`
                                  "
                                >
                                  {{ formatRatingValue(entry.rating) }}
                                </span>
                                <span v-else class="lineup-entry-meta-empty" aria-hidden="true">
                                  -
                                </span>
                              </span>
                            </span>
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
                </template>
              </Transition>
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
                <div v-if="activeStatView?.id === 'attack'" class="stats-action-row">
                  <button
                    type="button"
                    class="momentum-open-button"
                    :class="{ 'momentum-open-button--active': isMomentumPanelOpen }"
                    data-testid="program-momentum-open"
                    @click="isAiReviewPanelOpen = false; isMomentumPanelOpen = !isMomentumPanelOpen"
                  >
                    모멘텀
                  </button>
                  <button
                    type="button"
                    class="ai-review-open-button"
                    :class="{ 'ai-review-open-button--active': isAiReviewPanelOpen }"
                    :disabled="aiReviewButtonDisabled"
                    :title="aiReviewHydration.message"
                    data-testid="program-ai-review-open"
                    @click="requestAiReview()"
                  >
                    AI 리뷰
                  </button>
                </div>
              </header>
              <aside
                v-if="activeStatView?.id === 'attack' && isMomentumPanelOpen"
                class="momentum-panel"
                :class="{ 'momentum-panel--unavailable': !momentumView.available }"
                data-testid="program-momentum-panel"
              >
                <header>
                  <span>LIVE MOMENTUM</span>
                  <div class="momentum-title-row">
                    <strong>{{ momentumView.title }}</strong>
                    <button
                      type="button"
                      class="momentum-info-button"
                      aria-label="모멘텀 계산식 설명"
                    >
                      i
                      <span class="momentum-info-popover" role="tooltip">
                        <b>모멘텀 계산식</b>
                        <em>최근 변화량 12개 샘플을 가중 평균합니다.</em>
                        <small>득점 +8, xG +16, 슈팅 +0.8, 유효슈팅 +2, 박스 안 슈팅 +1.2, 코너킥 +1, 위험 이벤트 +3을 최근 샘플 가중치로 합산합니다.</small>
                        <small>xG가 없으면 슈팅 +1.2, 유효슈팅 +3, 박스 안 슈팅 +2로 대체해 기회 품질을 추정합니다.</small>
                        <small>패스 성공은 +0.02씩 최대 +2까지만 반영하고, 상대 경고 +0.4, 우리 경고 -0.3을 적용합니다.</small>
                        <small>현재 퇴장 수는 상대 퇴장당 +2.5, 우리 퇴장당 -2.5로 지속 보정합니다.</small>
                        <small>최종 점수는 양 팀 모두 기본값 12를 더한 뒤 비율화하며, 이 값은 승률이나 점유율이 아닙니다.</small>
                      </span>
                    </button>
                  </div>
                  <div v-if="momentumView.available" class="momentum-summary-row">
                    <b class="momentum-score momentum-score--home">
                      <span>{{ momentumView.homeLabel }}</span>
                      <strong>{{ momentumView.home }}</strong>
                    </b>
                    <small>{{ momentumView.detail }}</small>
                    <b class="momentum-score momentum-score--away">
                      <strong>{{ momentumView.away }}</strong>
                      <span>{{ momentumView.awayLabel }}</span>
                    </b>
                  </div>
                  <div v-else class="momentum-empty-message">
                    {{ momentumView.emptyMessage || "아직 이 경기의 모멘텀 데이터가 없습니다" }}
                  </div>
                  <button
                    type="button"
                    class="momentum-close-button"
                    aria-label="모멘텀 패널 닫기"
                    @click="isMomentumPanelOpen = false"
                  >
                    닫기
                  </button>
                </header>
                <div v-if="momentumView.available" class="momentum-panel-chart">
                  <ProgramMomentumLineChart :points="momentumChartPoints" />
                </div>
              </aside>
              <aside
                v-if="activeStatView?.id === 'attack' && isAiReviewPanelOpen"
                class="ai-review-panel"
                data-testid="program-ai-review-panel"
              >
                <header>
                  <span>AI MATCH REVIEW</span>
                  <i
                    v-if="aiReviewStatus === 'loading'"
                    class="ai-review-spinner"
                    aria-hidden="true"
                  ></i>
                  <strong>
                    {{
                      aiReviewStatus === "loading"
                        ? "생성 중"
                        : aiReviewResult?.commentary?.headline || "AI 경기리뷰"
                    }}
                  </strong>
                  <small v-if="aiReviewBasisLabel" class="ai-review-basis">
                    {{ aiReviewBasisLabel }}
                  </small>
                  <div class="ai-review-header-actions">
                    <button
                      type="button"
                      class="ai-review-refresh-button"
                      :disabled="aiReviewButtonDisabled"
                      aria-label="AI 경기리뷰 새로고침"
                      data-testid="program-ai-review-refresh"
                      @click="requestAiReview(true)"
                    >
                      새로고침
                    </button>
                    <button
                      type="button"
                      class="momentum-close-button"
                      aria-label="AI 경기리뷰 패널 닫기"
                      @click="isAiReviewPanelOpen = false"
                    >
                      닫기
                    </button>
                  </div>
                </header>
                <div class="ai-review-body">
                  <p v-if="aiReviewStatus === 'loading'" class="ai-review-muted">
                    경기 데이터와 모멘텀 변화량을 정리하고 있습니다.
                  </p>
                  <template v-else-if="aiReviewStatus === 'ready' && aiReviewResult?.commentary">
                    <strong>{{ aiReviewResult.commentary.oneLineSummary }}</strong>
                    <p>{{ aiReviewResult.commentary.mainCommentary }}</p>
                    <small v-if="aiReviewResult.commentary.limitations?.length">
                      {{ aiReviewResult.commentary.limitations.join(" · ") }}
                    </small>
                  </template>
                  <p v-else class="ai-review-muted">
                    {{ aiReviewError || aiReviewHydration.message }}
                  </p>
                </div>
              </aside>
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
              <div
                v-else-if="activeStatView?.id === 'group'"
                class="group-standings"
                data-testid="program-group-standings"
              >
                <template v-if="groupStandingsRows.length">
                  <div class="group-standings-table-wrap">
                    <table class="group-standings-table">
                      <colgroup>
                        <col class="group-standings-col-rank" />
                        <col class="group-standings-col-team" />
                        <col class="group-standings-col-stat" />
                        <col class="group-standings-col-stat" />
                        <col class="group-standings-col-stat" />
                        <col class="group-standings-col-stat" />
                        <col class="group-standings-col-stat" />
                        <col class="group-standings-col-stat" />
                        <col class="group-standings-col-stat" />
                        <col class="group-standings-col-stat" />
                      </colgroup>
                      <thead>
                        <tr>
                          <th>순위</th>
                          <th>팀</th>
                          <th>경기</th>
                          <th>승</th>
                          <th>무</th>
                          <th>패</th>
                          <th>득점</th>
                          <th>실점</th>
                          <th>득실차</th>
                          <th>승점</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr
                          v-for="row in groupStandingsRows"
                          :key="
                            row.teamId ?? `${row.teamCode}-${row.rank}`
                          "
                          :data-team-id="row.teamId"
                        >
                          <td>{{ row.rank }}</td>
                          <td>
                            <span class="group-standings-team-code">{{
                              row.teamCode
                            }}</span>
                          </td>
                          <td>{{ row.played }}</td>
                          <td>{{ row.win }}</td>
                          <td>{{ row.draw }}</td>
                          <td>{{ row.loss }}</td>
                          <td>{{ row.goalsFor }}</td>
                          <td>{{ row.goalsAgainst }}</td>
                          <td>{{ row.goalDiff }}</td>
                          <td>{{ row.points }}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </template>
                <template v-else>
                  <div class="stats-empty" data-testid="program-stats-empty">
                    <span>조 상황 데이터가 없습니다</span>
                  </div>
                </template>
              </div>
              <div v-else class="stats-empty" data-testid="program-stats-empty">
                <span>표시할 스탯이 없습니다</span>
              </div>
            </div>
          </Transition>
          <aside
            class="lineup-control-panel"
            role="tablist"
            aria-label="하단 판넬 버튼"
          >
            <button
              v-for="tab in bottomViewTabs"
              :key="`lineup-control-${tab.id}`"
              type="button"
              class="lineup-control-button"
              :class="{ active: activeBottomView === tab.id }"
              role="tab"
              :aria-selected="activeBottomView === tab.id"
              :data-tab-id="tab.id"
              @click="setBottomView(tab.id)"
            >
              {{ tab.shortLabel }}
            </button>
          </aside>
        </div>
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
  background: #00b140;
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
  grid-template-rows: 75% 25%;
  overflow: hidden;
}

.program-right {
  flex: 0 0 22%;
  min-width: 0;
  height: 100%;
  display: grid;
  grid-template-rows: 75% 25%;
  background: #00b140 !important;
  isolation: isolate;
  position: relative;
}

.feed-surface {
  position: relative;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  background: #00b140;
}

.feed-visual {
  position: absolute;
  inset: 0.72%;
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
  inset: 3.2%;
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
  padding: 0.55rem 0.88rem 0.5rem;
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

.bottom-content-grid {
  position: relative;
  z-index: 2;
  height: 100%;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 0.72rem;
  align-items: stretch;
  overflow: hidden;
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
    opacity 220ms cubic-bezier(0.16, 1, 0.3, 1),
    transform 220ms cubic-bezier(0.16, 1, 0.3, 1);
}

.bottom-view-leave-active {
  position: absolute;
  z-index: 3;
  inset: 0;
  pointer-events: none;
  transition:
    opacity 190ms cubic-bezier(0.32, 0, 0.67, 0),
    transform 190ms cubic-bezier(0.32, 0, 0.67, 0);
}

.bottom-view-leave-from,
.bottom-view-enter-to,
.bottom-view-leave-to {
  position: absolute;
  inset: 0;
}

.bottom-view-enter-from {
  opacity: 0;
  transform: translateX(12px);
}

.bottom-view-leave-to {
  opacity: 0;
  transform: translateX(-12px);
}

.bottom-content-grid[data-transition-direction="prev"] .bottom-view-enter-from {
  transform: translateX(-12px);
}

.bottom-content-grid[data-transition-direction="prev"] .bottom-view-leave-to {
  transform: translateX(12px);
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
  height: 100%;
  min-height: 0;
  position: relative;
  display: block;
  overflow: hidden;
}

.player-panel-state {
  position: absolute;
  inset: 0;
}

.lineup-board-content {
  min-height: 0;
  height: 100%;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 0.85rem;
  align-items: stretch;
}

.lineup-team {
  min-width: 0;
  min-height: 0;
  display: grid;
  grid-template-rows: auto 1fr;
  gap: 0.45rem;
  height: 100%;
  padding: 0.3rem 0.78rem 0.42rem;
  border: 0.08rem solid rgba(245, 241, 232, 0.24);
  background: rgba(245, 241, 232, 0.06);
}

.lineup-team-home {
  grid-column: 1 / 2;
}

.lineup-team-away {
  grid-column: 2 / 3;
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
  grid-template-columns: 1.42rem 2.8ch minmax(0, 1fr) 7.15rem;
  align-items: center;
  gap: 0.34rem;
  padding: 0 0.34rem;
  background: rgba(0, 0, 0, 0.24);
  border-left: 0.16rem solid rgba(245, 241, 232, 0.36);
  overflow: hidden;
  isolation: isolate;
  contain: paint;
}

.lineup-entry--player {
  cursor: pointer;
  padding-right: 0;
}

.lineup-entry--player:hover {
  background: rgba(255, 255, 255, 0.12);
}

.lineup-entry--player:focus-visible {
  outline: 0.08rem solid rgba(201, 151, 43, 0.92);
  outline-offset: 0.04rem;
}

.lineup-player--sub-in,
.lineup-entry[data-sub-in="true"] {
  border-left-color: #c9972b;
  background: rgba(201, 151, 43, 0.16);
}

.lineup-player--sent-off {
  border-left-color: rgba(255, 0, 60, 0.58);
  background:
    linear-gradient(90deg, rgba(70, 0, 14, 0.52), rgba(0, 0, 0, 0.28)),
    rgba(0, 0, 0, 0.2);
}

.lineup-player--sent-off:hover {
  background: rgba(70, 0, 14, 0.28);
}

.lineup-player--sent-off .lineup-entry-icon,
.lineup-player--sent-off > b,
.lineup-player--sent-off .lineup-entry-rating,
.lineup-player--sent-off .lineup-entry-goal {
  opacity: 0.46;
  filter: grayscale(0.8) saturate(0.6);
}

.lineup-player--sent-off > strong {
  color: #ffffff;
  font-weight: 900;
  opacity: 1;
  text-shadow: 0 0.08rem 0.18rem rgba(0, 0, 0, 0.78);
}

.lineup-player--sent-off .lineup-entry-card {
  min-width: 1.8rem;
  border-color: rgba(255, 214, 221, 0.92);
  background: rgba(255, 0, 60, 0.5);
  color: #ffffff;
  font-weight: 950;
  opacity: 1;
  box-shadow: 0 0 0.38rem rgba(255, 0, 60, 0.42);
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
  font-weight: 650;
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.lineup-entry--coach b {
  font-size: clamp(0.62rem, 0.68vw, 0.82rem);
  font-weight: 650;
  white-space: nowrap;
}

.lineup-entry strong {
  position: relative;
  z-index: 1;
  min-width: 0;
  overflow: hidden;
  color: #ffffff;
  font-size: clamp(0.78rem, 0.88vw, 1.08rem);
  font-weight: 700;
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

.lineup-entry-rating {
  justify-self: end;
  min-width: 2.05rem;
  max-width: 2.9rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 0.92rem;
  line-height: 1;
  border-radius: 0.34rem;
  font-weight: 700;
  letter-spacing: 0;
  border: 0.08rem solid transparent;
  box-shadow:
    0 0.12rem 0.32rem rgba(0, 0, 0, 0.35),
    inset 0 0 0 0.06rem rgba(255, 255, 255, 0.2);
  transform: translateY(-0.02rem);
}

.lineup-player-rating-text {
  box-sizing: border-box;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 0;
  min-height: 0;
  padding: 0 0.34rem;
  font-size: clamp(1.24rem, 1.9vw, 1.72rem);
  line-height: 1;
  font-weight: 900;
  letter-spacing: 0;
  border: 0.08rem solid rgba(245, 241, 232, 0.22);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.14), rgba(255, 255, 255, 0)),
    rgba(5, 5, 5, 0.72);
  box-shadow:
    inset 0 0 0 0.08rem rgba(255, 255, 255, 0.08),
    0 0.24rem 0.7rem rgba(0, 0, 0, 0.38);
  font-variant-numeric: tabular-nums;
  overflow: hidden;
}

.lineup-player-rating-text--rating-low {
  color: #ffd0d7;
}

.lineup-player-rating-text--rating-high {
  color: #d8ecff;
}

.lineup-player-rating-text--rating-mid {
  color: #f6e1a8;
}

.lineup-player-rating-text--rating-neutral {
  color: #f2f2f2;
}

.lineup-entry-rating--rating-low {
  background: rgba(200, 16, 46, 0.34);
  color: #ffd0d7;
  border-color: rgba(255, 208, 215, 0.88);
}

.lineup-entry-rating--rating-high {
  background: rgba(0, 132, 255, 0.34);
  color: #d8ecff;
  border-color: rgba(216, 236, 255, 0.9);
}

.lineup-entry-rating--rating-mid {
  background: rgba(255, 241, 232, 0.36);
  color: #f6e1a8;
  border-color: rgba(246, 225, 168, 0.84);
}

.lineup-entry-rating--rating-neutral {
  background: rgba(255, 255, 255, 0.32);
  color: #f2f2f2;
  border-color: rgba(255, 255, 255, 0.82);
}

.lineup-entry-meta {
  justify-self: end;
  width: 100%;
  max-width: 7.15rem;
  display: grid;
  grid-template-columns: 2.2rem 2.2rem 1.75rem;
  align-items: center;
  flex-wrap: nowrap;
  gap: 0.18rem;
  justify-items: center;
}

.lineup-entry-meta-cell {
  min-width: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.lineup-entry-card-cell {
  justify-content: center;
}

.lineup-entry-goal-cell {
  justify-content: center;
}

.lineup-entry-rating-cell {
  justify-content: center;
}

.lineup-entry-meta-empty {
  visibility: hidden;
  display: inline-flex;
  width: 100%;
  justify-content: center;
  align-items: center;
}

.lineup-entry-card {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 1.55rem;
  border-radius: 0.34rem;
  border: 0.08rem solid rgba(255, 214, 74, 0.86);
  background: rgba(255, 214, 74, 0.24);
  color: #fff3a3;
  font-size: 0.58rem;
  font-weight: 650;
  letter-spacing: 0;
}

.lineup-entry-card[data-card="RED"] {
  border-color: rgba(255, 0, 60, 0.78);
  background: rgba(255, 0, 60, 0.16);
  color: #ffd6dd;
}

.lineup-entry-goal {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 1.5rem;
  height: 1.18rem;
  gap: 0.08rem;
  border-radius: 0.34rem;
  border: 0.08rem solid rgba(245, 241, 232, 0.86);
  background:
    linear-gradient(135deg, rgba(245, 241, 232, 0.32), rgba(201, 151, 43, 0.18)),
    rgba(5, 5, 5, 0.34);
  color: #ffffff;
  font-size: 0.58rem;
  font-weight: 650;
  letter-spacing: 0;
}

.lineup-entry-goal img {
  width: 0.72rem;
  height: 0.72rem;
  object-fit: contain;
}

.lineup-entry-goal b {
  font-size: 0.58rem;
  line-height: 1;
  color: #ffffff;
}

.lineup-control-panel {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  align-self: stretch;
  justify-content: stretch;
  height: 100%;
  width: max-content;
  min-width: max-content;
  max-width: max-content;
  padding: 0.26rem 0;
  padding-inline: 0;
  overflow: hidden;
  align-items: stretch;
  flex: 0 0 auto;
}

.lineup-control-button {
  appearance: none;
  border: 0.08rem solid rgba(246, 225, 168, 0.58);
  min-height: 0;
  padding: 0.34rem 0.24rem;
  width: 100%;
  height: auto;
  flex: 1 1 0;
  background: rgba(5, 5, 5, 0.74);
  color: #f6e1a8;
  border-radius: 0.42rem;
  font-size: 0.74rem;
  font-weight: 900;
  white-space: nowrap;
  line-height: 1;
  cursor: pointer;
  transition:
    background-color 150ms ease,
    border-color 150ms ease,
    color 150ms ease;
}

.lineup-control-button:hover,
.lineup-control-button:focus-visible {
  border-color: #f6e1a8;
  background: rgba(201, 151, 43, 0.36);
  color: #ffffff;
}

.lineup-control-button.active {
  color: #ffffff;
  border-color: #f5f1e8;
  background: linear-gradient(
    180deg,
    rgba(201, 151, 43, 0.34),
    rgba(5, 5, 5, 0.86)
  );
}

.player-detail-panel {
  grid-column: 1 / -1;
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
  background: linear-gradient(
    90deg,
    #050505 0%,
    #111111 34%,
    #051b41 74%,
    #030915 100%
  );
  border: 0.08rem solid rgba(201, 151, 43, 0.5);
  padding: 0.7rem 0.86rem;
  display: grid;
  grid-template-rows: minmax(0, 1fr);
  z-index: 3;
  box-shadow:
    inset 0 0 0 0.08rem rgba(255, 255, 255, 0.06),
    0 0.3rem 1rem rgba(0, 0, 0, 0.55);
}

.player-detail-header {
  position: absolute;
  top: 0.5rem;
  right: 0.58rem;
  z-index: 6;
  display: flex;
  justify-content: flex-end;
}

.player-detail-content {
  min-width: 0;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(20rem, 0.88fr) minmax(0, 2.12fr);
  gap: 0.72rem;
  align-items: stretch;
  overflow: hidden;
}

.player-detail-profile {
  position: relative;
  min-width: 0;
  min-height: 0;
  display: grid;
  overflow: hidden;
  background:
    linear-gradient(135deg, rgba(245, 241, 232, 0.12), rgba(5, 5, 5, 0)),
    rgba(5, 5, 5, 0.36);
  border: 0.08rem solid rgba(245, 241, 232, 0.2);
  padding: 0.52rem;
  isolation: isolate;
}

.player-detail-profile::before {
  content: "";
  position: absolute;
  inset: 0;
  z-index: -1;
  background:
    linear-gradient(90deg, rgba(201, 151, 43, 0.16), transparent 38%),
    repeating-linear-gradient(
      135deg,
      rgba(255, 255, 255, 0.08) 0 0.08rem,
      transparent 0.08rem 0.56rem
    );
  opacity: 0.48;
}

.player-detail-photo-wrap {
  grid-area: photo;
  position: relative;
  box-sizing: border-box;
  place-self: stretch;
  width: 8.25rem;
  height: 100%;
  min-height: 0;
  max-height: 100%;
  border-radius: 0.2rem;
  border: 0.08rem solid rgba(246, 225, 168, 0.62);
  overflow: hidden;
  background:
    radial-gradient(circle at 50% 28%, rgba(246, 225, 168, 0.18), transparent 40%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.08), rgba(0, 0, 0, 0.32)),
    rgba(0, 0, 0, 0.34);
  flex: 0 0 auto;
  box-shadow:
    inset 0 0 0 0.08rem rgba(255, 255, 255, 0.08),
    0 0.28rem 0.85rem rgba(0, 0, 0, 0.42);
}

.player-detail-photo-wrap::after {
  content: "";
  position: absolute;
  inset: auto 0 0;
  height: 38%;
  background: linear-gradient(180deg, transparent, rgba(5, 5, 5, 0.68));
  pointer-events: none;
}

.player-detail-media {
  min-width: 0;
  min-height: 0;
  display: grid;
  grid-template-columns: 8.25rem minmax(0, 1fr);
  grid-template-rows: minmax(0, 1fr);
  grid-template-areas:
    "identity meta";
  gap: 0.62rem;
  align-items: stretch;
  height: 100%;
}

.player-detail-identity {
  grid-area: identity;
  position: relative;
  min-width: 0;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  grid-template-rows: minmax(0, 1fr);
  grid-template-areas:
    "photo";
  align-items: stretch;
  overflow: hidden;
}

.player-detail-identity > .lineup-player-rating-text {
  position: absolute;
  right: 0.34rem;
  bottom: 0.34rem;
  z-index: 3;
  width: auto;
  min-width: 3.6rem;
  height: 2.46rem;
}

.player-detail-number-plate {
  position: absolute;
  left: 0.34rem;
  top: 0.34rem;
  z-index: 3;
  min-width: 3.05rem;
  height: 2.35rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 0.08rem solid rgba(201, 151, 43, 0.78);
  background:
    linear-gradient(180deg, rgba(201, 151, 43, 0.22), rgba(5, 5, 5, 0.84)),
    rgba(201, 151, 43, 0.16);
  color: #f6e1a8;
  font-size: 1.72rem;
  font-weight: 950;
  line-height: 1;
  font-variant-numeric: tabular-nums;
  box-shadow:
    inset 0 0 0 0.08rem rgba(255, 255, 255, 0.12),
    0 0.24rem 0.7rem rgba(0, 0, 0, 0.34);
}

.player-detail-name-block {
  grid-area: meta;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 0.34rem;
  padding: 0.2rem 0.2rem 0.16rem 0;
}

.player-detail-photo {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center 18%;
  filter: saturate(1.04) contrast(1.04);
}

.player-detail-photo-empty {
  width: 100%;
  height: 100%;
  display: grid;
  place-items: center;
  color: #f6e1a8;
  font-size: clamp(3rem, 5vw, 5.4rem);
  font-weight: 950;
  line-height: 1;
  font-variant-numeric: tabular-nums;
}

.player-detail-fullname {
  margin: 0;
  color: rgba(245, 241, 232, 0.76);
  font-size: clamp(0.78rem, 1vw, 1.08rem);
  font-weight: 700;
  line-height: 1.08;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.player-detail-shortname {
  margin: 0;
  color: #ffffff;
  font-size: clamp(1.28rem, 2vw, 2.24rem);
  font-weight: 950;
  line-height: 1.02;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.player-detail-team {
  margin: 0;
  width: fit-content;
  min-width: 4.2rem;
  padding: 0.18rem 0.5rem;
  border: 0.08rem solid rgba(201, 151, 43, 0.58);
  background: rgba(201, 151, 43, 0.16);
  color: #f6e1a8;
  font-size: 0.82rem;
  font-weight: 950;
  line-height: 1;
  text-align: center;
}

.player-detail-stats {
  min-width: 0;
  min-height: 0;
  padding-right: 2.95rem;
  box-sizing: border-box;
}

.player-detail-stats dl {
  margin: 0;
  height: 100%;
  min-height: 0;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  grid-template-rows: repeat(2, minmax(0, 1fr));
  gap: 0.34rem;
}

.player-detail-stats dt,
.player-detail-stats dd {
  margin: 0;
}

.player-detail-stats dt {
  color: #f6e1a8;
  font-size: 0.94rem;
  font-weight: 850;
  letter-spacing: 0;
  line-height: 1.15;
}

.player-detail-stats dd {
  color: #ffffff;
  font-size: clamp(1.58rem, 2.35vw, 2.25rem);
  font-weight: 950;
  line-height: 1;
  white-space: nowrap;
}

.player-detail-stats > dl > div {
  min-width: 0;
  padding: 0.46rem 0.58rem;
  background:
    linear-gradient(180deg, rgba(245, 241, 232, 0.1), rgba(245, 241, 232, 0.04)),
    rgba(5, 5, 5, 0.26);
  border: 0.08rem solid rgba(245, 241, 232, 0.18);
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-content: center;
  align-items: center;
  gap: 0.08rem 0.48rem;
  overflow: hidden;
}

.player-detail-close {
  position: relative;
  width: 2.25rem;
  height: 2.25rem;
  border: 0.08rem solid rgba(245, 241, 232, 0.45);
  background: rgba(5, 5, 5, 0.72);
  color: #f5f1e8;
  border-radius: 50%;
  padding: 0;
  font-size: 0;
  font-weight: 900;
  cursor: pointer;
}

.player-detail-close::before,
.player-detail-close::after {
  content: "";
  position: absolute;
  top: 50%;
  left: 50%;
  width: 1rem;
  height: 0.1rem;
  background: currentColor;
  transform-origin: center;
}

.player-detail-close::before {
  transform: translate(-50%, -50%) rotate(45deg);
}

.player-detail-close::after {
  transform: translate(-50%, -50%) rotate(-45deg);
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
  height: 100%;
  min-height: 0;
  grid-template-columns: 18rem 1fr;
  align-items: stretch;
  gap: 1rem;
  position: relative;
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

.stats-action-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.76rem;
}

.momentum-open-button,
.ai-review-open-button {
  width: fit-content;
  border: 0.08rem solid rgba(201, 151, 43, 0.7);
  background:
    linear-gradient(145deg, rgba(201, 151, 43, 0.28), rgba(5, 5, 5, 0.72)),
    #050505;
  color: #f6e1a8;
  padding: 0.44rem 0.78rem;
  font-size: 0.78rem;
  font-weight: 950;
  cursor: pointer;
  letter-spacing: 0;
}

.momentum-open-button--active,
.momentum-open-button:hover,
.momentum-open-button:focus-visible,
.ai-review-open-button--active,
.ai-review-open-button:hover:not(:disabled),
.ai-review-open-button:focus-visible:not(:disabled) {
  background: #c9972b;
  color: #050505;
}

.ai-review-open-button:disabled {
  border-color: #4e493d;
  background: #111111;
  color: #736b5b;
  cursor: not-allowed;
}

.momentum-panel {
  position: absolute;
  z-index: 100;
  inset: 0.2rem 0.2rem 0.2rem 19rem;
  padding: 1rem;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 0.76rem;
  border: 0.1rem solid #c9972b;
  background-color: #050505;
  background-image: none;
  box-shadow: 0 1rem 2.4rem #000000;
  isolation: isolate;
  overflow: hidden;
}

.momentum-panel::before {
  content: "";
  position: absolute;
  inset: 0;
  z-index: 0;
  background-color: #050505;
  background-image: none;
}

.momentum-panel > * {
  position: relative;
  z-index: 1;
}

.momentum-panel header {
  display: grid;
  grid-template-columns: auto minmax(0, auto) minmax(14rem, 1fr) auto;
  align-items: center;
  gap: 0.7rem;
}

.momentum-panel header {
  z-index: 6;
}

.momentum-panel header span {
  color: #c9972b;
  font-size: 0.78rem;
  font-weight: 950;
  letter-spacing: 0.08em;
}

.momentum-title-row {
  position: relative;
  z-index: 7;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 0.46rem;
}

.momentum-panel header strong {
  color: #ffffff;
  font-size: 1.42rem;
  font-weight: 950;
  line-height: 1;
}

.momentum-close-button {
  border: 0.08rem solid #f5f1e8;
  background: #050505;
  color: #f5f1e8;
  padding: 0.32rem 0.58rem;
  font-size: 0.68rem;
  font-weight: 950;
  cursor: pointer;
}

.momentum-info-button {
  position: relative;
  z-index: 8;
  width: 1.02rem;
  height: 1.02rem;
  display: inline-grid;
  place-items: center;
  border: 0.08rem solid #c9972b;
  border-radius: 999px;
  background: #050505;
  color: #c9972b;
  font-size: 0.62rem;
  font-weight: 950;
  line-height: 1;
  cursor: help;
}

.momentum-info-popover {
  position: absolute;
  left: 0;
  top: calc(100% + 0.42rem);
  z-index: 20;
  width: min(42rem, calc(100vw - 35rem));
  padding: 0.78rem 0.88rem;
  display: grid;
  gap: 0.34rem;
  border: 0.08rem solid #c9972b;
  background: #050505;
  color: #f5f1e8;
  box-shadow: 0 0.8rem 1.8rem #000000;
  opacity: 0;
  overflow: visible;
  pointer-events: none;
  text-align: left;
  transform: translateY(-0.2rem);
  transition:
    opacity 120ms ease,
    transform 120ms ease;
}

.momentum-info-popover b {
  color: #c9972b;
  font-size: 0.72rem;
  font-style: normal;
  letter-spacing: 0.08em;
}

.momentum-info-popover em,
.momentum-info-popover small {
  color: #f5f1e8;
  font-size: 0.66rem;
  font-style: normal;
  font-weight: 850;
  line-height: 1.42;
}

.momentum-info-popover small {
  color: #cfc8b7;
}

.momentum-info-button:hover .momentum-info-popover,
.momentum-info-button:focus-visible .momentum-info-popover {
  opacity: 1;
  transform: translateY(0);
}

.momentum-panel-chart {
  position: relative;
  z-index: 1;
  min-width: 0;
  min-height: 0;
  padding: 0.5rem;
  border: 0.08rem solid #51452d;
  background-color: #0b0b0b;
  background-image: none;
  opacity: 1;
}

.momentum-score {
  min-width: 5.8rem;
  padding: 0.28rem 0.52rem;
  display: inline-flex;
  align-items: baseline;
  gap: 0.34rem;
  border: 0.08rem solid currentColor;
  background: #050505;
  line-height: 1;
}

.momentum-score span {
  font-size: 0.78rem;
  font-weight: 950;
}

.momentum-score strong {
  font-size: 1.18rem;
  font-weight: 950;
}

.momentum-score--home {
  justify-content: flex-start;
  color: #d8a21f;
  box-shadow: inset 0 0 0 0.08rem rgba(216, 162, 31, 0.18);
}

.momentum-score--away {
  justify-content: flex-end;
  color: #58a6ff;
  box-shadow: inset 0 0 0 0.08rem rgba(88, 166, 255, 0.18);
}

.momentum-summary-row {
  min-width: 0;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 0.52rem;
  color: #f5f1e8;
  font-weight: 950;
}

.momentum-summary-row small {
  min-width: 0;
  overflow: hidden;
  color: #c9bfa9;
  font-size: 0.78rem;
  text-align: center;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.momentum-empty-message {
  position: relative;
  z-index: 1;
  min-height: 4.5rem;
  display: grid;
  place-items: center;
  padding: 0.8rem 1rem;
  border: 0.08rem solid #51452d;
  background: #0b0b0b;
  color: #d8d1c2;
  font-size: 0.86rem;
  font-weight: 900;
  line-height: 1.35;
  text-align: center;
}

.momentum-panel--unavailable {
  opacity: 0.84;
}

.ai-review-panel {
  position: absolute;
  z-index: 110;
  inset: 0.2rem 0.2rem 0.2rem 19rem;
  padding: 1rem;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 0.76rem;
  border: 0.1rem solid #58a6ff;
  background: #050505;
  box-shadow: 0 1rem 2.4rem #000000;
  overflow: hidden;
}

.ai-review-panel header {
  min-width: 0;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 0.4rem 0.8rem;
  align-items: start;
}

.ai-review-panel header span {
  grid-column: 1 / span 2;
  color: #58a6ff;
  font-size: 0.72rem;
  font-weight: 950;
}

.ai-review-panel header strong {
  min-width: 0;
  grid-column: 2;
  color: #ffffff;
  font-size: 1.1rem;
  font-weight: 950;
  line-height: 1.15;
}

.ai-review-spinner {
  grid-column: 1;
  grid-row: 2;
  width: 0.9rem;
  height: 0.9rem;
  margin-top: 0.08rem;
  border: 0.12rem solid rgba(88, 166, 255, 0.22);
  border-top-color: #58a6ff;
  border-radius: 999px;
  animation: ai-review-spin 0.72s linear infinite;
}

@keyframes ai-review-spin {
  to {
    transform: rotate(360deg);
  }
}

.ai-review-basis {
  min-width: 0;
  grid-column: 2;
  color: #9fbedc;
  font-size: 0.72rem;
  font-weight: 850;
  line-height: 1.2;
}

.ai-review-header-actions {
  grid-column: 3;
  grid-row: 1 / span 3;
  display: flex;
  align-items: flex-start;
  gap: 0.4rem;
}

.ai-review-refresh-button {
  border: 0.08rem solid #58a6ff;
  background: #07131f;
  color: #d8ebff;
  padding: 0.32rem 0.58rem;
  font-size: 0.68rem;
  font-weight: 950;
  cursor: pointer;
}

.ai-review-refresh-button:hover:not(:disabled),
.ai-review-refresh-button:focus-visible:not(:disabled) {
  background: #58a6ff;
  color: #050505;
}

.ai-review-refresh-button:disabled {
  border-color: #334253;
  background: #111111;
  color: #667386;
  cursor: not-allowed;
}

.ai-review-body {
  min-height: 0;
  padding: 0.9rem;
  border: 0.08rem solid #324963;
  background: #0b0b0b;
  color: #f3efe5;
  overflow: auto;
}

.ai-review-body strong {
  display: block;
  color: #f6e1a8;
  font-size: 0.98rem;
  line-height: 1.35;
}

.ai-review-body p {
  margin: 0.72rem 0 0;
  font-size: 0.9rem;
  font-weight: 800;
  line-height: 1.55;
}

.ai-review-body small {
  display: block;
  margin-top: 0.72rem;
  color: #9f9889;
  font-size: 0.72rem;
  line-height: 1.35;
}

.ai-review-muted {
  color: #c9bfa9;
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

.group-standings {
  min-height: 0;
  min-width: 0;
  display: grid;
  gap: 0.54rem;
  align-items: center;
  align-content: center;
}

.group-standings-table-wrap {
  min-width: 0;
  min-height: 0;
  max-height: 100%;
  overflow: hidden;
}

.group-standings-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0 0.24rem;
  color: #ffffff;
  font-size: 1rem;
  table-layout: fixed;
}

.group-standings-col-rank {
  width: 14%;
}

.group-standings-col-team {
  width: 22%;
}

.group-standings-col-stat {
  width: 8%;
}

.group-standings-table thead th {
  text-align: left;
  color: #c9972b;
  font-size: 0.92rem;
  font-weight: 950;
  padding: 0 0.42rem 0.3rem;
}

.group-standings-table th:nth-child(n + 3),
.group-standings-table td:nth-child(n + 3) {
  text-align: center;
}

.group-standings-table tbody td {
  padding: 0.38rem 0.42rem;
  background: rgba(245, 241, 232, 0.08);
  color: #f6e1a8;
  font-weight: 950;
  border-top: 0.08rem solid rgba(0, 0, 0, 0.15);
  line-height: 1.2;
}

.group-standings-table tbody tr td:first-child {
  border-top-left-radius: 0.34rem;
  border-bottom-left-radius: 0.34rem;
}

.group-standings-table tbody tr td:last-child {
  border-top-right-radius: 0.34rem;
  border-bottom-right-radius: 0.34rem;
}

.group-standings-table tbody td:first-child {
  color: #ffffff;
}

.group-standings-team-code {
  display: block;
  color: #c9972b;
  font-size: 0.88rem;
  font-weight: 950;
  margin-bottom: 0.02rem;
}

.group-standings-team-name {
  display: block;
  color: #f6e1a8;
  font-size: 0.96rem;
  font-weight: 950;
  line-height: 1.05;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
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
  background: #00b140 !important;
}

.character-slot {
  height: 100%;
  min-height: 0;
  background: #00b140 !important;
}
</style>
