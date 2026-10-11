"use client"

import React, { useEffect, useMemo, useRef, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { useStore } from "@/store/useStore"
import { API_BASE_URL } from "@/lib/utils"
import { LoadingSpinner } from "@/components/ui/LoadingSpinner"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { ALL_PERIODS, MF2Sidebar } from "@/components/mf2/MF2Sidebar"
import { MF2Report } from "@/components/mf2/MF2Report"
import { CalendarTab, RankingsTab, ReturnsTab, RollingTab, VsBenchTab } from "@/components/mf2/MF2Tabs"
import { fmtDate } from "@/components/mf2/heat"
import type { Coverage, MF2Analysis, MF2Config } from "@/components/mf2/types"

type SubTab = "returns" | "calendar" | "rolling" | "vs" | "ranks"
const SUBTABS: { id: SubTab; label: string }[] = [
  { id: "returns", label: "Returns" },
  { id: "calendar", label: "Calendar Year Returns" },
  { id: "rolling", label: "3Yr Rolling" },
  { id: "vs", label: "Vs Benchmark" },
  { id: "ranks", label: "Rankings" },
]

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value)
  useEffect(() => { const t = setTimeout(() => setV(value), ms); return () => clearTimeout(t) }, [value, ms])
  return v
}

export function MF2View() {
  const { referenceDate } = useStore()
  const [minMonths, setMinMonths] = useState(12)

  const { data: cfg, isError: cfgError } = useQuery<MF2Config>({
    queryKey: ["mf2-config", referenceDate ?? null, minMonths],
    queryFn: async () => {
      const qs = new URLSearchParams({ min_months: String(minMonths) })
      if (referenceDate) qs.set("reference_date", referenceDate)
      const r = await fetch(`${API_BASE_URL}/api/mf2/config?${qs}`)
      if (!r.ok) throw new Error(`Config failed: ${r.status}`)
      return r.json()
    },
    staleTime: Infinity,
    placeholderData: prev => prev,
  })

  // ── selection state ───────────────────────────────────────────────────
  const [deselClasses, setDeselClasses] = useState<Set<string>>(new Set())   // exclusions => all selected by default
  const [selFunds, setSelFunds] = useState<Set<number>>(new Set())
  const [selIndices, setSelIndices] = useState<Set<string>>(new Set())       // none by default
  const [selPeriods, setSelPeriods] = useState<number[]>(ALL_PERIODS)
  const [benchmark, setBenchmark] = useState("NIFTY 50")
  const [sub, setSub] = useState<SubTab>("returns")
  const [coverage, setCoverage] = useState<Coverage>("half")
  const [rollStart, setRollStart] = useState<number | null>(null)
  const seenFunds = useRef<Set<number>>(new Set())

  const allClasses = useMemo(() => cfg?.classes.map(c => c.id) ?? [], [cfg])
  const selClasses = useMemo(() => new Set(allClasses.filter(c => !deselClasses.has(c))), [allClasses, deselClasses])
  const fundOptions = useMemo(() => (cfg?.funds ?? []).filter(f => selClasses.has(f.k)), [cfg, selClasses])

  // Funds that become visible for the first time (initial load, or a category being ticked) start selected.
  useEffect(() => {
    const fresh = fundOptions.filter(f => !seenFunds.current.has(f.c))
    if (!fresh.length) return
    fresh.forEach(f => seenFunds.current.add(f.c))
    setSelFunds(prev => { const n = new Set(prev); fresh.forEach(f => n.add(f.c)); return n })
  }, [fundOptions])

  const fundCodes = useMemo(() => fundOptions.filter(f => selFunds.has(f.c)).map(f => f.c), [fundOptions, selFunds])
  const indices = useMemo(() => Array.from(selIndices).sort(), [selIndices])
  const periods = useMemo(() => [...selPeriods].sort((a, b) => a - b), [selPeriods])

  const payload = useMemo(
    () => ({ fund_codes: fundCodes, indices, benchmark, periods, reference_date: referenceDate ?? null, min_months: minMonths }),
    [fundCodes, indices, benchmark, periods, referenceDate, minMonths],
  )

  const debounced = useDebounced(payload, 400)

  const { data, isLoading, isFetching, isError, error } = useQuery<MF2Analysis>({
    queryKey: ["mf2-analysis", debounced],
    queryFn: async () => {
      const res = await fetch(`${API_BASE_URL}/api/mf2/analysis`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(debounced),
      })
      if (!res.ok) {
        const e = await res.json().catch(() => ({}))
        throw new Error(e.detail || `Analysis failed: ${res.status}`)
      }
      return res.json()
    },
    enabled: !!cfg,
    placeholderData: prev => prev,
  })

  return (
    <div className="grid grid-cols-1 lg:grid-cols-4 gap-8 pb-20">
      <div className="lg:col-span-1 lg:sticky lg:top-4 lg:self-start">
        <MF2Sidebar
                  cfg={cfg}
                  selClasses={selClasses} onClasses={s => setDeselClasses(new Set(allClasses.filter(c => !s.has(c))))}
                  fundOptions={fundOptions} selFunds={selFunds} onFunds={setSelFunds}
                  selIndices={selIndices} onIndices={setSelIndices}
                  selPeriods={selPeriods} onPeriods={setSelPeriods}
                  benchmark={benchmark} onBenchmark={setBenchmark}
                  reportSlot={<MF2Report fundCodes={fundCodes} indices={indices} benchmark={benchmark} periods={periods}
                      rollStart={rollStart} referenceDate={referenceDate} minMonths={minMonths} />} minMonths={0} onMinMonths={function (m: number): void {
                          throw new Error("Function not implemented.")
                      } }        />
      </div>

      <div className="lg:col-span-3 min-w-0 space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <Tabs value={sub} onValueChange={v => setSub(v as SubTab)}>
            <TabsList className="h-11 inline-flex gap-1 bg-slate-100 dark:bg-slate-900 p-1 rounded-xl border border-slate-200 dark:border-slate-800">
              {SUBTABS.map(t => (
                <TabsTrigger key={t.id} value={t.id} type="button"
                  className="rounded-lg px-4 py-2 text-[11px] font-bold uppercase data-[state=active]:bg-white dark:data-[state=active]:bg-slate-800 data-[state=active]:text-blue-600 data-[state=active]:shadow-sm">
                  {t.label}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>

          <div className="flex items-center gap-4">
            {(sub === "calendar" || sub === "ranks") && (
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">Years with data for</span>
                <Select value={coverage} onValueChange={v => setCoverage(v as Coverage)}>
                  <SelectTrigger className="w-40 h-9 rounded-xl text-xs font-bold"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="any" className="text-xs font-bold">Any item</SelectItem>
                    <SelectItem value="half" className="text-xs font-bold">≥ 50% of items</SelectItem>
                    <SelectItem value="all" className="text-xs font-bold">Every item</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            )}
            {data && (
              <span className="text-[10px] text-slate-400 font-medium">
                {data.items.length} items · month-end NAV as of {fmtDate(data.as_of)}{isFetching ? " · updating…" : ""}
              </span>
            )}
          </div>
        </div>

        {cfgError ? (
          <div className="text-center text-xs text-red-500 py-16">Failed to load Mutual Fund configuration.</div>
        ) : isError && !data ? (
          <div className="text-center text-xs text-red-500 py-16">{(error as Error).message}</div>
        ) : !data ? (
          <div className="py-20"><LoadingSpinner /></div>
        ) : (
          <>
            {sub === "returns" && <ReturnsTab data={data} />}
            {sub === "calendar" && <CalendarTab data={data} coverage={coverage} />}
            {sub === "rolling" && <RollingTab data={data} rollStart={rollStart} setRollStart={setRollStart} />}
            {sub === "vs" && <VsBenchTab data={data} />}
            {sub === "ranks" && <RankingsTab data={data} coverage={coverage} />}
          </>
        )}
      </div>
    </div>
  )
}