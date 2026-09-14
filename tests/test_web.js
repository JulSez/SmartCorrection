// Focused UI logic tests without a browser or third-party dependencies.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../moteur/web/app.js'), 'utf8');

test('final selection shows reversible choices and counts only included copies',()=>{
 const h=harness();
 h.run(`state.copies=[{reference:'C001',numero:1,pages:[1],statut:'present',correction_id:1,exclue_final:0},{reference:'C002',numero:2,pages:[2],statut:'present',exclue_final:1}];renderCorrection(true)`);
 const html=h.node('#main').innerHTML;
 assert.match(html,/data-final-copy="C001"[^>]*checked/);
 assert.doesNotMatch(html,/data-final-copy="C002"[^>]*checked/);
 assert.match(html,/1 copie\(s\) incluse\(s\) · 1 exclue\(s\)/);
 assert.match(html,/<strong>0<\/strong><span>restantes/);
 h.run('state.copies.forEach(c=>c.exclue_final=1);renderCorrection(true)');
 assert.match(h.node('#main').innerHTML,/id="generate-pdf" disabled/);
 assert.match(h.node('#main').innerHTML,/id="generate-tex" disabled/);
 h.run('renderCorrection(false)');
 assert.doesNotMatch(h.node('#main').innerHTML,/data-final-copy=/);
});

test('final checkbox persists both choices and refreshes the dossier',async()=>{
 const h=harness(), calls=[];
 h.run('renderDossier=()=>{}');
 const box={dataset:{finalCopy:'C001'},checked:false};
 h.context.box=box;
 h.context.fetch=async(url,options)=>{
  if(options?.method==='POST')calls.push(JSON.parse(options.body));
  return {ok:true,json:async()=>({dossier:{id:'demo'},copies:[{reference:'C001',exclue_final:!box.checked}]})};
 };
 await h.run('toggleFinalCopy(box)');
 assert.equal(h.run('state.copies[0].exclue_final'),true);
 box.checked=true;
 await h.run('toggleFinalCopy(box)');
 assert.deepEqual(calls,[false,true].map(inclure=>({action:'selection_finale',dossier:'demo',reference:'C001',inclure})));
 assert.equal(h.run('state.copies[0].exclue_final'),false);
});

test('failed final selection restores the checkbox and explains the error',async()=>{
 const h=harness();
 h.context.box={dataset:{finalCopy:'C001'},checked:false};
 h.context.fetch=async()=>({ok:false,json:async()=>({erreur:'Enregistrement impossible'})});
 await h.run('toggleFinalCopy(box)');
 assert.equal(h.context.box.checked,true);
 assert.match(h.node('#toast').textContent,/Enregistrement impossible/);
});

test('identity reconciliation leaves ambiguous pupils undecided and labels a real merge',()=>{
 const h=harness();
 h.run(`renderRosterPreview({empreinte:'snapshot',identites:[],eleves:[{ligne:1,nom:'Dupont',prenom:'Alice',inscrit_id:1,lignes_proches:[],candidats:[{id:1,nom:'Dupont',prenom:'Alice',classes:['A'],raison:'Exact'},{id:8,nom:'Dupont Martin',prenom:'Alice',classes:['B'],raison:'Proche'}]}]})`);
 assert.equal(h.node('#roster-save').disabled,true);
 assert.match(h.node('#roster-preview').innerHTML,/Fusionner ID 1 dans ID 8/);
 h.node('#identity-1').value='id:8';
 assert.equal(JSON.stringify(h.run('rosterChoices()')),JSON.stringify([{id:8,fusionner:1}]));
 h.node('#identity-1').value='new';
 assert.equal(JSON.stringify(h.run('rosterChoices()')),JSON.stringify([{nouveau:true}]));
});

test('CSV duplicates can refer to an earlier line without creating another ID',()=>{
 const h=harness();
 h.run(`rosterPreview={eleves:[{ligne:1,inscrit_id:null},{ligne:2,inscrit_id:null}]}`);
 h.node('#identity-1').value='id:42';h.node('#identity-2').value='line:1';
 assert.equal(JSON.stringify(h.run('rosterChoices()')),JSON.stringify([{id:42},{ligne:1}]));
});

test('group editor is optional and shows local identities and missing groups',()=>{
 const h=harness();
 assert.doesNotMatch(h.run('groupsPanel()'),/id="groups-active" checked/);
 h.run("state.groupes={actif:true,membres:[{numero_groupe:1,numero:2,nom:'Local',prenom:'Alice'}],sans_groupe:[3]}");
 const html=h.run('groupsPanel()');
 assert.match(html,/id="groups-active" checked/);
 assert.match(html,/2 — Alice Local/);
 assert.match(html,/Sans groupe : 3/);
 assert.match(html,/Enregistrer les groupes/);
});

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

