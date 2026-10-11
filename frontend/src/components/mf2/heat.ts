import type { CSSProperties } from "react"

export const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v)
export const fmtNum = (v: number | null | undefined, d = 2) => (isNum(v) ? v.toFixed(d) : "—")

export const tone = (v: number | null | undefined) =>
  !isNum(v) ? "text-slate-400" : v > 0 ? "text-green-600 font-bold" : v < 0 ? "text-red-600 font-bold" : "text-slate-500"

export function robustScale(vals: Array<number | null | undefined>, q = 0.95): number {
  const a = vals.filter(isNum).map(Math.abs).sort((x, y) => x - y)
  if (!a.length) return 1
  return a[Math.min(a.length - 1, Math.floor(a.length * q))] || 1
}

export function signHeat(v: number | null | undefined, scale: number): CSSProperties {
  if (!isNum(v)) return {}
  const a = 0.1 + Math.min(Math.abs(v) / scale, 1) * 0.55
  return { backgroundColor: v >= 0 ? `hsl(142 70% 38% / ${a})` : `hsl(0 78% 50% / ${a})` }
}

export function rankHeat(rank: number | null | undefined, n: number | undefined): CSSProperties {
  if (!isNum(rank) || !n) return {}
  const p = (rank - 1) / Math.max(n - 1, 1)
  return { backgroundColor: `hsl(${130 - p * 130} 70% 48% / 0.4)` }
}

export const fmtDate = (iso: string) =>
  new Date(iso + "T00:00:00").toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" })