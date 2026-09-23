const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function harness() {
 const nodes=new Map();
 const node=s=>{if(!nodes.has(s))nodes.set(s,{content:'csrf',value:'',dataset:{},innerHTML:'',textContent:'',disabled:false,insertAdjacentHTML(_p,h){this.innerHTML+=h;}});return nodes.get(s);};
 const context=vm.createContext({document:{querySelector:node,querySelectorAll:()=>[],addEventListener(){}},fetch:()=>new Promise(()=>{}),setTimeout:()=>1,clearTimeout(){},window:{scrollTo(){}},navigator:{clipboard:{writeText:async()=>{}}}});
 const run=s=>vm.runInContext(s,context);
 const index=fs.readFileSync(path.join(__dirname,'../moteur/web/index.html'),'utf8');
 for(const m of index.matchAll(/<script src="\/([^"]+)"/g))run(fs.readFileSync(path.join(__dirname,'../moteur/web',m[1]),'utf8'));
 run(`state={dossier:{id:'demo',classe:'TEST',titre:'Test',revision:1},grille:[],versions:[],copies:[],brouillons:{},fichiers:[],rendus:[]};`);
 return {node,context,run};
}

test('active workflow selects newest valid PDF, never a stale SQLite false render',()=>{
 const h=harness();
 h.run('state.rendus=[{id:9,pdf:1,valide:0},{id:8,pdf:1,valide:1},{id:7,pdf:1,valide:1}]');
 assert.match(h.run('latestCalibrationRender()'),/id=8&/);
 assert.doesNotMatch(h.run('latestCalibrationRender()'),/id=9&|id=7&/);
});

test('active drafts restore, save before import, and survive rejected imports',async()=>{
 const h=harness(),calls=[];
 h.run(`state.brouillons.calibrage='saved';bindFastDraft('calibrage')`);
 assert.equal(h.node('#fast-response').value,'saved');
 h.run(`post=async data=>{calls.push(data);if(data.action==='echange'&&fail)throw Error('invalid');return {};}`.replace('calls.push(data)','record(data)'));
 h.context.record=x=>calls.push(JSON.parse(JSON.stringify(x)));h.context.fail=true;
 h.node('#fast-response').value='new';h.node('#fast-response').oninput();
 await assert.rejects(h.run("fastExchangeCommit('calibrage')"),/invalid/);
 assert.deepEqual(calls.map(c=>c.action),['brouillon','echange']);
 assert.equal(calls[0].texte,'new');
 assert.equal(h.run("drafts.get('demo:calibrage')"),'new');
 h.context.fail=false;
 await h.run("fastExchangeCommit('calibrage')");
 assert.equal(h.run("drafts.has('demo:calibrage')"),false);
});

test('active lot selection ignores excluded copies and includes previous copies to revisit',()=>{
 const h=harness();
 const result=h.run(`calibrationCandidates([{reference:'X',statut:'present',exclue_final:1},{reference:'R',statut:'present',correction_id:1,a_revoir:1},{reference:'N',statut:'present'},{reference:'A',statut:'absent'}])`);
 assert.deepEqual(Array.from(result),['N','R']);
 h.run(`state.copies=[{reference:'C001',statut:'present',pages:[1],exclue_final:0}];state.groupes={actif:true,membres:[],sans_groupe:[]}`);
 assert.match(h.run('copyControls()'),/data-final-copy="C001"/);
 assert.match(h.run('copyControls()'),/id="groups-active" checked/);
});

test('forward navigation validates calibration; refusal stays on the current screen',async()=>{
 for(const fail of [false,true]){
  const h=harness(), calls=[];
  h.context.record=x=>calls.push(x);h.context.fail=fail;
  h.run(`renderDossier=()=>{};state.grille=[{}];state.copies=[{reference:'C001',echantillon:1,statut:'present'}];
   get=async()=>state;post=async data=>{record(data);if(fail)throw Error('Copie à revoir');state.dossier.echantillon_valide=true};current=1;`);
  await h.run('goStep(2)');
  assert.equal(calls.length,1);assert.equal(calls[0].valider,true);
  assert.equal(h.run('current'),fail?1:2);
  if(fail)assert.match(h.node('#toast').textContent,/Copie à revoir/);
 }
 const h=harness();h.run('renderDossier=()=>{};get=async()=>state;post=async()=>{throw Error("Unexpected validation")};current=1');
 await h.run('goStep(0)');assert.equal(h.run('current'),0);
});

