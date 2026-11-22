import { useEffect, useId, useRef, useState } from 'react';
import type { CSSProperties, FormEvent, PointerEvent, ReactNode } from 'react';
import { api } from './api';
import './Wallet.css';

export type CardRule = {
  categoryId: string;
  rateBps: number;
  label?: string | null;
  source?: 'active' | 'base';
  month?: string;
  limitKopecks?: number | null;
  minAmountKopecks?: number;
  validFrom?: string | null;
  validThrough?: string | null;
};

type Paint = { color?: string; ink?: string; accent?: string; logo?: string };
type Bank = Paint & { id: string; name: string };
export type Card = {
  cardId: string;
  name: string;
  cardName: string;
  bankId?: string | null;
  bankName?: string | null;
  rules: CardRule[];
  kind: 'manual' | 'catalog';
  demo?: boolean;
  paint?: Paint;
};

type CatalogCard = Pick<Card, 'cardId' | 'cardName' | 'bankName' | 'rules'>;
type ManualCard = Pick<Card, 'cardId' | 'name' | 'bankId' | 'bankName' | 'rules'>;
type Meta = { banks: Bank[]; categories: Record<string, string>; catalogCategoryIds?: string[] };
type Deck = { cards: Card[]; catalog: CatalogCard[]; meta: Meta };
type Limits = { limitKopecks: number | null; usedKopecks: number | null };
type LimitInfo = Limits & { remainingKopecks: number | null; bankBalanceApplied?: boolean };
type CardLimits = { month: string; card: LimitInfo; categories: (LimitInfo & { categoryId: string; label: string })[] };
export type WalletProps = { onEdit?: (card: Card | null) => void };

const DEMO_COUNTS = [1, 2, 3, 4, 7];
const demoCategories: Record<string, string> = {
  transport: 'Транспорт', cafe: 'Кафе', all: 'Все покупки', supermarkets: 'Супермаркеты',
  fuel: 'АЗС', pharmacy: 'Аптеки', clothing: 'Одежда',
};
const DEMO_DECK = [
  demoCard('sber', 'Сбер', '#21a038', '#fff', 'transport', 1500, 'cafe', 400),
  demoCard('tbank', 'Т-Банк', '#ffdd2d', '#1d1e1a', 'supermarkets', 500, 'cafe', 700),
  demoCard('alfabank', 'Альфа-Банк', '#ef3124', '#fff', 'cafe', 700, 'fuel', 500),
  demoCard('vtb', 'ВТБ', '#002882', '#fff', 'transport', 1000, 'pharmacy', 500),
  demoCard('ozon', 'Ozon', '#005bff', '#fff', 'clothing', 500, 'supermarkets', 300),
  demoCard('akbars', 'Ак Барс', '#00915a', '#fff', 'fuel', 700, 'cafe', 400),
  demoCard('gazprombank', 'Газпромбанк', '#1f4e9d', '#fff', 'fuel', 1000, 'transport', 500),
];
const rubles = new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB' });
const percent = new Intl.NumberFormat('ru-RU', { style: 'percent', maximumFractionDigits: 2 });
const monthName = new Intl.DateTimeFormat('ru-RU', { year: 'numeric', month: 'long', timeZone: 'UTC' });
const MAX_KOPECKS = 10 ** 12;
const json = (method: string, body: unknown): RequestInit => ({
  method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
});
const manualPath = '/api/me/manual-cards';
const savedPath = '/api/me/cards';
const cardPath = (card: Card) => `${card.kind === 'manual' ? manualPath : savedPath}/${encodeURIComponent(card.cardId)}`;
const limitsPath = (card: Card) => `${savedPath}/${encodeURIComponent(card.cardId)}/cashback-limits`;
const message = (error: unknown) => error instanceof Error ? error.message : 'Не удалось выполнить запрос. Попробуйте ещё раз.';
const wrap = (value: number, count: number) => ((value % count) + count) % count;

function demoCard(bankId: string, name: string, color: string, ink: string, first: string, firstRate: number, second: string, secondRate: number): Card {
  return {
    cardId: `demo-${bankId}`, bankId, name, cardName: name, kind: 'manual', demo: true,
    paint: { color, ink, logo: `/static/banks/${bankId}.png` }, rules: [
      { categoryId: first, rateBps: firstRate }, { categoryId: second, rateBps: secondRate }, { categoryId: 'all', rateBps: 100 },
    ],
  };
}

