'use strict';

// Loaded after workflow-v2.js. Keep PDF display in one place so Firefox does not
// depend on iframe handling of application/pdf responses.
function pdfObject(url,title){
 return `<object class="pdf-viewer" data="${url}" type="application/pdf" aria-label="${esc(title)}"><div class="notice warning">Le navigateur n’affiche pas le PDF intégré. <a href="${url}" target="_blank" rel="noopener">Ouvrir le rendu dans un onglet ↗</a></div></object>`;
}

showCorrigePreview=function(){
 const url='/api/corrige-preview?id='+encodeURIComponent(state.dossier.id);
 showModal(`<div class="eyebrow">Corrigés</div><h1>Valider le rendu</h1><p class="lede">Vérifiez directement le corrigé dans le format choisi avant de l’enregistrer.</p><div class="actions"><a href="${url}" target="_blank" rel="noopener">Ouvrir dans un onglet ↗</a></div>${pdfObject(url,'Aperçu du corrigé')}`,true);
};

showGridPreviewV2=function(){
 const url='/api/grid-preview?id='+encodeURIComponent(state.dossier.id)+'&revision='+encodeURIComponent(state.dossier.revision);
 showModal(`<div class="eyebrow">Grille enregistrée</div><h1>Correction vide + corrigé</h1><p class="lede">Vérifiez la densité réelle du document avant de traiter les copies.</p><div class="actions"><a href="${url}" target="_blank" rel="noopener">Ouvrir dans un onglet ↗</a></div>${pdfObject(url,'Aperçu de la feuille de correction et du corrigé')}`,true);
};

const submitResponseBeforePr17=submitResponse;
submitResponse=async function(commit){
 const stage=$('#response')?.dataset.stage;
 const text=$('#response')?.value;
 await submitResponseBeforePr17(commit);
 // Dès que le JSON des corrigés passe la validation syntaxique/pédagogique,
 // afficher le vrai PDF. Il s'agit encore du brouillon : l'utilisateur garde
 // explicitement le bouton de validation pour l'enregistrer.
 if(!commit&&stage==='corriges'&&lastPreview&&previewText===text){
  showCorrigePreview();
 }
};

// Le cas normal est un collage depuis l'IA : supprimer le clic intermédiaire
// « Vérifier ». Le bouton reste disponible pour une saisie ou une réparation manuelle.
const bindCommonBeforePr17=bindCommon;
bindCommon=function(){
 bindCommonBeforePr17();
 const response=$('#response');
 if(response?.dataset.stage==='corriges'){
  response.addEventListener('paste',()=>setTimeout(()=>{
   if(!busy&&response.value.trim())submitResponse(false);
  },0),{once:true});
 }
};
