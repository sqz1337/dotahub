import { StrictMode, useMemo, useState, type CSSProperties, type ReactNode, type SyntheticEvent } from "react";
import { createRoot, type Root } from "react-dom/client";
import {
  ChevronDown,
  Crown,
  Gauge,
  Skull,
  Zap,
} from "lucide-react";
import cardPreset from "../../card_example.json";
import dashboardData from "../../data/dashboard.json";
import "./styles.css";

type DashboardData = typeof dashboardData;
type CardPreset = typeof cardPreset;
type CardPlayer = DashboardData["players"][number];
type LeaderboardPlayer = DashboardData["leaderboard"][number];
type RecentGame = DashboardData["recentPartyGames"][number];
type FeedEvent = DashboardData["feed"][number];
type GameModeFilter = "all" | "turbo" | "ranked" | "other";

const data = dashboardData as DashboardData;
const playersById = new Map(data.players.map((player) => [player.accountId, player]));

type Page = "dashboard" | "players";

const navItems: { label: string; href: string; page?: Page }[] = [
  { label: "Dashboard", href: "/dashboard/", page: "dashboard" },
  { label: "Players", href: "/players/", page: "players" },
  { label: "Matches", href: "/dashboard/" },
  { label: "Achievements", href: "/dashboard/" },
  { label: "Hall of Fame", href: "/dashboard/" },
];
const modeFilters: { label: string; value: GameModeFilter }[] = [
  { label: "All Modes", value: "all" },
  { label: "Turbo", value: "turbo" },
  { label: "Ranked", value: "ranked" },
  { label: "Other", value: "other" },
];
const rankNames = ["Unranked", "Herald", "Guardian", "Crusader", "Archon", "Legend", "Ancient", "Divine", "Immortal"];
const rankStars = ["", "I", "II", "III", "IV", "V"];
const statKeys = ["Imp", "Far", "Fgt", "Sur", "Obj", "Utl"] as const;
const cardCssMap = {
  cardWidth: "--card-width",
  fontFamily: "--font-family",
  textColor: "--text-color",
  avatarTop: "--avatar-top",
  avatarLeft: "--avatar-left",
  avatarWidth: "--avatar-width",
  avatarHeight: "--avatar-height",
  avatarScale: "--avatar-scale",
  avatarX: "--avatar-x",
  avatarY: "--avatar-y",
  avatarOpacity: "--avatar-opacity",
  avatarSaturate: "--avatar-saturate",
  avatarContrast: "--avatar-contrast",
  avatarBrightness: "--avatar-brightness",
  avatarBlend: "--avatar-blend",
  ratingTop: "--rating-top",
  ratingLeft: "--rating-left",
  ratingWidth: "--rating-width",
  rankTop: "--rank-top",
  rankLeft: "--rank-left",
  rankWidth: "--rank-width",
  rankScale: "--rank-scale",
  nameTop: "--name-top",
  nameLeft: "--name-left",
  nameWidth: "--name-width",
  statsTop: "--stats-top",
  statsLeft: "--stats-left",
  statsWidth: "--stats-width",
  ovrSize: "--ovr-size",
  positionSize: "--position-size",
  nameSize: "--name-size",
  nameSpacing: "--name-spacing",
  statsSize: "--stats-size",
  statsGap: "--stats-gap",
  fxIntensity: "--fx-intensity",
  fxSpeed: "--fx-speed",
  fxColor: "--fx-color",
  fxSecondaryColor: "--fx-secondary-color",
  fxSparkOpacity: "--fx-spark-opacity",
} as const;

function rankLabel(rankTier: number | null | undefined) {
  if (!rankTier) return "Unranked";
  const medal = Math.floor(rankTier / 10);
  const star = rankTier % 10;
  const name = rankNames[medal] ?? "Unranked";
  if (medal >= 8) return name;
  return `${name} ${rankStars[star] ?? ""}`.trim();
}

