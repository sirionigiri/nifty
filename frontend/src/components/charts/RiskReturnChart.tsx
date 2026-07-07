"use client"

import React, { useState, useRef, useEffect, useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { useStore } from "@/store/useStore"
import { BaseChart } from "./BaseChart"
import { getCategoricalColor } from "@/lib/colors"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Switch } from "@/components/ui/switch"
import { API_BASE_URL } from "@/lib/utils"
import { computeLabelLayout } from "@/lib/labelLayout"

const MARGIN = { l: 50, r: 20, t: 20, b: 50 }

export function RiskReturnChart() {
  const { selectedIndices, periods, referenceDate } = useStore()
  const [activePeriod, setActivePeriod] = useState("5 Yr")
  const [zoomEnabled, setZoomEnabled] = useState(false)

  const containerRef = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ width: 900, height: 480 })

  useEffect(() => {
    if (!containerRef.current) return
    const el = containerRef.current
    const observer = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect
      setSize({
        width: Math.max(width - MARGIN.l - MARGIN.r, 100),
        height: Math.max(height - MARGIN.t - MARGIN.b, 100),
      })
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  const { data, isLoading } = useQuery({
    queryKey: ["scatter", selectedIndices, activePeriod, referenceDate],
    queryFn: async () => {
      const res = await fetch(`${API_BASE_URL}/api/scatter-data`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          metric: "scatter",
          periods: [activePeriod],
          indices: selectedIndices,
          benchmark: "",
          reference_date: referenceDate,
        }),
      })
      return res.json()
    },
    enabled: selectedIndices.length > 0,
  })

  const points = useMemo(
    () =>
      (data ?? []).map((d: any) => ({
        x: d.risk,
        y: d.return,
        text: d.index,
        color: getCategoricalColor(d.index).hex,
      })),
    [data]
  )

  const { xRange, yRange } = useMemo(() => {
    if (!points.length) return { xRange: [0, 1] as [number, number], yRange: [0, 1] as [number, number] }
    const xs = points.map((p:any) => p.x)
    const ys = points.map((p:any) => p.y)
    const padX = (Math.max(...xs) - Math.min(...xs)) * 0.12 || 1
    const padY = (Math.max(...ys) - Math.min(...ys)) * 0.12 || 1
    return {
      xRange: [Math.min(...xs) - padX, Math.max(...xs) + padX] as [number, number],
      yRange: [Math.min(...ys) - padY, Math.max(...ys) + padY] as [number, number],
    }
  }, [points])

  const annotations = useMemo(() => {
    if (!points.length) return []
    return computeLabelLayout(points, {
      plotWidthPx: size.width,
      plotHeightPx: size.height,
      xRange,
      yRange,
      fontSize: 11,
      markerRadiusPx: 9,
    })
  }, [points, size, xRange, yRange])

  if (isLoading) return <Skeleton className="h-[500px] w-full rounded-3xl" />

  const plotData = [
    {
      x: points.map((p:any) => p.x),
      y: points.map((p:any) => p.y),
      text: points.map((p:any) => p.text),
      mode: "markers",
      type: "scatter",
      marker: {
        size: 14,
        color: points.map((p:any) => p.color),
        line: { width: 2, color: "white" },
        opacity: 0.85,
      },
      hovertemplate:
        "<b>%{text}</b><br>" + "Risk (Vol): <b>%{x:.2f}%</b><br>" + "Return (CAGR): <b>%{y:.2f}%</b>" + "<extra></extra>",
    },
  ]

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row justify-between items-center gap-4 bg-slate-50/50 dark:bg-slate-900/20 p-4 rounded-2xl border border-slate-100 dark:border-slate-800">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 px-3 py-1 bg-white dark:bg-slate-900 rounded-full border border-slate-200 dark:border-slate-800 shadow-sm">
            <span className="text-[9px] font-bold text-slate-400 uppercase tracking-widest">Interactive</span>
            <Switch checked={zoomEnabled} onCheckedChange={setZoomEnabled} className="scale-75 data-[state=checked]:bg-blue-600" />
          </div>
        </div>

        <Tabs value={activePeriod} onValueChange={setActivePeriod}>
          <TabsList className="segmented-tabs-list !mb-0">
            {["1 Yr", "3 Yr", "5 Yr", "10 Yr", "20 Yr"].map((p) => (
              <TabsTrigger key={p} value={p} className="segmented-tab-trigger">
                {p}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </div>

      <div ref={containerRef} className="h-[550px] w-full">
        <BaseChart
          data={plotData as any}
          zoomEnabled={zoomEnabled}
          layout={{
            hovermode: "closest",
            xaxis: {
              title: { text: "RISK (ANNUALISED VOLATILITY %)", font: { size: 12, fontWeight: "bold" } },
              gridcolor: "#f1f5f9",
              zeroline: false,
              range: xRange,
            },
            yaxis: {
              title: { text: "RETURN (CAGR %)", font: { size: 12, fontWeight: "bold" } },
              gridcolor: "#f1f5f9",
              zeroline: true,
              zerolinecolor: "#e2e8f0",
              range: yRange,
            },
            annotations,
            margin: MARGIN,
          }}
        />
      </div>
    </div>
  )
}