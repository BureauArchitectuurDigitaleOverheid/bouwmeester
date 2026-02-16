import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { CorpusMatrix } from './CorpusMatrix';
import { NodeType } from '@/types';
import type { GraphViewResponse } from '@/types';

// Mock contexts
vi.mock('@/contexts/VocabularyContext', () => ({
  useVocabulary: () => ({
    edgeLabel: (t: string) => t,
  }),
}));

const mockOpenNodeDetail = vi.fn();
vi.mock('@/contexts/NodeDetailContext', () => ({
  useNodeDetail: () => ({
    openNodeDetail: mockOpenNodeDetail,
  }),
}));

function wrapper({ children }: { children: React.ReactNode }) {
  return <MemoryRouter>{children}</MemoryRouter>;
}

const graphData: GraphViewResponse = {
  nodes: [
    { id: 'r1', title: 'Doel A', node_type: NodeType.DOEL, description: '' } as GraphViewResponse['nodes'][0],
    { id: 'r2', title: 'Doel B', node_type: NodeType.DOEL, description: '' } as GraphViewResponse['nodes'][0],
    { id: 'c1', title: 'Instrument X', node_type: NodeType.INSTRUMENT, description: '' } as GraphViewResponse['nodes'][0],
    { id: 'c2', title: 'Instrument Y', node_type: NodeType.INSTRUMENT, description: '' } as GraphViewResponse['nodes'][0],
  ],
  edges: [
    { id: 'e1', from_node_id: 'r1', to_node_id: 'c1', edge_type_id: 'related' },
    { id: 'e2', from_node_id: 'r2', to_node_id: 'c2', edge_type_id: 'implements' },
  ] as GraphViewResponse['edges'],
};

describe('CorpusMatrix', () => {
  beforeEach(() => {
    mockOpenNodeDetail.mockClear();
  });

  it('renders loading state', () => {
    const { container } = render(
      <CorpusMatrix
        rowNodeType={NodeType.DOEL}
        colNodeType={NodeType.INSTRUMENT}
        enabledEdgeTypes={new Set(['related'])}
        isLoading={true}
      />,
      { wrapper },
    );
    expect(container.querySelector('.animate-spin')).toBeInTheDocument();
  });

  it('renders error state', () => {
    render(
      <CorpusMatrix
        rowNodeType={NodeType.DOEL}
        colNodeType={NodeType.INSTRUMENT}
        enabledEdgeTypes={new Set(['related'])}
        isLoading={false}
        error={new Error('fail')}
      />,
      { wrapper },
    );
    expect(screen.getByText('Fout bij laden')).toBeInTheDocument();
  });

  it('renders empty state when no nodes match', () => {
    render(
      <CorpusMatrix
        rowNodeType={NodeType.DOEL}
        colNodeType={NodeType.INSTRUMENT}
        enabledEdgeTypes={new Set(['related'])}
        isLoading={false}
        graphData={{ nodes: [], edges: [] }}
      />,
      { wrapper },
    );
    expect(screen.getByText('Geen nodes gevonden voor de geselecteerde types.')).toBeInTheDocument();
  });

  it('renders row and column headers', () => {
    render(
      <CorpusMatrix
        rowNodeType={NodeType.DOEL}
        colNodeType={NodeType.INSTRUMENT}
        enabledEdgeTypes={new Set(['related', 'implements'])}
        isLoading={false}
        graphData={graphData}
      />,
      { wrapper },
    );
    expect(screen.getByText('Doel A')).toBeInTheDocument();
    expect(screen.getByText('Doel B')).toBeInTheDocument();
    expect(screen.getByText('Instrument X')).toBeInTheDocument();
    expect(screen.getByText('Instrument Y')).toBeInTheDocument();
  });

  it('renders connection dots for edges', () => {
    render(
      <CorpusMatrix
        rowNodeType={NodeType.DOEL}
        colNodeType={NodeType.INSTRUMENT}
        enabledEdgeTypes={new Set(['related', 'implements'])}
        isLoading={false}
        graphData={graphData}
      />,
      { wrapper },
    );
    // 2 edges → 2 dot buttons inside gridcells (not counting row header buttons)
    const grid = screen.getByRole('grid');
    const dotButtons = grid.querySelectorAll('td[role="gridcell"] button');
    expect(dotButtons).toHaveLength(2);
  });

  it('shows connection count in summary', () => {
    render(
      <CorpusMatrix
        rowNodeType={NodeType.DOEL}
        colNodeType={NodeType.INSTRUMENT}
        enabledEdgeTypes={new Set(['related', 'implements'])}
        isLoading={false}
        graphData={graphData}
      />,
      { wrapper },
    );
    expect(screen.getByText(/2 relaties/)).toBeInTheDocument();
  });

  it('filters edges by enabledEdgeTypes', () => {
    render(
      <CorpusMatrix
        rowNodeType={NodeType.DOEL}
        colNodeType={NodeType.INSTRUMENT}
        enabledEdgeTypes={new Set(['related'])}
        isLoading={false}
        graphData={graphData}
      />,
      { wrapper },
    );
    // Only 1 edge type enabled → 1 connection dot in gridcells
    const grid = screen.getByRole('grid');
    const dotButtons = grid.querySelectorAll('td[role="gridcell"] button');
    expect(dotButtons).toHaveLength(1);
  });

  it('has role="grid" on the table for accessibility', () => {
    render(
      <CorpusMatrix
        rowNodeType={NodeType.DOEL}
        colNodeType={NodeType.INSTRUMENT}
        enabledEdgeTypes={new Set(['related'])}
        isLoading={false}
        graphData={graphData}
      />,
      { wrapper },
    );
    expect(screen.getByRole('grid')).toBeInTheDocument();
  });

  it('shows symmetric hint when row and col types are the same', () => {
    const sameTypeData: GraphViewResponse = {
      nodes: [
        { id: 'n1', title: 'Doel A', node_type: NodeType.DOEL, description: '' } as GraphViewResponse['nodes'][0],
        { id: 'n2', title: 'Doel B', node_type: NodeType.DOEL, description: '' } as GraphViewResponse['nodes'][0],
      ],
      edges: [
        { id: 'e1', from_node_id: 'n1', to_node_id: 'n2', edge_type_id: 'related' },
      ] as GraphViewResponse['edges'],
    };

    render(
      <CorpusMatrix
        rowNodeType={NodeType.DOEL}
        colNodeType={NodeType.DOEL}
        enabledEdgeTypes={new Set(['related'])}
        isLoading={false}
        graphData={sameTypeData}
      />,
      { wrapper },
    );
    expect(screen.getByText(/symmetrische matrix/)).toBeInTheDocument();
  });

  it('opens row node detail when clicking a connection dot', async () => {
    const user = userEvent.setup();

    render(
      <CorpusMatrix
        rowNodeType={NodeType.DOEL}
        colNodeType={NodeType.INSTRUMENT}
        enabledEdgeTypes={new Set(['related'])}
        isLoading={false}
        graphData={graphData}
      />,
      { wrapper },
    );

    const grid = screen.getByRole('grid');
    const dotButton = grid.querySelector('td[role="gridcell"] button')!;
    await user.click(dotButton);
    // Should open the row node (r1), not the column node
    expect(mockOpenNodeDetail).toHaveBeenCalledWith('r1');
  });
});