function rankIconSrc(rankTier: number | null | undefined) {
  if (!rankTier) return null;
  const medal = Math.floor(rankTier / 10);
  if (medal < 1 || medal > 8) return null;
  return `/assets/ranks/rank_icon_${medal}.png`;
}

function pct(value: number | string) {
  return `${Number(value)}%`;
}

function px(value: number | string) {
  return `${Number(value)}px`;
}

function cardStyle(preset: Record<string, string | number>): CSSProperties {
  const style: Record<string, string | number> = {};
  Object.entries(cardCssMap).forEach(([key, cssName]) => {
    let value = preset[key as keyof CardPreset];
    if (value === undefined) return;
    if (key === "cardWidth") value = "clamp(150px, min(calc((100vw - 180px) / 5), calc((100svh - 152px) / 3.12)), 250px)";
    if (
      [
        "avatarTop",
        "avatarLeft",
        "avatarWidth",
        "avatarHeight",
        "avatarX",
        "avatarY",
        "ratingTop",
        "ratingLeft",
        "ratingWidth",
        "rankTop",
        "rankLeft",
        "rankWidth",
        "nameTop",
        "nameLeft",
        "nameWidth",
        "statsTop",
        "statsLeft",
        "statsWidth",
      ].includes(key)
    ) {
      value = pct(value as number);
    }
    if (key === "fontFamily") value = `"${value}", "Arial Narrow", Arial, sans-serif`;
    if (key === "nameSpacing") value = `${value}em`;
    if (key === "statsGap") value = px(value as number);
    style[cssName] = value as string | number;
  });

  const fxIntensity = Number(preset.fxIntensity ?? 0);
  const fxLevel = Math.min(1, Math.max(0, fxIntensity));
  const fxBrightness = 0.75 + fxIntensity * 0.65;
  style["--fx-brightness"] = fxBrightness;
  style["--fx-aura-dim"] = fxLevel * 0.62;
  style["--fx-holo-opacity"] = fxLevel * 0.7;
  style["--fx-holo-bright"] = fxBrightness * 1.12;
  style["--fx-holo-peak"] = fxBrightness * 1.28;
  style["--fx-spark-dim"] = Number(preset.fxSparkOpacity ?? 0) * 0.45;
  return style as CSSProperties;
}

function normalizeCardPlayer(player: CardPlayer) {
  const rows = player.card.rows;
  const state: Record<string, string | number> = {
    ...cardPreset,
    template: player.medal.template || cardPreset.template,
    avatar: String(player.accountId),
    rating: player.card.overall,
    position: player.card.position,
    name: player.name,
    rankIcon: String(player.medal.medal || cardPreset.rankIcon),
    rankStars: String(player.medal.stars || cardPreset.rankStars),
  };

  statKeys.forEach((key, index) => {
    const row = rows[index];
    if (!row) return;
    state[`stat${key}`] = row.value;
    state[`label${key}`] = row.label;
  });

  return state;
}

function handleAvatarError(event: SyntheticEvent<HTMLImageElement>) {
  const img = event.currentTarget;
  const fallback = img.dataset.fallback;
  if (fallback && img.src !== fallback) {
    img.src = fallback;
    img.dataset.fallback = "/assets/players/1.jpg";
  }
}

