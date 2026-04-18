"use client"

import React, { useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { useStore } from "@/store/useStore"
import { BaseChart } from "./BaseChart"
import { Skeleton } from "@/components/ui/skeleton"

export function RiskAdjustedHeatmap() {
  const { selectedIndices, benchmark, periods } = useStore()

  const { data, isLoading } = useQuery({
    queryKey: ["metrics", "te", selectedIndices, benchmark, periods],
    queryFn: async () => {
      const res = await fetch("http://localhost:8000/api/metrics", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ metric: "te", periods, indices: selectedIndices, benchmark })
      })
      return res.json()
    },
    enabled: selectedIndices.length > 0
  })

  const plotData = useMemo(() => {
    if (!data || data.length === 0) return null

    const yPeriods = data.map((d: any) => d.Period)
    const xIndices = Object.keys(data[0]).filter(k => k !== 'Period')

    const zData = yPeriods.map((p: string) => {
      const row = data.find((d: any) => d.Period === p)
      return xIndices.map(idx => row[idx])
    })

    return {
      z: zData,
      x: xIndices,
      y: yPeriods,
      type: "heatmap",
      colorscale: "RdYlGn", // Standard professional scale
      reversescale: true,
      text: zData.map(row => row.map(val => val ? val.toFixed(2) : "")),
      texttemplate: "%{text}",
      textfont: { family: "Geist Mono", size: 10 },
      hovertemplate: "<b>%{x}</b><br>Period: %{y}<br>Value: <b>%{z:.2f}</b><extra></extra>"
    }
  }, [data])

  if (isLoading) return <Skeleton className="h-[400px] w-full rounded-2xl" />

  return (
    <div className="heatmap-container">
      <div className="heatmap-title-row">
        <div className="flex items-center gap-3">
            <div className="h-6 w-1 bg-indigo-500 rounded-full" />
            <h3 className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-500">Risk-Adjusted Returns Heatmap</h3>
        </div>
      </div>
      <div className="h-[400px]">
        <BaseChart 
          data={[plotData]} 
          layout={{
            xaxis: { side: "bottom", showgrid: false },
            yaxis: { autorange: "reversed", showgrid: false },
            margin: { l: 100, r: 20, t: 20, b: 80 }
          }} 
        />
      </div>
    </div>
  )
}