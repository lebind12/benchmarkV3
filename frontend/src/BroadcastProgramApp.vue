<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import eventGoalSplashUrl from "@/assets/generated/broadcast-events/event-goal-wide.png?url";
import eventOwnGoalSplashUrl from "@/assets/generated/broadcast-events/event-own-goal-wide.png?url";
import eventRedCardSplashUrl from "@/assets/generated/broadcast-events/event-red-card-wide.png?url";
import eventSubstitutionSplashUrl from "@/assets/generated/broadcast-events/event-substitution-wide.png?url";
import eventVarSplashUrl from "@/assets/generated/broadcast-events/event-var-wide.png?url";
import eventYellowCardSplashUrl from "@/assets/generated/broadcast-events/event-yellow-card-wide.png?url";
import matchStatsIntroUrl from "@/assets/generated/broadcast-program/match-stats-intro.png?url";
import brazilFlagUrl from "@/assets/broadcast/flags/br.svg?url";
import koreaFlagUrl from "@/assets/broadcast/flags/kr.svg?url";
import worldCupKickoffBannerUrl from "@/assets/generated/broadcast-program/worldcup-kickoff-2026-banner5.png?url";
import PossessionPieChart from "@/components/broadcast/PossessionPieChart.vue";
import {
  API_FOOTBALL_LIVE_POLL_MS,
  fetchApiFootballBroadcastSnapshot,
  fetchApiFootballFirstLiveFixture,
  shouldUseApiFootballLive,
  type ApiFootballBroadcastEvent,
  type ApiFootballBroadcastLineupPlayer,
  type ApiFootballBroadcastSnapshot,
  type ApiFootballBroadcastStat,
} from "@/lib/api/apiFootballLive";
import { readBroadcastFixtureId } from "@/lib/broadcastQuery";

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

type ProgramEventType =
  | "goal"
  | "own-goal"
  | "card"
  | "var"
  | "substitution";

type EventSplashType =
  | "goal"
  | "own-goal"
  | "substitution"
  | "yellow-card"
  | "red-card"
  | "var";

type StatMetric = {
  id: string;
  label: string;
  home: string;
  away: string;
  homePct: number;
  awayPct: number;
};

type TopRatedPlayer = {
  name: string;
  teamCode: string;
  no: number;
  rating: string;
  photoUrl?: string;
};

type InfoCard = {
  id: string;
  kind:
    | "banner"
    | "image-banner"
    | "event-splash"
    | "possession-stat"
    | "metric-group"
    | "player-rating"
    | "stat"
    | "event"
    | "player"
    | "tactic";
  eyebrow: string;
  title: string;
  detail: string;
  leftValue?: string;
  rightValue?: string;
  label?: string;
  imageUrl?: string;
  eventType?: ProgramEventType;
  eventSplashType?: EventSplashType;
  eventPlayerName?: string;
  eventPlayerNumber?: number;
  eventPlayerImageUrl?: string;
  eventTeamLogoUrl?: string;
  substitutionOutName?: string;
  substitutionOutNumber?: number;
  substitutionOutImageUrl?: string;
  substitutionInName?: string;
  substitutionInNumber?: number;
  substitutionInImageUrl?: string;
  homeCode?: string;
  awayCode?: string;
  homePct?: number;
  awayPct?: number;
  metrics?: StatMetric[];
  metricTheme?: "attack" | "discipline";
  playerName?: string;
  playerTeamCode?: string;
  playerNumber?: number;
  playerRating?: string;
  playerImageUrl?: string;
};

type EventInfoCard = InfoCard & {
  kind: "event";
  eventType: ProgramEventType;
  eventSplashType: EventSplashType;
  sequence: number;
};

type EventSplashCard = InfoCard & {
  kind: "event-splash";
  eventType: ProgramEventType;
  eventSplashType: EventSplashType;
  imageUrl: string;
  sequence: number;
};

type EventDisplayCard = EventInfoCard | EventSplashCard;

type CarouselInfoCard = InfoCard & {
  carouselKey: string;
  isClone: boolean;
};

type ProgramMatch = {
  fixtureId: number;
  home: string;
  away: string;
  homeCode: string;
  awayCode: string;
  score: string;
  clock: string;
  status: string;
  baseInfoCards: InfoCard[];
  eventCards: EventInfoCard[];
};

const CAROUSEL_INTERVAL_MS = 7000;
const LATEST_EVENT_INSERT_INDEX = 1;
const POSSESSION_ANIMATION_MS = 900;
const PLAYER_RATING_ANIMATION_MS = 900;
const eventSplashImageUrls: Record<EventSplashType, string> = {
  goal: eventGoalSplashUrl,
  "own-goal": eventOwnGoalSplashUrl,
  substitution: eventSubstitutionSplashUrl,
  "yellow-card": eventYellowCardSplashUrl,
  "red-card": eventRedCardSplashUrl,
  var: eventVarSplashUrl,
};

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

function isEventInfoCard(card: InfoCard): card is EventInfoCard {
  return card.kind === "event";
}

function isEventDisplayCard(card: InfoCard): card is EventDisplayCard {
  return isEventInfoCard(card) || card.kind === "event-splash";
}

function sortEventCards(eventCards: EventInfoCard[]) {
  return [...eventCards].sort((a, b) => a.sequence - b.sequence);
}

function insertEventCardsAfterCurrent(
  queue: InfoCard[],
  eventCards: EventDisplayCard[],
): InfoCard[] {
  if (eventCards.length === 0) {
    return queue;
  }

  const incomingIds = new Set(eventCards.map((card) => card.id));
  const queueWithoutDuplicates = queue.filter(
    (card) => !incomingIds.has(card.id),
  );
  const insertIndex = Math.min(
    LATEST_EVENT_INSERT_INDEX,
    queueWithoutDuplicates.length,
  );

  return [
    ...queueWithoutDuplicates.slice(0, insertIndex),
    ...eventCards,
    ...queueWithoutDuplicates.slice(insertIndex),
  ];
}

const searchParams = new URLSearchParams(
  typeof window === "undefined" ? "" : window.location.search,
);
const requestedFixtureId = readBroadcastFixtureId(searchParams);
const requestedLeague = searchParams.get("league") as LeagueSlug | null;
const demoEventsMode = searchParams.get("demoEvents") === "all";
const selectedLeague =
  requestedLeague && Object.hasOwn(themes, requestedLeague)
    ? requestedLeague
    : "world-cup-2026";

const activeCardIndex = ref(0);
const carouselTransitionEnabled = ref(true);
const baseInfoCards = ref<InfoCard[]>([]);
const carouselQueue = ref<InfoCard[]>([]);
const previousEventCards = ref<EventInfoCard[]>([]);
const animatedPossession = ref({
  cardId: "",
  homePct: 0,
  awayPct: 0,
});
const animatedPlayerRating = ref({
  cardId: "",
  value: 0,
});
const liveStatus = ref<"loading" | "ready" | "error">("loading");
const liveError = ref<string | null>(null);
let carouselTimer: number | undefined;
let livePollingTimer: number | undefined;
let activeFixtureId: number | null = null;
let pendingBaseInfoCards: InfoCard[] | null = null;
let pendingEventCards: EventDisplayCard[] = [];
let possessionAnimationFrame: number | undefined;
let playerRatingAnimationFrame: number | undefined;
const seenEventIds = new Set<string>();

const theme = computed(() => themes[selectedLeague]);
const liveStateLabel = computed(() => {
  if (liveStatus.value === "loading")
    return "API-Football 라이브 데이터 로딩 중";
  if (liveStatus.value === "error")
    return liveError.value ?? "API-Football 라이브 데이터 사용 불가";
  return "API-Football 라이브 데이터";
});
const isAdminAllowed = ref(
  typeof localStorage !== "undefined" && localStorage.getItem("mockRole") === "ADMIN",
);
const carouselCards = computed<CarouselInfoCard[]>(() => {
  const cards = carouselQueue.value;
  const realCards = cards.map((card, index) => ({
    ...card,
    carouselKey: `real-${index}-${card.id}`,
    isClone: false,
  }));

  if (realCards.length <= 1) {
    return realCards;
  }

  return [
    ...realCards,
    {
      ...cards[0],
      carouselKey: `clone-${cards[0].id}`,
      isClone: true,
    },
  ];
});
const activeVisibleCard = computed(
  () => carouselQueue.value[activeCardIndex.value],
);
const activeVisibleCardKind = computed(
  () => activeVisibleCard.value?.kind ?? "empty",
);
const possessionHomeColor = computed(() =>
  selectedLeague === "world-cup-2026" ? "#1677FF" : theme.value.accentAlt,
);
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
  "--program-possession-home": possessionHomeColor.value,
  "--program-dark": theme.value.dark,
}));
const infoTrackStyle = computed<Record<string, string>>(() => {
  const style = {
    transform: `translateY(-${activeCardIndex.value * 100}%)`,
  };

  if (!carouselTransitionEnabled.value || demoEventsMode) {
    return {
      ...style,
      transition: "none",
    };
  }

  return style;
});

