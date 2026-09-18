const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname, '../moteur/web/workflow-v2.js'), 'utf8');
const layout = fs.readFileSync(path.join(__dirname, '../moteur/web/layout-v3.js'), 'utf8');
const index = fs.readFileSync(path.join(__dirname, '../moteur/web/index.html'), 'utf8');
const fast = fs.readFileSync(path.join(__dirname, '../moteur/web/fast-workflow.js'), 'utf8');

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
  assert.match(layout, /Correction — taille/);
  assert.match(layout, /Corrigé — taille/);
  assert.match(layout, /Pages dédiées/);
  assert.match(layout, /Colonnes du corrigé/);
  assert.match(layout, /Côte à côte/);
  assert.match(layout, /Format terminal d’impression/);
  assert.match(layout, /\/api\/layout-preview/);
  assert.match(layout, /Lorem ipsum/);
});

test('final step groups document notes and feedback', () => {
  assert.match(source, /Document final et notes/);
  assert.match(source, /notes\.pdf/);
  assert.match(source, /notes\.csv/);
  assert.match(source, /exchangePanel\('retour'/);
});

test('preview overlays are loaded in dependency order', () => {
  assert.ok(index.indexOf('/app.js') < index.indexOf('/workflow-v2.js'));
  assert.ok(index.indexOf('/workflow-v2.js') < index.indexOf('/grid-preview.js'));
  assert.ok(index.indexOf('/grid-preview.js') < index.indexOf('/layout-v3.js'));
});


test('fast workflow is loaded last and collapses the UI to four stages', () => {
  assert.ok(index.indexOf('/hotfix-pr20.js') < index.indexOf('/fast-workflow.js'));
  for (const label of ['Barème','Calibrage','Correction complète','Résultats']) assert.match(fast, new RegExp(label));
  assert.match(fast, /La correction me convient/);
  assert.match(fast, /slice\(0,5\)/);
});
