'use strict';

const dashboardModel = (() => {
  const metrics = () => ({ arrivals: 0, closures: 0, backlog: 0, aged30: 0 });
  const byLabel = new Intl.Collator('en', { numeric: true });
  const matches = (problem, borough, filters) =>
    (!filters.problem || filters.problem === problem) && (!filters.borough || filters.borough === borough);

  function group(map, key) {
    if (!map.has(key)) map.set(key, metrics());
    return map.get(key);
  }

  function summarize(rows, filters) {
    const days = new Map();
    const categories = new Map();
    const places = new Map();
    const last = filters.to || rows.at(-1)?.[0];
    const totals = metrics();

    for (const [day, problem, borough, arrivals, closures, backlog, aged30] of rows) {
      if ((filters.from && day < filters.from) || day > last) continue;
      const daily = group(days, day);
      if (!matches(problem, borough, filters)) continue;
      const category = group(categories, problem);
      const place = group(places, borough);
      for (const result of [totals, daily, category, place]) {
        result.arrivals += arrivals;
        result.closures += closures;
      }
      daily.backlog += backlog;
      daily.aged30 += aged30;
      if (day === last) {
        for (const result of [totals, category, place]) {
          result.backlog += backlog;
          result.aged30 += aged30;
        }
      }
    }

    const trend = Array.from(days, ([day, values]) => ({ day, ...values }));
    const weekMap = new Map();
    for (const point of trend) {
      const monday = new Date(point.day + 'T00:00:00Z');
      monday.setUTCDate(monday.getUTCDate() - (monday.getUTCDay() + 6) % 7);
      const week = monday.toISOString().slice(0, 10);
      if (!weekMap.has(week)) weekMap.set(week, { day: point.day, arrivals: 0, closures: 0 });
      weekMap.get(week).arrivals += point.arrivals;
      weekMap.get(week).closures += point.closures;
    }
    const labeled = (map) => Array.from(map, ([label, values]) => ({
      label, ...values, net: values.arrivals - values.closures,
    }));
    totals.net = totals.arrivals - totals.closures;
    totals.opening = totals.backlog - totals.net;
    return {
      totals,
      trend,
      weeks: Array.from(weekMap.values()),
      categories: labeled(categories).sort((a, b) => b.net - a.net || byLabel.compare(a.label, b.label)),
      places: labeled(places).sort((a, b) => b.backlog - a.backlog || byLabel.compare(a.label, b.label)),
    };
  }

  function reviewCases(rows, filters) {
    const query = (filters.search || '').trim().toLowerCase();
    return rows.filter(([key, problem, borough]) => matches(problem, borough, filters)
      && (!query || [key, problem, borough].some((value) => value.toLowerCase().includes(query))))
      .sort((a, b) => b[4] - a[4] || byLabel.compare(a[0], b[0]));
  }

  return { summarize, reviewCases };
})();

if (typeof module !== 'undefined') module.exports = dashboardModel;
