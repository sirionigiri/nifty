"use client"

import React, { useState, useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "@/components/ui/dialog"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { FileSpreadsheet, Search, Download, Loader2 } from "lucide-react"
import { useStore } from "@/store/useStore"
import { API_BASE_URL } from "@/lib/utils"

// 1. DEFINE THE INTERFACE SO TYPESCRIPT STOPS COMPLAINING
interface AppConfig {
  indices: string[];
  categories: Record<string, string[]>;
}

const PRESET_REPORT_PERIODS = ["MTD", "YTD", "1 Yr", "3 Yr", "5 Yr", "10 Yr", "Rolling 3-Yr Avg"];

export function ReportModal() {
  const { referenceDate } = useStore();
  const [isDownloading, setIsDownloading] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");

  const [repIndices, setRepIndices] = useState<string[]>(["NIFTY 500", "NIFTY ENERGY", "NIFTY AUTO", "NIFTY BANK"]);
  const [repBench, setRepBench] = useState("NIFTY 500");
  const [repPeriods, setRepPeriods] = useState(["MTD", "YTD", "1 Yr", "3 Yr", "5 Yr", "10 Yr", "Rolling 3-Yr Avg"]);

  // 2. APPLY THE INTERFACE TO THE QUERY
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
    
    // Explicitly type these as string arrays
    const sectoralRaw: string[] = [
      ...(config.categories["Sectoral"] || []),
      ...(config.categories["Thematic"] || []),
      ...(config.categories["Broad Market"] || [])
    ];
    const factorRaw: string[] = config.categories["Strategy"] || [];

    return {
      sectoral: Array.from(new Set(sectoralRaw)).filter(i => i.toLowerCase().includes(s)),
      factor: Array.from(new Set(factorRaw)).filter(i => i.toLowerCase().includes(s))
    };
  }, [config, searchTerm]);

  const toggleIdx = (idx: string) => setRepIndices(p => p.includes(idx) ? p.filter(i => i !== idx) : [...p, idx]);
  const togglePeriod = (p: string) => setRepPeriods(prev => prev.includes(p) ? prev.filter(x => x !== p) : [...prev, p]);

  const handleBulkToggle = (indices: string[], action: 'all' | 'none') => {
    if (action === 'all') {
      setRepIndices(prev => Array.from(new Set([...prev, ...indices])));
    } else {
      setRepIndices(prev => prev.filter(idx => !indices.includes(idx)));
    }
  };

  const handleDownload = async () => {
    setIsDownloading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/generate-report`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ benchmark: repBench, indices: repIndices, reference_date: referenceDate, metric: "full", periods: repPeriods })
      });
      const blob = await response.blob();
      const a = document.createElement('a');
      a.href = window.URL.createObjectURL(blob);
      a.download = `NSE_Report_${referenceDate}.xlsx`;
      a.click();
    } finally { setIsDownloading(false); }
  };

  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="outline" className="w-full text-[10px] font-bold uppercase tracking-wider h-9 rounded-lg text-slate-500 border-slate-200 dark:border-slate-800 hover:text-blue-600 transition-all">
           <FileSpreadsheet className="w-3 h-3 mr-1 text-emerald-500" /> Report
        </Button>
      </DialogTrigger>
      
      <DialogContent className="max-w-6xl h-[90vh] flex flex-col p-0 rounded-[32px] overflow-hidden border-none shadow-2xl bg-white dark:bg-[#09090b]">
        <DialogHeader className="p-8 bg-slate-50 dark:bg-slate-950 border-b shrink-0">
          <DialogTitle className="text-3xl font-black tracking-tight text-slate-900 dark:text-white uppercase italic">Report Builder</DialogTitle>
          <p className="text-xs text-slate-500 font-bold uppercase tracking-widest mt-1 text-center md:text-left">Configure independent Excel dashboard export</p>
        </DialogHeader>

        <Tabs defaultValue="sector" className="flex-1 flex flex-col min-h-0 overflow-hidden">
          <div className="px-8 py-4 flex flex-col md:flex-row justify-between items-center border-b bg-white dark:bg-black/20 shrink-0 gap-4">
            <TabsList className="segmented-tabs-list !mb-0 shrink-0">
              <TabsTrigger value="sector" className="segmented-tab-trigger px-6">1. Sector & Thematic</TabsTrigger>
              <TabsTrigger value="factor" className="segmented-tab-trigger px-6">2. Factor Dashboard</TabsTrigger>
            </TabsList>
            
            <div className="relative w-full md:w-80">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-400" />
              <Input 
                placeholder="Search indices for report..." 
                className="pl-10 h-10 text-[11px] font-bold rounded-full border-slate-200 dark:border-slate-800 bg-slate-50/50" 
                value={searchTerm} 
                onChange={(e) => setSearchTerm(e.target.value)} 
              />
            </div>
          </div>

          <div className="flex-1 overflow-y-auto bg-slate-50/30 dark:bg-transparent">
            <div className="p-8 space-y-12">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                <div className="space-y-3">
                  <label className="text-[10px] font-black uppercase text-slate-400 tracking-widest ml-1">Report Benchmark</label>
                  <Select value={repBench} onValueChange={setRepBench}>
                    <SelectTrigger className="rounded-xl h-14 font-bold text-xs border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 shadow-sm"><SelectValue /></SelectTrigger>
                    <SelectContent className="max-h-80">{config?.indices.map((idx) => <SelectItem key={idx} value={idx} className="text-xs font-bold">{idx}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                <div className="space-y-3">
                    <label className="text-[10px] font-black uppercase text-slate-400 tracking-widest ml-1">Reporting Date</label>
                    <div className="h-14 border rounded-xl flex items-center px-6 font-mono text-sm font-black text-blue-600 bg-blue-50/50 dark:bg-blue-900/10 border-blue-100 dark:border-blue-900 shadow-inner">
                        {referenceDate}
                    </div>
                </div>
              </div>

              <div className="space-y-4">
                <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 pb-3">
                    <h3 className="text-xs font-black uppercase text-slate-900 dark:text-slate-100 tracking-widest flex items-center gap-2">
                        <div className="w-1.5 h-4 bg-blue-600 rounded-full" />
                        Shortlist Indices ({repIndices.length})
                    </h3>
                    
                    <div className="flex items-center gap-2">
                      <TabsContent value="sector" className="m-0 flex gap-2">
                        <button type="button" onClick={() => handleBulkToggle(categorized.sectoral, 'all')} className="text-[9px] font-black bg-blue-50 text-blue-600 px-2 py-1 rounded-md hover:bg-blue-600 hover:text-white transition-all uppercase">Select All</button>
                        <button type="button" onClick={() => handleBulkToggle(categorized.sectoral, 'none')} className="text-[9px] font-black bg-slate-100 text-slate-500 px-2 py-1 rounded-md hover:bg-red-500 hover:text-white transition-all uppercase">Clear</button>
                      </TabsContent>
                      <TabsContent value="factor" className="m-0 flex gap-2">
                        <button type="button" onClick={() => handleBulkToggle(categorized.factor, 'all')} className="text-[9px] font-black bg-blue-50 text-blue-600 px-2 py-1 rounded-md hover:bg-blue-600 hover:text-white transition-all uppercase">Select All</button>
                        <button type="button" onClick={() => handleBulkToggle(categorized.factor, 'none')} className="text-[9px] font-black bg-slate-100 text-slate-500 px-2 py-1 rounded-md hover:bg-red-500 hover:text-white transition-all uppercase">Clear</button>
                      </TabsContent>
                    </div>
                </div>

                <TabsContent value="sector" className="m-0 outline-none">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 bg-white dark:bg-slate-900/40 p-6 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-sm max-h-[400px] overflow-y-auto sidebar-scroll">
                    {categorized.sectoral.map((idx) => (
                        <div key={idx} className="flex items-start space-x-3 p-2 rounded-xl hover:bg-slate-50 dark:hover:bg-slate-800 transition-all group">
                            <Checkbox id={`rep-s-${idx}`} className="mt-0.5" checked={repIndices.includes(idx)} onCheckedChange={() => toggleIdx(idx)} />
                            <label htmlFor={`rep-s-${idx}`} className="text-[10px] font-bold uppercase tracking-tight cursor-pointer leading-tight flex-1 text-slate-500 group-hover:text-blue-600 transition-colors">{idx}</label>
                        </div>
                    ))}
                    </div>
                </TabsContent>

                <TabsContent value="factor" className="m-0 outline-none">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 bg-white dark:bg-slate-900/40 p-6 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-sm max-h-[400px] overflow-y-auto sidebar-scroll">
                    {categorized.factor.map((idx) => (
                        <div key={idx} className="flex items-start space-x-3 p-2 rounded-xl hover:bg-slate-50 dark:hover:bg-slate-800 transition-all group">
                            <Checkbox id={`rep-f-${idx}`} className="mt-0.5" checked={repIndices.includes(idx)} onCheckedChange={() => toggleIdx(idx)} />
                            <label htmlFor={`rep-f-${idx}`} className="text-[10px] font-bold uppercase tracking-tight cursor-pointer leading-tight flex-1 text-slate-500 group-hover:text-blue-600 transition-colors">{idx}</label>
                        </div>
                    ))}
                    </div>
                </TabsContent>
              </div>

              <div className="space-y-6 pt-4">
                <h3 className="text-xs font-black uppercase text-slate-900 dark:text-slate-100 tracking-widest flex items-center gap-2">
                    <div className="w-1.5 h-4 bg-emerald-500 rounded-full" />
                    Include Time Periods
                </h3>
                <div className="flex flex-wrap gap-3">
                    {PRESET_REPORT_PERIODS.map(p => (
                        <div key={p} className="flex items-center space-x-3 bg-white dark:bg-slate-900 px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm hover:border-emerald-500/50 transition-all group">
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
            disabled={isDownloading || repIndices.length === 0} 
            onClick={handleDownload}
            className="w-full h-16 rounded-[20px] bg-blue-600 hover:bg-blue-700 text-white font-black uppercase tracking-[0.2em] text-sm shadow-xl shadow-blue-500/30 active:scale-[0.98] transition-all"
          >
            {isDownloading ? <Loader2 className="animate-spin mr-3 h-6 w-6" /> : <Download className="mr-3 h-6 w-6" />}
            Save & Build Financial Dashboard
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}