'use strict';

function showGridBlankPreview(){
 if(!state?.dossier?.revision)return;
 const url='/api/grid-preview?id='+encodeURIComponent(state.dossier.id)+'&revision='+encodeURIComponent(state.dossier.revision);
 showModal(`<div class="eyebrow">Grille enregistrée</div><h1>Feuille de correction vierge</h1><p class="lede">Vérifiez maintenant que les critères tiennent correctement sur la fiche. Les notes et retours sont volontairement vides.</p><div class="actions"><a href="${url}" target="_blank" rel="noopener">Ouvrir dans un onglet ↗</a></div><iframe title="Aperçu vierge de la feuille de correction" class="pdf-viewer" src="${url}"></iframe>`,true);
}

const renderGridWithoutPreview=renderGrid;
renderGrid=function(){
 renderGridWithoutPreview();
 if(!state.grille.length)return;
 const card=document.createElement('div');
 card.className='card';
 card.innerHTML='<h2>Vérifier la taille de la fiche</h2><p class="help">La feuille vierge utilise la grille enregistrée et le même format que les corrections finales.</p><div class="actions"><button id="blank-grid-preview">Voir la feuille de correction vierge</button></div>';
 $('#main').appendChild(card);
 $('#blank-grid-preview').onclick=showGridBlankPreview;
};

const submitResponseWithoutGridPreview=submitResponse;
submitResponse=async function(commit){
 const stage=$('#response')?.dataset.stage;
 const revision=state?.dossier?.revision??0;
 await submitResponseWithoutGridPreview(commit);
 if(commit&&stage==='grille'&&state?.dossier?.revision>revision)showGridBlankPreview();
};
