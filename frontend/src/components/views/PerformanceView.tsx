"use client"

import React from "react"
import { MetricSection } from "../dashboard/MetricSection"
import { NavView } from "./NavView" // Assuming NavView is in the same folder

export function PerformanceView() {
  return (
    <div className="space-y-12 pb-20">
      {/* Table + Bar Chart combo with Download button inside MetricSection */}
      <MetricSection 
        title="CAGR — Annualised Returns (%)" 
        metric="cagr" 
        chartLabel="CAGR %" 
        colorMode="conditional"
      />
    </div>
  );
}