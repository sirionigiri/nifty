"use client"

import React, { useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { useStore } from "@/store/useStore"
import { BaseChart } from "./BaseChart"
import { Skeleton } from "@/components/ui/skeleton"

// 1. HARDCODE THE COLORSCALE
// This guarantees Plotly uses Red-Yellow-Green and doesn't default to Blue-Red.
const RED_YELLOW_GREEN = [
  [0.0, '#a50026'], // Deep Red (Highest Negative)
  [0.2, '#d73027'],
  [0.4, '#f46d43'],
  [0.5, '#ffffbf'], // Pale Yellow (Exactly Zero)
  [0.6, '#a6d96a'],
  [0.8, '#66bd63'],
  [1.0, '#006837']  // Deep Green (Highest Positive)
];

export function CalendarHeatmap() {
  const { selectedIndices } = useStore()

  const { data, isLoading } = useQuery({
    queryKey: ["calendar-returns"],
    queryFn: async () => {
      const res = await fetch("http://localhost:8000/api/calendar-returns")
      return res.json()
    }
  })

  const plotData = useMemo(() => {
    if (!data || data.length === 0) return null;

    const indices = selectedIndices.filter(idx => Object.keys(data[0]).includes(idx));
    if (indices.length === 0) return null;

    const validRows = data.filter((row: any) => {
      return indices.some(idx => row[idx] !== null && row[idx] !== undefined);
    });

    const cleanYears = validRows.map((row: any) => {
      let y = String(row.Period);
      if (y.includes('-')) {
        const parts = y.split('-');
        const yr = parts[parts.length - 1].split('/').pop() || "";
        return yr.length === 2 ? `20${yr}` : yr;
      }
      return y;
    });

    const zData = validRows.map((row: any) => {
      return indices.map(idx => {
        const val = row[idx];
        return (val !== null && val !== undefined) ? Number(val) : null;
      });
    });

    // --- ADAPTIVE TEXT COLOR LOGIC ---
    // 1. Find the absolute maximum value to know the bounds of our colorscale
    const allValues = zData.flat().filter(v => v !== null) as number[];
    const maxVal = Math.max(...allValues);
    const minVal = Math.min(...allValues);
    const absMax = Math.max(Math.abs(maxVal), Math.abs(minVal));

    // 2. Build the text matrix with dynamic HTML spans
    const textData = zData.map(row => 
      row.map(val => {
        if (val === null) return "";
        
        // Calculate where this value sits on the colorscale (0.0 to 1.0)
        const ratio = absMax === 0 ? 0.5 : (val + absMax) / (2 * absMax);
        
        // If it's in the deep red (< 0.25) or deep green (> 0.75) zones, use white text. 
        // Otherwise, use dark text for the yellow/light zones.
        const textColor = (ratio < 0.25 || ratio > 0.75) ? "#ffffff" : "#1e293b";
        
        // Inject the color directly via Plotly's supported pseudo-HTML
        return `<span style="color: ${textColor}">${val.toFixed(1)}%</span>`;
      })
    );

    return {
      z: zData,
      x: indices,
      y: cleanYears,
      type: "heatmap",
      colorscale: RED_YELLOW_GREEN,
      zmid: 0, 
      showscale: true,
      hoverongaps: false,
      xgap: 4, 
      ygap: 4, 
      text: textData,
      texttemplate: "%{text}",
      // Removed the hardcoded color from textfont so the span styles take over!
      textfont: { family: "Geist Mono, monospace", size: 11, fontWeight: "bold" },
      hovertemplate: "<b>%{x}</b><br>Year: %{y}<br>Return: <b>%{text}</b><extra></extra>"
    }
  }, [data, selectedIndices]);

  if (isLoading) return <Skeleton className="h-[600px] w-full rounded-2xl" />
  
  if (!plotData) {
      return (
        <div className="h-[400px] w-full border border-dashed border-slate-200 dark:border-slate-800 rounded-2xl flex flex-col items-center justify-center text-slate-400">
            <p className="font-bold uppercase tracking-widest text-[10px]">Awaiting Indices</p>
            <p className="text-xs mt-1">Select indices to generate heatmap</p>
        </div>
      )
  }

  // Calculate dynamic height based on number of years so rows don't get squashed or overly stretched
  const chartHeight = Math.max(500, plotData.y.length * 35 + 150);

  return (
    <div className="bg-white dark:bg-[#09090b] border border-slate-200 dark:border-slate-800 rounded-3xl p-8 shadow-sm overflow-hidden flex flex-col items-center">
      <div className="w-full flex items-center gap-3 mb-4">
          <div className="h-6 w-1 bg-emerald-500 rounded-full" />
          <h3 className="text-xs font-black uppercase tracking-[0.2em] text-slate-500">Calendar Year Returns (%)</h3>
      </div>
      
      {/* Container is centered and constrained so 3 columns don't stretch 1600px wide */}
      <div className="w-full max-w-5xl mx-auto" style={{ height: `${chartHeight}px` }}>
        <BaseChart 
          data={[plotData]} 
          layout={{
            xaxis: { 
                type: 'category', 
                tickangle: -45, 
                side: "bottom", 
                showgrid: false,
                automargin: true,
                fixedrange: true // Prevents accidental zooming on the grid
            },
            yaxis: { 
                type: 'category', 
                autorange: "reversed", 
                showgrid: false,
                dtick: 1,
                fixedrange: true
            },
            hovermode: "closest", 
            margin: { l: 60, r: 20, t: 20, b: 120 },
            plot_bgcolor: "transparent",
            paper_bgcolor: "transparent",
          }} 
          config={{ displayModeBar: false }}
        />
      </div>
    </div>
  )
}