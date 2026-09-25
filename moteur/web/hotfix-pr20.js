'use strict';

// PR20: documents stay in the IA conversation; preprocessing is part of step 1.
stages.splice(0,stages.length,
 'Préparation','Corrigés','Grille','Tester la correction','Corriger le lot','Résultats et retour');

const pr20RenderPreviewBase=renderPreview;
renderPreview=function(stage,r,text){
 if(stage!=='pretraitement')return pr20RenderPreviewBase(stage,r,text);
 $('#preview').innerHTML=`<div class="card"><h2>Relire le prétraitement</h2><p class="success">${r.copies} copie(s) repérée(s) · ${r.pages_ignorees} page(s) ignorée(s).</p><p class="help">Ce repérage sera appliqué automatiquement dès que la grille sera validée.</p></div>`;
};

function anonymityControl(){
 const anonymous=state.anonymat!==false;
 const locked=!!state.pretraitement;
 return `<div class="field"><label for="ai-anonymity">Identité des élèves dans l’IA</label><select id="ai-anonymity" ${locked?'disabled':''}><option value="1" ${anonymous?'selected':''}>Mode anonymat — références C001, C002…</option><option value="0" ${!anonymous?'selected':''}>Anonymat désactivé — noms/prénoms visibles par l’IA</option></select><small>${anonymous?'Les noms visibles sur les copies ne doivent pas être restitués par l’IA.':'Les noms/prénoms visibles sur les copies peuvent être lus, restitués et utilisés dans les corrections.'}${locked?' Ce choix est verrouillé après validation des résultats de l’initialisation.':''}</small></div>`;
}
function bindAnonymity(){
 const select=$('#ai-anonymity');if(!select||select.disabled)return;
 select.onchange=()=>task(async()=>{
  const actif=select.value==='1';
  await post({action:'anonymat',dossier:state.dossier.id,actif});
  state=await get('/api/dossier?id='+state.dossier.id);
  renderDossier();
  toast(actif?'Mode anonymat activé.':'Anonymat désactivé : l’IA peut utiliser les noms des élèves.');
 });
}

