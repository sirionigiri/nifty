"use client"

import React, { useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { useStore } from "@/store/useStore"
import { DataTable } from "@/components/DataTable"
import { getCategoricalColor } from "@/lib/colors"
import { Skeleton } from "@/components/ui/skeleton"
import { Download } from "lucide-react"
import { Button } from "@/components/ui/button"
import { exportToExcel } from "@/lib/export"

export function RankingsTable() {
  const { selectedIndices, benchmark } = useStore()


  const handleDownload = () => {
    if (!data) return;
    exportToExcel(data, "Calendar_Year_Rankings");
  }


  const { data, isLoading } = useQuery({
    queryKey: ["rankings", selectedIndices],
    queryFn: async () => {
      const res = await fetch("http://localhost:8000/api/rankings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ indices: selectedIndices, benchmark, metric: "rank", periods: [] })
      })
      return res.json()
    },
    enabled: selectedIndices.length > 0
  })

  const columns = useMemo(() => {
    if (!data || !Array.isArray(data) || data.length === 0) return [];

    // FIX: Find ALL unique keys across ALL rows
    const allKeys = new Set<string>();
    data.forEach(row => {
      Object.keys(row).forEach(key => allKeys.add(key));
    });

    return Array.from(allKeys)
      .sort((a, b) => {
        if (a === 'Year') return -1;
        if (b === 'Year') return 1;
        const numA = parseInt(a.replace('Rank ', ''));
        const numB = parseInt(b.replace('Rank ', ''));
        return numA - numB;
      })
      .map(key => ({
        accessorKey: key,
        header: key,
        cell: ({ row }: any) => {
          const val = row.getValue(key);
          if (!val) return <div className="p-2 text-slate-300">—</div>;
          
          if (key === 'Year') {
            return <div className="p-2 font-bold text-slate-500 tabular-nums">{val}</div>;
          }

          const { hex, bg } = getCategoricalColor(val as string);
          return (
            <div className="p-1">
              <div 
                style={{ color: hex, backgroundColor: bg, borderColor: hex + '44' }} 
                className="px-2 py-1.5 rounded border text-[10px] font-bold text-center shadow-sm truncate min-w-[120px]"
              >
                {val}
              </div>
            </div>
          );
        }
      }));
  }, [data]);

  if (isLoading) return <Skeleton className="h-64 w-full rounded-xl" />;
  
  if (!data || data.length === 0) {
    return (
      <div className="p-12 border-2 border-dashed rounded-xl text-center">
        <p className="text-sm text-slate-500 font-medium tracking-tight">
          Select indices in the sidebar to generate rankings.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4 py-10">
      <div className="flex items-center gap-3">
        <div className="h-6 w-1 bg-indigo-500 rounded-full" />
        <h3 className="text-xs font-black uppercase tracking-[0.2em] text-slate-500">
            Calendar Year Rankings (Relative)
        </h3>
      </div>

      <Button 
          variant="outline" 
          size="sm" 
          onClick={handleDownload}
          className="h-8 text-[10px] font-bold uppercase tracking-widest border-slate-200 dark:border-slate-800"
        >
          <Download className="w-3 h-3 mr-2" /> Excel
        </Button>

      <div className="screener-table bg-white dark:bg-slate-900/40 rounded-xl border border-slate-200 dark:border-slate-800 p-2 shadow-sm overflow-x-auto">
        <DataTable columns={columns} data={data} />
      </div>
    </div>
  );
}