function handleInfoTrackTransitionEnd(event: TransitionEvent) {
  if (event.propertyName !== "transform") {
    return;
  }

  if (activeCardIndex.value !== 1 || carouselQueue.value.length <= 1) {
    return;
  }

  const finishedCard = carouselQueue.value[0];
  const remainingCards = carouselQueue.value.slice(1);
  carouselTransitionEnabled.value = false;
  if (!demoEventsMode && isEventDisplayCard(finishedCard)) {
    carouselQueue.value =
      remainingCards.length > 0 ? remainingCards : [...baseInfoCards.value];
  } else {
    carouselQueue.value = [...remainingCards, finishedCard];
  }
  activeCardIndex.value = 0;
  applyDeferredCarouselUpdates();

  window.requestAnimationFrame(() => {
    window.requestAnimationFrame(() => {
      carouselTransitionEnabled.value = true;
    });
  });
}

function manualNextBanner() {
  if (!demoEventsMode || carouselQueue.value.length <= 1) {
    return;
  }

  carouselQueue.value = [
    ...carouselQueue.value.slice(1),
    carouselQueue.value[0],
  ];
  activeCardIndex.value = 0;
}

function manualPreviousBanner() {
  if (!demoEventsMode || carouselQueue.value.length <= 1) {
    return;
  }

  const previousCard = carouselQueue.value.at(-1);
  if (!previousCard) {
    return;
  }

  carouselQueue.value = [
    previousCard,
    ...carouselQueue.value.slice(0, carouselQueue.value.length - 1),
  ];
  activeCardIndex.value = 0;
}

function handleDemoKeyboard(event: KeyboardEvent) {
  if (!demoEventsMode) {
    return;
  }

  const key = event.key.toLowerCase();

  if (key === "k") {
    event.preventDefault();
    manualNextBanner();
    return;
  }

  if (key === "i") {
    event.preventDefault();
    manualPreviousBanner();
  }
}

onMounted(() => {
  if (!isAdminAllowed.value) return;

  if (demoEventsMode) {
    loadDemoEventQueue();
    window.addEventListener("keydown", handleDemoKeyboard);
  } else {
    void refreshApiFootballLive();
  }

  if (!demoEventsMode && shouldUseApiFootballLive()) {
    livePollingTimer = window.setInterval(() => {
      void refreshApiFootballLive();
    }, API_FOOTBALL_LIVE_POLL_MS);
  }

  if (!demoEventsMode) {
    carouselTimer = window.setInterval(() => {
      if (carouselQueue.value.length <= 1 || activeCardIndex.value !== 0) {
        return;
      }

      activeCardIndex.value = 1;
    }, CAROUSEL_INTERVAL_MS);
  }
});

onBeforeUnmount(() => {
  if (demoEventsMode) {
    window.removeEventListener("keydown", handleDemoKeyboard);
  }
  if (carouselTimer !== undefined) {
    window.clearInterval(carouselTimer);
  }
  if (livePollingTimer !== undefined) {
    window.clearInterval(livePollingTimer);
  }
  cancelPossessionAnimation();
  cancelPlayerRatingAnimation();
});

watch(
  () => activeVisibleCard.value,
  (card) => {
    if (card?.kind === "possession-stat") {
      cancelPlayerRatingAnimation();
      animatedPlayerRating.value = {
        cardId: "",
        value: 0,
      };
      startPossessionAnimation(card);
      return;
    }

    cancelPossessionAnimation();
    animatedPossession.value = {
      cardId: "",
      homePct: 0,
      awayPct: 0,
    };

    if (card?.kind === "player-rating") {
      startPlayerRatingAnimation(card);
      return;
    }

    cancelPlayerRatingAnimation();
    animatedPlayerRating.value = {
      cardId: "",
      value: 0,
    };
  },
);

function clampPct(value: number | undefined) {
  if (value === undefined || !Number.isFinite(value)) {
    return 0;
  }

  return Math.max(0, Math.min(100, value));
}

function possessionValue(card: InfoCard, side: "home" | "away") {
  const target = side === "home" ? card.homePct : card.awayPct;
  if (animatedPossession.value.cardId !== card.id) {
    return clampPct(target);
  }

  return side === "home"
    ? animatedPossession.value.homePct
    : animatedPossession.value.awayPct;
}

function possessionPercentLabel(card: InfoCard, side: "home" | "away") {
  return `${Math.round(possessionValue(card, side))}%`;
}

function cancelPossessionAnimation() {
  if (possessionAnimationFrame !== undefined) {
    window.cancelAnimationFrame(possessionAnimationFrame);
    possessionAnimationFrame = undefined;
  }
}

function startPossessionAnimation(card: InfoCard) {
  cancelPossessionAnimation();
  const homeTarget = clampPct(card.homePct);
  const awayTarget = clampPct(card.awayPct);
  const startedAt = window.performance.now();

  animatedPossession.value = {
    cardId: card.id,
    homePct: 0,
    awayPct: 0,
  };

  const tick = (now: number) => {
    const progress = Math.min(
      1,
      (now - startedAt) / POSSESSION_ANIMATION_MS,
    );
    const easedProgress = 1 - (1 - progress) ** 3;

    animatedPossession.value = {
      cardId: card.id,
      homePct: homeTarget * easedProgress,
      awayPct: awayTarget * easedProgress,
    };

    if (progress < 1) {
      possessionAnimationFrame = window.requestAnimationFrame(tick);
      return;
    }

    animatedPossession.value = {
      cardId: card.id,
      homePct: homeTarget,
      awayPct: awayTarget,
    };
    possessionAnimationFrame = undefined;
  };

  possessionAnimationFrame = window.requestAnimationFrame(tick);
}

function playerRatingTarget(card: InfoCard) {
  const parsed = Number.parseFloat(card.playerRating ?? "");
  return Number.isFinite(parsed) ? parsed : 0;
}

function playerRatingLabel(card: InfoCard) {
  if (animatedPlayerRating.value.cardId !== card.id) {
    return playerRatingTarget(card).toFixed(1);
  }

  return animatedPlayerRating.value.value.toFixed(1);
}

function cancelPlayerRatingAnimation() {
  if (playerRatingAnimationFrame !== undefined) {
    window.cancelAnimationFrame(playerRatingAnimationFrame);
    playerRatingAnimationFrame = undefined;
  }
}

function startPlayerRatingAnimation(card: InfoCard) {
  cancelPlayerRatingAnimation();
  const target = playerRatingTarget(card);
  const startedAt = window.performance.now();

  animatedPlayerRating.value = {
    cardId: card.id,
    value: 0,
  };

  const tick = (now: number) => {
    const progress = Math.min(
      1,
      (now - startedAt) / PLAYER_RATING_ANIMATION_MS,
    );
    const easedProgress = 1 - (1 - progress) ** 3;

    animatedPlayerRating.value = {
      cardId: card.id,
      value: target * easedProgress,
    };

    if (progress < 1) {
      playerRatingAnimationFrame = window.requestAnimationFrame(tick);
      return;
    }

    animatedPlayerRating.value = {
      cardId: card.id,
      value: target,
    };
    playerRatingAnimationFrame = undefined;
  };

  playerRatingAnimationFrame = window.requestAnimationFrame(tick);
}

