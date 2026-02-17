export function formatCurrency(value?: number | string | null): string {
  if (value == null) return '-';
  const num = typeof value === 'string' ? parseFloat(value) : value;
  if (isNaN(num)) return '-';
  return new Intl.NumberFormat('nl-NL', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(num);
}

/**
 * Format currency in compact form for dashboard cards and summaries.
 * Examples: € 96,9M, € 1,2M, € 450K, € 12.500
 */
export function formatCurrencyCompact(value?: number | string | null): string {
  if (value == null) return '-';
  const num = typeof value === 'string' ? parseFloat(value) : value;
  if (isNaN(num)) return '-';
  const abs = Math.abs(num);
  const sign = num < 0 ? '- ' : '';
  if (abs >= 1_000_000) {
    const mln = abs / 1_000_000;
    const formatted = new Intl.NumberFormat('nl-NL', {
      minimumFractionDigits: mln >= 100 ? 0 : 1,
      maximumFractionDigits: mln >= 100 ? 0 : 1,
    }).format(mln);
    return `${sign}€\u00A0${formatted}M`;
  }
  if (abs >= 10_000) {
    const k = Math.round(abs / 1_000);
    const formatted = new Intl.NumberFormat('nl-NL').format(k);
    return `${sign}€\u00A0${formatted}K`;
  }
  return formatCurrency(value);
}
