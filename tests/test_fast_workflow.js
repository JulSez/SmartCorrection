const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function harness() {
 const nodes=new Map();
 const node=s=>{if(!nodes.has(s))nodes.set(s,{content:'csrf',value:'',dataset:{},innerHTML:'',textContent:'',disabled:false,insertAdjacentHTML(_p,h){this.innerHTML+=h;}});return nodes.get(s);};
 const context=vm.createContext({document:{querySelector:node,querySelectorAll:()=>[]},fetch:()=>new Promise(()=>{}),setTimeout:()=>1,clearTimeout(){},window:{scrollTo(){}},navigator:{clipboard:{writeText:async()=>{}}}});
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

test('new calibration remarks do not silently approve old grades',async()=>{
 const h=harness(),calls=[];
 h.run(`bindFastPrompt=()=>{};bindAssignments=()=>{};bindCopyControls=()=>{};renderDossier=()=>{};
 state.copies=[{reference:'C001',statut:'present',pages:[1],echantillon:1,correction_id:1}];
 get=async()=>state;post=async data=>record(data);current=1;renderCalibrationFast();`);
 h.context.record=x=>calls.push(JSON.parse(JSON.stringify(x)));
 h.node('#calibration-problems').value='Ne pas pénaliser deux fois';
 await h.node('#approve-calibration').onclick();
 assert.deepEqual(calls.map(c=>c.action),['brouillon']);
 assert.equal(h.run('current'),1);
 assert.match(h.node('#toast').textContent,/lot révisé/);
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
