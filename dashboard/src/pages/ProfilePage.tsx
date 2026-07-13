import { useEffect, useMemo, useState } from "react";
import { Settings, Shield } from "lucide-react";
import { data, defaultProfileAccountId, playersById } from "../data";
import { useAuthUser } from "../auth/useAuthUser";
import { Header } from "../components/Header";
import { heroPortrait, rankLabel, relativeTime } from "../utils/player";

type ShowcaseStat = "mmr" | "wins" | "matches" | "firstMatch";
type ProfileOverride = { matches?: number; firstMatchAt?: string; showcase?: ShowcaseStat[] };
type ProfileDraft = { matches: number; firstMatchAt: string; showcase: [ShowcaseStat, ShowcaseStat] };
type ProfileTab = "activity" | "games";

const showcaseOptions: { value: ShowcaseStat; label: string }[] = [
  { value: "mmr", label: "MMR" },
  { value: "wins", label: "Wins" },
  { value: "matches", label: "Matches" },
  { value: "firstMatch", label: "First Match" },
];

const gameDateFormat = new Intl.DateTimeFormat("en-US", { month: "numeric", day: "numeric", year: "numeric" });
const gameTimeFormat = new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit" });

function profileDate(value: string | null | undefined) {
  if (!value) return "Unknown";
  return new Intl.DateTimeFormat("en", { day: "numeric", month: "short", year: "numeric" }).format(new Date(value));
}

function profileInputDate(value: string | null | undefined) {
  return value ? value.slice(0, 10) : "";
}

function gameDateParts(value: string | null) {
  if (!value) return { date: "—", time: "" };
  const parsed = new Date(value);
  return { date: gameDateFormat.format(parsed), time: gameTimeFormat.format(parsed) };
}

function gameTypeLabel(game: { modeName: string; lobbyTypeName: string }) {
  const lobby = game.lobbyTypeName.toLowerCase();
  if (lobby.includes("ranked")) return "Ranked";
  if (game.modeName === "Turbo") return "Turbo";
  if (lobby === "normal") return "Unranked";
  return game.lobbyTypeName;
}

type RadarAxis = { label: string; value: number };

const CARD_RATING_FLOOR = 35;

function cardRatingToRadar(value: number) {
  // Card ratings start well above zero. Remove that built-in floor, then use a
  // gentle curve so mid-card values look modest without flattening 90+ stats.
  const normalized = Math.max(0, Math.min(1, (value - CARD_RATING_FLOOR) / (99 - CARD_RATING_FLOOR)));
  return Math.round(100 * normalized ** 1.35);
}

function PlayStyleRadar({ axes }: { axes: RadarAxis[] }) {
  const point = (index: number, radius: number) => {
    const angle = -Math.PI / 2 + (index * 2 * Math.PI) / axes.length;
    return [100 + Math.cos(angle) * radius, 102 + Math.sin(angle) * radius] as const;
  };
  const ring = (radius: number) =>
    axes.map((_, index) => point(index, radius).map((value) => value.toFixed(1)).join(",")).join(" ");
  const valuePoints = axes.map((axis, index) => point(index, 76 * Math.max(0.07, axis.value / 100)));
  const values = valuePoints.map((p) => p.map((value) => value.toFixed(1)).join(",")).join(" ");
  return (
    <div className="rp-radar">
      <svg viewBox="0 0 200 200" role="img" aria-label="Play style radar">
        <defs>
          <radialGradient id="rp-radar-heat" cx="50%" cy="50%" r="70%">
            <stop offset="0%" stopColor="rgba(244, 92, 22, 0.5)" />
            <stop offset="32%" stopColor="rgba(205, 88, 26, 0.26)" />
            <stop offset="70%" stopColor="rgba(165, 80, 26, 0.1)" />
            <stop offset="100%" stopColor="rgba(140, 72, 24, 0.04)" />
          </radialGradient>
        </defs>
        {axes.map((axis, index) => {
          const [x, y] = point(index, 76);
          return <line key={axis.label} className="rp-radar-spoke" x1="100" y1="102" x2={x} y2={y} />;
        })}
        <polygon className="rp-radar-grid" points={ring(76)} />
        <polygon className="rp-radar-grid" points={ring(7)} />
        <polygon className="rp-radar-value" points={values} />
        {valuePoints.map(([x, y], index) => (
          <circle key={axes[index].label} className="rp-radar-dot" cx={x.toFixed(1)} cy={y.toFixed(1)} r="2.4" />
        ))}
      </svg>
      {axes.map((axis, index) => {
        const [x, y] = point(index, 93);
        return (
          <span key={axis.label} className="rp-radar-label" style={{ left: `${x / 2}%`, top: `${y / 2}%` }}>
            {axis.label}
          </span>
        );
      })}
    </div>
  );
}

