'use strict';

// PR31: four-screen workflow. Technical substeps stay behind the calibration loop.
stages.splice(0,stages.length,'Barème','Calibrage','Correction complète','Résultats');

function fastHeader(title,lede){
 return `<div class="page-head"><div><div class="eyebrow">${esc(state.dossier.classe)}</div><h1>${esc(title)}</h1><p class="lede">${esc(lede)}</p></div><span class="badge">${esc(state.dossier.titre)}</span></div>`;
}
function fastExchange(stage,buttonLabel){
 return `<div class="split"><section class="pane"><div class="pane-head"><h2 class="exchange-title">Consigne à copier dans l’IA</h2></div><div class="pane-body"><textarea id="fast-prompt" readonly placeholder="Chargement…"></textarea></div><div class="pane-foot actions"><button class="primary" id="fast-copy" disabled>Copier</button></div></section><section class="pane"><div class="pane-head"><h2 class="exchange-title">JSON de l’IA</h2></div><div class="pane-body"><textarea id="fast-response" data-stage="${stage}" placeholder="Collez ici le bloc JSON final de l’IA."></textarea></div><div class="pane-foot"><div class="actions"><button class="primary" id="fast-submit">${buttonLabel}</button></div><div id="fast-error" role="alert"></div></div></section></div>`;
}
function bindFastPrompt(stage,mode='echantillon'){
 if(mode==='echantillon'){loadPrompt(stage,'#fast-prompt','#fast-copy');return;}
 const area=$('#fast-prompt'),button=$('#fast-copy');area.value='';button.disabled=true;
 get('/api/prompt?id='+encodeURIComponent(state.dossier.id)+'&etape='+encodeURIComponent(stage)+'&mode='+encodeURIComponent(mode)).then(r=>{
   area.value=r.texte;button.disabled=false;button.onclick=()=>copyText(area.value);
 }).catch(e=>{area.placeholder='Consigne indisponible : '+e.message;button.textContent='Réessayer';button.disabled=false;button.onclick=()=>bindFastPrompt(stage,mode);});
}
async function fastExchangeCommit(stage){
 const text=$('#fast-response').value.trim();
 if(!text)throw new Error('Collez le JSON de l’IA.');
 return post({action:'echange',dossier:state.dossier.id,etape:stage,texte:text,valider:true});
}
function latestCalibrationRender(){
 const renders=(state.rendus||[]).filter(r=>!r.final&&r.pdf&&r.valide!==false);
 if(!renders.length)return '';
 const r=renders[renders.length-1];
 return `<div class="card"><h2>Rendu du dernier lot</h2><object class="pdf-preview" type="application/pdf" data="/file?kind=rendu&id=${r.id}&name=corrections.pdf"></object><div class="actions"><a target="_blank" rel="noopener" href="/file?kind=rendu&id=${r.id}&name=corrections.pdf">Ouvrir le PDF ↗</a></div></div>`;
}
function renderBaremeFast(){
 $('#main').innerHTML=fastHeader('1. Barème','Discutez du barème avec l’IA. Quand il vous convient, l’IA fournit le JSON final à coller ici.')+
 layoutCard('setup')+
 `<div class="card"><h2>Documents côté IA</h2><p>Joignez directement dans la conversation IA : copies, sujet, corrigé éventuel et documents de cours. SmartCorrection ne les renvoie pas à l’IA.</p>${anonymityControl()}</div>`+
 fastExchange('bareme','Valider le barème')+
 (state.grille.length?`<div class="notice success">Barème validé — révision ${state.dossier.revision}.</div>`:'');
 bindLayout('setup');bindAnonymity();bindFastPrompt('bareme');
 $('#fast-submit').onclick=()=>task(async()=>{try{
   await fastExchangeCommit('bareme');state=await get('/api/dossier?id='+state.dossier.id);current=1;renderDossier();toast('Barème validé. Passage au calibrage.');
 }catch(e){$('#fast-error').innerHTML=`<div class="error">${esc(e.message)}</div>`;throw e;}});
}
function renderCalibrationFast(){
 const cal=state.calibrage||{}, selected=state.copies.filter(c=>c.echantillon).map(c=>c.reference);
 const pending=state.copies.filter(c=>c.statut==='present'&&!c.correction_id&&!c.a_revoir);
 const mean=cal.moyenne_estimee==null?'—':cal.moyenne_estimee+'/20';
 $('#main').innerHTML=fastHeader('2. Calibrage','Même écran à chaque lot : JSON → rendu → problèmes → lot suivant, jusqu’à ce que la correction vous convienne.')+
 `<div class="card"><div class="row"><div><strong>Lot</strong><br>${esc(selected.join(', ')||'Premier lot : 5 premières copies')}</div><div><strong>Moyenne estimée</strong><br>${esc(mean)}</div><div><strong>Copies restant à calibrer/corriger</strong><br>${pending.length}</div></div></div>`+
 fastExchange('calibrage','Importer le JSON et afficher le rendu')+
 latestCalibrationRender()+
 `<div class="card"><h2>Problèmes à corriger pour la suite</h2><p class="help">Barème mal appliqué, sévérité, erreurs de calcul, rédaction, symboles… Ces décisions sont cumulées et ajoutées automatiquement aux prochains prompts.</p><textarea id="calibration-problems" placeholder="Ex. : sanctionner davantage les erreurs de calcul ; ne pas enlever deux fois pour la même erreur…"></textarea><div class="actions"><button id="next-batch">Lot suivant</button><button class="primary" id="approve-calibration">La correction me convient</button></div><div id="calibration-error"></div></div>`+
 (state.pretraitement?assignmentPanel(state.pretraitement):'');
 bindFastPrompt('calibrage');bindAssignments();
 $('#fast-submit').onclick=()=>task(async()=>{try{
   await fastExchangeCommit('calibrage');
   state=await get('/api/dossier?id='+state.dossier.id);
   await post({action:'generer',dossier:state.dossier.id,final:false,pdf:true});
   state=await get('/api/dossier?id='+state.dossier.id);renderDossier();toast('Lot importé et rendu généré.');
 }catch(e){$('#fast-error').innerHTML=`<div class="error">${esc(e.message)}</div>`;throw e;}});
 async function saveProblems(){
   const text=$('#calibration-problems').value.trim();
   if(text)await post({action:'brouillon',dossier:state.dossier.id,etape:'calibrage-retours',texte:text});
 }
 $('#next-batch').onclick=()=>task(async()=>{try{
   await saveProblems();state=await get('/api/dossier?id='+state.dossier.id);
   const next=state.copies.filter(c=>c.statut==='present'&&!c.correction_id&&!c.a_revoir).slice(0,5).map(c=>c.reference);
   if(!next.length)throw new Error('Aucune copie non corrigée restante. Validez le calibrage.');
   await post({action:'echantillon',dossier:state.dossier.id,references:next,valider:false});
   state=await get('/api/dossier?id='+state.dossier.id);renderDossier();toast('Lot suivant prêt.');
 }catch(e){$('#calibration-error').innerHTML=`<div class="error">${esc(e.message)}</div>`;throw e;}});
 $('#approve-calibration').onclick=()=>task(async()=>{try{
   await saveProblems();state=await get('/api/dossier?id='+state.dossier.id);
   const refs=state.copies.filter(c=>c.echantillon).map(c=>c.reference);
   if(!refs.length)throw new Error('Importez au moins un lot avant de valider le calibrage.');
   await post({action:'echantillon',dossier:state.dossier.id,references:refs,valider:true});
   state=await get('/api/dossier?id='+state.dossier.id);current=2;renderDossier();toast('Calibrage validé.');
 }catch(e){$('#calibration-error').innerHTML=`<div class="error">${esc(e.message)}</div>`;throw e;}});
}
function renderFullCorrectionFast(){
 const remaining=state.copies.filter(c=>c.statut==='present'&&!c.exclue_final&&(!c.correction_id||c.a_revoir));
 $('#main').innerHTML=fastHeader('3. Correction complète','L’IA applique maintenant le barème et toutes les décisions figées pendant le calibrage à toutes les copies restantes.')+
 `<div class="card"><strong>${remaining.length}</strong> copie(s) restante(s).</div>`+
 fastExchange('correction','Importer toutes les corrections restantes');
 bindFastPrompt('correction','reste');
 $('#fast-submit').onclick=()=>task(async()=>{try{
   await fastExchangeCommit('correction');state=await get('/api/dossier?id='+state.dossier.id);
   const left=state.copies.filter(c=>c.statut==='present'&&!c.exclue_final&&(!c.correction_id||c.a_revoir));
   if(left.length)throw new Error(`${left.length} copie(s) restent à corriger ou à revoir.`);
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
 else renderFinalV2();
 $('#main').insertAdjacentHTML('beforeend',`<div class="footer-nav"><button id="previous" ${current===0?'disabled':''}>← Étape précédente</button>${current<3?'<button id="next">Étape suivante →</button>':'<button id="finish-home">Revenir à mes évaluations</button>'}</div>`);
 $('#previous').onclick=()=>goStep(current-1);if($('#next'))$('#next').onclick=()=>goStep(current+1);if($('#finish-home'))$('#finish-home').onclick=()=>loadHome();
 bindCommon();
};
goStep=async function(i){
 const next=Math.max(0,Math.min(3,i));
 if(next<=current){state=await get('/api/dossier?id='+state.dossier.id);current=next;renderDossier();window.scrollTo(0,0);return;}
 await task(async()=>{
   const latest=await get('/api/dossier?id='+state.dossier.id);
   if(next>0&&!latest.grille.length)throw new Error('Validez d’abord le barème.');
   if(next>1&&!latest.dossier.echantillon_valide)throw new Error('Validez d’abord le calibrage.');
   if(next>2){
     const left=latest.copies.filter(c=>c.statut==='present'&&!c.exclue_final&&(!c.correction_id||c.a_revoir));
     if(left.length)throw new Error(`${left.length} copie(s) restent à corriger ou à revoir.`);
   }
   state=latest;current=next;renderDossier();window.scrollTo(0,0);
 });
};
