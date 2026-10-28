// This calculation runs entirely in the browser; it never sends position inputs.
// Historical and current basic share counts must both be on today's split basis.
const SPLIT_DATE = '2024-08-08';
const SPLIT_FACTOR = 10;

function validDate(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}

function positiveNumber(value) {
  if (value === null || value === undefined || typeof value === 'boolean' ||
      (typeof value === 'string' && value.trim() === '')) return null;
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : null;
}

const unavailable = reason => ({ available: false, reason });

/**
 * Approximate the change in a fixed position's share of basic shares outstanding.
 * Purchase quantity and price are entered as they were on the purchase date.
 * All company share counts are assumed already adjusted for the 2024 split.
 * Rows are reconstructed snapshots, not exact daily issuance records. Their
 * provenance is returned so callers can show any carried or retrospective data.
 */
export function calculateDilution({ rows, purchaseDate, purchasePrice, purchasedShares,
                                    currentBasicShares, currentAsOf } = {}) {
  if (!validDate(purchaseDate)) return unavailable('Enter a valid purchase date.');
  const price = positiveNumber(purchasePrice);
  const quantity = positiveNumber(purchasedShares);
  if (price === null || quantity === null) return unavailable('Enter a positive purchase price and number of shares.');
  const currentShares = positiveNumber(currentBasicShares);
  if (currentShares === null) return unavailable('Current basic shares outstanding are unavailable.');
  if (currentAsOf != null && !validDate(currentAsOf)) return unavailable('The current share count has an invalid as-of date.');
  if (!Array.isArray(rows) || rows.length === 0) return unavailable('Historical share counts are unavailable.');

  let latestDate = null;
  let initial = null;
  for (const row of rows) {
    if (!row || !validDate(row.date)) continue;
    if (latestDate === null || row.date > latestDate) latestDate = row.date;
    if (row.date <= purchaseDate && positiveNumber(row.issuedShares) !== null &&
        (initial === null || row.date > initial.date)) initial = row;
  }
  if (latestDate === null) return unavailable('Historical share counts have no valid dates.');
  if (purchaseDate > latestDate) return unavailable('Purchase date is after the latest available trading observation.');
  if (initial === null) return unavailable('No historical basic share count is available on or before the purchase date.');

  const splitAdjusted = purchaseDate < SPLIT_DATE;
  const adjustedQuantity = quantity * (splitAdjusted ? SPLIT_FACTOR : 1);
  const adjustedPrice = price / (splitAdjusted ? SPLIT_FACTOR : 1);
  const initialShares = positiveNumber(initial.issuedShares);
  if (!Number.isFinite(adjustedQuantity) || adjustedQuantity > initialShares || adjustedQuantity > currentShares)
    return unavailable('The position exceeds the reported basic shares outstanding.');

  // Percent of the company held initially and today, assuming no later trades.
  // Dilution is relative loss of ownership, not the increase in shares issued.
  const initialOwnershipPct = 100 * adjustedQuantity / initialShares;
  const currentOwnershipPct = 100 * adjustedQuantity / currentShares;
  const dilutionPct = 100 * (1 - initialShares / currentShares);
  const initialCapitalPublishedAt = typeof initial.capitalPublishedAt === 'string' ? initial.capitalPublishedAt : null;
  return {
    available: true,
    reason: null,
    initialBasicShares: initialShares,
    currentBasicShares: currentShares,
    initialOwnershipPct,
    currentOwnershipPct,
    dilutionPct,
    initialRowDate: initial.date,
    initialCapitalAsOf: initial.capitalAsOf || null,
    initialCapitalPublishedAt,
    initialSharesBasis: initial.sharesBasis || null,
    currentAsOf: currentAsOf || null,
    purchasedSharesOnCurrentBasis: adjustedQuantity,
    purchasePriceOnCurrentBasis: adjustedPrice,
    splitAdjusted,
  };
}
