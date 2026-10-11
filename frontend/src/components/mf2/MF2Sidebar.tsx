"use client"

import React, { useMemo, useState } from "react"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command"
import { Check, ChevronsUpDown, Filter, Search } from "lucide-react"
import { cn } from "@/lib/utils"
import type { MF2Config, MF2Fund } from "@/components/mf2/types"

export const ALL_PERIODS = [1, 3, 5, 10, 15, 20]

function Header({ title, count, onAll, onNone }: { title: string; count?: string; onAll: () => void; onNone: () => void }) {
  return (
    <div className="flex items-center justify-between">
      <h4 className="text-[10px] font-black uppercase tracking-widest text-slate-400">
        {title}{count && <span className="ml-2 text-slate-300 font-bold normal-case">{count}</span>}
      </h4>
      <div className="flex gap-1">
        <button type="button" onClick={onAll} className="text-[9px] font-black uppercase px-2 py-1 rounded-md bg-blue-50 text-blue-600 hover:bg-blue-100 dark:bg-blue-900/20">All</button>
        <button type="button" onClick={onNone} className="text-[9px] font-black uppercase px-2 py-1 rounded-md bg-slate-100 text-slate-500 hover:bg-slate-200 dark:bg-slate-800">None</button>
      </div>
    </div>
  )
}

function SearchableList<K extends string | number>({
  title, items, selected, onChange, placeholder,
}: {
  title: string
  items: { id: K; label: string; sub?: string }[]
  selected: Set<K>
  onChange: (s: Set<K>) => void
  placeholder: string
}) {
  const [q, setQ] = useState("")
  const shown = useMemo(() => {
    const s = q.trim().toLowerCase()
    return s ? items.filter(i => i.label.toLowerCase().includes(s)) : items
  }, [items, q])
  const nSel = useMemo(() => items.reduce((n, i) => n + (selected.has(i.id) ? 1 : 0), 0), [items, selected])

  // "All" / "None" act on what's currently visible, so they respect the search box
  const all = () => { const n = new Set(selected); shown.forEach(i => n.add(i.id)); onChange(n) }
  const none = () => { const n = new Set(selected); shown.forEach(i => n.delete(i.id)); onChange(n) }

  return (
    <div className="space-y-3 pt-4 border-t border-slate-100 dark:border-slate-800">
      <Header title={title} count={`${nSel}/${items.length}`} onAll={all} onNone={none} />
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3 h-3 text-slate-400" />
        <Input value={q} onChange={e => setQ(e.target.value)} placeholder={placeholder} className="pl-9 h-9 text-xs rounded-xl" />
      </div>
      <div className="max-h-56 overflow-y-auto space-y-0.5 pr-1">
        {shown.length === 0 && <p className="text-[10px] text-slate-400 py-2">No matches.</p>}
        {shown.map(i => (
          <label key={String(i.id)} className="flex items-start gap-2 px-1 py-1 rounded-md hover:bg-slate-50 dark:hover:bg-slate-800/50 cursor-pointer">
            <input
              type="checkbox" className="mt-0.5 h-3.5 w-3.5 rounded accent-blue-600 shrink-0"
              checked={selected.has(i.id)}
              onChange={() => { const n = new Set(selected); n.has(i.id) ? n.delete(i.id) : n.add(i.id); onChange(n) }}
            />
            <span className="text-[11px] font-medium leading-tight text-slate-600 dark:text-slate-300">
              {i.label}{i.sub && <span className="block text-[9px] text-slate-400">{i.sub}</span>}
            </span>
          </label>
        ))}
      </div>
    </div>
  )
}

