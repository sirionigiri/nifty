"use client"
import { useQuery } from "@tanstack/react-query"
import { useStore } from "@/store/useStore"
import { BaseChart } from "@/components/charts/BaseChart"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { API_BASE_URL } from "@/lib/utils"


export function NavChartReal() {
  const { selectedIndices, benchmark, periods } = useStore();

  const { data, isLoading } = useQuery({
    queryKey: ["navData", selectedIndices, periods[0]],
    queryFn: async () => {
      const res = await fetch(`${API_BASE_URL}api/nav-data`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ metric: "nav", periods: [periods[0]], indices: selectedIndices, benchmark })
      });
      return res.json();
    },
  });

  const { data: ddData } = useQuery({
    queryKey: ["ddData", selectedIndices, periods[0]],
    queryFn: async () => {
      const res = await fetch(`${API_BASE_URL}/api/nav-data`, { // We will add a flag for DD
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ metric: "drawdown", periods: [periods[0]], indices: selectedIndices, benchmark })
      });
      return res.json();
    },
  });

  const plotDdData = ddData?.map((trace: any) => ({
    ...trace,
    type: 'scatter',
    mode: 'lines',
    fill: 'tozeroy', // Drawdown is always filled to zero
    line: { width: trace.name === benchmark ? 2 : 1 },
  }));

  const plotData = data?.map((trace: any) => ({
    ...trace,
    type: 'scatter',
    mode: 'lines',
    fill: trace.name === benchmark ? 'tozeroy' : 'none',
    fillcolor: 'rgba(59, 130, 246, 0.05)',
    line: { width: trace.name === benchmark ? 2.5 : 1.5, shape: 'spline', smoothing: 1.3, color: trace.name === benchmark ? '#2563eb' : undefined },
  }));

  return (
    <div className="bg-white dark:bg-[#09090b] border rounded-3xl p-8 shadow-sm">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-10">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Price Chart</h2>
          <p className="text-xs text-slate-400 font-medium uppercase tracking-widest mt-1">Rebased Index Performance</p>
        </div>

        {/* COMPACT PERIOD SWITCHER - Matches Image 1 */}
        <TabsList className="period-tabs-list">
          {["1M", "6M", "1Yr", "3Yr", "5Yr", "Max"].map(p => (
            <TabsTrigger key={p} value={p} className="period-tab-trigger">{p}</TabsTrigger>
          ))}
        </TabsList>
      </div>

      <div className="h-[450px]">
        <BaseChart 
          data={plotData} 
          layout={{ 
            hovermode: 'x unified',
            xaxis: { showgrid: false, zeroline: false },
            yaxis: { side: "right", showline: false }
          }} 
        />
      </div>
    </div>
  );
}