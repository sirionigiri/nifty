"use client"

import React, { useMemo, useState } from "react"
import { MatrixTable, type Axis, type Cell } from "@/components/mf2/MatrixTable"
import { BaseChart } from "@/components/charts/BaseChart"
import { Switch } from "@/components/ui/switch"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { fmtDate, fmtNum, isNum, rankHeat, robustScale, signHeat, tone } from "@/components/mf2/heat"
import type { Coverage, MF2Analysis, MF2Item, Num } from "@/components/mf2/types"

const axisOf = (it: MF2Item): Axis => ({
  key: it.id, label: it.name, bold: it.is_benchmark,
  sub: it.is_benchmark ? "Benchmark" : it.kind === "index" ? "Index" : it.cls ?? "",
})
const numCell = (v: Num | undefined, d = 2): Cell => ({ value: v ?? null, text: fmtNum(v, d), className: tone(v) })
const plainCell = (v: Num | undefined, d = 2): Cell => ({ value: v ?? null, text: fmtNum(v, d) })

/** Calendar years shown, by how many items have a full-year return in that year. */
export function visibleYears(data: MF2Analysis, coverage: Coverage): number[] {
  const N = data.items.length
  return data.years.filter(y => {
    const n = data.n_valid[String(y)] ?? 0
    return coverage === "any" ? n > 0 : coverage === "half" ? n >= Math.max(1, N / 2) : n === N
  })
}

/* ───────────────────────────── RETURNS ───────────────────────────── */
export function ReturnsTab({ data }: { data: MF2Analysis }) {
  const rows: Axis[] = data.periods.map(n => ({ key: String(n), label: `${n} Yr` }))
  const cols = data.items.map(axisOf)
  return (
    <MatrixTable
      title="CAGR — Annualised Returns (%)"
      subtitle={`Trailing, ending ${fmtDate(data.as_of)} (latest complete month-end)`}
      rowHeader="Period" colHeader="Fund / Index" rows={rows} cols={cols} flippable exportName="MF_CAGR_Returns"
      empty="Select at least one time period."
      cell={(r, c) => numCell(data.cagr[rows[r].key]?.[c])}
    />
  )
}

/* ─────────────────────────── CALENDAR YEARS ──────────────────────── */
export function CalendarTab({ data, coverage }: { data: MF2Analysis; coverage: Coverage }) {
  const years = useMemo(() => visibleYears(data, coverage), [data, coverage])
  const rows = useMemo(() => data.items.map(axisOf), [data])
  const cols: Axis[] = useMemo(
    () => [...years.map(y => ({ key: String(y), label: String(y) })),
           ...(data.ytd_year ? [{ key: "ytd", label: `${data.ytd_year} YTD` }] : [])],
    [years, data.ytd_year],
  )
  const scale = useMemo(
    () => robustScale([...years.flatMap(y => data.cal[String(y)] ?? []), ...(data.ytd ?? [])]),
    [years, data],
  )
  return (
    <MatrixTable
      title="Calendar Year Returns (%)"
      subtitle="Full Dec→Dec years · green = positive, red = negative · independent of the sidebar time periods"
      rowHeader="Fund / Index" colHeader="Year" rows={rows} cols={cols} exportName="MF_Calendar_Returns" flippable
      empty="No calendar year has data for every selected item. Lower the coverage."
      cell={(r, c) => {
        const col = cols[c]
        const v = col.key === "ytd" ? data.ytd?.[r] : data.cal[col.key]?.[r]
        return { value: v ?? null, text: fmtNum(v, 1), style: signHeat(v, scale) }
      }}
    />
  )
}

