"use client"

import React, { useMemo, useEffect, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { useStore } from "@/store/useStore"
import { DataTable } from "@/components/DataTable"
import { PeriodBarChart } from "@/components/charts/PeriodBarChart"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { motion, AnimatePresence } from "framer-motion"
import { useSearchParams, useRouter, usePathname } from "next/navigation"
import { Download } from "lucide-react" 
import { Button } from "@/components/ui/button"
import { Switch } from "@/components/ui/switch"
import { exportToExcel } from "@/lib/export"
import { LoadingSpinner } from "@/components/ui/LoadingSpinner"
import { API_BASE_URL } from "@/lib/utils"

export function MetricSection({ title, metric, chartLabel, colorMode = "categorical" }: any) {
  const { selectedIndices, benchmark, periods } = useStore();
  const [zoomEnabled, setZoomEnabled] = useState(false);
  
  const searchParams = useSearchParams()
  const pathname = usePathname()
  const { replace } = useRouter()

  const periodKey = `${metric}_p`
  const activePeriodFromUrl = searchParams.get(periodKey)

  const { data, isLoading, isError } = useQuery({
    queryKey: ["metrics", metric, selectedIndices, benchmark, periods],
    queryFn: async () => {
      const res = await fetch(`${API_BASE_URL}/api/metrics`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ metric, periods, indices: selectedIndices, benchmark })
      });
      if (!res.ok) throw new Error("Backend error");
      return res.json();
    },
    enabled: selectedIndices.length > 0,
    placeholderData: (prev) => prev,
  });

  // --- LOGIC: Filter out Rolling 3-Yr Avg for Max Drawdown ---
  const rows = useMemo(() => {
    let rawRows = [];
    if (Array.isArray(data)) rawRows = data;
    else if (data && typeof data === 'object' && Array.isArray((data as any).data)) rawRows = (data as any).data;
    else return [];

    // FIX: Specifically remove 'Rolling 3-Yr Avg' row if the metric is 'mdd'
    if (metric === "mdd") {
      return rawRows.filter((r: any) => r.Period !== "Rolling 3-Yr Avg");
    }
    return rawRows;
  }, [data, metric]);

  // Handle active period state and fallbacks
  const activePeriod = useMemo(() => {
    if (rows.length === 0) return "1 Yr";
    const exists = rows.some((r: any) => r.Period === activePeriodFromUrl);
    return exists ? activePeriodFromUrl : rows[0].Period;
  }, [rows, activePeriodFromUrl]);

  const handlePeriodChange = (newPeriod: string) => {
    const params = new URLSearchParams(window.location.search)
    params.set(periodKey, newPeriod)
    window.history.replaceState(null, '', `?${params.toString()}`)
    window.dispatchEvent(new Event('popstate'))
  }

  const handleDownload = () => {
    if (rows.length > 0) exportToExcel(rows, `${title.replace(/\s+/g, '_')}_Report`);
  }

  const activeChartData = useMemo(() => {
    if (rows.length === 0) return [];
    const periodRow = rows.find((row: any) => row.Period === activePeriod) || rows[0];
    if (!periodRow) return [];

    return Object.entries(periodRow)
      .filter(([key]) => key !== 'Period' && key !== 'Range')
      .map(([key, value]) => ({ indexName: key, value: value as number }))
      .filter(d => d.value !== null && d.value !== undefined);
  }, [rows, activePeriod]);

  if (isLoading && !data) {
    return (
      <div className="w-full py-20 border-b border-slate-100 dark:border-slate-800 flex flex-col items-center justify-center gap-6">
        <LoadingSpinner />
        <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest text-center">Calculating {title}...</p>
      </div>
    );
  }

  if (isError || rows.length === 0) return null;

  const columns = Object.keys(rows[0])
    .filter(key => key !== 'Range')
    .map(key => ({ 
      accessorKey: key, 
      header: key, 
      cell: ({ row }: any) => {
        const val = row.getValue(key);
        const range = row.original.Range;
        if (key === 'Period') return (
          <div className="p-3 flex flex-col leading-tight">
            <span className="font-bold text-slate-700 dark:text-slate-200">{val as string}</span>
            <span className="text-[9px] text-slate-400 font-medium mt-0.5 tabular-nums">{range}</span>
          </div>
        );
        const num = val as number | null;
        if (num === null || typeof num !== 'number') return <div className="p-3 text-right text-slate-400">—</div>;
        let color = "text-slate-600 dark:text-slate-300";
        if (metric === 'beta') color = num > 1.1 ? "text-red-600" : num < 0.9 ? "text-blue-600" : "text-slate-600";
        else if (metric === 'mdd' || num < 0) color = "text-red-600 font-bold";
        else if (num > 0) color = "text-green-600 font-bold";
        return <div className={`p-3 text-right font-mono font-medium ${color}`}>{num.toFixed(2)}</div>
      }
    }));

  const values = activeChartData.map(d => d.value);
  const maxVal = values.length > 0 ? Math.max(...values) : 0;
  const minVal = values.length > 0 ? Math.min(...values) : 0;
  const avgVal = values.length > 0 ? values.reduce((a, b) => a + b, 0) / values.length : 0;
  const bestIndex = activeChartData.find(d => d.value === maxVal)?.indexName || "—";
  const worstIndex = activeChartData.find(d => d.value === minVal)?.indexName || "—";

  return (
    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }} className="space-y-6 py-10 border-b border-slate-100 dark:border-slate-800 last:border-0">
      <div className="flex items-center justify-between border-b border-slate-50 dark:border-slate-900 pb-4">
        <div className="flex items-center gap-3">
          <div className="h-6 w-1 bg-blue-600 rounded-full" />
          <h3 className="text-[11px] font-black uppercase tracking-[0.2em] text-slate-500">{title}</h3>
        </div>
        <Button variant="outline" size="sm" onClick={handleDownload} className="h-8 text-[10px] font-bold uppercase tracking-widest border-slate-200 dark:border-slate-800 hover:bg-blue-50 dark:hover:bg-blue-900/20 hover:text-blue-600 transition-all shadow-sm">
          <Download className="w-3 h-3 mr-2" /> Excel
        </Button>
      </div>

      <div className="screener-table bg-white dark:bg-slate-900/40 rounded-xl border border-slate-200 dark:border-slate-800 p-2 shadow-sm overflow-x-auto [&_td]:p-0 [&_td]:overflow-hidden">
        <DataTable columns={columns} data={rows} />
      </div>

      <div className="bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm overflow-hidden">
        <Tabs defaultValue="chart-view" className="w-full">
          <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-8">
            <div className="flex items-center gap-4">
              <TabsList className="segmented-tabs-list !mb-0">
                <TabsTrigger value="chart-view" className="segmented-tab-trigger">Chart View</TabsTrigger>
                <TabsTrigger value="stats-view" className="segmented-tab-trigger">Summary</TabsTrigger>
              </TabsList>
              <div className="flex items-center gap-2 px-3 py-1 bg-slate-50 dark:bg-slate-900 rounded-full border border-slate-100 dark:border-slate-800">
                <span className="text-[9px] font-bold text-slate-400 uppercase tracking-widest">Interactive</span>
                <Switch checked={zoomEnabled} onCheckedChange={setZoomEnabled} className="scale-75 data-[state=checked]:bg-blue-600" />
              </div>
            </div>
            
            <div className="flex items-center gap-2 overflow-x-auto hide-scrollbar max-w-full">
              <div className="segmented-tabs-list !mb-0 shrink-0">
                {rows.map((row: any) => (
                  <button key={row.Period} type="button" onClick={() => handlePeriodChange(row.Period)} className={`segmented-tab-trigger ${activePeriod === row.Period ? '!bg-white dark:!bg-slate-800 !text-blue-600 dark:!text-blue-400 shadow-sm' : ''}`}>{row.Period}</button>
                ))}
              </div>
            </div>
          </div>
          
          <AnimatePresence mode="wait">
            <TabsContent value="chart-view" key={`chart-${activePeriod}`} className="h-[400px] mt-0 focus-visible:outline-none">
                <PeriodBarChart data={activeChartData} zoomEnabled={zoomEnabled} colorMode={colorMode} />
            </TabsContent>
            {/* ... StatsContent same as before ... */}
          </AnimatePresence>
        </Tabs>
      </div>
    </motion.div>
  );
}