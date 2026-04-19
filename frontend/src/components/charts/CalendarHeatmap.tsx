"use client"

import React, { useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { useStore } from "@/store/useStore"
import { BaseChart } from "./BaseChart"
import { Skeleton } from "@/components/ui/skeleton"

// PREMIUM "MUTED" COLORSCALE
const PROFESSIONAL_SCALE = [
  [0.0, '#7f1d1d'], // Deepest Crimson
  [0.2, '#ef4444'], // Bright Red
  [0.4, '#fee2e2'], // Soft Red-White
  [0.5, '#ffffff'], // Pure White (Exactly Zero)
  [0.6, '#dcfce7'], // Soft Green-White
  [0.8, '#22c55e'], // Bright Green
  [1.0, '#14532d']  // Deepest Emerald
];

export function CalendarHeatmap() {
  const { selectedIndices } = useStore()

  const { data: response, isLoading } = useQuery({
    queryKey: ["calendar-returns"],
    queryFn: async () => {
      const res = await fetch("http://localhost:8000/api/calendar-returns")
      return res.json()
    }
  })

  const plotData = useMemo(() => {
    // FIX: Extract the actual array from the response object
    const dataArray = response?.data;
    if (!dataArray || !Array.isArray(dataArray) || dataArray.length === 0) return null;

    // Filter indices based on what's actually in the keys of the first data object
    const indices = selectedIndices.filter(idx => Object.keys(dataArray[0]).includes(idx));
    if (indices.length === 0) return null;

    // Filter out rows where all selected indices are empty
    const validRows = dataArray.filter((row: any) => {
      return indices.some(idx => row[idx] !== null && row[idx] !== undefined);
    });

    // CLEAN YEAR LABELS
    const cleanYears = validRows.map((row: any) => {
      let y = String(row.Period);
      if (y.includes('-')) {
        const parts = y.split('-');
        const lastDate = parts[parts.length - 1];
        const yr = lastDate.split('/').pop() || "";
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

    // ADAPTIVE TEXT COLOR LOGIC
    const textData = zData.map(row => 
      row.map(val => {
        if (val === null) return "";
        const textColor = (val < -25 || val > 30) ? "#ffffff" : "#1e293b";
        return `<span style="color: ${textColor}">${val.toFixed(1)}%</span>`;
      })
    );

    return {
      z: zData,
      x: indices,
      y: cleanYears,
      type: "heatmap",
      colorscale: PROFESSIONAL_SCALE,
      zmid: 0,
      zmin: -50, 
      zmax: 50,
      showscale: true,
      colorbar: {
        thickness: 12,
        len: 0.8,
        title: { text: "%", font: { size: 10, family: "Geist Sans" } },
        outlinewidth: 0,
      },
      xgap: 2, 
      ygap: 2,
      text: textData,
      texttemplate: "%{text}",
      textfont: { family: "Geist Mono, monospace", size: 10, fontWeight: "bold" },
      hovertemplate: "<b>%{x}</b><br>Year: %{y}<br>Return: <b>%{z:.2f}%</b><extra></extra>"
    }
  }, [response, selectedIndices]);

  if (isLoading) return <Skeleton className="h-[600px] w-full rounded-3xl" />
  if (!plotData) return null;

  const chartHeight = Math.max(500, plotData.y.length * 32 + 150);

  return (
    <div className="bg-white dark:bg-[#09090b] border border-slate-200 dark:border-slate-800 rounded-3xl p-8 shadow-sm overflow-hidden flex flex-col items-center">
      <div className="w-full flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="h-6 w-1 bg-emerald-500 rounded-full" />
            <div>
                <h3 className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-500">Calendar Returns Heatmap</h3>
                {/* DISPLAY DATA SCOPE METADATA */}
                <p className="text-[9px] text-slate-400 font-bold uppercase mt-0.5 tracking-tight">
                  Scope: {response?.scope}
                </p>
            </div>
          </div>
      </div>
      
      <div className="w-full max-w-6xl mx-auto" style={{ height: `${chartHeight}px` }}>
        <BaseChart 
          data={[plotData]} 
          layout={{
            xaxis: { 
                type: 'category', 
                tickangle: -45, 
                side: "bottom", 
                showgrid: false,
                automargin: true,
                fixedrange: true
            },
            yaxis: { 
                type: 'category', 
                autorange: "reversed", 
                side: "left", 
                showgrid: false,
                dtick: 1,
                fixedrange: true,
                showline: false,
                tickfont: { size: 11, family: "Geist Mono", color: "#64748b" }
            },
            hovermode: "closest", 
            margin: { l: 70, r: 20, t: 20, b: 120 },
            plot_bgcolor: "transparent",
            paper_bgcolor: "transparent",
          }} 
          config={{ displayModeBar: false }}
        />
      </div>
    </div>
  )
}