'use strict';

const dashboardCharts = (() => {
  const green = '#17694f';
  const gold = '#a36d21';
  const closed = '#9cb8ad';
  const label = '#53635d';
  const format = new Intl.NumberFormat('en-US');
  const date = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' });
  const shortDate = (value) => date.format(new Date(value + 'T00:00:00Z'));

  function tickStep(span) {
    const raw = Math.max(1, span / 4);
    const factor = 10 ** Math.floor(Math.log10(raw));
    return [1, 2, 2.5, 5, 10].find((value) => value * factor >= raw) * factor;
  }

  function stroke(ctx, points, color, width = 1) {
    ctx.beginPath();
    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    points.forEach(([x, y], index) => index ? ctx.lineTo(x, y) : ctx.moveTo(x, y));
    ctx.stroke();
  }

  function chart(canvas, kind) {
    const ctx = canvas.getContext('2d');
    const tip = canvas.nextElementSibling;
    const bounds = { left: 43, right: 15, top: 13, bottom: 30 };
    let data = [];
    let geometry;
    let selected = -1;
    let keyboard = false;
    canvas.tabIndex = 0;
    canvas.title = 'Use the arrow keys to inspect each data point';
    tip.setAttribute('role', 'status');

    function show(index) {
      if (!geometry || !data[index]) return;
      const point = data[index];
      const headline = shortDate(point.day);
      const summary = kind === 'trend'
        ? `${format.format(point.backlog)} total open\n${format.format(point.aged30)} aged 30+ days`
        : `${format.format(point.arrivals)} new requests\n${format.format(point.closures)} recorded closures`;
      tip.textContent = `${headline}\n${summary}`;
      tip.hidden = false;
      tip.style.left = `${Math.max(4, Math.min(geometry.x(index) + 9, geometry.width - tip.offsetWidth - 4))}px`;
      tip.style.top = '5px';
    }

    function draw() {
      const box = canvas.getBoundingClientRect();
      const width = box.width;
      const height = box.height;
      if (width < 1 || height < 1) return;
      const scale = window.devicePixelRatio || 1;
      canvas.width = Math.round(width * scale);
      canvas.height = Math.round(height * scale);
      ctx.setTransform(scale, 0, 0, scale, 0, 0);
      const plotWidth = width - bounds.left - bounds.right;
      const plotHeight = height - bounds.top - bounds.bottom;
      const isTrend = kind === 'trend';
      const values = data.flatMap((p) => isTrend ? [p.backlog, p.aged30] : [p.arrivals, p.closures]);
      const max = Math.max(1, ...values);
      const min = isTrend && values.length ? Math.min(...values) : 0;
      const step = tickStep(max - min);
      const low = Math.floor(min / step) * step;
      const high = Math.max(low + step, Math.ceil(max / step) * step);
      const y = (num) => bounds.top + ((high - num) / (high - low)) * plotHeight;
      const stride = plotWidth / Math.max(1, isTrend ? data.length - 1 : data.length);
      const x = (index) => data.length === 1 ? bounds.left + plotWidth / 2
        : bounds.left + (index + (isTrend ? 0 : .5)) * stride;
      geometry = { width, x, stride };

      ctx.font = '11px "Segoe UI", sans-serif';
      ctx.fillStyle = label;
      ctx.textAlign = 'right';
      ctx.textBaseline = 'middle';
      for (let tick = low; tick <= high + step / 100; tick += step) {
        const row = y(tick);
        stroke(ctx, [[bounds.left, row], [width - bounds.right, row]], '#e3ebe4');
        ctx.fillText(tick >= 1000 ? `${format.format(tick / 1000)}k` : format.format(tick), bounds.left - 8, row);
      }

      if (isTrend && data.length) {
        const open = data.map((point, index) => [x(index), y(point.backlog)]);
        const aged = data.map((point, index) => [x(index), y(point.aged30)]);
        const shade = ctx.createLinearGradient(0, bounds.top, 0, y(low));
        shade.addColorStop(0, '#d4e9db');
        shade.addColorStop(1, '#f5faf6');
        ctx.beginPath();
        ctx.moveTo(open[0][0], y(low));
        open.forEach(([px, py]) => ctx.lineTo(px, py));
        ctx.lineTo(open.at(-1)[0], y(low));
        ctx.closePath();
        ctx.fillStyle = shade;
        ctx.fill();
        ctx.lineJoin = 'round';
        stroke(ctx, open, green, 2.4);
        ctx.setLineDash([5, 4]);
        stroke(ctx, aged, gold, 1.8);
        ctx.setLineDash([]);
        if (data.length === 1) {
          for (const [point, color] of [[open[0], green], [aged[0], gold]]) {
            ctx.beginPath();
            ctx.arc(point[0], point[1], 4, 0, Math.PI * 2);
            ctx.fillStyle = color;
            ctx.fill();
          }
        }
      } else if (!isTrend) {
        const bar = Math.min(15, stride * .33);
        for (const [index, point] of data.entries()) {
          const center = x(index);
          ctx.fillStyle = green;
          ctx.fillRect(center - bar - 1, y(point.arrivals), bar, y(low) - y(point.arrivals));
          ctx.fillStyle = closed;
          ctx.fillRect(center + 1, y(point.closures), bar, y(low) - y(point.closures));
        }
      }

      ctx.fillStyle = label;
      const marks = Math.min(data.length, width < 365 ? 3 : width < 490 ? 4 : 6);
      for (let mark = 0; mark < marks; mark++) {
        const index = marks === 1 ? 0 : Math.round(mark * (data.length - 1) / (marks - 1));
        const horizontal = x(index);
        const stamp = shortDate(data[index].day);
        const textWidth = ctx.measureText(stamp).width;
        ctx.textAlign = 'center';
        ctx.fillText(stamp, Math.max(textWidth, Math.min(width - textWidth, horizontal)), height - 12);
      }
      if (selected >= 0 && data[selected]) {
        const horizontal = x(selected);
        stroke(ctx, [[horizontal, bounds.top], [horizontal, y(low)]], '#688779');
        show(selected);
      }
    }
    function clear() {
      keyboard = false;
      selected = -1;
      tip.hidden = true;
      draw();
    }
    canvas.addEventListener('pointermove', (event) => {
      if (!geometry || !data.length) return;
      keyboard = false;
      const local = event.clientX - canvas.getBoundingClientRect().left;
      const index = Math.max(0, Math.min(data.length - 1, Math.round((local - geometry.x(0)) / geometry.stride)));
      if (index !== selected) {
        selected = index;
        draw();
      }
    });
    canvas.addEventListener('pointerleave', () => { if (!keyboard) clear(); });
    canvas.addEventListener('blur', clear);
    canvas.addEventListener('keydown', (event) => {
      if (!data.length || !['ArrowLeft', 'ArrowRight', 'Home', 'End', 'Escape'].includes(event.key)) return;
      event.preventDefault();
      if (event.key === 'Escape') { clear(); return; }
      keyboard = true;
      if (event.key === 'Home') selected = 0;
      else if (event.key === 'End') selected = data.length - 1;
      else selected = Math.max(0, Math.min(data.length - 1, selected + (event.key === 'ArrowRight' ? 1 : -1)));
      draw();
    });
    new ResizeObserver(draw).observe(canvas);
    return (next, description) => {
      data = next;
      canvas.setAttribute('aria-label', `${description}. Use arrow keys to inspect dates.`);
      clear();
    };
  }
  return { chart, shortDate };
})();
