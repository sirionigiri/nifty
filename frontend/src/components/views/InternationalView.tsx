"use client"

import React from "react"
import { useStore } from "@/store/useStore"
import { MetricSection } from "../dashboard/MetricSection"

export function InternationalView() {
  const { benchmark } = useStore();

  // THE FIXED "INTERNATIONAL" LIST
  // These are exactly the names used in your international_data.parquet
  const allIntl = [
    "S&P 500", 
    "Nasdaq 100 Futures", 
    "Bitcoin", 
    "Gold", 
    "Silver", 
    "EEM", 
    "KOSPI", 
    "Shanghai Composite", 
    "Bovespa", 
    "Mexico IPC", 
    "TAIEX", 
    "S&P Europe 350"
  ];

  return (
    <div className="space-y-12 pb-20">
      

      {/* 1. PERFORMANCE BLOCK (FORCED) */}
      <MetricSection 
        title="Global Performance Matrix" 
        metric="cagr" 
        chartLabel="Return %" 
        forcedIndices={allIntl} 
        colorMode="categorical"
      />

      {/* 2. RISK BLOCK (FORCED) */}
      <MetricSection 
        title="Global Volatility Comparison" 
        metric="vol" 
        chartLabel="Volatility %" 
        forcedIndices={allIntl} 
        colorMode="categorical"
      />

      {/* 3. DRAWDOWN BLOCK (FORCED) */}
      <MetricSection 
        title="Global Maximum Drawdown" 
        metric="mdd" 
        chartLabel="Drawdown %" 
        forcedIndices={allIntl} 
        colorMode="conditional"
      />
    </div>
  );
}