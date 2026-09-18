const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname, '../moteur/web/fast-workflow.js'), 'utf8');
const index = fs.readFileSync(path.join(__dirname, '../moteur/web/index.html'), 'utf8');

test('fast workflow exposes four teacher-facing stages', () => {
  for (const label of ['Barème','Calibrage','Correction complète','Résultats']) assert.match(source, new RegExp(label));
  assert.match(source, /JSON → rendu → problèmes → lot suivant/);
  assert.match(source, /La correction me convient/);
});

test('fast workflow is loaded after legacy patches', () => {
  assert.ok(index.indexOf('/hotfix-pr20.js') < index.indexOf('/fast-workflow.js'));
});

test('calibration imports one JSON then advances by five', () => {
  assert.match(source, /etape:'calibrage'/);
  assert.match(source, /slice\(0,5\)/);
  assert.match(source, /moyenne_estimee/);
  assert.match(source, /calibrage-retours/);
});
