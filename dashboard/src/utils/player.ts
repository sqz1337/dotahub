import type { CSSProperties, SyntheticEvent } from "react";
import { cardPreset, type CardPlayer, type CardPreset, type PlayerCardStats } from "../data";

const rankNames = ["Unranked", "Herald", "Guardian", "Crusader", "Archon", "Legend", "Ancient", "Divine", "Immortal"];
const rankStars = ["", "I", "II", "III", "IV", "V"];
export const statKeys = ["Imp", "Far", "Fgt", "Sur", "Obj", "Utl"] as const;
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

export function rankLabel(rankTier: number | null | undefined) {
  if (!rankTier) return "Unranked";
  const medal = Math.floor(rankTier / 10);
  const star = rankTier % 10;
  const name = rankNames[medal] ?? "Unranked";
  if (medal >= 8) return name;
  return `${name} ${rankStars[star] ?? ""}`.trim();
}

export function rankIconSrc(rankTier: number | null | undefined) {
  if (!rankTier) return null;
  const medal = Math.floor(rankTier / 10);
  if (medal < 1 || medal > 8) return null;
  return `/assets/ranks/rank_icon_${medal}.png`;
}

const mmrMedalThresholds = [
  [2310, 4, 1], [2450, 4, 2], [2610, 4, 3], [2770, 4, 4], [2930, 4, 5],
  [3080, 5, 1], [3230, 5, 2], [3390, 5, 3], [3540, 5, 4], [3700, 5, 5],
  [3850, 6, 1], [4000, 6, 2], [4150, 6, 3], [4300, 6, 4], [4460, 6, 5],
  [4620, 7, 1], [4820, 7, 2], [5020, 7, 3], [5220, 7, 4], [5420, 7, 5],
] as const;

export function mmrMedal(mmr: number) {
  if (mmr > 5620) return { medal: 8, star: 0, label: "Immortal" };
  const threshold = [...mmrMedalThresholds].reverse().find(([minimum]) => mmr >= minimum);
  const [, medal, star] = threshold ?? [0, 4, 1];
  return { medal, star, label: `${rankNames[medal]} ${rankStars[star]}` };
}

export function roleLabel(position: string) {
  return ({ CRY: "Carry", MID: "Mid", OFF: "Offlane", SUP: "Support", FLX: "Flex" } as Record<string, string>)[position] ?? position;
}

function pct(value: number | string) {
  return `${Number(value)}%`;
}

function px(value: number | string) {
  return `${Number(value)}px`;
}

export function cardStyle(preset: Record<string, string | number>): CSSProperties {
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
    // statsGap in the preset is px for the 424px reference card from cards.html;
    // scale it with the actual card width so number/label spacing stays true.
    if (key === "statsGap") value = `calc(var(--card-width) * ${(Number(value) / 424).toFixed(4)})`;
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

export function normalizeCardPlayer(player: CardPlayer, card: PlayerCardStats = player.card) {
  const rows = card.rows;
  const state: Record<string, string | number> = {
    ...cardPreset,
    template: player.medal.template || cardPreset.template,
    avatar: String(player.accountId),
    rating: card.overall,
    position: card.position,
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

export function handleAvatarError(event: SyntheticEvent<HTMLImageElement>) {
  const img = event.currentTarget;
  const fallback = img.dataset.fallback;
  if (fallback && img.src !== fallback) {
    img.src = fallback;
    img.dataset.fallback = "/assets/players/1.jpg";
  }
}

export function formatTime(value: string | null) {
  if (!value) return "Unknown";
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function relativeTime(value: string | null) {
  if (!value) return "Unknown";
  const diffMs = Date.now() - new Date(value).getTime();
  const hours = Math.max(0, Math.round(diffMs / 3_600_000));
  if (hours < 1) return "Just now";
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

export function heroPortrait(url: string | null | undefined) {
  if (!url) return null;
  return url.replace("/heroes/icons/", "/heroes/");
}
