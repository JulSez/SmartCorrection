'use strict';

// Compact workflow layered on the stable local UI primitives from app.js.
stages.splice(0,stages.length,
 'Format et documents','Corrigés','Grille','Prétraiter les copies','Tester la correction','Corriger le lot','Résultats et retour');

const v2RenderPreviewBase=renderPreview;

function formatOptions(selected){
 return ['A6','A5','A4'].map(x=>`<option value="${x}" ${selected===x?'selected':''}>${x} portrait</option>`).join('');
}
function formatsCard(extra=''){
 const f=state.formats||{correction:'A6',corrige:'A6'};
 return `<div class="card"><h2>Format du document</h2><p class="help">Les deux zones sont réglées séparément. A6 portrait est le format par défaut.</p><div class="row"><div class="field"><label for="format-correction">Feuille de correction</label><select id="format-correction">${formatOptions(f.correction)}</select></div><div class="field"><label for="format-corrige">Corrigé</label><select id="format-corrige">${formatOptions(f.corrige)}</select></div></div><div class="actions"><button id="save-formats">Enregistrer le format</button>${extra}</div></div>`;
}
function bindFormats(afterSave=null){
 const button=$('#save-formats');if(!button)return;
 button.onclick=()=>task(async()=>{
  await post({action:'formats',dossier:state.dossier.id,correction:$('#format-correction').value,corrige:$('#format-corrige').value});
  state=await get('/api/dossier?id='+state.dossier.id);
  renderDossier();toast('Format enregistré.');
  if(afterSave)afterSave();
 });
}
function showCorrigePreview(){
 const url='/api/corrige-preview?id='+encodeURIComponent(state.dossier.id);
 showModal(`<div class="eyebrow">Corrigés validés</div><h1>Aperçu du corrigé</h1><p class="lede">Le PDF utilise le format choisi pour la zone Corrigé.</p><div class="actions"><a href="${url}" target="_blank" rel="noopener">Ouvrir dans un onglet ↗</a></div><iframe title="Aperçu du corrigé" class="pdf-viewer" src="${url}"></iframe>`,true);
}
function showGridPreviewV2(){
 const url='/api/grid-preview?id='+encodeURIComponent(state.dossier.id)+'&revision='+encodeURIComponent(state.dossier.revision);
 showModal(`<div class="eyebrow">Grille enregistrée</div><h1>Correction vide + corrigé</h1><p class="lede">Vérifiez la densité réelle du document avant de traiter les copies. Vous pouvez changer les deux formats puis rouvrir cet aperçu.</p><div class="actions"><a href="${url}" target="_blank" rel="noopener">Ouvrir dans un onglet ↗</a></div><iframe title="Aperçu de la feuille de correction et du corrigé" class="pdf-viewer" src="${url}"></iframe>`,true);
}

resumeStep=function(){
 const present=state.copies.filter(c=>c.statut==='present'&&!c.exclue_final);
 const lotDone=present.length&&present.every(c=>c.correction_id&&!c.a_revoir);
 if(state.dossier.termine)return 6;
 if(!state.fichiers.length)return 0;
 if(!state.corriges_valides)return 1;
 if(!state.grille.length)return 2;
 if(!state.copies.length)return 3;
 if(!state.dossier.echantillon_valide)return 4;
 if(!lotDone)return 5;
 return 6;
};

