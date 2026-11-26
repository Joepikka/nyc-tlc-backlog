const { copyFileSync, mkdirSync } = require('node:fs');
const { dirname, join } = require('node:path');

const root = join(__dirname, '..');
const dashboard = ['index.html', 'styles.css', 'data.js', 'model.js', 'charts.js', 'dashboard.js']
  .map((name) => [`web/${name}`, name]);
const downloads = [
  'data/citywide-manifest.json',
  'report/review-list.xlsx',
  'report/validation.json',
  'report/walkthrough.mp4',
].map((name) => [name, name]);

for (const [source, destination] of [...dashboard, ...downloads]) {
  const target = join(root, 'dist', destination);
  mkdirSync(dirname(target), { recursive: true });
  copyFileSync(join(root, source), target);
}
