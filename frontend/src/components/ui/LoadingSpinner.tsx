import { cn } from "@/lib/utils"

export function LoadingSpinner({ className }: { className?: string }) {
  return (
    <div className={cn("flex items-center justify-center w-full h-full min-h-[100px]", className)}>
      <div className="loader text-slate-900 dark:text-white"></div>
    </div>
  )
}