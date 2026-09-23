'use strict';

function opt(values,selected,label=x=>x){return values.map(x=>`<option value="${x}" ${String(selected)===String(x)?'selected':''}>${label(x)}</option>`).join('');}
function currentLayout(){return state.layout||{correction:{size:'A6',orientation:'portrait',pages:1},corrige:{size:'A6',orientation:'portrait',pages:1,columns:1},assembly:'cote-a-cote',print_format:'auto'};}
function layoutPayload(){return {
 correction:{grid_mode:$('#l-grid-mode').value,size:$('#l-c-size').value,orientation:$('#l-c-orient').value,pages:Number($('#l-c-pages').value),newpage_after_correction:currentLayout().correction.newpage_after_correction??true},
 corrige:{size:$('#l-r-size').value,orientation:$('#l-r-orient').value,pages:Number($('#l-r-pages').value),columns:Number($('#l-r-columns').value)},
 assembly:$('#l-assembly').value,print_format:$('#l-print').value
};}
function layoutCard(stage='setup'){
 const l=currentLayout(), c=l.correction, r=l.corrige;
 const action=stage==='setup'?'<button class="primary" id="save-layout-preview">Enregistrer et voir le gabarit</button>':'<button id="save-layout">Enregistrer la mise en page</button>';
 return `<div class="card"><div class="eyebrow">1. Format de mise en page</div><h2>Correction, corrigé et impression</h2><p class="help">Choisissez le format logique de chaque partie, puis l’assemblage physique et le papier utilisé à l’impression.</p>
 <div class="field"><label for="l-grid-mode">Grille sur la fiche élève</label><select id="l-grid-mode">${opt(['questions','detaillee'],c.grid_mode||'questions',x=>x==='questions'?'Grille par question':'Grille détaillée')}</select><small>Par question : note et erreurs. Détaillée : exercices, questions et items. Les règles de correction restent invisibles.</small></div>
 <div class="row"><div class="field"><label>Correction — taille</label><select id="l-c-size">${opt(['A6','A5','A4'],c.size)}</select></div><div class="field"><label>Orientation</label><select id="l-c-orient">${opt(['portrait','paysage'],c.orientation)}</select></div><div class="field"><label>Pages dédiées</label><select id="l-c-pages">${opt([1,2,3,4],c.pages)}</select></div></div>
 <div class="row"><div class="field"><label>Corrigé — taille</label><select id="l-r-size">${opt(['A6','A5','A4'],r.size)}</select></div><div class="field"><label>Orientation</label><select id="l-r-orient">${opt(['portrait','paysage'],r.orientation)}</select></div><div class="field"><label>Pages dédiées</label><select id="l-r-pages">${opt([1,2,3,4],r.pages)}</select></div><div class="field"><label>Colonnes du corrigé</label><select id="l-r-columns">${opt([1,2],r.columns,x=>x+' colonne'+(x>1?'s':''))}</select></div></div>
 <div class="row"><div class="field"><label>Assemblage</label><select id="l-assembly"><option value="cote-a-cote" ${l.assembly==='cote-a-cote'?'selected':''}>Côte à côte</option><option value="separe" ${l.assembly==='separe'?'selected':''}>Feuilles séparées</option></select></div><div class="field"><label>Format terminal d’impression</label><select id="l-print">${opt(['auto','A6','A5','A4'],l.print_format,x=>x==='auto'?'Automatique':x)}</select></div></div>
 <div class="notice" id="layout-summary">${esc(state.layout_summary||'')}</div><div class="actions">${action}</div></div>`;
}
async function saveLayout(openPreview=false){
 await post({action:'formats',dossier:state.dossier.id,layout:layoutPayload()});
 state=await get('/api/dossier?id='+state.dossier.id);renderDossier();toast('Mise en page enregistrée.');
 if(openPreview)showLayoutPreview();
}
function bindLayout(stage='setup'){
 const b=$('#save-layout-preview')||$('#save-layout'); if(!b)return;
 b.onclick=()=>task(()=>saveLayout(stage==='setup'));
}
function pdfObj(url,title){return `<object class="pdf-viewer" data="${url}" type="application/pdf" aria-label="${esc(title)}"><div class="notice warning">Aperçu PDF indisponible ici. <a href="${url}" target="_blank" rel="noopener">Ouvrir dans un onglet ↗</a></div></object>`;}
function showLayoutPreview(){
 const url='/api/layout-preview?id='+encodeURIComponent(state.dossier.id);
 showModal(`<div class="eyebrow">Gabarit initial</div><h1>Correction vide + faux corrigé</h1><p class="lede">Le contenu est volontairement factice (Lorem ipsum). On valide ici uniquement la place disponible et le format physique.</p><div class="actions"><a href="${url}" target="_blank" rel="noopener">Ouvrir dans un onglet ↗</a></div>${pdfObj(url,'Gabarit initial')}`,true);
}

