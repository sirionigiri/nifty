"use client"
import { MetricSection } from "../dashboard/MetricSection"

export function RiskAdjustedView() {
  return (
    <div className="space-y-12 pb-20">
      <MetricSection title="Risk-Adjusted Return (CAGR / VOL)" metric="ra" chartLabel="Ratio" colorMode="categorical" />
      <MetricSection title="Information Ratio" metric="ir" chartLabel="Ratio" colorMode="categorical" />
    </div>
  )
}