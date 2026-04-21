"use client"

import { Suspense } from "react"
import { useSearchParams, useRouter, usePathname } from "next/navigation"
import { motion, AnimatePresence } from "framer-motion"

import { Sidebar } from "@/components/Sidebar"
import { ThemeToggle } from "@/components/ThemeToggle"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { LoadingSpinner } from "@/components/ui/LoadingSpinner"
import { SummaryCards } from "@/components/MetricCard"

// Views
import { PerformanceView } from "@/components/views/PerformanceView"
import { RiskMetricsView } from "@/components/views/RiskMetricsView"
import { RiskAdjustedView } from "@/components/views/RiskAdjustedView"
import { VsBenchmarkView } from "@/components/views/VsBenchmarkView"
import { CalendarView } from "@/components/views/CalendarView"
import { NavView } from "@/components/views/NavView"
import { RiskReturnChart } from "@/components/charts/RiskReturnChart"
import { ValuationView } from "@/components/views/ValuationView"

// Separate component for the tab content to keep the animation logic clean
const TabContentWrapper = ({ children, value, activeTab }: { children: React.ReactNode, value: string, activeTab: string }) => {
  return (
    <TabsContent value={value} className="m-0 focus-visible:outline-none">
      <AnimatePresence mode="wait">
        {activeTab === value && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
          >
            {children}
          </motion.div>
        )}
      </AnimatePresence>
    </TabsContent>
  );
};

function DashboardContent() {
  const searchParams = useSearchParams()
  const pathname = usePathname()
  const { replace } = useRouter()

  const activeTab = searchParams.get("tab") || "performance"

  const handleTabChange = (value: string) => {
    const params = new URLSearchParams(window.location.search)
    params.set("tab", value)
    // scroll: false prevents the jump to top
    replace(`${pathname}?${params.toString()}`, { scroll: false })
  }

  return (
    <div className="flex h-screen overflow-hidden bg-white dark:bg-[#020203]">
      <Sidebar />

      <div className="flex-1 flex flex-col h-screen overflow-hidden bg-slate-50/50 dark:bg-black/20">
        
        {/* Navbar */}
        <header className="h-16 border-b border-border flex items-center justify-between px-8 bg-white/80 dark:bg-[#09090b]/80 backdrop-blur z-10 shrink-0">
          <div className="flex items-center gap-4">
            <span className="text-[10px] bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 px-2 py-0.5 rounded border border-emerald-500/20 font-bold uppercase tracking-widest flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" /> Live
            </span>
            <p className="text-[11px] text-slate-500 font-bold uppercase tracking-widest hidden md:block">
              NSE Index Screener · Engine: Python 3.12
            </p>
          </div>
          <div className="flex items-center gap-4">
            <ThemeToggle />
            <div className="h-8 w-8 rounded-full bg-blue-600 flex items-center justify-center text-[10px] font-bold text-white shadow-md">
              US
            </div>
          </div>
        </header>

        <main 
          className="flex-1 overflow-y-scroll scroll-smooth" 
          style={{ scrollbarGutter: 'stable' }}
        >
          <div className="max-w-[1600px] mx-auto p-8 space-y-10">
            
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.5 }}>
              <SummaryCards />
            </motion.div>

            <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">
              <TabsList className="h-11 w-auto inline-flex items-center justify-start gap-1 bg-slate-100 dark:bg-slate-900 p-1 rounded-xl mb-8 border border-slate-200 dark:border-slate-800 overflow-x-auto hide-scrollbar">
                {[
                  { id: "performance", label: "Performance" },
                  { id: "risk", label: "Risk Metrics" },
                  { id: "risk-adjusted", label: "Risk-Adjusted" },
                  { id: "vs-bench", label: "Vs Benchmark" },
                  { id: "valuation", label: "Valuation" },
                  { id: "calendar", label: "Calendar" },
                  { id: "scatter", label: "Risk vs Return" },
                  { id: "nav", label: "NAV Chart" },
                ].map((tab) => (
                  <TabsTrigger
                    key={tab.id}
                    value={tab.id}
                    className="rounded-lg px-4 py-2 text-[11px] font-bold uppercase transition-all
                               data-[state=active]:bg-white dark:data-[state=active]:bg-slate-800 
                               data-[state=active]:text-blue-600 dark:data-[state=active]:text-blue-400
                               data-[state=active]:shadow-sm border border-transparent"
                  >
                    {tab.label}
                  </TabsTrigger>
                ))}
              </TabsList>

              {/* 
                  FIX: We use TabsContent for each view. 
                  This ensures views are kept in memory and not re-fetched every click.
              */}
              <div className="min-h-[800px]">
                <TabContentWrapper value="performance" activeTab={activeTab}><PerformanceView /></TabContentWrapper>
                <TabContentWrapper value="risk" activeTab={activeTab}><RiskMetricsView /></TabContentWrapper>
                <TabContentWrapper value="risk-adjusted" activeTab={activeTab}><RiskAdjustedView /></TabContentWrapper>
                <TabContentWrapper value="vs-bench" activeTab={activeTab}><VsBenchmarkView /></TabContentWrapper>
                <TabContentWrapper value="calendar" activeTab={activeTab}><CalendarView /></TabContentWrapper>
                <TabContentWrapper value="nav" activeTab={activeTab}><NavView /></TabContentWrapper>
                <TabContentWrapper value="valuation" activeTab={activeTab}><ValuationView /></TabContentWrapper>
                
                <TabsContent value="scatter" className="m-0 outline-none">
                  <TabContentWrapper value="scatter" activeTab={activeTab}>
                    <div className="bg-white dark:bg-[#09090b] border dark:border-slate-800 rounded-3xl p-8 shadow-sm">
                      <h2 className="text-xl font-bold tracking-tight mb-2 text-slate-900 dark:text-white">Risk vs Return</h2>
                      <p className="text-[10px] text-slate-400 font-black uppercase tracking-widest mb-10">Volatility vs CAGR</p>
                      <RiskReturnChart />
                    </div>
                  </TabContentWrapper>
                </TabsContent>
              </div>
            </Tabs>
          </div>
        </main>
      </div>
    </div>
  )
}

export default function Home() {
  return (
    <Suspense fallback={null}>
      <DashboardContent />
    </Suspense>
  )
}