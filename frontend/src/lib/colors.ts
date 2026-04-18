// Helper to generate a Heatmap Color (Yellow -> Orange -> Red)
export function getHeatmapColor(value: number, min: number, max: number): string {
  if (value === null || isNaN(value)) return 'transparent';
  
  // Normalize value between 0 and 1
  const ratio = max === min ? 0.5 : (value - min) / (max - min);
  
  // Plotly/Streamlit YlOrRd approximated hex scale
  const colors = [
    '#ffffcc', // Lightest yellow
    '#ffeda0',
    '#fed976',
    '#feb24c',
    '#fd8d3c',
    '#fc4e2a',
    '#e31a1c',
    '#b10026'  // Deepest red
  ];
  
  const index = Math.min(Math.floor(ratio * colors.length), colors.length - 1);
  return colors[Math.max(0, index)];
}

// Helper to generate consistent Categorical Colors for Indices (for the Rankings table)
const PALETTE = [
  { hex: "#5d90fc", rgb: "93, 144, 252" },
  { hex: "#6de197", rgb: "109, 225, 151" },
  { hex: "#ddcb82", rgb: "221, 203, 130" },
  { hex: "#bd9af8", rgb: "189, 154, 248" },
  { hex: "#e9b6a9", rgb: "233, 182, 169" },
  { hex: "#41dbb9", rgb: "65, 219, 185" },
];

export function getCategoricalColor(name: string) {
  if (!name || name === "—") return { hex: "transparent", bg: "transparent" };
  // Simple hash to consistently assign a color based on the index name
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
  const color = PALETTE[Math.abs(hash) % PALETTE.length];
  
  return { 
    hex: color.hex, 
    bg: `rgba(${color.rgb}, 0.15)` // 15% opacity for the background tint
  };
}

// Add this below your getHeatmapColor function in src/lib/colors.ts

export function getDivergingColor(value: number, min: number = 0.5, max: number = 1.5): string {
  if (value === null || isNaN(value)) return 'transparent';
  
  // Clamp value
  const val = Math.max(min, Math.min(max, value));
  const ratio = (val - min) / (max - min); // 0.0 to 1.0

  // RdBu_r equivalent: 0=Blue, 0.5=White, 1=Red
  const colors = [
    '#3182bd', // Deep Blue
    '#9ecae1',
    '#deebf7', 
    '#ffffff', // White (1.0)
    '#fee0d2',
    '#fc9272',
    '#de2d26'  // Deep Red
  ];
  
  const index = Math.floor(ratio * (colors.length - 1));
  return colors[index];
}