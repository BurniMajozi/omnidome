const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');
// Match the React runtime used by this Next app, independently of Expo's hoisted React.
const originalLoad = Module._load;
Module._load = function (name, parent, main) {
  if (name === 'react' || name === 'react/jsx-runtime') name = 'next/dist/compiled/' + name;
  return originalLoad.call(this, name, parent, main);
};
const React = require('next/dist/compiled/react');
const { renderToStaticMarkup } = require('next/dist/compiled/react-dom/server');
const file = path.resolve(__dirname, '../components/energy-dashboard.tsx');
const compiled = ts.transpileModule(fs.readFileSync(file, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } }).outputText;
const loaded = new Module(file, module);
loaded.filename = file;
loaded.paths = Module._nodeModulePaths(path.dirname(file));
loaded._compile(compiled, file);
const Dashboard = loaded.exports.default;
const render = report => renderToStaticMarkup(React.createElement(Dashboard, { report, day: '2026-10-14', onDayChange() {} }));
const value = number => ({ value: number, unit: 'kWh', reason: null });
test('empty readings preserve the six source layout without inventing zero usage', () => {
  const html = render(null);
  for (const name of ['Grid', 'Solar', 'Home', 'Battery', 'Gas', 'Water']) assert.ok(html.includes('>' + name + '</text>'));
  assert.equal((html.match(/r="52"/g) || []).length, 6);
  assert.ok(html.includes('Waiting for power readings'));
  assert.ok(!html.includes('0 kWh'));
});
test('home consumption balances all five measured counters', () => {
  const html = render({ totals: { grid_import: value(10), grid_export: value(2), solar: value(5), battery_charge: value(3), battery_discharge: value(1) }, power: {}, grid_cost_zar: 27.5, note: 'Recorded values' });
  assert.ok(html.includes('11 kWh'));
  assert.ok(html.includes('R27.50'));
});
test('missing balance inputs do not masquerade as whole-home consumption', () => {
  const html = render({ totals: { grid_import: value(10) }, power: {}, grid_cost_zar: null, note: '' });
  assert.ok(html.includes('Connect import, export, solar and battery meters'));
});
test('invalid power samples cannot produce NaN SVG coordinates', () => {
  const html = render({ totals: {}, power: { grid_power: [{ time: 'invalid', kw: NaN }, { time: '2026-10-14T08:00:00Z', kw: 1 }] }, grid_cost_zar: null, note: '' });
  assert.ok(!html.includes('NaN'));
  assert.ok(html.includes('Waiting for power readings'));
});
test('only confirmed fresh flow is animated and reduced motion is respected', () => {
  const html = render({ totals: {}, power: {}, flows: { grid_import: true }, grid_cost_zar: null, note: '' });
  assert.equal((html.match(/<animateMotion /g) || []).length, 1);
  assert.ok(html.includes('prefers-reduced-motion: reduce'));
  assert.ok(!render(null).includes('<animateMotion '));
});