renderSetup=function(){
 $('#main').innerHTML=header('Format et documents','Choisissez d’abord la taille visée, ajoutez les documents, puis ouvrez la conversation avec l’IA.')+
 formatsCard()+`<div class="split"><div class="card"><h2>Documents de l’évaluation</h2><p class="help">Le paquet reste un seul PDF. Ajoutez le sujet et les documents utiles ; ils restent sur cet ordinateur.</p>${filesHtml()}<div class="row"><div class="field"><label for="file-role">Document à ajouter</label><select id="file-role"><option value="paquet">Paquet de copies</option><option value="sujet">Sujet</option><option value="corrige">Corrigé existant</option><option value="cours">Cours / savoir-faire</option><option value="modele">Modèle de rédaction</option></select></div></div><div class="field"><label for="pdf-file">Choisir un PDF</label><input type="file" id="pdf-file" accept="application/pdf,.pdf"></div><button id="upload-file" class="primary">Ajouter le document</button></div><div class="card"><h2 class="exchange-title">Consigne à copier dans l’IA</h2><p class="help">La taille choisie est incluse dans les consignes envoyées à l’IA.</p><textarea id="opening" aria-label="Consigne de démarrage pour l’IA" readonly placeholder="Chargement de la consigne…"></textarea><div class="actions"><button class="primary" id="copy-opening" disabled>Copier</button></div><p class="help">Gardez cette conversation pour toutes les étapes.</p></div></div><div class="notice">Les consignes générales et celles de cette classe sont jointes automatiquement aux messages.</div><button id="view-policies">Voir les consignes mémorisées</button>`;
 bindFormats();
 $('#upload-file').onclick=()=>task(async()=>{const f=$('#pdf-file').files[0];if(!f)throw new Error('Choisir un fichier PDF.');const content=await fileBase64(f);await post({action:'upload',dossier:state.dossier.id,role:$('#file-role').value,nom:f.name,contenu:content});state=await get('/api/dossier?id='+state.dossier.id);renderDossier();toast('Document ajouté.');});
 loadPrompt('ouverture','#opening','#copy-opening');$('#view-policies').onclick=policiesModal;
};

function renderCorrigesV2(){
 $('#main').innerHTML=header('Tous les corrigés','Demandez toutes les versions d’un coup, collez le JSON puis vérifiez le rendu dans la taille choisie.')+
 exchangePanel('corriges','Tous les corrigés au format JSON','Une seule réponse JSON contenant toutes les versions et leur corrigé LaTeX.')+
 (state.corriges_valides?`<div class="card"><h2>Corrigés enregistrés</h2>${table(['Version','État'],state.corriges.map(c=>[c.version,'Corrigé enregistré']))}<div class="actions"><button id="preview-corriges">Voir le corrigé au bon format</button></div></div>`:'');
 if($('#preview-corriges'))$('#preview-corriges').onclick=showCorrigePreview;
}

renderGrid=function(){
 $('#main').innerHTML=header('Grille de correction','Discutez du barème avec l’IA, enregistrez-le, puis validez visuellement la feuille vide avec le corrigé.')+
 (state.dossier.revision?`<div class="notice ${state.copies.some(c=>c.correction_id)?'warning':''}">Grille ${state.dossier.revision} enregistrée. Une nouvelle validation crée une nouvelle révision.</div>`:'')+
 exchangePanel('grille','Grille au format JSON','Les versions et corrigés sont déjà fixés. Ici vous ne discutez que la grille de correction.')+
 (state.grille.length?`<details class="card" open><summary>Grille enregistrée</summary>${table(['Version','Ex. / Q.','Item','Critère','Points'],state.grille.map(i=>[i.version||'Commune',i.exercice+' / '+i.question,i.code,i.description,i.bareme_max]))}</details>`:'')+
 formatsCard(state.grille.length?'<button class="primary" id="preview-grid-v2">Voir Correction vide + Corrigé</button>':'');
 bindFormats();
 if($('#preview-grid-v2'))$('#preview-grid-v2').onclick=showGridPreviewV2;
};

renderPreview=function(stage,r,text){
 if(stage!=='corriges')return v2RenderPreviewBase(stage,r,text);
 text=responseBody(text,stage);const data=JSON.parse(text);
 $('#preview').innerHTML='<div class="card"><h2>Relire les corrigés</h2>'+table(['Version','Contenu'],data.corriges.map(c=>[c.version,(c.corrige_latex||'').length+' caractères']))+`<p class="success">${r.corriges.length} version(s) vérifiée(s).</p></div>`;
};

