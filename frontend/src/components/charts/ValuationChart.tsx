"use client"

import React, { useState } from "react"
import { BaseChart } from "./BaseChart"
import { Switch } from "@/components/ui/switch"

export function ValuationChart({ title, dates, values, stats, reverseColors = false }: any) {
  const [zoomEnabled, setZoomEnabled] = useState(false);
  
  // 7-Zone Color Palette (Red-Yellow-Green)
  // Index 0 is the highest zone, Index 6 is the lowest
  const standardPalette = [
    "#ff0071", // +4 SD (Red)
    "#fca5a5", // +3 SD (Light Red)
    "#ffba7f", // +2 SD (Orange)
    "#fef08a", // +1 SD (Yellow)
    "#dcfce7", // Median to -1 (Light Green)
    "#86efac", // -1 to -2 (Green)
    "#22c55e", // < -2 (Deep Green)
  ];

  const colors = reverseColors ? [...standardPalette].reverse() : standardPalette;

  // Define the colored background bands
  const shapes = [
    // Top Zone (> +4 SD)
    { type: 'rect', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: stats.upper4, y1: stats.upper4 * 2, fillcolor: colors[0], opacity: 0.25, line: {width: 0} },
    // +3 to +4 SD
    { type: 'rect', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: stats.upper3, y1: stats.upper4, fillcolor: colors[1], opacity: 0.25, line: {width: 0} },
    // +2 to +3 SD
    { type: 'rect', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: stats.upper2, y1: stats.upper3, fillcolor: colors[2], opacity: 0.25, line: {width: 0} },
    // +1 to +2 SD
    { type: 'rect', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: stats.upper1, y1: stats.upper2, fillcolor: colors[3], opacity: 0.25, line: {width: 0} },
    // Median to +1 SD
    { type: 'rect', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: stats.median, y1: stats.upper1, fillcolor: "#fdfcf0", opacity: 0.3, line: {width: 0} },
    // -1 SD to Median
    { type: 'rect', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: stats.lower1, y1: stats.median, fillcolor: colors[4], opacity: 0.25, line: {width: 0} },
    // -2 SD to -1 SD
    { type: 'rect', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: stats.lower2, y1: stats.lower1, fillcolor: colors[5], opacity: 0.25, line: {width: 0} },
    // Bottom Zone (< -2 SD)
    { type: 'rect', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: 0, y1: stats.lower2, fillcolor: colors[6], opacity: 0.25, line: {width: 0} },
  ];

  // Annotations for the lines
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
    font: { size: 8, family: 'Geist Mono', color: '#64748b' },
    bgcolor: 'rgba(255,255,255,0.9)',
    bordercolor: '#e2e8f0',
    borderwidth: 1,
  }));

  const plotData = [
    { 
      x: dates, 
      y: values, 
      type: 'scatter', 
      mode: 'lines', 
      name: title, 
      line: { color: '#231eb2', width: 2 }, // Darker line for better visibility over colors
      hovertemplate: `<b>${title}: %{y:.2f}</b><extra></extra>` 
    },
    { 
      x: [dates[0], dates[dates.length - 1]], 
      y: [stats.median, stats.median], 
      type: 'scatter', 
      mode: 'lines', 
      line: { color: '#64748b', width: 1.5, dash: 'dot' }, 
      hoverinfo: 'none' 
    }
  ];

  return (
    <div className="bg-white dark:bg-slate-950 border dark:border-slate-800 rounded-3xl p-6 shadow-sm">
      <div className="flex items-center justify-between mb-6">
        <div className="flex flex-col">
            <h2 className="text-xs font-black uppercase tracking-widest text-slate-400">{title} Ratio</h2>
            <span className="text-[10px] text-slate-400 font-bold">Historical Median: {stats.median}</span>
        </div>
        <div className="flex items-center gap-2 px-3 py-1 bg-slate-50 dark:bg-slate-900 rounded-full border border-slate-100 dark:border-slate-800">
            <span className="text-[9px] font-bold text-slate-400 uppercase tracking-widest">Interactive</span>
            <Switch checked={zoomEnabled} onCheckedChange={setZoomEnabled} className="scale-75 data-[state=checked]:bg-blue-600" />
        </div>
      </div>
      <div className="h-[500px]">
        <BaseChart 
            data={plotData} 
            zoomEnabled={zoomEnabled} 
            layout={{ 
                shapes, 
                annotations, 
                yaxis: { side: "right", range: [Math.min(...values) * 0.7, stats.upper4 * 1.15], zeroline: false },
                xaxis: { showgrid: false } 
            }} 
        />
      </div>
    </div>
  );
}