'use strict';

// PR20 hotfix: documents are attached directly to the IA conversation, so
// navigation must never depend on an uploaded subject inside SmartCorrection.
stages[3]='Importer le prétraitement';

const pr20GoStepBase=goStep;
goStep=async function(i){
 const next=Math.max(0,Math.min(6,i));
 if(next<=current){state=await get('/api/dossier?id='+state.dossier.id);current=next;renderDossier();window.scrollTo(0,0);return;}
 const references=current===4?sampleRefs():null;
 await task(async()=>{
  let latest=await get('/api/dossier?id='+state.dossier.id);
  if(next>1&&!latest.corriges_valides)throw new Error('Validez tous les corrigés avant de passer à la grille.');
  if(next>2&&!latest.grille.length)throw new Error('Validez la grille et son aperçu avant de poursuivre.');
  if(next>3&&!latest.copies.length)throw new Error('Importez le prétraitement des copies avant de corriger.');
  if(next>4&&(current===4||!latest.dossier.echantillon_valide)){
   const selected=references??latest.copies.filter(c=>c.echantillon).map(c=>c.reference);
   await post({action:'echantillon',dossier:latest.dossier.id,references:selected,valider:true});
   latest=await get('/api/dossier?id='+latest.dossier.id);
  }
  if(next>5){
   const pending=latest.copies.filter(c=>c.statut==='present'&&!c.exclue_final&&(!c.correction_id||c.a_revoir));
   if(pending.length)throw new Error(`${pending.length} copie(s) restent à corriger ou à revoir.`);
  }
  state=latest;current=next;renderDossier();window.scrollTo(0,0);
 });
};
