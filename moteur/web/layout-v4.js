'use strict';

// PR27: keep the existing layout UI and add one correction-sheet option.
const pr27LayoutPayloadBase=layoutPayload;
layoutPayload=function(){
 const payload=pr27LayoutPayloadBase();
 const checkbox=$('#l-c-newpage');
 payload.correction.newpage_after_correction=checkbox?checkbox.checked:true;
 return payload;
};

const pr27LayoutCardBase=layoutCard;
layoutCard=function(stage='setup'){
 const html=pr27LayoutCardBase(stage);
 const layout=currentLayout();
 const enabled=layout.correction.newpage_after_correction!==false;
 const option=`<div class="field"><label><input id="l-c-newpage" type="checkbox" ${enabled?'checked':''}> Saut de page après la correction</label><small>Si activé, Conseils, Grille et éventuels éléments à vérifier commencent sur une nouvelle page.</small></div>`;
 return html.replace('<div class="notice" id="layout-summary">',option+'<div class="notice" id="layout-summary">');
};
