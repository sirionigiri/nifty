"use client"

import { useQuery } from "@tanstack/react-query"
import { useStore } from "@/store/useStore"
import { Card, CardContent } from "@/components/ui/card"

export function SummaryCards() {
  const { benchmark, selectedIndices } = useStore()

  const { data } = useQuery({
    queryKey: ["summary", benchmark, selectedIndices.length],
    queryFn: async () => {
      const res = await fetch("http://localhost:8000/api/summary", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ benchmark, indices: selectedIndices, metric: "", periods: [] })
      })
      return res.json()
    }
  })

  const cards = [
    { title: `${benchmark} · 1Y CAGR`, value: data?.cagr1, sub: "latest 1 year", color: "text-green-600" },
    { title: `${benchmark} · 20Y CAGR`, value: data?.cagr20, sub: "20-year annualised", color: "text-green-600" },
    { title: `${benchmark} · Max DD (YTD)`, value: data?.mdd1, sub: "year to date", color: "text-red-600" },
    { title: `${benchmark} · Vol (YTD)`, value: data?.vol1, sub: "year to date", color: "text-amber-500" },
    { title: `Indices Selected`, value: data?.count, sub: `currently analyzing`, color: "text-blue-600" },
  ]

  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
      {cards.map((c, i) => (
        <Card key={i} className="border-none shadow-sm bg-white dark:bg-slate-900/50 rounded-2xl overflow-hidden relative">
          <div className={`absolute top-0 left-0 w-full h-1 bg-current opacity-10 ${c.color}`} />
          <CardContent className="p-4 pt-5">
            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">{c.title}</p>
            <h3 className={`text-2xl font-black font-mono ${c.color} tracking-tighter`}>{c.value || "—"}</h3>
            <p className="text-[10px] text-slate-500 mt-1 uppercase tracking-tight font-medium">{c.sub}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}