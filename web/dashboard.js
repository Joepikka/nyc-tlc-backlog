'use strict';

(() => {
  const byId = (id) => document.getElementById(id);
  const setText = (id, value) => { byId(id).textContent = value; };
  const number = new Intl.NumberFormat('en-US');
  const date = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' });
  const signed = (value) => value === 0 ? '0' : `${value > 0 ? '+' : '−'}${number.format(Math.abs(value))}`;
  const dateLabel = (day) => date.format(new Date(day + 'T00:00:00Z'));
  const title = (value) => value === 'Unspecified' || value === 'UNSPECIFIED' ? 'Unspecified'
    : value.toLowerCase().replace(/\b[a-z]/g, (letter) => letter.toUpperCase());
  const screens = { overview: 'Overview', review: 'Review queue', source: 'Data & methods' };
  const data = window.nycData;

  if (!data?.daily?.length || !Array.isArray(data.worklist) || !data.source?.firstDay || !data.source.lastDay) {
    setText('startup', 'Dashboard data could not be loaded. Regenerate web/data.js with scripts/build_web.py, then reopen this page.');
    return;
  }

  const { daily, worklist, source } = data;
  const pageSize = 20;
  let summary;
  let filters;
  let matches = [];
  let page = 0;
  let view = 'overview';

  function element(tag, text = '', className = '') {
    const node = document.createElement(tag);
    node.textContent = text;
    node.className = className;
    return node;
  }

  function populate(id, values, label) {
    for (const value of values) byId(id).append(new Option(label(value), value));
  }

  const problems = [...new Set(daily.map((row) => row[1]))].sort();
  const boroughs = [...new Set(daily.map((row) => row[2]))].sort();
  for (const id of ['problem', 'review-problem']) populate(id, problems, (value) => value);
  for (const id of ['borough', 'review-borough']) populate(id, boroughs, title);
  for (const input of [byId('date-from'), byId('date-to')]) {
    input.min = source.firstDay;
    input.max = source.lastDay;
  }

  const updateTrend = dashboardCharts.chart(byId('trend-chart'), 'trend');
  const updateFlow = dashboardCharts.chart(byId('flow-chart'), 'flow');

  function download(filename, header, rows) {
    const cell = (value) => `"${String(value).replaceAll('"', '""')}"`;
    const csv = [header, ...rows].map((row) => row.map(cell).join(',')).join('\r\n');
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function renderCategories(categories) {
    const target = byId('category-bars');
    if (!categories.length) {
      target.replaceChildren(element('p', 'No category data for this selection.', 'empty-chart'));
      return;
    }
    const scale = Math.max(1, ...categories.map((item) => Math.abs(item.net)));
    target.replaceChildren(...categories.map((item) => {
      const row = element('button', '', 'rank-row');
      row.type = 'button';
      row.dataset.problem = item.label;
      row.setAttribute('aria-pressed', String(filters.problem === item.label));
      row.title = `${item.label} · ${number.format(item.arrivals)} new · ${number.format(item.closures)} recorded closures`;
      const track = element('span', '', 'rank-track');
      track.setAttribute('aria-hidden', 'true');
      if (item.net !== 0) {
        const bar = element('span', '', item.net < 0 ? 'rank-bar decrease' : 'rank-bar');
        const barWidth = 50 * Math.abs(item.net) / scale;
        bar.style.width = `${barWidth}%`;
        bar.style.left = `${item.net < 0 ? 50 - barWidth : 50}%`;
        track.append(bar);
      }
      row.append(element('span', item.label, 'rank-label'), track,
        element('span', signed(item.net), item.net < 0 ? 'rank-amount decrease' : 'rank-amount'));
      return row;
    }));
  }

  function renderBoroughs(places) {
    const target = byId('borough-bars');
    if (!places.length) {
      target.replaceChildren(element('p', 'No borough data for this selection.', 'empty-chart'));
      return;
    }
    const largest = Math.max(1, ...places.map((item) => item.backlog));
    target.replaceChildren(...places.map((item) => {
      const row = element('div', '', 'borough-row');
      const track = element('div', '', 'borough-track');
      track.setAttribute('aria-hidden', 'true');
      const old = element('span', '', 'borough-old');
      const young = element('span', '', 'borough-young');
      old.style.width = `${item.aged30 * 100 / largest}%`;
      young.style.width = `${(item.backlog - item.aged30) * 100 / largest}%`;
      const name = title(item.label);
      row.title = `${name} · ${number.format(item.aged30)} of ${number.format(item.backlog)} open cases aged 30+ days`;
      row.setAttribute('role', 'img');
      row.setAttribute('aria-label', row.title);
      track.append(old, young);
      row.append(element('span', name), track, element('strong', number.format(item.backlog)));
      return row;
    }));
  }

  function renderOverview() {
    const start = byId('date-from');
    const end = byId('date-to');
    const valid = start.validity.valid && end.validity.valid && start.value <= end.value;
    byId('date-error').hidden = valid;
    start.setAttribute('aria-invalid', String(!valid));
    end.setAttribute('aria-invalid', String(!valid));
    byId('download-summary').disabled = !valid;
    if (!valid) return;

    filters = { from: start.value, to: end.value, borough: byId('borough').value, problem: byId('problem').value };
    summary = dashboardModel.summarize(daily, filters);
    const { totals, categories, trend, places, weeks } = summary;
    const asOf = dateLabel(filters.to);
    setText('kpi-backlog', number.format(totals.backlog));
    setText('kpi-asof', `As of ${asOf}`);
    setText('kpi-arrivals', number.format(totals.arrivals));
    setText('kpi-closures', number.format(totals.closures));
    const share = totals.backlog ? (totals.aged30 / totals.backlog * 100).toFixed(1) + '%' : '—';
    setText('kpi-aged', share);
    setText('kpi-aged-count', `${number.format(totals.aged30)} open requests`);
    setText('net-badge', `${signed(totals.net)} net change`);
    byId('net-badge').classList.toggle('growing', totals.net > 0);
    setText('borough-caption', `Open cases on ${asOf}`);
    renderCategories(categories);
    renderBoroughs(places);
    updateTrend(trend, `Daily backlog, ending at ${number.format(totals.backlog)} open cases with ${number.format(totals.aged30)} aged 30 days or more`);
    updateFlow(weeks, `Weekly flow, ${number.format(totals.arrivals)} new requests and ${number.format(totals.closures)} recorded closures`);
    const top = categories.find((item) => item.net > 0);
    byId('insight').hidden = !top;
    if (top) {
      setText('insight-title', `${top.label} added ${number.format(top.net)} open cases`);
      setText('insight-detail', `${number.format(top.arrivals)} new requests · ${number.format(top.closures)} recorded closures`);
      byId('insight-link').dataset.problem = top.label;
    }
  }

  function renderReview() {
    matches = dashboardModel.reviewCases(worklist, {
      problem: byId('review-problem').value,
      borough: byId('review-borough').value,
      search: byId('review-search').value,
    });
    const pageCount = Math.max(1, Math.ceil(matches.length / pageSize));
    page = Math.max(0, Math.min(page, pageCount - 1));
    const start = page * pageSize;
    const subset = matches.slice(start, start + pageSize);
    setText('review-count', matches.length
      ? `Showing ${number.format(start + 1)}–${number.format(start + subset.length)} of ${number.format(matches.length)} cases open on ${dateLabel(source.lastDay)}`
      : `No open cases on ${dateLabel(source.lastDay)} match these filters.`);
    setText('page-count', `Page ${number.format(page + 1)} of ${number.format(pageCount)}`);
    byId('previous-page').disabled = page === 0;
    byId('next-page').disabled = page + 1 >= pageCount;
    byId('download-review').disabled = matches.length === 0;
    const target = byId('review-rows');
    if (subset.length === 0) {
      const empty = element('td', 'Change or reset the filters to find requests.');
      empty.colSpan = 6;
      const row = element('tr');
      row.append(empty);
      target.replaceChildren(row);
      return;
    }
    target.replaceChildren(...subset.map(([key, problem, borough, created, age], index) => {
      const row = element('tr');
      for (const value of [number.format(start + index + 1), key, problem, title(borough), dateLabel(created)]) {
        row.append(element('td', value));
      }
      row.append(element('td', `${number.format(age)} days`, age >= 30 ? 'case-age' : ''));
      return row;
    }));
  }

  function showView(focus) {
    const hash = location.hash.slice(1);
    view = Object.hasOwn(screens, hash) ? hash : 'overview';
    for (const section of document.querySelectorAll('[data-screen]')) section.hidden = section.id !== view;
    for (const nav of document.querySelectorAll('[data-nav]')) {
      if (nav.dataset.nav === view) nav.setAttribute('aria-current', 'page');
      else nav.removeAttribute('aria-current');
    }
    setText('page-label', screens[view]);
    document.title = `${screens[view]} · NYC 311 TLC Operations`;
    if (view === 'overview') renderOverview();
    else if (view === 'review') renderReview();
    if (focus) {
      byId(view + '-title').focus({ preventScroll: true });
      window.scrollTo(0, 0);
    }
  }

  function resetOverview() {
    byId('date-from').value = source.firstDay;
    byId('date-to').value = source.lastDay;
    byId('borough').value = '';
    byId('problem').value = '';
    if (view === 'overview') renderOverview();
  }

  function updateReview() {
    page = 0;
    renderReview();
  }

  byId('overview-filters').addEventListener('submit', (event) => event.preventDefault());
  byId('overview-filters').addEventListener('change', renderOverview);
  byId('reset-overview').addEventListener('click', resetOverview);
  byId('category-bars').addEventListener('click', (event) => {
    const row = event.target.closest('[data-problem]');
    if (!row) return;
    const field = byId('problem');
    field.value = field.value === row.dataset.problem ? '' : row.dataset.problem;
    renderOverview();
    field.focus();
  });
  byId('download-summary').addEventListener('click', () => {
    const rows = summary.trend.map(({ day, arrivals, closures, backlog, aged30 }) => [
      day, filters.problem || 'All categories', filters.borough || 'All boroughs',
      backlog - arrivals + closures, arrivals, closures, arrivals - closures, backlog, aged30,
    ]);
    download(`nyc-tlc-summary-${filters.from}-to-${filters.to}.csv`,
      ['day', 'problem', 'borough', 'opening_backlog', 'arrivals', 'closures', 'net_change', 'closing_backlog', 'aged30'], rows);
  });

  byId('review-problem').value = problems.includes('Taxi Complaint') ? 'Taxi Complaint' : '';
  byId('review-filters').addEventListener('submit', (event) => event.preventDefault());
  byId('review-filters').addEventListener('input', updateReview);
  byId('reset-review').addEventListener('click', () => {
    for (const id of ['review-problem', 'review-borough', 'review-search']) byId(id).value = '';
    updateReview();
  });
  byId('previous-page').addEventListener('click', () => { page--; renderReview(); });
  byId('next-page').addEventListener('click', () => { page++; renderReview(); });
  byId('download-review').addEventListener('click', () => download(`nyc-tlc-review-${source.lastDay}.csv`,
    ['unique_key', 'problem', 'borough', 'created_day', 'age_days'], matches));
  byId('insight-link').addEventListener('click', (event) => {
    byId('review-problem').value = event.currentTarget.dataset.problem;
    byId('review-borough').value = filters.borough;
    byId('review-search').value = '';
    page = 0;
  });
  document.querySelector('.skip-link').addEventListener('click', (event) => {
    event.preventDefault();
    byId('content').focus();
  });
  setText('source-citywide', number.format(source.citywide));
  setText('source-tlc', number.format(source.tlc));
  const size = (source.bytes / 1e9).toFixed(2) + ' GB';
  setText('source-size', size);
  setText('source-footnote', `${size} of NYC 311 source data · ${number.format(source.tlc)} TLC cohort records`);
  resetOverview();
  byId('startup').hidden = true;
  showView(false);
  window.addEventListener('hashchange', () => showView(true));
})();
