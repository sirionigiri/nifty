"use client"

import dynamic from "next/dynamic"
import { useTheme } from "next-themes"
import { Skeleton } from "@/components/ui/skeleton"

const Plot = dynamic(() => import("react-plotly.js"), { 
  ssr: false,
  loading: () => <Skeleton className="w-full h-full min-h-[400px] rounded-xl" />
})

export function BaseChart({ data, layout = {}, config = {}, zoomEnabled = false }: any) {
  const { resolvedTheme } = useTheme()
  const isDark = resolvedTheme === "dark"

  const textColor = isDark ? '#94a3b8' : '#64748b';
  const gridColor = isDark ? '#1e293b' : '#f1f5f9';
  
  const baseLayout = {
    template: {
      layout: {
        font: { family: "Geist Sans, sans-serif", color: textColor, size: 10 },
        hoverlabel: {
          bgcolor: isDark ? "#0f172a" : "#ffffff",
          bordercolor: isDark ? "#334155" : "#e2e8f0",
          font: { color: isDark ? "#f1f5f9" : "#0f172a", size: 12, family: "Geist Mono" },
          align: "left",
        },
        xaxis: {
          showgrid: false,
          linecolor: isDark ? '#334155' : '#e2e8f0',
          zeroline: false,
          automargin: true,
          // LOCK AXIS IF ZOOM DISABLED
          fixedrange: !zoomEnabled,
        },
        yaxis: {
          gridcolor: gridColor,
          zeroline: false,
          side: "right",
          showline: false,
          automargin: true,
          // LOCK AXIS IF ZOOM DISABLED
          fixedrange: !zoomEnabled,
        },
        margin: { l: 20, r: 50, t: 20, b: 40 },
        plot_bgcolor: "transparent",
        paper_bgcolor: "transparent",
        hovermode: "x unified",
        dragmode: zoomEnabled ? "pan" : false, // Disable dragging if not enabled
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
          doubleClick: zoomEnabled ? 'reset' : false,
          scrollZoom: zoomEnabled, // Pinch/Wheel zoom only if enabled
          ...config 
        }}
        useResizeHandler={true}
        style={{ width: "100%", height: "100%" }}
      />
    </div>
  )
}