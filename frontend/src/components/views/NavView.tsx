"use client"

import React, { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { useStore } from "@/store/useStore"
import { BaseChart } from "@/components/charts/BaseChart" // Revert to BaseChart for Plotly
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Skeleton } from "@/components/ui/skeleton"
import { getCategoricalColor } from "@/lib/colors" // For consistent line colors

export function NavView() {
  const { selectedIndices, benchmark } = useStore();
  const navPeriods = ["Last Month", "YTD", "1 Yr", "3 Yr", "5 Yr", "10 Yr", "20 Yr"];
  const [activeWindow, setActiveWindow] = useState("5 Yr");

  // Fetch Price Data
  const { data: priceData, isLoading: loadingPrice } = useQuery({
    queryKey: ["navData", "price", selectedIndices, benchmark, activeWindow],
    queryFn: async () => {
      const res = await fetch("http://localhost:8000/api/nav-data", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ metric: "nav", periods: [activeWindow], indices: selectedIndices, benchmark })
      });
      return res.json();
    },
    enabled: selectedIndices.length > 0
  });

  // Fetch Drawdown Data
  const { data: ddData, isLoading: loadingDd } = useQuery({
    queryKey: ["navData", "drawdown", selectedIndices, benchmark, activeWindow],
    queryFn: async () => {
      const res = await fetch("http://localhost:8000/api/nav-data", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ metric: "drawdown", periods: [activeWindow], indices: selectedIndices, benchmark })
      });
      return res.json();
    },
    enabled: selectedIndices.length > 0
  });

  if (loadingPrice || loadingDd) return <Skeleton className="h-[600px] w-full rounded-3xl" />;
  if (!priceData || priceData.length === 0) return <div className="p-8 text-slate-500">No data available for this period.</div>;

  // Prepare data for Plotly's format
  const plotPrice = priceData?.map((trace: any) => {
    const isBenchmark = trace.name === benchmark;
    const { hex: lineColor } = getCategoricalColor(trace.name); // Use consistent color
    return {
      x: trace.x,
      y: trace.y,
      name: trace.name,
      type: 'scatter',
      mode: 'lines',
      fill: isBenchmark ? 'tozeroy' : 'none',
      fillcolor: isBenchmark ? 'rgba(37, 99, 235, 0.05)' : 'rgba(100, 116, 139, 0.03)',
      line: { 
          width: isBenchmark ? 2.5 : 1.5, 
          shape: 'spline', 
          smoothing: 1.3, 
          color: isBenchmark ? '#2563eb' : lineColor 
      },
      // Clean hover template for Plotly
      hovertemplate: '<b>%{fullData.name}</b><br>Date: %{x}<br>Value: %{y:.2f}<extra></extra>'
    };
  });

  const plotDd = ddData?.map((trace: any) => {
    const isBenchmark = trace.name === benchmark;
    const { hex: lineColor } = getCategoricalColor(trace.name); // Use consistent color
    return {
      x: trace.x,
      y: trace.y,
      name: trace.name,
      type: 'scatter',
      mode: 'lines',
      fill: 'tozeroy', // Drawdown is always filled to zero
      fillcolor: isBenchmark ? 'rgba(220, 38, 38, 0.1)' : 'rgba(100, 116, 139, 0.05)',
      line: { 
          width: isBenchmark ? 2 : 1, 
          color: isBenchmark ? '#dc2626' : lineColor 
      },
      // Clean hover template for Plotly
      hovertemplate: '<b>%{fullData.name}</b><br>Date: %{x}<br>Drawdown: %{y:.2f}%<extra></extra>'
    };
  });

  return (
    <div className="space-y-12 pb-20">
      
      {/* 1. PRICE CHART */}
      <div className="bg-white dark:bg-[#09090b] border dark:border-slate-800 rounded-3xl p-8 shadow-sm">
        <Tabs value={activeWindow} onValueChange={setActiveWindow} className="w-full">
          <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-10">
            <div>
              <h2 className="text-xl font-bold tracking-tight">Price Chart</h2>
              <p className="text-[10px] text-slate-400 font-black uppercase tracking-widest mt-1">Rebased to 100 at start of period</p>
            </div>
            <TabsList className="segmented-tabs-list !mb-0">
              {navPeriods.map(p => (
                <TabsTrigger key={p} value={p} className="segmented-tab-trigger">{p}</TabsTrigger>
              ))}
            </TabsList>
          </div>
        </Tabs>
        
        <div className="h-[450px]">
          <BaseChart 
            data={plotPrice} 
            layout={{ 
                hovermode: 'x unified', 
                xaxis: { showgrid: false }, 
                yaxis: { side: "right", title: "Index Value" } 
            }} 
          />
        </div>
      </div>

      {/* 2. DRAWDOWN CHART */}
      <div className="bg-white dark:bg-[#09090b] border dark:border-slate-800 rounded-3xl p-8 shadow-sm">
        <div className="mb-10">
          <h2 className="text-xl font-bold tracking-tight">Drawdown from Peak</h2>
          <p className="text-[10px] text-slate-400 font-black uppercase tracking-widest mt-1">Percentage Drop within selected window</p>
        </div>
        <div className="h-[350px]">
          <BaseChart data={plotDd} layout={{ hovermode: 'x unified', xaxis: { showgrid: false }, yaxis: { side: "right", title: "Drawdown %" } }} />
        </div>
      </div>

    </div>
  );
}