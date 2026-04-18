"use client"

import React, { useMemo, useEffect } from "react"
import { useQuery } from "@tanstack/react-query"
import { useStore } from "@/store/useStore"
import { DataTable } from "@/components/DataTable"
import { PeriodBarChart } from "@/components/charts/PeriodBarChart"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { motion, AnimatePresence } from "framer-motion"
import { useSearchParams, useRouter, usePathname } from "next/navigation"

export function MetricSection({ title, metric, chartLabel, colorMode = "categorical" }: any) {
  const { selectedIndices, benchmark, periods } = useStore();
  
  const searchParams = useSearchParams()
  const pathname = usePathname()
  const { replace } = useRouter()

  // Create a unique key for this metric in the URL (e.g., ?vol_p=1+Yr)
  const periodKey = `${metric}_p`
  const activePeriod = searchParams.get(periodKey) || "1 Yr"

  const { data, isLoading } = useQuery({
    queryKey: ["metrics", metric, selectedIndices, benchmark, periods],
    queryFn: async () => {
      const res = await fetch("http://localhost:8000/api/metrics", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ metric, periods, indices: selectedIndices, benchmark })
      });
      return res.json();
    },
    enabled: selectedIndices.length > 0,
  });

  const handlePeriodChange = (newPeriod: string) => {
    const params = new URLSearchParams(searchParams)
    params.set(periodKey, newPeriod)
    replace(`${pathname}?${params.toString()}`, { scroll: false })
  }

  // Effect to ensure URL always has a default if missing
  useEffect(() => {
    if (!searchParams.get(periodKey) && data && data.length > 0) {
       // We don't force replace here to avoid URL churn, 
       // the 'activePeriod' constant above handles the fallback.
    }
  }, [data, searchParams, periodKey])

  const activeChartData = useMemo(() => {
    if (!data || data.length === 0) return [];
    const periodRow = data.find((row: any) => row.Period === activePeriod) || data[0];
    return Object.entries(periodRow)
      .filter(([key]) => key !== 'Period')
      .map(([key, value]) => ({ indexName: key, value: value as number }))
      .filter(d => d.value !== null && d.value !== undefined);
  }, [data, activePeriod]);

  if (isLoading || !data || data.length === 0) return null;

  const columns = Object.keys(data[0]).map(key => ({ 
    accessorKey: key, 
    header: key, 
    cell: ({ row }: any) => {
      const val = row.getValue(key);
      if (key === 'Period') return <div className="p-3 font-bold text-slate-700 dark:text-slate-300">{val as string}</div>;
      const num = val as number | null;
      if (num === null) return <div className="p-3 text-right text-slate-400">—</div>;
      let color = "text-slate-600 dark:text-slate-300";
      if (metric === 'beta') {
          color = num > 1.1 ? "text-red-600" : num < 0.9 ? "text-blue-600" : "text-slate-600 dark:text-slate-300";
      } else if (metric === 'mdd' || num < 0) {
          color = "text-red-600";
      } else if (num > 0) {
          color = "text-green-600";
      }
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
    <motion.div 
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      className="space-y-6 py-10 border-b border-slate-100 dark:border-slate-800 last:border-0"
    >
      <div className="flex items-center gap-3">
        <div className="h-6 w-1 bg-blue-600 rounded-full" />
        <h3 className="text-xs font-black uppercase tracking-[0.2em] text-slate-500">{title}</h3>
      </div>

      <div className="screener-table bg-white dark:bg-slate-900/40 rounded-xl border border-slate-200 dark:border-slate-800 p-2 shadow-sm overflow-x-auto [&_td]:p-0 [&_td]:overflow-hidden">
        <DataTable columns={columns} data={data} />
      </div>

      <div className="bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm overflow-hidden">
        <Tabs defaultValue="chart-view" className="w-full">
          <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
            <TabsList className="segmented-tabs-list !mb-0">
              <TabsTrigger value="chart-view" className="segmented-tab-trigger">Chart View</TabsTrigger>
              <TabsTrigger value="stats-view" className="segmented-tab-trigger">Summary</TabsTrigger>
            </TabsList>
            
            <div className="flex items-center gap-2 overflow-x-auto hide-scrollbar">
              <div className="segmented-tabs-list !mb-0 shrink-0">
                {data.map((row: any) => (
                  <button 
                    key={row.Period}
                    onClick={() => handlePeriodChange(row.Period)}
                    className={`segmented-tab-trigger ${activePeriod === row.Period ? '!bg-white dark:!bg-slate-800 !text-blue-600 dark:!text-blue-400 shadow-sm' : ''}`}
                  >
                    {row.Period}
                  </button>
                ))}
              </div>
            </div>
          </div>
          
          <AnimatePresence mode="wait">
            <TabsContent value="chart-view" key={`chart-${activePeriod}`} className="h-[400px] mt-0 focus-visible:outline-none">
               <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="h-full">
                <PeriodBarChart data={activeChartData} title="" colorMode={colorMode} />
               </motion.div>
            </TabsContent>

            <TabsContent value="stats-view" key={`stats-${activePeriod}`} className="h-[400px] mt-0 focus-visible:outline-none flex items-center justify-center">
               <motion.div 
                initial={{ opacity: 0, scale: 0.98 }} 
                animate={{ opacity: 1, scale: 1 }} 
                className="grid grid-cols-2 gap-8 w-full max-w-3xl"
               >
                  <div className="bg-slate-50 dark:bg-slate-900 p-6 rounded-2xl border border-slate-100 dark:border-slate-800 flex flex-col justify-center">
                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">Average {chartLabel}</p>
                    <p className="text-3xl font-mono font-black text-slate-700 dark:text-slate-200">{avgVal.toFixed(2)}</p>
                    <p className="text-xs text-slate-500 mt-2 font-medium">For {activePeriod}</p>
                  </div>
                  <div className="bg-slate-50 dark:bg-slate-900 p-6 rounded-2xl border border-slate-100 dark:border-slate-800 flex flex-col justify-center">
                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">Spread (Max - Min)</p>
                    <p className="text-3xl font-mono font-black text-slate-700 dark:text-slate-200">{Math.abs(maxVal - minVal).toFixed(2)}</p>
                    <p className="text-xs text-slate-500 mt-2 font-medium">Difference between best and worst</p>
                  </div>
                  <div className="bg-green-50 dark:bg-green-950/30 p-6 rounded-2xl border border-green-100 dark:border-green-900/50 flex flex-col justify-center">
                    <p className="text-[10px] font-bold text-green-600/70 dark:text-green-500/70 uppercase tracking-widest mb-1">Highest Value</p>
                    <p className="text-3xl font-mono font-black text-green-600 dark:text-green-500">{maxVal.toFixed(2)}</p>
                    <p className="text-xs text-green-700/70 dark:text-green-400/70 mt-2 font-bold truncate" title={bestIndex}>{bestIndex}</p>
                  </div>
                  <div className="bg-red-50 dark:bg-red-950/30 p-6 rounded-2xl border border-red-100 dark:border-red-900/50 flex flex-col justify-center">
                    <p className="text-[10px] font-bold text-red-600/70 dark:text-red-500/70 uppercase tracking-widest mb-1">Lowest Value</p>
                    <p className="text-3xl font-mono font-black text-red-600 dark:text-red-500">{minVal.toFixed(2)}</p>
                    <p className="text-xs text-red-700/70 dark:text-red-400/70 mt-2 font-bold truncate" title={worstIndex}>{worstIndex}</p>
                  </div>
               </motion.div>
            </TabsContent>
          </AnimatePresence>
        </Tabs>
      </div>
    </motion.div>
  );
}