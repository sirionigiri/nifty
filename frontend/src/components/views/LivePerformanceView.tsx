"use client"

import { useQuery } from "@tanstack/react-query"
import { useStore } from "@/store/useStore"
import { ColumnDef } from "@tanstack/react-table"
import { DataTable } from "@/components/DataTable"
import { Skeleton } from "@/components/ui/skeleton"
import React from "react" // Import React to use React.ReactNode

// 1. Define a strict type for your data rows
// This tells TS: "Every row has a string 'Period', and other keys are numbers or null"
type MetricRow = {
  Period: string;
  [key: string]: string | number | null;
};

const fetchMetrics = async (filters: any): Promise<MetricRow[]> => {
  const response = await fetch("http://localhost:8000/api/metrics", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(filters),
  });
  if (!response.ok) throw new Error("Network response was not ok");
  return response.json();
};

const formatScreenerCell = (value: number | null) => {
    if (value === null || isNaN(value)) {
        return <span className="text-slate-500">—</span>;
    }
    const color = value > 0 ? "text-green-600 font-semibold" : value < 0 ? "text-red-600 font-semibold" : "text-slate-600";
    return <span className={`font-mono ${color}`}>{value > 0 ? `+${value.toFixed(2)}` : value.toFixed(2)}</span>;
};

export function LivePerformanceView() {
  const { selectedIndices, benchmark, periods } = useStore();

  const { data, isLoading, error, isFetching } = useQuery({
    queryKey: ["metrics", "cagr", selectedIndices, benchmark, periods],
    queryFn: () => fetchMetrics({ 
      metric: "cagr",
      periods: periods,
      indices: selectedIndices,
      benchmark: benchmark
    }),
    enabled: selectedIndices.length > 0,
  });

  if (isLoading || isFetching) return <Skeleton className="w-full h-64 rounded-lg" />;
  if (error) return <div className="text-red-500 p-4 border border-red-200 rounded-lg bg-red-50">Error: Could not connect to Python backend.</div>;

  // 2. Generate columns with explicit type casting
  const columns: ColumnDef<MetricRow>[] = data && data.length > 0 
    ? Object.keys(data[0]).map(key => ({
        accessorKey: key,
        header: key,
        cell: ({ row }) => {
            const value = row.getValue(key);
            
            // If it's the Period column, cast it as a string
            if (key === 'Period') {
                return <span className="font-semibold text-slate-700 dark:text-slate-300">{value as string}</span>;
            }
            
            // For all other columns (numerical data), cast as number or null
            return (
                <div className="text-right">
                    {formatScreenerCell(value as number | null)}
                </div>
            );
        }
      })) 
    : [];

  return (
    <div className="space-y-4">
        <div className="flex items-center justify-between">
            <h2 className="text-lg font-bold tracking-tight text-slate-900 dark:text-slate-100">Performance Comparison</h2>
            <span className="text-[10px] bg-slate-100 dark:bg-slate-800 text-slate-500 px-2 py-1 rounded font-bold uppercase tracking-widest">CAGR %</span>
        </div>
        <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#09090b] shadow-sm overflow-hidden">
            {data && <DataTable columns={columns} data={data} />}
        </div>
    </div>
  );
}