import { Fragment, useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { api } from './api';

export type Meta = { categories: Record<string, string>; banks: { id: string; name: string }[] };
export type PurchaseInput = { categoryId: string; amountKopecks: number };
type Scope = 'all' | 'mine';
type Calculation = {
  beforeLimitsKopecks: number;
  afterCategoryLimitKopecks: number;
  afterMonthlyCategoryLimitKopecks?: number;
  monthlyRemainingKopecks?: number | null;
  monthlyCategoryRemainingKopecks?: number | null;
  monthlyUsageKnown?: boolean;
  monthlyCategoryUsageKnown?: boolean;
};
type Match = {
  cardId: string;
  bankName: string;
  cardName: string;
  categoryId: string;
  cashbackKopecks: number;
  rateBps: number;
  label?: string | null;
  source?: string;
  calculation?: Calculation;
  limitKopecks?: number | null;
  minAmountKopecks?: number | null;
  validFrom?: string | null;
  validUntilExclusive?: string | null;
  updatedOn?: string | null;
};
type Recommendations = { top3: Match[]; allMatches: Match[] };
type CheckoutData = { meta: Meta; hasCards: boolean; login: string | null };
type Receipt = { signature: string; id: string };

const number = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 });
const date = new Intl.DateTimeFormat('ru-RU', { timeZone: 'UTC' });
export const money = (kopecks: number) => `${number.format(kopecks / 100)}\u00a0₽`;
export const rubles = (kopecks: number) => number.format(kopecks / 100);
export const errorText = (error: unknown, fallback: string) => error instanceof Error && error.message ? error.message : fallback;
export const json = (method: 'POST' | 'PUT', body: unknown): RequestInit => ({
  method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
});

export function parseAmount(raw: string, allowZero = false): { value: number } | { message: string } {
  const text = raw.trim();
  if (!text) return { message: 'Введите сумму покупки.' };
  if (text.startsWith('-')) return { message: 'Сумма не может быть отрицательной.' };
  if (/[.,]\d{3,}$/.test(text)) return { message: 'Укажите не больше двух знаков после запятой.' };
  const match = /^(\d+|\d{1,3}(?:[ \u00a0\u202f]\d{3})+)(?:[.,](\d{1,2}))?$/.exec(text);
  if (!match) return { message: 'Введите сумму целиком, например 2 500,50.' };
  const value = Number(match[1].replace(/\s/g, '')) * 100 + Number((match[2] ?? '').padEnd(2, '0'));
  if (value > 1e12) return { message: 'Максимальная сумма — 10 000 000 000 ₽.' };
  return value > 0 || allowZero ? { value } : { message: 'Сумма должна быть больше нуля.' };
}

const icons: Record<string, string> = {
  supermarkets: 'M2 3h3l3 13h12l2-10H6 M9 19a1.5 1.5 0 1 0 .1 0 M18 19a1.5 1.5 0 1 0 .1 0',
  cafe: 'M3 8h14v5a6 6 0 0 1-6 6H9a6 6 0 0 1-6-6z M17 9h2a3 3 0 0 1 0 6h-2 M3 22h16 M7 3v2 M12 2v3',
  fuel: 'M3 21V4a1 1 0 0 1 1-1h9a1 1 0 0 1 1 1v17 M2 21h14 M6 6h5v5H6z M14 12h2a2 2 0 0 1 2 2v3a2 2 0 0 0 4 0V9l-4-4 M20 7v3h2',
  pharmacy: 'M8 3h8v5h5v8h-5v5H8v-5H3V8h5z',
  transport: 'M5 17V6q0-3 7-3t7 3v11q0 2-2 2H7q-2 0-2-2z M5 11h14 M8 15h1 M15 15h1 M7 20l-2 2 M17 20l2 2',
  clothing: 'M8 3q4 4 8 0l6 4-3 5-3-2v11H8V10l-3 2-3-5z',
  electronics: 'M3 4h18v13H3z M12 17v4 M8 21h8',
  marketplace: 'M3 8l3-5h12l3 5v2q-2 3-4 0-3 3-5 0-3 3-5 0-2 3-4 0z M5 13v8h14v-8',
  entertainment: 'M3 7l16-5 2 5-16 5z M4 12h17v9H4z M8 6l3 3 M14 4l3 3',
  utilities: 'M13 2L5 14h6l-1 8 9-13h-7z',
  travel: 'M3 8h18v13H3z M9 8V4h6v4 M7 9v11 M17 9v11',
  all: 'M2 5h20v14H2z M3 10h18 M6 15h3', other: 'M3 5h12l7 7-10 10-9-9z M7 9h1',
};
const sources: Record<string, string> = { catalog: 'Учебный каталог', manual: 'Условия из вашего кошелька', confirmed: 'Подключённые условия' };
const dayText = (day: string) => date.format(new Date(`${day}T00:00:00Z`));

