import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Modal } from './Modal';

describe('Modal', () => {
  it('renders nothing when not open', () => {
    render(
      <Modal open={false} onClose={vi.fn()} title="Test">
        Content
      </Modal>,
    );
    expect(screen.queryByText('Test')).not.toBeInTheDocument();
    expect(screen.queryByText('Content')).not.toBeInTheDocument();
  });

  it('renders title and children when open', () => {
    render(
      <Modal open={true} onClose={vi.fn()} title="Bewerken">
        <p>Modal inhoud</p>
      </Modal>,
    );
    expect(screen.getByText('Bewerken')).toBeInTheDocument();
    expect(screen.getByText('Modal inhoud')).toBeInTheDocument();
  });

  it('renders footer when provided', () => {
    render(
      <Modal open={true} onClose={vi.fn()} title="Test" footer={<button>Opslaan</button>}>
        Body
      </Modal>,
    );
    expect(screen.getByText('Opslaan')).toBeInTheDocument();
  });

  it('calls onClose when close button is clicked', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(
      <Modal open={true} onClose={onClose} title="Sluiten">
        Content
      </Modal>,
    );

    // The close button contains an X icon - find the button near the title
    const buttons = screen.getAllByRole('button');
    await user.click(buttons[0]); // Close button is first
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('calls onClose when Escape is pressed', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(
      <Modal open={true} onClose={onClose} title="Escape test">
        Content
      </Modal>,
    );

    await user.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('calls onClose when overlay is clicked', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const { container } = render(
      <Modal open={true} onClose={onClose} title="Overlay">
        Content
      </Modal>,
    );

    // The overlay is the backdrop div
    const overlay = container.querySelector('.backdrop-blur-sm');
    if (overlay) await user.click(overlay);
    expect(onClose).toHaveBeenCalledOnce();
  });
});
