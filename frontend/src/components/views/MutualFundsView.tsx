"use client"

import React, { useState, useMemo, useEffect, useRef } from "react"
import { useQuery } from "@tanstack/react-query"
import { useStore } from "@/store/useStore"
import { DataTable } from "@/components/DataTable"
import { Input } from "@/components/ui/input"
import { Checkbox } from "@/components/ui/checkbox"
import { API_BASE_URL } from "@/lib/utils"
import { LoadingSpinner } from "../ui/LoadingSpinner"
import { Search, Filter, ChevronDown, ChevronRight } from "lucide-react"

type Facet = { subcategory: number; riskometer: string; benchmark: string }

type MFConfig = {
  categories: Record<string, { name: string; subs: Record<string, string> }>
  riskometers: string[]
  benchmarks: string[]
  facets: Facet[]
}

function formatPct(val: number | null | undefined) {
  if (val === null || val === undefined || Number.isNaN(val)) return "—"
  return `${val.toFixed(2)}%`
}

function formatNav(val: number | null | undefined) {
  if (val === null || val === undefined || Number.isNaN(val)) return "—"
  return val.toFixed(2)
}

function pctColor(val: number | null | undefined) {
  if (val === null || val === undefined) return "text-slate-400"
  return val > 0 ? "text-green-600" : val < 0 ? "text-red-600" : "text-slate-500"
}

// Given the full facet list and the currently active filters, return the set of
// values still valid for ONE dimension (excludeDim), with that dimension's own
// filter ignored (so its options reflect everything else that's selected).
function getAvailable(
  facets: Facet[],
  filters: { subs: number[]; risks: string[]; benches: string[] },
  excludeDim: "subs" | "risks" | "benches"
): Set<string | number> {
  const filtered = facets.filter(f => {
    if (excludeDim !== "subs" && filters.subs.length && !filters.subs.includes(f.subcategory)) return false
    if (excludeDim !== "risks" && filters.risks.length && !filters.risks.includes(f.riskometer)) return false
    if (excludeDim !== "benches" && filters.benches.length && !filters.benches.includes(f.benchmark)) return false
    return true
  })
  if (excludeDim === "subs") return new Set(filtered.map(f => f.subcategory))
  if (excludeDim === "risks") return new Set(filtered.map(f => f.riskometer))
  return new Set(filtered.map(f => f.benchmark))
}

