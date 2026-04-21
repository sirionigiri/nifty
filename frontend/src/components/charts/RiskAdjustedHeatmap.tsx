"use client"

import React, { useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { useStore } from "@/store/useStore"
import { BaseChart } from "./BaseChart"
import { Skeleton } from "@/components/ui/skeleton"
import { API_BASE_URL } from "@/lib/utils"

// Consistent professional colorscale
const PROFESSIONAL_SCALE = [
  [0.0, '#7f1d1d'], [0.2, '#ef4444'], [0.4, '#fee2e2'], 
  [0.5, '#ffffff'], [0.6, '#dcfce7'], [0.8, '#22c55e'], [1.0, '#14532d']
];

export function RiskAdjustedHeatmap() {
  const { selectedIndices, benchmark, periods } = useStore()

  const { data, isLoading } = useQuery({
    queryKey: ["metrics", "te", selectedIndices, benchmark, periods],
    queryFn: async () => {
      const res = await fetch(`${API_BASE_URL}/api/metrics`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ metric: "te", periods, indices: selectedIndices, benchmark })
      })
      return res.json()
    },
    enabled: selectedIndices.length > 0
  })

  const plotData = useMemo(() => {
    if (!data || !Array.isArray(data) || data.length === 0) return null

    const yPeriods = data.map((d: any) => d.Period)
    const xIndices = Object.keys(data[0]).filter(k => k !== 'Period' && k !== 'Range')

    const zData = yPeriods.map((p: string) => {
      const row = data.find((d: any) => d.Period === p)
      return xIndices.map(idx => row[idx])
    })

    // FIX: Added (row: any) and (val: any) types for Vercel build
    const textData = zData.map((row: any) => 
      row.map((val: any) => {
        if (val === null || val === undefined) return "";
        const textColor = (val < 0.5 || val > 1.5) ? "#ffffff" : "#1e293b";
        return `<span style="color: ${textColor}">${Number(val).toFixed(2)}</span>`;
      })
    );

    return {
      z: zData,
      x: xIndices,
      y: yPeriods,
      type: "heatmap",
      colorscale: PROFESSIONAL_SCALE,
      zmid: 1.0, // Center at 1.0 for risk/return ratios
      xgap: 2,
      ygap: 2,
      text: textData,
      texttemplate: "%{text}",
      textfont: { family: "Geist Mono, monospace", size: 10, fontWeight: 'bold' },
      hovertemplate: "<b>%{x}</b><br>Period: %{y}<br>Value: <b>%{z:.2f}</b><extra></extra>"
    }
  }, [data])

  if (isLoading) return <Skeleton className="h-[400px] w-full rounded-2xl" />

  return (
    <div className="bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm overflow-hidden">
      <div className="flex items-center gap-3 mb-6 border-b border-slate-50 dark:border-slate-900 pb-4">
        <div className="h-6 w-1 bg-indigo-500 rounded-full" />
        <h3 className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-500">Risk-Adjusted Returns Heatmap</h3>
      </div>
      <div className="h-[400px]">
        <BaseChart 
          data={plotData ? [plotData] : []} 
          layout={{
            xaxis: { type: 'category', side: "bottom", showgrid: false, automargin: true },
            yaxis: { type: 'category', autorange: "reversed", showgrid: false },
            hovermode: "closest", 
            margin: { l: 100, r: 20, t: 20, b: 80 }
          }} 
        />
      </div>
    </div>
  )
}