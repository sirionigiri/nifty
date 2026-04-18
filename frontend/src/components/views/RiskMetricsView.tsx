"use client"
import { MetricSection } from "../dashboard/MetricSection"

export function RiskMetricsView() {
  return (
    <div className="space-y-12">
      <MetricSection title="Volatility — Annualised (%)" metric="vol" chartLabel="Volatility %" colorMode="categorical" />
      <MetricSection title="Max Drawdown (%)" metric="mdd" chartLabel="Drawdown %" colorMode="conditional" />
      <MetricSection title="Beta vs Benchmark" metric="beta" chartLabel="Beta Value" colorMode="beta" />
    </div>
  )
}