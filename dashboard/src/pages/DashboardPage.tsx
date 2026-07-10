import { useMemo, useState, type ReactNode } from "react";
import {
  Activity,
  ChevronDown,
  ChevronRight,
  Crown,
  Eye,
  Frown,
  Gauge,
  Skull,
  TrendingUp,
  Users,
  Zap,
} from "lucide-react";
import {
  data,
  playersById,
  type FeedEvent,
  type GameModeFilter,
  type LeaderboardPlayer,
  type RecentGame,
} from "../data";
import { formatTime, heroPortrait, rankIconSrc, rankLabel, relativeTime } from "../utils/player";
import { Header } from "../components/Header";
import { Panel } from "../components/Panel";

const modeFilters: { label: string; value: GameModeFilter }[] = [
  { label: "All Modes", value: "all" },
  { label: "Turbo", value: "turbo" },
  { label: "Ranked", value: "ranked" },
  { label: "Other", value: "other" },
];

type TrackedGamePlayer = RecentGame["trackedPlayers"][number];

type DuoEntry = { a: TrackedGamePlayer; b: TrackedGamePlayer; games: number; wins: number };

function computeBestDuo() {
  const pairs = new Map<string, DuoEntry>();
  data.recentPartyGames.forEach((game) => {
    const players = game.trackedPlayers;
    for (let i = 0; i < players.length; i += 1) {
      for (let j = i + 1; j < players.length; j += 1) {
        const [a, b] = [players[i], players[j]].sort((x, y) => x.accountId - y.accountId);
        const key = `${a.accountId}-${b.accountId}`;
        const entry = pairs.get(key) ?? { a, b, games: 0, wins: 0 };
        entry.games += 1;
        if (game.result === "WIN") entry.wins += 1;
        pairs.set(key, entry);
      }
    }
  });
  let best: DuoEntry | null = null;
  for (const entry of Array.from(pairs.values())) {
    if (entry.games < 2) continue;
    const rate = entry.wins / entry.games;
    const bestRate = best ? best.wins / best.games : -1;
    if (!best || rate > bestRate || (rate === bestRate && entry.games > best.games)) best = entry;
  }
  return best;
}

const bestDuo = computeBestDuo();

function findHeroImage(heroName: string | null) {
  if (!heroName) return null;
  for (const game of data.recentPartyGames) {
    const hero = game.heroes.find((item) => item.heroName === heroName);
    if (hero) return hero.heroImage;
  }
  return null;
}