submitResponse=async function(commit){
 const stage=$('#response').dataset.stage,text=$('#response').value;
 if(commit&&(!lastPreview||text!==previewText)){toast('Vérifiez cette réponse avant de la valider.',true);return;}
 await task(async()=>{
  const req={action:stage.startsWith('corrige:')?'corrige':'echange',dossier:state.dossier.id,etape:stage,texte:text,valider:commit};
  if(stage.startsWith('corrige:')){req.version=stage.slice(8);req.revision=state.dossier.revision;}
  if(commit)clearTimeout(draftTimer);
  const r=await post(req);$('#exchange-error').innerHTML='';
  if(commit){
   clearTimeout(draftTimer);drafts.delete(state.dossier.id+':'+stage);state=await get('/api/dossier?id='+state.dossier.id);
   if(stage==='corriges'){current=2;renderDossier();window.scrollTo(0,0);toast('Tous les corrigés sont enregistrés.');showCorrigePreview();return;}
   if(stage==='grille'){current=2;renderDossier();window.scrollTo(0,0);toast('Grille enregistrée. Vérifiez maintenant le rendu.');showGridPreviewV2();return;}
   if(stage==='copies')current=4;
   renderDossier();window.scrollTo(0,0);toast(stage==='retour'?'Consignes remplacées pour les prochaines évaluations.':'Résultat enregistré.');
  }else{lastPreview=r;previewText=text;renderPreview(stage,r,text);$('#save-response').disabled=false;delete $('#save-response').dataset.wasDisabled;}
 },{response:true});
};

async function loadFinalNotes(renderId){
 const box=$('#final-notes-table');if(!box)return;
 try{
  const response=await fetch(`/file?kind=rendu&id=${encodeURIComponent(renderId)}&name=notes.json`);if(!response.ok)throw new Error('Notes indisponibles');
  const data=await response.json();let rows=[...(data.fiches||data.notes||[])];
  rows.sort((a,b)=>{if(a.nom==null&&b.nom!=null)return 1;if(a.nom!=null&&b.nom==null)return -1;return String(a.nom||'').localeCompare(String(b.nom||''),'fr',{sensitivity:'base'})||String(a.prenom||'').localeCompare(String(b.prenom||''),'fr',{sensitivity:'base'});});
  const grouped=rows.some(x=>x.note_groupe!=null&&Number(data.config?.note_groupe?.max||0)>0);
  const score=x=>x.statut==='absent'?'ABS':(x==null||x.note_finale==null?'--':String(x.note_finale).replace('.',','));
  box.innerHTML=grouped?table(['Nom','Prénom','Individuelle','Groupe','Finale'],rows.map(x=>[x.nom||x.label||'Copie non identifiée',x.prenom||'',x.statut==='absent'?'ABS':x.note_individuelle??'--',x.statut==='absent'?'ABS':x.note_groupe??'--',score(x)])):table(['Nom','Prénom','Note'],rows.map(x=>[x.nom||x.label||'Copie non identifiée',x.prenom||'',score(x)]));
 }catch(e){box.innerHTML=`<div class="error">${esc(e.message)}</div>`;}
}

function renderFinalV2(){
 const final=state.rendus.find(r=>r.final&&r.valide);
 const links=final&&final.pdf?`<div class="actions"><a target="_blank" rel="noopener" href="/file?kind=rendu&id=${final.id}&name=corrections.pdf" download>Corrections seules ↓</a>${final.intercale?`<a href="/file?kind=rendu&id=${final.id}&name=copies-et-corrections.pdf" download>Copies et corrections intercalées ↓</a>`:''}<a target="_blank" rel="noopener" href="/file?kind=rendu&id=${final.id}&name=notes.pdf">Relevé PDF ↗</a><a target="_blank" rel="noopener" href="/file?kind=rendu&id=${final.id}&name=notes.csv">Notes CSV ↗</a></div><div id="final-notes-table"><p class="help">Chargement des notes…</p></div>`:'<p class="help">Créez le document final pour afficher ici les liens et le tableau des notes.</p>';
 $('#main').innerHTML=header('Résultats et retour','Le document final, le tableau des notes et le retour d’expérience sont réunis au même endroit.')+
 `<div class="card"><h2>Document final et notes</h2>${links}<div class="actions"><button class="primary" id="generate-final-v2">${final?'Régénérer le document final':'Créer le document final'}</button></div><div id="render-error"></div></div>`+
 (state.dossier.termine?exchangePanel('retour','Nouvelles consignes au format JSON','Terminez par le retour d’expérience : deux textes complets, général et classe.'):'<div class="notice warning">Créez le document final avant le retour d’expérience.</div>')+
 `<button id="view-policies">Consulter les consignes et leur historique</button>`;
 $('#generate-final-v2').onclick=()=>task(async()=>{try{await post({action:'generer',dossier:state.dossier.id,final:true,pdf:true});state=await get('/api/dossier?id='+state.dossier.id);renderDossier();toast('Document final créé.');}catch(e){$('#render-error').innerHTML=`<div class="error">${esc(e.message)}</div>`;throw e;}});
 $('#view-policies').onclick=policiesModal;
 if(final)loadFinalNotes(final.id);
}

