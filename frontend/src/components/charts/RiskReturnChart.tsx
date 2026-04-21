"use client"

import React, { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { useStore } from "@/store/useStore"
import { BaseChart } from "./BaseChart"
import { getCategoricalColor } from "@/lib/colors"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Switch } from "@/components/ui/switch"
import { API_BASE_URL } from "@/lib/utils"


export function RiskReturnChart() {
  const { selectedIndices, periods } = useStore()
  const [activePeriod, setActivePeriod] = useState("5 Yr")
  const [zoomEnabled, setZoomEnabled] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ["scatter", selectedIndices, activePeriod],
    queryFn: async () => {
      const res = await fetch(`${API_BASE_URL}/api/scatter-data`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
            metric: "scatter", 
            periods: [activePeriod], 
            indices: selectedIndices, 
            benchmark: "" 
        })
      })
      return res.json()
    },
    enabled: selectedIndices.length > 0
  })

  if (isLoading) return <Skeleton className="h-[500px] w-full rounded-3xl" />

  const plotData = [{
    x: data?.map((d: any) => d.risk),
    y: data?.map((d: any) => d.return),
    text: data?.map((d: any) => d.index),
    mode: 'markers+text',
    type: 'scatter',
    textposition: 'top center',
    marker: { 
        size: 14, 
        color: data?.map((d: any) => getCategoricalColor(d.index).hex),
        line: { width: 2, color: 'white' },
        opacity: 0.8
    },
    textfont: { family: 'Geist Sans', size: 10, fontWeight: 'bold' },
    hovertemplate: 
        "<b>%{text}</b><br>" +
        "Risk (Vol): <b>%{x:.2f}%</b><br>" +
        "Return (CAGR): <b>%{y:.2f}%</b>" +
        "<extra></extra>"
  }]

  return (
    <div className="space-y-6">
      {/* HEADER WITH TOGGLE AND PERIODS */}
      <div className="flex flex-col md:flex-row justify-between items-center gap-4 bg-slate-50/50 dark:bg-slate-900/20 p-4 rounded-2xl border border-slate-100 dark:border-slate-800">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 px-3 py-1 bg-white dark:bg-slate-900 rounded-full border border-slate-200 dark:border-slate-800 shadow-sm">
            <span className="text-[9px] font-bold text-slate-400 uppercase tracking-widest">Interactive</span>
            <Switch 
                checked={zoomEnabled} 
                onCheckedChange={setZoomEnabled} 
                className="scale-75 data-[state=checked]:bg-blue-600" 
            />
          </div>
        </div>

        <Tabs value={activePeriod} onValueChange={setActivePeriod}>
          <TabsList className="segmented-tabs-list !mb-0">
            {/* Show common periods for the scatter plot */}
            {["1 Yr", "3 Yr", "5 Yr", "10 Yr", "20 Yr"].map(p => (
              <TabsTrigger key={p} value={p} className="segmented-tab-trigger">{p}</TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </div>

      {/* THE CHART */}
      <div className="h-[550px] w-full">
        <BaseChart 
          data={plotData as any} 
          zoomEnabled={zoomEnabled}
          layout={{ 
            hovermode: 'closest',
            xaxis: { 
                title: { text: "RISK (ANNUALISED VOLATILITY %)", font: { size: 10, family: 'Geist Sans', fontWeight: 'bold' } },
                gridcolor: '#f1f5f9',
                zeroline: false
            },
            yaxis: { 
                title: { text: "RETURN (CAGR %)", font: { size: 10, family: 'Geist Sans', fontWeight: 'bold' } },
                gridcolor: '#f1f5f9',
                zeroline: true,
                zerolinecolor: '#e2e8f0'
            },
            margin: { l: 50, r: 20, t: 20, b: 50 }
          }} 
        />
      </div>
    </div>
  )
}