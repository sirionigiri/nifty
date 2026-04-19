// src/lib/colors.ts

// 1. SPECIFIC MAPPINGS (Optional)
// Add indices here if you want them to have a FIXED color every time
const SPECIFIC_INDEX_COLORS: Record<string, string> = {
  "NIFTY 50": "#2563eb",        // Blue
  "NIFTY NEXT 50": "#0891b2",   // Cyan
  "NIFTY MIDCAP 150": "#7c3aed", // Violet
  "NIFTY SMALLCAP 250": "#db2777", // Pink
  "NIFTY MICROCAP250": "#ca8a04", // Gold
};

// 2. GENERAL PALETTE
// This is used for all other indices. Add or change hex codes here!
const PALETTE = [
  "#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", 
  "#ec4899", "#06b6d4", "#f97316", "#14b8a6", "#6366f1"
];

/**
 * Converts a hex color to an RGBA with opacity for backgrounds
 */
function hexToRGB(hex: string, alpha: number) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

export function getCategoricalColor(name: string) {
  if (!name || name === "—") return { hex: "#94a3b8", bg: "transparent" };

  // Check if we have a hardcoded color first
  let hex = SPECIFIC_INDEX_COLORS[name];

  // If not, generate a consistent color based on the name hash
  if (!hex) {
    let hash = 0;
    for (let i = 0; i < name.length; i++) {
      hash = name.charCodeAt(i) + ((hash << 5) - hash);
    }
    hex = PALETTE[Math.abs(hash) % PALETTE.length];
  }

  return {
    hex: hex,
    bg: hexToRGB(hex, 0.12), // 12% opacity background
  };
}

// Helper for the Volatility Heatmap (Yellow -> Orange -> Red)
export function getHeatmapColor(value: number, min: number, max: number) {
  const ratio = (value - min) / (max - min);
  if (ratio < 0.33) return "#fef08a"; // Yellow-200
  if (ratio < 0.66) return "#fb923c"; // Orange-400
  return "#ef4444"; // Red-500
}