function CategoryIcon({ id }: { id: string }) {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d={icons[id] ?? icons.other} /></svg>;
}

function Advice({ match: card, index, all, category, categories }: {
  match: Match; index: number; all: Match[]; category: string; categories: Record<string, string>;
}) {
  const name = card.bankName === card.cardName ? card.cardName : `${card.bankName} · ${card.cardName}`;
  const rate = `${number.format(card.rateBps / 100)}%`;
  const calc = card.calculation;
  const applied = calc && calc.afterCategoryLimitKopecks < calc.beforeLimitsKopecks;
  const tie = all.some((other) => other.cardId !== card.cardId && other.cashbackKopecks === card.cashbackKopecks);
  const rival = all[1];
  let why: string | undefined;
  if (calc?.monthlyRemainingKopecks != null && calc.monthlyRemainingKopecks < (calc.afterMonthlyCategoryLimitKopecks ?? calc.afterCategoryLimitKopecks)) {
    why = `По ставке ${money(calc.beforeLimitsKopecks)}. Остаток месяца — ${money(calc.monthlyRemainingKopecks)}.`;
  } else if (calc?.monthlyCategoryRemainingKopecks != null && calc.monthlyCategoryRemainingKopecks < calc.afterCategoryLimitKopecks) {
    why = `По ставке ${money(calc.beforeLimitsKopecks)}. Остаток по категории — ${money(calc.monthlyCategoryRemainingKopecks)}.`;
  } else if (applied && card.limitKopecks != null) {
    why = `Учтён лимит на покупку ${money(card.limitKopecks)}.`;
  } else if (rival && tie) {
    why = `Две карты дают по ${money(card.cashbackKopecks)}.`;
  } else if (rival && card.cashbackKopecks > rival.cashbackKopecks) {
    why = `На ${money(card.cashbackKopecks - rival.cashbackKopecks)} больше, чем «${rival.cardName}».`;
  }
  const terms: [string, string][] = [
    ['Ставка', rate], ['Категория правила', card.label || categories[card.categoryId] || card.categoryId],
    ['Минимальная покупка', card.minAmountKopecks == null ? 'Не указана' : money(card.minAmountKopecks)],
    ['Лимит на покупку', card.limitKopecks === null ? 'Без ограничения' : card.limitKopecks === undefined ? 'Неизвестен' : `${money(card.limitKopecks)} · ${applied ? 'применён' : 'не применён'}`],
  ];
  if (calc?.monthlyCategoryRemainingKopecks != null) terms.push(['Остаток по категории', money(calc.monthlyCategoryRemainingKopecks) + (calc.monthlyCategoryUsageKnown ? '' : ' · начисления не указаны')]);
  if (calc?.monthlyRemainingKopecks != null) terms.push(['Остаток месяца', money(calc.monthlyRemainingKopecks) + (calc.monthlyUsageKnown ? '' : ' · начисления не указаны')]);
  terms.push(
    ['Ожидаемый кэшбэк', money(card.cashbackKopecks)],
    ['Период', (card.validFrom ? `С ${dayText(card.validFrom)}` : 'Начало неизвестно') + (card.validUntilExclusive ? ` до ${dayText(card.validUntilExclusive)} (не включая)` : ' · конец не указан')],
    ['Актуальность', card.updatedOn ? dayText(card.updatedOn) : 'Дата не указана'],
    ['Источник', (card.source && (sources[card.source] ?? card.source)) || (card.cardId.startsWith('manual-') ? sources.manual : sources.catalog)],
  );
  return <article className={index ? 'advice-row' : 'advice-winner'}>
    <h4>{name}</h4>
    {index === 0 ? <>
      <p className="advice-lead"><strong className="advice-value">{money(card.cashbackKopecks)}</strong>{` · ${rate} на ${category.toLowerCase()}`}</p>
      {why && <p className="buy-why">{why}</p>}
    </> : <p className="advice-line">{money(card.cashbackKopecks)}</p>}
    {tie && <p className="buy-note">Ещё одна карта даёт такой же возврат.</p>}
    <details><summary>Условия</summary><dl>{terms.map(([key, value]) => <Fragment key={key}><dt>{key}</dt><dd>{value}</dd></Fragment>)}</dl></details>
  </article>;
}

