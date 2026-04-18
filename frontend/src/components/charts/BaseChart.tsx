"use client"

import dynamic from "next/dynamic"
import { useTheme } from "next-themes"
import { Skeleton } from "@/components/ui/skeleton"

const Plot = dynamic(() => import("react-plotly.js"), { 
  ssr: false,
  loading: () => <Skeleton className="w-full h-full min-h-[400px] rounded-xl" />
})

export function BaseChart({ data, layout = {}, config = {} }: any) {
  const { resolvedTheme } = useTheme()
  const isDark = resolvedTheme === "dark"

  const textColor = isDark ? '#d1d5db' : '#374151';
  const gridColor = isDark ? '#1e293b' : '#e5e7eb';
  const lineColor = isDark ? '#334155' : '#d1d5db';
  const hoverBg = isDark ? "#1e293b" : "#ffffff";
  const hoverBorder = isDark ? "#334155" : "#e2e8f0";
  const hoverFontColor = isDark ? "#f8fafc" : "#0f172a";

  const baseLayout = {
    template: {
      layout: {
        font: { family: "Geist Sans, sans-serif", color: textColor, size: 10 },
        hoverlabel: {
          bgcolor: hoverBg,
          bordercolor: hoverBorder,
          font: { color: hoverFontColor, size: 12, family: "Geist Mono" },
          align: "left",
        },
        xaxis: {
          showgrid: false,
          linecolor: lineColor,
          zeroline: false,
          ticks: "outside",
          tickcolor: lineColor,
          automargin: true,
          fixedrange: layout.xaxis?.fixedrange === undefined ? false : layout.xaxis.fixedrange,
        },
        yaxis: {
          gridcolor: gridColor,
          zeroline: false,
          side: "right",
          showline: false,
          ticks: "outside",
          tickcolor: lineColor,
          automargin: true,
          fixedrange: layout.yaxis?.fixedrange === undefined ? false : layout.yaxis.fixedrange,
        },
        margin: { l: 20, r: 60, t: 20, b: 40 },
        plot_bgcolor: "transparent",
        paper_bgcolor: "transparent",
        hovermode: "x unified",
        // --- FIX 1: Set dragmode back to 'pan' (or 'false') as zoom gestures handle zoom ---
        dragmode: "pan", // 'pan' allows dragging to move around, 'false' disables dragging
        legend: {
          orientation: "h",
          yanchor: "bottom",
          y: -0.3,
          xanchor: "center",
          x: 0.5,
          font: { size: 10, color: textColor }
        },
      }
    },
    ...layout
  }

  return (
    <div className="w-full h-full min-h-[350px]">
      <Plot
        data={data}
        layout={baseLayout as any}
        config={{ 
          displayModeBar: false, 
          responsive: true, 
          doubleClick: 'reset', // Keep double-click to reset zoom
          // --- FIX 2: Enable scrollZoom in the config object ---
          scrollZoom: true, // Enables mouse wheel and trackpad pinch zoom
          ...config 
        }}
        useResizeHandler={true}
        style={{ width: "100%", height: "100%" }}
      />
    </div>
  )
}