renderDossier=function(){
 lastPreview=null;previewText='';$('#breadcrumb').textContent=state.dossier.classe+' / '+state.dossier.titre;
 const present=state.copies.filter(c=>c.statut==='present'&&!c.exclue_final),lotDone=present.length&&present.every(c=>c.correction_id&&!c.a_revoir);
 const done=[state.fichiers.some(f=>f.role==='sujet'),state.corriges_valides,state.grille.length,state.copies.length,state.dossier.echantillon_valide,lotDone,state.dossier.termine];
 $('#dossier-nav').innerHTML=`<div class="nav-caption">Parcours de correction</div><nav class="steps" aria-label="Étapes">${stages.map((s,i)=>`<button class="step ${i===current?'active':''} ${done[i]?'done':''}" data-step="${i}" ${i===current?'aria-current="step"':''}><span class="num">${done[i]?'✓':i+1}</span>${s}</button>`).join('')}</nav>`;
 document.querySelectorAll('[data-step]').forEach(b=>b.onclick=()=>goStep(Number(b.dataset.step)));
 if(current===0)renderSetup();
 else if(current===1)renderCorrigesV2();
 else if(current===2)renderGrid();
 else if(current===3)renderInventory();
 else if(current===4)renderCorrection(false);
 else if(current===5){renderCorrection(true);const gen=$('#generate-pdf');if(gen)gen.closest('.card')?.remove();}
 else renderFinalV2();
 $('#main').insertAdjacentHTML('beforeend',`<div class="footer-nav"><button id="previous" ${current===0?'disabled':''}>← Étape précédente</button>${current<6?'<button id="next">Étape suivante →</button>':'<button id="finish-home">Revenir à mes évaluations</button>'}</div>`);
 $('#previous').onclick=()=>goStep(current-1);if($('#next'))$('#next').onclick=()=>goStep(current+1);if($('#finish-home'))$('#finish-home').onclick=()=>loadHome();
 bindCommon();
};

goStep=async function(i){
 const next=Math.max(0,Math.min(6,i));
 if(next<=current){state=await get('/api/dossier?id='+state.dossier.id);current=next;renderDossier();window.scrollTo(0,0);return;}
 const references=current===4?sampleRefs():null;
 await task(async()=>{
  let latest=await get('/api/dossier?id='+state.dossier.id);
  if(next>0&&!latest.fichiers.some(f=>f.role==='sujet'))throw new Error('Ajoutez le sujet avant de demander les corrigés.');
  if(next>1&&!latest.corriges_valides)throw new Error('Validez tous les corrigés avant de passer à la grille.');
  if(next>2&&!latest.grille.length)throw new Error('Validez la grille et son aperçu avant de prétraiter les copies.');
  if(next>3&&!latest.copies.length)throw new Error('Enregistrez le prétraitement du paquet avant de corriger.');
  if(next>4&&(current===4||!latest.dossier.echantillon_valide)){
   const selected=references??latest.copies.filter(c=>c.echantillon).map(c=>c.reference);
   await post({action:'echantillon',dossier:latest.dossier.id,references:selected,valider:true});
   latest=await get('/api/dossier?id='+latest.dossier.id);
  }
  if(next>5){const pending=latest.copies.filter(c=>c.statut==='present'&&!c.exclue_final&&(!c.correction_id||c.a_revoir));if(pending.length)throw new Error(`${pending.length} copie(s) restent à corriger ou à revoir.`);}
  state=latest;current=next;renderDossier();window.scrollTo(0,0);
 });
};
