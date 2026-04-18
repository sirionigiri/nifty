"use client"

import { BaseChart } from "./BaseChart"
import { getCategoricalColor } from "@/lib/colors"
import { useTheme } from 'next-themes';
import React, { useMemo } from 'react';

export function PeriodBarChart({ data, colorMode = "conditional" }: any) {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === "dark";

  const xValues = data.map((d: any) => d.indexName)
  const yValues = data.map((d: any) => d.value)
  
  const colors = data.map((d: any) => {
    if (colorMode === "categorical") {
      return getCategoricalColor(d.indexName).hex;
    }
    
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

    if (minVal >= 0) {
      return {
        range: [0, maxVal * 1.1],
        fixedrange: true, 
        zeroline: true,
        zerolinecolor: isDark ? '#334155' : '#e2e8f0',
        zerolinewidth: 2,
      };
    } else {
      return {
        fixedrange: false, 
        zeroline: true,
        zerolinecolor: isDark ? '#334155' : '#e2e8f0',
        zerolinewidth: 2,
      };
    }
  }, [yValues, isDark]);


  const plotData = [{
    x: xValues,
    y: yValues,
    type: "bar",
    marker: { 
        color: colors,
        line: { width: 0 },
        width: 0.6
    },
    
    // A cleaner hover template
    hovertemplate: 
      "<b>%{x}</b><br>" +
      "Value: <b>%{y:.2f}</b>" +
      "<extra></extra>", 
    
    hoverlabel: {
      bgcolor: "rgba(0,0,0,0.8)",      
      bordercolor: "rgba(255,255,255,0.2)",
      font: { family: "Geist Sans", size: 13, color: "#f8fafc" }
    },
      
    text: yValues.map((v: number | null | undefined) => 
      (v !== null && v !== undefined) ? v.toFixed(2) : "—"
    ),
    textposition: 'outside', 
    // --- Reduce font size and tracking for cleaner label appearance ---
    textfont: { 
        size: 9, // Reduced font size
        family: "Geist Mono", 
        color: isDark ? "#d1d5db" : "#374151",
    } 
  }];

  return (
    <BaseChart
      data={plotData as any}
      layout={{
        xaxis: { 
            tickangle: -45, 
            automargin: true,
            showline: true,
            linecolor: isDark ? '#334155' : '#e2e8f0', 
            zeroline: false,
            categorygap: 0.4, 
            // ticklabelstep: 1,
            // FIXED: More tight and limited chart margins
        },
        yaxis: { 
            title: "", 
            side: "right",
            ...yAxisConfig,
            automargin: true,
        },
        margin: { t: 20, b: 100, l: 20, r: 60 },
        hovermode: "closest", 
        bargap: 0.2, 
      }}
    />
  )
}