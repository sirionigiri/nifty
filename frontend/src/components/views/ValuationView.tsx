"use client"

import React, { useState, useEffect } from "react"
import { useQuery } from "@tanstack/react-query"
import { useStore } from "@/store/useStore"
import { ValuationChart } from "../charts/ValuationChart"
import { LoadingSpinner } from "../ui/LoadingSpinner"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { motion, AnimatePresence } from "framer-motion"
import { Check, ChevronsUpDown, Search } from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"

export function ValuationView() {
  const { selectedIndices, benchmark } = useStore();
  
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(benchmark);
  const [activeWindow, setActiveWindow] = useState("5 Yr");
  
  const navPeriods = ["Last Month", "YTD", "1 Yr", "3 Yr", "5 Yr", "10 Yr", "20 Yr"];

  // Sync activeIndex if user changes selection
  useEffect(() => {
    if (!selectedIndices.includes(activeIndex)) {
      setActiveIndex(selectedIndices[0] || benchmark);
    }
  }, [selectedIndices, benchmark]);

  const { data, isLoading } = useQuery({
    queryKey: ["valuation", activeIndex, activeWindow],
    queryFn: async () => {
      const res = await fetch("http://localhost:8000/api/valuation-data", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ benchmark: activeIndex, indices: [], metric: "", periods: [activeWindow] })
      });
      return res.json();
    },
    enabled: !!activeIndex
  });

  if (isLoading) return <LoadingSpinner />;

  return (
    <div className="space-y-10 pb-20">
      {/* HEADER CONTROLS */}
      <div className="flex flex-col gap-6 bg-white dark:bg-slate-900/40 p-6 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-sm">
        
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
          
          {/* SEARCHABLE DROPDOWN (COMBOBOX) */}
          <div className="space-y-2 w-full md:w-80">
            <h2 className="text-[10px] font-black uppercase tracking-widest text-slate-400 ml-1">Valuation Target</h2>
            <Popover open={open} onOpenChange={setOpen}>
              <PopoverTrigger asChild>
                <Button
                  variant="outline"
                  role="combobox"
                  aria-expanded={open}
                  className="w-full justify-between bg-white dark:bg-slate-950 border-slate-200 dark:border-slate-800 h-11 rounded-xl text-xs font-bold"
                >
                  {activeIndex ? activeIndex : "Select index..."}
                  <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-80 p-0 rounded-xl shadow-2xl border-slate-200 dark:border-slate-800">
                <Command className="dark:bg-slate-950">
                  <CommandInput placeholder="Search indices..." className="h-11 text-xs" />
                  <CommandList className="max-h-[300px] hide-scrollbar">
                    <CommandEmpty className="py-6 text-center text-xs text-slate-500 font-medium">No index found.</CommandEmpty>
                    <CommandGroup>
                      {selectedIndices.map((idx) => (
                        <CommandItem
                          key={idx}
                          value={idx}
                          onSelect={(currentValue) => {
                            setActiveIndex(currentValue);
                            setOpen(false);
                          }}
                          className="text-xs font-bold py-3 px-4 cursor-pointer hover:bg-blue-50 dark:hover:bg-blue-900/20"
                        >
                          <Check
                            className={cn(
                              "mr-2 h-4 w-4 text-blue-600",
                              activeIndex === idx ? "opacity-100" : "opacity-0"
                            )}
                          />
                          {idx}
                        </CommandItem>
                      ))}
                    </CommandGroup>
                  </CommandList>
                </Command>
              </PopoverContent>
            </Popover>
          </div>

          {/* PERIOD SWITCHER */}
          <div className="space-y-2">
            <h2 className="text-[10px] font-black uppercase tracking-widest text-slate-400 text-right mr-1">History Window</h2>
            <Tabs value={activeWindow} onValueChange={setActiveWindow}>
              <TabsList className="segmented-tabs-list !mb-0">
                {navPeriods.map(p => (
                  <TabsTrigger key={p} value={p} className="segmented-tab-trigger">{p}</TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
          </div>
        </div>
      </div>

      {/* CHARTS AREA */}
      <AnimatePresence mode="wait">
        <motion.div 
          key={activeIndex + activeWindow}
          initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}
          className="space-y-12"
        >
          {data?.error ? (
            <div className="p-20 text-center border-2 border-dashed rounded-3xl text-slate-400 font-bold uppercase tracking-widest text-[10px]">
              {data.error}
            </div>
          ) : (
            <>
              {data?.pe?.stats && <ValuationChart title="P/E Ratio" dates={data.dates} values={data.pe.values} stats={data.pe.stats} />}
              {data?.pb?.stats && <ValuationChart title="P/B Ratio" dates={data.dates} values={data.pb.values} stats={data.pb.stats} />}
              {data?.dy?.stats && <ValuationChart title="Dividend Yield" dates={data.dates} values={data.dy.values} stats={data.dy.stats} reverseColors={true} />}
            </>
          )}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}