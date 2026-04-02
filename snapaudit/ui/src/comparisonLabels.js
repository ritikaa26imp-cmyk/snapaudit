/** User-facing labels for API comparison_type values (internal keys unchanged). */
export const COMPARISON_TYPE_OPTIONS = [
  {
    value: 'catalog_vs_icud',
    label: 'Delivery Check (Reference vs Product Received by User)',
  },
  {
    value: 'catalog_vs_pickup',
    label: 'Return Check (Reference vs Product Returned by User)',
  },
];

export function labelForComparisonType(value) {
  const found = COMPARISON_TYPE_OPTIONS.find((o) => o.value === value);
  return found?.label ?? String(value ?? '');
}

/** Rewrite model-facing phrasing in verdict copy for the UI. */
export function humanizeVerdictCopy(text) {
  if (text == null || text === '') return text;
  let s = String(text);
  s = s.replace(/\bImage set 1\b/gi, 'Reference images');
  s = s.replace(/\bImage set 2\b/gi, 'Product Received by User / Product Returned by User');
  s = s.replace(/\bSet 1\b/gi, 'Reference images');
  s = s.replace(/\bSet 2\b/gi, 'Product Received by User / Product Returned by User');
  return s;
}
