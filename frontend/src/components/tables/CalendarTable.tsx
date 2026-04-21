"use client"

import React, { useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { useStore } from "@/store/useStore"
import { DataTable } from "@/components/DataTable"
import { Skeleton } from "@/components/ui/skeleton"
import { Download } from "lucide-react"
import { Button } from "@/components/ui/button"
import { exportToExcel } from "@/lib/export"
import { API_BASE_URL } from "@/lib/utils"



// Helper to generate a heatmap-style background color wash for table cells
const getReturnColorStyle = (val: number | null) => {
  if (val === null || isNaN(val)) return { bg: "transparent", text: "text-slate-400" };
  
  if (val > 0) {
    // Green wash for positive
    const opacity = Math.min(val / 50, 1) * 0.4 + 0.05; 
    const isDeep = opacity > 0.3;
    return { 
      bg: `rgba(34, 197, 94, ${opacity})`, 
      text: isDeep ? "text-green-900 dark:text-green-50 font-bold" : "text-green-700 dark:text-green-400" 
    };
  } else {
    // Red wash for negative
    const opacity = Math.min(Math.abs(val) / 50, 1) * 0.4 + 0.05; 
    const isDeep = opacity > 0.3;
    return { 
      bg: `rgba(239, 68, 68, ${opacity})`, 
      text: isDeep ? "text-red-900 dark:text-red-50 font-bold" : "text-red-700 dark:text-red-400" 
    };
  }
}

export function CalendarTable() {
  const { selectedIndices } = useStore()

  const { data: response, isLoading } = useQuery({
    queryKey: ["calendar-returns"],
    queryFn: async () => {
      const res = await fetch(`${API_BASE_URL}/api/calendar-returns`)
      return res.json()
    }
  })

  // FIX: Extract the actual array from the response object safely
  const rows = useMemo(() => response?.data || [], [response]);

  const handleDownload = () => {
    if (rows.length > 0) {
      exportToExcel(rows, "Calendar_Returns_Report");
    }
  }

  const columns = useMemo(() => {
    if (!rows || rows.length === 0) return [];
    
    // Always put 'Period' (Year) first, then only the selected indices
    const availableIndices = selectedIndices.filter(idx => Object.keys(rows[0]).includes(idx));
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
            className={`p-3 w-full h-full flex items-center justify-end font-mono text-[11px] transition-colors ${text}`}
            style={{ backgroundColor: bg }}
          >
            {num !== null ? (num > 0 ? `+${num.toFixed(2)}%` : `${num.toFixed(2)}%`) : "—"}
          </div>
        );
      }
    }));
  }, [rows, selectedIndices]);

  if (isLoading) return <Skeleton className="h-[400px] w-full rounded-2xl" />
  if (rows.length === 0) return null;

  return (
    <div className="space-y-4 py-8">
      <div className="flex items-center justify-between border-b border-slate-50 dark:border-slate-900 pb-4">
        <div className="flex items-center gap-3">
          <div className="h-6 w-1 bg-emerald-500 rounded-full" />
          <div>
            <h3 className="text-[11px] font-black uppercase tracking-[0.2em] text-slate-500">
                Calendar Year Returns Table
            </h3>
            <p className="text-[9px] text-slate-400 font-bold uppercase mt-0.5">
              Full Data Range: {response?.scope}
            </p>
          </div>
        </div>

        <Button 
          variant="outline" 
          size="sm" 
          onClick={handleDownload}
          className="h-8 text-[10px] font-bold uppercase tracking-widest border-slate-200 dark:border-slate-800 hover:bg-blue-50 dark:hover:bg-blue-900/20 hover:text-blue-600 transition-all"
        >
          <Download className="w-3 h-3 mr-2" /> Excel
        </Button>
      </div>
      
      <div className="screener-table bg-white dark:bg-slate-900/40 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-x-auto [&_td]:p-0 [&_td]:overflow-hidden">
        <DataTable columns={columns} data={rows} />
      </div>
    </div>
  )
}