/* ──────────────────────────── 3Y ROLLING ─────────────────────────── */
export function RollingTab({ data, rollStart, setRollStart }: {
  data: MF2Analysis; rollStart: number | null; setRollStart: (y: number) => void
}) {
  const ry = data.roll_years
  const maxEnd = ry.length ? Math.max(...ry) : 0
  const minStart = ry.length ? Math.min(...ry) - 2 : 0
  const maxStart = maxEnd - 2
  const start = Math.min(Math.max(rollStart ?? minStart, minStart), maxStart)
  const ends = useMemo(() => ry.filter(y => y >= start + 2), [ry, start])

  const stats = useMemo(() => data.items.map((_, i) => {
    const v = ends.map(y => data.roll3[String(y)]?.[i]).filter(isNum)
    return { avg: v.length ? v.reduce((a, b) => a + b, 0) / v.length : null, n: v.length }
  }), [data, ends])

  const rows = useMemo(() => data.items.map(axisOf), [data])
  const cols: Axis[] = useMemo(
    () => [{ key: "avg", label: "Average" }, { key: "n", label: "Windows" }, ...ends.map(y => ({ key: String(y), label: `${y - 2}–${y}`, sub: "3Y CAGR" }))],
    [ends],
  )
  const scale = useMemo(
    () => robustScale([...ends.flatMap(y => data.roll3[String(y)] ?? []), ...stats.map(s => s.avg)]),
    [ends, stats, data],
  )

  if (!ry.length) return <div className="py-16 text-center text-xs text-slate-400">Not enough history for 3-year rolling windows.</div>

  return (
    <div className="space-y-4">
      <div className="bg-white dark:bg-slate-900/40 rounded-2xl border border-slate-200 dark:border-slate-800 p-5">
        <div className="flex justify-between text-[10px] font-black uppercase tracking-widest text-slate-400 mb-2">
          <span>Calendar years from {start}</span>
          <span>to {maxEnd} (latest full year, fixed)</span>
        </div>
        <input type="range" min={minStart} max={Math.max(maxStart, minStart)} step={1} value={start}
          disabled={maxStart <= minStart} onChange={e => setRollStart(Number(e.target.value))}
          className="w-full accent-blue-600" />
        <div className="flex justify-between text-[9px] font-bold text-slate-400 mt-1">
          <span>{minStart}</span><span>{Math.max(maxStart, minStart)}</span>
        </div>
      </div>
      <MatrixTable
        title="3-Year Rolling Calendar Returns (CAGR %)"
        subtitle={`${ends.length} rolling windows · each column = 3 calendar years ending that year · Average = mean of the windows shown`}
        rowHeader="Fund / Index" colHeader="Window" rows={rows} cols={cols} exportName="MF_Rolling_3Y" flippable
        cell={(r, c) => {
          const col = cols[c]
          if (col.key === "avg") return { value: stats[r].avg, text: fmtNum(stats[r].avg, 1), style: signHeat(stats[r].avg, scale), className: "font-bold" }
          if (col.key === "n") return { value: stats[r].n, text: String(stats[r].n), className: "text-slate-400" }
          const v = data.roll3[col.key]?.[r]
          return { value: v ?? null, text: fmtNum(v, 1), style: signHeat(v, scale) }
        }}
      />
    </div>
  )
}

