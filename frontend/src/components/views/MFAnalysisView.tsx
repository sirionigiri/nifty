"use client"

import React, { useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { useStore } from "@/store/useStore"
import { API_BASE_URL } from "@/lib/utils"
import { LoadingSpinner } from "../ui/LoadingSpinner"
import { Checkbox } from "@/components/ui/checkbox"
import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Download } from "lucide-react"
import { exportToExcel } from "@/lib/export"

type ClassCfg = { id: string; count: number; benchmark: string | null; extras: string[] }
type Cfg = { classes: ClassCfg[]; indices: string[]; min_date: string; max_date: string }
type Num = number | null
type Row = {
  id: string; name: string; amc: string | null; is_index: boolean; is_benchmark: boolean
  ret: Record<string, Num>; partial: number[]; ytd: Num
  trail: Record<string, Num>; roll3: Record<string, Num>; roll3_avg: Num; corr: Num
  rank: Record<string, Num>
  avg_rank_10: Num; med_rank_10: Num; avg_rank_5: Num; avg_rank_3: Num
}
type Analysis = {
  as_of: string | null; years: number[]; ytd_year: number | null; benchmark: string
  n_funds: number; universe: Record<string, number>; rows: Row[]
}

type Mode = "returns" | "ranks" | "roll3"
type SortKey =
  | "trail10" | "trail5" | "trail3" | "trail1" | "roll3_avg" | "corr"
  | "avg_rank_10" | "med_rank_10" | "avg_rank_5" | "avg_rank_3"
const RANK_KEYS = new Set<SortKey>(["avg_rank_10", "med_rank_10", "avg_rank_5", "avg_rank_3"])

const fmt = (v: Num | undefined, d = 1) => (v == null ? "—" : v.toFixed(d))
const tone = (v: Num | undefined) =>
  v == null ? "text-slate-400" : v > 0 ? "text-green-600" : v < 0 ? "text-red-600" : "text-slate-500"

// rank 1 = green, last = red (alpha keeps it readable in dark mode)
function rankStyle(rank: Num | undefined, n: number | undefined): React.CSSProperties {
  if (rank == null || !n) return {}
  const p = (rank - 1) / Math.max(n - 1, 1)
  return { backgroundColor: `hsl(${130 - p * 130} 70% 50% / 0.35)` }
}

function getVal(r: Row, k: SortKey): Num {
  if (k.startsWith("trail")) return r.trail[k.replace("trail", "")]
  return (r as any)[k] ?? null
}

