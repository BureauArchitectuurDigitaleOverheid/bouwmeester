import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { InboxItemCard } from './InboxItem';
import { renderWithProviders } from '@/test/utils';
import type { InboxItem } from '@/types';

const baseItem: InboxItem = {
  id: 'item-1',
  type: 'message',
  title: 'Testbericht',
  description: 'Een test beschrijving',
  created_at: new Date().toISOString(),
  read: false,
};

const scrollMock = vi.fn();

beforeEach(() => {
  scrollMock.mockClear();
  Element.prototype.scrollIntoView = scrollMock;
});

describe('InboxItemCard', () => {
  it('renders title and description', () => {
    renderWithProviders(<InboxItemCard item={baseItem} />);
    expect(screen.getByText('Testbericht')).toBeInTheDocument();
    expect(screen.getByText('Een test beschrijving')).toBeInTheDocument();
  });

  it('applies highlight ring when highlighted', () => {
    const { container } = renderWithProviders(
      <InboxItemCard item={baseItem} highlighted />,
    );
    const card = container.querySelector('.ring-2');
    expect(card).toBeInTheDocument();
  });

  it('does not apply highlight ring by default', () => {
    const { container } = renderWithProviders(
      <InboxItemCard item={baseItem} />,
    );
    const card = container.querySelector('.ring-2');
    expect(card).not.toBeInTheDocument();
  });

  it('calls scrollIntoView when highlighted', () => {
    renderWithProviders(<InboxItemCard item={baseItem} highlighted />);
    expect(scrollMock).toHaveBeenCalledWith({ behavior: 'smooth', block: 'center' });
  });

  it('does not scroll when not highlighted', () => {
    renderWithProviders(<InboxItemCard item={baseItem} />);
    expect(scrollMock).not.toHaveBeenCalled();
  });
});
