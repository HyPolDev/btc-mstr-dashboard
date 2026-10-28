import test from 'node:test';
import assert from 'node:assert/strict';
import { calculateDilution } from '../dilution.mjs';

const rows = [
  { date: '2024-08-07', issuedShares: 100_000_000, capitalAsOf: '2024-06-30', sharesBasis: 'carried' },
  { date: '2024-08-08', issuedShares: 105_000_000, capitalAsOf: '2024-06-30' },
  { date: '2024-08-12', issuedShares: 120_000_000, capitalAsOf: '2024-08-11', capitalPublishedAt: '2024-08-12' },
];
const params = { rows, purchaseDate: '2024-08-07', purchasePrice: 1000, purchasedShares: 100,
                 currentBasicShares: 200_000_000, currentAsOf: '2024-08-11' };

test('ownership loss is a relative percentage, with the original position rebased for the split', () => {
  const r = calculateDilution(params);
  assert.equal(r.available, true);
  assert.equal(r.dilutionPct, 50);
  assert.equal(r.initialOwnershipPct, 0.001);
  assert.equal(r.currentOwnershipPct, 0.0005);
  assert.equal(r.purchasedSharesOnCurrentBasis, 1000);
  assert.equal(r.purchasePriceOnCurrentBasis, 100);
  assert.equal(r.initialRowDate, '2024-08-07');
  assert.equal(r.initialCapitalAsOf, '2024-06-30');
  assert.equal(r.initialSharesBasis, 'carried');
  assert.equal(r.splitAdjusted, true);
});

test('a purchase on the split date uses post-split shares and price', () => {
  const r = calculateDilution({ ...params, purchaseDate: '2024-08-08' });
  assert.equal(r.purchasedSharesOnCurrentBasis, 100);
  assert.equal(r.purchasePriceOnCurrentBasis, 1000);
  assert.equal(r.initialBasicShares, 105_000_000);
  assert.equal(r.splitAdjusted, false);
  assert.equal(r.dilutionPct, 47.5);
});

test('weekend selects prior trading observation even if rows are unsorted', () => {
  const r = calculateDilution({ ...params, rows: [...rows].reverse(), purchaseDate: '2024-08-11' });
  assert.equal(r.initialRowDate, '2024-08-08');
  assert.equal(r.initialBasicShares, 105_000_000);
});

test('a smaller current share count is ownership growth, not positive dilution', () => {
  const r = calculateDilution({ ...params, currentBasicShares: 80_000_000 });
  assert.equal(r.dilutionPct, -25);
  assert.ok(r.currentOwnershipPct > r.initialOwnershipPct);
});

test('later published historical estimates expose their provenance', () => {
  const r = calculateDilution({ ...params, purchaseDate: '2024-08-12' });
  assert.equal(r.initialCapitalPublishedAt, '2024-08-12');
  assert.equal(r.currentAsOf, '2024-08-11');
});

test('reject missing, impossible, or unavailable inputs without fabricating zero', () => {
  for (const override of [
    { purchaseDate: '2024-02-30' }, { purchaseDate: '2024-08-13' },
    { purchaseDate: '2020-01-01' }, { purchasePrice: '' }, { purchasedShares: 0 },
    { purchasedShares: Infinity }, { currentBasicShares: null }, { rows: [] },
    { currentAsOf: 'invalid' }, { purchasedShares: 100_000_001 },
  ]) {
    const r = calculateDilution({ ...params, ...override });
    assert.equal(r.available, false);
    assert.ok(r.reason);
    assert.equal(r.dilutionPct, undefined);
  }
});