stages[0]='Préparation';
resumeStep=function(){
 const present=state.copies.filter(c=>c.statut==='present'&&!c.exclue_final);
 const lotDone=present.length&&present.every(c=>c.correction_id&&!c.a_revoir);
 if(state.dossier.termine)return 6;
 if(!state.corriges_valides&&!state.grille.length&&!state.copies.length)return 0;
 if(!state.corriges_valides)return 1;
 if(!state.grille.length)return 2;
 if(!state.copies.length)return 3;
 if(!state.dossier.echantillon_valide)return 4;
 if(!lotDone)return 5;
 return 6;
};

renderSetup=function(){
 $('#main').innerHTML=`<div class="page-head"><div><div class="eyebrow">${esc(state.dossier.classe)}</div><h1>Étape 1/7</h1><p class="lede">Préparez le format et les documents à transmettre, puis initialisez la conversation avec l’IA.</p></div><span class="badge">${esc(state.dossier.titre)}</span></div>`+
 layoutCard('setup')+
 `<div class="card"><div class="eyebrow">2. Préparation des documents</div><h2>Documents à joindre à l’IA</h2><p class="help">Aucun document n’est envoyé ni copié dans SmartCorrection à cette étape. Préparez simplement les fichiers que vous joindrez directement à la conversation IA.</p><ul class="doc-list"><li><span>▤</span><div class="grow"><strong>Copies</strong><small>Le paquet PDF complet, non découpé.</small></div></li><li><span>▤</span><div class="grow"><strong>Sujet</strong><small>Le sujet de l’évaluation, avec toutes ses versions.</small></div></li><li><span>▤</span><div class="grow"><strong>Corrigé éventuel</strong><small>Seulement s’il existe déjà.</small></div></li><li><span>▤</span><div class="grow"><strong>Documents de cours de référence</strong><small>Savoir-faire, cours, modèles de rédaction ou documents utiles.</small></div></li></ul></div>`+
 `<div class="card"><div class="eyebrow">3. Initialisation de l’IA</div><h2>Consigne à copier</h2><p class="help">Joignez les documents préparés ci-dessus directement dans la conversation IA, puis copiez cette consigne.</p><textarea id="opening" aria-label="Consigne de démarrage pour l’IA" readonly placeholder="Chargement de la consigne…"></textarea><div class="actions"><button class="primary" id="copy-opening" disabled>Copier</button></div><p class="help">Gardez cette même conversation pour toutes les étapes suivantes.</p></div><div class="notice">Les consignes générales et celles de cette classe sont intégrées automatiquement au texte copié.</div><button id="view-policies">Voir les consignes mémorisées</button>`;
 bindLayout('setup');
 loadPrompt('ouverture','#opening','#copy-opening');
 $('#view-policies').onclick=policiesModal;
};

const renderCorrigesPr18Base=renderCorrigesV2;
renderCorrigesV2=function(){
 renderCorrigesPr18Base();
 $('#main').insertAdjacentHTML('afterbegin',layoutCard('corriges'));
 bindLayout('corriges');
};

const renderGridPr18Base=renderGrid;
renderGrid=function(){
 renderGridPr18Base();
 document.querySelectorAll('#main .card').forEach(card=>{if(card.querySelector('#format-correction'))card.remove();});
 $('#main').insertAdjacentHTML('afterbegin',layoutCard('grille'));
 bindLayout('grille');
};
