import {
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type MouseEvent,
} from "react";
import { data, type CardPlayer } from "../data";
import {
  cardStyle,
  handleAvatarError,
  normalizeCardPlayer,
  statKeys,
} from "../utils/player";
import { Header } from "../components/Header";

export function PlayersPage() {
  const [period, setPeriod] = useState<"season" | "allTime">("season");
  const [sortMode, setSortMode] = useState<"ovr" | "rank">("ovr");
  const cardMotionRefs = useRef(new Map<number, HTMLDivElement>());
  const previousCardPositions = useRef(new Map<number, DOMRect>());
  const cardForPeriod = (player: CardPlayer) => period === "allTime" ? player.allTimeCard : player.card;
  const visiblePlayers = [...data.players]
    .sort((a, b) => {
      const ovrDifference = cardForPeriod(b).overall - cardForPeriod(a).overall;
      if (sortMode === "ovr") return ovrDifference || a.accountId - b.accountId;
      // Stars do not create a separate rank group: Legend I and Legend V are
      // both Legend, so OVR decides their order within the medal.
      const rankDifference = Math.floor((b.rankTier ?? 0) / 10) - Math.floor((a.rankTier ?? 0) / 10);
      return rankDifference || ovrDifference || a.accountId - b.accountId;
    })
    .slice(0, 10);
  const rows = Math.max(1, Math.ceil(visiblePlayers.length / 5));
  const perRow = Math.ceil(visiblePlayers.length / rows);
  const gridStyle = { "--per-row": perRow } as CSSProperties;

  const captureCardPositions = () => {
    previousCardPositions.current = new Map(
      [...cardMotionRefs.current].map(([accountId, element]) => [accountId, element.getBoundingClientRect()]),
    );
  };

  const changePeriod = (nextPeriod: "season" | "allTime") => {
    if (nextPeriod === period) return;
    captureCardPositions();
    setPeriod(nextPeriod);
  };

  const changeSortMode = (nextSortMode: "ovr" | "rank") => {
    if (nextSortMode === sortMode) return;
    captureCardPositions();
    setSortMode(nextSortMode);
  };

  useLayoutEffect(() => {
    if (!previousCardPositions.current.size) return;
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    for (const [accountId, element] of cardMotionRefs.current) {
      const previous = previousCardPositions.current.get(accountId);
      if (!previous) continue;
      const next = element.getBoundingClientRect();
      const deltaX = previous.left - next.left;
      const deltaY = previous.top - next.top;
      if (!deltaX && !deltaY) continue;
      element.getAnimations().forEach((animation) => animation.cancel());
      if (!reduceMotion) {
        element.animate(
          [
            { transform: `translate(${deltaX}px, ${deltaY}px) scale(0.96)`, filter: "brightness(1.25)" },
            { transform: "translate(0, 0) scale(1)", filter: "brightness(1)" },
          ],
          { duration: 620, easing: "cubic-bezier(0.22, 1, 0.36, 1)" },
        );
      }
    }
    previousCardPositions.current.clear();
  }, [period, sortMode]);

  return (
    <>
      <Header activePage="players" />
      <section className="players-page" aria-label="Players">
        <div className="players-stage">
          <header className="players-hero">
            <div className="players-title-copy">
              <h1>Low-Priority Ultimate Collection</h1>
            </div>
            <div className="players-controls">
              <div className="period-toggle" aria-label="Players period">
                <button type="button" aria-pressed={period === "season"} onClick={() => changePeriod("season")}>This season</button>
                <button type="button" aria-pressed={period === "allTime"} onClick={() => changePeriod("allTime")}>All time</button>
              </div>
              <div className="period-toggle" aria-label="Players sort order">
                <button type="button" aria-pressed={sortMode === "ovr"} onClick={() => changeSortMode("ovr")}>OVR</button>
                <button type="button" aria-pressed={sortMode === "rank"} onClick={() => changeSortMode("rank")}>Rank</button>
              </div>
            </div>
          </header>
          <div className="players-roster-frame">
            <div className="players-cards-grid" style={gridStyle}>
              {visiblePlayers.map((player, index) => (
                <div
                  className="card-motion"
                  key={player.accountId}
                  ref={(element) => {
                    if (element) cardMotionRefs.current.set(player.accountId, element);
                    else cardMotionRefs.current.delete(player.accountId);
                  }}
                >
                  <PlayerCard player={player} index={index} period={period} />
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>
    </>
  );
}


function PlayerCard({ player, index, period }: { player: CardPlayer; index: number; period: "season" | "allTime" }) {
  const shellRef = useRef<HTMLElement | null>(null);
  const nameRef = useRef<HTMLHeadingElement | null>(null);
  const state = normalizeCardPlayer(player, period === "allTime" ? player.allTimeCard : player.card);

  const fullName = String(state.name);
  useLayoutEffect(() => {
    const el = nameRef.current;
    if (!el) return;
    // Keep one uniform font size; if the name is too long even at full width
    // (up to the wreaths), trim it and finish with "..".
    const fit = () => {
      el.textContent = fullName;
      if (el.scrollWidth <= el.clientWidth) return;
      let lo = 1;
      let hi = fullName.length;
      while (lo < hi) {
        const mid = Math.ceil((lo + hi) / 2);
        el.textContent = `${fullName.slice(0, mid)}..`;
        if (el.scrollWidth <= el.clientWidth) lo = mid;
        else hi = mid - 1;
      }
      el.textContent = `${fullName.slice(0, lo)}..`;
    };
    fit();
    let cancelled = false;
    document.fonts?.ready.then(() => {
      if (!cancelled) fit();
    });
    window.addEventListener("resize", fit);
    return () => {
      cancelled = true;
      window.removeEventListener("resize", fit);
    };
  }, [fullName]);
  const templatePath = `/assets/card-templates/${state.template}_card_transparent.png`;
  const localAvatar = `/assets/players/${state.avatar}.jpg`;
  const remoteAvatar = player.avatar || "/assets/players/1.jpg";
  const stats = statKeys.map((key) => ({
    label: state[`label${key}`],
    value: state[`stat${key}`],
  }));
  const style = {
    ...cardStyle(state),
    "--i": index,
    "--template-url": `url("${templatePath}")`,
  } as CSSProperties;

  const handleTilt = (event: MouseEvent<HTMLElement>) => {
    const shell = shellRef.current;
    if (!shell) return;
    const rect = shell.getBoundingClientRect();
    const x = (event.clientX - rect.left) / rect.width;
    const y = (event.clientY - rect.top) / rect.height;
    shell.style.setProperty("--tilt-y", `${((x - 0.5) * 16).toFixed(2)}deg`);
    shell.style.setProperty("--tilt-x", `${((0.5 - y) * 12).toFixed(2)}deg`);
    shell.style.setProperty("--glare-x", `${(x * 100).toFixed(1)}%`);
    shell.style.setProperty("--glare-y", `${(y * 100).toFixed(1)}%`);
  };

  const resetTilt = () => {
    const shell = shellRef.current;
    if (!shell) return;
    shell.style.setProperty("--tilt-x", "0deg");
    shell.style.setProperty("--tilt-y", "0deg");
  };

  const openProfile = () => {
    window.location.href = `/profile/${player.accountId}`;
  };

  return (
    <article
      ref={shellRef}
      className="card-shell"
      style={style}
      role="button"
      tabIndex={0}
      onMouseMove={handleTilt}
      onMouseLeave={resetTilt}
      onClick={openProfile}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          openProfile();
        }
      }}
      aria-label={`${state.name} card`}
    >
      <div className="player-card">
        <img className="template" src={templatePath} alt="" />
        <div className="avatar-frame">
          <img
            className="avatar"
            src={remoteAvatar}
            alt={String(state.name)}
            data-fallback={localAvatar}
            onError={handleAvatarError}
          />
        </div>
        <img className="frame-fx frame-aura" src={templatePath} alt="" aria-hidden="true" />
        <img className="frame-fx frame-holo" src={templatePath} alt="" aria-hidden="true" />
        <div className="spark-fx" aria-hidden="true" />
        <div className="glare-fx" aria-hidden="true" />
        <div className="rating">
          <span className="ovr">{state.rating}</span>
          <span className="position">{state.position}</span>
        </div>
        <span className="rating-rule" aria-hidden="true" />
        <div className="rank-mark" aria-label="Rank mark">
          <img className="rank-stars" src={`/assets/ranks/rank_star_${state.rankStars}.png`} alt="" />
          <img className="rank-icon" src={`/assets/ranks/rank_icon_${state.rankIcon}.png`} alt="" />
        </div>
        <h2 className="name" ref={nameRef}>{state.name}</h2>
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