function normalizeManual(card: ManualCard): Card {
  return { ...card, cardName: card.name, kind: 'manual' };
}

async function loadDeck(): Promise<Deck> {
  const [catalog, saved, manual, meta] = await Promise.all([
    api<CatalogCard[]>('/api/cards'), api<string[]>(savedPath), api<ManualCard[]>(manualPath), api<Meta>('/api/meta'),
  ]);
  const byId = new Map(catalog.map(card => [card.cardId, card]));
  return {
    catalog, meta,
    cards: [
      ...saved.map((cardId): Card => {
        const card = byId.get(cardId) ?? { cardId, bankName: 'Мой банк', cardName: cardId, rules: [] };
        return { ...card, name: card.cardName, kind: 'catalog' };
      }),
      ...manual.map(normalizeManual),
    ],
  };
}

function cardBank(card: Card, banks: Bank[]) {
  const key = (value: string) => value.toLowerCase().replace(/[^a-zа-яё0-9]/gi, '');
  return banks.find(bank => bank.id === card.bankId)
    ?? banks.find(bank => key(bank.name) === key(card.bankName || card.name));
}

function BankLogo({ name, src }: { name: string; src?: string }) {
  const [failed, setFailed] = useState(false);
  return <span className="kw-logo" aria-hidden="true">
    {src && !failed ? <img src={src} alt="" width={32} height={32} loading="lazy" decoding="async" onError={() => setFailed(true)} /> : name.charAt(0)}
  </span>;
}

function Carousel({ cards, banks, index, onSelect }: { cards: Card[]; banks: Bank[]; index: number; onSelect: (index: number) => void }) {
  const gesture = useRef<{ id: number; x: number; y: number; time: number; locked: boolean } | null>(null);
  const skipClick = useRef(false);
  const [drag, setDrag] = useState<number | null>(null);
  const card = cards[index];
  const move = (delta: number) => onSelect(wrap(index + delta, cards.length));
  const end = (event: PointerEvent<HTMLDivElement>, cancelled = false) => {
    const start = gesture.current;
    if (!start || start.id !== event.pointerId) return;
    gesture.current = null;
    setDrag(null);
    if (!start.locked) return;
    const dx = event.clientX - start.x;
    const elapsed = Math.max(1, event.timeStamp - start.time);
    if (!cancelled && (Math.abs(dx) >= 36 || (Math.abs(dx) >= 16 && Math.abs(dx) / elapsed > 0.45))) move(dx < 0 ? 1 : -1);
  };

  return <div className="kw-fan-area">
    <div className="kw-fan" data-dragging={drag !== null} tabIndex={0} role="region" aria-roledescription="карусель"
      aria-label={`Мои банковские карты. Активна: ${card.cardName}`}
      onPointerDown={event => {
        if (event.isPrimary === false || event.button !== 0) return;
        skipClick.current = false;
        if (cards.length > 1) gesture.current = { id: event.pointerId, x: event.clientX, y: event.clientY, time: event.timeStamp, locked: false };
      }}
      onPointerMove={event => {
        const start = gesture.current;
        if (!start || start.id !== event.pointerId) return;
        const dx = event.clientX - start.x;
        const dy = event.clientY - start.y;
        if (!start.locked) {
          if (Math.abs(dy) > 10 && Math.abs(dy) > Math.abs(dx)) { gesture.current = null; return; }
          if (Math.abs(dx) < 7) return;
          start.locked = true;
          skipClick.current = true;
          event.currentTarget.setPointerCapture(event.pointerId);
        }
        setDrag(Math.max(-1, Math.min(1, dx / Math.min(145, event.currentTarget.clientWidth * 0.34))));
      }}
      onPointerUp={event => end(event)} onPointerCancel={event => end(event, true)} onLostPointerCapture={event => end(event, true)}
      onKeyDown={event => {
        if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
          event.preventDefault(); move(event.key === 'ArrowLeft' ? -1 : 1);
        } else if (event.key === 'Home' || event.key === 'End') {
          event.preventDefault(); onSelect(event.key === 'Home' ? 0 : cards.length - 1);
        }
      }}>
      {cards.map((item, itemIndex) => {
        const total = cards.length;
        let relative = itemIndex - index + (drag ?? 0);
        if (total === 2 && itemIndex !== index) relative = 1 + (drag ?? 0);
        if (total > 2) {
          relative = wrap(relative + total / 2, total) - total / 2;
          if (relative === -total / 2 && itemIndex >= index) relative = total / 2;
        }
        const distance = Math.abs(relative);
        const side = Math.sign(relative) * Math.max(0, 1 - Math.abs(distance - 1) / (distance > 1 ? 0.72 : 1));
        const visible = distance < 1.72;
        const selected = itemIndex === index;
        const bank = cardBank(item, banks);
        const paint = item.paint ?? bank;
        const style = {
          '--kw-card-color': paint?.color || '#303333', '--kw-card-ink': paint?.ink || '#fff',
          '--kw-shift': `${side * 34}%`, '--kw-turn': `${side * 9}deg`, '--kw-drop': `${Math.min(distance, 1.6) * 11}px`,
          '--kw-scale': 1 - Math.min(distance, 1.6) * 0.1, opacity: Math.min(1, Math.max(0, (1.72 - distance) * 2.5)),
          zIndex: Math.round(100 - distance * 20),
        } as CSSProperties;
        return <button key={item.cardId} type="button" className="kw-card" style={style} data-selected={selected}
          aria-label={item.cardName} aria-hidden={!visible} aria-current={selected ? 'true' : undefined} tabIndex={selected ? 0 : -1}
          onClick={event => {
            if (event.detail !== 0 && skipClick.current) { skipClick.current = false; return; }
            if (!selected) { onSelect(itemIndex); return; }
            if (cards.length > 1 && event.detail > 0) {
              const box = event.currentTarget.getBoundingClientRect();
              move(event.clientX - box.left < box.width * 0.38 ? -1 : 1);
            }
          }}>
          <span className="kw-card-top"><span><strong>{item.cardName}</strong><small>{item.demo ? 'Демонстрационная карта' : item.kind === 'manual' ? 'Моя карта' : 'Карта в кошельке'}</small></span>
            <BankLogo name={item.cardName} src={paint?.logo || bank?.logo} />
          </span>
          <span className="kw-card-bottom" aria-hidden="true"><span className="kw-chip" /><span>•••• 0000</span></span>
        </button>;
      })}
    </div>
    {cards.length > 1 && <div className="kw-fan-controls">
      <button type="button" aria-label="Предыдущая карта" onClick={() => move(-1)}>‹</button>
      <span aria-live="polite">{index + 1} из {cards.length}</span>
      <button type="button" aria-label="Следующая карта" onClick={() => move(1)}>›</button>
    </div>}
  </div>;
}

