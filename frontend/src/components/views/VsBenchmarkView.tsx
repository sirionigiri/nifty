"use client"
import { MetricSection } from "../dashboard/MetricSection"

export function VsBenchmarkView() {
  return (
    <div className="space-y-12 pb-20">
      <MetricSection title="Excess CAGR vs Benchmark (%)" metric="exc" chartLabel="Alpha %" colorMode="conditional" />
      <MetricSection title="Tracking Error (%)" metric="te" chartLabel="Tracking Error %" colorMode="categorical" />
    </div>
  )
}