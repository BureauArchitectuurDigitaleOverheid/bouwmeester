import { useContext } from 'react';
import { GlobalFileDropContext } from '@/contexts/GlobalFileDropContext';

export function useGlobalFileDropContext() {
  const ctx = useContext(GlobalFileDropContext);
  if (!ctx) throw new Error('useGlobalFileDropContext must be used within GlobalFileDropProvider');
  return ctx;
}