/* ───────────────────────────── VS BENCHMARK ──────────────────────── */
export function VsBenchTab({ data }: { data: MF2Analysis }) {
  const rows: Axis[] = data.periods.map(n => ({ key: String(n), label: `${n} Yr` }))
  const cols = data.items.map(axisOf)
  const [period, setPeriod] = useState<number | null>(null)
  const [zoom, setZoom] = useState(false)
  const active = period && data.periods.includes(period) ? period : data.periods[0]

  const chart = useMemo(() => {
    if (!active) return []
    return data.items
      .map((it, i) => ({ name: it.name, kind: it.kind, v: data.te[String(active)]?.[i], bench: it.is_benchmark }))
      .filter(d => !d.bench && isNum(d.v))
      .sort((a, b) => (a.v as number) - (b.v as number))
      .slice(0, 40)                                           // 40 lowest tracking errors
  }, [data, active])

  const plot = useMemo(() => [{
    type: "bar", orientation: "h",
    x: chart.map(d => d.v), y: chart.map((_, i) => i),
    customdata: chart.map(d => d.name),
    marker: { color: chart.map(d => (d.kind === "index" ? "#7c3aed" : "#2563eb")) },
    hovertemplate: "%{customdata}<br><b>%{x:.2f}%</b><extra></extra>",
  }], [chart])

  return (
    <div className="space-y-6">
      <MatrixTable title="Excess CAGR vs Benchmark (%)" subtitle={`Item CAGR minus ${data.benchmark} CAGR over the same period`}
        rowHeader="Period" colHeader="Fund / Index" rows={rows} cols={cols} flippable exportName="MF_Excess_CAGR"
        empty="Select at least one time period." cell={(r, c) => numCell(data.excess[rows[r].key]?.[c])} />

      <MatrixTable title="Correlation vs Benchmark" subtitle="Monthly returns over each period · item must span the full period"
        rowHeader="Period" colHeader="Fund / Index" rows={rows} cols={cols} flippable exportName="MF_Correlation"
        empty="Select at least one time period." cell={(r, c) => plainCell(data.corr[rows[r].key]?.[c])} />

      <MatrixTable title="Tracking Error (% annualised)" subtitle="Std-dev of monthly excess returns vs benchmark × √12 · lower = closer to the index"
        rowHeader="Period" colHeader="Fund / Index" rows={rows} cols={cols} flippable exportName="MF_Tracking_Error"
        empty="Select at least one time period." cell={(r, c) => plainCell(data.te[rows[r].key]?.[c])} />

      {active && (
        <div className="bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-4 mb-4">
            <div>
              <h3 className="text-[11px] font-black uppercase tracking-[0.2em] text-slate-500">Tracking Error Chart</h3>
              <p className="text-[10px] text-slate-400 mt-1">40 lowest · purple = index, blue = fund</p>
            </div>
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2 px-3 py-1 bg-slate-50 dark:bg-slate-900 rounded-full border border-slate-100 dark:border-slate-800">
                <span className="text-[9px] font-bold text-slate-400 uppercase tracking-widest">Interactive</span>
                <Switch checked={zoom} onCheckedChange={setZoom} className="scale-75 data-[state=checked]:bg-blue-600" />
              </div>
              <div className="segmented-tabs-list !mb-0">
                {data.periods.map(n => (
                  <button key={n} type="button" onClick={() => setPeriod(n)}
                    className={`segmented-tab-trigger ${active === n ? "!bg-white dark:!bg-slate-800 !text-blue-600 shadow-sm" : ""}`}>
                    {n} Yr
                  </button>
                ))}
              </div>
            </div>
          </div>
          {chart.length === 0 ? (
            <div className="py-12 text-center text-xs text-slate-400">No item spans this full period.</div>
          ) : (
            <div style={{ height: Math.max(320, chart.length * 22 + 70) }}>
              <BaseChart data={plot} zoomEnabled={zoom} layout={{
                margin: { l: 300, r: 30, t: 10, b: 40 }, bargap: 0.25,
                xaxis: { title: { text: "Tracking error (% annualised)" }, tickfont: { size: 11 } },
                yaxis: {
                  tickmode: "array", tickvals: chart.map((_, i) => i), autorange: "reversed", tickfont: { size: 10 },
                  ticktext: chart.map(d => (d.name.length > 46 ? d.name.slice(0, 45) + "…" : d.name)),
                },
              }} />
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/* ──────────────────────────────── RANKINGS ───────────────────────── */
type SortKey = "median" | "a10" | "a5" | "a3" | "name"

export function RankingsTab({ data, coverage }: { data: MF2Analysis; coverage: Coverage }) {
  const [sort, setSort] = useState<SortKey>("median")
  const years = useMemo(() => visibleYears(data, coverage), [data, coverage])

  const order = useMemo(() => {
    const key = (i: number): Num =>
      sort === "median" ? data.median_rank[i]
      : sort === "a10" ? data.avg_rank["10"]?.[i] ?? null
      : sort === "a5" ? data.avg_rank["5"]?.[i] ?? null
      : data.avg_rank["3"]?.[i] ?? null
    return data.items.map((_, i) => i).sort((a, b) => {
      const A = data.items[a], B = data.items[b]
      if (A.is_benchmark !== B.is_benchmark) return A.is_benchmark ? -1 : 1
      if (sort === "name") return A.name.localeCompare(B.name)
      const x = key(a), y = key(b)
      if (x == null && y == null) return 0
      if (x == null) return 1
      if (y == null) return -1
      return x - y
    })
  }, [data, sort])

  const rows = useMemo(() => order.map(i => axisOf(data.items[i])), [order, data])
  const cols: Axis[] = useMemo(() => [
    { key: "median", label: "Median Rank" }, { key: "avg10", label: "Avg Rank 10Y" },
    { key: "avg5", label: "Avg Rank 5Y" }, { key: "avg3", label: "Avg Rank 3Y" },
    ...years.map(y => ({ key: String(y), label: String(y) })),
  ], [years])

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">Sort by</span>
        <Select value={sort} onValueChange={v => setSort(v as SortKey)}>
          <SelectTrigger className="w-48 h-9 rounded-xl text-xs font-bold"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="median" className="text-xs font-bold">Median rank</SelectItem>
            <SelectItem value="a10" className="text-xs font-bold">Avg rank 10Y</SelectItem>
            <SelectItem value="a5" className="text-xs font-bold">Avg rank 5Y</SelectItem>
            <SelectItem value="a3" className="text-xs font-bold">Avg rank 3Y</SelectItem>
            <SelectItem value="name" className="text-xs font-bold">Name</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <MatrixTable
        title="Calendar Year Rankings (1 = best)"
        subtitle="Ranked against every other selected fund / index with a full-year return · averages need the complete 10/5/3-year window"
        rowHeader="Fund / Index" colHeader="Metric" rows={rows} cols={cols} exportName="MF_Rankings" flippable
        cell={(r, c) => {
          const col = cols[c], i = order[r]
          if (col.key === "median") return { value: data.median_rank[i], text: fmtNum(data.median_rank[i], 1), className: "font-bold" }
          if (col.key.startsWith("avg")) {
            const v = data.avg_rank[col.key.slice(3)]?.[i]
            return { value: v ?? null, text: fmtNum(v, 0), className: "font-bold" }
          }
          const v = data.rank[col.key]?.[i]
          return { value: v ?? null, text: fmtNum(v, 0), style: rankHeat(v, data.universe[col.key]) }
        }}
      />
    </div>
  )
}