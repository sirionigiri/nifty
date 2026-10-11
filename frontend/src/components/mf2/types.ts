export type Num = number | null
export type Coverage = "any" | "half" | "all"

export type MF2Fund = { c: number; n: string; a: string | null; k: string }
export type MF2Config = {
  classes: { id: string; count: number }[]
  funds: MF2Fund[]
  hidden: number
  as_of: string | null
  indices: string[]
  min_date: string
  max_date: string
}
export type MF2Item = {
  id: string; name: string; kind: "fund" | "index"
  amc: string | null; cls: string | null; is_benchmark: boolean
}
export type MF2Analysis = {
  as_of: string; benchmark: string; periods: number[]; items: MF2Item[]
  cagr: Record<string, Num[]>; excess: Record<string, Num[]>
  corr: Record<string, Num[]>; te: Record<string, Num[]>
  years: number[]; n_valid: Record<string, number>
  cal: Record<string, Num[]>; ytd_year: number | null; ytd: Num[] | null
  roll_years: number[]; roll3: Record<string, Num[]>
  rank: Record<string, Num[]>; universe: Record<string, number>
  median_rank: Num[]; avg_rank: Record<string, Num[]>
}