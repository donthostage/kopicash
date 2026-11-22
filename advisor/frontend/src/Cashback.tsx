import { Fragment, useCallback, useEffect, useRef, useState } from 'react';
import type { FormEvent, ReactNode } from 'react';
import { api } from './api';
import './cashback-screens.css';
import { errorText, json, money, parseAmount, rubles } from './Checkout';
import type { Meta, PurchaseInput } from './Checkout';

export type CashbackView = 'cashback' | 'history' | 'account';

type Purchase = {
  id: number; date: string; categoryId: string; amountKopecks: number; cardId: string;
  chosenName: string | null; chosenKopecks: number | null; recommendedName: string | null;
  recommendedKopecks: number | null; usualKopecks: number | null; actualCashbackKopecks: number | null;
};
type Stats = {
  month: string; count: number; calculatedKopecks: number; missedKopecks: number;
  usualKopecks: number | null; actualCashbackKopecks: number | null; actualCashbackCount: number;
  purchases: Purchase[]; cards: {
    cardId: string; name: string; cashbackKopecks: number; actualCashbackKopecks: number | null; actualCashbackCount: number;
  }[];
};
type PlannedPurchase = { cardId: string | null; cardName: string | null; bankName: string | null; cashbackKopecks: number };
type PurchasePlan = {
  optimized: { totalKopecks: number; purchases: PlannedPurchase[] };
  sequential: { totalKopecks: number; purchases: PlannedPurchase[] };
  gainKopecks: number; assumedFullCardIds: string[];
};
type CategoryPlan = {
  baseKopecks: number; projectedKopecks: number; gainKopecks: number;
  warnings: string[]; choices: { cardId: string; bankId: string; labels: string[] }[];
};
type CategoryPlanInput = { month: string; spendingMonth: string; spending?: PurchaseInput[] };
type DraftRow = { id: number; categoryId: string; amount: string };

const monthAt = (delta = 0) => {
  const now = new Date();
  return new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() + delta, 1)).toISOString().slice(0, 7);
};
const monthFormat = new Intl.DateTimeFormat('ru-RU', { month: 'long', year: 'numeric', timeZone: 'UTC' });
const dayFormat = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', timeZone: 'UTC' });
const monthText = (month: string) => monthFormat.format(new Date(`${month}-01T12:00:00Z`));
const dayText = (day: string) => day ? dayFormat.format(new Date(`${day}T12:00:00Z`)) : 'Без даты';
const initialMeta: Meta = { categories: {}, banks: [] };
const blank = (id: number): DraftRow => ({ id, categoryId: '', amount: '' });

function useMonthlyStats(month: string) {
  const [revision, setRevision] = useState(0);
  const [result, setResult] = useState<{ key: string; data?: Stats; error?: string }>();
  const key = `${month}:${revision}`;
  useEffect(() => {
    const request = new AbortController();
    api<Stats>(`/api/me/stats?month=${encodeURIComponent(month)}`, { signal: request.signal }).then((data) => {
      if (!request.signal.aborted) setResult({ key, data });
    }, (error: unknown) => {
      if (!request.signal.aborted) setResult({ key, error: errorText(error, 'Не удалось загрузить статистику.') });
    });
    return () => request.abort();
  }, [key, month]);
  const reload = useCallback(() => setRevision((current) => current + 1), []);
  return { data: result?.key === key ? result.data : undefined, error: result?.key === key ? result.error : undefined, reload };
}

function useMeta() {
  const [meta, setMeta] = useState(initialMeta);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const request = new AbortController();
    api<Meta>('/api/meta', { signal: request.signal }).then((data) => {
      if (!request.signal.aborted) { setMeta(data); setError(''); }
    }, (cause: unknown) => {
      if (!request.signal.aborted) setError(errorText(cause, 'Не удалось загрузить категории.'));
    });
    return () => request.abort();
  }, [revision]);
  return { meta, error, reload: () => setRevision((current) => current + 1) };
}

function DataError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return <><p role="alert">{message}</p><button type="button" className="buy-secondary" onClick={onRetry}>Повторить загрузку</button></>;
}

