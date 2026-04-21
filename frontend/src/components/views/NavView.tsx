"use client"

import React, { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { useStore } from "@/store/useStore"
import { BaseChart } from "@/components/charts/BaseChart" 
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Skeleton } from "@/components/ui/skeleton"
import { Switch } from "@/components/ui/switch"
import { getCategoricalColor } from "@/lib/colors"
import { API_BASE_URL } from "@/lib/utils"



export function NavView() {
  const { selectedIndices, benchmark } = useStore();
  const [zoomEnabled, setZoomEnabled] = useState(false);
  const navPeriods = ["Last Month", "YTD", "1 Yr", "3 Yr", "5 Yr", "10 Yr", "20 Yr"];
  const [activeWindow, setActiveWindow] = useState("5 Yr");

  const { data: priceData, isLoading: loadingPrice } = useQuery({
    queryKey: ["navData", "price", selectedIndices, benchmark, activeWindow],
    queryFn: async () => {
      const res = await fetch(`${API_BASE_URL}/api/nav-data`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ metric: "nav", periods: [activeWindow], indices: selectedIndices, benchmark })
      });
      return res.json();
    },
    enabled: selectedIndices.length > 0
  });

  const { data: ddData, isLoading: loadingDd } = useQuery({
    queryKey: ["navData", "drawdown", selectedIndices, benchmark, activeWindow],
    queryFn: async () => {
      const res = await fetch(`${API_BASE_URL}/api/nav-data`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ metric: "drawdown", periods: [activeWindow], indices: selectedIndices, benchmark })
      });
      return res.json();
    },
    enabled: selectedIndices.length > 0
  });

  if (loadingPrice || loadingDd) return <div className="p-8"><Skeleton className="h-[600px] w-full rounded-3xl" /></div>;

  const plotPrice = priceData?.map((trace: any) => {
    const isBenchmark = trace.name === benchmark;
    const { hex: lineColor } = getCategoricalColor(trace.name);
    return {
      x: trace.x, y: trace.y, name: trace.name, type: 'scatter', mode: 'lines',
      fill: isBenchmark ? 'tozeroy' : 'none',
      fillcolor: isBenchmark ? 'rgba(37, 99, 235, 0.05)' : 'none',
      line: { width: isBenchmark ? 2.5 : 1.5, shape: 'spline', smoothing: 1.3, color: isBenchmark ? '#2563eb' : lineColor },
      hovertemplate: '<b>%{fullData.name}</b><br>Value: %{y:.2f}<extra></extra>'
    };
  });

  const plotDd = ddData?.map((trace: any) => {
    const isBenchmark = trace.name === benchmark;
    const { hex: lineColor } = getCategoricalColor(trace.name);
    return {
      x: trace.x, y: trace.y, name: trace.name, type: 'scatter', mode: 'lines',
      fill: 'tozeroy',
      fillcolor: isBenchmark ? 'rgba(220, 38, 38, 0.1)' : 'rgba(100, 116, 139, 0.05)',
      line: { width: isBenchmark ? 2 : 1, color: isBenchmark ? '#dc2626' : lineColor },
      hovertemplate: '<b>%{fullData.name}</b><br>Drawdown: %{y:.2f}%<extra></extra>'
    };
  });

  return (
    <div className="space-y-12 pb-20">
      <div className="bg-white dark:bg-[#09090b] border dark:border-slate-800 rounded-3xl p-8 shadow-sm">
        <Tabs value={activeWindow} onValueChange={setActiveWindow} className="w-full">
          <div className="flex flex-col md:flex-row justify-between items-center gap-4 mb-10">
            <div>
              <h2 className="text-xl font-bold tracking-tight">Price Chart</h2>
              <p className="text-[10px] text-slate-400 font-black uppercase mt-1 tracking-widest">Rebased Performance</p>
            </div>
            
            <div className="flex items-center gap-6">
              <div className="flex items-center gap-2 px-3 py-1 bg-slate-50 dark:bg-slate-900 rounded-full border border-slate-100 dark:border-slate-800">
                <span className="text-[9px] font-bold text-slate-400 uppercase tracking-widest">Interactive</span>
                <Switch checked={zoomEnabled} onCheckedChange={setZoomEnabled} className="scale-75 data-[state=checked]:bg-blue-600" />
              </div>
              <TabsList className="segmented-tabs-list !mb-0">
                {navPeriods.map(p => <TabsTrigger key={p} value={p} className="segmented-tab-trigger">{p}</TabsTrigger>)}
              </TabsList>
            </div>
          </div>
        </Tabs>
        <div className="h-[450px]">
          <BaseChart data={plotPrice} zoomEnabled={zoomEnabled} layout={{ hovermode: 'x unified', xaxis: { showgrid: false }, yaxis: { side: "right" } }} />
        </div>
      </div>

      <div className="bg-white dark:bg-[#09090b] border dark:border-slate-800 rounded-3xl p-8 shadow-sm">
        <div className="mb-10">
          <h2 className="text-xl font-bold tracking-tight">Drawdown Chart</h2>
          <p className="text-[10px] text-slate-400 font-black uppercase mt-1 tracking-widest">Percentage Drop from Peak</p>
        </div>
        <div className="h-[350px]">
          <BaseChart data={plotDd} zoomEnabled={zoomEnabled} layout={{ hovermode: 'x unified', xaxis: { showgrid: false }, yaxis: { side: "right" } }} />
        </div>
      </div>
    </div>
  );
}