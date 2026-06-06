"use client"

import React, { useState, useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "@/components/ui/dialog"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { FileSpreadsheet, Search, Download, Loader2, Calendar as CalendarIcon, CheckSquare, Square } from "lucide-react"
import { useStore } from "@/store/useStore"
import { API_BASE_URL } from "@/lib/utils"
import { Calendar } from "@/components/ui/calendar"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { format } from "date-fns"

const PRESET_REPORT_PERIODS = ["MTD", "YTD", "1 Yr", "3 Yr", "5 Yr", "10 Yr", "Rolling 3-Yr Avg"];

interface AppConfig {
  indices: string[];
  categories: Record<string, string[]>;
}

export function ReportModal() {
  const { referenceDate } = useStore();
  
  // --- INDEPENDENT MODAL STATE ---
  const [activeTab, setActiveTab] = useState("sector"); // Track which tab is open
  const [isDownloading, setIsDownloading] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [repDate, setRepDate] = useState(referenceDate);
  const [repBench, setRepBench] = useState("NIFTY 500");
  const [repPeriods, setRepPeriods] = useState<string[]>([...PRESET_REPORT_PERIODS]);
  
  // --- 💡 SEPARATE PRE-CHECKED LISTS ---
  const [sectorIndices, setSectorIndices] = useState<string[]>([
    "NIFTY 500", "NIFTY ENERGY", "NIFTY AUTO", "NIFTY BANK", "NIFTY IT", "NIFTY METAL", "NIFTY CEMENT", 'NIFTY CHEMICALS', 'NIFTY FINSEREXBNK', 'NIFTY HEALTHCARE', 'NIFTY METAL', 'NIFTY REALTY', 'NIFTY CAPITAL MKT', 'NIFTY CPSE', 'NIFTY INDIA MFG', 'NIFTY IND TOURISM', 'NIFTY INFRA', 'NIFTY IPO', 'NIFTY MNC'
  ]);
  const [factorIndices, setFactorIndices] = useState<string[]>([
    "NIFTY500 QLTY50",
    "NIFTY500 VALUE 50",
    "NIFTY MULTI MQ 50",
    "NIFTY500 MQVLV50",
    "NIFTY200MOMENTM30",
    "NIFTY200 QUALITY 30",
    "NIFTY200 VALUE 30",
    "NIFTY M150 QLTY50",
    "NIFTYM150MOMNTM50",
    "NIFTYSML250MQ 100",
    "NIFTY SML250 Q50",
    "NIFTY500MOMENTM50"
  ]);

  const { data: config } = useQuery<AppConfig>({
    queryKey: ["appConfig"],
    queryFn: async () => {
      const res = await fetch(`${API_BASE_URL}/api/config`);
      return res.json();
    }
  });

  const categorized = useMemo(() => {
    if (!config || !config.categories) return { sectoral: [], factor: [] };
    const s = searchTerm.toLowerCase();

    const sectoralKeys = ["Broad Market", "Sectoral", "Thematic"];
    const sectoralRaw = sectoralKeys.flatMap(key => config.categories[key] || []);

    const factorKeys = Object.keys(config.categories).filter(k => k.startsWith("Factor") || k === "Strategy");
    const factorRaw = factorKeys.flatMap(key => config.categories[key] || []);

    return {
      sectoral: Array.from(new Set(sectoralRaw)).filter(i => i.toLowerCase().includes(s)),
      factor: Array.from(new Set(factorRaw)).filter(i => i.toLowerCase().includes(s))
    };
  }, [config, searchTerm]);

  // Toggle Logic per Tab
  const toggleSectorIdx = (idx: string) => setSectorIndices(p => p.includes(idx) ? p.filter(i => i !== idx) : [...p, idx]);
  const toggleFactorIdx = (idx: string) => setFactorIndices(p => p.includes(idx) ? p.filter(i => i !== idx) : [...p, idx]);
  
  const togglePeriod = (p: string) => setRepPeriods(prev => prev.includes(p) ? prev.filter(x => x !== p) : [...prev, p]);

  const handleBulkToggle = (indices: string[], action: 'all' | 'none', tab: 'sector' | 'factor') => {
    const setter = tab === 'sector' ? setSectorIndices : setFactorIndices;
    if (action === 'all') {
      setter(prev => Array.from(new Set([...prev, ...indices])));
    } else {
      setter(prev => prev.filter(idx => !indices.includes(idx)));
    }
  };

  const handleDownload = async () => {
    setIsDownloading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/generate-report`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
          benchmark: repBench, 
          // CONCAT BOTH LISTS FOR BACKEND
          indices: [...sectorIndices, ...factorIndices], 
          reference_date: repDate, 
          metric: "full", 
          periods: repPeriods 
        })
      });
      const blob = await response.blob();
      const a = document.createElement('a');
      a.href = window.URL.createObjectURL(blob);
      a.download = `NSE_Index_Report_${repDate}.xlsx`;
      a.click();
    } finally { setIsDownloading(false); }
  };

  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="outline" className="w-full text-[10px] font-bold uppercase tracking-wider h-9 rounded-lg text-slate-500 border-slate-200 dark:border-slate-800 hover:text-blue-600 transition-all shadow-sm">
           <FileSpreadsheet className="w-3 h-3 mr-1 text-emerald-500" /> Report
        </Button>
      </DialogTrigger>
      
      <DialogContent className="!max-w-6xl h-[90vh] flex flex-col p-0 rounded-[32px] overflow-hidden border-none shadow-2xl bg-white dark:bg-[#09090b]">
        
        <DialogHeader className="p-8 bg-slate-50 dark:bg-slate-950 border-b shrink-0 text-left">
          <DialogTitle className="text-4xl font-black tracking-tighter text-slate-900 dark:text-white ">Export an Excel Report</DialogTitle>
          <p className="text-xs text-slate-500">Configure Excel export</p>
        </DialogHeader>

        <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1 flex flex-col min-h-0 overflow-hidden">
          
          <div className="px-8 py-5 flex items-center justify-between border-b bg-white dark:bg-black/20 shrink-0">
            <TabsList className="segmented-tabs-list !mb-0">
              <TabsTrigger value="sector" className="segmented-tab-trigger px-8 font-black uppercase">1. Sector & Thematic</TabsTrigger>
              <TabsTrigger value="factor" className="segmented-tab-trigger px-8 font-black uppercase">2. Factor Dashboard</TabsTrigger>
            </TabsList>
            
            <div className="relative w-96">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
              <Input 
                placeholder="Search indices for current tab..." 
                className="pl-10 h-11 text-xs font-bold rounded-full border-slate-200 dark:border-slate-800 bg-slate-50/50" 
                value={searchTerm} 
                onChange={(e) => setSearchTerm(e.target.value)} 
              />
            </div>
          </div>

          <div className="flex-1 overflow-y-auto bg-slate-50/30 dark:bg-transparent">
            <div className="p-10 space-y-12">
              
              <div className="grid grid-cols-2 gap-12">
                <div className="space-y-3">
                  <label className="text-[10px] font-black uppercase text-slate-400 tracking-widest ml-1">Report Benchmark</label>
                  <Select value={repBench} onValueChange={setRepBench}>
                    <SelectTrigger className="rounded-2xl h-14 font-bold text-sm border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 shadow-sm"><SelectValue /></SelectTrigger>
                    <SelectContent className="max-h-80">{config?.indices.map((idx) => <SelectItem key={idx} value={idx} className="text-xs font-bold">{idx}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                <div className="space-y-3">
                    <label className="text-[10px] font-black uppercase text-slate-400 tracking-widest ml-1">Reporting Date</label>
                    <Popover>
                        <PopoverTrigger asChild>
                            <Button variant="outline" className="w-full h-14 border-blue-100 dark:border-blue-900 bg-blue-50/50 dark:bg-blue-900/10 rounded-2xl flex justify-between px-6 font-mono text-sm font-black text-blue-600 shadow-inner">
                                {format(new Date(repDate), "PPP")}
                                <CalendarIcon className="h-4 w-4 opacity-50" />
                            </Button>
                        </PopoverTrigger>
                        <PopoverContent className="w-auto p-0 rounded-3xl overflow-hidden shadow-2xl border-none" align="end">
                            <Calendar mode="single" captionLayout="dropdown" startMonth={new Date(2005, 0)} endMonth={new Date()} disabled={{ after: new Date() }} selected={new Date(repDate)} onSelect={(date) => date && setRepDate(format(date, "yyyy-MM-dd"))} />
                        </PopoverContent>
                    </Popover>
                </div>
              </div>

              <div className="space-y-6">
                <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 pb-4">
                    <h3 className="text-xs font-black uppercase text-slate-900 dark:text-slate-100 tracking-widest flex items-center gap-3">
                        <div className={`w-1.5 h-5 rounded-full ${activeTab === "sector" ? "bg-blue-600" : "bg-purple-600"}`} />
                        {activeTab === "sector" ? "Sector Shortlist" : "Factor Shortlist"} 
                        {/* 🚀 TAB SPECIFIC COUNT */}
                        ({activeTab === "sector" ? sectorIndices.length : factorIndices.length})
                    </h3>
                    
                    <div className="flex items-center gap-2">
                        {/* BULK TOGGLES SYNCED TO ACTIVE TAB */}
                        <Button 
                            variant="ghost" 
                            size="sm" 
                            onClick={() => handleBulkToggle(activeTab === 'sector' ? categorized.sectoral : categorized.factor, 'all', activeTab as 'sector' | 'factor')} 
                            className="text-[10px] font-black text-blue-600 hover:text-blue-700 uppercase h-7 px-2"
                        >
                            <CheckSquare className="w-3 h-3 mr-1" /> Select All
                        </Button>
                        <Button 
                            variant="ghost" 
                            size="sm" 
                            onClick={() => handleBulkToggle(activeTab === 'sector' ? categorized.sectoral : categorized.factor, 'none', activeTab as 'sector' | 'factor')} 
                            className="text-[10px] font-black text-slate-400 hover:text-red-500 uppercase h-7 px-2"
                        >
                            <Square className="w-3 h-3 mr-1" /> Clear
                        </Button>
                    </div>
                </div>

                <TabsContent value="sector" className="m-0 outline-none">
                    <div className="grid grid-cols-4 gap-3 bg-white dark:bg-slate-900/40 p-6 rounded-[32px] border border-slate-200 dark:border-slate-800 shadow-sm max-h-[450px] overflow-y-auto sidebar-scroll">
                    {categorized.sectoral.map((idx) => (
                        <div key={idx} className="flex items-start space-x-3 p-2 rounded-xl hover:bg-slate-50 dark:hover:bg-slate-800 transition-all group">
                            <Checkbox id={`rep-s-${idx}`} className="mt-0.5" checked={sectorIndices.includes(idx)} onCheckedChange={() => toggleSectorIdx(idx)} />
                            <label htmlFor={`rep-s-${idx}`} className="text-[10px] font-bold uppercase tracking-tight cursor-pointer leading-tight flex-1 text-slate-500 group-hover:text-blue-600 transition-colors">{idx}</label>
                        </div>
                    ))}
                    </div>
                </TabsContent>

                <TabsContent value="factor" className="m-0 outline-none">
                    <div className="grid grid-cols-4 gap-3 bg-white dark:bg-slate-900/40 p-6 rounded-[32px] border border-slate-200 dark:border-slate-800 shadow-sm max-h-[450px] overflow-y-auto sidebar-scroll">
                    {categorized.factor.map((idx) => (
                        <div key={idx} className="flex items-start space-x-3 p-2 rounded-xl hover:bg-slate-50 dark:hover:bg-slate-800 transition-all group">
                            <Checkbox id={`rep-f-${idx}`} className="mt-0.5" checked={factorIndices.includes(idx)} onCheckedChange={() => toggleFactorIdx(idx)} />
                            <label htmlFor={`rep-f-${idx}`} className="text-[10px] font-bold uppercase tracking-tight cursor-pointer leading-tight flex-1 text-slate-500 group-hover:text-purple-600 transition-colors">{idx}</label>
                        </div>
                    ))}
                    </div>
                </TabsContent>
              </div>

              {/* PERIOD SELECTION */}
              <div className="space-y-6 pt-4">
                <h3 className="text-xs font-black uppercase text-slate-900 dark:text-slate-100 tracking-widest flex items-center gap-3">
                    <div className="w-1.5 h-5 bg-emerald-500 rounded-full" />
                    Include Time Periods
                </h3>
                <div className="flex flex-wrap gap-4">
                    {PRESET_REPORT_PERIODS.map(p => (
                        <div key={p} className="flex items-center space-x-3 bg-white dark:bg-slate-900 px-5 py-3 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm hover:border-emerald-500/50 transition-all group">
                            <Checkbox id={`p-rep-${p}`} checked={repPeriods.includes(p)} onCheckedChange={() => togglePeriod(p)} />
                            <label htmlFor={`p-rep-${p}`} className="text-[11px] font-black uppercase cursor-pointer text-slate-500 group-hover:text-emerald-600 transition-colors">{p}</label>
                        </div>
                    ))}
                </div>
              </div>
            </div>
          </div>
        </Tabs>

        <DialogFooter className="p-8 bg-slate-50 dark:bg-black/40 border-t shrink-0">
          <Button 
            disabled={isDownloading || (sectorIndices.length === 0 && factorIndices.length === 0)} 
            onClick={handleDownload}
            className="w-full h-12 rounded-[24px] bg-blue-600 hover:bg-blue-700 text-white font-black text-sm shadow-2xl shadow-blue-500/40 active:scale-[0.97] transition-all"
          >
            {isDownloading ? <Loader2 className="animate-spin mr-4 h-6 w-6" /> : <Download className="mr-4 h-6 w-6" />}
            Export to Excel
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}