/* Drafts are kept only in memory. Planning never writes bank selections. */
(() => {
  'use strict';
  const review = $('catalogDialog'), planner = $('planDialog');
  let draftEpoch = 0, planEpoch = 0, busy = false, dirty = false, planDirty = false;
  let target, replay, image = '', origin, planOrigin, selectedManualCard;
  const node = (tag,text,cls) => { const el=document.createElement(tag); if(text!=null) el.textContent=text; if(cls) el.className=cls; return el; };
  function setCatalogBusy(on){
    busy=!!on;
    const layer=$('catalogBusy');
    if(layer) layer.hidden=!on;
    review.classList.toggle('is-busy',!!on);
    review.setAttribute('aria-busy', on?'true':'false');
    if(!on && !$('reviewForm').hidden) updateReviewFooter();
  }
  function reviewEditSummary(){const summary=node('summary',null,'review-edit-toggle'); summary.setAttribute('aria-label','Изменить'); summary.innerHTML='<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M12 20h9" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'; return summary;}
  const action = (label,fn) => {const el=node('button',label); el.type='button'; el.onclick=fn; return el;};
  const bankName = id => banks.find(b=>b.id===id)?.name || id;
  const monthAt = delta => {const now=new Date(); return new Date(Date.UTC(now.getUTCFullYear(),now.getUTCMonth()+delta,1)).toISOString().slice(0,7);};
  const periodName = month => new Intl.DateTimeFormat('ru-RU',{month:'long',year:'numeric',timeZone:'UTC'}).format(new Date(month+'-01T12:00:00Z'));
  const newKey = () => Array.from(crypto.getRandomValues(new Uint8Array(16)),b=>b.toString(16).padStart(2,'0')).join('');
  const post = (url,body,timeout) => api('/api/me/'+url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)},timeout);
  const messages = {401:'Сессия закончилась. Войдите снова.',403:'Нет доступа к этой карте.',404:'Карта не найдена. Обновите кошелёк.',409:'Условия изменились. Проверьте карту.',422:'Проверьте месяц и значения в строках.',429:'Слишком много запросов. Повторите позже.',502:'Распознавание недоступно. Попробуйте другой снимок или повторите позже.'};
  function fail(error,out) {
    setCatalogBusy(false);
    const text=error?.message||(error?.status&&messages[error.status])||(error?.name==='TimeoutError'?'Сервер не ответил вовремя. Повторите запрос.':'Не удалось выполнить запрос. Повторите.');
    out.textContent=text;
    if(error.status===401){toast(messages[401]); clearShot(); invalidatePlan(); dirty=planDirty=false; review.hidden=planner.hidden=true; $('reviewRows').replaceChildren(); if(window.expireSession) window.expireSession(); else {deviceLogin=null; $('appScreen').hidden=true; $('authScreen').hidden=true; $('welcomeScreen').hidden=false;}}
  }
  function invalidatePlan(){++planEpoch; $('planResult').replaceChildren(); $('planError').textContent=''; $('calculatePlan').disabled=false; const forecast=$('planForecast'); if(forecast){forecast.hidden=true; forecast.textContent='';}}
  function clearShot(){++draftEpoch; image=''; $('cashbackShot').value=''; $('shotPreview').textContent='Снимок из банка · JPG, PNG или WebP'; $('confirmCard').disabled=true; $('confirmCard').hidden=true; $('confirmCard').textContent='Повторить распознавание'; $('shotError').textContent='';}
  function cardOptions(){
    const bank=$('bankId').value;
    const matches=manual.filter(c=>c.bankId===bank || (!c.bankId && (c.name===bankName(bank)||c.cardId===selectedManualCard?.cardId)));
    const preferred=selectedManualCard?.cardId;
    $('cashbackCard').replaceChildren(new Option(matches.length?'Выберите карту':'Создать карту при сохранении',''));
    matches.forEach((c,i)=>$('cashbackCard').append(new Option(c.name+(matches.length>1?` · карта ${i+1}`:''),c.cardId)));
    $('cashbackCardField').hidden=matches.length<2;
    $('cashbackCard').value=matches.some(c=>c.cardId===preferred)?preferred:matches.length===1?matches[0].cardId:'';
  }
  function showStep(id,title,focus){
    for(const key of ['decisionStep','screenshotForm','reviewForm']) $(key).hidden=key!==id;
  const compact=id==='reviewForm' && $('reviewForm').dataset.density==='compact';
  review.classList.toggle('catalog-sheet', id==='screenshotForm' || compact);
  review.classList.toggle('catalog-confirm', compact);
    $('dialogTitle').textContent=title;
    $('dialogTitle').classList.toggle('is-visual', id==='screenshotForm');
    $('shotError').textContent=''; review.querySelector('.dialog-card').scrollTop=0; $(focus)?.focus?.();
  }
  function openDecision(trigger,{selectedCard=false}={}){
    origin=trigger; dirty=false; clearShot(); planner.hidden=true; review.hidden=false;
    const card=selectedCard ? activeCard() : null;
    selectedManualCard=card?.kind==='manual'?card:null;
    const bank=selectedManualCard ? walletBank(card) : null;
    if(bank) $('bankId').value=bank.id;
    cardOptions();
    if(bank && card?.cardId){
      $('cashbackCard').value=card.cardId;
      chooseActive();
    }else{
      showStep('decisionStep','Условия кэшбэка','bankId');
    }
  }
  $('addCashbackBtn').addEventListener('click',e=>openDecision(e.currentTarget,{selectedCard:true}));
  $('bankId').onchange=()=>cardOptions();
  function chooseActive(){
    const bankId=$('bankId').value, cardId=$('cashbackCard').value;
    if(!bankId || (!$('cashbackCardField').hidden && !cardId)){
      fail(new Error('Выберите банк и карту.'),$('shotError'));return;
    }
    target={bankId,cardId:cardId||undefined};
    showStep('screenshotForm','Условия кэшбэка','cashbackShot');
    const context=$('entryContext');
    context.hidden=false;
    context.textContent=bankName(bankId)+' · '+periodName(monthAt(0));
  }
  $('chooseActive').onclick=chooseActive;
  $('enterCashbackManually').onclick=()=>startReview([{selected:true}],monthAt(0),'manual');
  let discardResolver = null;
  function askDiscard(){
    return new Promise(resolve=>{
      if(!dirty){resolve(true); return;}
      const dialog=$('discardDialog');
      discardResolver=resolve;
      dialog.hidden=false;
      $('discardStay').focus();
    });
  }
  async function mayDiscard(){ return askDiscard(); }
  if($('discardStay')) $('discardStay').onclick=()=>{ $('discardDialog').hidden=true; const r=discardResolver; discardResolver=null; r?.(false); };
  if($('discardLeave')) $('discardLeave').onclick=()=>{ $('discardDialog').hidden=true; const r=discardResolver; discardResolver=null; r?.(true); };
  if($('discardDialog')) $('discardDialog').addEventListener('keydown',e=>{ if(e.key==='Escape'){ e.preventDefault(); $('discardStay').click(); }});
  $('cashbackShot').onchange=async()=>{
    clearFileState(); const token=draftEpoch,file=$('cashbackShot').files[0]; if(!file) return clearShot();
    dirty=true; $('shotPreview').textContent='Читаем снимок…';
    try{if(file.size>4000000) throw new Error('Снимок больше 4 МБ'); const data=await readShot(file); if(token!==draftEpoch)return;
      image=data; const img=node('img'); img.alt='Предпросмотр снимка'; img.src=image; $('shotPreview').replaceChildren(img); $('confirmCard').disabled=false; $('confirmCard').hidden=false; $('confirmCard').textContent='Отправить на распознавание';
    }catch(e){if(token===draftEpoch){$('shotPreview').textContent='Выберите другой снимок'; fail(e,$('shotError'));}}
  };
  function clearFileState(){++draftEpoch; image=''; $('confirmCard').disabled=true; $('confirmCard').hidden=true; $('confirmCard').textContent='Повторить распознавание'; $('shotError').textContent='';}
  $('screenshotForm').onsubmit=e=>{e.preventDefault(); void recognizeShot();};
  async function recognizeShot(){
    if(!image || $('confirmCard').disabled)return;
    const token=++draftEpoch;
    $('confirmCard').disabled=true; setCatalogBusy(true); $('shotError').textContent='';
  try{
      const data=await post('cashback-screenshot',{...target,image},45000);
      if(token===draftEpoch)startReview(data.rules,data.month,'shot');
    }catch(err){
      if(token===draftEpoch){fail(err,$('shotError')); $('confirmCard').hidden=false; $('confirmCard').textContent='Повторить распознавание';}
    }finally{
      if(token===draftEpoch){$('confirmCard').disabled=false; setCatalogBusy(false);}
    }
  }
  function labelled(parent,title,control,cls){const label=node('label',title,cls); label.append(control); parent.append(label); return control;}
  function input(parent,key,title,value,cls){const field=node('input'); field.dataset.key=key; field.value=value??''; return labelled(parent,title,field,cls);}
  function formatRateText(bps){ if(bps==null||bps==='') return null; return (Number(bps)/100).toLocaleString('ru-RU',{maximumFractionDigits:2})+'%'; }
  function syncMonthText(){
    const value=$('reviewMonth').value;
    const text=$('reviewMonthText');
    if(!text) return;
    text.textContent=value?periodName(value).replace(/\s*г\.?$/,'').replace(/^./,c=>c.toUpperCase()):'Выберите месяц';
    text.classList.toggle('is-empty', !value);
  }
  function updateReviewFooter(){
    const compact=$('reviewForm').dataset.density==='compact';
    const boxes=[...$('reviewRows').children];
    let selected=0, needRate=false;
    boxes.forEach(box=>{
      const fields=Object.fromEntries([...box.querySelectorAll('[data-key]')].map(f=>[f.dataset.key,f]));
      if(!fields.include?.checked) return;
      selected+=1;
      const rateField=fields.rateBps;
      if(!rateField) return;
      const empty=!(rateField.value||'').trim();
      if(rateField.classList.contains('needs-input') && empty) needRate=true;
      else if(!compact && empty) needRate=true;
    });
    if($('reviewCount')) $('reviewCount').textContent=`Выбрано: ${selected}`;
    const needs=[];
    if(!$('reviewMonth').value) needs.push('укажите месяц');
    if(!selected) needs.push('отметьте категорию');
    if(needRate) needs.push('укажите ставку');
    const ready=!needs.length && !busy;
    const need=$('reviewNeed');
    if(need){
      need.textContent=needs.length?'Нужно: '+needs.join(', '):'';
      need.hidden=compact && !needs.length;
    }
    const save=$('saveReview');
    save.disabled=!ready;
    save.classList.toggle('is-ready', ready);
    save.setAttribute('aria-disabled', ready?'false':'true');
  }
  function canCompactReview(rules, kind){
    return kind==='shot' && rules.length>0;
  }
  function compactRow(rule={}){
    const box=node('div',null,'review-row review-row-compact');
    if(rule.uncertain) box.classList.add('is-uncertain');
    const head=node('div',null,'review-row-head');
    const title=node('div',null,'review-row-title');
    const labelText=rule.label || categories[rule.categoryId] || 'Категория';
    const rate=formatRateText(rule.rateBps);
    const name=node('strong', rate?`${labelText} · ${rate}`:labelText);
    if(rule.uncertain && rate) name.append(document.createTextNode(' · проверьте'));
    title.append(name);
    const include=node('input'); include.type='checkbox'; include.dataset.key='include'; include.checked=rule.rateBps!=null && rule.selected!==false;
    const includeLabel=node('label','Подключена','review-check review-check-compact');
    includeLabel.prepend(include);
    const details=node('details',null,'review-details review-details-compact');
    details.append(reviewEditSummary());
    const grid=node('div',null,'cb-fields'); details.append(grid);
    head.append(title, details, includeLabel); box.append(head);
    const label=input(grid,'label','Название в банке',rule.label,'wide'); label.maxLength=80;
    label.addEventListener('input',()=>{ const r=formatRateText(rateField.value===''?null:Number(String(rateField.value).replace(',','.'))*100); name.textContent=[label.value.trim()||'Категория', r].filter(Boolean).join(' · '); updateReviewFooter(); });
    const category=input(grid,'categoryId','Категория для расчёта',rule.categoryId||'','wide'); category.setAttribute('list','cbCategoryIds'); category.maxLength=80;
    const rateField=input(grid,'rateBps','Ставка, %',rule.rateBps==null?'':rule.rateBps/100); rateField.inputMode='decimal';
    if(rule.rateBps==null){ rateField.required=true; rateField.placeholder='Укажите ставку'; rateField.classList.add('needs-input'); }
    rateField.addEventListener('input',()=>{ const r=formatRateText(rateField.value===''?null:Number(String(rateField.value).replace(',','.'))*100); name.textContent=[label.value.trim()||'Категория', r||'ставка ?'].filter(Boolean).join(' · '); updateReviewFooter(); });
    input(grid,'limitKopecks','Лимит кэшбэка, ₽',rule.limitKopecks==null?'':rule.limitKopecks/100);
    input(grid,'minAmountKopecks','Минимальная сумма покупки, ₽',rule.minAmountKopecks==null?'':rule.minAmountKopecks/100);
    include.addEventListener('change',updateReviewFooter);
    validityFields(grid,rule);
    $('reviewRows').append(box); return include;
  }
  function validityFields(container,rule){
    for(const [key,label] of [['validFrom','Действует с'],['validThrough','Действует по включительно']]){
      const field=input(container,key,label,rule[key]);
      field.type='date';
    }
  }
  function row(rule={}, open=false){
    const box=node('fieldset','','review-row');
    const head=node('div',null,'review-row-head');
    const title=node('div',null,'review-row-title');
    const name=node('strong', rule.label || categories[rule.categoryId] || 'Новая категория');
    const meta=[]; const rate=formatRateText(rule.rateBps); if(rate) meta.push(rate);
    if(rule.limitKopecks!=null) meta.push('лимит '+(rule.limitKopecks/100).toLocaleString('ru-RU')+' ₽');
    if(!rate) meta.push('ставка не указана');
    const summary=node('span', meta.join(' · '), 'review-row-meta');
    title.append(name, summary);
    const include=node('input'); include.type='checkbox'; include.dataset.key='include'; include.checked=rule.selected===true;
    const includeLabel=node('label','Подключена','review-check');
    includeLabel.prepend(include);
    head.append(title, includeLabel); box.append(head);
    if(rule.uncertain) box.append(node('p','Проверьте неуверенно распознанные поля.','cb-warning'));
    const details=node('details',null,'review-details');
    details.open=open;
    details.append(node('summary','Подробнее'));
    const grid=node('div',null,'cb-fields'); details.append(grid);
    const label=input(grid,'label','Название в банке',rule.label,'wide'); label.maxLength=80;
    label.addEventListener('input',()=>{ name.textContent=label.value.trim()||'Новая категория'; updateReviewFooter(); });
    const category=input(grid,'categoryId','Категория для расчёта',rule.categoryId||'','wide'); category.setAttribute('list','cbCategoryIds'); category.maxLength=80;
    const rateField=input(grid,'rateBps','Ставка, %',rule.rateBps==null?'':rule.rateBps/100); rateField.inputMode='decimal';
    if(rule.rateBps==null){ rateField.required=true; rateField.placeholder='Укажите ставку'; rateField.classList.add('needs-input'); }
    rateField.addEventListener('input',()=>{
      const formatted=formatRateText(rateField.value===''?null:Number(String(rateField.value).replace(',','.'))*100);
      summary.textContent=[formatted||'ставка не указана', rule.limitKopecks!=null?('лимит '+(rule.limitKopecks/100).toLocaleString('ru-RU')+' ₽'):null].filter(Boolean).join(' · ');
      updateReviewFooter();
    });
    const limit=input(grid,'limitKopecks','Лимит кэшбэка, ₽',rule.limitKopecks==null?'':rule.limitKopecks/100); limit.inputMode='decimal'; limit.placeholder='Не указан';
    const minimum=input(grid,'minAmountKopecks','Минимальная сумма покупки, ₽',rule.minAmountKopecks==null?'':rule.minAmountKopecks/100); minimum.inputMode='decimal'; minimum.placeholder='Не указана';
    if(rule.uncertain){
      const warn=node('p','Значение распознано неуверенно — сверьте со снимком.','cb-warning');
      rateField.parentElement.append(warn.cloneNode(true));
    }
    validityFields(grid,rule);
    box.append(details);
    include.addEventListener('change',updateReviewFooter);
    box.append(action('Убрать строку',()=>{dirty=true; box.remove(); updateReviewFooter(); $('addRule').focus();}));
    $('reviewRows').append(box); return label;
  }
  function startReview(rules,month,kind){
    if(!Array.isArray(rules))throw new Error('Сервер не вернул список условий.');
    clearShot(); dirty=kind==='shot'; replay=null; $('reviewRows').replaceChildren();
    const cardLabel=manual.find(c=>c.cardId===$('cashbackCard').value)?.name || bankName(target.bankId);
    const bank=bankName(target.bankId);
    const same=bank===cardLabel || cardLabel.startsWith(bank+' ');
    $('reviewContext').textContent=same?cardLabel:`${bank} · ${cardLabel}`;
    const compactReview=canCompactReview(rules, kind);
    month=month||monthAt(0);
    $('reviewMonth').value=month || ''; syncMonthText();
    if($('reviewWarnings')){ $('reviewWarnings').hidden=true; $('reviewWarnings').textContent=''; }
    const compact=compactReview;
    $('reviewForm').dataset.density=compact?'compact':'full';
    if($('addRule')) $('addRule').hidden=compact;
    const hint=$('reviewHint');
    if(hint){
      hint.hidden=compact;
      hint.textContent='Укажите ставку. Лимит и даты в пределах выбранного месяца можно оставить пустыми.';
    }
    if($('reviewCount')) $('reviewCount').hidden=compact;
  const monthWrap=$('reviewMonth')?.closest('.review-month');
  if(monthWrap) monthWrap.classList.toggle('is-compact', compact);
  if(compact && month){ $('reviewMonth').classList.add('is-collapsed'); } else { $('reviewMonth')?.classList.remove('is-collapsed'); }
    $('saveReview').textContent=compact?'Сохранить':'Сохранить категории';
    const fields=rules.map(rule=>compact?compactRow(rule):row(rule,kind==='manual'));
    setCatalogBusy(false);
    updateReviewFooter();
    showStep('reviewForm',compact?'Всё верно?':'Ввести кэшбэк вручную','reviewMonthText');
    if(kind==='manual') fields[0]?.focus();
  }
  $('reviewForm').oninput=()=>{dirty=true; updateReviewFooter();};
  $('reviewMonth').addEventListener('change',()=>{dirty=true; syncMonthText(); updateReviewFooter();});
  $('addRule').onclick=()=>{dirty=true;row({selected:true},true).focus(); updateReviewFooter();};
  function hundredths(raw,fallback,name){const text=raw.trim(); if(!text && fallback!==undefined)return fallback; if(!/^\d+(?:[.,]\d{1,2})?$/.test(text))throw new Error(`Проверьте поле «${name}».`); const [whole,part='']=text.split(/[.,]/),value=Number(whole)*100+Number(part.padEnd(2,'0')); if(!Number.isSafeInteger(value))throw new Error(`Слишком большое значение: ${name}.`); return value;}
  $('reviewForm').onsubmit=async e=>{
    e.preventDefault(); if(busy)return; updateReviewFooter(); if($('saveReview').disabled) return;
    try{const rules=[]; for(const box of $('reviewRows').children){const fields=Object.fromEntries([...box.querySelectorAll('[data-key]')].map(f=>[f.dataset.key,f])); if(!fields.include.checked)continue;
      const label=fields.label.value.trim(); if(!label)throw new Error('Укажите название категории, как в банке.'); const rateBps=hundredths(fields.rateBps.value,undefined,'Ставка'); if(rateBps>10000)throw new Error('Ставка не может превышать 100 %.');
      rules.push({label,categoryId:fields.categoryId.value.trim() || label,rateBps,limitKopecks:hundredths(fields.limitKopecks.value,null,'Лимит'),minAmountKopecks:hundredths(fields.minAmountKopecks.value,1,'Минимальная покупка'),validFrom:fields.validFrom.value||null,validThrough:fields.validThrough.value||null,selected:true,uncertain:false});
    }
    if(!rules.length)throw new Error('Отметьте хотя бы одну проверенную строку.');
    const body={...target,month:$('reviewMonth').value,mode:'active',slots:null,rules};
    const signature=JSON.stringify(body); if(replay?.signature!==signature)replay={signature,key:newKey()};
    setCatalogBusy(true); $('saveReview').disabled=true; $('shotError').textContent='';
    const response=await post('cashback-confirm',{...body,requestId:replay.key});
    walletPreferredCard=response.cardId || target.cardId || walletPreferredCard;
    setCatalogBusy(false);
    dirty=false;
    await closeReview(true);
    try{await load();}catch(loadErr){toast(loadErr.message||'Не удалось обновить кошелёк');}
    invalidatePlan();
    walletRoute('cards', true);
    toast('Категории сохранены');
    }catch(err){fail(err,$('shotError')||$('reviewNeed'));}finally{setCatalogBusy(false); $('saveReview').disabled=false; $('saveReview').textContent=$('reviewForm').dataset.density==='compact'?'Сохранить':'Сохранить категории'; updateReviewFooter();}
  };
  async function closeReview(force){
    if(busy) return false;
    if(!force && !(await mayDiscard())) return false;
    dirty=false; clearShot(); review.hidden=true; $('reviewRows').replaceChildren();
    const focusEl=(origin?.isConnected&&!origin.hidden)?origin:(!$('addCashbackBtn').hidden?$('addCashbackBtn'):$('openCatalog'));
    focusEl?.focus();
    return true;
  }
  function closePlanner(){
    if(planDirty && !window.confirm('Закрыть план? Введённые расходы не сохранятся.'))return false;
    planDirty=false; invalidatePlan(); planner.hidden=true;
    if(planOrigin?.isConnected && !$('cashbackOverview')?.closest('[hidden]')) planOrigin.focus();
    else if(typeof walletRoute==='function') walletRoute('cashback', true);
    else ($('openPlan')||planOrigin)?.focus();
    return true;
  }
  $('closeCatalog').onclick=()=>{setCatalogBusy(false); closeReview();}; $('closePlan').onclick=closePlanner;
  window.walletCashbackBack=()=>{
    if(!review.hidden){setCatalogBusy(false); void closeReview(true);return true;}
    const discard=$('discardDialog');
    if(discard&&!discard.hidden){$('discardStay').click();return true;}
    if(!planner.hidden){closePlanner();return true;}
    return false;
  };
  window.addEventListener('beforeunload',e=>{if(dirty || planDirty){e.preventDefault(); e.returnValue='';}});
  for(const [dialog,close] of [[review,closeReview],[planner,closePlanner]]){dialog.onclick=e=>{if(e.target===dialog)close();}; dialog.onkeydown=e=>{
    if(e.key==='Escape'){e.preventDefault();e.stopPropagation();close();return;} if(e.key!=='Tab')return;
    const items=[...dialog.querySelectorAll('button,input,select')].filter(x=>!x.disabled && x.getClientRects().length && !x.closest('[inert]'));
    if(!items.length)return; if(e.shiftKey && document.activeElement===items[0]){e.preventDefault();items.at(-1).focus();}else if(!e.shiftKey && document.activeElement===items.at(-1)){e.preventDefault();items[0].focus();}
  };}
  const list=node('datalist'); list.id='cbCategoryIds'; document.body.append(list);
  function syncCategories(){list.replaceChildren(...Object.entries(categories).map(([id,name])=>new Option(name,id)));}
  document.addEventListener('wallet-updated',()=>{syncCategories(); invalidatePlan();}); syncCategories();
  function spendRow(){const wrap=node('div',null,'cb-fields');
    const cat=labelled(wrap,'Категория покупки',node('select'));
    cat.dataset.key='categoryId';
    cat.append(new Option('Выберите категорию',''),...Object.entries(categories).map(([id,name])=>new Option(name,id))); const amount=input(wrap,'amount','Сумма, ₽','');amount.inputMode='decimal';wrap.append(action('Убрать покупку',()=>{wrap.remove();planDirty=true;invalidatePlan();$('addSpend').focus();})); $('spendRows').append(wrap);return cat;}
  function switchSource(){const manualInput=$('spendingSource').value==='manual';$('spendingInputs').hidden=!manualInput; $('spendingPeriod').hidden=manualInput; $('spendingMonth').disabled=manualInput; invalidatePlan();}
  function setPlanMonth(delta){
    $('planMonth').value=monthAt(delta);
    $('planMonthText').textContent=periodName($('planMonth').value);
    $('planCurrent').setAttribute('aria-pressed',String(delta===0));
    $('planNext').setAttribute('aria-pressed',String(delta===1));
    invalidatePlan();
  }
  $('openPlan').onclick=e=>{planOrigin=e.currentTarget;planDirty=false;invalidatePlan(); planner.hidden=false; setPlanMonth(1); $('spendingMonth').value=monthAt(0); $('spendingSource').value='history';switchSource();
    const rows=node('div');rows.id='spendRows';const add=action('Добавить покупку',()=>spendRow().focus());add.id='addSpend'; $('spendingInputs').replaceChildren(node('p','Одна строка — один чек. Для нескольких покупок одной категории добавьте несколько строк.','cb-note'),rows,add);spendRow(); planner.querySelector('.dialog-card').scrollTop=0; $('planNext').focus();};
  $('spendingSource').onchange=switchSource;
  $('planForm').oninput=e=>{if($('spendingInputs').contains(e.target))planDirty=true;invalidatePlan();};
  for(const [id,delta] of [['planCurrent',0],['planNext',1]])$(id).onclick=()=>setPlanMonth(delta);
  function showPlan(data,body){const host=$('planResult'),month=body.month,warnings=data.warnings||[];
    const title=node('h3','Прогноз · '+periodName(month)); title.tabIndex=-1; host.replaceChildren(title,node('p','Источник: '+(body.spending?'Ручной ввод · покупок: '+body.spending.length:'История покупок · '+periodName(body.spendingMonth)),'cb-note'));
    const noSpend=warnings.some(w=>w.startsWith('Нет расходов')),noTerms=warnings.some(w=>w.startsWith('Нет подтверждённых условий'));
    if(!noSpend && !noTerms){const forecast=$('planForecast'); if(forecast && data.projectedKopecks!=null){forecast.hidden=false; forecast.textContent='По плану '+money(data.projectedKopecks);} const metrics=node('dl');for(const [caption,value] of [['Сейчас',data.baseKopecks],['По плану',data.projectedKopecks],['Разница',data.gainKopecks]]){const v=node('dd',money(value));v.dataset.kopecks=value;metrics.append(node('dt',caption),v);}host.append(metrics);}
    if(warnings.some(w=>w.includes('Перебор ограничен')))host.append(node('strong','Приблизительный план'));
    if(!data.choices.length && !noSpend && !noTerms)host.append(node('p','Дополнительных категорий с известным приростом нет.'));
    for(const choice of data.choices){const group=node('article');group.append(node('h3',bankName(choice.bankId)),node('p',`Для плана: ${choice.labels.length} мест.`));const names=node('ul');choice.labels.forEach(name=>names.append(node('li',name)));group.append(names,node('p','Сначала подключите эти категории в приложении банка.','cb-note'));host.append(group);}
    for(const warning of warnings)host.append(node('p',warning,'cb-warning'));
    if(noSpend)host.append(action('Ввести расходы',()=>{$('spendingSource').value='manual';switchSource();$('spendRows').querySelector('input')?.focus();}));
    title.focus();
  }
  $('planForm').onsubmit=async e=>{e.preventDefault(); if($('calculatePlan').disabled)return;invalidatePlan();const token=planEpoch;
    try{const body={month:$('planMonth').value,spendingMonth:$('spendingMonth').value || monthAt(0)};
      if($('spendingSource').value==='manual'){body.spending=[];for(const r of $('spendRows').children){const cat=r.querySelector('[data-key=categoryId]'),amt=r.querySelector('[data-key=amount]');if(!cat.value.trim() && !amt.value.trim())continue;
        if(!cat.value.trim())throw new Error('Введите категорию покупки.');const amountKopecks=hundredths(amt.value,undefined,'Сумма');if(!amountKopecks)throw new Error('Сумма должна быть больше нуля.');const value=cat.value.trim(),cid=Object.keys(categories).find(k=>categories[k].toLowerCase()===value.toLowerCase()) || value;body.spending.push({categoryId:cid,amountKopecks});}
        if(!body.spending.length)throw new Error('Введите хотя бы одну покупку.');}
      $('calculatePlan').disabled=true; $('planResult').textContent='Сравниваем предложения банков…';const data=await post('cashback-plan',body,45000); if(token===planEpoch)showPlan(data,body);
    }catch(err){if(token===planEpoch){$('planResult').replaceChildren();fail(err,$('planError'));}}finally{if(token===planEpoch)$('calculatePlan').disabled=false;}
  };
  window.openCashbackDecision=trigger=>openDecision(trigger);
})();
