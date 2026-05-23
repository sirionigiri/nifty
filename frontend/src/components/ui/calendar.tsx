"use client"

import * as React from "react"
import { ChevronLeft, ChevronRight } from "lucide-react"
import { DayPicker } from "react-day-picker"

import { cn } from "@/lib/utils"
import { buttonVariants } from "@/components/ui/button"

export type CalendarProps = React.ComponentProps<typeof DayPicker>

function Calendar({
  className,
  classNames,
  showOutsideDays = true,
  ...props
}: CalendarProps) {
  return (
    <DayPicker
      showOutsideDays={showOutsideDays}
      // --- FIX 1: This forces the calendar to always show 6 rows ---
      // This stops the height from jumping when switching months
      fixedWeeks 
      className={cn("p-3 bg-white dark:bg-slate-950", className)}
      classNames={{
        months: "flex flex-col sm:flex-row space-y-4 sm:space-x-4 sm:space-y-0",
        month: "space-y-4",
        
        // --- FIX 2: Header Layout ---
        // Increased height and added relative positioning
        month_caption: "flex justify-center pt-1 relative items-center h-10 mb-2",
        
        caption_label: "hidden", 
        
        dropdowns: "flex justify-center items-center gap-2 z-10", 
        dropdown: "flex items-center font-bold text-[11px] bg-slate-100 dark:bg-slate-900 px-2 py-1 rounded-md border border-slate-200 dark:border-slate-800 cursor-pointer outline-none hover:bg-slate-200 dark:hover:bg-slate-800 transition-colors",
        dropdown_root: "inline-flex items-center",
        
        nav: "flex items-center",
        // --- FIX 3: Arrow Positioning ---
        // Moved them slightly higher and ensured they don't overlap the first row of days
        button_previous: cn(
          buttonVariants({ variant: "outline" }),
          "h-7 w-7 bg-transparent p-0 opacity-50 hover:opacity-100 absolute left-4 top-5 z-20"
        ),
        button_next: cn(
          buttonVariants({ variant: "outline" }),
          "h-7 w-7 bg-transparent p-0 opacity-50 hover:opacity-100 absolute right-4 top-5 z-20"
        ),
        
        month_grid: "w-full border-collapse space-y-1",
        weekdays: "flex",
        weekday: "text-muted-foreground rounded-md w-9 font-normal text-[0.8rem]",
        week: "flex w-full mt-2",
        day: cn(
          buttonVariants({ variant: "ghost" }),
          "h-9 w-9 p-0 font-normal aria-selected:opacity-100"
        ),
        selected: "bg-blue-600 text-white hover:bg-blue-700 hover:text-white focus:bg-blue-600 focus:text-white rounded-md",
        today: "bg-slate-100 dark:bg-slate-800 text-slate-900 dark:text-slate-100 font-bold border border-blue-200 dark:border-blue-900",
        outside: "day-outside text-muted-foreground opacity-50 aria-selected:bg-accent/50 aria-selected:text-muted-foreground aria-selected:opacity-30",
        disabled: "text-muted-foreground opacity-50",
        hidden: "invisible",
        ...classNames,
      }}
      components={{
        CaptionLabel: () => <></>,
        Chevron: ({ orientation }) => {
          const Icon = orientation === "left" ? ChevronLeft : ChevronRight;
          return <Icon className="h-4 w-4" />;
        },
      }}
      {...props}
    />
  )
}
Calendar.displayName = "Calendar"

export { Calendar }