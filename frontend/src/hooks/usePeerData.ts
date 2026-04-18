// src/hooks/usePeerData.ts
import { useQuery } from '@tanstack/react-query';

export const usePeerData = () => {
  return useQuery({
    queryKey: ['peers'],
    queryFn: async () => {
      const res = await fetch('http://localhost:8000/api/peer-comparison');
      return res.json();
    }
  });
};