function Modal({ title, busy = false, onClose, children }: { title: string; busy?: boolean; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  const id = useId();
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    const previous = document.activeElement;
    dialog.showModal();
    return () => {
      dialog.close();
      if (previous instanceof HTMLElement && previous.isConnected) previous.focus({ preventScroll: true });
    };
  }, []);
  return <dialog ref={ref} className="kw-dialog" aria-labelledby={id} aria-busy={busy}
    onCancel={event => { event.preventDefault(); if (!busy) onClose(); }}
    onClick={event => { if (event.target === event.currentTarget && !busy) onClose(); }}>
    <div className="kw-dialog-body">
      <header><h2 id={id}>{title}</h2><button type="button" className="kw-close" aria-label="Закрыть" disabled={busy} onClick={onClose}>×</button></header>
      {children}
    </div>
  </dialog>;
}

function AddCardDialog({ deck, onClose, onImport, onAdded }: { deck: Deck; onClose: () => void; onImport: () => void; onAdded: (card: Card) => void }) {
  const [catalogMode, setCatalogMode] = useState(false);
  const [selected, setSelected] = useState('');
  const [query, setQuery] = useState('');
  const [expanded, setExpanded] = useState(true);
  const [highlighted, setHighlighted] = useState(-1);
  const bankInput = useRef<HTMLInputElement>(null);
  const suggestionId = useId();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const keyword = query.trim().toLowerCase();
  const banks = deck.meta.banks.filter(bank => bank.name.toLowerCase().includes(keyword) || bank.id.toLowerCase().includes(keyword));
  const bank = deck.meta.banks.find(item => item.id === selected);
  const catalogCard = deck.catalog.find(item => item.cardId === selected);
  const chooseBank = (item: Bank) => {
    setQuery(item.name); setSelected(item.id); setExpanded(false); setHighlighted(-1); setError('');
    bankInput.current?.focus();
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (busy || !(catalogMode ? catalogCard : bank)) return;
    setError(''); setBusy(true);
    try {
      if (!catalogMode && bank) {
        const data = { name: bank.name, bankId: bank.id, rules: [] };
        const { cardId } = await api<{ cardId: string }>(manualPath, json('POST', data));
        onAdded(normalizeManual({ ...data, cardId }));
      } else if (catalogCard && !deck.cards.some(card => card.cardId === catalogCard.cardId)) {
        await api<void>(`${savedPath}/${encodeURIComponent(catalogCard.cardId)}`, { method: 'PUT' });
        onAdded({ ...catalogCard, name: catalogCard.cardName, kind: 'catalog' });
      } else if (catalogCard) {
        const allowed = new Set(deck.meta.catalogCategoryIds ?? Object.keys(deck.meta.categories));
        const rates = new Map<string, CardRule>();
        for (const rule of catalogCard.rules) {
          if (!allowed.has(rule.categoryId) || rates.has(rule.categoryId)) continue;
          rates.set(rule.categoryId, { categoryId: rule.categoryId, rateBps: rule.rateBps });
        }
        if (!rates.size) throw new Error('У учебной карты нет доступных категорий.');
        const suffix = Array.from(crypto.getRandomValues(new Uint8Array(4)), byte => byte.toString(16).padStart(2, '0')).join('');
        const data = { name: `${catalogCard.cardName.slice(0, 58)} · учебная ${suffix}`, rules: [...rates.values()] };
        const { cardId } = await api<{ cardId: string }>(manualPath, json('POST', data));
        onAdded(normalizeManual({ ...data, cardId, bankName: catalogCard.bankName }));
      }
    } catch (failure) { setError(message(failure)); }
    finally { setBusy(false); }
  };

  return <Modal title="Добавить карту" busy={busy} onClose={onClose}>
    <form className="kw-form" onSubmit={submit}>
      <div className="kw-source" role="group" aria-label="Источник карты">
        <button type="button" aria-pressed={!catalogMode} disabled={busy} onClick={() => { setCatalogMode(false); setSelected(''); setError(''); }}>Мой банк</button>
        <button type="button" aria-pressed={catalogMode} disabled={busy} onClick={() => { setCatalogMode(true); setSelected(''); setError(''); }}>Учебный каталог</button>
      </div>
      {catalogMode ? <label>Карта<select value={selected} required disabled={busy} onChange={event => setSelected(event.target.value)}>
        <option value="">Выберите карту</option>
        {deck.catalog.map(card => <option key={card.cardId} value={card.cardId}>{card.cardName} · {card.bankName}</option>)}
      </select></label> : <>
        <label>Найти банк<input ref={bankInput} autoFocus type="search" role="combobox" value={query} placeholder="Название банка" disabled={busy}
          aria-autocomplete="list" aria-expanded={expanded} aria-controls={suggestionId}
          aria-activedescendant={expanded && highlighted >= 0 ? `${suggestionId}-${highlighted}` : undefined}
          onChange={event => { setQuery(event.target.value); setSelected(''); setExpanded(true); setHighlighted(-1); }}
          onKeyDown={event => {
            if (event.key === 'Escape' && expanded) {
              event.preventDefault(); event.stopPropagation(); setExpanded(false); setHighlighted(-1);
            } else if ((event.key === 'ArrowDown' || event.key === 'ArrowUp') && banks.length) {
              event.preventDefault();
              const next = event.key === 'ArrowDown' ? Math.min(banks.length - 1, highlighted + 1) : Math.max(0, highlighted - 1);
              setExpanded(true); setHighlighted(next);
              requestAnimationFrame(() => document.getElementById(`${suggestionId}-${next}`)?.scrollIntoView({ block: 'nearest' }));
            } else if (event.key === 'Enter' && expanded && banks.length && !selected) {
              event.preventDefault(); chooseBank(banks[Math.max(0, highlighted)]);
            }
          }} /></label>
        <div className="kw-bank-list" id={suggestionId} role="listbox" aria-label="Банки" hidden={!expanded || busy || !banks.length}>
          {banks.map((item, index) => <button type="button" key={item.id} id={`${suggestionId}-${index}`} role="option" tabIndex={-1}
            aria-selected={highlighted === index} onMouseDown={event => event.preventDefault()} onClick={() => chooseBank(item)}>
            <BankLogo name={item.name} src={item.logo} />{item.name}
          </button>)}
        </div>
        {!banks.length && <p role="status">Ничего не найдено</p>}
        {bank && <p>Выбран: {bank.name}</p>}
        <button type="button" disabled={busy} onClick={onImport}>Импортировать со скриншота</button>
      </>}
      <button className="kw-primary" type="submit" disabled={busy || !selected}>{busy ? 'Сохраняем…' : 'Добавить карту'}</button>
      {error && <p className="kw-error" role="alert">{error}</p>}
    </form>
  </Modal>;
}