function formatTime(value: string | null) {
  if (!value) return "Unknown";
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function relativeTime(value: string | null) {
  if (!value) return "Unknown";
  const diffMs = Date.now() - new Date(value).getTime();
  const hours = Math.max(0, Math.round(diffMs / 3_600_000));
  if (hours < 1) return "Just now";
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

function Panel({
  title,
  action,
  children,
  className = "",
}: {
  title: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`} aria-label={title}>
      <header className="panel-header">
        <h2>{title}</h2>
        {action}
      </header>
      {children}
    </section>
  );
}

function Header({ activePage }: { activePage: Page }) {
  return (
    <header className="site-header">
      <a className="brand" href="/dashboard/">
        <span className="brand-mark" aria-hidden="true">
          <span />
          <span />
          <span />
          <span />
        </span>
        <span>KASTEMS HUB</span>
      </a>

      <nav className="nav-links" aria-label="Primary navigation">
        {navItems.map((item) => (
          <a key={item.label} aria-current={item.page === activePage ? "page" : undefined} href={item.href}>
            {item.label}
          </a>
        ))}
      </nav>
    </header>
  );
}

function RankBadge({ rank }: { rank: number }) {
  return <span className={`rank-badge rank-${Math.min(rank, 3)}`}>{rank}</span>;
}

function FormDots({ form }: { form: string[] }) {
  return (
    <div className="form-dots" aria-label={`Form ${form.join("")}`}>
      {form.map((item, index) => (
        <span key={`${item}-${index}`} className={item === "W" ? "form-win" : "form-loss"}>
          {item}
        </span>
      ))}
    </div>
  );
}

function Leaderboard() {
  return (
    <Panel title="Friends Leaderboard" className="leaderboard-panel">
      <div className="leaderboard-head">
        <span>#</span>
        <span>Player</span>
        <span>Record</span>
        <span>Win Rate</span>
        <span>Form</span>
      </div>
      <div className="leaderboard-list">
        {data.leaderboard.map((player: LeaderboardPlayer) => (
          <article className="leaderboard-row" key={player.accountId}>
            <RankBadge rank={player.rank} />
            <div className="player-cell">
              <img className="player-avatar" src={player.avatar ?? ""} alt="" />
              <div>
                <strong>{player.name}</strong>
                <span className="rank-line">
                  {rankIconSrc(playersById.get(player.accountId)?.rankTier) ? (
                    <img src={rankIconSrc(playersById.get(player.accountId)?.rankTier) ?? ""} alt="" />
                  ) : null}
                  {rankLabel(playersById.get(player.accountId)?.rankTier)}
                </span>
              </div>
            </div>
            <strong className="record">
              <span className="record-wins">{player.wins}</span>
              <span className="record-separator">-</span>
              <span className="record-losses">{player.losses}</span>
            </strong>
            <strong className="win-rate">{player.winRate}%</strong>
            <FormDots form={player.form} />
          </article>
        ))}
      </div>
    </Panel>
  );
}

function PartyStack({ game }: { game: RecentGame }) {
  const players = game.trackedPlayers;
  return (
    <div className="party-stack">
      {players.slice(0, 5).map((player, index) => (
        <img
          key={`${game.matchId}-${player.accountId}-${index}`}
          src={player.avatar ?? ""}
          alt={player.name}
          title={`${player.name} · ${player.heroName}`}
        />
      ))}
    </div>
  );
}

function HeroStack({ game }: { game: RecentGame }) {
  return (
    <div className="hero-stack">
      {game.trackedPlayers.slice(0, 5).map((player, index) => (
        <img
          key={`${game.matchId}-${player.accountId}-${player.heroId}-${index}`}
          src={player.heroImage ?? ""}
          alt={player.heroName}
          title={`${player.name} · ${player.heroName}`}
        />
      ))}
    </div>
  );
}

function isRankedGame(game: RecentGame) {
  return game.lobbyTypeName.toLowerCase().includes("ranked") || game.modeName.toLowerCase().includes("ranked");
}

function matchesModeFilter(game: RecentGame, filter: GameModeFilter) {
  const isTurbo = game.modeName.toLowerCase() === "turbo";
  const isRanked = isRankedGame(game);
  if (filter === "turbo") return isTurbo;
  if (filter === "ranked") return isRanked;
  if (filter === "other") return !isTurbo && !isRanked;
  return true;
}

function RecentGames() {
  const [modeFilter, setModeFilter] = useState<GameModeFilter>("all");
  const visibleGames = useMemo(
    () => data.recentPartyGames.filter((game) => matchesModeFilter(game, modeFilter)).slice(0, 20),
    [modeFilter],
  );

  return (
    <Panel
      title="Recent Games"
      className="games-panel"
      action={
        <label className="mode-select" aria-label="Filter recent games by mode">
          <select value={modeFilter} onChange={(event) => setModeFilter(event.target.value as GameModeFilter)}>
            {modeFilters.map((filter) => (
              <option key={filter.value} value={filter.value}>
                {filter.label}
              </option>
            ))}
          </select>
          <ChevronDown aria-hidden="true" />
        </label>
      }
    >
      <div className="games-head">
        <span>Party</span>
        <span>Result</span>
        <span>Mode</span>
        <span>Duration</span>
        <span>Date / Time</span>
        <span>Heroes</span>
      </div>
      <div className="games-list">
        {visibleGames.length ? visibleGames.map((game: RecentGame) => (
          <article className="game-row" key={game.matchId}>
            <PartyStack game={game} />
            <span className={`result-pill ${game.result === "WIN" ? "win" : "loss"}`}>
              {game.result === "WIN" ? "W" : "L"}
            </span>
            <span className="mode-cell">{game.modeName}</span>
            <span>{game.durationLabel}</span>
            <span className="date-cell">
              <strong>{relativeTime(game.startedAt)}</strong>
              <small>{formatTime(game.startedAt)}</small>
            </span>
            <span className="heroes-cell">
              <HeroStack game={game} />
            </span>
          </article>
        )) : <div className="games-empty">No games for this mode</div>}
      </div>
    </Panel>
  );
}

function MetaRow({
  icon,
  label,
  heroName,
  heroImage,
  value,
  tone = "neutral",
}: {
  icon: ReactNode;
  label: string;
  heroName: string | null;
  heroImage?: string | null;
  value: string;
  tone?: "good" | "bad" | "neutral";
}) {
  return (
    <div className="meta-row">
      <span className={`meta-icon ${tone}`}>{icon}</span>
      <span>{label}</span>
      <span className="meta-hero">
        {heroImage ? <img src={heroImage} alt="" /> : null}
        <strong>{heroName ?? "Unknown"}</strong>
      </span>
      <strong className={tone}>{value}</strong>
    </div>
  );
}

function formatHeroMetaValue(hero: { winRate: number; games: number }) {
  return `${hero.winRate}% / ${hero.games} games`;
}

function SquadMeta() {
  const { squadMeta } = data;
  return (
    <Panel title="Squad Meta" className="meta-panel">
      <div className="meta-list">
        <MetaRow
          icon={<Gauge aria-hidden="true" />}
          label="Most Picked Hero"
          heroName={squadMeta.mostPickedHero.heroName}
          heroImage={squadMeta.mostPickedHero.heroImage}
          value={formatHeroMetaValue(squadMeta.mostPickedHero)}
        />
        <MetaRow
          icon={<Crown aria-hidden="true" />}
          label="Best Hero"
          heroName={squadMeta.bestHero.heroName}
          heroImage={squadMeta.bestHero.heroImage}
          value={formatHeroMetaValue(squadMeta.bestHero)}
          tone="good"
        />
        <MetaRow
          icon={<Skull aria-hidden="true" />}
          label="Cursed Hero"
          heroName={squadMeta.cursedHero.heroName}
          heroImage={squadMeta.cursedHero.heroImage}
          value={formatHeroMetaValue(squadMeta.cursedHero)}
          tone="bad"
        />
      </div>
    </Panel>
  );
}

function SquadFeed() {
  return (
    <Panel title="Squad Feed" className="feed-panel">
      <div className="feed-list">
        {data.feed.map((event: FeedEvent) => (
          <article className={`feed-item ${event.type}`} key={`${event.matchId}-${event.accountId}-${event.type}`}>
            <img src={event.avatar ?? ""} alt="" />
            <p>
              <strong>{event.player}</strong>
              <span>{event.message.replace(event.player, "").trim()}</span>
            </p>
            <span className="feed-time">{relativeTime(event.createdAt)}</span>
          </article>
        ))}
      </div>
    </Panel>
  );
}

function DashboardPage() {
  return (
    <>
      <Header activePage="dashboard" />
      <div className="dashboard-grid">
        <Leaderboard />
        <RecentGames />
        <aside className="side-column">
          <SquadMeta />
          <SquadFeed />
        </aside>
      </div>
    </>
  );
}

function PlayersPage() {
  const visiblePlayers = data.players.slice(0, 10);

  return (
    <>
      <Header activePage="players" />
      <section className="players-page" aria-label="Players">
        <div className="players-stage">
          <header className="players-hero">
            <div className="players-title-lines" aria-hidden="true">
              <span />
              <span />
            </div>
            <div className="players-title-copy">
              <h1>PLAYERS</h1>
              <p>LOW-PRIORITY ULTIMATE COLLECTION</p>
            </div>
            <div className="period-toggle" aria-label="Players period">
              <button type="button" aria-pressed="true">This season</button>
              <button type="button" aria-pressed="false">All time</button>
            </div>
          </header>
          <div className="players-roster-frame">
            <div className="players-cards-grid">
              {visiblePlayers.map((player) => (
                <PlayerCard player={player} key={player.accountId} />
              ))}
            </div>
          </div>
        </div>
      </section>
    </>
  );
}

function PlayerCard({ player }: { player: CardPlayer }) {
  const state = normalizeCardPlayer(player);
  const templatePath = `/assets/card-templates/${state.template}_card_transparent.png`;
  const localAvatar = `/assets/players/${state.avatar}.jpg`;
  const remoteAvatar = player.avatar || "/assets/players/1.jpg";
  const stats = statKeys.map((key) => ({
    label: state[`label${key}`],
    value: state[`stat${key}`],
  }));

  return (
    <article className="card-shell" style={cardStyle(state)} aria-label={`${state.name} card`}>
      <div className="player-card">
        <img className="template" src={templatePath} alt="" />
        <div className="avatar-frame">
          <img
            className="avatar"
            src={localAvatar}
            alt={String(state.name)}
            data-fallback={remoteAvatar}
            onError={handleAvatarError}
          />
        </div>
        <img className="frame-fx frame-aura" src={templatePath} alt="" aria-hidden="true" />
        <img className="frame-fx frame-holo" src={templatePath} alt="" aria-hidden="true" />
        <div className="spark-fx" aria-hidden="true" />
        <div className="rating">
          <span className="ovr">{state.rating}</span>
          <span className="position">{state.position}</span>
        </div>
        <span className="rating-rule" aria-hidden="true" />
        <div className="rank-mark" aria-label="Rank mark">
          <img className="rank-stars" src={`/assets/ranks/rank_star_${state.rankStars}.png`} alt="" />
          <img className="rank-icon" src={`/assets/ranks/rank_icon_${state.rankIcon}.png`} alt="" />
        </div>
        <h2 className="name">{state.name}</h2>
        <section className="stats" aria-label="Player stats">
          <div>
            {stats.slice(0, 3).map((stat) => (
              <div className="stat" key={String(stat.label)}>
                <strong>{stat.value}</strong>
                <span>{stat.label}</span>
              </div>
            ))}
          </div>
          <div className="divider" />
          <div>
            {stats.slice(3).map((stat) => (
              <div className="stat" key={String(stat.label)}>
                <strong>{stat.value}</strong>
                <span>{stat.label}</span>
              </div>
            ))}
          </div>
        </section>
      </div>
    </article>
  );
}

function App() {
  const page: Page = window.location.pathname.startsWith("/players") ? "players" : "dashboard";

  return (
    <main className={`dashboard-shell ${page === "players" ? "players-shell" : ""}`}>
      {page === "players" ? <PlayersPage /> : <DashboardPage />}
    </main>
  );
}

const rootElement = document.getElementById("root") as HTMLElement & { dashboardRoot?: Root };
const root = rootElement.dashboardRoot ?? createRoot(rootElement);
rootElement.dashboardRoot = root;

root.render(
  <StrictMode>
    <App />
  </StrictMode>,
);
