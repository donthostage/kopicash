/* Navigation, cards, history and account. Checkout stays in checkout.js.
   Taiga UI patterns, adapted to this page: drawer (add/import/delete), combobox (bank search),
   accordion rows (history), button hierarchy and toast. */
let walletPreferredCard = null, walletReturn = null, deleteTarget = null, addReturn = null, bankSuggest = -1, historyMonth = null;
let usualCardId = null, usualCardBusy = false, renderedCardId = null;
const shellRoutes = ['home', 'buy', 'cards', 'cashback', 'history', 'account'];
const DEMO_DECK = [
  {cardId:'demo-sber', name:'Сбер', demo:true, paint:{color:'#21A038', ink:'#ffffff', accent:'#d8f5e0'}, rules:[{label:'Транспорт', categoryId:'transport', rateBps:1500},{label:'Кафе', categoryId:'cafe', rateBps:400},{label:'Все покупки', categoryId:'all', rateBps:100}]},
  {cardId:'demo-tbank', name:'Т-Банк', demo:true, paint:{color:'#FFDD2D', ink:'#1D1E1A', accent:'#1D1E1A'}, rules:[{label:'Супермаркеты', categoryId:'supermarkets', rateBps:500},{label:'Кафе', categoryId:'cafe', rateBps:700},{label:'Все покупки', categoryId:'all', rateBps:100}]},
  {cardId:'demo-alfa', name:'Альфа-Банк', demo:true, paint:{color:'#EF3124', ink:'#ffffff', accent:'#ffd0cc'}, rules:[{label:'Кафе', categoryId:'cafe', rateBps:700},{label:'АЗС', categoryId:'fuel', rateBps:500},{label:'Все покупки', categoryId:'all', rateBps:100}]},
  {cardId:'demo-vtb', name:'ВТБ', demo:true, paint:{color:'#002882', ink:'#ffffff', accent:'#c9d4ff'}, rules:[{label:'Транспорт', categoryId:'transport', rateBps:1000},{label:'Аптеки', categoryId:'pharmacy', rateBps:500},{label:'Все покупки', categoryId:'all', rateBps:100}]},
  {cardId:'demo-ozon', name:'Ozon', demo:true, paint:{color:'#005BFF', ink:'#ffffff', accent:'#d6e4ff'}, rules:[{label:'Одежда', categoryId:'clothes', rateBps:500},{label:'Супермаркеты', categoryId:'supermarkets', rateBps:300},{label:'Все покупки', categoryId:'all', rateBps:100}]},
  {cardId:'demo-akbars', name:'Ак Барс', demo:true, paint:{color:'#00915A', ink:'#ffffff', accent:'#d2f5e4'}, rules:[{label:'АЗС', categoryId:'fuel', rateBps:700},{label:'Кафе', categoryId:'cafe', rateBps:400},{label:'Все покупки', categoryId:'all', rateBps:100}]},
  {cardId:'demo-gpb', name:'Газпромбанк', demo:true, paint:{color:'#1F4E9D', ink:'#ffffff', accent:'#d5e2ff'}, rules:[{label:'АЗС', categoryId:'fuel', rateBps:1000},{label:'Транспорт', categoryId:'transport', rateBps:500},{label:'Все покупки', categoryId:'all', rateBps:100}]}
];
const categoryIconPaths={
  supermarkets:'M2 3h3l3 13h12l2-10H6 M9 19a1.5 1.5 0 1 0 .1 0 M18 19a1.5 1.5 0 1 0 .1 0',
  cafe:'M3 8h14v5a6 6 0 0 1-6 6H9a6 6 0 0 1-6-6z M17 9h2a3 3 0 0 1 0 6h-2 M3 22h16 M7 3v2 M12 2v3',
  fuel:'M3 21V4a1 1 0 0 1 1-1h9a1 1 0 0 1 1 1v17 M2 21h14 M6 6h5v5H6z M14 12h2a2 2 0 0 1 2 2v3a2 2 0 0 0 4 0V9l-4-4 M20 7v3h2',
  pharmacy:'M8 3h8v5h5v8h-5v5H8v-5H3V8h5z',
  transport:'M5 17V6q0-3 7-3t7 3v11q0 2-2 2H7q-2 0-2-2z M5 11h14 M8 15h1 M15 15h1 M7 20l-2 2 M17 20l2 2',
  clothes:'M8 3q4 4 8 0l6 4-3 5-3-2v11H8V10l-3 2-3-5z', clothing:'M8 3q4 4 8 0l6 4-3 5-3-2v11H8V10l-3 2-3-5z',
  electronics:'M3 4h18v13H3z M12 17v4 M8 21h8', marketplace:'M3 8l3-5h12l3 5v2q-2 3-4 0-3 3-5 0-3 3-5 0-2 3-4 0z M5 13v8h14v-8',
  entertainment:'M3 7l16-5 2 5-16 5z M4 12h17v9H4z M8 6l3 3 M14 4l3 3', utilities:'M13 2L5 14h6l-1 8 9-13h-7z',
  travel:'M3 8h18v13H3z M9 8V4h6v4 M7 9v11 M17 9v11', all:'M2 5h20v14H2z M3 10h18 M6 15h3',
  other:'M3 5h12l7 7-10 10-9-9z M7 9h1'
};
function categoryIconSvg(id){
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
  svg.setAttribute('viewBox','0 0 24 24');
  svg.setAttribute('aria-hidden','true');
  const path=document.createElementNS('http://www.w3.org/2000/svg','path');
  path.setAttribute('d', categoryIconPaths[id]||categoryIconPaths.other);
  svg.append(path);
  return svg;
}
function walletCount(n){return n===1?'1 карта':n>1&&n<5?`${n} карты`:`${n} карт`;}
function rubFromField(text){
  const raw=String(text||'').trim();
  if(!raw) throw new Error('Введите сумму');
  if(!/^\d+(?:[.,]\d{1,2})?$/.test(raw)) throw new Error('Проверьте сумму');
  const [whole,part='']=raw.split(/[.,]/);
  return Number(whole)*100+Number(part.padEnd(2,'0'));
}
function rubDisplay(kopecks){return (kopecks/100).toLocaleString('ru-RU',{minimumFractionDigits:kopecks%100?'2':0,maximumFractionDigits:2});}
function renderAccountIdentity(){
  const login=(deviceLogin||'').trim();
  const guest=!login;
  $('accountAvatar').textContent=guest?'Г':Array.from(login)[0].toLocaleUpperCase('ru-RU');
  $('settingsUser').textContent=guest?'Гость':`@${login}`;
}
function walletBank(card){
  const key=(card?.bankId||card?.name||card?.cardName||'').toString().toLowerCase().replace(/[^a-zа-я0-9]/gi,'');
  return banks.find(bank=>bank.id===card?.bankId || bank.name===(card?.name||card?.cardName) || bank.name.toLowerCase().replace(/[^a-zа-я0-9]/gi,'')===key) || null;
}
function walletBankLogo(card){
  if(card?.demo && typeof card.cardId==='string' && card.cardId.startsWith('demo-')){
    const hit=banks.find(bank=>bank.id===card.cardId.slice(5));
    if(hit?.logo) return hit.logo;
  }
  const bank=walletBank(card);
  return bank?.logo || null;
}
window.walletBankLogo=walletBankLogo;
function carouselCardLogoMarkup(card){
  const logo=walletBankLogo(card);
  const letter=escapeHtml((card?.cardName||card?.name||'?').charAt(0));
  if(logo) return `<span class="carousel-card-logo has-img" aria-hidden="true"><img src="${escapeHtml(logo)}" alt="" width="31" height="31" decoding="async" loading="lazy"></span>`;
  return `<span class="carousel-card-logo" aria-hidden="true">${letter}</span>`;
}
window.carouselCardLogoMarkup=carouselCardLogoMarkup;
function walletCardCaption(card){
  const rules=card.rules||[];
  if(!rules.length) return 'Добавить условия';
  const best=rules.reduce((a,b)=>b.rateBps>a.rateBps?b:a);
  return `${best.label||categories[best.categoryId]||best.categoryId} ${formatRate(best.rateBps)}%`;
}
function ruleLine(rule){return `${rule.label||categories[rule.categoryId]||rule.categoryId} · ${formatRate(rule.rateBps)}%`;}
function ruleEditor(card, rule, name){
  const details=document.createElement('details');
  const trigger=document.createElement('summary');
  trigger.textContent='Изменить '+name;
  const form=document.createElement('form'); form.className='shot-form';
  const title=document.createElement('input'); title.value=name; title.required=true; title.maxLength=80;
  const rate=document.createElement('input'); rate.value=formatRate(rule.rateBps); rate.inputMode='decimal'; rate.required=true;
  const limit=document.createElement('input'); limit.inputMode='decimal'; limit.placeholder='Не указан';
  if(rule.limitKopecks!=null) limit.value=rubDisplay(rule.limitKopecks);
  const from=document.createElement('input'); from.type='date'; from.value=rule.validFrom||'';
  const through=document.createElement('input'); through.type='date'; through.value=rule.validThrough||'';
  const label=(text,field)=>{const item=document.createElement('label'); item.textContent=text; item.append(field); return item;};
  const save=document.createElement('button'); save.textContent='Сохранить'; save.type='submit'; save.className='buy-primary';
  const hint=document.createElement('p'); hint.className='cb-note';
  hint.textContent=rule.month?`Лимит и даты необязательны. Даты можно указать в пределах месяца «${monthTitle(rule.month)}».`:
    'Лимит и даты можно оставить пустыми.';
  const error=document.createElement('p'); error.setAttribute('role','status');
  form.append(label('Название категории',title),label('Ставка, %',rate),label('Лимит кэшбэка, ₽',limit),
    label('Действует с',from),label('Действует по включительно',through),hint,save,error);
  form.onsubmit=async event=>{
    event.preventDefault();
    const parsed=checkout.parseAmount(rate.value,true);
    if(parsed.value==null || parsed.value>10000){error.textContent='Введите ставку от 0 до 100 %.';return;}
    const limitValue=limit.value.trim()?checkout.parseAmount(limit.value,true).value:null;
    if(limit.value.trim() && limitValue==null){error.textContent='Введите лимит в рублях.';return;}
    save.disabled=true; error.textContent='';
    try{
      await api('/api/me/manual-cards/'+encodeURIComponent(card.cardId)+'/rate',{
        method:'PATCH',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({categoryId:rule.categoryId,label:rule.label??null,
          source:rule.source==='active'?'active':'base',month:rule.month,newLabel:title.value.trim(),rateBps:parsed.value,
          limitKopecks:limitValue,validFrom:from.value||null,validThrough:through.value||null})
      });
      await load(); toast('Условия обновлены');
    }catch(failure){error.textContent=failure.message;}finally{save.disabled=false;}
  };
  details.append(trigger,form);
  return details;
}
function renderWalletCardDetails(card){
  const host=$('carouselSummary'); if(!host) return; host.replaceChildren();
  const title=document.createElement('p');
  title.className='carousel-bank-title';
  title.textContent=card.cardName||card.name;
  host.append(title);
  if(card.demo){
    host.append(Object.assign(document.createElement('p'),{className:'carousel-demo-note',textContent:'Ставки демонстрационные'}));
  }
  const rules=card.rules||[];
  const list=$('carouselCategories');
  if(list){
    list.replaceChildren();
    list.hidden=!rules.length;
    rules.forEach(rule=>{
      const li=document.createElement('li');
      const catId=rule.categoryId||'other';
      const name=rule.label||categories[catId]||catId;
      const main=document.createElement('span'); main.className='carousel-cat-main';
      const mark=document.createElement('span'); mark.className='carousel-cat-mark'; mark.append(categoryIconSvg(catId));
      const nameEl=document.createElement('span'); nameEl.className='carousel-cat-name'; nameEl.textContent=name;
      main.append(mark, nameEl);
      li.append(main, Object.assign(document.createElement('span'),{className:'carousel-cat-rate',textContent:`${formatRate(rule.rateBps)}%`}));
      list.append(li);
      if(card.kind==='manual' && !card.demo){
        const editor=document.createElement('li');
        editor.className='carousel-rule-editor';
        const terms=[rule.limitKopecks==null?'':`На покупку до ${money(rule.limitKopecks)}`];
        const dateText=value=>value.split('-').reverse().join('.');
        if(rule.validFrom) terms.push(`с ${dateText(rule.validFrom)}`);
        if(rule.validThrough) terms.push(`по ${dateText(rule.validThrough)} включительно`);
        if(terms.some(Boolean)) editor.append(Object.assign(document.createElement('p'),{
          className:'carousel-rule-terms',textContent:terms.filter(Boolean).join(' · '),
        }));
        editor.append(ruleEditor(card,rule,name)); list.append(editor);
      }
    });
  }
  const hint=$('carouselEmptyHint');
  if(hint) hint.hidden=!!rules.length || document.documentElement.dataset.demo==='cards';
  const cashback=$('addCashbackBtn');
  if(cashback){
    cashback.hidden=false;
    $('addCashbackLabel').textContent=rules.length?'Обновить категории':'Добавить категории';
    cashback.disabled=!card;
  }
  if($('cardActions')) $('cardActions').hidden=!card;
  const currentCardId=card?.cardId??null;
  if(renderedCardId!==currentCardId) $('cardSettings').open=false;
  renderedCardId=currentCardId;
  syncUsualCard(card);
  if($('deleteActiveBtn')) $('deleteActiveBtn').disabled=!card;
}
const carouselPos={value:0,target:0,all:[]};
const homeCarouselPos={value:0,target:0,all:[]};
const walletCarousel=createCardCarousel({
  root:$('cardCarousel'), track:$('carouselTrack'), state:carouselPos, onChange:updateCarouselDetails,
});
const homeCarousel=createCardCarousel({
  root:$('homeCarousel'), track:$('homeCarouselTrack'), state:homeCarouselPos, onChange:updateHomeCarousel, onOpen:openHomeCard,
});
function syncUsualCard(card){
  const button=$('makeUsualBtn');
  const selected=!!card && usualCardId===card.cardId;
  button.disabled=!card || usualCardBusy;
  button.setAttribute('aria-pressed',String(selected));
  button.setAttribute('aria-describedby','usualCardHelp');
  $('usualCardHelp').textContent=selected
    ?'Эта карта взята за основу для сравнения новых покупок.'
    :'В статистике увидите, сколько вернулось бы, если бы вы оплатили этой картой.';
}
function activeCard(){ return walletCarousel.selected(); }
let limitsCardId=null, limitsRequest=0;
function renderCardLimits(card, endpoint, data, ticket){
  const host=$('cardLimitsBody');
  const form=document.createElement('form');
  const formatMonth=new Intl.DateTimeFormat('ru-RU',{month:'long',year:'numeric',timeZone:'UTC'});
  const month=formatMonth.format(new Date(data.month+'-01T00:00:00Z'));
  const note=Object.assign(document.createElement('p'),{textContent:
    `${month}. Сверьте сумму уже полученного кэшбэка с приложением банка.`});
  form.append(note);

  function fields(label, info){
    const group=document.createElement('fieldset');
    group.append(Object.assign(document.createElement('legend'),{textContent:label}));
    const inputs=[['Лимит, ₽','limitKopecks'],['Уже получено, ₽','usedKopecks']].map(([title,key])=>{
      const field=Object.assign(document.createElement('label'),{textContent:title});
      const input=Object.assign(document.createElement('input'),{
        inputMode:'decimal', value:info[key]==null?'':String(info[key]/100), placeholder:'Не указано',
      });
      field.append(input); group.append(field);
      return input;
    });
    const remaining=info.remainingKopecks==null?'Лимит не указан':`Осталось ${money(info.remainingKopecks)}`;
    const suffix=info.bankBalanceApplied?' · по сверке с банком':
      info.limitKopecks!=null&&info.usedKopecks==null?' · начисления не указаны':'';
    group.append(Object.assign(document.createElement('p'),{textContent:remaining+suffix}));
    form.append(group);
    return ()=>{
      const [limitKopecks,usedKopecks]=inputs.map(input=>{
        if(input.value.trim()==='') return null;
        const amount=rubFromField(input.value);
        if(!Number.isSafeInteger(amount)||amount>10**12) throw new Error('Сумма превышает допустимый максимум');
        return amount;
      });
      return {limitKopecks,usedKopecks};
    };
  }

  const readCard=fields('Вся карта',data.card);
  const readCategories=data.categories.map(info=>{
    const read=fields(info.label,info);
    return ()=>({categoryId:info.categoryId,...read()});
  });
  if(!readCategories.length) form.append(Object.assign(document.createElement('p'),{
    textContent:'Добавьте категории кэшбэка, чтобы указать лимиты для каждой из них.',
  }));
  const save=Object.assign(document.createElement('button'),{type:'submit',className:'confirm',textContent:'Сохранить лимиты'});
  const status=document.createElement('p');
  status.setAttribute('role','status');
  form.append(save,status);
  host.replaceChildren(form);
  form.onsubmit=async event=>{
    event.preventDefault();
    if(save.disabled) return;
    save.disabled=true;
    status.textContent='';
    try{
      const body={month:data.month,card:readCard(),categories:readCategories.map(read=>read())};
      const updated=await api(endpoint,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      if(ticket===limitsRequest&&card.cardId===activeCard()?.cardId){
        renderCardLimits(card,endpoint,updated,ticket);
        host.querySelector('button').focus({preventScroll:true});
      }
      toast('Лимиты сохранены');
    }catch(error){status.textContent=error.message;}
    finally{save.disabled=false;}
  };
}
$('cardLimits').addEventListener('toggle',async()=>{
  const ticket=++limitsRequest;
  if(!$('cardLimits').open) return;
  const card=activeCard();
  if(!card) return;
  const host=$('cardLimitsBody');
  host.textContent='Загружаем лимиты…';
  const endpoint='/api/me/cards/'+encodeURIComponent(card.cardId)+'/cashback-limits';
  try{
    const data=await api(endpoint);
    if(ticket===limitsRequest&&card.cardId===activeCard()?.cardId) renderCardLimits(card,endpoint,data,ticket);
  }catch(error){
    if(ticket===limitsRequest) host.textContent=error.message;
  }
});
function updateCarouselDetails(card){
  $('cardCarousel').hidden=!card;
  $('walletEmpty').hidden=Boolean(card);
  $('carouselControls').hidden=carouselPos.all.length<2;
  $('carouselDetails').hidden=!card;
  $('cardActions').hidden=!card;
  if(limitsCardId!==(card?.cardId??null)){
    limitsCardId=card?.cardId??null;
    ++limitsRequest;
    $('cardLimits').open=false;
  }
  $('cardLimits').hidden=!!card?.demo;
  if(!card) return;
  $('carouselPosition').textContent=`${mod(Math.round(carouselPos.value),carouselPos.all.length)+1} из ${carouselPos.all.length}`;
  renderWalletCardDetails(card);
}
function updateHomeCarousel(card){
  $('homeCarousel').hidden=!card;
  $('homeCarouselControls').hidden=homeCarouselPos.all.length<2;
  $('openHomeCard').hidden=!card;
  $('homeWalletEmpty').hidden=Boolean(card);
  if(!card) return;
  $('homeCarousel').style.setProperty('--carousel-glow',carouselCardPaint(card).color);
  $('homeCarouselPosition').textContent=`${mod(Math.round(homeCarouselPos.value),homeCarouselPos.all.length)+1} из ${homeCarouselPos.all.length}`;
}
function selectDeck(state, cards, preferred){
  const index=cards.findIndex(card=>card.cardId===preferred);
  state.all=cards;
  state.value=state.target=Math.max(0,index);
}
function renderCards(){
  const walletCard=walletPreferredCard||activeCard()?.cardId;
  const homeCard=homeCarousel.selected()?.cardId;
  const cards=[
    ...saved.map(cardId=>({...cardInfo(cardId),kind:'catalog'})),
    ...manual.map(card=>({...card, cardName:card.name, kind:'manual'})),
  ];
  walletPreferredCard=null;
  selectDeck(carouselPos,cards,walletCard);
  selectDeck(homeCarouselPos,cards,homeCard);
  walletCarousel.render();
  homeCarousel.render();
}
function openHomeCard(card){
  if(!card) return;
  selectDeck(carouselPos,carouselPos.all,card.cardId);
  walletRoute('cards');
  walletCarousel.render();
  $('addCashbackBtn').focus({preventScroll:true});
}
function applyWalletRoute(route){
  const isCashback=route==='cashback'||route==='history';
  $('hero').hidden=route!=='home';
  $('content').hidden=route==='home';
  $('buyPanel').hidden=route!=='buy';
  $('cardsPanel').hidden=route!=='cards';
  $('cashbackPanel').hidden=!isCashback;
  $('historyPanel').hidden=route!=='history';
  $('cashbackOverview').hidden=route!=='cashback';
  $('accountPanel').hidden=route!=='account';
  $('brandHomeLabel').hidden=route==='home';
  markRoute(route);
  window.scrollTo(0,0);

  if(route==='buy') checkout.open();
  if(route==='cards') walletCarousel.refresh();
  if(route==='home') homeCarousel.refresh();
  if(route==='history') renderHistory();
  if(route==='account') renderAccount();
  if(route==='cashback') renderMonthCashback();

  const focus={home:'homeTitle',cards:'cards-title',cashback:'cashbackTitle',history:'historyTitle',account:'accountTitle'}[route];
  if(focus) $(focus).focus({preventScroll:true});
}
function walletRoute(route, replace){
  const safe=shellRoutes.includes(route)?route:'home';
  const hash='#'+safe;
  history[replace||location.hash===hash?'replaceState':'pushState']({advisor:true, route:safe},'',hash);
  applyWalletRoute(safe);
}
function markRoute(route){
  document.querySelectorAll('[data-route]').forEach(button=>{
    const selected=button.dataset.route===route||(button.id==='openCashback'&&route==='history')||(button.id==='openHome'&&route==='buy');
    if(selected) button.setAttribute('aria-current','page');
    else button.removeAttribute('aria-current');
  });
}
function entryRoute(forceHome){
  if(forceHome) return 'home';
  const hash=(location.hash||'').replace(/^#/,'');
  if(!hash || hash==='home') return 'home';
  return shellRoutes.includes(hash)?hash:'home';
}
function syncWalletRoute(forceHome){ walletRoute(entryRoute(forceHome), true); }
async function loadWalletData(){
  checkout.setWalletReady(false);
  const statusRow=$('walletStatus')?.closest('.wallet-status');
  if(statusRow) statusRow.classList.remove('is-error');
  $('walletStatus').textContent=''; $('retryWallet').hidden=true;
  try{
    [catalog, saved, manual]=await Promise.all([
      apiPart('Справочник карт','/api/cards'),
      apiPart('Список в кошельке','/api/me/cards'),
      apiPart('Ваши карты','/api/me/manual-cards'),
    ]);
    await fillMeta(); renderCards(); writeDevice();
    checkout.setWalletReady(true);
    if(!$('accountPanel').hidden) renderAccount();
  }catch(error){
    if(statusRow) statusRow.classList.add('is-error');
    $('walletStatus').textContent=error.message||'Не удалось загрузить кошелёк.';
    $('retryWallet').hidden=false;
  }
}
function expireSession(){
  checkout.setWalletReady(false);
  deviceLogin=null;
  usualCardId=null;
  sessionStorage.removeItem('advisor-auth-home');
  manual=[];
  saved=[];
  renderCards();
  for(const id of ['addDialog','deleteDialog','planDialog','catalogDialog']) {const node=$(id); if(node) node.hidden=true;}
  if($('accountPanel')) $('accountPanel').hidden=true;
  $('hero').hidden=false; $('content').hidden=true;
  $('buyPanel').hidden=true; $('cardsPanel').hidden=true; $('cashbackPanel').hidden=true; $('historyPanel').hidden=true;
  if(location.hash) history.replaceState(null,'',location.pathname+location.search);
  $('authScreen').hidden=true;
  $('appScreen').hidden=true;
  $('welcomeScreen').hidden=false;
  if($('authPassword')) $('authPassword').value='';
  if($('sessionGate')) $('sessionGate').hidden=true;
}
window.expireSession=expireSession;
function openDialog(dialog, focus, source){walletReturn=source||document.activeElement; dialog.hidden=false; focus?.focus();}
function closeDialog(dialog){dialog.hidden=true; if(walletReturn?.isConnected) walletReturn.focus();}
function trap(dialog){if(!dialog) return; dialog.addEventListener('keydown',event=>{
  if(event.key==='Escape'){event.preventDefault(); dialog.querySelector('.close, .cancel')?.click(); return;}
  if(event.key!=='Tab') return;
  const items=[...dialog.querySelectorAll('button,input,select,a')].filter(item=>!item.disabled && !item.closest('[hidden]') && item.getClientRects().length);
  if(!items.length) return;
  if(event.shiftKey && document.activeElement===items[0]){event.preventDefault(); items.at(-1).focus();}
  else if(!event.shiftKey && document.activeElement===items.at(-1)){event.preventDefault(); items[0].focus();}
});}
function openAddCard(source){
  if(document.documentElement.dataset.demo==='cards') return;
  addReturn=walletReturn=source||document.activeElement;
  $('addRoutes').hidden=false; $('addCardForm').hidden=true; $('addTitle').textContent='Добавить карту';
  $('addStatus').textContent=''; $('retryAdd').hidden=true; $('addDialog').hidden=false; $('addRouteBank').focus();
}
function showBankForm(){
  $('addRoutes').hidden=true; $('addCardForm').hidden=false; $('addCardForm').dataset.mode='bank'; $('addSource').value='bank';
  $('bankSearch').value=''; $('bankSearch').hidden=false; $('searchLabel').hidden=false;
  if($('addSelectedBank')) {$('addSelectedBank').hidden=true; $('addSelectedBank').textContent='';}
  if($('openCatalogSource')) $('openCatalogSource').hidden=false;
  fillAddChoices(); $('bankSearch').focus();
}
function showCatalogForm(){
  $('addRoutes').hidden=true; $('addCardForm').hidden=false; $('addCardForm').dataset.mode='catalog'; $('addSource').value='catalog';
  $('bankSearch').value=''; $('bankSearch').hidden=true; $('searchLabel').hidden=true;
  if($('addSelectedBank')) {$('addSelectedBank').hidden=true; $('addSelectedBank').textContent='';}
  if($('openCatalogSource')) $('openCatalogSource').hidden=true;
  fillAddChoices(); $('newBank').focus();
}
function fillAddChoices(){
  const select=$('newBank'), catalogMode=$('addSource').value==='catalog', query=$('bankSearch').value.trim().toLowerCase();
  const previous=select.value;
  select.hidden=!catalogMode; $('bankSelectLabel').hidden=!catalogMode;
  select.replaceChildren();
  if(!catalogMode) select.append(new Option('Выберите банк',''));
  const bankItem=bank=>({value:bank.id,label:bank.name,logo:bank.logo||null});
  const items=catalogMode?catalog.map(card=>({value:card.cardId,label:`${card.cardName} · ${card.bankName}`,logo:null}))
    :banks.filter(bank=>!query || bank.name.toLowerCase().includes(query) || bank.id.includes(query)).map(bankItem);
  items.forEach(item=>select.append(new Option(item.label,item.value)));
  if(previous && [...select.options].some(option=>option.value===previous)) select.value=previous;
  else if(catalogMode&&items.length===1) select.value=items[0].value;
  const box=$('bankSuggestions'); box.replaceChildren(); box.className='suggest bank-list'; bankSuggest=-1;
  if(catalogMode){box.hidden=true; $('bankSearch').setAttribute('aria-expanded','false');}
  else {
    box.hidden=false; $('bankSearch').removeAttribute('aria-activedescendant'); $('bankSearch').setAttribute('aria-expanded','true');
    const list=query?items:banks.map(bankItem);
    list.forEach((item,index)=>{
      const option=document.createElement('button'); option.type='button'; option.className='bank-row'; option.setAttribute('role','option'); option.id=`bank-option-${index}`; option.tabIndex=-1;
      if(item.logo){const logo=document.createElement('img'); logo.className='bank-row-logo'; logo.src=item.logo; logo.alt=''; logo.width=32; logo.height=32; logo.decoding='async'; logo.loading='lazy'; logo.onerror=()=>logo.remove(); option.append(logo);}
      const label=document.createElement('span'); label.className='bank-row-name'; label.textContent=item.label; option.append(label);
      option.onmousedown=event=>event.preventDefault();
      option.onclick=()=>{
        $('newBank').value=item.value; $('bankSearch').value=item.label;
        if($('addSelectedBank')){$('addSelectedBank').hidden=false; $('addSelectedBank').textContent='Выбран: '+item.label;}
        box.hidden=true; $('bankSearch').removeAttribute('aria-activedescendant'); $('bankSearch').setAttribute('aria-expanded','false'); $('addStatus').textContent=''; $('saveNewCard').disabled=false;
      };
      box.append(option); option.setAttribute('aria-selected','false');
    });
    if(!list.length){const empty=document.createElement('p'); empty.className='cb-note'; empty.textContent='Ничего не найдено'; box.append(empty);}
  }
  $('addStatus').textContent=items.length?'':catalogMode?'В каталоге нет карт.':'Ничего не найдено';
  $('saveNewCard').disabled=!items.length || !select.value;
}
function monthTitle(month){
  if(!month) return '';
  const name=new Intl.DateTimeFormat('ru-RU',{month:'long', year:'numeric', timeZone:'UTC'}).format(new Date(month+'-01T12:00:00Z')).replace(/\s*г\.?$/,'');
  return name.charAt(0).toUpperCase()+name.slice(1);
}
async function renderMonthCashback(){
  const section=$('homeMonthCashback'), host=$('homeMonthCashbackBody');
  if(section.closest('[hidden]')) return;
  host.className='month-cashback is-loading';
  host.textContent='Считаем кэшбэк…';
  try{
    const data=await api('/api/me/stats');
    host.className='month-cashback';
    host.replaceChildren();
    if(!data.count){
      const empty=document.createElement('p');
      empty.className='month-cashback-meta';
      empty.textContent='Покупок в этом месяце пока нет. Запишите покупку после совета.';
      host.append(empty);
      const journal=document.createElement('button');
      journal.type='button'; journal.className='month-cashback-journal'; journal.textContent='Покупки за месяц';
      journal.onclick=()=>walletRoute('history');
      host.append(journal);
      return;
    }
    const grid=document.createElement('div'); grid.className='month-cashback-grid';
    const actual=document.createElement('div'); actual.className='month-cashback-actual';
    const kicker=document.createElement('span'); kicker.className='month-cashback-kicker'; kicker.textContent='Получено';
    actual.append(kicker);
    if(data.actualCashbackKopecks==null){
      const pending=document.createElement('span'); pending.className='month-cashback-pending'; pending.textContent='—';
      actual.append(pending);
    }else{
      const value=document.createElement('strong'); value.className='money'; value.textContent=money(data.actualCashbackKopecks);
      actual.append(value);
    }
  const side=document.createElement('div'); side.className='month-cashback-side';
    const calc=document.createElement('p');
    calc.append(Object.assign(document.createElement('span'),{textContent:'По расчёту'}),
      Object.assign(document.createElement('strong'),{className:'money',textContent:money(data.calculatedKopecks)}));
    const missed=document.createElement('p');
    missed.append(Object.assign(document.createElement('span'),{textContent:'Можно было ещё'}),
      Object.assign(document.createElement('strong'),{className:'money',textContent:money(Math.max(0,data.missedKopecks||0))}));
    side.append(calc, missed);
    grid.append(actual, side);
    host.append(grid);
    const meta=document.createElement('p'); meta.className='month-cashback-meta';
    if(!data.actualCashbackCount) meta.textContent='Нет подтверждённых начислений';
    else meta.textContent=`Подтверждённые начисления: ${data.actualCashbackCount} из ${data.count}`;
    host.append(meta);
    if(Array.isArray(data.cards)&&data.cards.length){
      const cards=document.createElement('details'); cards.className='month-cashback-cards';
      const summary=document.createElement('summary'); summary.textContent='По картам'; cards.append(summary);
      const list=document.createElement('ul');
      data.cards.forEach(card=>{
        const li=document.createElement('li');
        const name=document.createElement('span'); name.className='name'; name.textContent=card.name||card.cardId;
        const vals=document.createElement('span'); vals.className='vals';
        const actualText=card.actualCashbackCount
          ?`${money(card.actualCashbackKopecks)} · ${card.actualCashbackCount}`
          :`${money(card.cashbackKopecks)} расчёт`;
        vals.textContent=actualText;
        li.append(name, vals); list.append(li);
      });
      cards.append(list); host.append(cards);
    }
    const journal=document.createElement('button');
    journal.type='button'; journal.className='month-cashback-journal'; journal.textContent='Покупки за месяц';
    journal.onclick=()=>walletRoute('history');
    host.append(journal);
  }catch(error){
    host.className='month-cashback is-error'; host.replaceChildren();
    const message=document.createElement('p'); message.textContent=error.message||'Не удалось загрузить сводку.';
    const retry=document.createElement('button'); retry.type='button'; retry.textContent='Повторить';
    retry.onclick=()=>renderMonthCashback();
    host.append(message, retry);
  }
}
function buildActualCashbackEditor(item, trigger){
  const wrap=document.createElement('div'); wrap.className='journal-actual';
  const title=document.createElement('h4'); title.textContent='Фактический кэшбэк';
  const label=document.createElement('label');
  label.textContent='Сколько начислил банк, ₽';
  const input=document.createElement('input');
  input.inputMode='decimal'; input.autocomplete='off';
  input.placeholder='Например, 48';
  if(item.actualCashbackKopecks!=null) input.value=rubDisplay(item.actualCashbackKopecks);
  label.append(input);
  const note=document.createElement('p'); note.className='journal-actual-note';
  const syncNote=()=>{
    clear.hidden=item.actualCashbackKopecks==null;
    if(item.actualCashbackKopecks==null) note.textContent='Начисление ещё не подтверждено';
    else if(item.actualCashbackKopecks===0) note.textContent='Подтверждённый ноль';
    else note.textContent=`Сохранено: ${money(item.actualCashbackKopecks)}`;
  };
  const error=document.createElement('p'); error.className='journal-actual-error'; error.hidden=true;
  const actions=document.createElement('div'); actions.className='journal-actual-actions';
  const save=document.createElement('button'); save.type='button'; save.className='primary'; save.textContent='Сохранить';
  const clear=document.createElement('button'); clear.type='button'; clear.textContent='Удалить отметку';
  syncNote();
  const busy=flag=>{save.disabled=flag; clear.disabled=flag; input.readOnly=flag;};
  save.onclick=async()=>{
    error.hidden=true;
    let amount;
    try{amount=rubFromField(input.value);}catch(e){error.textContent=e.message; error.hidden=false; return;}
    busy(true);
    try{
      await api(`/api/me/purchases/${item.id}/cashback`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({amountKopecks:amount})});
      item.actualCashbackKopecks=amount; syncNote(); trigger.textContent='Изменить кэшбэк'; toast('Начисление сохранено');
    }catch(e){error.textContent=e.message||'Не удалось сохранить'; error.hidden=false;}
    finally{busy(false);}
  };
  clear.onclick=async()=>{
    error.hidden=true; busy(true);
    try{
      await api(`/api/me/purchases/${item.id}/cashback`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({amountKopecks:null})});
      item.actualCashbackKopecks=null; input.value=''; syncNote(); trigger.textContent='Подтвердить кэшбэк'; toast('Отметка удалена');
    }catch(e){error.textContent=e.message||'Не удалось удалить'; error.hidden=false;}
    finally{busy(false);}
  };
  actions.append(save, clear);
  wrap.append(title, label, note, actions, error);
  wrap.addEventListener('click', event=>event.stopPropagation());
  return wrap;
}
function dayTitle(iso){
  if(!iso) return 'Без даты';
  return new Intl.DateTimeFormat('ru-RU',{day:'numeric', month:'long', timeZone:'UTC'}).format(new Date(iso.slice(0,10)+'T12:00:00Z'));
}
let journalRequest = 0;