function SquadPulse() {
  const { squadPulse } = data;
  return (
    <section className="pulse-bar" aria-label="Squad pulse">
      <div className="pulse-item pulse-label">
        <Activity aria-hidden="true" />
        <span>Squad Pulse</span>
      </div>
      <div className="pulse-item">
        <TrendingUp className={squadPulse.record.wins >= squadPulse.record.losses ? "pulse-good" : "pulse-bad"} aria-hidden="true" />
        <strong>{squadPulse.record.label}</strong>
        <span>this season</span>
      </div>
      <div className="pulse-item">
        <Zap className="pulse-gold" aria-hidden="true" />
        <strong>
          {squadPulse.turboMatches}/{squadPulse.trackedPlayerMatches}
        </strong>
        <span>turbo games</span>
      </div>
      {bestDuo ? (
        <div className="pulse-item">
          <Users className="pulse-good" aria-hidden="true" />
          <span>Best duo:</span>
          <span className="pulse-duo">
            <img src={bestDuo.a.avatar ?? ""} alt="" />
            <img src={bestDuo.b.avatar ?? ""} alt="" />
          </span>
          <strong>
            {bestDuo.a.name} + {bestDuo.b.name}
          </strong>
          <span>
            {Math.round((bestDuo.wins / bestDuo.games) * 100)}% of {bestDuo.games}
          </span>
        </div>
      ) : (
        <div className="pulse-item">
          <Crown className="pulse-gold" aria-hidden="true" />
          <span>On fire:</span>
          <strong>{squadPulse.bestPerformer.name}</strong>
          <span>{squadPulse.bestPerformer.winRate}% WR</span>
        </div>
      )}
      <div className="pulse-item">
        <Frown className="pulse-bad" aria-hidden="true" />
        <span>Cursed pick:</span>
        {squadPulse.cursedPick.heroImage ? (
          <img className="pulse-hero" src={heroPortrait(squadPulse.cursedPick.heroImage) ?? ""} alt="" />
        ) : null}
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
              <img className="player-avatar" src={player.avatar ?? ""} alt="" />
              <div>
                <strong>{player.name}</strong>
                <span className="rank-line">
                  {rankIconSrc(playersById.get(player.accountId)?.rankTier) ? (
                    <img src={rankIconSrc(playersById.get(player.accountId)?.rankTier) ?? ""} alt="" />
                  ) : null}
                  {rankLabel(playersById.get(player.accountId)?.rankTier)}
                  <span className="rank-kda">· KDA {player.kda}</span>
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
      <a className="panel-footer" href="/players/">
        View all players
        <ChevronRight aria-hidden="true" />
      </a>
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

function GameHighlight({ game }: { game: RecentGame }) {
  const highlight = game.highlight;
  if (!highlight) return <span className="highlight-cell highlight-empty">—</span>;
  const won = highlight.won;
  return (
    <span className="highlight-cell">
      <img className="highlight-hero" src={heroPortrait(highlight.heroImage) ?? ""} alt={highlight.heroName} />
      <span className="highlight-copy">
        <strong>{highlight.name}</strong>
        <small>
          {highlight.kills}/{highlight.deaths}/{highlight.assists} · {highlight.heroName}
        </small>
      </span>
      {won ? <Crown className="highlight-badge" aria-label="MVP" /> : null}
    </span>
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
        <span>Highlight</span>
      </div>
      <div className="games-list">
        {visibleGames.length ? visibleGames.map((game: RecentGame) => (
          <article className="game-row" key={game.matchId}>
            <PartyStack game={game} />
            <span className={`result-pill ${game.result === "WIN" ? "win" : "loss"}`}>
              {game.result === "WIN" ? "W" : "L"}
            </span>
            <span className="mode-cell">{game.modeName}</span>
            <span className="duration-cell">{game.durationLabel}</span>
            <span className="date-cell">
              <strong>{relativeTime(game.startedAt)}</strong>
              <small>{formatTime(game.startedAt)}</small>
            </span>
            <GameHighlight game={game} />
          </article>
        )) : <div className="games-empty">No games for this mode</div>}
      </div>
      <a className="panel-footer" href="/dashboard/">
        View all party games
        <ChevronRight aria-hidden="true" />
      </a>
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
  tone?: "good" | "bad" | "gold" | "neutral";
}) {
  return (
    <div className="meta-row">
      <span className={`meta-icon ${tone}`}>{icon}</span>
      <span>{label}</span>
      <span className="meta-hero">
        {heroImage ? <img src={heroPortrait(heroImage) ?? ""} alt="" /> : null}
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
          label="Most Picked"
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
        <MetaRow
          icon={<Zap aria-hidden="true" />}
          label="Fastest Win"
          heroName={squadMeta.fastestWin.heroName}
          heroImage={findHeroImage(squadMeta.fastestWin.heroName)}
          value={squadMeta.fastestWin.durationLabel}
          tone="gold"
        />
      </div>
    </Panel>
  );
}

const feedIcons: Record<string, { icon: ReactNode; tone: string }> = {
  crown: { icon: <Crown aria-hidden="true" />, tone: "gold" },
  skull: { icon: <Skull aria-hidden="true" />, tone: "bad" },
  eye: { icon: <Eye aria-hidden="true" />, tone: "good" },
};

function SquadFeed() {
  return (
    <Panel title="Squad Feed" className="feed-panel">
      <div className="feed-list">
        {data.feed.map((event: FeedEvent) => {
          const feedIcon = feedIcons[event.icon] ?? feedIcons.eye;
          return (
            <article className={`feed-item ${event.type}`} key={`${event.matchId}-${event.accountId}-${event.type}`}>
              <img src={event.avatar ?? ""} alt="" />
              <p>
                <strong>{event.player}</strong>
                <span>{event.message.replace(event.player, "").trim()}</span>
              </p>
              <span className="feed-meta">
                <span className="feed-time">{relativeTime(event.createdAt)}</span>
                <span className={`feed-icon ${feedIcon.tone}`}>{feedIcon.icon}</span>
              </span>
            </article>
          );
        })}
      </div>
    </Panel>
  );
}

export function DashboardPage() {
  return (
    <>
      <Header activePage="dashboard" />
      <SquadPulse />
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
