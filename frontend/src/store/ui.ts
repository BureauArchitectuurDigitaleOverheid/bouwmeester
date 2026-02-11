import { create } from 'zustand';
import type { NodeType } from '@/types';

interface UIState {
  sidebarOpen: boolean;
  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;

  mobileSidebarOpen: boolean;
  toggleMobileSidebar: () => void;
  setMobileSidebarOpen: (open: boolean) => void;

  selectedNodeType: NodeType | undefined;
  setSelectedNodeType: (nodeType: NodeType | undefined) => void;

  graphFilters: {
    nodeTypes: NodeType[];
    depth: number;
  };
  setGraphFilters: (filters: Partial<UIState['graphFilters']>) => void;
}

export const useUIStore = create<UIState>((set) => ({
  sidebarOpen: true,
  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
  setSidebarOpen: (open) => set({ sidebarOpen: open }),

  mobileSidebarOpen: false,
  toggleMobileSidebar: () => set((state) => ({ mobileSidebarOpen: !state.mobileSidebarOpen })),
  setMobileSidebarOpen: (open) => set({ mobileSidebarOpen: open }),

  selectedNodeType: undefined,
  setSelectedNodeType: (nodeType) => set({ selectedNodeType: nodeType }),

  graphFilters: {
    nodeTypes: [],
    depth: 2,
  },
  setGraphFilters: (filters) =>
    set((state) => ({
      graphFilters: { ...state.graphFilters, ...filters },
    })),
}));