function parseHundredths(input: string, invalid: string, max = MAX_KOPECKS): number | null {
  const text = input.trim();
  if (!text) return null;
  if (!/^\d+(?:[.,]\d{1,2})?$/.test(text)) throw new Error(invalid);
  const [whole, fraction = ''] = text.split(/[.,]/);
  const amount = Number(whole) * 100 + Number(fraction.padEnd(2, '0'));
  if (!Number.isSafeInteger(amount) || amount > max) throw new Error(max === MAX_KOPECKS ? 'Сумма превышает допустимый максимум' : invalid);
  return amount;
}

function LimitFields({ label, info, prefix, invalid }: { label: string; info: LimitInfo; prefix: string; invalid: string }) {
  return <fieldset>
    <legend>{label}</legend>
    <label>Лимит, ₽<input name={`${prefix}-limit`} inputMode="decimal" placeholder="Не указано"
      aria-invalid={invalid === `${prefix}-limit` || undefined} defaultValue={info.limitKopecks === null ? '' : String(info.limitKopecks / 100)} /></label>
    <label>Уже получено, ₽<input name={`${prefix}-used`} inputMode="decimal" placeholder="Не указано"
      aria-invalid={invalid === `${prefix}-used` || undefined} defaultValue={info.usedKopecks === null ? '' : String(info.usedKopecks / 100)} /></label>
    <p>{info.remainingKopecks === null ? 'Лимит не указан' : `Осталось ${rubles.format(info.remainingKopecks / 100)}`}
      {info.bankBalanceApplied ? ' · по сверке с банком' : info.limitKopecks !== null && info.usedKopecks === null ? ' · начисления не указаны' : ''}</p>
  </fieldset>;
}

