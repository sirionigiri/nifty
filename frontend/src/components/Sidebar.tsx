"use client"

import { useQuery } from "@tanstack/react-query"
import { useStore, CategoryMap } from "@/store/useStore"
import { Checkbox } from "@/components/ui/checkbox"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion"
import { Skeleton } from "@/components/ui/skeleton"
import { Switch } from "@/components/ui/switch"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Download, FileSpreadsheet } from "lucide-react"

const fetchConfig = async (): Promise<{ indices: string[], categories: CategoryMap }> => {
  const res = await fetch("http://localhost:8000/api/config");
  if (!res.ok) throw new Error("Failed to fetch config");
  return res.json();
}

export function Sidebar() {
  const { selectedIndices, benchmark, toggleIndex, setBenchmark, selectAll, deselectAll } = useStore();

  const { data: config, isLoading, error } = useQuery({
    queryKey: ["appConfig"],
    queryFn: fetchConfig,
  });

  if (isLoading) return <aside className="w-72 border-r bg-white dark:bg-[#09090b] h-screen p-6"><Skeleton className="w-full h-full" /></aside>;
  if (error || !config) return <aside className="w-72 p-6 text-red-500 font-bold text-xs">OFFLINE: BACKEND NOT FOUND</aside>;
  
  const allIndices = config.indices;
  const isAllSelected = selectedIndices.length === allIndices.length;

  return (
    <aside className="w-72 flex flex-col border-r bg-white dark:bg-[#09090b] h-screen sticky top-0 overflow-hidden shadow-xl z-20">
      
      <div className="p-6 border-b shrink-0 h-16 flex items-center justify-between bg-white dark:bg-[#09090b]">
        <h1 className="text-sm font-black tracking-tighter text-blue-600 dark:text-blue-400">NSE SCREENER</h1>
        <div className="h-2 w-2 rounded-full bg-green-500 animate-pulse" title="Live Connection" />
      </div>

      <ScrollArea className="flex-1 overflow-y-auto px-4 py-4 sidebar-scroll bg-slate-50/30 dark:bg-transparent">
        <div className="space-y-8">
          <div className="px-2 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-[10px] font-black uppercase tracking-[0.15em] text-slate-400">Select Indices</h3>
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-bold text-slate-400">ALL</span>
                <Switch className="scale-75 data-[state=checked]:bg-blue-600" checked={isAllSelected} onCheckedChange={(checked) => checked ? selectAll(allIndices) : deselectAll()} />
              </div>
            </div>

            <Accordion type="multiple" defaultValue={Object.keys(config.categories)} className="w-full space-y-1">
              {Object.entries(config.categories).map(([cat, indices]) => (
                <AccordionItem key={cat} value={cat} className="border-none">
                  <AccordionTrigger className="hover:no-underline py-2 text-[11px] font-bold text-slate-600 dark:text-slate-400 uppercase hover:bg-slate-100 dark:hover:bg-slate-900 px-2 rounded-md transition-all">
                    {cat}
                  </AccordionTrigger>
                  <AccordionContent className="pt-2 pb-2 pl-2 space-y-1">
                    {indices.filter(idx => allIndices.includes(idx)).map(idx => (
                      <div key={idx} className="flex items-center space-x-3 p-1 rounded-md hover:bg-slate-50 dark:hover:bg-slate-900 group transition-colors">
                        <Checkbox id={idx} checked={selectedIndices.includes(idx)} onCheckedChange={() => toggleIndex(idx)} className="border-slate-300 dark:border-slate-700 data-[state=checked]:bg-blue-600" />
                        <label htmlFor={idx} className="text-xs font-medium cursor-pointer text-slate-600 dark:text-slate-300 group-hover:text-blue-600">{idx}</label>
                      </div>
                    ))}
                  </AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
          </div>

          <div className="px-2 pt-4 border-t border-slate-100 dark:border-slate-900 space-y-3">
            <h3 className="text-[10px] font-black uppercase tracking-[0.15em] text-slate-400">Benchmark Index</h3>
            <Select value={benchmark} onValueChange={setBenchmark}>
              <SelectTrigger className="w-full h-9 text-xs font-bold border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950">
                <SelectValue placeholder="Select Benchmark" />
              </SelectTrigger>
              <SelectContent className="dark:bg-slate-950 dark:border-slate-800">
                {allIndices.map(idx => <SelectItem key={idx} value={idx} className="text-xs font-medium">{idx}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        </div>
      </ScrollArea>

      <div className="p-4 border-t bg-white dark:bg-[#09090b] shrink-0 space-y-2">
        <Button className="w-full bg-blue-600 hover:bg-blue-700 text-white text-xs font-black uppercase tracking-widest h-10 shadow-sm transition-all active:scale-95">
          Apply Analytics
        </Button>
        <div className="grid grid-cols-2 gap-2">
          <Button variant="outline" className="w-full text-[10px] font-bold uppercase tracking-wider h-8 text-slate-500 border-slate-200 dark:border-slate-800 hover:text-blue-600">
            <FileSpreadsheet className="w-3 h-3 mr-1" /> Report
          </Button>
          <Button variant="outline" className="w-full text-[10px] font-bold uppercase tracking-wider h-8 text-slate-500 border-slate-200 dark:border-slate-800 hover:text-blue-600">
            <Download className="w-3 h-3 mr-1" /> Config
          </Button>
        </div>
      </div>
    </aside>
  );
}