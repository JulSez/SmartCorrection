// Focused UI logic tests without a browser or third-party dependencies.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../moteur/web/app.js'), 'utf8');

function harness() {
  const nodes = new Map();
  const node = selector => {
    if (!nodes.has(selector)) nodes.set(selector, {content: 'csrf', dataset: {}, value: '',
      innerHTML: '', textContent: '', disabled: false,
      insertAdjacentHTML(_where, html) { this.innerHTML += html; }});
    return nodes.get(selector);
  };
  const context = vm.createContext({
    document: {querySelector: node, querySelectorAll: () => []},
    fetch: () => new Promise(() => {}), setTimeout: () => 1, clearTimeout() {},
    window: {scrollTo() {}}, navigator: {clipboard: {writeText: async () => {}}},
  });
  const run = text => vm.runInContext(text, context);
  run(source);
  run(`state={dossier:{id:'demo',classe:'TEST',titre:'Équations',revision:1},
    grille:[],versions:[{version:'A',corrige_latex:'Corrigé intégral <fin>.'}],
    copies:[],brouillons:{},fichiers:[],rendus:[]};`);
  return {node, nodes, context, run};
}

test('grille and corrigé have separate screens, with a prerequisite before any grid exists', () => {
  const {run, node} = harness();
  run('renderGrid()');
  assert.match(node('#main').innerHTML, /data-stage="grille"/);
  assert.doesNotMatch(node('#main').innerHTML, /data-stage="corrige:/);
  run('current=2;renderReference()');
  assert.match(node('#main').innerHTML, /Étape 3 sur 7/);
  assert.match(node('#main').innerHTML, /data-stage="corrige:A"/);
  assert.doesNotMatch(node('#main').innerHTML, /data-stage="grille"|data-version=/);
  run('state.versions=[];renderReference()');
  assert.match(node('#main').innerHTML, /Validez d’abord la grille/);
  assert.doesNotMatch(node('#main').innerHTML, /id="response"/);
});

test('saved references reload in full and independent drafts take priority, even empty ones', () => {
  const {run, node} = harness();
  run('renderReference()');
  assert.match(node('#main').innerHTML, /Corrigé intégral &lt;fin&gt;\./);
  run("state.versions.push({version:'B',corrige_latex:'Seconde version'});referenceVersion='B';renderReference()");
  assert.match(node('#main').innerHTML, /data-stage="corrige:B"/);
  assert.match(node('#main').innerHTML, /Seconde version/);
  run("state.brouillons['corrige:A']='Brouillon A';referenceVersion='A';renderReference()");
  assert.match(node('#main').innerHTML, /Brouillon A/);
  run("drafts.set('demo:corrige:A','');renderReference()");
  assert.match(node('#main').innerHTML, /data-stage="corrige:A"[^>]*><\/textarea>/);
  assert.doesNotMatch(node('#main').innerHTML, /Brouillon A|Corrigé intégral/);
});

test('resume and navigation use the seven screens and independent validation markers', () => {
  const {run, node} = harness();
  assert.equal(run('resumeStep()'), 3);
  assert.equal(run("state.versions[0].corrige_latex='';resumeStep()"), 2);
  assert.equal(run("state.versions[0].corrige_latex='OK';state.copies=[{}];resumeStep()"), 4);
  assert.equal(run('state.dossier.echantillon_valide=true;resumeStep()'), 5);
  assert.equal(run('state.dossier.termine=true;resumeStep()'), 6);
  run(`bindCommon=()=>{};renderSetup=()=>{};renderGrid=()=>{};renderReference=()=>{};
    renderInventory=()=>{};renderCorrection=()=>{};renderFeedback=()=>{};
    state.grille=[{}];state.versions[0].corrige_latex='';current=2;renderDossier()`);
  assert.match(node('#dossier-nav').innerHTML, /step\s+done" data-step="1"/);
  assert.match(node('#dossier-nav').innerHTML, /step active\s*" data-step="2"/);
  assert.equal((node('#dossier-nav').innerHTML.match(/data-step=/g) || []).length, 7);
});

test('prompts load automatically and stale requests cannot overwrite a new screen or selection', async () => {
  const h = harness();
  h.context.fetch = async () => ({ok: true, json: async () => ({texte: 'Consigne JSON'})});
  await h.run("loadPrompt('grille')");
  assert.equal(h.node('#prompt').value, 'Consigne JSON');
  assert.equal(h.node('#copy-prompt').disabled, false);
  assert.doesNotMatch(source, /get-prompt|get-opening|Préparer la consigne|Préparer la procédure/);
  let resolve;
  h.context.fetch = () => new Promise(r => { resolve = r; });
  const pending = h.run("loadPrompt('grille')");
  h.nodes.delete('#prompt');
  const newArea = h.node('#prompt');
  resolve({ok: true, json: async () => ({texte: 'Ancienne consigne'})});
  await pending;
  assert.equal(newArea.value, '');
  const cancelled = h.run("loadPrompt('correction')");
  h.node('#prompt').dataset.cancelled = '1';
  resolve({ok: true, json: async () => ({texte: 'Ancienne sélection'})});
  await cancelled;
  assert.equal(h.node('#copy-prompt').disabled, true);
  assert.equal(h.node('#prompt').value, '');
});

test('a failed automatic prompt offers a retry; loading respects the existing busy state', async () => {
  const h = harness();
  h.context.fetch = async () => ({ok: false, json: async () => ({erreur: 'Valider la grille'})});
  await h.run("loadPrompt('grille')");
  assert.match(h.node('#prompt').placeholder, /Valider la grille/);
  assert.match(h.node('#copy-prompt').textContent, /Réessayer/);
  h.context.fetch = async () => ({ok: true, json: async () => ({texte: 'Nouvelle consigne'})});
  h.node('#copy-prompt').dataset.wasDisabled = '1';
  await h.node('#copy-prompt').onclick();
  assert.equal(h.node('#prompt').value, 'Nouvelle consigne');
  assert.equal(h.node('#copy-prompt').dataset.wasDisabled, '0');
  assert.equal(h.node('#copy-prompt').disabled, true);
});

test('JSON and LaTeX previews unwrap one code block without losing content', () => {
  const {run, context} = harness();
  for (const [stage, language, body] of [['grille', 'json', '{"grilles":[]}'], ['corrige:A', 'latex', 'Fin du corrigé.']]) {
    context.response = '```' + language + '\r\n' + body + '\r\n```';
    context.stage = stage;
    assert.equal(run('responseBody(response,stage)'), body);
  }
  context.response = 'Avant\n```json\n{}\n```';
  assert.equal(run("responseBody(response,'grille')"), context.response);
});

test('format repair is only offered for response validation errors with complete context', async () => {
  const h = harness();
  h.node('#prompt').value = 'Consigne JSON';
  h.node('#response').value = '{broken}';
  h.context.fetch = async () => ({ok: false, json: async () => ({erreur: 'Accès refusé', reponse_reparable: false})});
  await h.run("task(()=>post({action:'echange'}),{response:true})");
  assert.doesNotMatch(h.node('#exchange-error').innerHTML, /repair-prompt/);
  h.context.fetch = async () => ({ok: false, json: async () => ({erreur: 'JSON invalide', reponse_reparable: true})});
  await h.run("task(()=>post({action:'echange'}),{response:true})");
  assert.match(h.node('#exchange-error').innerHTML, /repair-prompt/);
  h.node('#response').value = '';
  await h.run("task(()=>post({action:'echange'}),{response:true})");
  assert.doesNotMatch(h.node('#exchange-error').innerHTML, /repair-prompt/);
  h.node('#exchange-error').innerHTML = '';
  await h.run("task(()=>post({action:'generer'}))");
  assert.equal(h.node('#exchange-error').innerHTML, '');
});
