"use client"

import { useState } from "react"
import { BaseChart } from "./BaseChart"
import { Switch } from "@/components/ui/switch"

export function NavChart() {
  const [logScale, setLogScale] = useState(true)

  // Dummy Time Series Data (Replace with FastAPI data later)
  const xData = ["2023-01-01", "2023-06-01", "2024-01-01", "2024-06-01"]
  const data = [
    {
      x: xData,
      y: [100, 112, 125, 140],
      type: "scatter",
      mode: "lines",
      name: "NIFTY 50",
      line: { color: "#3b82f6", width: 3 }, // Blue
    },
    {
      x: xData,
      y: [100, 120, 115, 150],
      type: "scatter",
      mode: "lines",
      name: "NIFTY NEXT 50",
      line: { color: "#10b981", width: 2 }, // Green
    }
  ]

  return (
    <div className="space-y-4">
      {/* Chart Header & Controls */}
      <div className="flex items-center justify-between border-b pb-4">
        <div>
          <h3 className="text-sm font-bold uppercase tracking-wider text-slate-800 dark:text-slate-200 border-l-4 border-slate-800 dark:border-slate-200 pl-2">
            Rebased NAV — 1 Yr Window
          </h3>
          <p className="text-xs text-muted-foreground mt-1 ml-3">Base = 100</p>
        </div>
        
        <div className="flex items-center space-x-2">
          <span className="text-sm font-medium">Log Scale</span>
          <Switch checked={logScale} onCheckedChange={setLogScale} />
        </div>
      </div>

      {/* Render Chart */}
      <div className="border border-border rounded-xl p-2 bg-card">
        <BaseChart 
          data={data} 
          layout={{
            yaxis: { type: logScale ? "log" : "linear" },
            legend: { orientation: "h", yanchor: "bottom", y: -0.2, xanchor: "center", x: 0.5 }
          }} 
        />
      </div>
    </div>
  )
}