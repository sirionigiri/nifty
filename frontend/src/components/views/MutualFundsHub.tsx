"use client"

import React, { useState } from "react"
import { MutualFundsView } from "@/components/views/MutualFundsView"
import { MF2View } from "@/components/mf2/MF2View"

export function MutualFundsHub() {
  const [sub, setSub] = useState<"impl1" | "impl2">("impl1")
  const [visited2, setVisited2] = useState(false)

  const go = (id: "impl1" | "impl2") => { setSub(id); if (id === "impl2") setVisited2(true) }

  return (
    <div className="space-y-8">
      <div className="inline-flex gap-1 bg-slate-100 dark:bg-slate-900 p-1 rounded-xl border border-slate-200 dark:border-slate-800">
        {([["impl1", "Implementation 1"], ["impl2", "Implementation 2"]] as const).map(([id, label]) => (
          <button key={id} type="button" onClick={() => go(id)}
            className={`px-5 py-2 rounded-lg text-[11px] font-bold uppercase transition-all ${sub === id ? "bg-white dark:bg-slate-800 text-blue-600 shadow-sm" : "text-slate-500"}`}>
            {label}
          </button>
        ))}
      </div>

      <div className={sub === "impl1" ? "" : "hidden"}><MutualFundsView /></div>
      {visited2 && <div className={sub === "impl2" ? "" : "hidden"}><MF2View /></div>}
    </div>
  )
}