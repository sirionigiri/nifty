"use client"

import { useQuery } from "@tanstack/react-query"
import { useStore, CategoryMap } from "@/store/useStore"
import { Checkbox } from "@/components/ui/checkbox"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion"
import { Skeleton } from "@/components/ui/skeleton"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Input } from "@/components/ui/input"
import { Download, FileSpreadsheet, Search, Loader2 } from "lucide-react"
import { useState, useMemo } from "react"
import { exportToExcel, exportFullReport } from "@/lib/export"
import { LoadingSpinner } from "./ui/LoadingSpinner"

import { API_BASE_URL } from "@/lib/utils" // 1. Import it

const fetchConfig = async (): Promise<{ indices: string[], categories: CategoryMap }> => {
  // 2. Use backticks (`) and the variable
  const res = await fetch(`${API_BASE_URL}/api/config`); 
  if (!res.ok) throw new Error("Failed to fetch config");
  return res.json();
}

export function Sidebar() {
  const { selectedIndices, setSelectedIndices, benchmark, periods, toggleIndex, setBenchmark, deselectAll } = useStore();
  const [searchQuery, setSearchQuery] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);

  const { data: config, isLoading, error } = useQuery({
    queryKey: ["appConfig"],
    queryFn: fetchConfig,
  });

  // 1. Organize Categories & Dynamic "Others"
  const organizedCategories = useMemo(() => {
    if (!config) return null;
    const mappedSet = new Set(Object.values(config.categories).flat());
    const otherIndices = config.indices.filter(idx => !mappedSet.has(idx));

    const fullMap = { ...config.categories };
    if (otherIndices.length > 0) {
      fullMap["Others"] = otherIndices;
    }

    const filtered: CategoryMap = {};
    Object.entries(fullMap).forEach(([cat, list]) => {
      const matches = list.filter(idx => 
        idx.toLowerCase().includes(searchQuery.toLowerCase())
      );
      if (matches.length > 0) filtered[cat] = matches;
    });
    return filtered;
  }, [config, searchQuery]);

  // 2. Category Bulk Toggle Logic
  const handleBulkSet = (indicesInCat: string[], action: 'all' | 'none') => {
    if (action === 'all') {
      // Add all indices in this category to current selection (unique only)
      const newSelection = Array.from(new Set([...selectedIndices, ...indicesInCat]));
      setSelectedIndices(newSelection);
    } else {
      // Remove all indices of this category from current selection
      const newSelection = selectedIndices.filter(idx => !indicesInCat.includes(idx));
      setSelectedIndices(newSelection);
    }
  };

  const handleDownloadFullReport = async () => {
    setIsGenerating(true);
    try {
      const fetchMetric = async (m: string) => {
        const res = await fetch(`${API_BASE_URL}/api/metrics`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ metric: m, periods, indices: selectedIndices, benchmark })
        });
        return res.json();
      };
      const [cagr, vol, mdd] = await Promise.all([fetchMetric("cagr"), fetchMetric("vol"), fetchMetric("mdd")]);
      exportFullReport([{ name: "Annualised Returns", data: cagr }, { name: "Volatility", data: vol }, { name: "Max Drawdown", data: mdd }], "NSE_Full_Index_Report");
    } catch (err) { console.error(err); } finally { setIsGenerating(false); }
  };

  const defaultOpenCategories = useMemo(() => {
    if (!organizedCategories) return [];
    return Object.keys(organizedCategories).filter(
      (key) => key !== "Thematic Indices" && key !== "Others"
    );
  }, [organizedCategories]);


  if (isLoading) return <aside className="w-72 border-r bg-white dark:bg-[#09090b] h-screen flex items-center justify-center"><LoadingSpinner /></aside>;
  if (error || !config) return <aside className="w-72 p-6 text-red-500 font-bold text-xs uppercase">Connection Error</aside>;

  return (
    <aside className="w-72 flex flex-col border-r bg-white dark:bg-[#09090b] h-screen sticky top-0 overflow-hidden shadow-xl z-20">
      <div className="p-6 border-b shrink-0 bg-white dark:bg-[#09090b]">
        <h1 className="text-base font-black tracking-tighter text-blue-600 dark:text-blue-400">NSE SCREENER</h1>
      </div>

      <div className="px-4 py-3 border-b bg-slate-50/50 dark:bg-black/20 shrink-0">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
          <Input 
            placeholder="Search indices..." 
            className="pl-9 h-9 text-xs font-medium border-slate-200 dark:border-slate-800 rounded-xl bg-white dark:bg-slate-950 shadow-sm"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
      </div>

      <ScrollArea className="flex-1 overflow-y-auto px-4 py-4 sidebar-scroll">
        <div className="space-y-8">
          <div className="px-1 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-black uppercase tracking-widest text-slate-400">Categories</h3>
              <button onClick={deselectAll} className="text-[10px] font-bold text-blue-500 hover:text-blue-600 uppercase">Clear Global</button>
            </div>

            <Accordion type="multiple" defaultValue={defaultOpenCategories} key={defaultOpenCategories.join('-')}  className="w-full space-y-2">
              {organizedCategories && Object.entries(organizedCategories).map(([cat, indices]) => (
                <AccordionItem key={cat} value={cat} className="border border-slate-100 dark:border-slate-800 rounded-2xl px-3 bg-white dark:bg-slate-950/40 shadow-sm overflow-hidden">
                  <div className="flex items-center justify-between w-full">
                    <AccordionTrigger className="hover:no-underline py-4 text-[11px] font-black text-slate-600 dark:text-slate-300 uppercase flex-1 text-left tracking-tight">
                      {cat}
                    </AccordionTrigger>
                    
                    {/* CATEGORY LEVEL BULK TOGGLES */}
                    <div className="flex items-center gap-2 pr-2">
                        <button 
                            onClick={(e) => { e.preventDefault(); e.stopPropagation(); handleBulkSet(indices, 'all'); }}
                            className="text-[9px] font-black bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 px-1.5 py-0.5 rounded border border-blue-100 dark:border-blue-800 hover:bg-blue-600 hover:text-white transition-all"
                        >
                            ALL
                        </button>
                        <button 
                            onClick={(e) => { e.preventDefault(); e.stopPropagation(); handleBulkSet(indices, 'none'); }}
                            className="text-[9px] font-black bg-slate-50 dark:bg-slate-800 text-slate-500 px-1.5 py-0.5 rounded border border-slate-200 dark:border-slate-700 hover:bg-red-500 hover:text-white transition-all"
                        >
                            NONE
                        </button>
                    </div>
                  </div>

                  <AccordionContent className="pb-4 space-y-1">
                    {indices.map(idx => (
                      <div 
                        key={idx} 
                        // Changed 'items-center' to 'items-start' for better multiline alignment
                        className="flex items-start space-x-3 p-2 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-900 group transition-colors"
                      >
                        <Checkbox 
                          id={`check-${idx}`} 
                          checked={selectedIndices.includes(idx)} 
                          onCheckedChange={() => toggleIndex(idx)} 
                          // Added 'mt-0.5' to perfectly align checkbox with the first line of text
                          className="h-4 w-4 mt-0.5 border-slate-300 dark:border-slate-700 data-[state=checked]:bg-blue-600 border-2 shrink-0" 
                        />
                        <label 
                          htmlFor={`check-${idx}`} 
                          // Removed 'truncate', added 'leading-tight' and 'flex-1'
                          className="text-[11px] font-bold cursor-pointer text-slate-600 dark:text-slate-300 group-hover:text-blue-600 transition-colors uppercase tracking-tight flex-1 wrap-break-word leading-tight"
                        >
                          {idx}
                        </label>
                      </div>
                    ))}
                  </AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
          </div>

          <div className="px-1 pt-4 border-t border-slate-100 dark:border-slate-800 space-y-3 pb-12">
            <h3 className="text-xs font-black uppercase tracking-widest text-slate-400">Benchmark</h3>
            <Select value={benchmark} onValueChange={setBenchmark}>
              <SelectTrigger className="w-full h-10 text-xs font-bold border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 rounded-xl">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="dark:bg-slate-950">
                {config.indices.map(idx => <SelectItem key={idx} value={idx} className="text-xs font-bold">{idx}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        </div>
      </ScrollArea>

      <div className="p-4 border-t bg-white dark:bg-[#09090b] shrink-0 space-y-2">
        <Button className="w-full bg-blue-600 hover:bg-blue-700 text-white text-xs font-black uppercase tracking-widest h-11 rounded-xl shadow-md active:scale-95 transition-all">
          Apply Filters
        </Button>
        <div className="grid grid-cols-2 gap-2">
          <Button variant="outline" disabled={isGenerating} onClick={handleDownloadFullReport} className="w-full text-[10px] font-bold uppercase tracking-wider h-9 rounded-lg text-slate-500 border-slate-200 dark:border-slate-800 hover:bg-slate-50">
            {isGenerating ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <FileSpreadsheet className="w-3 h-3 mr-1 text-emerald-500" />} Report
          </Button>
          <Button variant="outline" onClick={() => exportToExcel([{Benchmark: benchmark, Indices: selectedIndices.join(', ')}], "Config")} className="w-full text-[10px] font-bold uppercase tracking-wider h-9 rounded-lg text-slate-500 border-slate-200 dark:border-slate-800 hover:bg-slate-50">
            <Download className="w-3 h-3 mr-1 text-blue-500" /> Config
          </Button>
        </div>
      </div>
    </aside>
  );
}