async function renderHistory(){
  const ticket = ++journalRequest;
  const host=$('historyBody'); host.className='journal is-loading'; host.textContent='Загружаем историю…';
  try{
    const query=historyMonth?`?month=${encodeURIComponent(historyMonth)}`:'';
    const data=await api('/api/me/stats'+query);
    if (ticket !== journalRequest) return;
    host.className='journal'; host.replaceChildren();
    if($('historyMonth') && data.month) $('historyMonth').value=data.month;
    historyMonth=data.month;
    const summary=document.createElement('section'); summary.className='journal-summary';
    const total=document.createElement('p'); total.className='journal-total';
    const strong=document.createElement('strong'); strong.className='money'; strong.textContent=money(data.calculatedKopecks);
    const caption=document.createElement('span'); caption.textContent='Расчётный кэшбэк за месяц';
    total.append(caption, strong);
    summary.append(total);
    const ask=document.createElement('button'); ask.type='button'; ask.className='buy-primary'; ask.textContent='Разбор за месяц';
    ask.onclick=async()=>{ask.disabled=true; ask.textContent='Разбираем…'; try{const reply=await api('/api/me/stats/comment?month='+encodeURIComponent(data.month),{method:'POST'},45000); const comment=document.createElement('p'); comment.textContent=reply.comment; summary.append(comment);}catch(error){toast(error.message);}finally{ask.disabled=false; ask.textContent='Разбор за месяц';}};
    summary.append(ask); host.append(summary);
    if(!data.purchases.length){host.classList.add('is-empty'); const empty=document.createElement('p'); empty.textContent='Покупок в этом месяце нет. Запишите покупку после совета.'; host.append(empty); return;}
    const groups=new Map();
    data.purchases.forEach(item=>{const key=(item.date||'').slice(0,10); if(!groups.has(key)) groups.set(key,[]); groups.get(key).push(item);});
    groups.forEach((items,key)=>{
      const day=document.createElement('h3'); day.className='journal-day'; day.textContent=dayTitle(key); host.append(day);
      const list=document.createElement('div'); list.className='journal-list';
      items.forEach(item=>{
        const gap=(item.recommendedKopecks??0)-(item.chosenKopecks??0);
        const row=document.createElement('button'); row.type='button'; row.className='journal-row'; row.setAttribute('aria-expanded','false');
        const main=document.createElement('span'); main.className='journal-main';
        const title=document.createElement('span'); title.className='journal-title'; title.textContent=categories[item.categoryId]||item.categoryId||'Покупка';
        const bank=document.createElement('span'); bank.className='journal-bank'; bank.textContent=item.chosenName||'Карта';
        main.append(title, bank);
        if(gap>0){const extra=document.createElement('span'); extra.className='journal-gap'; extra.textContent=`Можно было получить ещё ${money(gap)}`; main.append(extra);}
        const moneyCol=document.createElement('span'); moneyCol.className='journal-money';
        const amount=document.createElement('strong'); amount.className='money'; amount.textContent=money(item.amountKopecks);
        const cash=document.createElement('span'); cash.className='journal-cash'; cash.textContent=item.chosenKopecks==null?'':`+${money(item.chosenKopecks)}`;
        moneyCol.append(amount, cash);
        const chevron=document.createElement('span'); chevron.className='journal-chevron'; chevron.setAttribute('aria-hidden','true');
        moneyCol.append(chevron);
        row.append(main, moneyCol);
        const detail=document.createElement('div'); detail.className='journal-detail'; detail.hidden=true;
        const chosen=document.createElement('p'); chosen.textContent=`Выбранная карта: ${item.chosenName||'—'}${item.chosenKopecks==null?'':`, ${money(item.chosenKopecks)}`}`;
        const best=document.createElement('p'); best.textContent=`Лучшая по расчёту: ${item.recommendedName||'—'}${item.recommendedKopecks==null?'':`, ${money(item.recommendedKopecks)}`}`;
        const diff=document.createElement('p'); diff.textContent=`Разница: ${item.recommendedKopecks==null||item.chosenKopecks==null?'—':money(gap)}`;
        detail.append(chosen, best, diff);
        detail.id='purchase-detail-'+item.id;
        row.setAttribute('aria-controls', detail.id);
        row.onclick=()=>{detail.hidden=!detail.hidden; row.setAttribute('aria-expanded', String(!detail.hidden));};

        const purchase=document.createElement('article'); purchase.className='journal-purchase';
        purchase.append(row, detail);
        if(item.id!=null){
          const confirm=document.createElement('button'); confirm.type='button'; confirm.className='journal-confirm';
          confirm.textContent=item.actualCashbackKopecks==null?'Подтвердить кэшбэк':'Изменить кэшбэк';
          confirm.setAttribute('aria-expanded','false');
          const editor=buildActualCashbackEditor(item,confirm);
          editor.id='purchase-cashback-'+item.id;
          editor.hidden=true;
          confirm.setAttribute('aria-controls',editor.id);
          confirm.onclick=()=>{
            editor.hidden=!editor.hidden;
            confirm.setAttribute('aria-expanded',String(!editor.hidden));
            if(!editor.hidden) editor.querySelector('input').focus();
          };
          purchase.append(confirm,editor);
        }
        list.append(purchase);
      });
      host.append(list);
    });
  }catch(error){
    if (ticket !== journalRequest) return;
    host.className='journal is-error'; host.replaceChildren();
    const message=document.createElement('p'); message.textContent=error.message||'Не удалось загрузить историю.';
    const retry=document.createElement('button'); retry.type='button'; retry.textContent='Повторить загрузку'; retry.onclick=()=>renderHistory();
    host.append(message, retry);
  }
}
function profileMetrics(data){
  const metrics=document.createElement('dl'); metrics.className='profile-metrics';
  const spent=data.purchases.reduce((sum,purchase)=>sum+purchase.amountKopecks,0);
  for(const [label,value] of [
    ['Потрачено',money(spent)],
    ['Кэшбэк получен',data.actualCashbackKopecks==null?'—':money(data.actualCashbackKopecks)],
    ['Кэшбэк по расчёту',money(data.calculatedKopecks)],
    ['Покупок',String(data.count)],
  ]){
    const item=document.createElement('div');
    const name=document.createElement('dt'); name.textContent=label;
    const amount=document.createElement('dd'); amount.textContent=value;
    item.append(name,amount); metrics.append(item);
  }
  return metrics;
}
function spendingChart(purchases){
  const byCategory=new Map();
  for(const {categoryId,amountKopecks} of purchases){
    byCategory.set(categoryId,(byCategory.get(categoryId)||0)+amountKopecks);
  }
  const entries=[...byCategory.entries()].sort((a,b)=>b[1]-a[1]);
  const total=entries.reduce((sum,[,amount])=>sum+amount,0);
  const section=document.createElement('section'); section.className='profile-chart';
  const title=document.createElement('h3'); title.textContent='Траты по категориям';
  section.append(title);
  const rows=document.createElement('ul');
  for(const [categoryId,amount] of entries){
    const item=document.createElement('li');
    const label=document.createElement('span'); label.textContent=categories[categoryId]||categoryId;
    const value=document.createElement('strong'); value.textContent=money(amount);
    const bar=document.createElement('span'); bar.className='profile-chart-bar'; bar.setAttribute('aria-hidden','true');
    const fill=document.createElement('span'); fill.style.inlineSize=`${amount/total*100}%`;
    bar.append(fill); item.append(label,value,bar); rows.append(item);
  }
  section.append(rows);
  return section;
}
let profileRequest=0;
async function renderAccount(){
  const ticket=++profileRequest;
  const host=$('accountStats');
  renderAccountIdentity();
  $('settingsStatus').textContent='';
  host.className=''; host.setAttribute('aria-busy','true'); host.textContent='Загружаем статистику…';
  try{
    const data=await api('/api/me/stats');
    if(ticket!==profileRequest) return;
    const month=document.createElement('p'); month.className='profile-month'; month.textContent=monthTitle(data.month);
    host.replaceChildren(month,profileMetrics(data));
    if(data.purchases.length) host.append(spendingChart(data.purchases));
    const note=document.createElement('p'); note.className='journal-meta';
    note.textContent=!data.count?'За этот месяц покупок пока нет.':
      data.actualCashbackKopecks==null?'Полученный кэшбэк появится после подтверждения в истории покупок.':
      `Подтверждённые начисления: ${data.actualCashbackCount} из ${data.count}.`;
    host.append(note);
  }catch(error){
    if(ticket!==profileRequest) return;
    host.className='account-error'; host.replaceChildren();
    const message=document.createElement('p'); message.textContent=error.message||'Не удалось загрузить статистику.';
    const retry=document.createElement('button'); retry.type='button'; retry.textContent='Повторить загрузку'; retry.onclick=renderAccount;
    host.append(message,retry);
  }finally{
    if(ticket===profileRequest) host.setAttribute('aria-busy','false');
  }
}
$('brandHome').onclick=()=>walletRoute('home');
document.querySelectorAll('[data-route]').forEach(button=>button.addEventListener('click',()=>walletRoute(button.dataset.route)));
$('openBuy').addEventListener('click',()=>{
  walletRoute('buy');
});
if($('authGuest')) $('authGuest').addEventListener('click',async()=>{
  const button=$('authGuest');
  button.disabled=true; $('authError').textContent='';
  try{
    const user=await api('/api/auth/guest',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:'{}',
    });
    deviceLogin=user.login; localStorage.setItem('advisor-login',user.login);
    sessionStorage.setItem('advisor-auth-home','1'); await checkAuth();
  }catch(error){
    const text=error.status===404
      ?'Вход как гость недоступен — перезапустите сервер с последней версией.'
      :error.message||'Не удалось войти как гость';
    $('authError').textContent=text;
    button.disabled=false;
  }
});
$('previousCard').addEventListener('click',()=>walletCarousel.step(-1));
$('nextCard').addEventListener('click',()=>walletCarousel.step(1));
$('homePreviousCard').addEventListener('click',()=>homeCarousel.step(-1));
$('homeNextCard').addEventListener('click',()=>homeCarousel.step(1));
$('openHomeCard').addEventListener('click',()=>openHomeCard(homeCarousel.selected()));
$('homeAddCard').addEventListener('click',()=>{
  walletRoute('cards');
  openAddCard($('openCatalog'));
});
$('themeToggle').addEventListener('click',()=>applyTheme(document.documentElement.dataset.theme==='dark'?'light':'dark'));
$('openCatalog').addEventListener('click',event=>openAddCard(event.currentTarget));
$('retryWallet').addEventListener('click',()=>load());
$('historyMonth').addEventListener('change',()=>{
  historyMonth=$('historyMonth').value||null;
  renderHistory();
});
window.addEventListener('popstate',()=>{
  if($('appScreen').hidden) return;
  if(typeof window.walletCashbackBack==='function' && !$('catalogDialog').hidden) window.walletCashbackBack();
  for(const id of ['addDialog','deleteDialog','planDialog']) {const node=$(id); if(node) node.hidden=true;}
  const route=(location.hash||'#home').slice(1); applyWalletRoute(shellRoutes.includes(route)?route:'home');
});
$('passwordToggle').addEventListener('click',()=>{
  const input=$('authPassword'), btn=$('passwordToggle');
  const next=input.type==='password'?'text':'password';
  input.type=next;
  const shown=next==='text';
  btn.setAttribute('aria-pressed', String(shown));
  btn.setAttribute('aria-label', shown?'Скрыть пароль':'Показать пароль');
  const eye=btn.querySelector('.icon-eye'), off=btn.querySelector('.icon-eye-off');
  if(eye) eye.hidden=shown;
  if(off) off.hidden=!shown;
});
$('addSource').addEventListener('change',fillAddChoices);
if($('openCatalogSource')) $('openCatalogSource').addEventListener('click',showCatalogForm);
$('bankSearch').addEventListener('input',()=>{
  $('newBank').value='';
  $('addSelectedBank').hidden=true;
  fillAddChoices();
});
$('bankSearch').addEventListener('keydown',event=>{
  const options=[...$('bankSuggestions').querySelectorAll('[role=option]')]; if(!options.length || $('bankSuggestions').hidden) return;
  if(event.key==='ArrowDown' || event.key==='ArrowUp'){event.preventDefault(); bankSuggest=event.key==='ArrowDown'?Math.min(options.length-1, bankSuggest+1):Math.max(0, bankSuggest-1); options.forEach((option,index)=>option.setAttribute('aria-selected', String(index===bankSuggest))); $('bankSearch').setAttribute('aria-activedescendant',options[bankSuggest].id); options[bankSuggest].scrollIntoView({block:'nearest'});}
  else if(event.key==='Enter'){event.preventDefault(); options[Math.max(0,bankSuggest)].click();}
  else if(event.key==='Escape'){event.stopPropagation(); $('bankSearch').removeAttribute('aria-activedescendant'); $('bankSuggestions').hidden=true; $('bankSearch').setAttribute('aria-expanded','false');}
});
$('retryAdd').addEventListener('click',async()=>{try{await fillMeta(); fillAddChoices();}catch(error){$('addStatus').textContent=error.message;}});
async function submitNewCard(event){
  event.preventDefault(); if($('saveNewCard').disabled) return;
  const catalogMode=$('addSource').value==='catalog', id=$('newBank').value, button=$('saveNewCard');
  if(!id){$('addStatus').textContent='Выберите банк из списка.'; return;}
  button.disabled=true; button.textContent='Сохраняем…';
  try{
    if(catalogMode){await api('/api/me/cards/'+encodeURIComponent(id),{method:'PUT'}); walletPreferredCard=id;}
    else{const bank=banks.find(item=>item.id===id); const created=await api('/api/me/manual-cards',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:bank.name,bankId:bank.id,rules:[]})}); walletPreferredCard=created.cardId;}
    $('addDialog').hidden=true; toast('Карта добавлена'); await load(); walletRoute('cards',true);
    $('addCashbackBtn').focus();
  }catch(error){$('addStatus').textContent=error.message; $('retryAdd').hidden=false;}
  finally{button.textContent='Добавить карту'; button.disabled=$('newBank').options.length===0;}
}
$('closeAdd').addEventListener('click',()=>closeDialog($('addDialog')));
$('addRouteBank').addEventListener('click',showBankForm);
$('addRouteShot').addEventListener('click',()=>{
  const back=addReturn||$('openCatalog');
  $('addDialog').hidden=true;
  if(typeof window.openCashbackDecision==='function') window.openCashbackDecision(back);
  else $('addCashbackBtn').click();
});
$('makeUsualBtn').addEventListener('click',async()=>{
  const card=activeCard(); if(!card || usualCardBusy) return;
  const clear=usualCardId===card.cardId;
  usualCardBusy=true; syncUsualCard(card);
  try{
    const options=clear?{method:'DELETE'}:{
      method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({cardId:card.cardId}),
    };
    await api('/api/me/usual-card',options);
    usualCardId=clear?null:card.cardId;
    toast(clear?'Карта убрана из сравнения':'Карта выбрана для сравнения в статистике');
  }catch(error){toast(error.message);}
  finally{usualCardBusy=false; syncUsualCard(activeCard());}
});
$('deleteActiveBtn').addEventListener('click',()=>{
  const card=activeCard(); if(!card) return;
  deleteTarget=card;
  const menu=$('cardSettings');
  menu.open=false;
  $('deleteDescription').textContent=`Карта «${card.cardName||card.name}» исчезнет из кошелька вместе с её условиями. Покупки останутся в истории.`;
  $('deleteStatus').textContent='';
  openDialog($('deleteDialog'),$('cancelDelete'),menu.querySelector('summary'));
});
$('logout').addEventListener('click',async()=>{
  if(!window.confirm('Выйти из кошелька на этом устройстве?')) return;
  $('logout').disabled=true; $('settingsStatus').textContent='';
  try{await api('/api/auth/logout',{method:'POST'});}
  catch(error){$('settingsStatus').textContent=error.message; return;}
  finally{$('logout').disabled=false;}
  expireSession();
});
$('cancelDelete').addEventListener('click',()=>closeDialog($('deleteDialog')));
$('confirmDelete').addEventListener('click',async()=>{
  if(!deleteTarget) return; $('confirmDelete').disabled=true; $('confirmDelete').textContent='Удаляем…';
  try{
    const path=deleteTarget.kind==='manual'?`/api/me/manual-cards/${encodeURIComponent(deleteTarget.cardId)}`:`/api/me/cards/${encodeURIComponent(deleteTarget.cardId)}`;
    await api(path,{method:'DELETE'});
    if(usualCardId===deleteTarget.cardId) usualCardId=null;
    $('deleteDialog').hidden=true; toast('Карта удалена'); await load(); $('cards-title').focus();
  }catch(error){$('deleteStatus').textContent=error.message;}
  finally{$('confirmDelete').disabled=false; $('confirmDelete').textContent='Удалить карту';}
});
['addDialog','deleteDialog'].forEach(id=>trap($(id)));
function showSessionGate(message, retry){
  const gate=$('sessionGate'); if(!gate) return;
  gate.hidden=false; $('sessionGateStatus').textContent=message;
  $('sessionGateRetry').hidden=!retry;
  $('welcomeScreen').hidden=true; $('authScreen').hidden=true; $('appScreen').hidden=true;
}
function hideSessionGate(){ if($('sessionGate')) $('sessionGate').hidden=true; }
window.shellCheckAuth=async function(){
  const forceHome=sessionStorage.getItem('advisor-auth-home')==='1';
  sessionStorage.removeItem('advisor-auth-home');
  showSessionGate('Проверяем вход…', false);
  try{
    const user=await api('/api/auth/me');
    hideSessionGate();
    if(user.authenticated){
      $('welcomeScreen').hidden=true; $('authScreen').hidden=true; $('appScreen').hidden=false;
      deviceLogin=user.login; $('authPassword').value='';
      syncWalletRoute(forceHome); await load();
    }else{
      $('welcomeScreen').hidden=false; $('authScreen').hidden=true; $('appScreen').hidden=true;
    }
  }catch(error){
    showSessionGate('Не удалось проверить вход', true);
    $('sessionGateRetry').onclick=()=>window.shellCheckAuth();
  }
};
checkAuth=window.shellCheckAuth;
function applyDemoCount(count){
  const deck=DEMO_DECK.slice(0, count).map(card=>({...card, rules:card.rules.map(rule=>({...rule}))}));
  manual=deck; saved=[]; walletPreferredCard=deck[0]?.cardId||null; carouselPos.value=0; carouselPos.target=0;
  renderCards(); applyWalletRoute('cards');
  document.querySelectorAll('[data-demo-count]').forEach(button=>button.setAttribute('aria-pressed', String(Number(button.dataset.demoCount)===count)));
}
function startDemo(){
  document.documentElement.dataset.demo='cards';
  hideSessionGate();
  $('welcomeScreen').hidden=true; $('authScreen').hidden=true; $('appScreen').hidden=false;
  if($('demoBar')) $('demoBar').hidden=false;
  applyDemoCount(7);
}
document.querySelectorAll('[data-demo-count]').forEach(button=>button.addEventListener('click',()=>applyDemoCount(Number(button.dataset.demoCount))));
if($('demoReset')) $('demoReset').addEventListener('click',()=>applyDemoCount(7));
if(new URLSearchParams(location.search).get('demo')==='cards') startDemo();
else checkAuth();

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(() => {});
  });
}
