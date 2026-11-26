const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { summarize, reviewCases } = require('../web/model.js');

const project = path.join(__dirname, '..');
const { window: { nycData } } = vm.runInNewContext(
  fs.readFileSync(path.join(project, 'web/data.js'), 'utf8') + '\n;({window})',
  { window: {} },
);
const validation = JSON.parse(fs.readFileSync(path.join(project, 'report/validation.json'), 'utf8'));

test('the quarter dashboard reconciles to the validated roll-forward', () => {
  const { totals, categories, places, weeks } = summarize(nycData.daily, {});
  for (const key of ['opening', 'arrivals', 'closures', 'backlog', 'aged30']) {
    assert.equal(totals[key], validation.quarter[key], key);
  }
  assert.equal(totals.opening + totals.arrivals - totals.closures, totals.backlog);
  assert.equal(categories[0].label, 'Taxi Complaint');
  assert.equal(categories[0].net, 412);
  assert.equal(places.reduce((sum, item) => sum + item.backlog, 0), totals.backlog);
  assert.equal(weeks.reduce((sum, item) => sum + item.arrivals, 0), totals.arrivals);
});

test('single-day and combined filters retain the correct opening and closing balances', () => {
  const filters = { from: '2025-03-31', to: '2025-03-31', borough: 'QUEENS', problem: 'Taxi Complaint' };
  const { totals, trend } = summarize(nycData.daily, filters);
  assert.equal(trend.length, 1);
  assert.equal(totals.opening + totals.arrivals - totals.closures, totals.backlog);
  assert.equal(totals.backlog, reviewCases(nycData.worklist, filters).length);
  assert.equal(summarize(nycData.daily, { borough: 'QUEENS' }).totals.backlog, 2023);
  assert.equal(summarize(nycData.daily, { from: '2025-03-31', to: '2025-03-31' }).totals.backlog, 9685);
  assert.equal(summarize(nycData.daily, { borough: 'Missing' }).totals.backlog, 0);
});

test('the fixed March review queue matches Excel ordering and accepts exact key searches', () => {
  const filtered = reviewCases(nycData.worklist, { problem: 'Taxi Complaint' });
  assert.equal(filtered.length, 2089);
  assert.deepEqual(Array.from(filtered.slice(0, 20), (row) => row[0]),
    validation.taxi_review_list.map((row) => row.unique_key));
  assert.equal(reviewCases(nycData.worklist, { search: '59896371' })[0][4], 455);
  assert.equal(reviewCases(nycData.worklist, { search: 'no-matching-request' }).length, 0);
});