export function ProfilePage() {
  const { authUser, resolved: authResolved } = useAuthUser();
  const pathAccountId = window.location.pathname.match(/^\/profile\/(\d+)/)?.[1];
  const requestedAccountId = Number(pathAccountId);
  const hasValidPathAccountId = Number.isFinite(requestedAccountId) && playersById.has(requestedAccountId);
  const accountId = hasValidPathAccountId
    ? requestedAccountId
    : Number(authUser?.accountId ?? defaultProfileAccountId);
  const player = playersById.get(accountId) ?? data.players[0];
  const [overrides, setOverrides] = useState<ProfileOverride>({});
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [tab, setTab] = useState<ProfileTab>("games");
  const baseFirstMatch = profileInputDate(player.profile.firstMatchAt);
  const [draft, setDraft] = useState<ProfileDraft>({ matches: 0, firstMatchAt: baseFirstMatch, showcase: ["mmr", "wins"] });

  useEffect(() => {
    if (!authResolved || hasValidPathAccountId) return;
    const canonicalAccountId = Number(authUser?.accountId ?? defaultProfileAccountId);
    window.location.replace(`/profile/${canonicalAccountId}`);
  }, [authResolved, authUser?.accountId, hasValidPathAccountId]);

  useEffect(() => {
    setEditing(false);
    fetch(`/api/profiles/${player.accountId}`)
      .then((response) => response.ok ? response.json() : null)
      .then((payload) => setOverrides(payload?.overrides ?? {}))
      .catch(() => setOverrides({}));
  }, [player.accountId]);

  const values: Record<ShowcaseStat, string> = {
    mmr: Math.round(player.computedMmr ?? 3000).toLocaleString("en-US"),
    wins: player.wins.toLocaleString("en-US"),
    matches: (overrides.matches ?? player.matches).toLocaleString("en-US"),
    firstMatch: profileDate(overrides.firstMatchAt ?? baseFirstMatch),
  };
  const showcase: [ShowcaseStat, ShowcaseStat] = overrides.showcase?.length === 2
    ? [overrides.showcase[0], overrides.showcase[1]]
    : ["mmr", "wins"];
  const isOwner = String(authUser?.accountId ?? "") === String(player.accountId);
  const statLabel = (stat: ShowcaseStat) => showcaseOptions.find((option) => option.value === stat)?.label ?? stat;

  const beginEdit = () => {
    setDraft({
      matches: overrides.matches ?? player.matches,
      firstMatchAt: overrides.firstMatchAt ?? baseFirstMatch,
      showcase: [...showcase],
    });
    setEditing(true);
  };

  const changeShowcase = (slot: number, value: ShowcaseStat) => {
    setDraft((current) => {
      const next = [...current.showcase] as [ShowcaseStat, ShowcaseStat];
      const other = slot === 0 ? 1 : 0;
      if (next[other] === value) next[other] = next[slot];
      next[slot] = value;
      return { ...current, showcase: next };
    });
  };

  const saveProfile = async () => {
    setSaving(true);
    try {
      const response = await fetch("/api/profile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(draft),
      });
      const payload = await response.json();
      if (response.ok) {
        setOverrides(payload.overrides);
        setEditing(false);
      }
    } finally {
      setSaving(false);
    }
  };

  // VERSATILITY reflects hero-pool density in the recent games, not a card stat:
  // spamming 2-3 heroes keeps it low, a wide pool pushes it toward 100.
  const radarAxes = useMemo(() => {
    const byKey = new Map(player.card.rows.map((row) => [row.label, row.value]));
    const games = player.profile.recentGames.slice(0, 20);
    const uniqueHeroes = new Set(games.map((game) => game.heroName)).size;
    const versatility = games.length ? Math.round((uniqueHeroes / games.length) * 100) : 50;
    return [
      { label: "FIGHTING", value: cardRatingToRadar(byKey.get("FGT") ?? CARD_RATING_FLOOR) },
      { label: "FARMING", value: cardRatingToRadar(byKey.get("FRM") ?? CARD_RATING_FLOOR) },
      { label: "SUPPORTING", value: cardRatingToRadar(byKey.get("UTL") ?? CARD_RATING_FLOOR) },
      { label: "PUSHING", value: cardRatingToRadar(byKey.get("OBJ") ?? CARD_RATING_FLOOR) },
      { label: "VERSATILITY", value: versatility },
    ];
  }, [player]);

  const heroImageByMatch = useMemo(
    () => new Map(player.profile.recentGames.map((game) => [game.matchId, game.heroImage])),
    [player],
  );

  const draftValue = (stat: ShowcaseStat, slot: number) => {
    if (stat === "mmr") {
      return <strong key={slot}>{values.mmr}</strong>;
    }
    if (stat === "matches") {
      return <input type="number" min={0} value={draft.matches} onChange={(event) => setDraft({ ...draft, matches: Number(event.target.value) })} aria-label="Matches" />;
    }
    if (stat === "firstMatch") {
      return <input type="date" value={draft.firstMatchAt} onChange={(event) => setDraft({ ...draft, firstMatchAt: event.target.value })} aria-label="First match date" />;
    }
    return <strong key={slot}>{values.wins}</strong>;
  };

  return (
    <>
      <Header activePage="profile" />
      <section className="rp-page" aria-label={`${player.name} profile`}>
        <nav className="rp-crumbs" aria-label="Profile sections">
          <strong>PROFILE</strong>
          <span>/</span>
          <span>TROPHIES</span>
          <span>/</span>
          <span>TICKETS</span>
        </nav>

        <header className="rp-identity">
          <div className="rp-identity-main">
            <img className="rp-identity-avatar" src={player.avatar ?? "/assets/players/1.jpg"} alt="" />
            <h1>{player.name}</h1>
          </div>
          <div className="rp-identity-stats">
            <div className="rp-stat">
              <span>MMR</span>
              <strong>{values.mmr}</strong>
            </div>
          </div>
          <div className="rp-identity-meta">
            {isOwner ? (
              editing ? (
                <button className="rp-btn rp-btn-save" type="button" onClick={saveProfile} disabled={saving}>
                  ✓ SAVE CHANGES
                </button>
              ) : (
                <button className="rp-btn" type="button" onClick={beginEdit}>EDIT PROFILE</button>
              )
            ) : null}
            <span className="rp-friend-id">
              <Shield aria-hidden="true" />
              FRIEND ID: <strong>{player.accountId}</strong>
            </span>
          </div>
        </header>

        <div className="rp-columns">
          <div className="rp-left">
            <div className="rp-showcase" aria-label="Profile showcase">
              <div className="rp-slot" />
              <div className="rp-slot" />
              <div className="rp-slot" />
              <div className="rp-badge" title={rankLabel(player.rankTier)}>
                <img src={`/assets/ranks/rank_icon_${player.medal.medal || 1}.png`} alt={rankLabel(player.rankTier)} />
                <span className="rp-badge-level">{player.card.overall}</span>
              </div>
            </div>

            <section className="rp-panel rp-playstyle" aria-label="Play style">
              <div className="rp-playstyle-grid">
                <div className="rp-playstyle-left">
                  <h3>PLAY STYLE</h3>
                  <small>MOST RECENT {player.card.source.games} GAME(S)</small>
                  <PlayStyleRadar axes={radarAxes} />
                </div>
                <div className="rp-lifetime">
                  <h3>LIFETIME STATS</h3>
                  <ul>
                    <li><b>{Math.round(player.card.source.avgGpm)}</b><span>Avg GPM</span></li>
                    <li><b>{Math.round(player.card.source.avgXpm)}</b><span>Avg XPM</span></li>
                    <li><b>{Math.round(player.card.source.avgLastHits)}</b><span>Avg Last Hits</span></li>
                    <li className="rp-lifetime-divider" aria-hidden="true" />
                    <li><b>{player.wins.toLocaleString("en-US")}</b><span>Wins</span></li>
                    <li><b>{player.losses.toLocaleString("en-US")}</b><span>Losses</span></li>
                    <li><b>{player.kills.toLocaleString("en-US")}</b><span>Total Kills</span></li>
                    <li><b>{player.deaths.toLocaleString("en-US")}</b><span>Total Deaths</span></li>
                    <li><b>{player.assists.toLocaleString("en-US")}</b><span>Total Assists</span></li>
                    <li><b>{player.kda}</b><span>KDA</span></li>
                    <li><b>{player.winRate}%</b><span>Win Rate</span></li>
                  </ul>
                </div>
              </div>
              <footer className="rp-compare">
                <span className="rp-legend"><i aria-hidden="true" />{player.name}</span>
              </footer>
            </section>
          </div>

          <div className="rp-history">
            <nav className="rp-tabs" aria-label="Profile history">
              <button type="button" aria-pressed={tab === "activity"} onClick={() => setTab("activity")}>ACTIVITY FEED</button>
              <span>/</span>
              <button type="button" aria-pressed={tab === "games"} onClick={() => setTab("games")}>RECENT GAMES</button>
              <span>/</span>
              <button type="button" disabled title="Coming soon">ALL-HERO CHALLENGE</button>
            </nav>
            <div className="rp-panel rp-history-panel">
              {tab === "games" ? (
                <>
                  <div className="rp-games-head">
                    <span>DATE / TIME</span>
                    <span>HERO PLAYED</span>
                    <span>MMR</span>
                    <span>DURATION</span>
                    <span>TYPE</span>
                    <Settings aria-hidden="true" />
                  </div>
                  <div className="rp-games-body">
                    {player.profile.recentGames.length ? (
                      player.profile.recentGames.slice(0, 20).map((game) => {
                        const started = gameDateParts(game.startedAt);
                        return (
                          <article className="rp-game-row" key={game.matchId}>
                            <span className="rp-game-date">
                              {started.date}
                              <em>{started.time}</em>
                            </span>
                            <span className="rp-game-hero">
                              {game.heroImage ? <img src={heroPortrait(game.heroImage) ?? ""} alt="" /> : null}
                              <b>{game.heroName}</b>
                            </span>
                            <span className="rp-game-result">
                              {game.mmrAfter !== null ? (
                                <b className={game.mmrChange >= 0 ? "rp-mmr-gain" : "rp-mmr-loss"}>
                                  {game.mmrAfter.toLocaleString("en-US")} ({game.mmrChange >= 0 ? "+" : ""}{game.mmrChange})
                                </b>
                              ) : (
                                <b className={game.result === "WIN" ? "rp-win" : "rp-loss"} title="Unrated match">
                                  {game.result === "WIN" ? "Win" : "Loss"}
                                </b>
                              )}
                            </span>
                            <span className="rp-game-duration">{game.durationLabel}</span>
                            <span>{gameTypeLabel(game)}</span>
                          </article>
                        );
                      })
                    ) : (
                      <p className="rp-empty">No recent games recorded for this player yet.</p>
                    )}
                  </div>
                </>
              ) : (
                <div className="rp-games-body rp-activity">
                  {player.profile.activityFeed.length ? (
                    player.profile.activityFeed.map((event) => {
                      const heroImage = heroImageByMatch.get(event.matchId);
                      return (
                        <article className="rp-activity-row" key={`${event.matchId}-${event.type}`}>
                          {heroImage ? (
                            <img className="rp-activity-hero" src={heroPortrait(heroImage) ?? ""} alt="" />
                          ) : (
                            <span className={`rp-activity-icon ${event.icon}`}>◆</span>
                          )}
                          <p>
                            {event.message}
                            <small>
                              {event.stats.kills}/{event.stats.deaths}/{event.stats.assists} · {relativeTime(event.createdAt)}
                            </small>
                          </p>
                        </article>
                      );
                    })
                  ) : (
                    <p className="rp-empty">No squad-feed events for this player yet.</p>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </section>
    </>
  );
}