function keepHistoryMonth(month: string) {
  try { window.sessionStorage.setItem('advisor-history-month', month); } catch { /* Use current month if storage is unavailable. */ }
}

function savedHistoryMonth() {
  try {
    const saved = window.sessionStorage.getItem('advisor-history-month');
    if (saved && /^\d{4}-(0[1-9]|1[0-2])$/.test(saved)) return saved;
  } catch { /* Use current month if storage is unavailable. */ }
  return monthAt();
}

export function MonthCashback({ month = monthAt() }: { month?: string }) {
  const { data, error, reload } = useMonthlyStats(month);
  useEffect(() => {
    const refresh = () => reload();
    document.addEventListener('purchase-updated', refresh);
    return () => document.removeEventListener('purchase-updated', refresh);
  }, [reload]);
  return <section className="home-month-cashback" id="homeMonthCashback" aria-labelledby="homeMonthCashbackTitle">
    <h2 id="homeMonthCashbackTitle">Кэшбэк за месяц</h2>
    <div id="homeMonthCashbackBody" className={`month-cashback${error ? ' is-error' : data ? '' : ' is-loading'}`} aria-live="polite">
      {error ? <DataError message={error} onRetry={reload} /> : !data ? 'Считаем кэшбэк…' : <>
        {data.count ? <>
          <div className="month-cashback-grid">
            <div className="month-cashback-actual"><span className="month-cashback-kicker">Получено</span>
              {data.actualCashbackKopecks === null ? <span className="month-cashback-pending">—</span> : <strong className="money">{money(data.actualCashbackKopecks)}</strong>}
            </div>
            <div className="month-cashback-side">
              <p><span>По расчёту</span><strong className="money">{money(data.calculatedKopecks)}</strong></p>
              <p><span>Можно было ещё</span><strong className="money">{money(data.missedKopecks)}</strong></p>
            </div>
          </div>
          <p className="month-cashback-meta">{data.actualCashbackCount ? `Подтверждённые начисления: ${data.actualCashbackCount} из ${data.count}` : 'Нет подтверждённых начислений'}</p>
          {data.cards.length > 0 && <details className="month-cashback-cards"><summary>По картам</summary><ul>
            {data.cards.map((card) => <li key={card.cardId}>
              <span className="name">{card.name || card.cardId}</span>
              <span className="vals">{money(card.cashbackKopecks)} по расчёту{card.actualCashbackKopecks === null ? '' : ` · ${money(card.actualCashbackKopecks)} подтверждено (${card.actualCashbackCount})`}</span>
            </li>)}
          </ul></details>}
        </> : <div className="month-cashback-empty"><p className="month-cashback-meta">Покупок в этом месяце пока нет.</p><button type="button" className="month-cashback-action" onClick={() => { location.hash = 'buy'; }}>Рассчитать покупку</button></div>}
        {data.count > 0 && <button type="button" className="month-cashback-journal" onClick={() => { keepHistoryMonth(data.month); location.hash = 'history'; }}>Покупки за месяц</button>}
      </>}
    </div>
  </section>;
}