test('partial full import is successful and keeps remaining copies visible',async()=>{
 const h=harness();
 h.run(`bindFastPrompt=()=>{};bindCopyControls=()=>{};renderDossier=()=>{};
 state.copies=[{reference:'C001',statut:'present',pages:[1]}];get=async()=>state;
 fastExchangeCommit=async()=>({});current=2;renderFullCorrectionFast();`);
 await h.node('#fast-submit').onclick();
 assert.equal(h.run('current'),2);
 assert.match(h.node('#toast').textContent,/1 copie\(s\) restent/);
 assert.equal(h.node('#fast-error').innerHTML,'');
});

test('barème opens its PDF only after successful validation and stays on screen one',async()=>{
 for(const fail of [false,true]){
  const h=harness(),calls=[];
  h.context.record=x=>calls.push(x);h.context.fail=fail;
  h.run(`bindLayout=()=>{};bindAnonymity=()=>{};bindFastPrompt=()=>{};renderDossier=()=>{};
   showGridPreviewV2=()=>record('pdf');get=async()=>{record('refresh');return state};
   fastExchangeCommit=async()=>{record('validate');if(fail)throw Error('JSON invalide')};current=0;renderBaremeFast()`);
  assert.match(h.node('#main').innerHTML,/Valider et voir le barème/);
  await h.node('#fast-submit').onclick();
  assert.deepEqual(calls,fail?['validate']:['validate','refresh','pdf']);
  assert.equal(h.run('current'),0);
 }
});

test('assignment suggestions exclude assigned IDs and release them after unassignment',()=>{
 const h=harness();
 h.run(`state.eleves=[{id:1,numero:1,prenom:'Alice',nom:'A'},{id:2,numero:2,prenom:'Alice',nom:'B'},{id:3,numero:3,prenom:'Bob',nom:'C'}];
 state.pretraitement={copies:[{reference:'C001',eleve_id:'1'},{reference:'C002',eleve_id:null}]}`);
 assert.deepEqual(Array.from(h.run('availableAssignmentStudents().map(s=>s.id)')),[2,3]);
 const input={value:'Ali'},suggestions={innerHTML:'',querySelectorAll:()=>[]};
 const box={dataset:{reference:'C002'},querySelector:s=>s==='.copy-student-search'?input:s==='.student-suggestions'?suggestions:null};
 h.context.document.querySelectorAll=s=>s==='.student-search'?[box]:[];
 h.run('bindAssignments()');input.onfocus();
 assert.match(suggestions.innerHTML,/data-id="2"/);
 assert.doesNotMatch(suggestions.innerHTML,/data-id="1"|data-id="3"/);
 h.run('state.pretraitement.copies[0].eleve_id=null');input.oninput();
 assert.match(suggestions.innerHTML,/data-id="1"/);
 h.run('state.pretraitement.copies[1].eleve_id=2');input.oninput();
 assert.doesNotMatch(suggestions.innerHTML,/data-id="2"/);
});

test('layout offers explicit question and detailed grid modes and saves the choice',()=>{
 const h=harness();
 h.run("state.layout=currentLayout();state.layout.correction.grid_mode='detaillee'");
 const html=h.run('layoutCard()');
 assert.match(html,/value="detaillee" selected>Grille détaillée/);
 assert.match(html,/Grille par question/);
 h.node('#l-grid-mode').value='detaillee';
 assert.equal(h.run('layoutPayload().correction.grid_mode'),'detaillee');
});

test('copy grades distinguish zero, missing, absence, pending groups and review',()=>{
 const h=harness();
 assert.equal(h.run("copyGrade({statut:'present',correction_id:1,note_finale:0,note_max:20})"),'0/20');
 assert.equal(h.run("copyGrade({statut:'present'})"),'—');
 assert.equal(h.run("copyGrade({statut:'absent'})"),'ABS');
 assert.match(h.run("copyGrade({statut:'present',correction_id:1,etat_groupe:'En attente des camarades'})"),/En attente/);
 assert.match(h.run("copyGrade({statut:'present',correction_id:1,note_finale:12.5,a_revoir:'Revoir'})"),/12,5\/20.*Provisoire/);
});

test('packet upload and interleaved downloads appear on active screens',()=>{
 const h=harness();
 assert.match(h.run('packetPanel()'),/Importer le PDF des copies/);
 h.run("state.fichiers=[{id:'packet',role:'paquet',nom:'Copies.pdf',pages:8}]");
 assert.doesNotMatch(h.run('packetPanel()'),/upload-packet/);
 h.run("state.rendus=[{id:'render',pdf:true,valide:1,intercale:true,final:false}]");
 assert.match(h.run('latestCalibrationRender()'),/name=copies-et-corrections.pdf/);
 h.run("state.rendus[0].final=true;loadFinalNotes=()=>{};renderFinalV2()");
 assert.match(h.node('#main').innerHTML,/Corrections seules/);
 assert.match(h.node('#main').innerHTML,/Copies et corrections intercalées/);
});
