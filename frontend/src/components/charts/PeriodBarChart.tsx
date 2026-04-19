"use client"
import { BaseChart } from "./BaseChart"
import { getCategoricalColor } from "@/lib/colors"
import { useTheme } from 'next-themes'
import React, { useMemo } from 'react'

export function PeriodBarChart({ data, colorMode = "conditional", zoomEnabled = false }: any) {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === "dark";

  const xValues = data.map((d: any) => d.indexName);
  const yValues = data.map((d: any) => d.value);
  
  const colors = data.map((d: any) => {
    if (colorMode === "categorical") return getCategoricalColor(d.indexName).hex;
    if (colorMode === "beta") {
      if (d.value > 1.1) return "#ef4444"; 
      if (d.value < 0.9) return "#3b82f6";
      return "#9ca3af";
    }
    return d.value >= 0 ? "#16a34a" : "#dc2626";
  });

  const yAxisConfig = useMemo(() => {
    const minVal = yValues.length > 0 ? Math.min(...yValues.filter(v => typeof v === 'number')) : 0;
    const maxVal = yValues.length > 0 ? Math.max(...yValues.filter(v => typeof v === 'number')) : 0;

    return {
      range: minVal >= 0 ? [0, maxVal * 1.15] : undefined,
      zeroline: true,
      zerolinecolor: isDark ? '#334155' : '#e2e8f0',
      zerolinewidth: 2,
    };
  }, [yValues, isDark]);

  const plotData = [{
    x: xValues,
    y: yValues,
    type: "bar",
    marker: { color: colors, line: { width: 0 }, width: 0.6 },
    hovertemplate: "<b>%{x}</b><br>Value: <b>%{y:.2f}</b><extra></extra>", 
    text: yValues.map((v: any) => (typeof v === 'number' ? v.toFixed(2) : "—")),
    textposition: 'outside', 
    textfont: { size: 9, family: "Geist Mono", color: isDark ? "#d1d5db" : "#374151" } 
  }];

  return (
    <BaseChart
      data={plotData as any}
      zoomEnabled={zoomEnabled}
      layout={{
        xaxis: { tickangle: -45, automargin: true, showline: true, linecolor: isDark ? '#334155' : '#e2e8f0' },
        yaxis: { side: "right", ...yAxisConfig, automargin: true },
        margin: { t: 20, b: 120, l: 20, r: 60 },
        hovermode: "closest", 
      }}
    />
  )
}