function LimitsEditor({ card, revision, onSaved }: { card: Card; revision: number; onSaved: () => void }) {
  const [data, setData] = useState<CardLimits | null>(null);
  const [loadError, setLoadError] = useState('');
  const [retry, setRetry] = useState(0);
  const [savedVersion, setSavedVersion] = useState(0);
  const [formError, setFormError] = useState('');
  const [success, setSuccess] = useState(false);
  const [invalid, setInvalid] = useState('');
  const [busy, setBusy] = useState(false);
  const saveButton = useRef<HTMLButtonElement>(null);
  const endpoint = limitsPath(card);
  useEffect(() => {
    let current = true;
    setLoadError(''); setData(null); setFormError(''); setInvalid(''); setSuccess(false);
    void api<CardLimits>(endpoint).then(value => { if (current) setData(value); }, failure => {
      if (current) setLoadError(message(failure));
    });
    return () => { current = false; };
  }, [endpoint, retry, revision]);
  useEffect(() => {
    if (savedVersion > 0) saveButton.current?.focus({ preventScroll: true });
  }, [savedVersion]);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!data || busy) return;
    const form = event.currentTarget;
    const fields = new FormData(form);
    let field = '';
    const read = (prefix: string): Limits => {
      field = `${prefix}-limit`;
      const limitKopecks = parseHundredths(String(fields.get(field) ?? ''), 'Проверьте сумму лимита');
      field = `${prefix}-used`;
      const usedKopecks = parseHundredths(String(fields.get(field) ?? ''), 'Проверьте сумму полученного кэшбэка');
      if (limitKopecks !== null && usedKopecks !== null && usedKopecks > limitKopecks) throw new Error('Уже получено не может быть больше лимита');
      return { limitKopecks, usedKopecks };
    };
    setFormError(''); setInvalid(''); setSuccess(false);
    let payload;
    try {
      payload = { month: data.month, card: read('card'), categories: data.categories.map((item, index) => ({ categoryId: item.categoryId, ...read(`category-${index}`) })) };
    } catch (failure) {
      setFormError(message(failure)); setInvalid(field);
      (form.elements.namedItem(field) as HTMLInputElement | null)?.focus();
      return;
    }
    setBusy(true);
    try {
      const updated = await api<CardLimits>(endpoint, json('PUT', payload));
      setData(updated); setSavedVersion(value => value + 1); setSuccess(true); onSaved();
    } catch (failure) { setFormError(message(failure)); }
    finally { setBusy(false); }
  };

  return <section className="kw-limits" aria-label="Лимиты кэшбэка на месяц">
    <h3>Лимиты кэшбэка на месяц</h3>
    {loadError ? <><p className="kw-error" role="alert">{loadError}</p><button type="button" onClick={() => setRetry(value => value + 1)}>Повторить загрузку</button></>
      : !data ? <p role="status">Загружаем лимиты…</p>
      : <form className="kw-form" key={savedVersion} onSubmit={submit}>
        <p>{monthName.format(new Date(`${data.month}-01T00:00:00Z`))}. Сверьте сумму уже полученного кэшбэка с приложением банка.</p>
        <LimitFields label="Вся карта" info={data.card} prefix="card" invalid={invalid} />
        {data.categories.map((item, index) => <LimitFields key={item.categoryId} label={item.label} info={item} prefix={`category-${index}`} invalid={invalid} />)}
        {!data.categories.length && <p>Добавьте категории кэшбэка, чтобы указать лимиты для каждой из них.</p>}
        <button ref={saveButton} type="submit" className="kw-primary" disabled={busy}>{busy ? 'Сохраняем…' : 'Сохранить лимиты'}</button>
        <p className="kw-error" role="status">{formError}</p>
        {success && <p role="status">Лимиты сохранены</p>}
      </form>}
  </section>;
}

