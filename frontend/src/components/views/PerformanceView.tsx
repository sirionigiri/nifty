"use client"

import React, { useState, useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { useStore } from "@/store/useStore"
import { DataTable } from "@/components/DataTable"
import { PeriodBarChart } from "@/components/charts/PeriodBarChart"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Skeleton } from "@/components/ui/skeleton"

export function PerformanceView() {
  const { selectedIndices, benchmark, periods } = useStore();
  const [activePeriod, setActivePeriod] = useState("1 Yr");

  const { data, isLoading } = useQuery({
    queryKey: ["metrics", "cagr", selectedIndices, benchmark, periods],
    queryFn: async () => {
      const res = await fetch("http://localhost:8000/api/metrics", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ metric: "cagr", periods, indices: selectedIndices, benchmark })
      });
      return res.json();
    },
    enabled: selectedIndices.length > 0,
  });

  const columns = useMemo(() => {
    if (!data || data.length === 0) return [];
    return Object.keys(data[0]).map(key => ({
      accessorKey: key,
      header: key,
      cell: ({ row }: any) => {
        const val = row.getValue(key);
        if (key === 'Period') return <span className="font-bold text-slate-700 dark:text-slate-300">{val as string}</span>;
        const num = val as number | null;
        return (
          <div className={`text-right font-mono font-medium ${num && num > 0 ? 'text-green-600' : 'text-red-600'}`}>
            {num !== null ? (num > 0 ? `+${num.toFixed(2)}` : num.toFixed(2)) : "—"}
          </div>
        )
      }
    }));
  }, [data]);

  const activeChartData = useMemo(() => {
    if (!data || data.length === 0) return [];
    const periodRow = data.find((row: any) => row.Period === activePeriod);
    if (!periodRow) return [];
    return Object.entries(periodRow)
      .filter(([key]) => key !== 'Period')
      .map(([key, value]) => ({ indexName: key, value: value as number }));
  }, [data, activePeriod]);

  if (isLoading) return <Skeleton className="h-[600px] w-full rounded-2xl" />;

  return (
    <div className="space-y-12 pb-20">
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <div className="h-6 w-1 bg-blue-600 rounded-full" />
          <h3 className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-500">
            CAGR — Annualised Returns (%)
          </h3>
        </div>
        <div className="screener-table bg-white dark:bg-slate-900/40 border dark:border-slate-800 rounded-xl p-2 shadow-sm overflow-hidden">
          <DataTable columns={columns} data={data} />
        </div>
      </div>

      <div className="bg-white dark:bg-slate-950 border dark:border-slate-800 rounded-2xl p-8 shadow-sm space-y-6">
        <Tabs value={activePeriod} onValueChange={setActivePeriod} className="w-full">
          <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
            <TabsList className="segmented-tabs-list">
              {periods.map((p) => (
                <TabsTrigger key={p} value={p} className="segmented-tab-trigger">{p}</TabsTrigger>
              ))}
            </TabsList>
            <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">
              CAGR Breakdown — {activePeriod}
            </span>
          </div>
          <div className="h-[450px]">
            <PeriodBarChart data={activeChartData} title="" colorMode="conditional" />
          </div>
        </Tabs>
      </div>
    </div>
  );
}