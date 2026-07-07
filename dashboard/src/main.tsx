import { StrictMode, useMemo, useState, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import {
  ChevronDown,
  Crown,
  Gauge,
  Skull,
  Zap,
} from "lucide-react";
import dashboardData from "../../data/dashboard.json";
import "./styles.css";

type DashboardData = typeof dashboardData;
type LeaderboardPlayer = DashboardData["leaderboard"][number];
type RecentGame = DashboardData["recentPartyGames"][number];
type FeedEvent = DashboardData["feed"][number];
type GameModeFilter = "all" | "turbo" | "ranked" | "other";

const data = dashboardData as DashboardData;
const playersById = new Map(data.players.map((player) => [player.accountId, player]));

const navItems = ["Dashboard", "Players", "Matches", "Achievements", "Hall of Fame"];
const modeFilters: { label: string; value: GameModeFilter }[] = [
  { label: "All Modes", value: "all" },
  { label: "Turbo", value: "turbo" },
  { label: "Ranked", value: "ranked" },
  { label: "Other", value: "other" },
];
const rankNames = ["Unranked", "Herald", "Guardian", "Crusader", "Archon", "Legend", "Ancient", "Divine", "Immortal"];
const rankStars = ["", "I", "II", "III", "IV", "V"];

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

function Header() {
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
          <a key={item} aria-current={item === "Dashboard" ? "page" : undefined} href="/dashboard/">
            {item}
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

function App() {
  return (
    <main className="dashboard-shell">
      <Header />
      <div className="dashboard-grid">
        <Leaderboard />
        <RecentGames />
        <aside className="side-column">
          <SquadMeta />
          <SquadFeed />
        </aside>
      </div>
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