export function MutualFundsView() {
  const { benchmark, referenceDate } = useStore()

  const [search, setSearch] = useState("")
  const [selectedSubs, setSelectedSubs] = useState<number[]>([])
  const [selectedRiskometers, setSelectedRiskometers] = useState<string[]>([])
  const [selectedBenchmarks, setSelectedBenchmarks] = useState<string[]>([])
  const [openCategory, setOpenCategory] = useState<string | null>("1") // default open Equity
  const [page, setPage] = useState(1)
  const PAGE_SIZE = 100
  const didInitDefaults = useRef(false)

  const { data: config, isError: configError } = useQuery<MFConfig>({
    queryKey: ["mf-config"],
    queryFn: async () => {
      const res = await fetch(`${API_BASE_URL}/api/mf-config`)
      if (!res.ok) throw new Error(`Config fetch failed: ${res.status}`)
      return res.json()
    },
    staleTime: Infinity,
  })

  // ── Default selection: Equity category (all its subs) + "Very High" riskometer ──
  // ── Default selection: Equity > Large Cap only + "Very High" riskometer ──
    useEffect(() => {
    if (config && !didInitDefaults.current) {
        const largeCap = config.categories?.["1"]?.subs?.["1"] // category 1 = Equity, sub 1 = Large Cap
        if (largeCap) {
        setSelectedSubs([1])
        }
        if (config.riskometers?.includes("Very High")) {
        setSelectedRiskometers(["Very High"])
        }
        didInitDefaults.current = true
    }
    }, [config])

  const facets = config?.facets ?? []

  // ── Faceted option sets: what's actually selectable given the OTHER active filters ──
  const availableSubs = useMemo(
    () => getAvailable(facets, { subs: selectedSubs, risks: selectedRiskometers, benches: selectedBenchmarks }, "subs"),
    [facets, selectedRiskometers, selectedBenchmarks]
  )
  const availableRiskometers = useMemo(
    () => getAvailable(facets, { subs: selectedSubs, risks: selectedRiskometers, benches: selectedBenchmarks }, "risks"),
    [facets, selectedSubs, selectedBenchmarks]
  )
  const availableBenchmarks = useMemo(
    () => getAvailable(facets, { subs: selectedSubs, risks: selectedRiskometers, benches: selectedBenchmarks }, "benches"),
    [facets, selectedSubs, selectedRiskometers]
  )

  const { data, isLoading, isError } = useQuery({
    queryKey: [
      "mf-data", benchmark, referenceDate, search,
      selectedSubs, selectedRiskometers, selectedBenchmarks, page,
    ],
    queryFn: async () => {
      const res = await fetch(`${API_BASE_URL}/api/mf-data`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          search,
          subcategories: selectedSubs,
          riskometers: selectedRiskometers,
          benchmarks: selectedBenchmarks,
          compare_index: benchmark,
          reference_date: referenceDate,
          page,
          page_size: PAGE_SIZE,
        }),
      })
      if (!res.ok) throw new Error(`Request failed: ${res.status}`)
      return res.json()
    },
    enabled: didInitDefaults.current || !config, // wait for defaults to be set once config arrives
  })

  const rows = data?.rows ?? []
  const comparisonRow = data?.comparison_row
  const total = data?.total ?? 0
  const tableRows = comparisonRow ? [comparisonRow, ...rows] : rows

  const toggleSub = (subId: number) => {
    setPage(1)
    setSelectedSubs(prev =>
      prev.includes(subId) ? prev.filter(s => s !== subId) : [...prev, subId]
    )
  }

  const toggleCategory = (subIds: number[]) => {
    setPage(1)
    const allSelected = subIds.every(id => selectedSubs.includes(id))
    setSelectedSubs(prev => {
      if (allSelected) return prev.filter(id => !subIds.includes(id))
      return Array.from(new Set([...prev, ...subIds]))
    })
  }

  const toggleRiskometer = (val: string) => {
    setPage(1)
    setSelectedRiskometers(prev =>
      prev.includes(val) ? prev.filter(r => r !== val) : [...prev, val]
    )
  }

  const toggleBenchmark = (val: string) => {
    setPage(1)
    setSelectedBenchmarks(prev =>
      prev.includes(val) ? prev.filter(b => b !== val) : [...prev, val]
    )
  }

  const columns = useMemo(() => [
    {
      accessorKey: "schemeName",
      header: "Scheme Name",
      cell: ({ row }: any) => (
        <div className="py-2">
          <span className={row.original.is_benchmark ? "font-black text-blue-600" : "font-bold text-slate-700 dark:text-slate-200"}>
            {row.getValue("schemeName")}
          </span>
          {!row.original.is_benchmark && (
            <div className="flex gap-2 mt-1">
              <span className="text-[9px] bg-slate-100 dark:bg-slate-800 px-1 rounded text-slate-500 font-bold">
                {row.original.riskometerScheme}
              </span>
            </div>
          )}
        </div>
      ),
    },
    {
      accessorKey: "benchmark",
      header: "AMFI Benchmark",
      cell: ({ row }: any) => (
        <span className="text-[10px] text-slate-500 font-medium uppercase">{row.getValue("benchmark")}</span>
      ),
    },
    {
      accessorKey: "navRegular",
      header: "NAV",
      cell: ({ row }: any) => <div className="text-right font-mono">{formatNav(row.getValue("navRegular"))}</div>,
    },
    {
      accessorKey: "return1YearRegular",
      header: "1 Yr (%)",
      cell: ({ row }: any) => {
        const val = row.getValue("return1YearRegular")
        return <div className={`text-right font-mono font-bold ${pctColor(val)}`}>{formatPct(val)}</div>
      },
    },
    {
      accessorKey: "return3YearRegular",
      header: "3 Yr (%)",
      cell: ({ row }: any) => {
        const val = row.getValue("return3YearRegular")
        return <div className={`text-right font-mono font-bold ${pctColor(val)}`}>{formatPct(val)}</div>
      },
    },
    {
      accessorKey: "return5YearRegular",
      header: "5 Yr (%)",
      cell: ({ row }: any) => {
        const val = row.getValue("return5YearRegular")
        return <div className={`text-right font-mono font-bold ${pctColor(val)}`}>{formatPct(val)}</div>
      },
    },
    {
      accessorKey: "return10YearRegular",
      header: "10 Yr (%)",
      cell: ({ row }: any) => {
        const val = row.getValue("return10YearRegular")
        return <div className={`text-right font-mono font-bold ${pctColor(val)}`}>{formatPct(val)}</div>
      },
    },
  ], [])

  const totalPages = Math.max(Math.ceil(total / PAGE_SIZE), 1)

  return (
    <div className="space-y-8 pb-20">
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">

        {/* LEFT: FILTERS */}
        <div className="lg:col-span-1 space-y-6 bg-white dark:bg-slate-900/40 p-6 rounded-3xl border border-slate-200 dark:border-slate-800 h-fit max-h-[80vh] overflow-y-auto">
          <div className="flex items-center gap-2 mb-4 border-b pb-4">
            <Filter className="w-4 h-4 text-blue-600" />
            <h3 className="text-xs font-black uppercase tracking-widest">MF Explorer</h3>
          </div>

          {configError && (
            <div className="text-[10px] text-red-500 px-1">Failed to load filters.</div>
          )}

          <div className="space-y-6">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3 h-3 text-slate-400" />
              <Input
                placeholder="Search schemes..."
                className="pl-9 h-9 text-xs rounded-xl"
                value={search}
                onChange={(e) => { setPage(1); setSearch(e.target.value) }}
              />
            </div>

            {/* Category / Subcategory accordion */}
            <div className="space-y-2 pt-4 border-t">
              <h4 className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-2">Category</h4>
              {config?.categories && Object.entries(config.categories).map(([catId, cat]) => {
                const subIds = Object.keys(cat.subs).map(Number)
                const allSelected = subIds.length > 0 && subIds.every(id => selectedSubs.includes(id))
                const someSelected = subIds.some(id => selectedSubs.includes(id))
                const isOpen = openCategory === catId

                return (
                  <div key={catId} className="border border-slate-100 dark:border-slate-800 rounded-xl overflow-hidden">
                    <button
                      type="button"
                      onClick={() => setOpenCategory(isOpen ? null : catId)}
                      className="w-full flex items-center justify-between px-3 py-2 hover:bg-slate-50 dark:hover:bg-slate-800/50"
                    >
                      <div className="flex items-center gap-2">
                        <Checkbox
                          checked={allSelected}
                          className={someSelected && !allSelected ? "opacity-60" : ""}
                          onCheckedChange={() => toggleCategory(subIds)}
                          onClick={(e: any) => e.stopPropagation()}
                        />
                        <span className="text-xs font-bold text-slate-600 dark:text-slate-300">{cat.name}</span>
                      </div>
                      {isOpen ? <ChevronDown className="w-3 h-3 text-slate-400" /> : <ChevronRight className="w-3 h-3 text-slate-400" />}
                    </button>

                    {isOpen && (
                      <div className="px-3 pb-3 pt-1 space-y-2 bg-slate-50/50 dark:bg-slate-900/30">
                        {Object.entries(cat.subs).map(([subId, subName]) => {
                          const id = Number(subId)
                          const isSelected = selectedSubs.includes(id)
                          const isAvailable = availableSubs.has(id) || isSelected
                          return (
                            <div key={subId} className={`flex items-center gap-2 pl-5 ${!isAvailable ? "opacity-35" : ""}`}>
                              <Checkbox
                                id={`sub-${subId}`}
                                checked={isSelected}
                                disabled={!isAvailable}
                                onCheckedChange={() => isAvailable && toggleSub(id)}
                              />
                              <label
                                htmlFor={`sub-${subId}`}
                                className={`text-[11px] font-medium ${!isAvailable ? "text-slate-400 cursor-not-allowed" : "text-slate-600 dark:text-slate-400 cursor-pointer"}`}
                              >
                                {subName}
                              </label>
                            </div>
                          )
                        })}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>

            {/* Riskometer */}
            <div className="space-y-2 pt-4 border-t">
              <h4 className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-2">Riskometer</h4>
              <div className="space-y-2 max-h-40 overflow-y-auto">
                {config?.riskometers?.map(risk => {
                  const isSelected = selectedRiskometers.includes(risk)
                  const isAvailable = availableRiskometers.has(risk) || isSelected
                  return (
                    <div key={risk} className={`flex items-center gap-2 ${!isAvailable ? "opacity-35" : ""}`}>
                      <Checkbox
                        id={`risk-${risk}`}
                        checked={isSelected}
                        disabled={!isAvailable}
                        onCheckedChange={() => isAvailable && toggleRiskometer(risk)}
                      />
                      <label
                        htmlFor={`risk-${risk}`}
                        className={`text-xs font-bold ${!isAvailable ? "text-slate-400 cursor-not-allowed" : "text-slate-600 cursor-pointer"}`}
                      >
                        {risk}
                      </label>
                    </div>
                  )
                })}
              </div>
            </div>

            {/* Benchmark */}
            <div className="space-y-2 pt-4 border-t">
              <h4 className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-2">AMFI Benchmark</h4>
              <div className="space-y-2 max-h-40 overflow-y-auto">
                {config?.benchmarks?.map(b => {
                  const isSelected = selectedBenchmarks.includes(b)
                  const isAvailable = availableBenchmarks.has(b) || isSelected
                  return (
                    <div key={b} className={`flex items-center gap-2 ${!isAvailable ? "opacity-35" : ""}`}>
                      <Checkbox
                        id={`bench-${b}`}
                        checked={isSelected}
                        disabled={!isAvailable}
                        onCheckedChange={() => isAvailable && toggleBenchmark(b)}
                      />
                      <label
                        htmlFor={`bench-${b}`}
                        className={`text-[11px] font-medium truncate ${!isAvailable ? "text-slate-400 cursor-not-allowed" : "text-slate-600 cursor-pointer"}`}
                      >
                        {b}
                      </label>
                    </div>
                  )
                })}
              </div>
            </div>
          </div>
        </div>

        {/* RIGHT: TABLE */}
        <div className="lg:col-span-3 space-y-4">
          <div className="flex items-center justify-between px-2">
            <div className="flex items-center gap-3">
              <div className="h-6 w-1 bg-blue-600 rounded-full" />
              <h3 className="text-[11px] font-black uppercase tracking-[0.2em] text-slate-500">
                Mutual Fund Performance vs {benchmark}
              </h3>
            </div>
            {!isLoading && !isError && (
              <span className="text-[10px] text-slate-400 font-medium">
                {total.toLocaleString()} funds match filters
              </span>
            )}
          </div>

          <div className="screener-table bg-white dark:bg-slate-900/40 rounded-3xl border border-slate-200 dark:border-slate-800 p-2 shadow-sm overflow-hidden">
            {isLoading ? (
              <LoadingSpinner />
            ) : isError ? (
              <div className="text-center text-xs text-red-500 py-10">
                Failed to load mutual fund data. Please try again.
              </div>
            ) : (
              <DataTable columns={columns} data={tableRows} />
            )}
          </div>

          {!isLoading && !isError && totalPages > 1 && (
            <div className="flex items-center justify-center gap-4 pt-2">
              <button
                disabled={page <= 1}
                onClick={() => setPage(p => Math.max(p - 1, 1))}
                className="text-xs font-bold text-slate-500 disabled:opacity-30 px-3 py-1 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800"
              >
                ← Prev
              </button>
              <span className="text-xs text-slate-400 font-medium">Page {page} of {totalPages}</span>
              <button
                disabled={page >= totalPages}
                onClick={() => setPage(p => Math.min(p + 1, totalPages))}
                className="text-xs font-bold text-slate-500 disabled:opacity-30 px-3 py-1 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800"
              >
                Next →
              </button>
            </div>
          )}
        </div>

      </div>
    </div>
  )
}