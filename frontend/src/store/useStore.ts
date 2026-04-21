import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

export type CategoryMap = Record<string, string[]>;

interface FilterState {
  selectedIndices: string[];
  benchmark: string;
  periods: string[];
  toggleIndex: (index: string) => void;
  // NEW: Bulk update function
  setSelectedIndices: (indices: string[]) => void;
  setBenchmark: (benchmark: string) => void;
  selectAll: (indices: string[]) => void;
  deselectAll: () => void;
}


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
      setSelectedIndices: (indices) => set({ selectedIndices: indices }),
      setBenchmark: (benchmark) => set({ benchmark }),
      selectAll: (indices) => set({ selectedIndices: indices }),
      deselectAll: () => set({ selectedIndices: [] }),
    }),
    {
      name: 'nse-screener-filters', // Unique key in LocalStorage
      storage: createJSONStorage(() => localStorage),
    }
  )
)