function navigationHarness(error=null) {
  const h=harness(), calls=[];
  const server={dossier:{id:'demo',echantillon_valide:false},copies:[{reference:'C001',echantillon:true}]};
  h.run('current=4;renderDossier=()=>{};');
  h.context.document.querySelectorAll=selector=>selector==='[data-sample]:checked'?[{dataset:{sample:'C001'}}]:[];
  h.context.fetch=async(url,options)=>{
    if(options?.method==='POST'){
      calls.push(JSON.parse(options.body));
      if(error)return {ok:false,json:async()=>({erreur:error})};
      server.dossier.echantillon_valide=true;
    }
    return {ok:true,json:async()=>JSON.parse(JSON.stringify(server))};
  };
  return {...h,calls};
}

test('next step validates the sample before navigating, without a separate approval button',async()=>{
  const h=navigationHarness();
  await h.run('goStep(5)');
  assert.equal(h.run('current'),5);
  assert.equal(h.run('state.dossier.echantillon_valide'),true);
  assert.deepEqual(h.calls,[{action:'echantillon',dossier:'demo',references:['C001'],valider:true}]);
  assert.doesNotMatch(source,/approve-sample|Je valide l’échantillon/);
});

test('a rejected sample keeps the current screen and explains what is missing',async()=>{
  const h=navigationHarness('C001 doit être corrigée et vérifiée avant validation');
  await h.run('goStep(5)');
  assert.equal(h.run('current'),4);
  assert.match(h.node('#toast').textContent,/C001 doit être corrigée/);
});

test('backward navigation never approves; a sidebar jump uses the saved selection',async()=>{
  const h=navigationHarness();
  await h.run('goStep(3)');
  assert.equal(h.calls.length,0);
  await h.run('goStep(5)');
  assert.deepEqual(h.calls[0].references,['C001']);
  assert.equal(h.run('current'),5);
});

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

test('saving advances preparation only after success and offers each missing reference',async()=>{
  for(const [stage,start,versions,expected,nextVersion] of [
    ['grille',1,[{version:'A',corrige_latex:''}],2,null],
    ['corrige:A',2,[{version:'A',corrige_latex:'ok'},{version:'B',corrige_latex:''}],2,'B'],
    ['corrige:A',2,[{version:'A',corrige_latex:'ok'}],3,null],
    ['copies',3,[],4,null],
    ['correction',4,[],4,null],
    ['correction',5,[],5,null],
  ]){
    const h=harness();
    h.run(`current=${start};referenceVersion=null;lastPreview={};previewText='{}';renderDossier=()=>{};`);
    h.node('#response').dataset.stage=stage;h.node('#response').value='{}';
    const server={dossier:{id:'demo',revision:1,echantillon_valide:false},versions};
    const calls=[];
    h.context.fetch=async(_url,options)=>{
      if(options)calls.push(JSON.parse(options.body));
      return {ok:true,json:async()=>server};
    };
    await h.run('submitResponse(true)');
    assert.equal(h.run('current'),expected,stage);
    assert.equal(h.run('referenceVersion'),nextVersion);
    assert.equal(h.run('state.dossier.echantillon_valide'),false);
    assert.equal(calls.length,1);
    assert.equal(calls[0].valider,true);
  }
  const h=harness();
  h.run("current=1;lastPreview={};previewText='{}';drafts.set('demo:grille','{}');");
  h.node('#response').dataset.stage='grille';h.node('#response').value='{}';
  h.context.fetch=async()=>({ok:false,json:async()=>({erreur:'Grille invalide'})});
  await h.run('submitResponse(true)');
  assert.equal(h.run('current'),1);
  assert.equal(h.run("drafts.get('demo:grille')"),'{}');
});

test('exchange panels expose IA wording and primary actions, with exports in more options',()=>{
  const h=harness();
  const html=h.run("exchangePanel('grille')");
  assert.match(html,/Consigne à copier dans l’IA/);
  assert.match(html,/Résultat de l’IA/);
  assert.match(html,/id="copy-prompt" disabled>Copier<\/button>/);
  assert.match(html,/Enregistrer et continuer/);
  assert.doesNotMatch(source,/ChatGPT|chatgpt\.com/);
  h.run('renderCorrection(false)');
  assert.match(h.node('#main').innerHTML,/Voir les fiches du test/);
  assert.match(h.node('#main').innerHTML,/<details class="more-options"><summary>Plus d’options<\/summary><button id="generate-tex"/);
});
