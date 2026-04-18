"use client"

import { useQuery } from "@tanstack/react-query"
import { useStore } from "@/store/useStore"
import { BaseChart } from "./BaseChart"
import { getCategoricalColor } from "@/lib/colors"

export function RiskReturnChart() {
  const { selectedIndices, periods } = useStore()
  const activePeriod = periods[0] // e.g., "5 Yr"

  const { data } = useQuery({
    queryKey: ["scatter", selectedIndices, activePeriod],
    queryFn: async () => {
      const res = await fetch("http://localhost:8000/api/scatter-data", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ metric: "", periods: [activePeriod], indices: selectedIndices, benchmark: "" })
      })
      return res.json()
    }
  })

  const plotData = [{
    x: data?.map((d: any) => d.risk),
    y: data?.map((d: any) => d.return),
    text: data?.map((d: any) => d.index),
    mode: 'markers+text',
    type: 'scatter',
    textposition: 'top center',
    marker: { 
        size: 12, 
        color: data?.map((d: any) => getCategoricalColor(d.index).hex),
        line: { width: 2, color: 'white' }
    },
    hovertemplate: "<b>%{text}</b><br>Risk: %{x:.2f}%<br>Return: %{y:.2f}%<extra></extra>"
  }]

  return (
    <div className="h-[500px] w-full">
      <BaseChart 
        data={plotData as any} 
        layout={{ 
            xaxis: { title: "Risk (Volatility %)", showgrid: false },
            yaxis: { title: "Return (CAGR %)", gridcolor: '#f1f5f9' },
            hovermode: 'closest'
        }} 
      />
    </div>
  )
}