async function refreshApiFootballLive() {
  if (!shouldUseApiFootballLive()) {
    liveStatus.value = "error";
    liveError.value = "API-Football 라이브 모드가 설정되지 않았습니다";
    return;
  }

  try {
    liveStatus.value = carouselQueue.value.length > 0 ? "ready" : "loading";
    liveError.value = null;
    const snapshot =
      requestedFixtureId !== null
        ? await fetchApiFootballBroadcastSnapshot(requestedFixtureId)
        : await fetchApiFootballFirstLiveFixture();
    const liveMatch = createProgramMatchFromSnapshot(snapshot);
    syncCarouselFromLiveMatch(liveMatch);
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

function syncCarouselFromLiveMatch(liveMatch: ProgramMatch) {
  const sortedEventCards = sortEventCards(liveMatch.eventCards);

  if (activeFixtureId !== liveMatch.fixtureId) {
    resetCarouselForFixture(
      liveMatch.fixtureId,
      liveMatch.baseInfoCards,
      sortedEventCards,
    );
    return;
  }

  syncBaseInfoCards(liveMatch.baseInfoCards);
  syncLiveEventCards(sortedEventCards);
  flushPendingEventCards();
}

function resetCarouselForFixture(
  fixtureId: number,
  nextBaseInfoCards: InfoCard[],
  nextEventCards: EventInfoCard[],
) {
  activeFixtureId = fixtureId;
  pendingBaseInfoCards = null;
  pendingEventCards = [];
  baseInfoCards.value = nextBaseInfoCards;
  carouselQueue.value = insertEventCardsAfterCurrent(
    [...nextBaseInfoCards],
    nextEventCards.flatMap(createEventDisplayCards),
  );
  previousEventCards.value = nextEventCards;
  activeCardIndex.value = 0;
  seenEventIds.clear();
  nextEventCards.forEach((eventCard) => seenEventIds.add(eventCard.id));
}

function syncBaseInfoCards(nextBaseInfoCards: InfoCard[]) {
  baseInfoCards.value = nextBaseInfoCards;
  if (activeCardIndex.value !== 0 && carouselQueue.value.length > 1) {
    pendingBaseInfoCards = nextBaseInfoCards;
    return;
  }

  applyBaseInfoCards(nextBaseInfoCards);
}

function applyBaseInfoCards(nextBaseInfoCards: InfoCard[]) {
  if (carouselQueue.value.length === 0) {
    carouselQueue.value = [...nextBaseInfoCards];
    return;
  }

  const nextBaseById = new Map(
    nextBaseInfoCards.map((card) => [card.id, card]),
  );
  const retainedCards = carouselQueue.value.flatMap((card) => {
    if (isEventDisplayCard(card)) {
      return [card];
    }

    const nextCard = nextBaseById.get(card.id);
    return nextCard ? [nextCard] : [];
  });
  const retainedBaseIds = new Set(
    retainedCards
      .filter((card) => !isEventDisplayCard(card))
      .map((card) => card.id),
  );
  const missingBaseCards = nextBaseInfoCards.filter(
    (card) => !retainedBaseIds.has(card.id),
  );

  carouselQueue.value = [...retainedCards, ...missingBaseCards];
}

function syncLiveEventCards(nextEventCards: EventInfoCard[]) {
  const newEventCards = nextEventCards.filter(
    (eventCard) => !seenEventIds.has(eventCard.id),
  );
  previousEventCards.value = nextEventCards;

  if (newEventCards.length === 0) {
    return;
  }

  newEventCards.forEach((eventCard) => seenEventIds.add(eventCard.id));
  pendingEventCards = [
    ...pendingEventCards,
    ...newEventCards.flatMap(createEventDisplayCards),
  ];
}

function flushPendingEventCards() {
  if (pendingEventCards.length === 0 || activeCardIndex.value !== 0) {
    return;
  }

  if (carouselQueue.value.length === 0) {
    carouselQueue.value = [...baseInfoCards.value];
  }

  carouselQueue.value = insertEventCardsAfterCurrent(
    carouselQueue.value,
    pendingEventCards,
  );
  pendingEventCards = [];
}

function applyDeferredCarouselUpdates() {
  if (pendingBaseInfoCards) {
    const nextBaseInfoCards = pendingBaseInfoCards;
    pendingBaseInfoCards = null;
    applyBaseInfoCards(nextBaseInfoCards);
  }

  flushPendingEventCards();
}

function pickStat(stats: ApiFootballBroadcastStat[], label: string) {
  return stats.find((stat) => stat.label === label);
}

function statMetric(stat: ApiFootballBroadcastStat): StatMetric {
  return {
    id: stat.label,
    label: stat.label,
    home: stat.home,
    away: stat.away,
    homePct: stat.homePct,
    awayPct: stat.awayPct,
  };
}

function compactMetrics(
  stats: Array<ApiFootballBroadcastStat | undefined>,
): StatMetric[] {
  return stats
    .filter((stat): stat is ApiFootballBroadcastStat => stat !== undefined)
    .map((stat) => statMetric(stat));
}

function topRatedPlayerFromSnapshot(
  snapshot: ApiFootballBroadcastSnapshot,
): TopRatedPlayer | null {
  const players = snapshot.lineups.flatMap((lineup) =>
    lineup.players.map((player: ApiFootballBroadcastLineupPlayer) => ({
      player,
      teamCode: lineup.code,
      ratingValue: Number.parseFloat(player.rating ?? ""),
    })),
  );
  const [topPlayer] = players
    .filter((entry) => Number.isFinite(entry.ratingValue))
    .sort((a, b) => b.ratingValue - a.ratingValue);

  if (!topPlayer) {
    return null;
  }

  return {
    name: topPlayer.player.longName ?? topPlayer.player.name,
    teamCode: topPlayer.teamCode,
    no: topPlayer.player.no,
    rating: topPlayer.player.rating ?? topPlayer.ratingValue.toFixed(1),
    photoUrl: topPlayer.player.photoUrl,
  };
}

function loadDemoEventQueue() {
  const baseMatch = createProgramMatchFromSnapshot(
    createDemoBroadcastSnapshot([]),
  );
  const eventMatch = createProgramMatchFromSnapshot(
    createDemoBroadcastSnapshot(createDemoBroadcastEvents()),
  );

  liveError.value = null;
  liveStatus.value = "ready";
  resetCarouselForFixture(baseMatch.fixtureId, baseMatch.baseInfoCards, []);
  syncLiveEventCards(sortEventCards(eventMatch.eventCards));
  flushPendingEventCards();
}

function createDemoBroadcastSnapshot(
  events: ApiFootballBroadcastEvent[],
): ApiFootballBroadcastSnapshot {
  return {
    fixtureId: 20260525,
    leagueId: 1,
    leagueName: "FIFA 월드컵 2026",
    leagueShortName: "월드컵",
    season: 2026,
    home: "대한민국",
    away: "브라질",
    homeId: 10,
    awayId: 20,
    homeCode: "KOR",
    awayCode: "BRA",
    homeEnglishCode: "KOR",
    awayEnglishCode: "BRA",
    homeLogoUrl: koreaFlagUrl,
    awayLogoUrl: brazilFlagUrl,
    score: "2-1",
    clock: "72'",
    addedTime: "",
    status: "후반 72분",
    venue: "Broadcast Demo Stadium",
    lineups: [
      {
        teamId: 10,
        name: "대한민국",
        code: "KOR",
        shape: "4-2-3-1",
        substituteNumbers: {},
        players: [
          {
            id: 7,
            no: 7,
            name: "손흥민",
            pos: "FW",
            rating: "8.7",
            photoUrl: "https://media.api-sports.io/football/players/186.png",
          },
          {
            id: 18,
            no: 18,
            name: "이강인",
            pos: "MF",
            rating: "7.1",
            photoUrl: "https://media.api-sports.io/football/players/27843.png",
          },
          {
            id: 11,
            no: 11,
            name: "황희찬",
            pos: "FW",
            rating: "7.4",
            photoUrl: "https://media.api-sports.io/football/players/2480.png",
          },
        ],
      },
      {
        teamId: 20,
        name: "브라질",
        code: "BRA",
        shape: "4-3-3",
        substituteNumbers: {},
        players: [
          {
            id: 9,
            no: 10,
            name: "네이마르",
            pos: "FW",
            rating: "7.9",
            photoUrl: "https://media.api-sports.io/football/players/276.png",
          },
          {
            id: 4,
            no: 4,
            name: "마르키뉴스",
            pos: "DF",
            rating: "6.8",
            photoUrl: "https://media.api-sports.io/football/players/305.png",
          },
        ],
      },
    ],
    playerRatings: {
      7: "8.7",
      9: "7.9",
    },
    stats: [
      {
        label: "점유율",
        home: "58%",
        away: "42%",
        homePct: 58,
        awayPct: 42,
      },
      {
        label: "전체슈팅",
        home: "13",
        away: "9",
        homePct: 59,
        awayPct: 41,
      },
      {
        label: "유효슈팅",
        home: "6",
        away: "4",
        homePct: 60,
        awayPct: 40,
      },
      {
        label: "코너킥",
        home: "7",
        away: "4",
        homePct: 64,
        awayPct: 36,
      },
      {
        label: "레드카드",
        home: "0",
        away: "1",
        homePct: 0,
        awayPct: 100,
      },
      {
        label: "옐로카드",
        home: "1",
        away: "3",
        homePct: 25,
        awayPct: 75,
      },
      {
        label: "파울",
        home: "8",
        away: "13",
        homePct: 38,
        awayPct: 62,
      },
    ],
    events,
  };
}

function createDemoBroadcastEvents(): ApiFootballBroadcastEvent[] {
  return [
    {
      id: "demo-goal",
      kind: "goal",
      teamId: 10,
      teamCode: "KOR",
      opponentCode: "BRA",
      minute: "64'",
      title: "득점",
      detail: "손흥민 · 필드골",
      playerId: 7,
      player: "손흥민",
      playerNumber: 7,
      playerPhotoUrl: "https://media.api-sports.io/football/players/186.png",
      teamLogoUrl: koreaFlagUrl,
      score: "2-1",
    },
    {
      id: "demo-own-goal",
      kind: "own-goal",
      teamId: 20,
      teamCode: "BRA",
      opponentCode: "KOR",
      minute: "66'",
      title: "자책골",
      detail: "마르키뉴스 · 자책골",
      playerId: 4,
      player: "마르키뉴스",
      playerNumber: 4,
      playerPhotoUrl: "https://media.api-sports.io/football/players/305.png",
      teamLogoUrl: brazilFlagUrl,
      score: "2-2",
    },
    {
      id: "demo-substitution",
      kind: "substitution",
      teamId: 10,
      teamCode: "KOR",
      opponentCode: "BRA",
      minute: "67'",
      title: "선수 교체",
      detail: "이강인 OUT · 황희찬 IN",
      playerId: 18,
      player: "이강인",
      assistId: 11,
      assist: "황희찬",
      outPlayer: "이강인",
      outPlayerNumber: 18,
      outPlayerPhotoUrl: "https://media.api-sports.io/football/players/27843.png",
      inPlayer: "황희찬",
      inPlayerNumber: 11,
      inPlayerPhotoUrl: "https://media.api-sports.io/football/players/2480.png",
      teamLogoUrl: koreaFlagUrl,
    },
    {
      id: "demo-yellow-card",
      kind: "yellow-card",
      teamId: 20,
      teamCode: "BRA",
      opponentCode: "KOR",
      minute: "69'",
      title: "경고",
      detail: "네이마르 · 옐로카드",
      playerId: 9,
      player: "네이마르",
      playerNumber: 10,
      playerPhotoUrl: "https://media.api-sports.io/football/players/276.png",
      teamLogoUrl: brazilFlagUrl,
    },
    {
      id: "demo-red-card",
      kind: "red-card",
      teamId: 20,
      teamCode: "BRA",
      opponentCode: "KOR",
      minute: "71'",
      title: "퇴장",
      detail: "수비수 · 레드카드",
      playerId: 4,
      player: "마르키뉴스",
      playerNumber: 4,
      playerPhotoUrl: "https://media.api-sports.io/football/players/305.png",
      teamLogoUrl: brazilFlagUrl,
    },
    {
      id: "demo-var",
      kind: "var",
      teamId: 10,
      teamCode: "KOR",
      opponentCode: "BRA",
      minute: "74'",
      title: "VAR 판독",
      detail: "득점 여부 확인",
    },
  ];
}

function createProgramMatchFromSnapshot(
  snapshot: ApiFootballBroadcastSnapshot,
): ProgramMatch {
  const possession = pickStat(snapshot.stats, "점유율");
  const shots = pickStat(snapshot.stats, "전체슈팅");
  const shotsOnGoal = pickStat(snapshot.stats, "유효슈팅");
  const corners = pickStat(snapshot.stats, "코너킥");
  const redCards = pickStat(snapshot.stats, "레드카드");
  const yellowCards = pickStat(snapshot.stats, "옐로카드");
  const fouls = pickStat(snapshot.stats, "파울");
  const attackMetrics = compactMetrics([shots, shotsOnGoal, corners]);
  const disciplineMetrics = compactMetrics([redCards, yellowCards, fouls]);
  const topRatedPlayer = topRatedPlayerFromSnapshot(snapshot);
  const statInfoCards: InfoCard[] = [];
  const baseInfoCards: InfoCard[] = [
    {
      id: "worldcup-kickoff-banner",
      kind: "image-banner",
      eyebrow: "FIFA 월드컵 2026",
      title: "북중미 월드컵",
      detail: "개막을 향한 카운트다운",
      label: "KICKOFF 2026",
      imageUrl: worldCupKickoffBannerUrl,
    },
    {
      id: "live-banner",
      kind: "banner",
      eyebrow: snapshot.leagueName,
      title: `${snapshot.home} vs ${snapshot.away}`,
      detail: snapshot.venue,
      leftValue: snapshot.homeCode,
      rightValue: snapshot.awayCode,
      label: `${snapshot.homeCode} / ${snapshot.awayCode}`,
    },
  ];

  if (possession) {
    statInfoCards.push({
      id: "possession-stat",
      kind: "possession-stat",
      eyebrow: "경기 주도권",
      title: "점유율",
      detail: `${snapshot.clock} 기준 라이브 점유율`,
      leftValue: possession.home,
      rightValue: possession.away,
      label: `${snapshot.homeCode} / ${snapshot.awayCode}`,
      homeCode: snapshot.homeCode,
      awayCode: snapshot.awayCode,
      homePct: possession.homePct,
      awayPct: possession.awayPct,
    });
  }

  if (attackMetrics.length > 0) {
    statInfoCards.push({
      id: "attack-stats",
      kind: "metric-group",
      eyebrow: "공격 지표",
      title: "슈팅 · 유효슈팅 · 코너킥",
      detail: `${snapshot.homeCode} / ${snapshot.awayCode}`,
      label: "ATTACK",
      homeCode: snapshot.homeCode,
      awayCode: snapshot.awayCode,
      metricTheme: "attack",
      metrics: attackMetrics,
    });
  }

  if (disciplineMetrics.length > 0) {
    statInfoCards.push({
      id: "discipline-stats",
      kind: "metric-group",
      eyebrow: "징계 지표",
      title: "레드카드 · 옐로카드 · 파울",
      detail: `${snapshot.homeCode} / ${snapshot.awayCode}`,
      label: "DISCIPLINE",
      homeCode: snapshot.homeCode,
      awayCode: snapshot.awayCode,
      metricTheme: "discipline",
      metrics: disciplineMetrics,
    });
  }

  if (topRatedPlayer) {
    statInfoCards.push({
      id: "top-rated-player",
      kind: "player-rating",
      eyebrow: "플레이어 포커스",
      title: "최고 평점 선수",
      detail: topRatedPlayer.name,
      label: "TOP RATED",
      playerName: topRatedPlayer.name,
      playerTeamCode: topRatedPlayer.teamCode,
      playerNumber: topRatedPlayer.no,
      playerRating: topRatedPlayer.rating,
      playerImageUrl: topRatedPlayer.photoUrl,
    });
  }

  if (statInfoCards.length > 0) {
    baseInfoCards.push(
      {
        id: "match-stats-intro",
        kind: "image-banner",
        eyebrow: "주요 경기 기록",
        title: "주요 경기 기록",
        detail: "라이브 지표 소개",
        label: "MATCH STATS",
        imageUrl: matchStatsIntroUrl,
      },
      ...statInfoCards,
    );
  }

  return {
    fixtureId: snapshot.fixtureId,
    home: snapshot.home,
    away: snapshot.away,
    homeCode: snapshot.homeCode,
    awayCode: snapshot.awayCode,
    score: snapshot.score,
    clock: snapshot.clock,
    status: snapshot.status,
    baseInfoCards,
    eventCards: snapshot.events.map((event, index) => ({
      id: event.id,
      kind: "event",
      eventType: programEventType(event),
      eventSplashType: eventSplashType(event),
      sequence: index + 1,
      eyebrow: event.minute,
      title: event.title,
      detail: [event.player, event.detail].filter(Boolean).join(" · "),
      leftValue: eventLeftValue(event, snapshot.score),
      rightValue: eventRightValue(event),
      label: event.teamCode,
      eventPlayerName: event.player,
      eventPlayerNumber: event.kind === "var" ? undefined : event.playerNumber,
      eventPlayerImageUrl: event.playerPhotoUrl,
      eventTeamLogoUrl:
        event.teamLogoUrl ??
        (event.teamId === snapshot.homeId
          ? snapshot.homeLogoUrl
          : event.teamId === snapshot.awayId
            ? snapshot.awayLogoUrl
            : undefined),
      substitutionOutName:
        event.outPlayer ?? event.player,
      substitutionOutNumber: event.outPlayerNumber ?? event.playerNumber,
      substitutionOutImageUrl: event.outPlayerPhotoUrl ?? event.playerPhotoUrl,
      substitutionInName:
        event.inPlayer ?? event.assist,
      substitutionInNumber: event.inPlayerNumber ?? event.assistNumber,
      substitutionInImageUrl: event.inPlayerPhotoUrl ?? event.assistPhotoUrl,
    })),
  };
}

function createEventDisplayCards(eventCard: EventInfoCard): EventDisplayCard[] {
  return [createEventSplashCard(eventCard), eventCard];
}

function createEventSplashCard(eventCard: EventInfoCard): EventSplashCard {
  return {
    id: `${eventCard.id}-splash`,
    kind: "event-splash",
    eventType: eventCard.eventType,
    eventSplashType: eventCard.eventSplashType,
    sequence: eventCard.sequence,
    eyebrow: eventCard.eyebrow,
    title: eventCard.title,
    detail: eventCard.detail,
    leftValue: eventCard.leftValue,
    rightValue: eventCard.rightValue,
    label: eventCard.label,
    eventPlayerName: eventCard.eventPlayerName,
    eventPlayerNumber: eventCard.eventPlayerNumber,
    eventPlayerImageUrl: eventCard.eventPlayerImageUrl,
    eventTeamLogoUrl: eventCard.eventTeamLogoUrl,
    substitutionOutName: eventCard.substitutionOutName,
    substitutionOutNumber: eventCard.substitutionOutNumber,
    substitutionOutImageUrl: eventCard.substitutionOutImageUrl,
    substitutionInName: eventCard.substitutionInName,
    substitutionInNumber: eventCard.substitutionInNumber,
    substitutionInImageUrl: eventCard.substitutionInImageUrl,
    imageUrl: eventSplashImageUrls[eventCard.eventSplashType],
  };
}

function programEventType(
  event: ApiFootballBroadcastEvent,
): EventInfoCard["eventType"] {
  switch (event.kind) {
    case "goal":
      return "goal";
    case "own-goal":
      return "own-goal";
    case "yellow-card":
    case "red-card":
    case "card":
      return "card";
    case "var":
      return "var";
    case "substitution":
      return "substitution";
  }
}

function eventSplashType(event: ApiFootballBroadcastEvent): EventSplashType {
  switch (event.kind) {
    case "goal":
      return "goal";
    case "own-goal":
      return "own-goal";
    case "substitution":
      return "substitution";
    case "yellow-card":
    case "card":
      return "yellow-card";
    case "red-card":
      return "red-card";
    case "var":
      return "var";
  }
}

function eventLeftValue(event: ApiFootballBroadcastEvent, score: string) {
  if (event.kind === "goal" || event.kind === "own-goal")
    return event.score ?? score;
  if (event.kind === "yellow-card") return "경고";
  if (event.kind === "red-card") return "퇴장";
  if (event.kind === "var") return "VAR";
  if (event.kind === "substitution") return "교체";
  return "라이브";
}

function eventRightValue(event: ApiFootballBroadcastEvent) {
  if (event.kind === "substitution") return "투입";
  return event.teamCode;
}

function playerInitial(name: string | undefined) {
  return name?.trim().slice(0, 1) || "?";
}

function playerNumberLabel(number: number | undefined) {
  return number === undefined ? "#--" : `#${number}`;
}
</script>

<template>
  <main
    v-if="isAdminAllowed"
    class="program-stage"
    :data-league="theme.slug"
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
        class="bottom-info-carousel"
        data-testid="program-bottom-carousel"
        :data-active-card-kind="activeVisibleCardKind"
        :data-carousel-interval-ms="CAROUSEL_INTERVAL_MS"
        :data-event-insert-index="LATEST_EVENT_INSERT_INDEX"
        aria-live="polite"
      >
        <div class="carousel-window">
          <div
            v-if="carouselCards.length === 0"
            class="program-live-state"
            data-testid="program-live-empty"
          >
            <span>라이브 데이터</span>
            <strong>{{ liveStateLabel }}</strong>
          </div>
          <div
            v-else
            class="carousel-track"
            :style="infoTrackStyle"
            data-testid="program-info-track"
            @transitionend="handleInfoTrackTransitionEnd"
          >
            <article
              v-for="(card, cardIndex) in carouselCards"
              :key="card.carouselKey"
              :class="[
                'info-card',
                `info-card--${card.kind}`,
                card.eventType ? `info-card--event-${card.eventType}` : '',
                card.metricTheme
                  ? `info-card--metric-${card.metricTheme}`
                  : '',
                { 'info-card--active': cardIndex === activeCardIndex },
                { 'info-card--clone': card.isClone },
              ]"
              :data-card-id="card.id"
              :data-card-kind="card.kind"
              :data-carousel-clone="card.isClone ? 'true' : 'false'"
              :data-event-type="card.eventType"
              :data-event-splash-type="card.eventSplashType"
              :data-testid="
                card.isClone ? 'program-info-card-clone' : 'program-info-card'
              "
              :aria-hidden="card.isClone ? 'true' : undefined"
            >
              <template
                v-if="
                  card.kind === 'image-banner' || card.kind === 'event-splash'
                "
              >
                <img
                  class="program-image-banner"
                  :src="card.imageUrl"
                  :alt="card.title"
                  :data-testid="
                    card.kind === 'event-splash'
                      ? 'program-event-splash-image'
                      : 'program-image-banner'
                  "
                />
              </template>

              <template v-else-if="card.kind === 'possession-stat'">
                <div class="broadcast-stat-copy">
                  <span>{{ card.eyebrow }}</span>
                  <strong>{{ card.title }}</strong>
                  <p>
                    {{ card.homeCode }}
                    {{ possessionPercentLabel(card, "home") }} ·
                    {{ card.awayCode }}
                    {{ possessionPercentLabel(card, "away") }}
                  </p>
                </div>
                <div class="possession-chart" aria-hidden="true">
                  <div class="possession-side possession-side-home">
                    <span>{{ card.homeCode }}</span>
                    <strong>{{ possessionPercentLabel(card, "home") }}</strong>
                  </div>
                  <PossessionPieChart
                    class="possession-pie"
                    :home-pct="possessionValue(card, 'home')"
                    :away-pct="possessionValue(card, 'away')"
                    :home-color="possessionHomeColor"
                    :away-color="theme.accent"
                  />
                  <div class="possession-side possession-side-away">
                    <strong>{{ possessionPercentLabel(card, "away") }}</strong>
                    <span>{{ card.awayCode }}</span>
                  </div>
                </div>
              </template>

              <template v-else-if="card.kind === 'metric-group'">
                <div class="broadcast-stat-copy">
                  <span>{{ card.eyebrow }}</span>
                  <strong>{{ card.title }}</strong>
                  <p>{{ card.detail }}</p>
                </div>
                <div class="metric-grid" aria-hidden="true">
                  <div
                    v-for="metric in card.metrics"
                    :key="metric.id"
                    class="metric-cell"
                  >
                    <span class="metric-label">{{ metric.label }}</span>
                    <div class="metric-bars">
                      <div class="metric-bar metric-bar-home">
                        <span :style="{ '--bar-height': `${metric.homePct}%` }"></span>
                      </div>
                      <div class="metric-bar metric-bar-away">
                        <span :style="{ '--bar-height': `${metric.awayPct}%` }"></span>
                      </div>
                    </div>
                    <strong class="metric-score">
                      <b>{{ metric.home }}</b>
                      <i></i>
                      <b>{{ metric.away }}</b>
                    </strong>
                  </div>
                </div>
              </template>

              <template v-else-if="card.kind === 'player-rating'">
                <div class="player-rating-portrait">
                  <img
                    v-if="card.playerImageUrl"
                    :src="card.playerImageUrl"
                    :alt="card.playerName"
                  />
                  <span v-else>{{ card.playerName?.slice(0, 1) }}</span>
                </div>
                <div class="broadcast-stat-copy">
                  <span>{{ card.eyebrow }}</span>
                  <strong>{{ card.playerName }}</strong>
                  <p>{{ card.title }}</p>
                </div>
                <div class="player-rating-meta">
                  <span>{{ card.playerTeamCode }}</span>
                  <b>No. {{ card.playerNumber }}</b>
                  <strong>{{ playerRatingLabel(card) }}</strong>
                  <i>현재 평점</i>
                </div>
              </template>

              <template v-else-if="card.kind === 'banner'">
                <div class="host-map-line" aria-hidden="true">
                  <span>VAN</span><span>TOR</span><span>NYC</span
                  ><span>DAL</span><span>MEX</span>
                </div>
                <div class="host-map-copy">
                  <b>{{ card.eyebrow }}</b>
                  <strong>{{ card.title }}</strong>
                  <p>{{ card.detail }}</p>
                </div>
              </template>

              <template v-else-if="card.kind === 'stat'">
                <div class="stat-seal">WC<br />26</div>
                <div class="stat-copy">
                  <span>{{ card.eyebrow }}</span>
                  <strong>{{ card.title }}</strong>
                  <p>{{ card.detail }}</p>
                </div>
                <div class="stat-values">
                  <b>{{ card.leftValue }}</b>
                  <i>{{ card.label }}</i>
                  <b>{{ card.rightValue }}</b>
                </div>
              </template>

              <template
                v-else-if="
                  card.kind === 'event' && card.eventType === 'substitution'
                "
              >
                <figure class="event-player event-player--out">
                  <img
                    v-if="card.substitutionOutImageUrl"
                    :src="card.substitutionOutImageUrl"
                    :alt="card.substitutionOutName"
                  />
                  <span v-else>{{
                    playerInitial(card.substitutionOutName)
                  }}</span>
                </figure>
                <div class="substitution-copy">
                  <span>{{ card.eyebrow }} · {{ card.label }}</span>
                  <div class="substitution-row substitution-row--out">
                    <strong>{{
                      card.substitutionOutName ?? card.eventPlayerName
                    }}</strong>
                    <b>{{ playerNumberLabel(card.substitutionOutNumber) }}</b>
                    <i aria-hidden="true">↓</i>
                  </div>
                  <div class="substitution-row substitution-row--in">
                    <strong>{{ card.substitutionInName }}</strong>
                    <b>{{ playerNumberLabel(card.substitutionInNumber) }}</b>
                    <i aria-hidden="true">↑</i>
                  </div>
                </div>
                <figure class="event-player event-player--in">
                  <img
                    v-if="card.substitutionInImageUrl"
                    :src="card.substitutionInImageUrl"
                    :alt="card.substitutionInName"
                  />
                  <span v-else>{{ playerInitial(card.substitutionInName) }}</span>
                </figure>
              </template>

              <template v-else-if="card.kind === 'event'">
                <figure class="event-player event-player--primary">
                  <img
                    v-if="card.eventPlayerImageUrl"
                    :src="card.eventPlayerImageUrl"
                    :alt="card.eventPlayerName"
                  />
                  <span v-else>{{ playerInitial(card.eventPlayerName) }}</span>
                </figure>
                <div class="event-copy">
                  <span>{{ card.eyebrow }} · {{ card.label }}</span>
                  <strong>{{ card.title }}</strong>
                  <p>
                    {{ card.eventPlayerName ?? card.detail }}
                    <b v-if="card.eventPlayerNumber !== undefined">{{
                      playerNumberLabel(card.eventPlayerNumber)
                    }}</b>
                  </p>
                </div>
                <figure class="event-team-mark">
                  <img
                    v-if="card.eventTeamLogoUrl"
                    :src="card.eventTeamLogoUrl"
                    :alt="card.label"
                  />
                  <span v-else>{{ card.label }}</span>
                </figure>
              </template>

              <template v-else-if="card.kind === 'player'">
                <div class="medal-marker">1</div>
                <div class="medal-copy">
                  <span>{{ card.eyebrow }}</span>
                  <strong>{{ card.title }}</strong>
                  <p>{{ card.detail }}</p>
                </div>
                <div class="medal-rating">{{ card.leftValue }}</div>
              </template>

              <template v-else>
                <header class="info-card-kicker">
                  <span>{{ card.eyebrow }}</span>
                  <b>{{ card.label }}</b>
                </header>
                <div class="info-card-main">
                  <strong class="info-value">{{ card.leftValue }}</strong>
                  <div class="info-copy">
                    <span>{{ card.title }}</span>
                    <p>{{ card.detail }}</p>
                  </div>
                  <strong class="info-value info-value-away">{{
                    card.rightValue
                  }}</strong>
                </div>
              </template>
            </article>
          </div>
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
  <main v-else class="program-stage program-stage--locked" data-testid="program-locked">
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
  display: flex;
  flex-direction: column;
}

