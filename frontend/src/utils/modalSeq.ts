/**
 * Shared global counter for modal stacking order.
 * Each open*Detail() call gets a unique, monotonically increasing number
 * so DetailModals can sort all open modals by recency.
 */
let _seq = 0;

export function nextModalSeq(): number {
  return ++_seq;
}
