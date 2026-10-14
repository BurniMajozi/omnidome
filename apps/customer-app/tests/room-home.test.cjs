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
const file = path.resolve(__dirname, '../components/room-home.tsx');
const loaded = new Module(file, module); loaded.filename = file; loaded.paths = Module._nodeModulePaths(path.dirname(file));
loaded._compile(ts.transpileModule(fs.readFileSync(file, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } }).outputText, file);
const props = { homeId: 'home', devices: [], rooms: [], owner: true, connected: false, control: true, camera: false, busy: false, call: () => { throw Error('SSR must not call services'); }, changed: async () => {}, openMedia() {}, cameraPreview: () => null };
const render = changes => renderToStaticMarkup(React.createElement(loaded.exports.default, { ...props, ...changes }));
test('empty homes land on labelled interactive room showcase with tile actions', () => {
  const html = render({});
  for (const room of ['Living room', 'Kitchen', 'Bedroom', 'Energy']) assert.ok(html.includes(room));
  assert.ok(html.includes('Interactive showcase'));
  assert.ok(html.includes('preview only'));
  assert.ok(html.includes('Create room'));
  assert.ok(html.includes('Floor lamp, 70%. Open controls.'));
});
test('real rooms remain visible even when empty and are grouped separately', () => {
  const device = { id: 'device', name: 'Desk lamp', domain: 'light', room: 'Office', state: 'on', attributes: { brightness: 128 }, observed_at: '' };
  const html = render({ devices: [device], rooms: [{ id: 'r1', name: 'Office', kind: 'office' }, { id: 'r2', name: 'Kitchen', kind: 'kitchen' }] });
  assert.ok(!html.includes('Interactive showcase'));
  assert.ok(html.includes('Kitchen'));
  assert.ok(html.includes('This room is ready for devices'));
  assert.ok(html.includes('Desk lamp, 50%. Open controls.'));
  assert.ok(!html.includes('Floor lamp'));
});
test('staff cannot see create-room affordance', () => assert.ok(!render({ owner: false }).includes('Create room')));
test('unavailable devices and door sensors use truthful display states', () => {
  assert.equal(loaded.exports.deviceValue({ domain: 'light', state: 'unavailable', attributes: { brightness: 128 } }), 'Unavailable');
  assert.equal(loaded.exports.deviceValue({ domain: 'binary_sensor', state: 'off', attributes: { device_class: 'door' } }), 'Closed');
});
test('pop-ups show Off and Unavailable rather than an old brightness percentage', () => {
  assert.equal(loaded.exports.controlValue({ domain: 'light', state: 'off', attributes: { brightness: 179 } }, 70), 'Off');
  assert.equal(loaded.exports.controlValue({ domain: 'cover', state: 'unavailable', attributes: { current_position: 100 } }, 100), 'Unavailable');
  assert.equal(loaded.exports.controlValue({ domain: 'light', state: 'on', attributes: { brightness: 179 } }, 70), '70%');
});
test('showcase transitions keep zero brightness and closed blinds consistent', () => {
  const row = { id: 'demo', domain: 'light', state: 'on', attributes: { brightness: 179 } };
  assert.equal(loaded.exports.previewUpdate(row, 'turn_on', { brightness_pct: 0 }).state, 'off');
  assert.equal(loaded.exports.previewUpdate(row, 'set_cover_position', { position: 0 }).state, 'closed');
  assert.equal(loaded.exports.previewUpdate(row, 'set_cover_position', { position: 45 }).attributes.current_position, 45);
  assert.equal(loaded.exports.previewUpdate(row, 'media_pause').state, 'paused');
  assert.equal(row.attributes.brightness, 179);
});

