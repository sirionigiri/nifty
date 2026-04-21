// src/hooks/usePeerData.ts
import { useQuery } from '@tanstack/react-query';
import { API_BASE_URL} from '@/lib/utils';


export const usePeerData = () => {
  return useQuery({
    queryKey: ['peers'],
    queryFn: async () => {
      const res = await fetch(`${API_BASE_URL}/api/peer-comparison`);
      return res.json();
    }
  });
};