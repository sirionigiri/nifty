"use client"

import React, { useState } from "react"
import { format } from "date-fns"
import { toast } from "sonner"
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Calendar } from "@/components/ui/calendar"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { Calendar as CalendarIcon, Download, FileSpreadsheet, Loader2 } from "lucide-react"
import { API_BASE_URL } from "@/lib/utils"

const SHEETS = [
  { id: "returns", label: "Returns (CAGR)" },
  { id: "calendar", label: "Calendar Year Returns" },
  { id: "rolling", label: "3Y Rolling Returns" },
  { id: "vs_benchmark", label: "Vs Benchmark (Excess / Correlation / Tracking Error)" },
  { id: "rankings", label: "Rankings" },
]

type Props = {
  minMonths: number
  fundCodes: number[]; indices: string[]; benchmark: string; periods: number[]
  rollStart: number | null; referenceDate?: string | null
}

export function MF2Report({ fundCodes, indices, benchmark, periods, rollStart, referenceDate, minMonths }: Props) {
  const [repDate, setRepDate] = useState<string>(referenceDate ?? format(new Date(), "yyyy-MM-dd"))
  const [sheets, setSheets] = useState<string[]>(SHEETS.map(s => s.id))
  const [busy, setBusy] = useState(false)

  const download = async () => {
    setBusy(true)
    try {
      const res = await fetch(`${API_BASE_URL}/api/mf2/report`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            fund_codes: fundCodes, indices, benchmark, periods, reference_date: repDate,
            sheets, roll_start_year: rollStart, min_months: minMonths,
            }),
      })
      if (!res.ok) {
        const e = await res.json().catch(() => ({}))
        throw new Error(e.detail || `Report failed (${res.status})`)
      }
      const blob = await res.blob()
      const a = document.createElement("a")
      a.href = URL.createObjectURL(blob)
      a.download = `MF_Report_${repDate}.xlsx`
      a.click()
      setTimeout(() => URL.revokeObjectURL(a.href), 5000)
    } catch (e) {
      toast.error("Report failed", { description: (e as Error).message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="outline" className="w-full text-[10px] font-bold uppercase tracking-wider h-9 rounded-lg text-slate-500 border-slate-200 dark:border-slate-800 hover:text-blue-600">
          <FileSpreadsheet className="w-3 h-3 mr-1 text-emerald-500" /> Report
        </Button>
      </DialogTrigger>

      <DialogContent className="!max-w-xl rounded-[28px] border-none shadow-2xl bg-white dark:bg-[#09090b]">
        <DialogHeader className="text-left">
          <DialogTitle className="text-2xl font-black tracking-tighter">Export MF Report</DialogTitle>
          <p className="text-xs text-slate-500">
            {fundCodes.length} schemes · {indices.length} indices · benchmark {benchmark} · {periods.length} periods (from the sidebar)
          </p>
        </DialogHeader>

        <div className="space-y-6 py-2">
          <div className="space-y-2">
            <label className="text-[10px] font-black uppercase tracking-widest text-slate-400">Reporting date</label>
            <Popover>
              <PopoverTrigger asChild>
                <Button variant="outline" className="w-full h-12 border-blue-100 dark:border-blue-900 bg-blue-50/50 dark:bg-blue-900/10 rounded-2xl flex justify-between px-5 font-mono text-sm font-black text-blue-600">
                  {format(new Date(repDate), "PPP")}<CalendarIcon className="h-4 w-4 opacity-50" />
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-auto p-0 rounded-3xl overflow-hidden shadow-2xl border-none" align="start">
                <Calendar mode="single" captionLayout="dropdown" startMonth={new Date(2005, 0)} endMonth={new Date()}
                  disabled={{ after: new Date() }} selected={new Date(repDate)}
                  onSelect={d => d && setRepDate(format(d, "yyyy-MM-dd"))} />
              </PopoverContent>
            </Popover>
            <p className="text-[10px] text-slate-400">Fund data is month-end, so this snaps back to the latest complete month-end.</p>
          </div>

          <div className="space-y-3">
            <label className="text-[10px] font-black uppercase tracking-widest text-slate-400">Sheets</label>
            <div className="space-y-2">
              {SHEETS.map(s => (
                <label key={s.id} className="flex items-center gap-3 cursor-pointer">
                  <Checkbox checked={sheets.includes(s.id)}
                    onCheckedChange={() => setSheets(p => p.includes(s.id) ? p.filter(x => x !== s.id) : [...p, s.id])} />
                  <span className="text-xs font-bold text-slate-600 dark:text-slate-300">{s.label}</span>
                </label>
              ))}
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button disabled={busy || sheets.length === 0 || (fundCodes.length === 0 && indices.length === 0)} onClick={download}
            className="w-full h-11 rounded-[20px] bg-blue-600 hover:bg-blue-700 text-white font-black text-sm">
            {busy ? <Loader2 className="animate-spin mr-3 h-5 w-5" /> : <Download className="mr-3 h-5 w-5" />}
            Export to Excel
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}