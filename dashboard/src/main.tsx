import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  ChevronDown,
  ChevronRight,
  Crown,
  Eye,
  Flame,
  Gauge,
  HeartPulse,
  Shield,
  ShieldAlert,
  Skull,
  Swords,
  Trophy,
  Zap,
} from "lucide-react";
import dashboardData from "../../data/dashboard.json";
import "./styles.css";

type DashboardData = typeof dashboardData;
type LeaderboardPlayer = DashboardData["leaderboard"][number];
type RecentGame = DashboardData["recentPartyGames"][number];
type FeedEvent = DashboardData["feed"][number];

const data = dashboardData as DashboardData;

const navItems = ["Dashboard", "Players", "Matches", "Achievements", "Hall of Fame"];

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

function eventIcon(event: FeedEvent) {
  if (event.icon === "skull") return <Skull aria-hidden="true" />;
  if (event.icon === "crown") return <Crown aria-hidden="true" />;
  return <Eye aria-hidden="true" />;
}

function Panel({
  title,
  action,
  children,
  className = "",
}: {
  title: string;
  action?: React.ReactNode;
  children: React.ReactNode;
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
        <span className="brand-mark">
          <Swords aria-hidden="true" />
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

      <button className="season-button" type="button">
        <Shield aria-hidden="true" />
        <span>Season 1</span>
        <ChevronDown aria-hidden="true" />
      </button>
    </header>
  );
}

function SquadPulse() {
  const { squadPulse } = data;
  return (
    <section className="pulse-strip" aria-label="Squad pulse">
      <div className="pulse-label">
        <HeartPulse aria-hidden="true" />
        <span>Squad Pulse</span>
      </div>
      <div className="pulse-item win">
        <Activity aria-hidden="true" />
        <strong>{squadPulse.record.label}</strong>
        <span>last {squadPulse.trackedPlayerMatches} player games</span>
      </div>
      <div className="pulse-item">
        <Zap aria-hidden="true" />
        <strong>{squadPulse.turboMatches}</strong>
        <span>turbo entries</span>
      </div>
      <div className="pulse-item">
        <Trophy aria-hidden="true" />
        <span>Best form:</span>
        <strong>{squadPulse.bestPerformer?.name ?? "Unknown"}</strong>
      </div>
      <div className="pulse-item danger">
        <ShieldAlert aria-hidden="true" />
        <span>Cursed pick:</span>
        <strong>{squadPulse.cursedPick.heroName}</strong>
      </div>
    </section>
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
              <img src={player.avatar ?? ""} alt="" />
              <div>
                <strong>{player.name}</strong>
                <span>KDA {player.kda} · {player.matches} games</span>
              </div>
            </div>
            <strong className="record">
              {player.wins}-{player.losses}
            </strong>
            <strong className={player.winRate >= 55 ? "good" : "bad"}>{player.winRate}%</strong>
            <FormDots form={player.form} />
          </article>
        ))}
      </div>
      <button className="panel-link" type="button">
        <span>View all players</span>
        <ChevronRight aria-hidden="true" />
      </button>
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

function RecentGames() {
  return (
    <Panel
      title="Recent Party Games"
      className="games-panel"
      action={
        <button className="mode-button" type="button">
          <span>All Modes</span>
          <ChevronDown aria-hidden="true" />
        </button>
      }
    >
      <div className="games-head">
        <span>Party</span>
        <span>Result</span>
        <span>Mode</span>
        <span>Duration</span>
        <span>Date / Time</span>
        <span>Highlight</span>
      </div>
      <div className="games-list">
        {data.recentPartyGames.slice(0, 6).map((game: RecentGame) => (
          <article className="game-row" key={game.matchId}>
            <PartyStack game={game} />
            <span className={`result-pill ${game.result === "WIN" ? "win" : "loss"}`}>{game.result}</span>
            <span className="mode-cell">{game.modeName}</span>
            <span>{game.durationLabel}</span>
            <span className="date-cell">
              <strong>{relativeTime(game.startedAt)}</strong>
              <small>{formatTime(game.startedAt)}</small>
            </span>
            <span className="highlight-cell">
              <strong>{game.highlight?.name ?? "Unknown"}</strong>
              <small>
                {game.highlight
                  ? `${game.highlight.kills}/${game.highlight.deaths}/${game.highlight.assists}`
                  : "No stats"}
              </small>
            </span>
          </article>
        ))}
      </div>
      <button className="panel-link" type="button">
        <span>View all party games</span>
        <ChevronRight aria-hidden="true" />
      </button>
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
  icon: React.ReactNode;
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
          value={`${squadMeta.mostPickedHero.games} picks`}
        />
        <MetaRow
          icon={<Crown aria-hidden="true" />}
          label="Best Hero"
          heroName={squadMeta.bestHero.heroName}
          heroImage={squadMeta.bestHero.heroImage}
          value={`${squadMeta.bestHero.winRate}%`}
          tone="good"
        />
        <MetaRow
          icon={<Skull aria-hidden="true" />}
          label="Cursed Hero"
          heroName={squadMeta.cursedHero.heroName}
          heroImage={squadMeta.cursedHero.heroImage}
          value={`${squadMeta.cursedHero.winRate}%`}
          tone="bad"
        />
        <MetaRow
          icon={<Zap aria-hidden="true" />}
          label="Fastest Win"
          heroName={squadMeta.fastestWin.heroName}
          value={squadMeta.fastestWin.durationLabel}
          tone="good"
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
            <p>{event.message}</p>
            <span className="feed-time">{relativeTime(event.createdAt)}</span>
            <span className="feed-icon">{eventIcon(event)}</span>
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
      <SquadPulse />
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

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
