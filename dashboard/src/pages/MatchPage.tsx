import { Shield } from "lucide-react";
import { Header } from "../components/Header";
import { matchesById, type MatchDetail, type MatchPlayer } from "../data";

const number = new Intl.NumberFormat("en-US");

function formatClock(seconds: number | null) {
  if (seconds === null || seconds < 0) return "—";
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(seconds % 60).padStart(2, "0")}`;
}

function signed(value: number | null) {
  if (value === null) return "—";
  return `${value > 0 ? "+" : ""}${value}`;
}

function kdaLabel(player: MatchPlayer) {
  return ((player.kills + player.assists) / Math.max(1, player.deaths)).toFixed(1);
}

function impactTone(value: number | null) {
  if (value === null) return "neutral";
  if (value >= 75) return "elite";
  if (value >= 60) return "good";
  if (value < 40) return "bad";
  return "neutral";
}

function impactTitle(player: MatchPlayer) {
  if (!player.impactAxes) return player.tracked ? "KASTEMS match impact" : undefined;
  return Object.entries(player.impactAxes)
    .map(([axis, value]) => `${axis}: ${Math.round(Number(value))}`)
    .join(" · ");
}

function ItemStrip({ player }: { player: MatchPlayer }) {
  const slots = Array.from({ length: 6 }, (_, index) => player.items[index] ?? null);
  return (
    <span className="match-items">
      {slots.map((item, index) => item?.image ? (
        <img key={`${item.id}-${index}`} src={item.image} alt={item.name} title={item.name} />
      ) : (
        <span className="match-item-empty" key={`empty-${index}`} title={item?.name} />
      ))}
      {player.neutralItem?.image ? (
        <img className="neutral" src={player.neutralItem.image} alt={player.neutralItem.name} title={`Neutral: ${player.neutralItem.name}`} />
      ) : (
        <span className="match-item-empty neutral" />
      )}
    </span>
  );
}

function ScoreRow({ player }: { player: MatchPlayer }) {
  return (
    <div className={`match-score-row ${player.tracked ? "tracked" : ""}`}>
      <span className="match-player-cell">
        {player.heroImage ? <img src={player.heroImage} alt="" /> : <span className="hero-placeholder" />}
        <span>
          <strong>{player.name}</strong>
          <small>{player.heroName}{player.position ? ` · ${player.position}` : ""}</small>
        </span>
      </span>
      <span>{player.kills}</span>
      <span>{player.deaths}</span>
      <span>{player.assists}</span>
      <span className="kda-value">{kdaLabel(player)}</span>
      <strong className="net-worth">{number.format(player.netWorth)}</strong>
      <span>{player.lastHits} / {player.denies}</span>
      <span>{player.gpm}</span>
      <span>{player.xpm}</span>
      <span>{number.format(player.heroDamage)}</span>
      {player.heroHealing ? <span>{number.format(player.heroHealing)}</span> : <span className="muted-value">—</span>}
      {player.towerDamage ? <span>{number.format(player.towerDamage)}</span> : <span className="muted-value">—</span>}
      <ItemStrip player={player} />
      <strong className={`impact-value ${impactTone(player.impact)}`} title={impactTitle(player)}>{player.impact ?? "—"}</strong>
      <strong className={player.mmrChange === null ? "muted-value" : player.mmrChange >= 0 ? "mmr-up" : "mmr-down"}>
        {signed(player.mmrChange)}
      </strong>
    </div>
  );
}

function TeamSide({ label, won }: { label: "radiant" | "dire"; won: boolean }) {
  return (
    <section className={`team-side ${label}`}>
      <div className="team-title">
        <strong>{label.toUpperCase()}</strong>
        <b className={`result-badge ${won ? "win" : "loss"}`}>{won ? "VICTORY" : "DEFEATED"}</b>
      </div>
    </section>
  );
}

function MatchHero({ match }: { match: MatchDetail }) {
  return (
    <section className="match-hero-panel">
      <TeamSide label="radiant" won={match.radiantWin} />
      <div className="match-result">
        <span className="result-mode">{match.gameModeName} · {match.lobbyTypeName}</span>
        <div className="result-score">
          <b className="radiant">{match.radiantScore}</b>
          <i>—</i>
          <b className="dire">{match.direScore}</b>
        </div>
        <span className="result-sub">{match.durationLabel} · FIRST BLOOD {formatClock(match.firstBloodTime)}</span>
      </div>
      <TeamSide label="dire" won={!match.radiantWin} />
    </section>
  );
}

function Scoreboard({ match }: { match: MatchDetail }) {
  const radiant = match.scoreboard.filter((player) => player.team === "radiant");
  const dire = match.scoreboard.filter((player) => player.team === "dire");
  return (
    <section className="match-scoreboard panel">
      <header><h2>SCOREBOARD</h2></header>
      <div className="match-table-scroll">
        <div className="match-score-grid">
          <div className="match-score-head">
            <span>PLAYER</span><span>K</span><span>D</span><span>A</span><span>KDA</span><span>NET</span><span>LH / DN</span><span>GPM</span><span>XPM</span><span>DMG</span><span>HEAL</span><span>BLD</span><span>ITEMS</span><span>IMPACT</span><span>MMR CHANGE</span>
          </div>
          <div className="match-team-divider radiant">RADIANT</div>
          {radiant.map((player) => <ScoreRow key={player.playerSlot} player={player} />)}
          <div className="match-team-divider dire">DIRE</div>
          {dire.map((player) => <ScoreRow key={player.playerSlot} player={player} />)}
        </div>
      </div>
    </section>
  );
}

const performerDefs: { label: string; unit: string; tone: string; pick: (player: MatchPlayer) => number }[] = [
  { label: "MOST KILLS", unit: "KILLS", tone: "", pick: (player) => player.kills },
  { label: "MOST DAMAGE", unit: "DAMAGE", tone: "", pick: (player) => player.heroDamage },
  { label: "MOST HEALING", unit: "HEALING", tone: "heal", pick: (player) => player.heroHealing },
  { label: "MOST NET WORTH", unit: "NET WORTH", tone: "gold", pick: (player) => player.netWorth },
  { label: "MOST DEATHS", unit: "DEATHS", tone: "bad", pick: (player) => player.deaths },
];

function TopPerformers({ match }: { match: MatchDetail }) {
  if (!match.scoreboard.length) return null;
  const cards = performerDefs
    .map((def) => {
      const player = match.scoreboard.reduce((best, next) => (def.pick(next) > def.pick(best) ? next : best));
      return { ...def, player, value: def.pick(player) };
    })
    .filter((card) => card.value > 0);
  return (
    <aside className="match-performers panel">
      <h2>TOP PERFORMERS</h2>
      <div className="performer-list">
        {cards.map((card) => (
          <div className={`performer-card ${card.player.tracked ? "tracked" : ""}`} key={card.label}>
            {card.player.heroImage ? <img src={card.player.heroImage} alt={card.player.heroName} /> : <span className="hero-empty" />}
            <div>
              <small>{card.label}</small>
              <strong>{card.player.name}</strong>
              <b className={card.tone}>{number.format(card.value)}<span>{card.unit}</span></b>
            </div>
          </div>
        ))}
      </div>
    </aside>
  );
}

export function MatchPage() {
  const matchId = window.location.pathname.match(/^\/matches\/(\d+)/)?.[1];
  const match = matchId ? matchesById.get(matchId) : undefined;
  return (
    <>
      <Header activePage="match" />
      <div className="match-page">
        <div className="match-topbar">
          <div className="match-breadcrumb"><strong>MATCH #{matchId ?? "UNKNOWN"}</strong></div>
          {match ? (
            <a className="opendota-link topbar-opendota" href={`https://www.opendota.com/matches/${match.matchId}`} target="_blank" rel="noreferrer">OPEN IN OPENDOTA</a>
          ) : null}
        </div>
        {match ? (
          <>
            <MatchHero match={match} />
            <div className="match-content"><Scoreboard match={match} /><TopPerformers match={match} /></div>
          </>
        ) : (
          <section className="match-missing panel"><Shield aria-hidden="true" /><h1>Match not found</h1><p>This match is outside the current recent-game cache.</p><a href="/dashboard/">BACK TO DASHBOARD</a></section>
        )}
      </div>
    </>
  );
}