function RuleEditor({ card, rule, name, onSaved }: { card: Card; rule: CardRule; name: string; onSaved: (rule: CardRule) => void }) {
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (busy) return;
    const fields = new FormData(event.currentTarget);
    const text = (field: string) => String(fields.get(field) ?? '').trim();
    setError('');
    try {
      const label = text('label');
      if (!label || label.length > 80) throw new Error('Укажите название категории (не более 80 символов).');
      const rateBps = parseHundredths(text('rate'), 'Введите ставку от 0 до 100 %.', 10_000);
      if (rateBps === null) throw new Error('Введите ставку от 0 до 100 %.');
      const limitKopecks = parseHundredths(text('limit'), 'Введите лимит в рублях.');
      const validFrom = text('from') || null;
      const validThrough = text('through') || null;
      if (validFrom && validThrough && validFrom > validThrough) throw new Error('Дата начала не может быть позже даты окончания.');
      if (rule.month && [validFrom, validThrough].some(date => date !== null && date.slice(0, 7) !== rule.month)) {
        throw new Error('Укажите даты в пределах месяца действия категории.');
      }
      setBusy(true);
      await api<void>(`${cardPath(card)}/rate`, json('PATCH', {
        categoryId: rule.categoryId, label: rule.label ?? null, source: rule.source === 'active' ? 'active' : 'base', month: rule.month,
        newLabel: label, rateBps, limitKopecks, validFrom, validThrough,
      }));
      setOpen(false);
      onSaved({ ...rule, label, rateBps, limitKopecks, validFrom, validThrough });
    } catch (failure) { setError(message(failure)); }
    finally { setBusy(false); }
  };

  return <details open={open} onToggle={event => setOpen(event.currentTarget.open)}>
    <summary>Изменить {name}</summary>
    {open && <form className="kw-form" onSubmit={submit}>
      <label>Название категории<input name="label" defaultValue={name} required maxLength={80} /></label>
      <label>Ставка, %<input name="rate" defaultValue={String(rule.rateBps / 100)} required inputMode="decimal" /></label>
      <label>Лимит кэшбэка, ₽<input name="limit" inputMode="decimal" placeholder="Не указан" defaultValue={rule.limitKopecks == null ? '' : String(rule.limitKopecks / 100)} /></label>
      <label>Действует с<input name="from" type="date" defaultValue={rule.validFrom ?? ''} /></label>
      <label>Действует по включительно<input name="through" type="date" defaultValue={rule.validThrough ?? ''} /></label>
      <p>Лимит и даты необязательны{rule.month ? `; даты должны быть в пределах месяца ${rule.month}` : ''}.</p>
      <button type="submit" className="kw-primary" disabled={busy}>{busy ? 'Сохраняем…' : 'Сохранить'}</button>
      {error && <p className="kw-error" role="alert">{error}</p>}
    </form>}
  </details>;
}

