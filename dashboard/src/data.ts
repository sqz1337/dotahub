import cardPresetJson from "../../card_example.json";
import dashboardData from "../../data/dashboard.json";

export type DashboardData = typeof dashboardData;
export type CardPreset = typeof cardPresetJson;
export type CardPlayer = DashboardData["players"][number];
export type PlayerCardStats = {
  overall: number;
  position: string;
  rows: { label: string; value: number }[];
  source: {
    avgGpm: number;
    avgXpm: number;
    avgLastHits: number;
  };
};
export type LeaderboardPlayer = DashboardData["leaderboard"][number];
export type RecentGame = DashboardData["recentPartyGames"][number];
export type FeedEvent = DashboardData["feed"][number];
export type GameModeFilter = "all" | "turbo" | "ranked" | "other";
export type Page = "dashboard" | "players" | "profile";

export const data = dashboardData as DashboardData;
export const cardPreset = cardPresetJson as CardPreset;
export const playersById = new Map(data.players.map((player) => [player.accountId, player]));

const admiralAccountId = 175966938;
export const defaultProfileAccountId = playersById.has(admiralAccountId)
  ? admiralAccountId
  : Number(data.players[0]?.accountId ?? 0);
