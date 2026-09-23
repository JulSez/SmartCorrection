'use strict';

// Active four-screen workflow. Legacy screens are compatibility helpers only.
stages.splice(0,stages.length,'Barème','Calibrage','Correction complète','Résultats');

let fastDraftPending=null,fastDraftTimer=null,fastDraftWrites=Promise.resolve();
function queueFastDraft(entry){
 const write=fastDraftWrites.catch(()=>{}).then(()=>post({action:'brouillon',...entry}));
 fastDraftWrites=write;
 return write;
}
async function flushFastDraft(){
 clearTimeout(fastDraftTimer);
 if(fastDraftPending){const entry=fastDraftPending;fastDraftPending=null;await queueFastDraft(entry);}
 else await fastDraftWrites;
}
function bindFastDraft(stage){
 const area=$('#fast-response'),key=state.dossier.id+':'+stage;
 area.value=drafts.has(key)?drafts.get(key):(state.brouillons?.[stage]??'');
 area.oninput=()=>{
  drafts.set(key,area.value);$('#save-status').textContent='Brouillon…';
  fastDraftPending={dossier:state.dossier.id,etape:stage,texte:area.value};
  clearTimeout(fastDraftTimer);
  fastDraftTimer=setTimeout(()=>flushFastDraft().then(()=>$('#save-status').textContent='Brouillon enregistré').catch(e=>toast('Brouillon non enregistré : '+e.message,true)),500);
 };
}
function bindCopyControls(){
 document.querySelectorAll('[data-final-copy]').forEach(box=>box.onchange=()=>toggleFinalCopy(box));
 document.querySelectorAll('[data-review]').forEach(b=>b.onclick=()=>task(async()=>{
  await post({action:'revue',dossier:state.dossier.id,reference:b.dataset.review});
  state=await get('/api/dossier?id='+state.dossier.id);renderDossier();
 }));
 bindGroups();
}
function copyControls(){
 return `<details class="card"><summary>Copies incluses et points à revoir</summary><p class="help">Décochez pour exclure une copie des documents finaux, sans supprimer sa correction.</p>${copyTable(state.copies,false,true)}</details>`+groupsPanel();
}
function calibrationCandidates(copies){
 const eligible=copies.filter(c=>c.statut==='present'&&!c.exclue_final&&(!c.correction_id||c.a_revoir));
 return [...eligible.filter(c=>!c.correction_id),...eligible.filter(c=>c.correction_id)].slice(0,5).map(c=>c.reference);
}
function fastHeader(title,lede){
 return `<div class="page-head"><div><div class="eyebrow">${esc(state.dossier.classe)}</div><h1>${esc(title)}</h1><p class="lede">${esc(lede)}</p></div><span class="badge">${esc(state.dossier.titre)}</span></div>`;
}
function fastExchange(stage,buttonLabel){
 return `<div class="split"><section class="pane"><div class="pane-head"><h2 class="exchange-title">Consigne à copier dans l’IA</h2></div><div class="pane-body"><textarea id="fast-prompt" readonly placeholder="Chargement…"></textarea></div><div class="pane-foot actions"><button class="primary" id="fast-copy" disabled>Copier</button></div></section><section class="pane"><div class="pane-head"><h2 class="exchange-title">JSON de l’IA</h2></div><div class="pane-body"><textarea id="fast-response" data-stage="${stage}" placeholder="Collez ici le bloc JSON final de l’IA."></textarea></div><div class="pane-foot"><div class="actions"><button class="primary" id="fast-submit">${buttonLabel}</button></div><div id="fast-error" role="alert"></div></div></section></div>`;
}
function bindFastPrompt(stage,mode='echantillon'){
 bindFastDraft(stage);
 if(mode==='echantillon'){loadPrompt(stage,'#fast-prompt','#fast-copy');return;}
 const area=$('#fast-prompt'),button=$('#fast-copy');area.value='';button.disabled=true;
 get('/api/prompt?id='+encodeURIComponent(state.dossier.id)+'&etape='+encodeURIComponent(stage)+'&mode='+encodeURIComponent(mode)).then(r=>{
   area.value=r.texte;button.disabled=false;button.onclick=()=>copyText(area.value);
 }).catch(e=>{area.placeholder='Consigne indisponible : '+e.message;button.textContent='Réessayer';button.disabled=false;button.onclick=()=>bindFastPrompt(stage,mode);});
}
async function fastExchangeCommit(stage){
 const text=$('#fast-response').value.trim();
 if(!text)throw new Error('Collez le JSON de l’IA.');
 await flushFastDraft();
 const r=await post({action:'echange',dossier:state.dossier.id,etape:stage,texte:text,valider:true});
 drafts.delete(state.dossier.id+':'+stage);return r;
}
function latestCalibrationRender(){
 const renders=(state.rendus||[]).filter(r=>!r.final&&r.pdf&&Boolean(r.valide));
 if(!renders.length)return '';
 const r=renders[0],name=r.intercale?'copies-et-corrections.pdf':'corrections.pdf';
 return `<div class="card"><h2>Rendu du dernier lot</h2><object class="pdf-preview" type="application/pdf" data="/file?kind=rendu&id=${r.id}&name=${name}"></object><div class="actions"><a target="_blank" rel="noopener" href="/file?kind=rendu&id=${r.id}&name=${name}">Ouvrir le PDF ↗</a></div></div>`;
}
function packetPanel(){
 const packet=(state.fichiers||[]).find(f=>f.role==='paquet');
 return packet?`<div class="card"><h2>PDF des copies</h2><p>${esc(packet.nom)} · ${packet.pages} pages</p><a target="_blank" rel="noopener" href="/file?kind=source&id=${packet.id}">Ouvrir le paquet ↗</a></div>`:
 `<div class="card"><h2>PDF des copies</h2><p class="help">Importez le paquet pour afficher les pages des élèves avec leurs fiches. Joignez-le aussi séparément dans l’IA.</p><input type="file" id="packet-file" accept="application/pdf,.pdf"><button id="upload-packet">Importer le PDF des copies</button></div>`;
}
function bindPacket(){
 const button=$('#upload-packet');if(!button)return;
 button.onclick=()=>task(async()=>{
  const file=$('#packet-file').files[0];if(!file)throw Error('Choisir le PDF des copies.');
  await post({action:'upload',dossier:state.dossier.id,role:'paquet',nom:file.name,contenu:await fileBase64(file)});
  state=await get('/api/dossier?id='+state.dossier.id);renderDossier();toast('PDF des copies importé.');
 });
}
function renderBaremeFast(){
 $('#main').innerHTML=fastHeader('1. Barème','Discutez du barème avec l’IA. Quand il vous convient, l’IA fournit le JSON final à coller ici.')+
 layoutCard('setup')+packetPanel()+
 `<div class="card"><h2>Documents côté IA</h2><p>Joignez directement dans la conversation IA : copies, sujet, corrigé éventuel et documents de cours. SmartCorrection ne les renvoie pas à l’IA.</p>${anonymityControl()}</div>`+
 fastExchange('bareme','Valider et voir le barème')+
 (state.grille.length?`<div class="notice success">Barème validé — révision ${state.dossier.revision}.</div>`:'');
 bindLayout('setup');bindPacket();bindAnonymity();bindFastPrompt('bareme');
 $('#fast-submit').onclick=()=>task(async()=>{try{
   await fastExchangeCommit('bareme');state=await get('/api/dossier?id='+state.dossier.id);renderDossier();showGridPreviewV2();toast('Barème validé. Vérifiez le PDF, puis passez au calibrage.');
 }catch(e){$('#fast-error').innerHTML=`<div class="error">${esc(e.message)}</div>`;throw e;}});
}
function renderCalibrationFast(){
 const cal=state.calibrage||{}, selected=state.copies.filter(c=>c.echantillon).map(c=>c.reference);
 const pending=state.copies.filter(c=>c.statut==='present'&&!c.exclue_final&&(!c.correction_id||c.a_revoir));
 const mean=cal.moyenne_estimee==null?'—':cal.moyenne_estimee+'/20';
 $('#main').innerHTML=fastHeader('2. Calibrage','Même écran à chaque lot : JSON → rendu → lot suivant, jusqu’à ce que la correction vous convienne.')+
 `<div class="card"><div class="row"><div><strong>Lot</strong><br>${esc(selected.join(', ')||'Premier lot : 5 premières copies')}</div><div><strong>Moyenne estimée</strong><br>${esc(mean)}</div><div><strong>Copies restant à calibrer/corriger</strong><br>${pending.length}</div></div></div>`+
 fastExchange('calibrage','Importer le JSON et afficher le rendu')+
 latestCalibrationRender()+
 `<div class="actions"><button id="next-batch">Lot suivant</button></div><div id="calibration-error"></div>`+
 (state.pretraitement?assignmentPanel(state.pretraitement):'')+copyControls();
 bindFastPrompt('calibrage');bindAssignments();bindCopyControls();
 $('#fast-submit').onclick=()=>task(async()=>{try{
   await fastExchangeCommit('calibrage');
   state=await get('/api/dossier?id='+state.dossier.id);
   await post({action:'generer',dossier:state.dossier.id,final:false,pdf:true});
   state=await get('/api/dossier?id='+state.dossier.id);renderDossier();toast('Lot importé et rendu généré.');
 }catch(e){$('#fast-error').innerHTML=`<div class="error">${esc(e.message)}</div>`;throw e;}});
 $('#next-batch').onclick=()=>task(async()=>{try{
   state=await get('/api/dossier?id='+state.dossier.id);
   const next=calibrationCandidates(state.copies);
   if(!next.length)throw new Error('Aucune copie non corrigée restante. Passez à l’étape suivante.');
   await post({action:'echantillon',dossier:state.dossier.id,references:next,valider:false});
   state=await get('/api/dossier?id='+state.dossier.id);renderDossier();toast('Lot suivant prêt.');
 }catch(e){$('#calibration-error').innerHTML=`<div class="error">${esc(e.message)}</div>`;throw e;}});

}
function renderFullCorrectionFast(){
 const remaining=state.copies.filter(c=>c.statut==='present'&&!c.exclue_final&&(!c.correction_id||c.a_revoir));
 $('#main').innerHTML=fastHeader('3. Correction complète','L’IA applique maintenant le barème et toutes les décisions figées pendant le calibrage à toutes les copies restantes.')+
 `<div class="card"><strong>${remaining.length}</strong> copie(s) restante(s).</div>`+
 (remaining.length?fastExchange('correction','Importer les corrections'):'<div class="notice success">Toutes les copies incluses sont corrigées. Passez aux résultats.</div>')+copyControls();
 bindCopyControls();
 if(!remaining.length)return;
 bindFastPrompt('correction','reste');
 $('#fast-submit').onclick=()=>task(async()=>{try{
   await fastExchangeCommit('correction');state=await get('/api/dossier?id='+state.dossier.id);
   const left=state.copies.filter(c=>c.statut==='present'&&!c.exclue_final&&(!c.correction_id||c.a_revoir));
   if(left.length){renderDossier();toast(`${left.length} copie(s) restent à corriger ou à revoir. La consigne est actualisée.`);return;}
   current=3;renderDossier();toast('Toutes les corrections sont importées.');
 }catch(e){$('#fast-error').innerHTML=`<div class="error">${esc(e.message)}</div>`;throw e;}});
}
function resumeStep(){
 if(state.dossier.termine)return 3;
 if(!state.grille.length)return 0;
 if(!state.dossier.echantillon_valide)return 1;
 const left=state.copies.filter(c=>c.statut==='present'&&!c.exclue_final&&(!c.correction_id||c.a_revoir));
 return left.length?2:3;
}
renderDossier=function(){
 lastPreview=null;previewText='';$('#breadcrumb').textContent=state.dossier.classe+' / '+state.dossier.titre;
 const left=state.copies.filter(c=>c.statut==='present'&&!c.exclue_final&&(!c.correction_id||c.a_revoir));
 const done=[!!state.grille.length,!!state.dossier.echantillon_valide,state.dossier.echantillon_valide&&!left.length,!!state.dossier.termine];
 $('#dossier-nav').innerHTML=`<div class="nav-caption">Parcours de correction</div><nav class="steps" aria-label="Étapes">${stages.map((s,i)=>`<button class="step ${i===current?'active':''} ${done[i]?'done':''}" data-step="${i}"><span class="num">${done[i]?'✓':i+1}</span>${s}</button>`).join('')}</nav>`;
 document.querySelectorAll('[data-step]').forEach(b=>b.onclick=()=>goStep(Number(b.dataset.step)));
 if(current===0)renderBaremeFast();
 else if(current===1)renderCalibrationFast();
 else if(current===2)renderFullCorrectionFast();
 else {renderFinalV2();$('#main').insertAdjacentHTML('beforeend',copyControls());bindCopyControls();}
 $('#main').insertAdjacentHTML('beforeend',`<div class="footer-nav"><button id="previous" ${current===0?'disabled':''}>← Étape précédente</button>${current<3?'<button id="next">Étape suivante →</button>':'<button id="finish-home">Revenir à mes évaluations</button>'}</div>`);
 $('#previous').onclick=()=>goStep(current-1);if($('#next'))$('#next').onclick=()=>goStep(current+1);if($('#finish-home'))$('#finish-home').onclick=()=>loadHome();
 bindCommon();
};
goStep=async function(i){
 const next=Math.max(0,Math.min(3,i));
 await task(async()=>{
   await flushFastDraft();
   let latest=await get('/api/dossier?id='+state.dossier.id);
   if(next>current){
    if(next>0&&!latest.grille.length)throw new Error('Validez d’abord le barème.');
    if(next>1&&!latest.dossier.echantillon_valide){
     const selected=latest.copies.filter(c=>c.echantillon);
     const refs=selected.filter(c=>!c.exclue_final).map(c=>c.reference);
     if(!refs.length)throw new Error('Importez au moins un lot avant de passer à la suite.');
     if(refs.length!==selected.length)await post({action:'echantillon',dossier:latest.dossier.id,references:refs,valider:false});
     await post({action:'echantillon',dossier:latest.dossier.id,references:refs,valider:true});
     latest=await get('/api/dossier?id='+latest.dossier.id);
    }
    if(next>2){
     const left=latest.copies.filter(c=>c.statut==='present'&&!c.exclue_final&&(!c.correction_id||c.a_revoir));
     if(left.length)throw new Error(`${left.length} copie(s) restent à corriger ou à revoir.`);
    }
   }
   state=latest;current=next;renderDossier();window.scrollTo(0,0);
 });
};
