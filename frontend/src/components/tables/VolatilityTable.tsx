"use client"

import { ColumnDef } from "@tanstack/react-table"
import { DataTable } from "@/components/DataTable"
import { getHeatmapColor } from "@/lib/colors"

export type VolatilityData = {
  period: string
  nifty50: number
  niftyNext50: number
  niftyMidcap150: number
}

// To calculate the gradient, we need the global min/max of the dataset
const MIN_VOL = 10.0;
const MAX_VOL = 25.0;

// Reusable cell formatter for the heatmap
const formatHeatmapCell = (val: number) => {
  if (val === null || val === undefined) return <div className="p-3">—</div>;
  const bgColor = getHeatmapColor(val, MIN_VOL, MAX_VOL);
  // We use dark text here because the background is yellow/orange/red
  return (
    <div 
      className="p-3 w-full h-full flex items-center justify-end font-medium text-slate-900 transition-colors"
      style={{ backgroundColor: bgColor }}
    >
      {val.toFixed(2)}
    </div>
  );
}

export const columns: ColumnDef<VolatilityData>[] = [
  {
    accessorKey: "period",
    header: "Period",
    cell: ({ row }) => <div className="p-3 font-semibold text-foreground">{row.getValue("period")}</div>,
  },
  {
    accessorKey: "nifty50",
    header: () => <div className="text-right p-3">NIFTY 50</div>,
    cell: ({ row }) => formatHeatmapCell(row.getValue("nifty50")),
  },
  {
    accessorKey: "niftyNext50",
    header: () => <div className="text-right p-3">NIFTY NEXT 50</div>,
    cell: ({ row }) => formatHeatmapCell(row.getValue("niftyNext50")),
  },
  {
    accessorKey: "niftyMidcap150",
    header: () => <div className="text-right p-3">NIFTY MIDCAP 150</div>,
    cell: ({ row }) => formatHeatmapCell(row.getValue("niftyMidcap150")),
  },
]

const dummyData: VolatilityData[] = [
  { period: "Last Week", nifty50: 13.00, niftyNext50: 13.02, niftyMidcap150: 11.21 },
  { period: "Last Month", nifty50: 15.20, niftyNext50: 18.29, niftyMidcap150: 17.25 },
  { period: "YTD", nifty50: 13.03, niftyNext50: 17.66, niftyMidcap150: 16.89 },
  { period: "1 Yr", nifty50: 11.92, niftyNext50: 15.72, niftyMidcap150: 15.50 },
  { period: "20 Yr", nifty50: 20.89, niftyNext50: 22.95, niftyMidcap150: 20.95 },
]

export function VolatilityTable() {
  return (
    <div className="space-y-4">
      <div className="border-b pb-4">
        <h3 className="text-sm font-bold uppercase tracking-wider text-slate-800 dark:text-slate-200 border-l-4 border-slate-800 dark:border-slate-200 pl-2">
          Volatility — Annualised (%)
        </h3>
      </div>
      {/* We add a custom wrapper to override the default padding of DataTable cells for edge-to-edge color */}
      <div className="[&_td]:p-0 [&_td]:overflow-hidden">
        <DataTable columns={columns} data={dummyData} />
      </div>
    </div>
  )
}