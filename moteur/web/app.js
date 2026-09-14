'use strict';
const $=s=>document.querySelector(s);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const token=$('meta[name="csrf-token"]').content;
const stages=['Préparer le dossier','Grille','Corrigé','Repérer les copies','Tester la correction','Corriger le reste','Retour d’expérience'];
let homeData=null,state=null,current=0,referenceVersion=null,correctionMode='echantillon',busy=false;
let lastPreview=null,previewText='',toastTimer,draftTimer,rosterText='',rosterChecked=false;
const drafts=new Map();
async function get(url){const r=await fetch(url);const d=await r.json();if(!r.ok)throw new Error(d.erreur||'Lecture impossible');return d;}
async function post(data){const r=await fetch('/api/action',{method:'POST',headers:{'Content-Type':'application/json','X-SmartCorrection-Token':token},body:JSON.stringify(data)});const d=await r.json();if(!r.ok){const error=new Error(d.erreur||'Action impossible');error.responseRepairable=d.reponse_reparable===true;throw error;}return d;}
function toast(text,bad=false){clearTimeout(toastTimer);const el=$('#toast');el.textContent=text;el.className='toast'+(bad?' bad':'');el.hidden=false;toastTimer=setTimeout(()=>el.hidden=true,6500);}
async function task(fn,{response=false}={}){if(busy)return;busy=true;let failed=false;$('#save-status').innerHTML='<span class="busy-label">En cours…</span>';document.querySelectorAll('button, input, select, textarea').forEach(b=>{b.dataset.wasDisabled=b.disabled?'1':'0';b.disabled=true;});try{await fn();}catch(e){failed=true;toast(e.message,true);if(response&&$('#exchange-error')){const repair=e.responseRepairable&&$('#response')?.value.trim()&&$('#prompt')?.value.trim();$('#exchange-error').innerHTML=`<div class="error">${esc(e.message)}</div>${repair?'<button id="repair-prompt">Copier une demande de réparation du format</button>':''}`;}}finally{busy=false;document.querySelectorAll('button, input, select, textarea').forEach(b=>{if(b.dataset.wasDisabled!==undefined){b.disabled=b.dataset.wasDisabled==='1';delete b.dataset.wasDisabled;}});$('#save-status').textContent=failed?'À vérifier':'Enregistré localement';}}
function showModal(html,wide=false){$('#modal').classList.toggle('wide',wide);$('#modal-content').innerHTML=html;$('#modal').showModal();}
$('#close-modal').onclick=()=>$('#modal').close();
$('#home-button').onclick=()=>loadHome();
$('.brand').onclick=e=>{e.preventDefault();loadHome();};
async function loadHome(){state=null;$('#dossier-nav').innerHTML='';$('#breadcrumb').textContent='Mes évaluations';homeData=await get('/api/home');renderHome();}
function renderHome(){
 $('#main').innerHTML=`<div class="eyebrow">Votre espace de travail</div><h1>Mes évaluations</h1><p class="lede">Préparez la correction avec l’IA, vérifiez les résultats et retrouvez vos dossiers à tout moment.</p>
 <div class="hero-actions"><button class="action-card" id="add-class"><div><div class="icon">＋</div><strong>Ajouter une classe</strong><span>Importez votre liste d’élèves depuis un CSV nom / prénom.</span></div></button><button class="action-card featured" id="new-dossier"><div><div class="icon">↗</div><strong>Corriger un paquet de copies</strong><span>Un PDF entier, une grille discutée ensemble et des fiches prêtes à partager.</span></div></button></div>
 <div class="section-label"><h2>Dossiers de correction</h2><span class="count">${homeData.dossiers.length} dossier${homeData.dossiers.length!==1?'s':''}</span></div>
 ${homeData.dossiers.length?`<div class="dossier-list">${homeData.dossiers.map(d=>`<div class="dossier-row"><div class="grow"><strong>${esc(d.titre)}</strong><small>${esc(d.classe)} · Grille ${d.revision||'à préparer'}</small></div><span class="badge ${d.termine?'ok':''}">${d.termine?'Document final disponible':'En cours'}</span><button data-open="${esc(d.id)}">Reprendre →</button></div>`).join('')}</div>`:'<div class="empty">Votre premier dossier apparaîtra ici.<br>Commencez par ajouter une classe.</div>'}
 <div class="section-label"><h2>Mes classes</h2></div><div>${homeData.classes.map(c=>`<span class="class-chip">${esc(c.classe)} <span class="tiny">${c.effectif} élèves</span></span>`).join('')||'<span class="help">Aucune classe importée pour le moment.</span>'}</div>
 ${homeData.latex?'':'<div class="notice warning">LaTeX n’est pas détecté. Vous pouvez préparer les corrections ; la génération PDF demandera une installation LaTeX.</div>'}`;
 $('#add-class').onclick=classModal;$('#new-dossier').onclick=newModal;
 document.querySelectorAll('[data-open]').forEach(b=>b.onclick=()=>openDossier(b.dataset.open));
}
function classModal(){rosterText='';rosterChecked=false;showModal(`<div class="eyebrow">Liste des élèves</div><h1>Ajouter une classe</h1><p class="lede">Vérifiez les noms et les numéros avant l’import.</p><div class="field"><label for="class-name">Nom de la classe</label><input id="class-name" placeholder="Ex. 1GSpé"></div><div class="field"><label for="class-file">Fichier CSV</label><input id="class-file" type="file" accept=".csv,.tsv,text/csv"><small>Colonnes nom et prénom. Le numéro est facultatif ; il sera attribué dans l’ordre du CSV.</small></div><div class="actions"><button id="roster-check">Vérifier le fichier</button><button class="primary" id="roster-save" disabled>Ajouter la classe</button></div><div id="roster-preview"></div>`);
 $('#class-file').onchange=async e=>{const f=e.target.files[0];if(!f)return;const buffer=await f.arrayBuffer();try{rosterText=new TextDecoder('utf-8',{fatal:true}).decode(buffer);}catch{rosterText=new TextDecoder('windows-1252').decode(buffer);}rosterChecked=false;$('#roster-save').disabled=true;};
 $('#class-name').oninput=()=>{rosterChecked=false;$('#roster-save').disabled=true;};
 $('#roster-check').onclick=()=>task(async()=>{const r=await post({action:'classe',classe:$('#class-name').value,texte:rosterText});$('#roster-preview').innerHTML=table(['N°','Nom','Prénom'],r.eleves.map(x=>[x.numero,x.nom,x.prenom]));rosterChecked=true;$('#roster-save').disabled=false;delete $('#roster-save').dataset.wasDisabled;});
 $('#roster-save').onclick=()=>task(async()=>{if(!rosterChecked)return;await post({action:'classe',classe:$('#class-name').value,texte:rosterText,valider:true});$('#modal').close();await loadHome();toast('Classe enregistrée.');});
}
function newModal(){if(!homeData.classes.length){classModal();return;}showModal(`<div class="eyebrow">Nouveau dossier</div><h1>Corriger un paquet</h1><div class="field"><label for="new-class">Classe</label><select id="new-class">${homeData.classes.map(c=>`<option>${esc(c.classe)}</option>`).join('')}</select></div><div class="field"><label for="new-title">Nom de l’évaluation</label><input id="new-title" placeholder="Ex. Équations — savoir-faire 1"></div><button class="primary" id="create-dossier">Créer le dossier →</button>`);$('#create-dossier').onclick=()=>task(async()=>{const r=await post({action:'creer',classe:$('#new-class').value,titre:$('#new-title').value});$('#modal').close();await openDossier(r.id,0);});}
function resumeStep(){return state.dossier.termine?6:!state.dossier.revision?0:state.versions.some(v=>!v.corrige_latex)?2:!state.copies.length?3:state.dossier.echantillon_valide?5:4;}
async function openDossier(id,step=null){state=await get('/api/dossier?id='+encodeURIComponent(id));current=step===null?resumeStep():step;referenceVersion=null;renderDossier();}
function header(title,description){return `<div class="page-head"><div><div class="eyebrow">Étape ${current+1} sur ${stages.length} · ${esc(state.dossier.classe)}</div><h1>${title}</h1><p class="lede">${description}</p></div><span class="badge">${esc(state.dossier.titre)}</span></div>`;}
function table(heads,rows){return `<div class="table-wrap"><table><thead><tr>${heads.map(x=>`<th>${esc(x)}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${r.map(x=>`<td>${esc(x)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;}
function renderDossier(){
 lastPreview=null;previewText='';$('#breadcrumb').textContent=state.dossier.classe+' / '+state.dossier.titre;
 const done=[state.fichiers.some(f=>f.role==='paquet'),state.grille.length,state.versions.length&&state.versions.every(v=>v.corrige_latex),state.copies.length,state.dossier.echantillon_valide,state.dossier.termine,false];
 $('#dossier-nav').innerHTML=`<div class="nav-caption">Parcours de correction</div><nav class="steps" aria-label="Étapes">${stages.map((s,i)=>`<button class="step ${i===current?'active':''} ${done[i]?'done':''}" data-step="${i}" ${i===current?'aria-current="step"':''}><span class="num">${done[i]?'✓':i+1}</span>${s}</button>`).join('')}</nav>`;
 document.querySelectorAll('[data-step]').forEach(b=>b.onclick=()=>goStep(Number(b.dataset.step)));
 if(current===0)renderSetup();else if(current===1)renderGrid();else if(current===2)renderReference();else if(current===3)renderInventory();else if(current===4)renderCorrection(false);else if(current===5)renderCorrection(true);else renderFeedback();
 $('#main').insertAdjacentHTML('beforeend',`<div class="footer-nav"><button id="previous" ${current===0?'disabled':''}>← Étape précédente</button>${current<stages.length-1?([1,2,3].includes(current)?'':'<button id="next">Étape suivante →</button>'):'<button id="finish-home">Revenir à mes évaluations</button>'}</div>`);
 $('#previous').onclick=()=>goStep(current-1);if($('#next'))$('#next').onclick=()=>goStep(current+1);if($('#finish-home'))$('#finish-home').onclick=()=>loadHome();
 bindCommon();
}
async function goStep(i){
 const next=Math.max(0,Math.min(stages.length-1,i));
 const references=current===4?sampleRefs():null;
 await task(async()=>{
  let latest=await get('/api/dossier?id='+state.dossier.id);
  if(next>4&&(current===4||!latest.dossier.echantillon_valide)){
   const selected=references??latest.copies.filter(c=>c.echantillon).map(c=>c.reference);
   await post({action:'echantillon',dossier:latest.dossier.id,references:selected,valider:true});
   latest=await get('/api/dossier?id='+latest.dossier.id);
  }
  state=latest;current=next;renderDossier();window.scrollTo(0,0);
 });
}
function filesHtml(){return `<ul class="doc-list">${state.fichiers.map(f=>`<li><span>▤</span><div class="grow"><a target="_blank" rel="noopener" href="/file?kind=source&id=${esc(f.id)}">${esc(f.nom)}</a><small>${esc(f.role)} · ${f.pages} pages</small></div></li>`).join('')}</ul>`;}
function renderSetup(){
 $('#main').innerHTML=header('Préparer le dossier','Ajoutez vos documents, puis envoyez la consigne ci-dessous dans une nouvelle conversation avec l’IA.')+`<div class="split"><div class="card"><h2>Documents de l’évaluation</h2><p class="help">Le paquet reste un seul PDF. Les documents sélectionnés sont copiés dans le dossier local de l’application.</p>${filesHtml()}<div class="row"><div class="field"><label for="file-role">Document à ajouter</label><select id="file-role"><option value="paquet">Paquet de copies</option><option value="sujet">Sujet</option><option value="corrige">Corrigé existant</option><option value="cours">Cours / savoir-faire</option><option value="modele">Modèle de rédaction</option></select></div></div><div class="field"><label for="pdf-file">Choisir un PDF</label><input type="file" id="pdf-file" accept="application/pdf,.pdf"></div><button id="upload-file" class="primary">Ajouter le document</button></div><div class="card"><h2 class="exchange-title">Consigne à copier dans l’IA</h2><p class="help">Copiez cette consigne et envoyez-la dans l’IA. Joignez aussi le paquet, le sujet et les documents utiles dans cette conversation ; ils ne sont pas transmis par l’application.</p><textarea id="opening" aria-label="Consigne de démarrage pour l’IA" readonly placeholder="Chargement de la consigne…"></textarea><div class="actions"><button class="primary" id="copy-opening" disabled>Copier</button></div><p class="help">Gardez cette conversation pour les étapes suivantes.</p></div></div><div class="notice">Les consignes générales et celles de cette classe sont jointes automatiquement aux messages. Vous pourrez les réécrire avec l’IA en fin de correction.</div><button id="view-policies">Voir les consignes mémorisées</button>`;
 $('#upload-file').onclick=()=>task(async()=>{const f=$('#pdf-file').files[0];if(!f)throw new Error('Choisir un fichier PDF.');const content=await fileBase64(f);await post({action:'upload',dossier:state.dossier.id,role:$('#file-role').value,nom:f.name,contenu:content});state=await get('/api/dossier?id='+state.dossier.id);renderDossier();toast('Document ajouté.');});
 loadPrompt('ouverture','#opening','#copy-opening');$('#view-policies').onclick=policiesModal;
}
function exchangePanel(stage,outputTitle='Réponse de l’IA',intro='Collez la réponse, vérifiez son contenu puis validez cette étape.'){
 const key=state.dossier.id+':'+stage;
 const saved=stage.startsWith('corrige:')?state.versions.find(v=>v.version===stage.slice(8))?.corrige_latex:'';
 const val=drafts.has(key)?drafts.get(key):(state.brouillons[stage]??saved??'');
 return `<div class="split"><section class="pane"><div class="pane-head"><h2 class="exchange-title">Consigne à copier dans l’IA</h2></div><div class="pane-body"><textarea id="prompt" aria-label="Consigne pour l’IA" readonly placeholder="Chargement de la consigne…"></textarea></div><div class="pane-foot actions"><button class="primary" id="copy-prompt" disabled>Copier</button><p class="copy-help">Envoyez ce texte dans votre conversation avec l’IA.</p></div></section><section class="pane"><div class="pane-head"><h2 class="exchange-title">Résultat de l’IA</h2><p>${intro}</p></div><div class="pane-body"><textarea id="response" aria-label="${outputTitle}" data-stage="${esc(stage)}" placeholder="Collez ici la réponse de l’IA.">${esc(val)}</textarea></div><div class="pane-foot"><div class="actions"><button id="check-response">Vérifier</button><button class="primary" id="save-response" disabled>${stage==='retour'?'Remplacer les consignes':stage==='correction'?'Enregistrer les corrections':'Enregistrer et continuer'}</button></div><div id="exchange-error" role="alert"></div></div></section></div><section class="preview" id="preview" aria-live="polite"></section>`;
}
function renderGrid(){
 $('#main').innerHTML=header('Grille de notation','Discutez de la grille avec l’IA, puis collez sa réponse à droite.')+
 (state.dossier.revision?`<div class="notice ${state.copies.some(c=>c.correction_id)?'warning':''}">Grille ${state.dossier.revision} enregistrée. Une nouvelle validation crée une nouvelle révision ; les corrections précédentes restent archivées et les copies seront à reprendre.</div>`:'')+
 exchangePanel('grille','Grille au format JSON','Copiez le bloc de code JSON de l’IA. Le barème s’affichera sous forme de tableau pour relecture.')+
 (state.grille.length?`<details class="card"><summary>Voir la grille enregistrée</summary>${table(['Version','Ex. / Q.','Item','Critère','Points'],state.grille.map(i=>[i.version||'Commune',i.exercice+' / '+i.question,i.code,i.description,i.bareme_max]))}</details>`:'');
}
function renderReference(){
 const intro=header('Corrigé de référence','Demandez le corrigé à l’IA, puis collez son code LaTeX à droite.');
 if(!state.versions.length){$('#main').innerHTML=intro+'<div class="notice warning">Validez d’abord la grille pour définir les versions du sujet.</div><button id="go-grid" class="primary">Aller à la grille</button>';$('#go-grid').onclick=()=>goStep(1);return;}
 if(!state.versions.some(v=>v.version===referenceVersion))referenceVersion=(state.versions.find(v=>!v.corrige_latex)||state.versions[0]).version;
 const tabs=state.versions.length>1?`<div class="subnav" aria-label="Versions du corrigé">${state.versions.map(v=>`<button data-version="${esc(v.version)}" class="${referenceVersion===v.version?'selected':''}" aria-pressed="${referenceVersion===v.version}">Version ${esc(v.version)} ${v.corrige_latex?'✓':''}</button>`).join('')}</div>`:'';
 $('#main').innerHTML=intro+tabs+'<div class="reference-editor">'+exchangePanel('corrige:'+referenceVersion,'Corrigé LaTeX — version '+esc(referenceVersion),'Collez le corrigé LaTeX complet, sans préambule ni début / fin de document.')+'</div>';
 document.querySelectorAll('[data-version]').forEach(b=>b.onclick=()=>{referenceVersion=b.dataset.version;renderDossier();});
}
function groupsPanel(){
 const g=state.groupes||{actif:false,membres:[],sans_groupe:[]}, groups=new Map();
 for(const m of g.membres){if(!groups.has(m.numero_groupe))groups.set(m.numero_groupe,[]);groups.get(m.numero_groupe).push(m);}
 const text=[...groups.values()].map(ms=>ms.map(m=>m.numero).join(', ')).join('\n');
 return `<details class="card" ${g.actif?'open':''}><summary>Note de groupe · Maths expertes ${g.actif?'activée':'facultative'}</summary><p>Individuelle /15 + moyenne des autres camarades /5 = finale /20. Les absents sont exclus ; les notes incomplètes restent en attente.</p><label><input type="checkbox" id="groups-active" ${g.actif?'checked':''}> Activer la note de groupe</label><label for="groups-text">Un groupe par ligne · numéros des élèves</label><textarea id="groups-text" style="min-height:110px" placeholder="2, 31, 3, 22&#10;20, 25, 11, 27">${esc(text)}</textarea><button id="save-groups">Enregistrer les groupes</button><div id="groups-error" role="alert"></div>${table(['Groupe','Élèves'],[...groups].map(([n,ms])=>[n,ms.map(m=>m.numero+' — '+m.prenom+' '+m.nom).join(', ')]))}${g.actif&&g.sans_groupe.length?'<p class="notice warning">Sans groupe : '+esc(g.sans_groupe.join(', '))+'. Leur note finale restera à traiter.</p>':''}<p class="help">Ces identités et groupes restent dans l’application, jamais dans la consigne IA. Les PDF existants seront à régénérer.</p></details>`;
}
function bindGroups(){
 if(!$('#save-groups'))return;
 $('#save-groups').onclick=()=>task(async()=>{
  try{await post({action:'groupes',dossier:state.dossier.id,actif:$('#groups-active').checked,texte:$('#groups-text').value});
   state=await get('/api/dossier?id='+state.dossier.id);renderDossier();toast('Groupes enregistrés. Les notes seront recalculées au prochain rendu.');
  }catch(e){$('#groups-error').innerHTML='<div class="error">'+esc(e.message)+'</div>';throw e;}
 });
}
function renderInventory(){
 $('#main').innerHTML=header('Repérer les copies','Demandez à l’IA de repérer les copies du paquet, puis collez sa réponse à droite.')+
 (!state.dossier.revision?'<div class="notice warning">Validez d’abord la grille et ses versions.</div>':'')+exchangePanel('copies','Inventaire au format JSON')+
 (state.copies.length?`<div class="card"><h2>Copies enregistrées</h2>${copyTable(state.copies,false)}</div>`:'')+(state.dossier.revision?groupsPanel():'');
 bindGroups();
}
function copyTable(copies,select){return `<div class="table-wrap"><table><thead><tr>${select?'<th>Test</th>':''}<th>Copie</th><th>Élève</th><th>Pages</th><th>Version</th><th>État</th></tr></thead><tbody>${copies.map(c=>`<tr>${select?`<td>${c.statut==='present'?`<input type="checkbox" aria-label="Sélectionner ${esc(c.reference)}" data-sample="${esc(c.reference)}" ${c.echantillon?'checked':''}>`:''}</td>`:''}<td>${esc(c.reference)}</td><td>${c.numero!==null?esc('N° '+c.numero+' — '+(c.prenom||'')+' '+(c.nom||'')):'<span class="badge warn">Non identifié</span>'}</td><td>${esc(c.pages.join(', '))}</td><td>${esc(c.version)}</td><td>${c.a_revoir?`<span class="badge warn">À revoir</span><small>${esc(c.a_revoir)}</small>${c.correction_id?`<button class="tiny" data-review="${esc(c.reference)}">J’ai vérifié cette correction</button>`:''}`:c.statut==='absent'?'Absent':c.correction_id?'<span class="badge ok">Corrigée</span>':'À corriger'}</td></tr>`).join('')}</tbody></table></div>`;}
function renderCorrection(rest){
 correctionMode=rest?'reste':'echantillon';const present=state.copies.filter(c=>c.statut==='present');const done=present.filter(c=>c.correction_id&&!c.a_revoir).length;const review=present.filter(c=>c.a_revoir).length;
 $('#main').innerHTML=header(rest?'Corriger le reste':'Tester la correction',rest?'Demandez la correction de toutes les copies restantes. Vous pouvez importer plusieurs réponses, chacune contenant des copies complètes.':'Choisissez jusqu’à cinq copies, vérifiez les fiches puis ajustez avec l’IA jusqu’à être satisfait.')+
 `<div class="metrics"><div class="metric"><strong>${present.length}</strong><span>copies repérées</span></div><div class="metric"><strong>${done}</strong><span>corrigées</span></div><div class="metric"><strong>${review}</strong><span>à revoir</span></div><div class="metric"><strong>${present.length-done-review}</strong><span>restantes</span></div></div>`+
 groupsPanel()+(rest&&!state.dossier.echantillon_valide?'<div class="notice warning">Terminez la correction de l’échantillon, puis passez à l’étape suivante pour la valider.</div>':'')+
 `<div class="card"><h2>${rest?'Suivi du paquet':'Copies de l’échantillon'}</h2>${copyTable(state.copies,!rest)}${!rest?'<div class="actions"><button id="save-sample">Enregistrer la sélection</button></div>':''}</div>`+exchangePanel('correction','Corrections au format JSON')+
 `<div class="card"><h2>${rest?'Document final':'Vérifier les fiches'}</h2><p class="help">Relisez les fiches après avoir enregistré les corrections.${rest?'':' Passer à l’étape suivante valide l’échantillon.'}</p><div class="actions"><button class="primary" id="generate-pdf">${rest?'Créer le PDF final':'Voir les fiches du test'}</button></div><div id="render-error"></div><details class="more-options"><summary>Plus d’options</summary><button id="generate-tex">Exporter les sources LaTeX</button>${renderLinks()}</details></div>`;
 if($('#save-sample'))$('#save-sample').onclick=()=>task(async()=>{await post({action:'echantillon',dossier:state.dossier.id,references:sampleRefs()});state=await get('/api/dossier?id='+state.dossier.id);renderDossier();toast('Sélection enregistrée.');});
 $('#generate-pdf').onclick=()=>generate(rest,true);$('#generate-tex').onclick=()=>generate(rest,false);bindGroups();
 if(!rest)document.querySelectorAll('[data-sample]').forEach(box=>box.onchange=()=>{for(const id of ['copy-prompt','check-response','save-response','generate-pdf','generate-tex'])$('#'+id).disabled=true;$('#prompt').dataset.cancelled='1';$('#prompt').value='';$('#prompt').placeholder='Enregistrez la sélection pour afficher la consigne actualisée.';toast('Enregistrez la sélection avant de copier la consigne ou de voir les fiches.');});
 document.querySelectorAll('[data-review]').forEach(b=>b.onclick=()=>task(async()=>{await post({action:'revue',dossier:state.dossier.id,reference:b.dataset.review});state=await get('/api/dossier?id='+state.dossier.id);renderDossier();}));
}
function sampleRefs(){return [...document.querySelectorAll('[data-sample]:checked')].map(x=>x.dataset.sample);}
function renderLinks(){return state.rendus.length?`<h3>Documents précédents (${state.rendus.length})</h3><ul class="doc-list">${state.rendus.map(r=>`<li><div class="grow">${r.final?'Document final':'Test'} · grille ${r.revision}<small>${esc(r.cree_le)}${!r.valide?' — à régénérer':''}</small></div><a target="_blank" rel="noopener" href="/file?kind=rendu&id=${r.id}&name=notes.json">Données</a><a target="_blank" rel="noopener" href="/file?kind=rendu&id=${r.id}&name=notes.csv">Notes CSV</a>${r.pdf?`<a target="_blank" rel="noopener" href="/file?kind=rendu&id=${r.id}&name=corrections.pdf">PDF</a>`:'Sources seules'}</li>`).join('')}</ul>`:'';}
async function generate(final,pdf){await task(async()=>{try{const r=await post({action:'generer',dossier:state.dossier.id,final,pdf});state=await get('/api/dossier?id='+state.dossier.id);renderDossier();if(pdf){const url=`/file?kind=rendu&id=${r.id}&name=corrections.pdf`;showModal(`<h2>${final?'Document final':'Fiches du test'}</h2><div class="actions"><a href="${url}" target="_blank" rel="noopener">Ouvrir dans un onglet ↗</a></div><iframe title="Fiches de correction" class="pdf-viewer" src="${url}"></iframe>`,true);}else{showModal(`<h2>Sources exportées</h2><ul>${r.fichiers.map(name=>`<li><a href="/file?kind=rendu&id=${r.id}&name=${encodeURIComponent(name)}" target="_blank" rel="noopener">${esc(name)}</a></li>`).join('')}</ul>`);}}catch(e){$('#render-error').innerHTML=`<div class="error">${esc(e.message)}</div>`;throw e;}});}
function renderFeedback(){
 $('#main').innerHTML=header('Préparer la prochaine fois','Demandez à l’IA de réécrire les consignes à partir de votre discussion, puis relisez les changements avant de les enregistrer.')+
 (!state.dossier.termine?'<div class="notice warning">Le retour d’expérience sera disponible après la génération du document final.</div>':'<div class="notice">Les deux textes validés remplaceront les consignes actives : générales pour toutes les classes, et spécifiques pour cette classe. Les anciennes versions restent consultables.</div>')+
 exchangePanel('retour','Nouvelles consignes au format JSON','Deux textes complets : les consignes générales et les consignes de la classe.')+`<button id="view-policies">Consulter les consignes et leur historique</button>`;
 $('#view-policies').onclick=policiesModal;
}
async function policiesModal(){const history=await get('/api/history?classe='+encodeURIComponent(state.dossier.classe));showModal(`<h2>Consignes mémorisées</h2><p class="help">Les nouveaux dossiers reprennent les dernières consignes validées. Un dossier en cours conserve celles de son démarrage.</p><h3>Générales</h3><div class="policy">${esc(state.consignes.generales.texte||'Aucune consigne générale enregistrée.')}</div><h3>${esc(state.dossier.classe)}</h3><div class="policy">${esc(state.consignes.classe.texte||'Aucune consigne de classe enregistrée.')}</div><h3>Historique</h3>${history.map(r=>`<details><summary>${esc(r.portee)} · ${esc(r.cree_le)} · version ${r.id}</summary><div class="policy">${esc(r.texte)}</div></details>`).join('')||'<p class="help">Aucune version antérieure.</p>'}`,true);}
function promptUrl(stage){let url='/api/prompt?id='+state.dossier.id+'&etape='+encodeURIComponent(stage.startsWith('corrige:')?'corrige':stage);if(stage.startsWith('corrige:'))url+='&version='+encodeURIComponent(stage.slice(8));if(stage==='correction')url+='&mode='+correctionMode;return url;}
async function loadPrompt(stage,areaSelector='#prompt',buttonSelector='#copy-prompt'){
 const area=$(areaSelector),button=$(buttonSelector);
 area.value='';area.placeholder='Chargement de la consigne…';button.disabled=true;
 try{
  const response=await get(promptUrl(stage));
  if($(areaSelector)!==area||area.dataset.cancelled)return;
  if(typeof response.texte!=='string'||!response.texte.trim())throw new Error('Consigne vide.');
  area.value=response.texte;button.textContent='Copier';
  button.onclick=()=>copyText(area.value);
 }catch(e){
  if($(areaSelector)!==area||area.dataset.cancelled)return;
  area.placeholder='Consigne indisponible : '+e.message;
  button.textContent='Réessayer l’affichage de la consigne';
  button.onclick=()=>loadPrompt(stage,areaSelector,buttonSelector);
 }
 // Preserve the busy-state restoration when another action is still running.
 if(button.dataset.wasDisabled!==undefined)button.dataset.wasDisabled='0';
 else button.disabled=false;
}
function bindCommon(){
 if(!$('#response'))return;
 const area=$('#response');const stage=area.dataset.stage;
 area.oninput=()=>{const key=state.dossier.id+':'+stage;drafts.set(key,area.value);lastPreview=null;$('#save-response').disabled=true;$('#save-status').textContent='Brouillon…';clearTimeout(draftTimer);const dossier=state.dossier.id,text=area.value;draftTimer=setTimeout(()=>post({action:'brouillon',dossier,etape:stage,texte:text}).then(()=>$('#save-status').textContent='Brouillon enregistré').catch(e=>toast('Brouillon non enregistré : '+e.message,true)),500);};
 loadPrompt(stage);
 $('#check-response').onclick=()=>submitResponse(false);$('#save-response').onclick=()=>submitResponse(true);
 $('#exchange-error').onclick=e=>{if(e.target.id==='repair-prompt'){copyText('Corrige uniquement le format de ta réponse précédente en respectant la consigne suivante. Conserve les décisions pédagogiques déjà validées.\n\n'+($('#prompt').value||'Consigne de l’étape en cours')+'\n\nErreur de l’application :\n'+$('#exchange-error .error').textContent+'\n\nRéponse à réparer :\n'+$('#response').value);}};
}
async function submitResponse(commit){const stage=$('#response').dataset.stage,text=$('#response').value;if(commit&&(!lastPreview||text!==previewText)){toast('Vérifiez cette réponse avant de la valider.',true);return;}await task(async()=>{const req={action:stage.startsWith('corrige:')?'corrige':'echange',dossier:state.dossier.id,etape:stage,texte:text,valider:commit};if(stage.startsWith('corrige:')){req.version=stage.slice(8);req.revision=state.dossier.revision;}if(commit)clearTimeout(draftTimer);const r=await post(req);$('#exchange-error').innerHTML='';if(commit){clearTimeout(draftTimer);drafts.delete(state.dossier.id+':'+stage);state=await get('/api/dossier?id='+state.dossier.id);if(stage==='grille'){current=2;referenceVersion=null;}else if(stage.startsWith('corrige:')){const missing=state.versions.find(v=>!v.corrige_latex);current=missing?2:3;referenceVersion=missing?.version??null;}else if(stage==='copies'){current=4;}renderDossier();window.scrollTo(0,0);toast(stage==='retour'?'Consignes remplacées pour les prochaines évaluations.':'Résultat enregistré.');}else{lastPreview=r;previewText=text;renderPreview(stage,r,text);$('#save-response').disabled=false;delete $('#save-response').dataset.wasDisabled}},{response:true});}
function responseBody(text,stage){
 const languages=stage.startsWith('corrige:')?'(?:latex|tex)?':'(?:json)?';
 const match=text.trim().match(new RegExp('^```'+languages+'[ \\t]*\\r?\\n([\\s\\S]*?)\\r?\\n```$','i'));
 return match&&!/^```/m.test(match[1])?match[1]:text;
}
function renderPreview(stage,r,text){
 text=responseBody(text,stage);
 let html='<div class="card"><h2>Relire le résultat</h2>';
 if(stage==='grille'){const data=JSON.parse(text);html+=table(['Version','Exercice','Question','Item','Critère','Points'],data.grilles.flatMap(g=>g.exercices.flatMap(e=>e.questions.flatMap(q=>q.items.map(i=>[g.version||'Commune',e.numero,q.numero,i.code,i.description,i.bareme_max])))));html+=`<p class="success">${r.grilles.map(g=>esc(g.nom||'Grille')+' : '+g.total_points+' points').join(' · ')}</p>`;if(r.copies_a_reprendre)html+=`<div class="notice warning">${r.copies_a_reprendre} corrections resteront archivées. Les copies devront être corrigées avec la nouvelle grille.</div>`;}
 else if(stage==='copies'){const data=JSON.parse(text);html+=`<p class="help">Vous pouvez rectifier les identités, les pages et les versions ci-dessous, puis cliquer à nouveau sur « Vérifier ».</p><div class="table-wrap"><table><thead><tr><th>Copie</th><th>Élève</th><th>Version</th><th>Pages</th></tr></thead><tbody>${data.copies.map((c,i)=>`<tr><td>${esc(c.reference)}</td><td><select data-edit-copy="${i}" data-field="numero"><option value="">Non identifié</option>${state.eleves.map(e=>`<option value="${e.numero}" ${c.numero===e.numero?'selected':''}>${e.numero} — ${esc(e.prenom+' '+e.nom)}</option>`).join('')}</select></td><td><select data-edit-copy="${i}" data-field="version">${state.versions.map(v=>`<option ${c.version===v.version?'selected':''}>${esc(v.version)}</option>`).join('')}</select></td><td><input data-edit-copy="${i}" data-field="pages" aria-label="Pages ${esc(c.reference)}" value="${esc(c.pages.join(', '))}"></td></tr>`).join('')}</tbody></table></div><p class="help">Élèves sans copie repérée : ${esc(r.sans_copie_reperee.join(', ')||'aucun')}. Aucun n’est déclaré absent automatiquement.</p>`;}
 else if(stage==='correction'){html+=table(['Copie','Points','Action'],r.corrections.map(c=>[c.reference,c.note_brute+' / '+c.bareme,c.remplacement?'Remplacer la correction':'Enregistrer']));for(const c of r.a_revoir)html+=`<div class="notice warning">${esc(c.reference)} : ${esc(c.motif)}</div>`;html+=`<details><summary>Relire le détail par item et les conseils</summary><pre>${esc(text)}</pre></details>`;}
 else if(stage==='retour'){for(const key of ['generales','classe'])html+=`<h3>${key==='generales'?'Consignes générales':'Consignes de la classe'}</h3><div class="policy">${esc(r[key].apres||'(texte vide)')}</div><details open><summary>Modifications proposées</summary><pre>${esc(r[key].diff||'Aucune modification.')}</pre></details>`;}
 else html+=`<p class="success">Corrigé de la version ${esc(r.version)} prêt à enregistrer (${r.caracteres} caractères). La compilation sera vérifiée lors de la génération des fiches.</p><pre>${esc(text)}</pre>`;
 $('#preview').innerHTML=html+'</div>';
 document.querySelectorAll('[data-edit-copy]').forEach(input=>input.onchange=()=>{const data=JSON.parse(responseBody($('#response').value,'copies')),index=Number(input.dataset.editCopy),field=input.dataset.field;let value=input.value;if(field==='numero')value=value?Number(value):null;if(field==='pages')value=value.split(',').map(x=>Number(x.trim()));data.copies[index][field]=value;$('#response').value=JSON.stringify(data,null,2);$('#response').dispatchEvent(new Event('input'));});
}
async function copyText(text){if(!text){toast('La consigne n’est pas encore disponible.',true);return;}try{await navigator.clipboard.writeText(text);toast('Copié. Envoyez cette consigne dans votre conversation avec l’IA.');}catch{toast('Le navigateur refuse la copie automatique. Sélectionnez le texte puis utilisez Ctrl+C.',true);}}
function fileBase64(file){return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(new Error('Lecture du fichier impossible'));reader.readAsDataURL(file);});}
loadHome().catch(e=>{$('#main').innerHTML=`<div class="error">${esc(e.message)}</div>`;});
