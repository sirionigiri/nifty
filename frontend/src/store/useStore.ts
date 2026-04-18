import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface FilterState {
  selectedIndices: string[];
  benchmark: string;
  periods: string[];
  toggleIndex: (index: string) => void;
  setBenchmark: (benchmark: string) => void;
  selectAll: (indices: string[]) => void;
  deselectAll: () => void;
}

// Using 'persist' middleware so your checkboxes survive a refresh automatically
export const useStore = create<FilterState>()(
  persist(
    (set) => ({
      selectedIndices: ["NIFTY 50", "NIFTY NEXT 50"],
      benchmark: 'NIFTY 50',
      periods: ["Last Week", "1 Yr", "3 Yr", "5 Yr", "10 Yr", "Rolling 3-Yr Avg"],

      toggleIndex: (index) => set((state) => ({
        selectedIndices: state.selectedIndices.includes(index)
          ? state.selectedIndices.filter((i) => i !== index)
          : [...state.selectedIndices, index],
      })),
      setBenchmark: (benchmark) => set({ benchmark }),
      selectAll: (indices) => set({ selectedIndices: indices }),
      deselectAll: () => set({ selectedIndices: [] }),
    }),
    { name: 'nse-screener-storage' } // unique name for localStorage
  )
)