export function MFAnalysisView() {
  const { referenceDate } = useStore()

  const [clsOverride, setClsOverride] = useState<string | null>(null)
  const [benchOverride, setBenchOverride] = useState<string | null>(null)
  const [mode, setMode] = useState<Mode>("returns")
  const [sortKey, setSortKey] = useState<SortKey>("trail5")
  const [minHist, setMinHist] = useState(true)             // require >= 12 months of history
  const [rankPartial, setRankPartial] = useState(false)    // include part-year returns in ranks
  const [rankWithIdx, setRankWithIdx] = useState(true)     // rank funds alongside index rows

  const { data: cfg } = useQuery<Cfg>({
    queryKey: ["mf-analysis-config"],
    queryFn: async () => {
      const res = await fetch(`${API_BASE_URL}/api/mf-analysis-config`)
      if (!res.ok) throw new Error(`Config failed: ${res.status}`)
      return res.json()
    },
    staleTime: Infinity,
  })

  const cls =
    clsOverride ??
    cfg?.classes.find(c => c.id === "Mid-Cap" && c.count > 0)?.id ??
    cfg?.classes.find(c => c.count > 0)?.id ??
    null
  const clsCfg = cfg?.classes.find(c => c.id === cls)
  const bench = benchOverride ?? clsCfg?.benchmark ?? "NIFTY 500"

  const { data, isLoading, isError, error } = useQuery<Analysis>({
    queryKey: ["mf-analysis", cls, bench, referenceDate, minHist, rankPartial, rankWithIdx],
    queryFn: async () => {
      const res = await fetch(`${API_BASE_URL}/api/mf-analysis`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          fund_class: cls,
          benchmark_index: bench,
          extra_indices: benchOverride ? [] : null,        // custom benchmark -> no default peers
          reference_date: referenceDate,
          min_history_months: minHist ? 12 : 0,
          include_partial_in_rank: rankPartial,
          rank_with_indices: rankWithIdx,
        }),
      })
      if (!res.ok) throw new Error(`Analysis failed: ${res.status}`)
      return res.json()
    },
    enabled: !!cls,
  })

  const rows = useMemo(() => {
    if (!data) return []
    const pinned = data.rows.filter(r => r.is_index)
    const funds = data.rows.filter(r => !r.is_index)
    const asc = RANK_KEYS.has(sortKey)
    funds.sort((a, b) => {
      const x = getVal(a, sortKey), y = getVal(b, sortKey)
      if (x == null && y == null) return 0
      if (x == null) return 1
      if (y == null) return -1
      return asc ? x - y : y - x
    })
    return [...pinned, ...funds]
  }, [data, sortKey])

  const handleExport = () => {
    if (!data) return
    const out = rows.map(r => {
      const o: Record<string, any> = { "Fund / Index": r.name }
      data.years.forEach(y => { o[`${y} Ret %`] = r.ret[String(y)] })
      if (data.ytd_year) o[`${data.ytd_year} YTD %`] = r.ytd
      ;[10, 5, 3, 1].forEach(n => { o[`${n}Y CAGR %`] = r.trail[String(n)] })
      data.years.forEach(y => { o[`Roll3Y ${y} %`] = r.roll3[String(y)] })
      o["Avg Roll3Y %"] = r.roll3_avg
      o[`Corr vs ${data.benchmark}`] = r.corr
      data.years.forEach(y => { o[`Rank ${y}`] = r.rank[String(y)] })
      o["Avg Rank 10Y"] = r.avg_rank_10; o["Median Rank 10Y"] = r.med_rank_10
      o["Avg Rank 5Y"] = r.avg_rank_5; o["Avg Rank 3Y"] = r.avg_rank_3
      return o
    })
    exportToExcel(out, `MF_${cls}_vs_${data.benchmark}`.replace(/[^\w]+/g, "_"))
  }

  const Th = ({ children, k, className = "" }: { children: React.ReactNode; k?: SortKey; className?: string }) => (
    <th
      onClick={k ? () => setSortKey(k) : undefined}
      className={`px-3 py-2 text-[10px] font-black uppercase tracking-wider text-slate-500 whitespace-nowrap text-right ${k ? "cursor-pointer hover:text-blue-600" : ""} ${sortKey === k ? "text-blue-600" : ""} ${className}`}
    >
      {children}{sortKey === k ? (RANK_KEYS.has(k!) ? " ↑" : " ↓") : ""}
    </th>
  )

  return (
    <div className="space-y-6 pb-20">
      {/* CONTROLS */}
      <div className="flex flex-wrap items-end gap-6 bg-white dark:bg-slate-900/40 p-6 rounded-3xl border border-slate-200 dark:border-slate-800">
        <div className="space-y-2 w-56">
          <label className="text-[10px] font-black uppercase tracking-widest text-slate-400">Fund Category</label>
          <Select value={cls ?? ""} onValueChange={v => { setClsOverride(v); setBenchOverride(null) }}>
            <SelectTrigger className="h-10 rounded-xl text-xs font-bold"><SelectValue /></SelectTrigger>
            <SelectContent>
              {cfg?.classes.map(c => (
                <SelectItem key={c.id} value={c.id} disabled={c.count === 0} className="text-xs font-bold">
                  {c.id} ({c.count})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2 w-72">
          <label className="text-[10px] font-black uppercase tracking-widest text-slate-400">Benchmark Index</label>
          <Select value={bench} onValueChange={setBenchOverride}>
            <SelectTrigger className="h-10 rounded-xl text-xs font-bold"><SelectValue /></SelectTrigger>
            <SelectContent className="max-h-80">
              {cfg?.indices.map(i => <SelectItem key={i} value={i} className="text-xs font-bold">{i}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>

        <div className="flex gap-1 bg-slate-100 dark:bg-slate-900 p-1 rounded-xl border border-slate-200 dark:border-slate-800">
          {([["returns", "Returns %"], ["ranks", "Ranks"], ["roll3", "Rolling 3Y"]] as const).map(([id, label]) => (
            <button
              key={id} type="button" onClick={() => setMode(id)}
              className={`px-4 py-2 rounded-lg text-[11px] font-bold uppercase transition-all ${mode === id ? "bg-white dark:bg-slate-800 text-blue-600 shadow-sm" : "text-slate-500"}`}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="flex flex-col gap-2">
          {[
            [minHist, setMinHist, "Hide funds < 12 months old"],
            [rankPartial, setRankPartial, "Include part-year returns in ranks"],
            [rankWithIdx, setRankWithIdx, "Rank funds alongside indices"],
          ].map(([val, set, label]: any) => (
            <label key={label} className="flex items-center gap-2 text-[11px] font-bold text-slate-500 cursor-pointer">
              <Checkbox checked={val} onCheckedChange={(v: any) => set(!!v)} /> {label}
            </label>
          ))}
        </div>

        <Button variant="outline" size="sm" onClick={handleExport} disabled={!data?.rows.length}
          className="ml-auto h-9 text-[10px] font-bold uppercase tracking-widest">
          <Download className="w-3 h-3 mr-2" /> Excel
        </Button>
      </div>

      {/* TABLE */}
      <div className="bg-white dark:bg-slate-900/40 rounded-3xl border border-slate-200 dark:border-slate-800 p-2 shadow-sm">
        {isLoading || !cfg ? (
          <LoadingSpinner />
        ) : isError ? (
          <div className="text-center text-xs text-red-500 py-10">{(error as Error).message}</div>
        ) : !data?.rows.length ? (
          <div className="text-center text-xs text-slate-400 py-10">No funds for this category / date.</div>
        ) : (
          <>
            <p className="px-4 pt-3 pb-2 text-[10px] font-bold uppercase tracking-widest text-slate-400">
              {cls} · {data.n_funds} funds · month-end NAV as of {data.as_of} · * = part-year (since first NAV)
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-xs border-separate border-spacing-0">
                <thead>
                  <tr className="border-b">
                    <th className="sticky left-0 z-10 bg-white dark:bg-slate-950 px-3 py-2 text-left text-[10px] font-black uppercase text-slate-500 min-w-[280px]">Fund</th>
                    {data.years.map(y => <Th key={y}>{y}</Th>)}
                    {mode === "returns" && data.ytd_year && <Th>{data.ytd_year} YTD</Th>}
                    <Th k="trail10" className="border-l">10Y</Th>
                    <Th k="trail5">5Y</Th>
                    <Th k="trail3">3Y</Th>
                    <Th k="trail1">1Y</Th>
                    <Th k="roll3_avg" className="border-l">Avg 3Y Roll</Th>
                    <Th k="corr">Corr</Th>
                    <Th k="med_rank_10" className="border-l">Med Rk 10Y</Th>
                    <Th k="avg_rank_10">Avg Rk 10Y</Th>
                    <Th k="avg_rank_5">Avg Rk 5Y</Th>
                    <Th k="avg_rank_3">Avg Rk 3Y</Th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map(r => (
                    <tr key={r.id} className={`border-b hover:bg-slate-50 dark:hover:bg-slate-800/40 ${r.is_index ? "bg-blue-50/60 dark:bg-blue-900/10" : ""}`}>
                      <td className={`sticky left-0 z-10 px-3 py-2 font-bold ${r.is_index ? "text-blue-600 bg-blue-50 dark:bg-slate-950" : "text-slate-700 dark:text-slate-200 bg-white dark:bg-slate-950"}`}>
                        {r.is_benchmark ? "⭐ " : ""}{r.name}
                      </td>
                      {data.years.map(y => {
                        const k = String(y)
                        if (mode === "ranks")
                          return <td key={y} style={rankStyle(r.rank[k], data.universe[k])} className="px-3 py-2 text-right font-mono font-bold">{r.rank[k] ?? "—"}</td>
                        if (mode === "roll3")
                          return <td key={y} className={`px-3 py-2 text-right font-mono ${tone(r.roll3[k])}`}>{fmt(r.roll3[k])}</td>
                        const part = r.partial.includes(y)
                        return (
                          <td key={y} title={part ? "Part-year: since first NAV" : undefined}
                              className={`px-3 py-2 text-right font-mono ${tone(r.ret[k])} ${part ? "italic opacity-60" : ""}`}>
                            {fmt(r.ret[k])}{part && "*"}
                          </td>
                        )
                      })}
                      {mode === "returns" && data.ytd_year && (
                        <td className={`px-3 py-2 text-right font-mono ${tone(r.ytd)}`}>{fmt(r.ytd)}</td>
                      )}
                      {["10", "5", "3", "1"].map((n, i) => (
                        <td key={n} className={`px-3 py-2 text-right font-mono font-bold ${tone(r.trail[n])} ${i === 0 ? "border-l" : ""}`}>{fmt(r.trail[n])}</td>
                      ))}
                      <td className={`px-3 py-2 text-right font-mono border-l ${tone(r.roll3_avg)}`}>{fmt(r.roll3_avg)}</td>
                      <td className="px-3 py-2 text-right font-mono text-slate-500">{fmt(r.corr, 2)}</td>
                      <td className="px-3 py-2 text-right font-mono border-l">{fmt(r.med_rank_10)}</td>
                      <td className="px-3 py-2 text-right font-mono">{fmt(r.avg_rank_10)}</td>
                      <td className="px-3 py-2 text-right font-mono">{fmt(r.avg_rank_5)}</td>
                      <td className="px-3 py-2 text-right font-mono">{fmt(r.avg_rank_3)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </div>
  )
}