.program-right {
  flex: 0 0 22%;
  min-width: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #00b140;
}

.feed-surface {
  position: relative;
  flex: 0 0 78%;
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

.bottom-info-carousel {
  position: relative;
  flex: 0 0 22%;
  min-height: 0;
  overflow: hidden;
  background: linear-gradient(
    90deg,
    var(--program-dark),
    color-mix(in srgb, var(--program-panel) 78%, #000000)
  );
  border-right: 0.12rem solid
    color-mix(in srgb, var(--program-line) 38%, #000000);
  isolation: isolate;
}

.bottom-info-carousel::before {
  content: "";
  position: absolute;
  z-index: 1;
  top: 0;
  left: 0;
  right: 0;
  height: 0.42rem;
  background: linear-gradient(
    90deg,
    var(--program-accent) 0 18%,
    var(--program-panel-alt) 18% 48%,
    var(--program-accent-alt) 48% 78%,
    var(--program-line) 78% 100%
  );
}

.bottom-info-carousel[data-active-card-kind="event-splash"] {
  border-right-color: transparent;
}

.bottom-info-carousel[data-active-card-kind="event-splash"]::before {
  opacity: 0;
}

.carousel-window {
  position: relative;
  z-index: 2;
  width: 100%;
  height: 100%;
  overflow: hidden;
}

.program-live-state {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.55rem;
  color: var(--program-text);
  text-align: center;
}

.program-live-state span {
  color: var(--program-muted);
  font-size: 0.8rem;
  font-weight: 900;
}

.program-live-state strong {
  max-width: 72%;
  font-size: 1.2rem;
  line-height: 1.2;
}

.carousel-track {
  width: 100%;
  height: 100%;
  transition: transform 620ms cubic-bezier(0.22, 0.82, 0.2, 1);
}

.info-card {
  position: relative;
  height: 100%;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  padding: 1.45% 2.2% 1.15%;
  background:
    linear-gradient(
      90deg,
      color-mix(in srgb, var(--program-accent) 18%, transparent),
      transparent 30%
    ),
    linear-gradient(
      180deg,
      color-mix(in srgb, var(--program-panel) 90%, #000000),
      var(--program-dark)
    );
  border-top: 0.08rem solid color-mix(in srgb, var(--program-line) 42%, #ffffff);
  isolation: isolate;
}

.info-card--event {
  background:
    linear-gradient(
      90deg,
      color-mix(in srgb, var(--program-accent) 38%, transparent),
      transparent 34%
    ),
    linear-gradient(
      180deg,
      color-mix(in srgb, var(--program-panel-alt) 24%, var(--program-dark)),
      var(--program-dark)
    );
}

.info-card--event .info-card-kicker span,
.info-card--event .info-value-away {
  color: var(--program-panel-alt);
}

.info-card--event .info-value {
  color: var(--program-line);
}

.info-card--image-banner {
  padding: 0;
  background: #061b57;
}

.info-card--event-splash {
  padding: 0;
  background: #000000;
  border-top: 0;
}

.program-image-banner {
  width: 100%;
  height: 100%;
  display: block;
  object-fit: cover;
  object-position: center;
}

.info-card--event-splash .program-image-banner {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 100%;
  height: auto;
  object-fit: initial;
  background: #000000;
  transform: translate(-50%, -50%);
}

.info-card--banner,
.info-card--possession-stat,
.info-card--metric-group,
.info-card--player-rating,
.info-card--stat,
.info-card--player,
.info-card--event-goal,
.info-card--event-own-goal,
.info-card--event-card,
.info-card--event-substitution,
.info-card--event-var {
  flex-direction: row;
  align-items: center;
  gap: 1.4rem;
  padding: 1.3% 2.2%;
}

.host-map-line,
.stat-seal,
.goal-orbit,
.mesh-badge,
.medal-marker,
.event-player,
.event-copy,
.event-team-mark,
.substitution-copy,
.broadcast-stat-copy,
.possession-chart,
.metric-grid,
.player-rating-portrait,
.player-rating-meta,
.stat-copy,
.host-map-copy,
.goal-copy,
.mesh-copy,
.medal-copy,
.stat-values,
.goal-score,
.mesh-value,
.medal-rating {
  position: relative;
  z-index: 2;
}

.host-map-line {
  flex: 0 0 40%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 0.8rem;
}

.host-map-line::before {
  content: "";
  position: absolute;
  left: 3.2rem;
  right: 3.2rem;
  top: 50%;
  height: 0.12rem;
  background: var(--program-panel-alt);
  transform: translateY(-50%);
}

.host-map-line span {
  z-index: 2;
  display: grid;
  place-items: center;
  width: 3.35rem;
  aspect-ratio: 1;
  border-radius: 50%;
  background: var(--program-line);
  color: var(--program-dark);
  font-size: 0.78rem;
  font-weight: 950;
}

.host-map-copy,
.broadcast-stat-copy,
.stat-copy,
.goal-copy,
.mesh-copy,
.medal-copy {
  min-width: 0;
  flex: 1 1 auto;
}

.host-map-copy b,
.broadcast-stat-copy span,
.stat-copy span,
.goal-copy span,
.mesh-copy span,
.medal-copy span {
  display: block;
  color: var(--program-panel-alt);
  font-size: 1rem;
  font-weight: 950;
}

.host-map-copy strong,
.broadcast-stat-copy strong,
.stat-copy strong,
.goal-copy strong,
.mesh-copy strong,
.medal-copy strong {
  display: block;
  margin-top: 0.1rem;
  color: var(--program-text);
  font-size: clamp(1.8rem, 2.65vw, 3.7rem);
  font-weight: 950;
  line-height: 0.92;
}

.host-map-copy p,
.broadcast-stat-copy p,
.stat-copy p,
.goal-copy p,
.mesh-copy p,
.medal-copy p {
  margin: 0.45rem 0 0;
  color: var(--program-muted);
  font-size: clamp(0.95rem, 1.12vw, 1.35rem);
  font-weight: 850;
  line-height: 1.2;
}

.info-card--possession-stat,
.info-card--metric-group,
.info-card--player-rating {
  background:
    radial-gradient(
      circle at 5% 50%,
      rgba(201, 151, 43, 0.32),
      transparent 19%
    ),
    linear-gradient(
      90deg,
      rgba(0, 52, 120, 0.32),
      transparent 38%,
      rgba(245, 241, 232, 0.1)
    ),
    linear-gradient(180deg, #101010 0%, #050505 100%);
}

.broadcast-stat-copy {
  min-width: 0;
  flex: 1 1 auto;
}

.info-card--possession-stat .broadcast-stat-copy {
  flex: 0 1 27%;
  max-width: 29%;
}

.possession-chart {
  flex: 1 1 0;
  min-width: 0;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: clamp(0.85rem, 1.25vw, 1.45rem);
}

.possession-side {
  flex: 0 0 clamp(10rem, 11.6vw, 13.75rem);
  display: grid;
  align-items: center;
  column-gap: clamp(0.55rem, 0.72vw, 0.9rem);
  color: var(--program-text);
  font-weight: 950;
}

.possession-side-home {
  grid-template-columns: minmax(3.2rem, max-content) minmax(6.2rem, 1fr);
  justify-items: end;
}

.possession-side-away {
  grid-template-columns: minmax(6.2rem, 1fr) minmax(3.2rem, max-content);
  justify-items: start;
}

.possession-side span {
  font-size: clamp(1.18rem, 1.42vw, 1.78rem);
  line-height: 1;
}

.possession-side-home span {
  color: var(--program-possession-home);
}

.possession-side-away span {
  color: var(--program-accent);
}

.possession-side strong {
  color: var(--program-text);
  width: 100%;
  font-size: clamp(1.85rem, 2.28vw, 3.25rem);
  font-variant-numeric: tabular-nums;
  line-height: 0.9;
  text-align: center;
}

.possession-pie {
  flex: 0 0 auto;
  width: min(8.1rem, 35%);
  aspect-ratio: 1;
}

.metric-grid {
  flex: 0 0 45%;
  height: 100%;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  align-items: stretch;
}

.metric-cell {
  min-width: 0;
  display: grid;
  grid-template-rows: auto 1fr auto;
  align-items: center;
  gap: 0.42rem;
  padding: 0.25rem 1rem;
}

.metric-cell + .metric-cell {
  border-left: 0.14rem solid rgba(255, 255, 255, 0.92);
}

.metric-label {
  color: var(--program-panel-alt);
  font-size: clamp(0.78rem, 0.86vw, 1rem);
  font-weight: 950;
  white-space: nowrap;
  text-align: center;
}

.metric-bars {
  height: 4.9rem;
  min-height: 0;
  display: flex;
  align-items: end;
  justify-content: center;
  gap: 0.42rem;
}

.metric-bar {
  width: 1.1rem;
  height: 100%;
  display: flex;
  align-items: end;
  background: rgba(255, 255, 255, 0.16);
  overflow: hidden;
}

.metric-bar span {
  width: 100%;
  height: var(--bar-height);
  min-height: 0.28rem;
  display: block;
  transform: scaleY(0);
  transform-origin: bottom;
}

.metric-bar-home span {
  background: linear-gradient(180deg, var(--program-line), var(--program-accent));
}

.metric-bar-away span {
  background: linear-gradient(
    180deg,
    var(--program-panel-alt),
    var(--program-accent-alt)
  );
}

.info-card--active .metric-bar span {
  animation: bar-rise 760ms cubic-bezier(0.18, 0.78, 0.2, 1) forwards;
}

.metric-score {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: 0.38rem;
  color: var(--program-text);
  font-size: clamp(1.15rem, 1.35vw, 1.65rem);
  font-weight: 950;
  line-height: 1;
}

.metric-score b {
  text-align: center;
}

.metric-score i {
  width: 0.12rem;
  height: 1.2rem;
  background: rgba(255, 255, 255, 0.92);
}

.info-card--metric-discipline .metric-bar-home span {
  background: linear-gradient(180deg, #f5f1e8, #c9972b);
}

.info-card--metric-discipline .metric-bar-away span {
  background: linear-gradient(180deg, #ff6f7d, #c8102e);
}

.player-rating-portrait {
  flex: 0 0 auto;
  width: 7.2rem;
  aspect-ratio: 1;
  display: grid;
  place-items: center;
  overflow: hidden;
  border-radius: 50%;
  background:
    linear-gradient(#050505, #050505) padding-box,
    conic-gradient(
        from 210deg,
        var(--program-panel-alt),
        var(--program-line),
        var(--program-accent),
        var(--program-panel-alt)
      )
      border-box;
  border: 0.26rem solid transparent;
  box-shadow: 0 0 1.4rem rgba(201, 151, 43, 0.42);
}

.player-rating-portrait img {
  width: 100%;
  height: 100%;
  display: block;
  object-fit: cover;
}

.player-rating-portrait span {
  color: var(--program-panel-alt);
  font-size: 3rem;
  font-weight: 950;
}

.player-rating-meta {
  flex: 0 0 34%;
  display: grid;
  grid-template-columns: repeat(3, auto);
  align-items: baseline;
  justify-content: end;
  gap: 0.26rem 1.05rem;
  color: var(--program-text);
  text-align: right;
}

.player-rating-meta span,
.player-rating-meta b,
.player-rating-meta strong {
  color: var(--program-text);
  font-size: clamp(2.1rem, 2.85vw, 4rem);
  font-weight: 950;
  line-height: 0.85;
  white-space: nowrap;
}

.player-rating-meta strong {
  color: var(--program-panel-alt);
  min-width: 2.9ch;
}

.player-rating-meta i {
  grid-column: 1 / -1;
  justify-self: end;
  color: var(--program-muted);
  font-size: 0.9rem;
  font-style: normal;
  font-weight: 950;
  letter-spacing: 0;
}

@keyframes bar-rise {
  from {
    transform: scaleY(0);
  }

  to {
    transform: scaleY(1);
  }
}

.stat-seal {
  flex: 0 0 auto;
  width: 6.8rem;
  aspect-ratio: 1;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background:
    radial-gradient(
      circle at 34% 25%,
      rgba(255, 255, 255, 0.72),
      transparent 24%
    ),
    linear-gradient(
      135deg,
      var(--program-line),
      var(--program-panel-alt) 48%,
      #7b4d11
    );
  color: var(--program-dark);
  font-size: 1.75rem;
  font-weight: 950;
  line-height: 0.88;
  text-align: center;
  box-shadow:
    0 0 0 0.28rem var(--program-dark),
    0 0 0 0.44rem var(--program-accent);
}

.stat-values {
  flex: 0 0 26%;
  display: grid;
  grid-template-columns: auto auto auto;
  align-items: center;
  justify-content: end;
  gap: 0.75rem;
}

.stat-values b {
  color: var(--program-text);
  font-size: clamp(2.5rem, 3.5vw, 4.9rem);
  font-weight: 950;
  line-height: 0.9;
}

.stat-values i {
  color: var(--program-panel-alt);
  font-size: 0.9rem;
  font-style: normal;
  font-weight: 950;
  white-space: nowrap;
}

.goal-orbit {
  flex: 0 0 auto;
  width: 6.8rem;
  aspect-ratio: 1;
  display: grid;
  place-items: center;
  border: 0.14rem dashed var(--program-panel-alt);
  border-radius: 50%;
}

.goal-orbit img {
  width: 3.9rem;
  display: block;
}

.goal-orbit span {
  position: absolute;
  width: 0.9rem;
  aspect-ratio: 1;
  border-radius: 50%;
  background: var(--program-accent);
  transform: translate(2.5rem, -2.55rem);
}

.goal-score,
.mesh-value,
.medal-rating {
  flex: 0 0 auto;
  color: var(--program-panel-alt);
  font-size: clamp(2.6rem, 3.6vw, 5rem);
  font-weight: 950;
  line-height: 0.9;
  text-align: right;
}

.info-card--event-card,
.info-card--event-substitution,
.info-card--event-var {
  background:
    linear-gradient(
      45deg,
      rgba(245, 241, 232, 0.12) 0 0.08rem,
      transparent 0.08rem 1.2rem
    ),
    linear-gradient(
      -45deg,
      rgba(245, 241, 232, 0.1) 0 0.08rem,
      transparent 0.08rem 1.2rem
    ),
    linear-gradient(
      90deg,
      rgba(200, 16, 46, 0.22),
      transparent 34%,
      rgba(201, 151, 43, 0.2)
    ),
    var(--program-dark);
}

.event-player {
  flex: 0 0 clamp(5.2rem, 6.2vw, 7.35rem);
  height: clamp(5.2rem, 6.2vw, 7.35rem);
  margin: 0;
  display: grid;
  place-items: center;
  overflow: hidden;
  border-radius: 50%;
  background:
    linear-gradient(#050505, #050505) padding-box,
    conic-gradient(
        from 210deg,
        var(--program-panel-alt),
        var(--program-line),
        var(--program-accent),
        var(--program-panel-alt)
      )
      border-box;
  border: 0.26rem solid transparent;
  box-shadow: 0 0 1.4rem rgba(201, 151, 43, 0.42);
}

.event-player img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.event-player span {
  color: var(--program-panel-alt);
  font-size: clamp(2rem, 2.35vw, 3rem);
  font-weight: 950;
}

.event-player--out {
  box-shadow:
    0 0 1.4rem rgba(201, 151, 43, 0.42),
    0 0 1.25rem rgba(200, 16, 46, 0.32);
}

.event-player--in {
  box-shadow:
    0 0 1.4rem rgba(201, 151, 43, 0.42),
    0 0 1.25rem rgba(33, 196, 111, 0.32);
}

.event-copy,
.substitution-copy {
  min-width: 0;
  flex: 1 1 auto;
}

.event-copy span,
.substitution-copy > span {
  display: block;
  color: var(--program-panel-alt);
  font-size: clamp(0.9rem, 1vw, 1.16rem);
  font-weight: 950;
}

.event-copy strong {
  display: block;
  margin-top: 0.12rem;
  color: var(--program-text);
  font-size: clamp(1.85rem, 2.65vw, 3.65rem);
  font-weight: 950;
  line-height: 0.92;
}

.event-copy p {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin: 0.42rem 0 0;
  color: var(--program-muted);
  font-size: clamp(1rem, 1.2vw, 1.45rem);
  font-weight: 900;
  line-height: 1;
}

.event-copy p b {
  padding: 0.18rem 0.52rem;
  background: rgba(245, 241, 232, 0.12);
  color: var(--program-text);
  font-size: 0.92em;
}

.event-team-mark {
  flex: 0 0 clamp(4.8rem, 5.3vw, 6.35rem);
  height: clamp(4.8rem, 5.3vw, 6.35rem);
  margin: 0;
  display: grid;
  place-items: center;
  padding: 0.46rem;
  overflow: hidden;
  border-radius: 0.72rem;
  background:
    linear-gradient(#ffffff, #ffffff) padding-box,
    conic-gradient(
        from 210deg,
        var(--program-panel-alt),
        var(--program-line),
        var(--program-accent),
        var(--program-panel-alt)
      )
      border-box;
  border: 0.22rem solid transparent;
  box-shadow: 0 0 1.25rem rgba(201, 151, 43, 0.36);
}

.event-team-mark img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}

.event-team-mark span {
  color: #050505;
  font-size: clamp(0.95rem, 1vw, 1.2rem);
  font-weight: 950;
}

.substitution-copy {
  display: grid;
  grid-template-rows: auto 1fr 1fr;
  gap: 0.32rem;
}

.substitution-row {
  min-width: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 0.72rem;
  padding: 0.32rem 0.78rem;
  background: rgba(245, 241, 232, 0.08);
}

.substitution-row strong {
  min-width: 0;
  overflow: hidden;
  color: var(--program-text);
  font-size: clamp(1.25rem, 1.65vw, 2.25rem);
  font-weight: 950;
  line-height: 1;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.substitution-row b {
  color: rgba(245, 241, 232, 0.82);
  font-size: clamp(0.9rem, 1vw, 1.2rem);
  font-weight: 950;
}

.substitution-row i {
  width: 2rem;
  aspect-ratio: 1;
  display: grid;
  place-items: center;
  font-size: clamp(1.25rem, 1.5vw, 1.9rem);
  font-style: normal;
  font-weight: 950;
  line-height: 1;
}

.substitution-row--out {
  border-left: 0.28rem solid #c8102e;
}

.substitution-row--out i {
  color: #ff405f;
}

.substitution-row--in {
  border-left: 0.28rem solid #21c46f;
}

.substitution-row--in i {
  color: #37ef8f;
}

.mesh-badge {
  flex: 0 0 6.8rem;
  height: 5.7rem;
  display: grid;
  place-items: center;
  background: var(--program-accent);
  border: 0.12rem solid var(--program-line);
  color: var(--program-text);
  font-size: 2.2rem;
  font-weight: 950;
}

.medal-marker {
  flex: 0 0 auto;
  width: 6.8rem;
  aspect-ratio: 1;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: radial-gradient(
    circle at 35% 25%,
    #ffffff,
    var(--program-panel-alt) 42%,
    #5e3709
  );
  color: var(--program-dark);
  font-size: 3.1rem;
  font-weight: 950;
}

.medal-rating {
  padding: 0.85rem 1.05rem;
  background: var(--program-panel-alt);
  color: var(--program-dark);
  border-radius: 0.3rem;
}

.info-card-kicker {
  flex: 0 0 26%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: var(--program-muted);
  font-weight: 950;
}

.info-card-kicker span {
  color: var(--program-accent-alt);
  font-size: 1.05rem;
}

.info-card-kicker b {
  padding: 0.25rem 0.8rem;
  background: var(--program-dark);
  border: 0.08rem solid var(--program-accent-alt);
  border-radius: 999rem;
  color: var(--program-text);
  font-size: 0.9rem;
}

.info-card-main {
  flex: 1 1 auto;
  min-height: 0;
  display: grid;
  grid-template-columns: 20% 1fr 20%;
  align-items: center;
  gap: 1.3rem;
}

.info-value {
  color: var(--program-text);
  font-size: clamp(2.8rem, 4.2vw, 5.6rem);
  font-weight: 950;
  line-height: 0.9;
  text-align: left;
}

.info-value-away {
  color: var(--program-accent-alt);
  text-align: right;
}

.info-copy {
  min-width: 0;
}

.info-copy span {
  display: block;
  color: var(--program-text);
  font-size: clamp(1.8rem, 2.4vw, 3.6rem);
  font-weight: 950;
  line-height: 1;
}

.info-copy p {
  max-width: 100%;
  margin: 0.55rem 0 0;
  color: var(--program-muted);
  font-size: clamp(1rem, 1.25vw, 1.5rem);
  font-weight: 800;
  line-height: 1.25;
}

.chat-slot {
  flex: 0 0 78%;
  min-height: 0;
  background: #00b140;
}

.character-slot {
  flex: 0 0 22%;
  min-height: 0;
  background: #00b140;
}

.program-stage[data-league="world-cup-2026"] .info-card {
  border-color: color-mix(in srgb, var(--program-panel-alt) 80%, #ffffff);
}

.program-stage[data-league="world-cup-2026"] .bottom-info-carousel {
  background: linear-gradient(
    90deg,
    #050505 0%,
    #111111 34%,
    #051b41 74%,
    #030915 100%
  );
  border-top: 0.18rem solid #c9972b;
  border-right-color: #c9972b;
  box-shadow:
    inset 0 1rem 2.4rem rgba(255, 255, 255, 0.05),
    inset 0 -1.6rem 3rem rgba(0, 0, 0, 0.45);
}

.program-stage[data-league="world-cup-2026"] .bottom-info-carousel::before {
  height: 0.56rem;
  background: linear-gradient(
    90deg,
    #c8102e 0 16%,
    #f5f1e8 16% 30%,
    #c9972b 30% 56%,
    #003478 56% 80%,
    #c8102e 80% 100%
  );
}

.program-stage[data-league="world-cup-2026"] .info-card {
  background:
    linear-gradient(
      90deg,
      rgba(200, 16, 46, 0.26),
      transparent 27%,
      rgba(0, 52, 120, 0.3)
    ),
    linear-gradient(180deg, #151515 0%, #050505 100%);
}

.program-stage[data-league="world-cup-2026"] .info-card--possession-stat,
.program-stage[data-league="world-cup-2026"] .info-card--metric-group,
.program-stage[data-league="world-cup-2026"] .info-card--player-rating {
  background:
    radial-gradient(
      circle at 7% 50%,
      rgba(201, 151, 43, 0.34),
      transparent 20%
    ),
    linear-gradient(
      90deg,
      rgba(0, 52, 120, 0.34),
      transparent 38%,
      rgba(245, 241, 232, 0.1)
    ),
    linear-gradient(180deg, #101010 0%, #050505 100%);
}

.program-stage[data-league="world-cup-2026"] .info-card--event-splash {
  background: #000000;
  border-top: 0;
}

.program-stage[data-league="world-cup-2026"]
  .bottom-info-carousel[data-active-card-kind="event-splash"] {
  border-top-color: transparent;
  border-right-color: transparent;
}

.program-stage[data-league="world-cup-2026"] .info-card--event {
  background:
    linear-gradient(
      90deg,
      rgba(200, 16, 46, 0.42),
      transparent 36%,
      rgba(201, 151, 43, 0.28)
    ),
    linear-gradient(180deg, #1b0a0e 0%, #050505 100%);
}

.program-stage[data-league="world-cup-2026"] .info-card--banner {
  background:
    radial-gradient(
      circle at 18% 64%,
      rgba(200, 16, 46, 0.28),
      transparent 25%
    ),
    linear-gradient(105deg, #050505 0%, #111111 48%, #1b1408 100%);
}

.program-stage[data-league="world-cup-2026"] .host-map-line::before {
  background: #c9972b;
}

.program-stage[data-league="world-cup-2026"] .host-map-line span {
  background: #f5f1e8;
  color: #050505;
  box-shadow: 0 0 0 0.2rem #c9972b;
}

.program-stage[data-league="world-cup-2026"] .info-card--stat {
  background:
    linear-gradient(
      90deg,
      rgba(200, 16, 46, 0.2),
      transparent 20%,
      rgba(201, 151, 43, 0.18) 72%,
      rgba(245, 241, 232, 0.08)
    ),
    linear-gradient(180deg, #17140d 0%, #050505 100%);
}

.program-stage[data-league="world-cup-2026"] .info-card--player {
  background:
    radial-gradient(
      circle at 8% 50%,
      rgba(201, 151, 43, 0.34),
      transparent 20%
    ),
    linear-gradient(90deg, #050505, #17110a 52%, #050505);
}

.program-stage[data-league="world-cup-2026"] .info-card--event-goal {
  background:
    radial-gradient(
      circle at 13% 50%,
      rgba(245, 241, 232, 0.18),
      transparent 18%
    ),
    linear-gradient(90deg, #1a0b10, #050505 48%, #111111);
}

.program-stage[data-league="world-cup-2026"] .info-card--event-own-goal {
  background:
    radial-gradient(
      circle at 13% 50%,
      rgba(245, 241, 232, 0.16),
      transparent 18%
    ),
    linear-gradient(90deg, #05142d, #050505 48%, #24120b);
}

.program-stage[data-league="world-cup-2026"] .info-card--event-card,
.program-stage[data-league="world-cup-2026"] .info-card--event-substitution,
.program-stage[data-league="world-cup-2026"] .info-card--event-var {
  background:
    linear-gradient(
      45deg,
      rgba(245, 241, 232, 0.12) 0 0.08rem,
      transparent 0.08rem 1.2rem
    ),
    linear-gradient(
      -45deg,
      rgba(245, 241, 232, 0.1) 0 0.08rem,
      transparent 0.08rem 1.2rem
    ),
    linear-gradient(
      90deg,
      rgba(200, 16, 46, 0.28),
      transparent 34%,
      rgba(201, 151, 43, 0.24)
    ),
    #070707;
}

.program-stage[data-league="world-cup-2026"] .info-card-kicker span {
  color: #c9972b;
}

.program-stage[data-league="world-cup-2026"] .info-card-kicker b {
  background: #050505;
  border-color: #c9972b;
}

.program-stage[data-league="world-cup-2026"] .info-value-away {
  color: #f6e1a8;
}

.program-stage[data-league="world-cup-2026"]
  .info-card--event
  .info-value-away {
  color: #c9972b;
}
</style>