function studentLabel(s){
 const name=[s.prenom,s.nom].filter(Boolean).join(' ');
 return 'n° '+s.numero+' — '+name;
}
function normalizeStudentSearch(value){
 return String(value||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().trim();
}
function studentMatches(s,query){
 const q=normalizeStudentSearch(query);
 if(!q)return true;
 const fields=[String(s.numero),s.nom,s.prenom,[s.prenom,s.nom].filter(Boolean).join(' '),[s.nom,s.prenom].filter(Boolean).join(' ')];
 return fields.some(value=>normalizeStudentSearch(value).split(/[\s-]+/).some(part=>part.startsWith(q))||normalizeStudentSearch(value).startsWith(q));
}
function assignmentPanel(prep){
 if(!prep)return '';
 const students=state.eleves||[];
 const byId=new Map(students.map(s=>[Number(s.id),s]));
 const rows=prep.copies.map(c=>{
  const read=c.identite_lue||[c.prenom,c.nom].filter(Boolean).join(' ')||'Non reconnu par l’IA';
  const current=c.eleve_id==null?null:byId.get(Number(c.eleve_id));
  const currentText=current?studentLabel(current):'Non attribuée';
  return `<tr><td><strong>${esc(c.reference)}</strong><br><small>p. ${c.pages.join(', ')} · version ${esc(c.version)}</small></td><td>${esc(read)}</td><td><div class="student-search" data-reference="${esc(c.reference)}"><div class="student-current"><strong>${esc(currentText)}</strong>${current?'<button type="button" class="clear-student" title="Retirer le nom sans supprimer la correction">Retirer le nom</button>':''}</div><input class="copy-student-search" type="search" autocomplete="off" placeholder="N° ou nom de l’élève…" aria-label="Rechercher un élève pour ${esc(c.reference)}"><div class="student-suggestions" hidden></div></div></td></tr>`;
 }).join('');
 return `<div class="card"><h3>Affectation locale des élèves</h3><p class="help">Une copie peut rester sans élève. Recherchez par numéro, nom ou prénom : par exemple <strong>Moh</strong> propose les élèves dont le nom ou le prénom commence par « Moh ». Seuls les élèves non attribués sont proposés. Cette liste reste locale et n’est pas envoyée à l’IA.</p><div class="table-wrap"><table><thead><tr><th>Copie</th><th>Identité lue par l’IA</th><th>Élève</th></tr></thead><tbody>${rows}</tbody></table></div></div>`;
}
function availableAssignmentStudents(){
 const copies=state.pretraitement?.copies??state.copies??[];
 const assigned=new Set(copies.filter(c=>c.eleve_id!=null).map(c=>Number(c.eleve_id)));
 return (state.eleves||[]).filter(s=>!assigned.has(Number(s.id)));
}
function bindAssignments(){
 const assign=async(ref,value)=>{
  await post({action:'revue',dossier:state.dossier.id,reference:'@affectation:'+ref+':'+value});
  state=await get('/api/dossier?id='+state.dossier.id);
  renderDossier();
  toast(value?'Élève affecté à '+ref+'.':ref+' reste sans élève.');
 };
 document.querySelectorAll('.student-search').forEach(box=>{
  const input=box.querySelector('.copy-student-search');
  const suggestions=box.querySelector('.student-suggestions');
  const ref=box.dataset.reference;
  const renderSuggestions=()=>{
   const q=input.value.trim();
   const matches=availableAssignmentStudents().filter(s=>studentMatches(s,q)).slice(0,8);
   suggestions.innerHTML=matches.length?matches.map(s=>`<button type="button" class="student-suggestion" data-id="${s.id}"><span>${esc(studentLabel(s))}</span></button>`).join(''):'<div class="help">Aucun élève disponible pour cette recherche.</div>';
   suggestions.hidden=false;
   suggestions.querySelectorAll('.student-suggestion').forEach(button=>button.onclick=()=>task(()=>assign(ref,button.dataset.id)));
  };
  input.oninput=renderSuggestions;
  input.onfocus=renderSuggestions;
  input.onkeydown=event=>{
   if(event.key==='Escape')suggestions.hidden=true;
   if(event.key==='Enter'){
    const first=suggestions.querySelector('.student-suggestion');
    if(first){event.preventDefault();first.click();}
   }
  };
  const clear=box.querySelector('.clear-student');
  if(clear)clear.onclick=()=>task(()=>assign(ref,''));
 });
 document.addEventListener('click',event=>{
  if(!event.target.closest('.student-search'))document.querySelectorAll('.student-suggestions').forEach(x=>x.hidden=true);
 },{once:true});
}

renderSetup=function(){
 const prep=state.pretraitement;
 const names=state.anonymat===false;
 $('#main').innerHTML=`<div class="page-head"><div><div class="eyebrow">${esc(state.dossier.classe)}</div><h1>Étape 1/6</h1><p class="lede">Choisissez le format, préparez les documents puis initialisez l’IA et récupérez le résultat de cette première lecture.</p></div><span class="badge">${esc(state.dossier.titre)}</span></div>`+
 layoutCard('setup')+
 `<div class="card"><div class="eyebrow">2. Préparation des documents</div><h2>Documents à joindre à l’IA</h2><p class="help">Aucun upload dans SmartCorrection. Joignez directement ces fichiers dans la conversation IA.</p><ul class="doc-list"><li><span>▤</span><div class="grow"><strong>Copies</strong><small>Le paquet PDF complet, non découpé.</small></div></li><li><span>▤</span><div class="grow"><strong>Sujet</strong><small>Le sujet de l’évaluation avec toutes ses versions.</small></div></li><li><span>▤</span><div class="grow"><strong>Corrigé éventuel</strong><small>Seulement s’il existe déjà.</small></div></li><li><span>▤</span><div class="grow"><strong>Documents de cours de référence</strong><small>Savoir-faire, cours, modèles de rédaction ou documents utiles.</small></div></li></ul>${anonymityControl()}</div>`+
 `<div class="card"><div class="eyebrow">3. Initialisation de l’IA</div><h2>Première lecture des copies</h2><p class="help">Joignez les documents ci-dessus, puis copiez la consigne ci-dessous dans l’IA. Elle repère immédiatement les copies, leurs versions probables et les erreurs communes ; cette première lecture servira ensuite au corrigé et à la grille.${names?' Le mode anonymat est désactivé : l’IA conserve aussi les noms/prénoms qu’elle arrive à lire sur les copies.':''}</p><h3>Consigne à copier dans l’IA</h3><textarea id="opening" aria-label="Consigne de démarrage pour l’IA" readonly placeholder="Chargement de la consigne…"></textarea><div class="actions"><button class="primary" id="copy-opening" disabled>Copier</button></div><p class="help">Gardez cette même conversation pour toutes les étapes suivantes.</p></div>`+
 `<div class="card"><div class="eyebrow">4. Résultats de l’initialisation</div><h2>Prétraitement des copies</h2><p class="help">Après la première lecture, demandez à l’IA son JSON de repérage des copies puis collez-le ci-dessous.${names?' Les noms/prénoms peuvent être absents si l’IA ne les lit pas.':''} Aucun PDF n’est importé dans SmartCorrection.</p>`+
 exchangePanel('pretraitement','Résultat de l’initialisation au format JSON',names?'Le JSON contient les copies, les noms/prénoms lisibles s’ils sont connus, leurs pages, leur version probable et les pages ignorées.':'Le JSON contient les copies repérées, leurs pages, leur version probable et les pages ignorées.')+
 (prep?`<div class="notice success">Prétraitement enregistré : ${prep.copies.length} copie(s). Il sera appliqué automatiquement à la validation de la grille.</div>`:'')+
 `</div>`+assignmentPanel(prep)+`<div class="notice">Les consignes générales et celles de cette classe sont intégrées automatiquement au texte copié.</div><button id="view-policies">Voir les consignes mémorisées</button>`;
 bindLayout('setup');
 bindAnonymity();
 bindAssignments();
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
