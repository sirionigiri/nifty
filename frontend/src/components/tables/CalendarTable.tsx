"use client"

import React, { useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { useStore } from "@/store/useStore"
import { DataTable } from "@/components/DataTable"
import { Skeleton } from "@/components/ui/skeleton"

// Helper to generate a heatmap-style background color wash
const getReturnColorStyle = (val: number | null) => {
  if (val === null || isNaN(val)) return { bg: "transparent", text: "text-slate-400" };
  
  if (val > 0) {
    // Green wash for positive (max intensity at +80% return)
    const opacity = Math.min(val / 80, 1) * 0.35 + 0.05; 
    return { 
      bg: `rgba(34, 197, 94, ${opacity})`, 
      text: "text-green-700 dark:text-green-400" 
    };
  } else {
    // Red wash for negative (max intensity at -60% return)
    const opacity = Math.min(Math.abs(val) / 60, 1) * 0.35 + 0.05; 
    return { 
      bg: `rgba(239, 68, 68, ${opacity})`, 
      text: "text-red-700 dark:text-red-400" 
    };
  }
}

export function CalendarTable() {
  const { selectedIndices } = useStore()

  const { data, isLoading } = useQuery({
    queryKey: ["calendar-returns"],
    queryFn: async () => {
      const res = await fetch("http://localhost:8000/api/calendar-returns")
      return res.json()
    }
  })

  const columns = useMemo(() => {
    if (!data || data.length === 0) return [];
    
    // Always put 'Period' first, then only the selected indices
    const availableIndices = selectedIndices.filter(idx => Object.keys(data[0]).includes(idx));
    const colsToShow = ['Period', ...availableIndices];

    return colsToShow.map(key => ({
      accessorKey: key,
      header: key,
      cell: ({ row }: any) => {
        const val = row.getValue(key);
        
        if (key === 'Period') {
          return (
            <div className="p-3 font-bold text-slate-500 tabular-nums">
              {val}
            </div>
          );
        }

        const num = val as number | null;
        const { bg, text } = getReturnColorStyle(num);

        return (
          <div 
            className={`p-3 w-full h-full flex items-center justify-end font-mono font-bold text-[11px] ${text}`}
            style={{ backgroundColor: bg }}
          >
            {num !== null ? (num > 0 ? `+${num.toFixed(2)}%` : `${num.toFixed(2)}%`) : "—"}
          </div>
        );
      }
    }));
  }, [data, selectedIndices]);

  if (isLoading) return <Skeleton className="h-[500px] w-full rounded-2xl" />
  if (!data || data.length === 0) return null;

  return (
    <div className="space-y-4 py-8">
      <div className="flex items-center gap-3">
        <div className="h-6 w-1 bg-emerald-500 rounded-full" />
        <h3 className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-500">
            Calendar Year Returns (%)
        </h3>
      </div>
      
      {/* 
        [&_td]:p-0 removes the default DataTable padding so our cell background 
        colors stretch edge-to-edge, creating the seamless heatmap look. 
      */}
      <div className="screener-table bg-white dark:bg-slate-900/40 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-x-auto [&_td]:p-0 [&_td]:overflow-hidden">
        <DataTable columns={columns} data={data} />
      </div>
    </div>
  )
}