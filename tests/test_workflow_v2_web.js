const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname, '../moteur/web/workflow-v2.js'), 'utf8');
const index = fs.readFileSync(path.join(__dirname, '../moteur/web/index.html'), 'utf8');

test('workflow exposes the seven requested stages in order', () => {
  const expected = ['Format et documents','Corrigés','Grille','Prétraiter les copies','Tester la correction','Corriger le lot','Résultats et retour'];
  let last = -1;
  for (const label of expected) {
    const at = source.indexOf(`'${label}'`);
    assert.ok(at > last, `missing or out of order: ${label}`);
    last = at;
  }
});

test('format choice defaults to A6 and separates correction from corrige', () => {
  assert.match(source, /\['A6','A5','A4'\]/);
  assert.match(source, /format-correction/);
  assert.match(source, /format-corrige/);
  assert.match(source, /correction:'A6',corrige:'A6'/);
});

test('final step groups document notes and feedback', () => {
  assert.match(source, /Document final et notes/);
  assert.match(source, /notes\.pdf/);
  assert.match(source, /notes\.csv/);
  assert.match(source, /exchangePanel\('retour'/);
});

test('PR17 preview overlay is loaded after workflow v2', () => {
  assert.ok(index.indexOf('/app.js') < index.indexOf('/workflow-v2.js'));
  assert.ok(index.indexOf('/workflow-v2.js') < index.indexOf('/grid-preview.js'));
});
