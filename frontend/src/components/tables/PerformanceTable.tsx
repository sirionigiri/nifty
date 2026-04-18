"use client"

import { ColumnDef } from "@tanstack/react-table"
import { DataTable } from "@/components/DataTable"

// 1. Define the shape of our data
export type PerformanceData = {
  period: string
  nifty50: number
  niftyNext50: number
  niftyMidcap150: number
  niftySmallcap250: number
}

// 2. Helper function to colorize numbers
const formatCell = (val: number) => {
  if (val === null || val === undefined) return <span className="text-muted-foreground">—</span>;
  const isPositive = val > 0;
  const colorClass = isPositive ? "text-green-600 dark:text-green-500 font-medium" : "text-red-600 dark:text-red-500 font-medium";
  return <span className={colorClass}>{val > 0 ? `+${val.toFixed(2)}` : val.toFixed(2)}</span>;
}

// 3. Define columns
export const columns: ColumnDef<PerformanceData>[] = [
  {
    accessorKey: "period",
    header: "Period",
    cell: ({ row }) => <span className="font-semibold text-foreground">{row.getValue("period")}</span>,
  },
  {
    accessorKey: "nifty50",
    header: () => <div className="text-right">NIFTY 50</div>,
    cell: ({ row }) => <div className="text-right">{formatCell(row.getValue("nifty50"))}</div>,
  },
  {
    accessorKey: "niftyNext50",
    header: () => <div className="text-right">NIFTY NEXT 50</div>,
    cell: ({ row }) => <div className="text-right">{formatCell(row.getValue("niftyNext50"))}</div>,
  },
  {
    accessorKey: "niftyMidcap150",
    header: () => <div className="text-right">NIFTY MIDCAP 150</div>,
    cell: ({ row }) => <div className="text-right">{formatCell(row.getValue("niftyMidcap150"))}</div>,
  },
  {
    accessorKey: "niftySmallcap250",
    header: () => <div className="text-right">NIFTY SMALLCAP 250</div>,
    cell: ({ row }) => <div className="text-right">{formatCell(row.getValue("niftySmallcap250"))}</div>,
  },
]

// 4. Dummy Data (Matches your Streamlit screenshot roughly)
const dummyData: PerformanceData[] = [
  { period: "Last Week", nifty50: -55.39, niftyNext50: 21.28, niftyMidcap150: -15.49, niftySmallcap250: -22.46 },
  { period: "Last Month", nifty50: 0.74, niftyNext50: 70.63, niftyMidcap150: 51.61, niftySmallcap250: 51.14 },
  { period: "YTD", nifty50: -20.27, niftyNext50: 4.02, niftyMidcap150: -10.64, niftySmallcap250: -26.33 },
  { period: "1 Yr", nifty50: 12.94, niftyNext50: 19.68, niftyMidcap150: 20.98, niftySmallcap250: 12.48 },
  { period: "3 Yr", nifty50: 14.44, niftyNext50: 24.25, niftyMidcap150: 25.18, niftySmallcap250: 22.05 },
  { period: "5 Yr", nifty50: 12.94, niftyNext50: 16.23, niftyMidcap150: 20.76, niftySmallcap250: 19.03 },
]

export function PerformanceTable() {
  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-bold uppercase tracking-wider text-slate-800 dark:text-slate-200 border-l-4 border-slate-800 dark:border-slate-200 pl-2">
          CAGR — Annualised Returns (%)
        </h3>
        <p className="text-xs text-muted-foreground mt-1 ml-3">
          'Rolling 3-Yr Avg' = simple mean of last 3 complete calendar year returns.
        </p>
      </div>
      <DataTable columns={columns} data={dummyData} />
    </div>
  )
}