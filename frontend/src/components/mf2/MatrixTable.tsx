"use client"

import React, { useMemo, useState } from "react"
import { Button } from "@/components/ui/button"
import { ArrowDown, ArrowLeftRight, ArrowUp, ArrowUpDown, Download } from "lucide-react"
import { exportToExcel } from "@/lib/export"

export type Cell = { text: string; value?: number | null; style?: React.CSSProperties; className?: string }
export type Axis = { key: string; label: string; sub?: string; bold?: boolean }

type Props = {
  title: string
  subtitle?: string
  rowHeader: string
  colHeader: string
  rows: Axis[]
  cols: Axis[]
  cell: (r: number, c: number) => Cell
  exportName: string
  flippable?: boolean
  defaultFlipped?: boolean
  empty?: string
}

const clamp3: React.CSSProperties = { display: "-webkit-box", WebkitLineClamp: 3, WebkitBoxOrient: "vertical", overflow: "hidden" }

export function MatrixTable({
  title, subtitle, rowHeader, colHeader, rows, cols, cell, exportName,
  flippable = false, defaultFlipped = false,
  empty = "No data for the current selection.",
}: Props) {
  const [flip, setFlip] = useState(defaultFlipped)
  const [sortColKey, setSortColKey] = useState<string | null>(null)
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc")

  // Base rows & cols given the current flip state
  const baseR = flip ? cols : rows
  const baseC = flip ? rows : cols
  const getRaw = (rIdx: number, cIdx: number): Cell => (flip ? cell(cIdx, rIdx) : cell(rIdx, cIdx))

  // Sorted row indices
  const rowIndices = useMemo(() => {
    const indices = baseR.map((_, i) => i)
    if (!sortColKey) return indices

    const targetColIdx = baseC.findIndex(c => c.key === sortColKey)
    if (targetColIdx === -1) return indices

    return indices.sort((a, b) => {
      // Benchmark always stays on top if present
      const aBold = baseR[a].bold
      const bBold = baseR[b].bold
      if (aBold !== bBold) return aBold ? -1 : 1

      const cellA = getRaw(a, targetColIdx)
      const cellB = getRaw(b, targetColIdx)
      const valA = cellA.value
      const valB = cellB.value

      const hasA = valA !== null && valA !== undefined && !Number.isNaN(valA)
      const hasB = valB !== null && valB !== undefined && !Number.isNaN(valB)

      if (!hasA && !hasB) return 0
      if (!hasA) return 1
      if (!hasB) return -1

      return sortDir === "asc" ? (valA as number) - (valB as number) : (valB as number) - (valA as number)
    })
  }, [baseR, baseC, sortColKey, sortDir, flip, rows, cols, cell])

  const R = useMemo(() => rowIndices.map(i => baseR[i]), [rowIndices, baseR])
  const C = baseC
  const get = (i: number, j: number): Cell => getRaw(rowIndices[i], j)

  const handleHeaderClick = (colKey: string) => {
    if (sortColKey === colKey) {
      if (sortDir === "desc") {
        setSortDir("asc")
      } else {
        // Reset sort
        setSortColKey(null)
        setSortDir("desc")
      }
    } else {
      setSortColKey(colKey)
      setSortDir("desc")
    }
  }

  const handleExport = () => {
    const out = R.map((r, i) => {
      const o: Record<string, any> = { [flip ? colHeader : rowHeader]: r.label }
      C.forEach((c, j) => {
        let k = c.label
        while (k in o) k += " " // keep duplicate names distinct
        o[k] = get(i, j).value ?? null
      })
      return o
    })
    exportToExcel(out, exportName)
  }

  return (
    <div className="bg-white dark:bg-slate-900/40 rounded-3xl border border-slate-200 dark:border-slate-800 p-4 shadow-sm space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3 px-2">
        <div>
          <div className="flex items-center gap-3">
            <div className="h-6 w-1 bg-blue-600 rounded-full" />
            <h3 className="text-[11px] font-black uppercase tracking-[0.2em] text-slate-500">{title}</h3>
          </div>
          {subtitle && <p className="text-[10px] text-slate-400 font-medium mt-1 ml-4">{subtitle}</p>}
        </div>
        <div className="flex items-center gap-2">
          {flippable && (
            <Button variant="outline" size="sm" onClick={() => { setFlip(f => !f); setSortColKey(null) }}
              className="h-8 text-[10px] font-bold uppercase tracking-widest border-slate-200 dark:border-slate-800">
              <ArrowLeftRight className="w-3 h-3 mr-2" /> Flip
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={handleExport} disabled={!R.length || !C.length}
            className="h-8 text-[10px] font-bold uppercase tracking-widest border-slate-200 dark:border-slate-800 hover:bg-blue-50 dark:hover:bg-blue-900/20 hover:text-blue-600">
            <Download className="w-3 h-3 mr-2" /> Excel
          </Button>
        </div>
      </div>

      {!R.length || !C.length ? (
        <div className="py-12 text-center text-xs text-slate-400 font-medium">{empty}</div>
      ) : (
        <div className="overflow-auto max-h-[70vh] rounded-xl border border-slate-100 dark:border-slate-800">
          <table className="w-max min-w-full text-xs border-separate border-spacing-0">
            <thead>
              <tr>
                <th className="sticky left-0 top-0 z-30 bg-slate-50 dark:bg-slate-900 px-3 py-2 text-left text-[10px] font-black uppercase tracking-wider text-slate-500 min-w-[240px] border-b border-r border-slate-200 dark:border-slate-800">
                  {flip ? colHeader : rowHeader}
                </th>
                {C.map(c => {
                  const isSorted = sortColKey === c.key
                  return (
                    <th key={c.key} title={`${c.label} (Click to sort)`}
                      onClick={() => handleHeaderClick(c.key)}
                      className="sticky top-0 z-20 bg-slate-50 dark:bg-slate-900 px-3 py-2 text-center align-bottom text-[10px] font-black uppercase tracking-wider text-slate-500 min-w-[104px] max-w-[150px] border-b border-slate-200 dark:border-slate-800 cursor-pointer select-none hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors">
                      <div className="flex items-center justify-center gap-1">
                        <div style={clamp3}>{c.label}</div>
                        {isSorted ? (
                          sortDir === "desc" ? <ArrowDown className="w-3 h-3 text-blue-600 shrink-0" /> : <ArrowUp className="w-3 h-3 text-blue-600 shrink-0" />
                        ) : (
                          <ArrowUpDown className="w-2.5 h-2.5 text-slate-300 dark:text-slate-600 opacity-60 hover:opacity-100 shrink-0" />
                        )}
                      </div>
                      {c.sub && <div className="text-[8px] font-bold text-slate-400 normal-case">{c.sub}</div>}
                    </th>
                  )
                })}
              </tr>
            </thead>
            <tbody>
              {R.map((r, i) => (
                <tr key={r.key} className="hover:bg-slate-50/70 dark:hover:bg-slate-800/30">
                  <td className="sticky left-0 z-10 bg-white dark:bg-slate-950 px-3 py-2 min-w-[240px] max-w-[340px] border-b border-r border-slate-100 dark:border-slate-800">
                    <div className={r.bold ? "font-black text-blue-600" : "font-bold text-slate-700 dark:text-slate-200"}>{r.label}</div>
                    {r.sub && <div className="text-[9px] text-slate-400 font-medium">{r.sub}</div>}
                  </td>
                  {C.map((c, j) => {
                    const x = get(i, j)
                    return (
                      <td key={c.key} style={x.style}
                        className={`px-3 py-2 text-center font-mono tabular-nums border-b border-slate-100 dark:border-slate-800 ${x.className ?? ""}`}>
                        {x.text}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
