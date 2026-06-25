"use client"

import React, { useState, useMemo, useCallback } from "react"
import { useQuery } from "@tanstack/react-query"
import { useStore } from "@/store/useStore"
import { BaseChart } from "@/components/charts/BaseChart" 
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Skeleton } from "@/components/ui/skeleton"
import { Switch } from "@/components/ui/switch"
import { getCategoricalColor } from "@/lib/colors"
import { API_BASE_URL } from "@/lib/utils"

export function NavView() {
  const { selectedIndices, benchmark, referenceDate } = useStore();
  
  // 1. ALL HOOKS MUST BE AT THE TOP
  const [zoomEnabled, setZoomEnabled] = useState(false);
  const [activeWindow, setActiveWindow] = useState("5 Yr");
  const [hoveredName, setHoveredName] = useState<string | null>(null);

  const navPeriods = ["Last Month", "YTD", "1 Yr", "3 Yr", "5 Yr", "10 Yr", "20 Yr"];

  // Fetching Data
  const { data: priceData, isLoading: loadingPrice } = useQuery({
    queryKey: ["navData", "price", selectedIndices, benchmark, activeWindow, referenceDate],
    queryFn: async () => {
      const res = await fetch(`${API_BASE_URL}/api/nav-data`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ metric: "nav", periods: [activeWindow], indices: selectedIndices, benchmark, reference_date: referenceDate })
      });
      return res.json();
    },
    enabled: selectedIndices.length > 0
  });

  const { data: ddData, isLoading: loadingDd } = useQuery({
    queryKey: ["navData", "drawdown", selectedIndices, benchmark, activeWindow, referenceDate],
    queryFn: async () => {
      const res = await fetch(`${API_BASE_URL}/api/nav-data`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ metric: "drawdown", periods: [activeWindow], indices: selectedIndices, benchmark, reference_date: referenceDate })
      });
      return res.json();
    },
    enabled: selectedIndices.length > 0
  });

  // SPOTLIGHT LOGIC: Price Chart
  const plotPrice = useMemo(() => {
    if (!priceData || !Array.isArray(priceData)) return [];
    
    return priceData.map((trace: any) => {
      const isBenchmark = trace.name === benchmark;
      const isHovered = hoveredName === trace.name;
      const somethingIsHovered = hoveredName !== null;
      
      const opacity = !somethingIsHovered ? 1 : (isHovered ? 1 : 0.15);
      const lineWidth = isHovered ? 4 : (isBenchmark ? 2.5 : 1.5);
      const { hex: lineColor } = getCategoricalColor(trace.name);

      return {
        ...trace,
        type: 'scatter',
        mode: 'lines',
        opacity: opacity,
        line: { 
          width: lineWidth, 
          shape: 'spline', 
          smoothing: 1.3, 
          color: isBenchmark ? '#2563eb' : lineColor 
        },
        fill: isBenchmark && !somethingIsHovered ? 'tozeroy' : 'none',
        fillcolor: 'rgba(37, 99, 235, 0.05)',
        hovertemplate: '<b>%{fullData.name}</b><br>Value: <b>%{y:.2f}</b><extra></extra>'
      };
    });
  }, [priceData, benchmark, hoveredName]);

  // SPOTLIGHT LOGIC: Drawdown Chart
  const plotDd = useMemo(() => {
    if (!ddData || !Array.isArray(ddData)) return [];

    return ddData.map((trace: any) => {
      const isHovered = hoveredName === trace.name;
      const somethingIsHovered = hoveredName !== null;
      const opacity = !somethingIsHovered ? 1 : (isHovered ? 1 : 0.15);
      const { hex: lineColor } = getCategoricalColor(trace.name);

      return {
        ...trace,
        type: 'scatter',
        mode: 'lines',
        opacity: opacity,
        fill: 'tozeroy',
        fillcolor: trace.name === benchmark ? 'rgba(220, 38, 38, 0.1)' : 'rgba(100, 116, 139, 0.05)',
        line: { 
          width: isHovered ? 3 : 1, 
          color: trace.name === benchmark ? '#dc2626' : lineColor 
        },
        hovertemplate: '<b>%{fullData.name}</b><br>Drawdown: <b>%{y:.2f}%</b><extra></extra>'
      };
    });
  }, [ddData, benchmark, hoveredName]);

  // Event Handlers
  const handleHover = useCallback((event: any) => {
    if (event.points && event.points[0]) {
      setHoveredName(event.points[0].fullData.name);
    }
  }, []);

  const handleUnhover = useCallback(() => {
    setHoveredName(null);
  }, []);

  // 2. CONDITIONAL RETURNS HAPPEN HERE (AFTER ALL HOOKS)
  if (loadingPrice || loadingDd) return <div className="p-8"><Skeleton className="h-[600px] w-full rounded-3xl" /></div>;
  if (!priceData || priceData.length === 0) return <div className="p-20 text-center text-slate-400 font-bold uppercase tracking-widest text-xs">No Data for this Period</div>;

  return (
    <div className="space-y-12 pb-20">
      {/* 1. PRICE CHART */}
      <div className="bg-white dark:bg-[#09090b] border dark:border-slate-800 rounded-3xl p-8 shadow-sm">
        <Tabs value={activeWindow} onValueChange={setActiveWindow} className="w-full">
          <div className="flex flex-col md:flex-row justify-between items-center gap-4 mb-10">
            <div>
              <h2 className="text-xl font-bold tracking-tight text-slate-900 dark:text-white">Price Chart</h2>
              <p className="text-[10px] text-slate-400 font-black uppercase mt-1 tracking-widest">Rebased Performance</p>
            </div>
            
            <div className="flex items-center gap-6">
              <div className="flex items-center gap-2 px-3 py-1 bg-slate-50 dark:bg-slate-900 rounded-full border border-slate-100 dark:border-slate-800">
                <span className="text-[9px] font-bold text-slate-400 uppercase tracking-widest">Interactive</span>
                <Switch checked={zoomEnabled} onCheckedChange={setZoomEnabled} className="scale-75 data-[state=checked]:bg-blue-600 shadow-none" />
              </div>
              <TabsList className="segmented-tabs-list !mb-0 shrink-0">
                {navPeriods.map(p => <TabsTrigger key={p} value={p} className="segmented-tab-trigger">{p}</TabsTrigger>)}
              </TabsList>
            </div>
          </div>
        </Tabs>
        <div className="h-[450px]">
          <BaseChart 
            data={plotPrice} 
            zoomEnabled={zoomEnabled} 
            onHover={handleHover}
            onUnhover={handleUnhover}
            layout={{ hovermode: 'closest', xaxis: { showgrid: false }, yaxis: { side: "right" } }} 
          />
        </div>
      </div>

      {/* 2. DRAWDOWN CHART */}
      <div className="bg-white dark:bg-[#09090b] border dark:border-slate-800 rounded-3xl p-8 shadow-sm">
        <div className="mb-10 flex justify-between items-center">
          <div>
            <h2 className="text-xl font-bold tracking-tight text-slate-900 dark:text-white">Drawdown Chart</h2>
            <p className="text-[10px] text-slate-400 font-black uppercase mt-1 tracking-widest">Percentage Drop from Peak</p>
          </div>
        </div>
        <div className="h-[350px]">
          <BaseChart 
            data={plotDd} 
            zoomEnabled={zoomEnabled} 
            onHover={handleHover}
            onUnhover={handleUnhover}
            layout={{ hovermode: 'closest', xaxis: { showgrid: false }, yaxis: { side: "right" } }} 
          />
        </div>
      </div>
    </div>
  );
}