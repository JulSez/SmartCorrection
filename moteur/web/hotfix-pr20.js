'use strict';

// PR20: documents stay in the IA conversation; preprocessing is part of step 1.
stages.splice(0,stages.length,
 'Préparation','Corrigés','Grille','Tester la correction','Corriger le lot','Résultats et retour');

const pr20RenderPreviewBase=renderPreview;
renderPreview=function(stage,r,text){
 if(stage!=='pretraitement')return pr20RenderPreviewBase(stage,r,text);
 $('#preview').innerHTML=`<div class="card"><h2>Relire le prétraitement</h2><p class="success">${r.copies} copie(s) repérée(s) · ${r.pages_ignorees} page(s) ignorée(s).</p><p class="help">Ce repérage sera appliqué automatiquement dès que la grille sera validée.</p></div>`;
};

renderSetup=function(){
 const prep=state.pretraitement;
 $('#main').innerHTML=`<div class="page-head"><div><div class="eyebrow">${esc(state.dossier.classe)}</div><h1>Étape 1/6</h1><p class="lede">Choisissez le format, préparez les documents puis lancez la première lecture des copies avec l’IA.</p></div><span class="badge">${esc(state.dossier.titre)}</span></div>`+
 layoutCard('setup')+
 `<div class="card"><div class="eyebrow">2. Préparation des documents</div><h2>Documents à joindre à l’IA</h2><p class="help">Aucun upload dans SmartCorrection. Joignez directement ces fichiers dans la conversation IA.</p><ul class="doc-list"><li><span>▤</span><div class="grow"><strong>Copies</strong><small>Le paquet PDF complet, non découpé.</small></div></li><li><span>▤</span><div class="grow"><strong>Sujet</strong><small>Le sujet de l’évaluation avec toutes ses versions.</small></div></li><li><span>▤</span><div class="grow"><strong>Corrigé éventuel</strong><small>Seulement s’il existe déjà.</small></div></li><li><span>▤</span><div class="grow"><strong>Documents de cours de référence</strong><small>Savoir-faire, cours, modèles de rédaction ou documents utiles.</small></div></li></ul></div>`+
 `<div class="card"><div class="eyebrow">3. Initialisation de l’IA</div><h2>Première lecture des copies</h2><p class="help">Joignez les documents ci-dessus, puis copiez cette consigne. L’IA repère immédiatement les copies et fait une première lecture transversale des erreurs communes ; elle réutilisera cette lecture pour le corrigé et la grille.</p><textarea id="opening" aria-label="Consigne de démarrage pour l’IA" readonly placeholder="Chargement de la consigne…"></textarea><div class="actions"><button class="primary" id="copy-opening" disabled>Copier</button></div><p class="help">Gardez cette même conversation pour toutes les étapes suivantes.</p></div>`+
 exchangePanel('pretraitement','Prétraitement des copies au format JSON','Après la première lecture, demandez à l’IA le JSON de repérage des copies puis collez-le ici. Aucun PDF n’est importé dans SmartCorrection.')+
 (prep?`<div class="notice success">Prétraitement enregistré : ${prep.copies.length} copie(s). Il sera appliqué automatiquement à la validation de la grille.</div>`:'')+
 `<div class="notice">Les consignes générales et celles de cette classe sont intégrées automatiquement au texte copié.</div><button id="view-policies">Voir les consignes mémorisées</button>`;
 bindLayout('setup');
 loadPrompt('ouverture','#opening','#copy-opening');
 $('#view-policies').onclick=policiesModal;
};

resumeStep=function(){
 const present=state.copies.filter(c=>c.statut==='present'&&!c.exclue_final);
 const lotDone=present.length&&present.every(c=>c.correction_id&&!c.a_revoir);
 if(state.dossier.termine)return 5;
 if(!state.pretraitement)return 0;
 if(!state.corriges_valides)return 1;
 if(!state.grille.length)return 2;
 if(!state.copies.length)return 0;
 if(!state.dossier.echantillon_valide)return 3;
 if(!lotDone)return 4;
 return 5;
};

renderDossier=function(){
 lastPreview=null;previewText='';$('#breadcrumb').textContent=state.dossier.classe+' / '+state.dossier.titre;
 const present=state.copies.filter(c=>c.statut==='present'&&!c.exclue_final),lotDone=present.length&&present.every(c=>c.correction_id&&!c.a_revoir);
 const done=[!!state.pretraitement,state.corriges_valides,state.grille.length&&state.copies.length,state.dossier.echantillon_valide,lotDone,state.dossier.termine];
 $('#dossier-nav').innerHTML=`<div class="nav-caption">Parcours de correction</div><nav class="steps" aria-label="Étapes">${stages.map((s,i)=>`<button class="step ${i===current?'active':''} ${done[i]?'done':''}" data-step="${i}" ${i===current?'aria-current="step"':''}><span class="num">${done[i]?'✓':i+1}</span>${s}</button>`).join('')}</nav>`;
 document.querySelectorAll('[data-step]').forEach(b=>b.onclick=()=>goStep(Number(b.dataset.step)));
 if(current===0)renderSetup();
 else if(current===1)renderCorrigesV2();
 else if(current===2)renderGrid();
 else if(current===3)renderCorrection(false);
 else if(current===4){renderCorrection(true);const gen=$('#generate-pdf');if(gen)gen.closest('.card')?.remove();}
 else renderFinalV2();
 $('#main').insertAdjacentHTML('beforeend',`<div class="footer-nav"><button id="previous" ${current===0?'disabled':''}>← Étape précédente</button>${current<5?'<button id="next">Étape suivante →</button>':'<button id="finish-home">Revenir à mes évaluations</button>'}</div>`);
 $('#previous').onclick=()=>goStep(current-1);if($('#next'))$('#next').onclick=()=>goStep(current+1);if($('#finish-home'))$('#finish-home').onclick=()=>loadHome();
 bindCommon();
};

goStep=async function(i){
 const next=Math.max(0,Math.min(5,i));
 if(next<=current){state=await get('/api/dossier?id='+state.dossier.id);current=next;renderDossier();window.scrollTo(0,0);return;}
 const references=current===3?sampleRefs():null;
 await task(async()=>{
  let latest=await get('/api/dossier?id='+state.dossier.id);
  if(next>0&&!latest.pretraitement)throw new Error('Enregistrez le prétraitement des copies dans l’étape 1.');
  if(next>1&&!latest.corriges_valides)throw new Error('Validez tous les corrigés avant de passer à la grille.');
  if(next>2&&(!latest.grille.length||!latest.copies.length))throw new Error('Validez la grille ; le prétraitement sera alors appliqué automatiquement aux copies.');
  if(next>3&&(current===3||!latest.dossier.echantillon_valide)){
   const selected=references??latest.copies.filter(c=>c.echantillon).map(c=>c.reference);
   await post({action:'echantillon',dossier:latest.dossier.id,references:selected,valider:true});
   latest=await get('/api/dossier?id='+latest.dossier.id);
  }
  if(next>4){
   const pending=latest.copies.filter(c=>c.statut==='present'&&!c.exclue_final&&(!c.correction_id||c.a_revoir));
   if(pending.length)throw new Error(`${pending.length} copie(s) restent à corriger ou à revoir.`);
  }
  state=latest;current=next;renderDossier();window.scrollTo(0,0);
 });
};