function PurchaseEntry({ item, category }: { item: Purchase; category: string }) {
  const [detailOpen, setDetailOpen] = useState(false);
  const [editorOpen, setEditorOpen] = useState(false);
  const [confirmed, setConfirmed] = useState(item.actualCashbackKopecks);
  const [amount, setAmount] = useState(() => confirmed === null ? '' : rubles(confirmed));
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const input = useRef<HTMLInputElement>(null);
  const gap = item.recommendedKopecks == null || item.chosenKopecks == null ? null : item.recommendedKopecks - item.chosenKopecks;
  const detailId = `purchase-detail-${item.id}`;
  const editorId = `purchase-cashback-${item.id}`;

  async function update(value: number | null) {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError('');
    try {
      await api<void>(`/api/me/purchases/${encodeURIComponent(item.id)}/cashback`, json('PUT', { amountKopecks: value }));
      setConfirmed(value);
      if (value === null) setAmount('');
      document.dispatchEvent(new Event('purchase-updated'));
    } catch (cause) {
      setError(errorText(cause, value === null ? 'Не удалось удалить отметку.' : 'Не удалось сохранить начисление.'));
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsed = parseAmount(amount, true);
    if ('message' in parsed) { setError(parsed.message); input.current?.focus(); return; }
    void update(parsed.value);
  }

  return <article className="journal-purchase">
    <button type="button" className="journal-row" aria-expanded={detailOpen} aria-controls={detailId} onClick={() => setDetailOpen(!detailOpen)}>
      <span className="journal-main"><span className="journal-title">{category || 'Покупка'}</span><span className="journal-bank">{item.chosenName || 'Карта'}</span>
        {gap !== null && gap > 0 && <span className="journal-gap">Можно было получить ещё {money(gap)}</span>}
      </span>
      <span className="journal-money"><strong className="money">{money(item.amountKopecks)}</strong>
        {item.chosenKopecks != null && <span className="journal-cash">+{money(item.chosenKopecks)}</span>}<span className="journal-chevron" aria-hidden="true" />
      </span>
    </button>
    <div className="journal-detail" id={detailId} hidden={!detailOpen}>
      <p>Выбранная карта: {item.chosenName || '—'}{item.chosenKopecks == null ? '' : `, ${money(item.chosenKopecks)}`}</p>
      <p>Лучшая по расчёту: {item.recommendedName || '—'}{item.recommendedKopecks == null ? '' : `, ${money(item.recommendedKopecks)}`}</p>
      <p>Разница: {gap === null ? '—' : money(gap)}</p>
      {item.usualKopecks != null && <p>Карта для сравнения: {money(item.usualKopecks)}</p>}
    </div>
    {item.id != null && <>
      <button type="button" className="journal-confirm" aria-expanded={editorOpen} aria-controls={editorId} onClick={() => {
        setEditorOpen(!editorOpen);
        if (!editorOpen) requestAnimationFrame(() => input.current?.focus());
      }}>{confirmed === null ? 'Подтвердить кэшбэк' : 'Изменить кэшбэк'}</button>
      <form id={editorId} className="journal-actual" hidden={!editorOpen} onSubmit={save}>
        <h4>Фактический кэшбэк</h4>
        <label>Сколько начислил банк, ₽<input ref={input} inputMode="decimal" autoComplete="off" placeholder="Например, 48" value={amount} readOnly={busy} onChange={(event) => { setAmount(event.target.value); setError(''); }} /></label>
        <p className="journal-actual-note" role="status">{confirmed === null ? 'Начисление ещё не подтверждено' : confirmed === 0 ? 'Подтверждённый ноль' : `Сохранено: ${money(confirmed)}`}</p>
        <div className="journal-actual-actions"><button type="submit" className="primary" disabled={busy}>Сохранить</button>
          {confirmed !== null && <button type="button" disabled={busy} onClick={() => void update(null)}>Удалить отметку</button>}
        </div>
        {error && <p className="journal-actual-error" role="alert">{error}</p>}
      </form>
    </>}
  </article>;
}

function Comparison({ amount }: { amount: number | null }) {
  return amount === null ? null : <p className="journal-meta">По карте для сравнения на момент покупок: {money(amount)}.</p>;
}

function Journal({ data, categories }: { data: Stats; categories: Meta['categories'] }) {
  const [comment, setComment] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const groups = new Map<string, Purchase[]>();
  for (const item of data.purchases) {
    const day = item.date.slice(0, 10);
    const group = groups.get(day);
    if (group) group.push(item); else groups.set(day, [item]);
  }
  async function ask() {
    setBusy(true);
    setError('');
    try {
      const reply = await api<{ comment: string }>(`/api/me/stats/comment?month=${encodeURIComponent(data.month)}`, { method: 'POST' });
      setComment(reply.comment);
    } catch (cause) { setError(errorText(cause, 'Не удалось загрузить разбор.')); }
    finally { setBusy(false); }
  }
  return <>
    <section className="journal-summary">
      <p className="journal-total"><span>Расчётный кэшбэк за месяц</span><strong className="money">{money(data.calculatedKopecks)}</strong></p>
      <Comparison amount={data.usualKopecks} />
      <button type="button" className="buy-primary" disabled={busy} onClick={() => void ask()}>{busy ? 'Разбираем…' : 'Разбор за месяц'}</button>
      {error ? <p role="alert">{error}</p> : comment && <p>{comment}</p>}
    </section>
    {!groups.size && <p>Покупок в этом месяце нет. Запишите покупку после совета.</p>}
    {Array.from(groups, ([day, items]) => <Fragment key={day}>
      <h3 className="journal-day">{dayText(day)}</h3>
      <div className="journal-list">{items.map((item) => <PurchaseEntry key={item.id} item={item} category={categories[item.categoryId] ?? item.categoryId} />)}</div>
    </Fragment>)}
  </>;
}

function History({ categories }: { categories: Meta['categories'] }) {
  const [month, setMonth] = useState(savedHistoryMonth);
  const { data, error, reload } = useMonthlyStats(month);
  return <section id="historyPanel" aria-labelledby="historyTitle">
    <h2 id="historyTitle" tabIndex={-1}>История покупок</h2>
    <label className="history-month-label"><span className="history-month-text">Месяц покупок</span><input id="historyMonth" type="month" value={month} onChange={(event) => {
      const selected = event.target.value || monthAt();
      setMonth(selected); keepHistoryMonth(selected);
    }} /></label>
    <div id="historyBody" className={`journal${error ? ' is-error' : !data ? ' is-loading' : !data.count ? ' is-empty' : ''}`} aria-live="polite">
      {error ? <DataError message={error} onRetry={reload} /> : data ? <Journal key={data.month} data={data} categories={categories} /> : 'Загружаем историю…'}
    </div>
  </section>;
}

function ProfileStats({ categories }: { categories: Meta['categories'] }) {
  const { data, error, reload } = useMonthlyStats(monthAt());
  let content: ReactNode = error ? <DataError message={error} onRetry={reload} /> : 'Загружаем статистику…';
  if (data) {
    const byCategory = new Map<string, number>();
    let total = 0;
    for (const { categoryId, amountKopecks } of data.purchases) {
      byCategory.set(categoryId, (byCategory.get(categoryId) ?? 0) + amountKopecks);
      total += amountKopecks;
    }
    const items = [...byCategory].sort((a, b) => b[1] - a[1]);
    const metrics = [['Потрачено', money(total)], ['Кэшбэк получен', data.actualCashbackKopecks === null ? '—' : money(data.actualCashbackKopecks)], ['Кэшбэк по расчёту', money(data.calculatedKopecks)], ['Покупок', data.count]];
    content = <>
      <p className="profile-month">{monthText(data.month)}</p>
      <dl className="profile-metrics">{metrics.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
      <Comparison amount={data.usualKopecks} />
      {items.length > 0 && <section className="profile-chart"><h3>Траты по категориям</h3><ul>
        {items.map(([id, amount]) => <li key={id}><span>{categories[id] ?? id}</span><strong>{money(amount)}</strong><span className="profile-chart-bar" aria-hidden="true"><span style={{ inlineSize: `${total ? amount / total * 100 : 0}%` }} /></span></li>)}
      </ul></section>}
      <p className="journal-meta">{!data.count ? 'За этот месяц покупок пока нет.' : data.actualCashbackKopecks === null
        ? 'Полученный кэшбэк появится после подтверждения в истории покупок.' : `Подтверждённые начисления: ${data.actualCashbackCount} из ${data.count}.`}</p>
    </>;
  }
  return <section className="profile-statistics" aria-labelledby="profileStatsTitle"><h2 id="profileStatsTitle">Статистика за месяц</h2>
    <div id="accountStats" className={error ? 'account-error' : undefined} aria-live="polite" aria-busy={!data && !error}>{content}</div>
  </section>;
}

function CategoryOptions({ categories }: { categories: Meta['categories'] }) {
  return <><option value="">Выберите категорию</option>{Object.entries(categories).map(([id, name]) => <option key={id} value={id}>{name}</option>)}</>;
}

function PurchasePlanner({ categories }: { categories: Meta['categories'] }) {
  const [rows, setRows] = useState<DraftRow[]>([blank(0), blank(1)]);
  const [invalid, setInvalid] = useState<number>();
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState('');
  const [result, setResult] = useState<{ data: PurchasePlan; purchases: PurchaseInput[] }>();
  const nextRow = useRef(2);
  const request = useRef<AbortController | null>(null);
  const grid = useRef<HTMLDivElement>(null);
  const add = useRef<HTMLButtonElement>(null);
  useEffect(() => () => request.current?.abort(), []);

  function clear() {
    request.current?.abort();
    setInvalid(undefined); setBusy(false); setStatus(''); setResult(undefined);
  }
  function change(id: number, patch: Partial<DraftRow>) {
    clear();
    setRows((current) => current.map((row) => row.id === id ? { ...row, ...patch } : row));
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    clear();
    const purchases: PurchaseInput[] = [];
    for (const [index, row] of rows.entries()) {
      const parsed = parseAmount(row.amount);
      if ('message' in parsed) {
        setInvalid(row.id); setStatus(`Покупка ${index + 1}. ${parsed.message}`);
        grid.current?.querySelector<HTMLInputElement>(`[data-plan-row="${row.id}"] input`)?.focus();
        return;
      }
      purchases.push({ categoryId: row.categoryId, amountKopecks: parsed.value });
    }
    const controller = new AbortController();
    request.current = controller;
    setBusy(true); setStatus('Сравниваем варианты…');
    try {
      const data = await api<PurchasePlan>('/api/me/purchase-plan', { ...json('POST', { purchases }), signal: controller.signal });
      if (controller.signal.aborted) return;
      setResult({ data, purchases }); setStatus('План рассчитан.');
    } catch (cause) {
      if (!controller.signal.aborted) setStatus(errorText(cause, 'Не удалось рассчитать план покупок.'));
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  return <details id="purchasePlan" className="purchase-plan">
    <summary>Спланировать несколько покупок</summary>
    <form id="purchasePlanForm" onSubmit={submit}>
      <p className="buy-note">Выберите покупки на этот месяц. Порядок строк — порядок оплаты.</p>
      <div id="purchasePlanRows" ref={grid}>{rows.map((row, index) => <fieldset key={row.id} data-plan-row={row.id}>
        <legend>Покупка {index + 1}</legend>
        <label>Категория<select value={row.categoryId} required onChange={(event) => change(row.id, { categoryId: event.target.value })}><CategoryOptions categories={categories} /></select></label>
        <label>Сумма, ₽<input value={row.amount} inputMode="decimal" placeholder="Например, 1 000" required aria-invalid={invalid === row.id} onChange={(event) => change(row.id, { amount: event.target.value })} /></label>
        <button type="button" className="buy-secondary" disabled={rows.length <= 2} aria-label={`Удалить покупку ${index + 1}`} onClick={() => {
          clear(); setRows((current) => current.filter((item) => item.id !== row.id)); add.current?.focus();
        }}>Удалить</button>
      </fieldset>)}</div>
      <div className="purchase-plan-actions">
        <button id="purchasePlanAdd" ref={add} type="button" className="buy-secondary" disabled={rows.length >= 8} onClick={() => {
          clear(); const id = nextRow.current++; setRows((current) => [...current, blank(id)]);
          requestAnimationFrame(() => grid.current?.querySelector<HTMLSelectElement>(`[data-plan-row="${id}"] select`)?.focus());
        }}>Добавить покупку</button>
        <button id="purchasePlanSubmit" type="submit" className="buy-primary" disabled={busy}>Рассчитать план</button>
      </div>
    </form>
    <p id="purchasePlanStatus" role="status">{status}</p>
    <div id="purchasePlanResult" hidden={!result}>{result && <>
      <h3>Ожидаемый кэшбэк: {money(result.data.optimized.totalKopecks)}</h3>
      <p>При выборе лучшей карты для каждой покупки по очереди: {money(result.data.sequential.totalKopecks)}.</p>
      {result.data.gainKopecks > 0 && <p className="purchase-plan-gain">+{money(result.data.gainKopecks)} за весь план</p>}
      {result.data.assumedFullCardIds.length > 0 && <p className="buy-note">По некоторым картам начисления за месяц неизвестны. Для них расчёт предполагает полный лимит.</p>}
      <ol>{result.data.optimized.purchases.map((item, index) => {
        const purchase = result.purchases[index];
        const card = !item.cardId ? 'Нет карты с положительным кэшбэком' : item.bankName && item.bankName !== item.cardName ? `${item.bankName} · ${item.cardName}` : item.cardName;
        return <li key={index}><strong>{categories[purchase.categoryId] ?? purchase.categoryId} · {money(purchase.amountKopecks)}</strong><span>{card} · {money(item.cashbackKopecks)}</span></li>;
      })}</ol>
    </>}</div>
  </details>;
}

const noSpending = (data: CategoryPlan) => data.warnings.some((warning) => warning.startsWith('Нет расходов'));
const noTerms = (data: CategoryPlan) => data.warnings.some((warning) => warning.startsWith('Нет подтверждённых условий'));

type PlanCache = { key: string; data: CategoryPlan; time: number };

function CategoryPlanner({ meta, onClose, onForecast, cache }: {
  meta: Meta; onClose: () => void; onForecast: (value: number | null) => void;
  cache: { current: PlanCache | null };
}) {
  const [month, setMonth] = useState(() => monthAt(1));
  const [spendingMonth, setSpendingMonth] = useState(monthAt);
  const [source, setSource] = useState<'history' | 'manual'>('history');
  const [rows, setRows] = useState<DraftRow[]>([blank(0)]);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<{ data: CategoryPlan; body: CategoryPlanInput }>();
  const request = useRef<AbortController | null>(null);
  const nextRow = useRef(1);
  const dialog = useRef<HTMLDialogElement>(null);
  const nextMonth = useRef<HTMLButtonElement>(null);
  const rowsHost = useRef<HTMLDivElement>(null);
  const add = useRef<HTMLButtonElement>(null);
  const resultHeading = useRef<HTMLHeadingElement>(null);
  const manual = source === 'manual';

  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    nextMonth.current?.focus();
    return () => { request.current?.abort(); element?.close(); };
  }, []);
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);
  useEffect(() => { if (result) resultHeading.current?.focus(); }, [result]);

  function clear() {
    request.current?.abort(); setBusy(false); setError(''); setResult(undefined); onForecast(null);
  }
  function close() {
    if (dirty && !window.confirm('Закрыть план? Введённые расходы не сохранятся.')) return;
    onClose();
  }
  function changeRow(id: number, patch: Partial<DraftRow>) {
    clear(); setDirty(true);
    setRows((current) => current.map((row) => row.id === id ? { ...row, ...patch } : row));
  }
  function output(data: CategoryPlan, body: CategoryPlanInput) {
    setResult({ data, body });
    onForecast(noSpending(data) || noTerms(data) ? null : data.projectedKopecks);
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    clear();
    const body: CategoryPlanInput = { month, spendingMonth: spendingMonth || monthAt() };
    if (manual) {
      body.spending = [];
      for (const row of rows) {
        if (!row.categoryId && !row.amount.trim()) continue;
        if (!row.categoryId) { setError('Введите категорию покупки.'); return; }
        const parsed = parseAmount(row.amount);
        if ('message' in parsed) { setError(parsed.message); return; }
        body.spending.push({ categoryId: row.categoryId, amountKopecks: parsed.value });
      }
      if (!body.spending.length) { setError('Введите хотя бы одну покупку.'); return; }
    }
    const key = JSON.stringify(body);
    if (cache.current?.key === key && Date.now() - cache.current.time < 30_000) { output(cache.current.data, body); return; }
    const controller = new AbortController();
    request.current = controller;
    setBusy(true);
    try {
      const data = await api<CategoryPlan>('/api/me/cashback-plan', { ...json('POST', body), signal: controller.signal });
      if (controller.signal.aborted) return;
      if (!noSpending(data) && !noTerms(data)) cache.current = { key, data, time: Date.now() };
      output(data, body);
    } catch (cause) {
      if (!controller.signal.aborted) setError(errorText(cause, 'Не удалось рассчитать план кэшбэка.'));
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  return <dialog id="planDialog" className="react-plan-dialog cashback-dialog" ref={dialog} aria-labelledby="planTitle" onCancel={(event) => { event.preventDefault(); close(); }} onClick={(event) => {
    if (event.target === event.currentTarget) close();
  }}><div className="dialog-card">
    <div className="dialog-head"><h2 id="planTitle">План кэшбэка</h2><button id="closePlan" className="close" type="button" aria-label="Закрыть" onClick={close}>×</button></div>
    <form id="planForm" className="shot-form" onSubmit={submit}>
      <p className="cb-note">Сравните, какие категории подключить в каждом банке. План ничего не меняет в кошельке.</p>
      <div>Месяц выбора<input id="planMonth" type="hidden" value={month} /> <span id="planMonthText" aria-live="polite">{monthText(month)}</span></div>
      <div className="cb-months"><button id="planCurrent" type="button" aria-pressed={month === monthAt()} onClick={() => { clear(); setMonth(monthAt()); }}>Этот месяц</button>
        <button id="planNext" ref={nextMonth} type="button" aria-pressed={month === monthAt(1)} onClick={() => { clear(); setMonth(monthAt(1)); }}>Следующий месяц</button></div>
      <label>Траты для прогноза<select id="spendingSource" value={source} onChange={(event) => { clear(); setSource(event.target.value === 'manual' ? 'manual' : 'history'); }}>
        <option value="history">Из истории покупок</option><option value="manual">Ввести суммы по категориям</option>
      </select></label>
      <label id="spendingPeriod" hidden={manual}>Месяц покупок<input id="spendingMonth" type="month" required disabled={manual} value={spendingMonth} onChange={(event) => { clear(); setSpendingMonth(event.target.value); }} /></label>
      <div id="spendingInputs" hidden={!manual}>
        <p className="cb-note">Одна строка — один чек. Для нескольких покупок одной категории добавьте несколько строк.</p>
        <div id="spendRows" ref={rowsHost}>{rows.map((row) => <div className="cb-fields" key={row.id} data-spend-row={row.id}>
          <label>Категория покупки<select data-key="categoryId" value={row.categoryId} onChange={(event) => changeRow(row.id, { categoryId: event.target.value })}><CategoryOptions categories={meta.categories} /></select></label>
          <label>Сумма, ₽<input data-key="amount" inputMode="decimal" value={row.amount} onChange={(event) => changeRow(row.id, { amount: event.target.value })} /></label>
          <button type="button" onClick={() => { clear(); setDirty(true); setRows((current) => current.filter((item) => item.id !== row.id)); add.current?.focus(); }}>Убрать покупку</button>
        </div>)}</div>
        <button id="addSpend" ref={add} type="button" disabled={rows.length >= 1000} onClick={() => {
          clear(); setDirty(true); const id = nextRow.current++;
          setRows((current) => [...current, blank(id)]);
          requestAnimationFrame(() => rowsHost.current?.querySelector<HTMLSelectElement>(`[data-spend-row="${id}"] select`)?.focus());
        }}>Добавить покупку</button>
      </div>
      <button className="confirm" id="calculatePlan" type="submit" disabled={busy}>Сравнить варианты</button>
    </form>
    <div id="planResult" aria-live="polite">{busy ? 'Сравниваем предложения банков…' : result && <>
      <h3 ref={resultHeading} tabIndex={-1}>Прогноз · {monthText(result.body.month)}</h3>
      <p className="cb-note">Источник: {result.body.spending ? `Ручной ввод · покупок: ${result.body.spending.length}` : `История покупок · ${monthText(result.body.spendingMonth)}`}</p>
      {!noTerms(result.data) && !noSpending(result.data) && <dl>
        {([['Сейчас', result.data.baseKopecks], ['По плану', result.data.projectedKopecks], ['Разница', result.data.gainKopecks]] as const).map(([label, value]) => <Fragment key={label}><dt>{label}</dt><dd data-kopecks={value}>{money(value)}</dd></Fragment>)}
      </dl>}
      {result.data.warnings.some((warning) => warning.includes('Перебор ограничен')) && <strong>Приблизительный план</strong>}
      {!result.data.choices.length && !noTerms(result.data) && !noSpending(result.data) && <p>Дополнительных категорий с известным приростом нет.</p>}
      {result.data.choices.map((choice) => <article key={choice.cardId}>
        <h3>{meta.banks.find((bank) => bank.id === choice.bankId)?.name ?? choice.bankId}</h3><p>Для плана: {choice.labels.length} мест.</p>
        <ul>{choice.labels.map((label, index) => <li key={`${label}-${index}`}>{label}</li>)}</ul><p className="cb-note">Сначала подключите эти категории в приложении банка.</p>
      </article>)}
      {result.data.warnings.map((warning, index) => <p className="cb-warning" key={`${index}-${warning}`}>{warning}</p>)}
      {noSpending(result.data) && <button type="button" onClick={() => {
        clear(); setSource('manual'); if (!rows.length) setRows([blank(nextRow.current++)]);
        requestAnimationFrame(() => rowsHost.current?.querySelector('input')?.focus());
      }}>Ввести расходы</button>}
    </>}</div>
    {error && <p id="planError" className="auth-error" role="alert">{error}</p>}
  </div></dialog>;
}

function CashbackOverview({ meta }: { meta: Meta }) {
  const [month, setMonth] = useState(monthAt);
  const [open, setOpen] = useState(false);
  const [forecast, setForecast] = useState<number | null>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const cache = useRef<PlanCache | null>(null);
  useEffect(() => {
    const invalidate = () => { cache.current = null; setForecast(null); };
    document.addEventListener('purchase-updated', invalidate);
    document.addEventListener('wallet-updated', invalidate);
    return () => {
      document.removeEventListener('purchase-updated', invalidate);
      document.removeEventListener('wallet-updated', invalidate);
    };
  }, []);
  return <div id="cashbackOverview">
    <label className="history-month-label"><span className="history-month-text">Месяц сводки</span><input id="cashbackMonth" type="month" value={month} onChange={(event) => setMonth(event.target.value || monthAt())} /></label>
    <MonthCashback month={month} />
    <section className="cashback-planning" aria-labelledby="cashbackPlanTitle">
      <h2 id="cashbackPlanTitle">План кэшбэка</h2>
      <button id="openPlan" ref={trigger} type="button" className="buy-primary" onClick={() => { setForecast(null); setOpen(true); }}>Подобрать категории на месяц</button>
      <span id="planForecast" hidden={forecast === null}>{forecast === null ? '' : `По плану ${money(forecast)}`}</span>
      <PurchasePlanner categories={meta.categories} />
    </section>
    {open && <CategoryPlanner meta={meta} cache={cache} onForecast={setForecast} onClose={() => {
      setOpen(false); setForecast(null); requestAnimationFrame(() => trigger.current?.focus());
    }} />}
  </div>;
}

export default function Cashback({ view }: { view: CashbackView }) {
  const { meta, error, reload } = useMeta();
  if (view === 'account') return <ProfileStats categories={meta.categories} />;
  return <section className="panel" id="cashbackPanel" aria-labelledby="cashbackTitle">
    <h1 id="cashbackTitle" className="screen-title" tabIndex={-1}>Кэшбэк</h1>
    <nav className="cashback-switch" aria-label="Разделы кэшбэка">
      <button type="button" data-route="cashback" aria-controls={view === 'cashback' ? 'cashbackOverview' : undefined} aria-current={view === 'cashback' ? 'page' : undefined} onClick={() => { location.hash = 'cashback'; }}>Сводка и план</button>
      <button type="button" id="showStatsBtn" data-route="history" aria-controls={view === 'history' ? 'historyPanel' : undefined} aria-current={view === 'history' ? 'page' : undefined} onClick={() => { location.hash = 'history'; }}>История покупок</button>
    </nav>
    {error && <DataError message={error} onRetry={reload} />}
    {view === 'cashback' ? <CashbackOverview meta={meta} /> : <History categories={meta.categories} />}
  </section>;
}