function BenchmarkPicker({ value, options, onChange }: { value: string; options: string[]; onChange: (v: string) => void }) {
  const [open, setOpen] = useState(false)
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" role="combobox" aria-expanded={open}
          className="w-full justify-between h-10 rounded-xl text-xs font-bold">
          <span className="truncate">{value || "Select index..."}</span>
          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-72 p-0 rounded-xl shadow-2xl">
        <Command>
          <CommandInput placeholder="Search indices..." className="h-10 text-xs" />
          <CommandList className="max-h-[280px]">
            <CommandEmpty className="py-6 text-center text-xs text-slate-500">No index found.</CommandEmpty>
            <CommandGroup>
              {options.map(idx => (
                <CommandItem key={idx} value={idx} onSelect={() => { onChange(idx); setOpen(false) }} className="text-xs font-bold cursor-pointer">
                  <Check className={cn("mr-2 h-4 w-4 text-blue-600", value === idx ? "opacity-100" : "opacity-0")} />
                  {idx}
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}

type Props = {
  cfg?: MF2Config
  selClasses: Set<string>; onClasses: (s: Set<string>) => void
  fundOptions: MF2Fund[]
  selFunds: Set<number>; onFunds: (s: Set<number>) => void
  selIndices: Set<string>; onIndices: (s: Set<string>) => void
  selPeriods: number[]; onPeriods: (p: number[]) => void
  benchmark: string; onBenchmark: (b: string) => void
  reportSlot: React.ReactNode
minMonths: number; onMinMonths: (m: number) => void
  hidden?: number
}

export function MF2Sidebar(p: Props) {
  const classes = p.cfg?.classes ?? []
  const fundItems = useMemo(() => p.fundOptions.map(f => ({ id: f.c, label: f.n, sub: f.k })), [p.fundOptions])
  const indexItems = useMemo(() => (p.cfg?.indices ?? []).map(i => ({ id: i, label: i })), [p.cfg])

  return (
    <div className="bg-white dark:bg-slate-900/40 p-6 rounded-3xl border border-slate-200 dark:border-slate-800 space-y-5 max-h-[calc(100vh-7rem)] overflow-y-auto">
      <div className="flex items-center gap-2 border-b pb-4">
        <Filter className="w-4 h-4 text-blue-600" />
        <h3 className="text-xs font-black uppercase tracking-widest">MF Analytics</h3>
      </div>

      {/* BENCHMARK */}
      <div className="space-y-2">
        <h4 className="text-[10px] font-black uppercase tracking-widest text-slate-400">Benchmark (always included)</h4>
        <BenchmarkPicker value={p.benchmark} options={p.cfg?.indices ?? []} onChange={p.onBenchmark} />
      </div>

      {/* ELIGIBILITY */}
      <div className="space-y-2 pt-4 border-t border-slate-100 dark:border-slate-800">
        <h4 className="text-[10px] font-black uppercase tracking-widest text-slate-400">Minimum NAV history</h4>
        <Select value={String(p.minMonths)} onValueChange={v => p.onMinMonths(Number(v))}>
          <SelectTrigger className="w-full h-10 rounded-xl text-xs font-bold"><SelectValue /></SelectTrigger>
          <SelectContent>
            {[[12, "12 months"], [36, "3 years"], [60, "5 years"], [120, "10 years"], [0, "Any (live funds)"]].map(([m, l]) => (
              <SelectItem key={m} value={String(m)} className="text-xs font-bold">{l}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-[10px] text-slate-400 leading-snug">
          Closed funds and funds without a recent NAV are always hidden{p.hidden ? ` · ${p.hidden} hidden` : ""}
        </p>
      </div>

      {/* CATEGORIES */}
      <div className="space-y-3 pt-4 border-t border-slate-100 dark:border-slate-800">
        <Header title="Fund Categories"
          onAll={() => p.onClasses(new Set(classes.map(c => c.id)))} onNone={() => p.onClasses(new Set())} />
        <div className="space-y-2">
          {classes.map(c => (
            <label key={c.id} className="flex items-center gap-2 cursor-pointer">
              <Checkbox checked={p.selClasses.has(c.id)}
                onCheckedChange={() => { const n = new Set(p.selClasses); n.has(c.id) ? n.delete(c.id) : n.add(c.id); p.onClasses(n) }} />
              <span className="text-xs font-bold text-slate-600 dark:text-slate-300">{c.id}</span>
              <span className="text-[10px] text-slate-400">({c.count})</span>
            </label>
          ))}
        </div>
      </div>

      <SearchableList title="Mutual Fund Schemes" items={fundItems} selected={p.selFunds} onChange={p.onFunds} placeholder="Search schemes..." />
      <SearchableList title="Indices" items={indexItems} selected={p.selIndices} onChange={p.onIndices} placeholder="Search indices..." />

      {/* PERIODS */}
      <div className="space-y-3 pt-4 border-t border-slate-100 dark:border-slate-800">
        <Header title="Time Periods" onAll={() => p.onPeriods(ALL_PERIODS)} onNone={() => p.onPeriods([])} />
        <div className="grid grid-cols-3 gap-2">
          {ALL_PERIODS.map(n => (
            <label key={n} className="flex items-center gap-2 cursor-pointer">
              <Checkbox checked={p.selPeriods.includes(n)}
                onCheckedChange={() => p.onPeriods(p.selPeriods.includes(n) ? p.selPeriods.filter(x => x !== n) : [...p.selPeriods, n])} />
              <span className="text-xs font-bold text-slate-600 dark:text-slate-300">{n} Yr</span>
            </label>
          ))}
        </div>
      </div>

      <div className="pt-4 border-t border-slate-100 dark:border-slate-800">{p.reportSlot}</div>
    </div>
  )
}