function DeleteDialog({ card, onClose, onDeleted }: { card: Card; onClose: () => void; onDeleted: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const remove = async () => {
    if (busy) return;
    setBusy(true); setError('');
    try {
      await api<void>(cardPath(card), { method: 'DELETE' });
      onDeleted();
    } catch (failure) { setError(message(failure)); }
    finally { setBusy(false); }
  };
  return <Modal title="Удалить карту?" busy={busy} onClose={onClose}>
    <p>Карта «{card.cardName}» исчезнет из кошелька вместе с её условиями. Покупки останутся в истории.</p>
    <div className="kw-delete-actions">
      <button type="button" disabled={busy} onClick={onClose}>Отмена</button>
      <button type="button" className="kw-danger" disabled={busy} onClick={() => { void remove(); }}>{busy ? 'Удаляем…' : 'Удалить карту'}</button>
    </div>
    {error && <p className="kw-error" role="alert">{error}</p>}
  </Modal>;
}

export default function Wallet({ onEdit }: WalletProps = {}) {
  const [demo] = useState(() => new URLSearchParams(window.location.search).get('demo') === 'cards');
  const [demoCount, setDemoCount] = useState(7);
  const [deck, setDeck] = useState<Deck | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const [limitsRevision, setLimitsRevision] = useState(0);
  const [loadError, setLoadError] = useState('');
  const [notice, setNotice] = useState('');
  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(''), 3000);
    return () => window.clearTimeout(timer);
  }, [notice]);
  const [dialog, setDialog] = useState<'add' | 'settings' | 'delete' | null>(null);
  const [backToSettings, setBackToSettings] = useState(false);
  const titleId = useId();
  const title = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (demo) return;
    let current = true;
    setLoadError('');
    void loadDeck().then(value => { if (current) setDeck(value); }, failure => {
      if (current) setLoadError(message(failure));
    });
    return () => { current = false; };
  }, [demo, revision]);
  useEffect(() => {
    if (demo) return;
    const refresh = () => setRevision(value => value + 1);
    document.addEventListener('wallet-updated', refresh);
    return () => document.removeEventListener('wallet-updated', refresh);
  }, [demo]);

  const cards = demo ? DEMO_DECK.slice(0, demoCount) : deck?.cards ?? [];
  const index = Math.max(0, cards.findIndex(item => item.cardId === selectedId));
  const card = cards[index];
  const banks = deck?.meta.banks ?? [];
  const categories = demo ? demoCategories : deck?.meta.categories ?? {};
  const close = () => setDialog(null);
  const select = (next: number) => { setSelectedId(cards[next].cardId); close(); };
  const selectDemo = (size: number) => { setDemoCount(size); setSelectedId(null); };
  const edit = (target: Card | null) => {
    close();
    if (onEdit) onEdit(target);
    else document.dispatchEvent(new CustomEvent<Card | null>('kopicash:edit-card', { detail: target }));
  };
  const added = (next: Card) => {
    setDeck(current => {
      if (!current) return current;
      const list = [...current.cards, next];
      return { ...current, cards: list.filter(item => item.kind === 'catalog').sort((a, b) => a.cardId.localeCompare(b.cardId)).concat(list.filter(item => item.kind === 'manual')) };
    });
    setSelectedId(next.cardId); close(); setNotice('Карта добавлена');
  };
  const askDelete = (fromSettings: boolean) => { setBackToSettings(fromSettings); setDialog('delete'); };
  const removed = () => {
    if (!card) return;
    setSelectedId(cards[index + 1]?.cardId ?? cards[index - 1]?.cardId ?? null);
    setDeck(current => current && { ...current, cards: current.cards.filter(item => item.cardId !== card.cardId) });
    close(); setNotice('Карта удалена');
    requestAnimationFrame(() => title.current?.focus({ preventScroll: true }));
  };
  const updateRule = (ruleIndex: number, rule: CardRule) => {
    setDeck(current => current && { ...current, cards: current.cards.map(item => item.cardId === card.cardId
      ? { ...item, rules: item.rules.map((old, i) => i === ruleIndex ? rule : old) } : item) });
    setLimitsRevision(value => value + 1); setNotice('Условия обновлены');
  };
  const ruleName = (rule: CardRule) => rule.label || categories[rule.categoryId] || rule.categoryId;

  return <section className="kw-wallet" aria-labelledby={titleId}>
    <header className="kw-heading">
      <h1 id={titleId} ref={title} tabIndex={-1}>Мои карты</h1>
      {!demo && <button type="button" className="kw-primary" disabled={!deck} onClick={() => { setNotice(''); setDialog('add'); }}>＋ Добавить карту</button>}
    </header>
    {demo && <div className="kw-demo">
      <div role="group" aria-label="Сколько карт показать">{DEMO_COUNTS.map(count => <button type="button" key={count}
        aria-pressed={demoCount === count} onClick={() => selectDemo(count)}>{count}</button>)}</div>
      <button type="button" onClick={() => selectDemo(7)}>Сначала</button><a href="/">В приложение</a>
    </div>}
    {loadError && <div role="alert"><p className="kw-error">{loadError}</p>
      <button type="button" onClick={() => setRevision(value => value + 1)}>Повторить загрузку</button></div>}
    {!demo && !deck && !loadError && <p role="status">Загружаем кошелёк…</p>}
    {card ? <div className="kw-layout">
      <Carousel cards={cards} banks={banks} index={index} onSelect={select} />
      <div className="kw-details">
        <h2>{card.cardName}</h2>
        {card.demo ? <>
          <p>Ставки демонстрационные</p>
          <ul className="kw-rules">{card.rules.map(rule => <li key={rule.categoryId}>
            <div><strong>{ruleName(rule)}</strong><strong>{percent.format(rule.rateBps / 10_000)}</strong></div>
          </li>)}</ul>
        </> : <div className="kw-card-actions">
          <button type="button" className="kw-primary" onClick={() => card.rules.length ? setDialog('settings') : edit(card)}>
            {card.rules.length ? 'Настройки карты' : 'Добавить категории'}
          </button>
          {!card.rules.length && <button type="button" onClick={() => setDialog('settings')}>Настройки карты</button>}
          {card.rules.length > 0 && <ul className="kw-rules">{card.rules.map((rule, i) => <li key={`${rule.categoryId}-${i}`}>
            <div><strong>{ruleName(rule)}</strong><strong>{percent.format(rule.rateBps / 10_000)}</strong></div>
          </li>)}</ul>}
          <button type="button" className="kw-delete" onClick={() => askDelete(false)}>Удалить карту</button>
        </div>}
      </div>
    </div> : deck && <div className="kw-empty"><div aria-hidden="true" /><h2>Кошелёк пуст</h2><p>Добавьте карту, чтобы сравнить кэшбэк.</p></div>}
    <p className="kw-notice" role="status">{notice}</p>
    {dialog === 'add' && deck && <AddCardDialog deck={deck} onAdded={added} onClose={close} onImport={() => edit(null)} />}
    {dialog === 'settings' && card && <Modal title="Настройки карты" onClose={close}>
      <p className="kw-settings-name">{card.cardName}</p>
      {card.rules.length > 0 && <ul className="kw-rules">{card.rules.map((rule, ruleIndex) => {
        const name = ruleName(rule);
        const terms = [rule.limitKopecks == null ? '' : `Лимит: ${rubles.format(rule.limitKopecks / 100)}`,
          rule.validFrom ? `с ${rule.validFrom.split('-').reverse().join('.')}` : '',
          rule.validThrough ? `по ${rule.validThrough.split('-').reverse().join('.')} включительно` : ''].filter(Boolean);
        return <li key={`${rule.source ?? 'base'}-${rule.categoryId}-${ruleIndex}`}>
          <div><strong>{name}</strong><strong>{percent.format(rule.rateBps / 10_000)}</strong></div>
          {terms.length > 0 && <p>{terms.join(' · ')}</p>}
          {card.kind === 'manual' && <RuleEditor card={card} rule={rule} name={name} onSaved={changed => updateRule(ruleIndex, changed)} />}
        </li>;
      })}</ul>}
      <button type="button" className="kw-primary" onClick={() => edit(card.kind === 'manual' ? card : null)}>
        {card.kind === 'manual' && card.rules.length ? 'Обновить категории' : 'Добавить категории'}
      </button>
      <LimitsEditor card={card} revision={limitsRevision} onSaved={() => setNotice('Лимиты сохранены')} />
      <button type="button" className="kw-delete" onClick={() => askDelete(true)}>Удалить карту</button>
    </Modal>}
    {dialog === 'delete' && card && <DeleteDialog card={card} onDeleted={removed} onClose={() => setDialog(backToSettings ? 'settings' : null)} />}
  </section>;
}
