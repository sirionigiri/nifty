"use client"

import React, { useState } from "react"
import { BaseChart } from "./BaseChart"
import { Switch } from "@/components/ui/switch"

export function ValuationChart({ title, dates, values, stats, reverseColors = false }: any) {
  const [zoomEnabled, setZoomEnabled] = useState(false);
  
  const standardPalette = [
    "#ff0071", // +4 SD
    "#fca5a5", // +3 SD
    "#ffba7f", // +2 SD
    "#fef08a", // +1 SD
    "#dcfce7", // Median to -1
    "#86efac", // -1 to -2
    "#22c55e", // < -2
  ];

  const colors = reverseColors ? [...standardPalette].reverse() : standardPalette;

  // 1. DYNAMIC Y-BOUNDS CALCULATION
  // This ensures the chart "snaps" to the visible bands, not the infinite void
  // 1. DYNAMIC Y-BOUNDS CALCULATION
  const maxValue = Math.max(...values);
  const minValue = Math.min(...values);

  // Derive one real SD unit directly from the stats already computed server-side
  const sd = stats.upper1 - stats.median;

  const sdLevels = [
    stats.lower2,
    stats.lower1,
    stats.median,
    stats.upper1,
    stats.upper2,
    stats.upper3,
    stats.upper4,
  ].filter(v => v !== null && v !== undefined);

  // Ceiling: whichever is greater — the actual data max, or the topmost defined SD band —
  // plus a full extra SD of headroom above it.
  const dynamicCeiling = Math.max(maxValue, stats.upper4) + sd;

  // Floor: whichever is lower — the actual data min, or the bottom defined SD band —
  // minus a full extra SD below it.
  const dynamicFloor = Math.min(minValue, stats.lower2) - sd;

  // 2. DEFINE COLORED BANDS (SHAPES)
  const shapes = [
    { type: 'rect', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: stats.upper4, y1: stats.upper4 * 2, fillcolor: colors[0], opacity: 0.25, line: {width: 0} },
    { type: 'rect', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: stats.upper3, y1: stats.upper4, fillcolor: colors[1], opacity: 0.25, line: {width: 0} },
    { type: 'rect', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: stats.upper2, y1: stats.upper3, fillcolor: colors[2], opacity: 0.25, line: {width: 0} },
    { type: 'rect', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: stats.upper1, y1: stats.upper2, fillcolor: colors[3], opacity: 0.25, line: {width: 0} },
    { type: 'rect', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: stats.median, y1: stats.upper1, fillcolor: "#fdfcf0", opacity: 0.3, line: {width: 0} },
    { type: 'rect', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: stats.lower1, y1: stats.median, fillcolor: colors[4], opacity: 0.25, line: {width: 0} },
    { type: 'rect', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: stats.lower2, y1: stats.lower1, fillcolor: colors[5], opacity: 0.25, line: {width: 0} },
    { type: 'rect', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: 0, y1: stats.lower2, fillcolor: colors[6], opacity: 0.25, line: {width: 0} },
  ];

  // 3. DEFINE RIGHT-SIDE LABELS (ANNOTATIONS)
  const annotations = [
    { y: stats.upper4, text: "+4 SD" },
    { y: stats.upper3, text: "+3 SD" },
    { y: stats.upper2, text: "+2 SD" },
    { y: stats.upper1, text: "+1 SD" },
    { y: stats.median, text: "MEDIAN" },
    { y: stats.lower1, text: "-1 SD" },
    { y: stats.lower2, text: "-2 SD" },
  ].map(ann => ({
    xref: 'paper', x: 1, y: ann.y,
    text: `<b>${ann.text}: ${ann.y}</b>`,
    showarrow: false,
    xanchor: 'left',
    font: { size: 10, family: 'Geist Mono', color: '#64748b' },
    bgcolor: 'rgba(255,255,255,0.9)',
    bordercolor: '#e2e8f0',
    borderwidth: 1,
    borderpad: 2,
  }));

  const plotData = [
    { 
      x: dates, 
      y: values, 
      type: 'scatter', 
      mode: 'lines', 
      name: title, 
      line: { color: '#231eb2', width: 2.5 },
      hovertemplate: `<b>${title}: %{y:.2f}</b><extra></extra>` 
    },
    { 
      x: [dates[0], dates[dates.length - 1]], 
      y: [stats.median, stats.median], 
      type: 'scatter', 
      mode: 'lines', 
      line: { color: '#475569', width: 2, dash: 'dot' }, 
      hoverinfo: 'none' 
    }
  ];

  return (
    <div className="bg-white dark:bg-slate-950 border dark:border-slate-800 rounded-3xl p-6 shadow-sm overflow-hidden">
      <div className="flex items-center justify-between mb-6">
        <div className="flex flex-col">
          <h2 className="text-xs font-black uppercase tracking-widest text-slate-400">{title}</h2>
          <span className="text-[10px] text-slate-400 font-bold uppercase tracking-tight">Period Median: {stats.median}</span>
        </div>
        <div className="flex items-center gap-2 px-3 py-1 bg-slate-50 dark:bg-slate-900 rounded-full border border-slate-100 dark:border-slate-800 shadow-sm">
          <span className="text-[9px] font-bold text-slate-400 uppercase tracking-widest">Interactive</span>
          <Switch checked={zoomEnabled} onCheckedChange={setZoomEnabled} className="scale-75 data-[state=checked]:bg-blue-600 shadow-none" />
        </div>
      </div>
      
      <div className="h-[500px]">
        <BaseChart 
          data={plotData} 
          zoomEnabled={zoomEnabled} 
          layout={{ 
            shapes, 
            annotations, 
            yaxis: { 
              side: "right", 
              range: [dynamicFloor, dynamicCeiling],
              zeroline: false,
              tickfont: { size: 12, family: "Geist Mono", color: "#64748b" }
            },
            xaxis: { 
              showgrid: false,
              tickfont: { size: 11, family: "Geist Sans", color: "#64748b" }
            },
            margin: { l: 20, r: 80, t: 20, b: 40 } // Increased right margin for SD labels
          }} 
        />
      </div>
    </div>
  );
}