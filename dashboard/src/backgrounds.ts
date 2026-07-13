export type BackgroundId = "red" | "green" | "purple" | "gold" | "none";

export const backgroundOptions: { id: BackgroundId; label: string }[] = [
  { id: "red", label: "Red" },
  { id: "green", label: "Green" },
  { id: "purple", label: "Purple" },
  { id: "gold", label: "Gold" },
  { id: "none", label: "No background" },
];

const storageKey = "kastems-hub-background";
const defaultBackground: BackgroundId = "red";
const backgroundIds = new Set<BackgroundId>(backgroundOptions.map((option) => option.id));

function isBackgroundId(value: string | null): value is BackgroundId {
  return value !== null && backgroundIds.has(value as BackgroundId);
}

export function getBackgroundPreference(): BackgroundId {
  try {
    const stored = window.localStorage.getItem(storageKey);
    return isBackgroundId(stored) ? stored : defaultBackground;
  } catch {
    return defaultBackground;
  }
}

export function applyBackgroundPreference(background: BackgroundId) {
  document.documentElement.dataset.siteBackground = background;
}

export function initializeBackgroundPreference() {
  applyBackgroundPreference(getBackgroundPreference());
}

export function saveBackgroundPreference(background: BackgroundId) {
  applyBackgroundPreference(background);
  try {
    window.localStorage.setItem(storageKey, background);
  } catch {
    // The visual choice still applies for this page when storage is unavailable.
  }
}
