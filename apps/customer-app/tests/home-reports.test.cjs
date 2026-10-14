const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');
const originalLoad = Module._load;
Module._load = function(name, parent, main) { if (name === 'react' || name === 'react/jsx-runtime') name = 'next/dist/compiled/' + name; return originalLoad.call(this, name, parent, main); };
require.extensions['.css'] = loaded => { loaded.exports = new Proxy({}, { get: (_, key) => String(key) }); };
const React = require('next/dist/compiled/react');
const { renderToStaticMarkup } = require('next/dist/compiled/react-dom/server');
const file = path.resolve(__dirname, '../components/home-reports.tsx');
const loaded = new Module(file, module); loaded.filename = file; loaded.paths = Module._nodeModulePaths(path.dirname(file));
loaded._compile(ts.transpileModule(fs.readFileSync(file, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } }).outputText, file);
const call = () => { throw Error('SSR must not call services'); };
test('owner has an upgrade journey that explains no charge and unpublished pricing', () => {
  const html = renderToStaticMarkup(React.createElement(loaded.exports.default, { homeId: 'home', owner: true, call }));
  assert.ok(html.includes('Upgrade reporting'));
  assert.ok(html.includes('Pricing is not published yet'));
  assert.ok(html.includes('does not activate a paid plan or charge you'));
  assert.ok(html.includes('aria-labelledby="reporting-upgrade-title"'));
});
test('support viewers do not receive customer purchasing controls', () => {
  const html = renderToStaticMarkup(React.createElement(loaded.exports.default, { homeId: 'home', owner: false, call }));
  assert.ok(!html.includes('Upgrade reporting'));
  assert.ok(!html.includes('<dialog'));
});
test('negative measurements render with nonnegative SVG dimensions and calendar gaps', () => {
  const html = renderToStaticMarkup(React.createElement(loaded.exports.ReportChart, { sample: true, unit: '°C', points: [
    { date: '2026-09-01', value: -5, samples: 1 }, { date: '2026-09-03', value: 10, samples: 1 }
  ] }));
  assert.ok(html.includes('Sample daily values'));
  assert.ok(html.includes('-5 °C'));
  const bars = [...html.matchAll(/<rect[^>]*x="([\d.]+)"[^>]*height="([\d.]+)"/g)];
  assert.equal(bars.length, 2);
  assert.ok(Number(bars[1][1]) - Number(bars[0][1]) > 400);
  assert.ok(bars.every(row => Number(row[2]) > 0));
});