function loadCheckout(signal: AbortSignal): Promise<CheckoutData> {
  return Promise.all([
    api<Meta>('/api/meta', { signal }),
    api<string[]>('/api/me/cards', { signal }),
    api<{ cardId: string }[]>('/api/me/manual-cards', { signal }),
    api<{ login?: string | null }>('/api/auth/me', { signal }),
  ]).then(([meta, saved, manual, auth]) => ({ meta, hasCards: Boolean(saved.length || manual.length), login: auth.login ?? null }));
}

function readReceipt(key: string): Receipt | null {
  try {
    const raw = window.sessionStorage.getItem(key);
    if (!raw) return null;
    const value: unknown = JSON.parse(raw);
    if (typeof value !== 'object' || value === null || !('signature' in value) || !('id' in value)) return null;
    return typeof value.signature === 'string' && typeof value.id === 'string' ? { signature: value.signature, id: value.id } : null;
  } catch { return null; }
}

function storeReceipt(key: string, receipt: Receipt | null) {
  try {
    if (receipt) window.sessionStorage.setItem(key, JSON.stringify(receipt));
    else window.sessionStorage.removeItem(key);
  } catch { /* The in-memory key still protects retries on this screen. */ }
}

export default function Checkout() {
  const [checkout, setCheckout] = useState<CheckoutData>();
  const [walletError, setWalletError] = useState('');
  const [walletRevision, setWalletRevision] = useState(0);
  const [scope, setScope] = useState<Scope>('all');
  const [categoryId, setCategoryId] = useState('');
  const [expanded, setExpanded] = useState(true);
  const [more, setMore] = useState(false);
  const [amount, setAmount] = useState('');
  const [revision, setRevision] = useState(0);
  const [outcome, setOutcome] = useState<{ key: string; data?: Recommendations; error?: string }>();
  const [paidWith, setPaidWith] = useState('');
  const [recording, setRecording] = useState(false);
  const [recordError, setRecordError] = useState('');
  const [recorded, setRecorded] = useState('');
  const lock = useRef(false);
  const receiptRef = useRef<Receipt | null>(null);
  const changeButton = useRef<HTMLButtonElement>(null);
  const tiles = useRef<HTMLDivElement>(null);
  const amountInput = useRef<HTMLInputElement>(null);
  const historyLink = useRef<HTMLButtonElement>(null);
  const preferredScope = useRef(false);
  const categories = checkout?.meta.categories ?? {};
  const category = categories[categoryId] ?? categoryId;
  const parsed = parseAmount(amount);
  const value = 'value' in parsed ? parsed.value : null;
  const key = JSON.stringify([categoryId, amount, scope, revision]);
  const result = outcome?.key === key ? outcome : undefined;
  const matches = result?.data?.allMatches;

  useEffect(() => {
    const controller = new AbortController();
    loadCheckout(controller.signal).then((data) => {
      if (controller.signal.aborted) return;
      setCheckout(data);
      setWalletError('');
      if (!preferredScope.current) setScope(data.hasCards ? 'mine' : 'all');
    }, (error: unknown) => {
      if (!controller.signal.aborted) setWalletError(errorText(error, 'Не удалось загрузить кошелёк.'));
    });
    return () => controller.abort();
  }, [walletRevision]);

  useEffect(() => {
    if (value === null || !categoryId) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      api<Recommendations>('/api/recommendations', {
        ...json('POST', { categoryId, amountKopecks: value, scope }), signal: controller.signal,
      }).then((data) => {
        if (!controller.signal.aborted) setOutcome({ key, data });
      }, (error: unknown) => {
        if (!controller.signal.aborted) setOutcome({ key, error: errorText(error, 'Не удалось рассчитать кэшбэк. Проверьте соединение и повторите.') });
      });
    }, 160);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [categoryId, key, scope, value]);

  useEffect(() => { if (recorded) historyLink.current?.focus(); }, [recorded]);

  function changeInput() {
    setPaidWith('');
    setRecordError('');
    setRecorded('');
    setRevision((current) => current + 1);
  }

  async function record(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (lock.current || value === null || !matches?.some((match) => match.cardId === paidWith)) return;
    const body = { chosenCardId: paidWith, categoryId, amountKopecks: value };
    const signature = JSON.stringify(body);
    const storageKey = `advisor-purchase:${checkout?.login ?? 'local'}`;
    let receipt = receiptRef.current ?? readReceipt(storageKey);
    if (receipt?.signature !== signature) {
      receipt = { signature, id: Array.from(crypto.getRandomValues(new Uint8Array(16)), (byte) => byte.toString(16).padStart(2, '0')).join('') };
    }
    receiptRef.current = receipt;
    storeReceipt(storageKey, receipt);
    lock.current = true;
    setRecording(true);
    setRecordError('');
    try {
      await api('/api/me/purchases', {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': receipt.id },
        body: JSON.stringify({ ...body, requestId: receipt.id }),
      });
      receiptRef.current = null;
      storeReceipt(storageKey, null);
      try { window.sessionStorage.removeItem('advisor-history-month'); } catch { /* History defaults to the current month. */ }
      setAmount('');
      setPaidWith('');
      setRecorded(`Покупка записана. ${category} · ${money(value)}`);
      document.dispatchEvent(new Event('purchase-updated'));
    } catch (error) {
      setRecordError(error instanceof TypeError
        ? 'Не удалось подтвердить запись. Повторите с теми же данными — дубля не будет.'
        : errorText(error, 'Не удалось подтвердить запись.'));
    } finally {
      lock.current = false;
      setRecording(false);
    }
  }

  const status = recorded || walletError || (!checkout ? 'Загружаем категории…' : !categoryId ? 'Выберите категорию покупки.'
    : 'message' in parsed ? parsed.message : result?.error ? result.error : !matches ? 'Считаем…'
    : matches.length === 0 ? scope === 'all' ? 'В каталоге подходящих условий нет.' : checkout.hasCards ? 'По вашим картам подходящих условий нет.' : 'Кошелёк пуст. Добавьте карту.'
    : matches[0].cashbackKopecks === 0 ? `В категории «${category}» — 0 ₽.` : `Ожидаемый возврат · карт в сравнении: ${matches.length}`);
  const top = result?.data?.top3 ?? [];
  const remaining = matches?.slice(top.length) ?? [];
  const categoryEntries = Object.entries(categories);

  return <section id="buyPanel" className="panel buy-panel" aria-labelledby="buyTitle">
    <h1 id="buyTitle" className="screen-title" tabIndex={-1}>Сравнить карты</h1>
    <div className="buy-switch" role="group" aria-label="Какие карты сравнить">
      {(['all', 'mine'] as const).map((item) => <button type="button" key={item} id={item === 'all' ? 'scopeAll' : 'scopeMine'} aria-pressed={scope === item} disabled={recording || (item === 'mine' && !checkout)} onClick={() => {
        preferredScope.current = true;
        if (scope !== item) { setScope(item); changeInput(); }
      }}>{item === 'all' ? 'Все карты' : 'Мои карты'}</button>)}
    </div>
    <div className="buy-body">
      <div className="buy-inputs">
        <h3 id="categoryHeading" hidden={Boolean(categoryId)}>Выберите категорию</h3>
        <button id="changeCategory" ref={changeButton} type="button" hidden={!categoryId} disabled={recording} aria-expanded={expanded} aria-controls="categoryGrid" onClick={() => {
          setExpanded(!expanded);
          if (!expanded) requestAnimationFrame(() => tiles.current?.querySelector<HTMLButtonElement>('[aria-pressed=true]')?.focus());
        }}><CategoryIcon id={categoryId} /><strong>{category}</strong><span>{expanded ? 'Свернуть' : 'Изменить'}</span></button>
        <div id="categoryGrid" ref={tiles} className="category-grid" role="group" aria-label="Категория покупки" hidden={!expanded} style={expanded ? { display: 'grid' } : undefined}>
          {categoryEntries.map(([id, name], index) => <button key={id} type="button" data-id={id} className={`tile${name.length > 12 ? ' tile-wide' : ''}`} aria-pressed={id === categoryId} hidden={index >= 6 && !more && id !== categoryId} disabled={recording} onClick={() => {
            setCategoryId(id); setExpanded(false); changeInput();
            requestAnimationFrame(() => changeButton.current?.focus({ preventScroll: true }));
          }}><CategoryIcon id={id} /><span>{name}</span></button>)}
        </div>
        <button id="moreCategories" aria-expanded={more} aria-controls="categoryGrid" className="buy-secondary" type="button" hidden={!expanded || categoryEntries.length <= 6} disabled={recording} onClick={() => {
          setMore(!more);
          if (!more) requestAnimationFrame(() => (tiles.current?.children[6] as HTMLButtonElement | undefined)?.focus());
        }}>{more ? 'Скрыть остальные категории' : 'Все категории'}</button>
        <label className="buy-label" htmlFor="buyAmount">Сумма покупки, ₽</label>
        <div className="amount-wrap">
          <input id="buyAmount" ref={amountInput} className="buy-amount" name="purchaseAmount" inputMode="decimal" autoComplete="off" placeholder="Например, 2 500" aria-describedby="buyStatus" aria-invalid={Boolean(amount) && value === null} value={amount} readOnly={recording} onChange={(event) => { setAmount(event.target.value); changeInput(); }} />
          <button type="button" id="clearAmount" aria-label="Очистить сумму" hidden={!amount} disabled={recording} onClick={() => { setAmount(''); changeInput(); amountInput.current?.focus(); }}>×</button>
        </div>
      </div>
      <div className="buy-advice">
        <h3>Совет перед оплатой</h3>
        <p id="buyStatus" role="status" aria-live="polite">{status}</p>
        <div id="buyResults">
          {walletError && <button className="buy-secondary" type="button" onClick={() => { setWalletError(''); setWalletRevision((current) => current + 1); }}>Повторить загрузку</button>}
          {recorded && <button type="button" ref={historyLink} className="buy-secondary" onClick={() => { location.hash = 'history'; }}>Открыть историю</button>}
          {result?.error && <button type="button" className="buy-secondary" onClick={changeInput}>Повторить расчёт</button>}
          {matches && <Fragment key={key}>
            {top.map((match, index) => <Advice key={match.cardId} match={match} index={index} all={matches} category={category} categories={categories} />)}
            {remaining.length > 0 && <details className="more-results"><summary>Все подходящие карты ({matches.length})</summary>
              {remaining.map((match, index) => <Advice key={match.cardId} match={match} index={index + top.length} all={matches} category={category} categories={categories} />)}
            </details>}
            {scope === 'mine' && matches.length === 0 && checkout && !checkout.hasCards && <a className="buy-secondary" href="#cards">Добавить карту</a>}
            {scope === 'mine' && matches.length > 0 && value !== null && <form className="record-form" onSubmit={record}>
              <h4>Запись в историю</h4>
              <p>{category} · {money(value)}. Просмотр совета не сохраняет покупку.</p>
              <label htmlFor="paidWith">Какой картой вы оплатили?</label>
              <select id="paidWith" required disabled={recording} value={paidWith} onChange={(event) => { setPaidWith(event.target.value); setRecordError(''); }}>
                <option value="">Выберите карту</option>
                {matches.map((match) => <option key={match.cardId} value={match.cardId}>{match.cardName}</option>)}
              </select>
              <button type="submit" className="buy-primary" disabled={recording}>Записать покупку</button>
              <p role="status">{recording ? 'Записываем…' : recordError}</p>
            </form>}
          </Fragment>}
        </div>
      </div>
    </div>
  </section>;
}
