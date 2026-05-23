"use client"

import { useQuery } from "@tanstack/react-query"
import { useStore } from "@/store/useStore"
import { Card, CardContent } from "@/components/ui/card"
import { API_BASE_URL } from "@/lib/utils"

export function SummaryCards() {
  const { benchmark, selectedIndices, referenceDate } = useStore() // Get referenceDate

  const { data } = useQuery({
    queryKey: ["summary", benchmark, selectedIndices.length, referenceDate],
    queryFn: async () => {
      const res = await fetch(`${API_BASE_URL}/api/summary`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // Pass referenceDate to backend
        body: JSON.stringify({ benchmark, indices: selectedIndices, metric: "", periods: [], reference_date: referenceDate })
      })
      return res.json()
    }
  })

  // Helper to determine color based on value string
  const getColor = (val: string | undefined, defaultColor: string) => {
    if (!val || val === "—") return "text-slate-400";
    if (val.startsWith("-")) return "text-red-600 dark:text-red-500";
    if (val.startsWith("+") || parseFloat(val) > 0) return "text-green-600 dark:text-green-500";
    return defaultColor;
  }

  const cards = [
    { title: `${benchmark} · 1Y CAGR`, value: data?.cagr1, sub: "calculated from ref", color: getColor(data?.cagr1, "text-green-600") },
    { title: `${benchmark} · 20Y CAGR`, value: data?.cagr20, sub: "20-year window", color: getColor(data?.cagr20, "text-green-600") },
    { title: `${benchmark} · Max DD (YTD)`, value: data?.mdd1, sub: "ref date to Jan 1", color: "text-red-600" }, // Always red for DD
    { title: `${benchmark} · Vol (YTD)`, value: data?.vol1, sub: "ref date to Jan 1", color: "text-amber-500" },
    { title: `Indices Selected`, value: selectedIndices.length, sub: `active in analysis`, color: "text-blue-600" },
  ]

  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
      {cards.map((c, i) => (
        <Card key={i} className="border-none shadow-sm bg-white dark:bg-slate-900/50 rounded-2xl overflow-hidden relative">
          <div className={`absolute top-0 left-0 w-full h-1 bg-current opacity-10 ${c.color}`} />
          <CardContent className="p-4 pt-5">
            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1 truncate">{c.title}</p>
            <h3 className={`text-2xl font-black font-mono ${c.color} tracking-tighter`}>{c.value || "—"}</h3>
            <p className="text-[10px] text-slate-500 mt-1 uppercase tracking-tight font-medium">{c.sub}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}