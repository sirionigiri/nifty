"use client"

import { CalendarTable } from "../tables/CalendarTable"
import { RankingsTable } from "../tables/RankingsTable"
import { CalendarHeatmap } from "../charts/CalendarHeatmap"


export function CalendarView() {
  return (
    <div className="space-y-16 pb-20">

        <CalendarHeatmap />
      
        {/* 1. The Color-Coded Returns Table (replaces the Plotly heatmap) */}
        <CalendarTable />
        
        {/* 2. The Rankings Table */}
        <RankingsTable />

      
      
    </div>
  )
}