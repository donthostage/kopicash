import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { api } from './api';
import './cashback-editor.css';

type Card = { cardId: string; bankId?: string | null; name?: string; cardName?: string };
type Props = { card: Card | null; onClose: () => void; onSaved: () => void };
type Bank = { id: string; name: string };
type Meta = { banks: Bank[]; categories: Record<string, string> };
type Target = { bankId: string; cardId?: string };
type RecognizedRule = {
  label?: string; categoryId?: string; rateBps?: number | null; limitKopecks?: number | null;
  minAmountKopecks?: number | null; validFrom?: string | null; validThrough?: string | null;
  selected?: boolean | null; uncertain?: boolean;
};
type Draft = {
  id: number; label: string; categoryId: string; selected: boolean; uncertain: boolean;
  rate: string; limit: string; minimum: string; validFrom: string; validThrough: string;
};
const MAX_ROWS = 128;
const MAX_AMOUNT = 10 ** 12;
const toDisplay = (value?: number | null) => value == null ? '' : String(value / 100);
const currentMonth = () => new Date().toISOString().slice(0, 7);
const validMonth = (month: string) => /^(?!0000)\d{4}-(0[1-9]|1[0-2])$/.test(month) && month < '9999-12';
const monthName = (month: string) => validMonth(month) ? new Intl.DateTimeFormat('ru-RU', {
  month: 'long', year: 'numeric', timeZone: 'UTC',
}).format(new Date(`${month}-01T12:00:00Z`)) : 'Выберите месяц';
const cardName = (card: Card) => card.name || card.cardName || card.cardId;
const fixedBank = (card: Card, banks: Bank[]) => card.bankId && banks.some(bank => bank.id === card.bankId)
  ? card.bankId : banks.find(bank => !card.bankId && compareName(bank.name) === compareName(cardName(card)))?.id;
const compareName = (name: string) => name.toLowerCase().replace(/[^a-zа-яё0-9]/gi, '');
const errorText = (error: unknown) => error instanceof Error && error.name === 'TimeoutError'
  ? 'Сервер не ответил вовремя. Повторите запрос.'
  : error instanceof Error && error.message ? error.message : 'Не удалось выполнить запрос. Повторите.';

function hundredths(raw: string, field: string, max: number): number {
  const value = raw.trim();
  if (!/^\d+(?:[.,]\d{1,2})?$/.test(value)) throw new Error(`Проверьте поле «${field}».`);
  const [whole, part = ''] = value.split(/[.,]/);
  const result = Number(whole) * 100 + Number(part.padEnd(2, '0'));
  if (!Number.isSafeInteger(result) || result > max) {
    throw new Error(field === 'Ставка' ? 'Ставка не может превышать 100 %.' : `Слишком большое значение: ${field}.`);
  }
  return result;
}

function validateRules(rows: Draft[], month: string) {
  if (!validMonth(month)) throw new Error('Укажите месяц действия.');
  const selected = rows.filter(row => row.selected);
  if (!selected.length) throw new Error('Отметьте хотя бы одну проверенную строку.');
  if (selected.length > MAX_ROWS) throw new Error('Слишком много категорий для одной карты.');
  const seen = new Set<string>();
  return selected.map(row => {
    const label = row.label.trim();
    const categoryId = row.categoryId.trim() || label;
    if (!label) throw new Error('Укажите название категории, как в банке.');
    if (label.length > 80 || categoryId.length > 80) throw new Error('Используйте не больше 80 символов в названии категории.');
    if (seen.has(label)) throw new Error(`Название «${label}» уже используется.`);
    seen.add(label);
    const { validFrom, validThrough } = row;
    for (const date of [validFrom, validThrough]) {
      if (date && !date.startsWith(`${month}-`)) throw new Error('Укажите даты в пределах месяца действия категории.');
    }
    if (validFrom && validThrough && validFrom > validThrough) throw new Error('Дата окончания должна быть не раньше даты начала.');
    return {
      label, categoryId, selected: true, uncertain: false,
      rateBps: hundredths(row.rate, 'Ставка', 10000),
      limitKopecks: row.limit.trim() ? hundredths(row.limit, 'Лимит', MAX_AMOUNT) : null,
      minAmountKopecks: row.minimum.trim() ? hundredths(row.minimum, 'Минимальная покупка', MAX_AMOUNT) : 1,
      validFrom: validFrom || null, validThrough: validThrough || null,
    };
  });
}

async function readShot(file: File): Promise<string> {
  if (file.size > 4_000_000) throw new Error('Скриншот больше 4 МБ');
  const bytes = new Uint8Array(await file.arrayBuffer());
  const mime = bytes.length > 3 && bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff ? 'image/jpeg'
    : bytes.length > 8 && bytes[0] === 0x89 && bytes[1] === 0x50 && bytes[2] === 0x4e && bytes[3] === 0x47 ? 'image/png'
    : bytes.length > 12 && String.fromCharCode(...bytes.subarray(0, 4)) === 'RIFF'
      && String.fromCharCode(...bytes.subarray(8, 12)) === 'WEBP' ? 'image/webp' : '';
  if (!mime) throw new Error('Нужен снимок JPG, PNG или WebP');
  const parts: string[] = [];
  for (let offset = 0; offset < bytes.length; offset += 0x8000) {
    parts.push(String.fromCharCode(...bytes.subarray(offset, offset + 0x8000)));
  }
  return `data:${mime};base64,${btoa(parts.join(''))}`;
}

function post<T>(action: 'screenshot' | 'confirm', body: unknown, controller: AbortController) {
  return api<T>(`/api/me/cashback-${action}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    signal: AbortSignal.any([controller.signal, AbortSignal.timeout(45_000)]),
  });
}

export default function CashbackEditor(props: Props) {
  // A different target card must never inherit an in-progress draft.
  return <Editor key={props.card?.cardId ?? ''} {...props} />;
}

function Editor({ card, onClose, onSaved }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const initialName = useRef<HTMLInputElement>(null);
  const stayButton = useRef<HTMLButtonElement>(null);
  const work = useRef<AbortController | null>(null);
  const fileVersion = useRef(0);
  const nextRow = useRef(0);
  const replay = useRef<{ signature: string; key: string } | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [source, setSource] = useState<{ meta: Meta; cards: Card[] } | null>(null);
  const [loadError, setLoadError] = useState('');
  const [pickedBank, setPickedBank] = useState('');
  const [pickedCard, setPickedCard] = useState('');
  const [target, setTarget] = useState<Target | null>(null);
  const [image, setImage] = useState('');
  const [reading, setReading] = useState(false);
  const [review, setReview] = useState<'manual' | 'shot' | null>(null);
  const [rows, setRows] = useState<Draft[]>([]);
  const [month, setMonth] = useState(currentMonth);
  const [busy, setBusy] = useState<'shot' | 'save' | null>(null);
  const [error, setError] = useState('');
  const [dirty, setDirty] = useState(false);
  const [discard, setDiscard] = useState(false);
  const [retryShot, setRetryShot] = useState(false);

  useEffect(() => {
    const element = dialog.current;
    const trigger = document.activeElement;
    element?.showModal();
    return () => {
      element?.close();
      work.current?.abort();
      fileVersion.current += 1;
      if (trigger instanceof HTMLElement && trigger.isConnected) trigger.focus();
    };
  }, []);

  const selectedCardId = card?.cardId;
  useEffect(() => {
    const controller = new AbortController();
    const options = { signal: AbortSignal.any([controller.signal, AbortSignal.timeout(15_000)]) };
    void Promise.all([
      api<Meta>('/api/meta', options),
      selectedCardId ? Promise.resolve([]) : api<Card[]>('/api/me/manual-cards', options),
    ]).then(([meta, cards]) => {
      if (!controller.signal.aborted) setSource({ meta, cards });
    }).catch((reason: unknown) => {
      if (!controller.signal.aborted) setLoadError(errorText(reason));
    });
    return () => controller.abort();
  }, [attempt, selectedCardId]);

  const knownBank = card && source ? fixedBank(card, source.meta.banks) : undefined;
  const bankId = knownBank || pickedBank || (!card ? source?.meta.banks[0]?.id : '') || '';
  const bank = source?.meta.banks.find(item => item.id === bankId);
  const matches = card ? [card] : (source?.cards.filter(item => item.bankId === bankId
    || (!item.bankId && bank?.name === cardName(item))) ?? []);
  const matchingCard = matches.find(item => item.cardId === pickedCard) ?? (matches.length === 1 ? matches[0] : undefined);
  const currentTarget = target ?? (knownBank && card ? { bankId: knownBank, cardId: card.cardId } : null);
  const selected = rows.filter(row => row.selected);
  const needs = [!month && 'укажите месяц', !selected.length && 'отметьте категорию',
    selected.some(row => !row.rate.trim()) && 'укажите ставку'].filter(Boolean);
  const chosenCard = card ?? source?.cards.find(item => item.cardId === currentTarget?.cardId);
  const targetBank = source?.meta.banks.find(item => item.id === currentTarget?.bankId)?.name;
  const targetLabel = chosenCard ? cardName(chosenCard) : targetBank;
  const context = targetBank && targetLabel && targetLabel !== targetBank && !targetLabel.startsWith(`${targetBank} `)
    ? `${targetBank} · ${targetLabel}` : targetLabel;

  useEffect(() => {
    if (discard) stayButton.current?.focus();
    else if (review === 'manual') initialName.current?.focus();
    else if (review || currentTarget) heading.current?.focus();
  }, [discard, review, currentTarget?.cardId, currentTarget?.bankId]);

  function close() {
    if (discard) setDiscard(false);
    else if (work.current) return;
    else if (dirty) setDiscard(true);
    else onClose();
  }

  function draft(rule: RecognizedRule, manual: boolean): Draft {
    return {
      id: nextRow.current++, label: rule.label ?? '', categoryId: rule.categoryId ?? '',
      rate: toDisplay(rule.rateBps), limit: toDisplay(rule.limitKopecks), minimum: toDisplay(rule.minAmountKopecks),
      validFrom: rule.validFrom ?? '', validThrough: rule.validThrough ?? '',
      selected: manual || (rule.rateBps != null && rule.selected !== false),
      uncertain: !!rule.uncertain || (!manual && rule.rateBps == null),
    };
  }

  function updateRow(id: number, patch: Partial<Draft>) {
    setRows(previous => previous.map(row => row.id === id ? { ...row, ...patch } : row));
    setDirty(true);
    setError('');
  }

  function startReview(kind: 'manual' | 'shot', rules: RecognizedRule[], suggestedMonth?: string | null) {
    fileVersion.current += 1;
    setReading(false);
    setImage('');
    setError('');
    setReview(kind);
    setRows(rules.map(rule => draft(rule, kind === 'manual')));
    setMonth(suggestedMonth && validMonth(suggestedMonth) ? suggestedMonth : currentMonth());
    if (kind === 'shot') setDirty(true);
  }

  async function selectFile(file?: File) {
    const version = ++fileVersion.current;
    setImage('');
    setError('');
    setRetryShot(false);
    setReading(!!file);
    if (!file) return;
    setDirty(true);
    try {
      const data = await readShot(file);
      if (version === fileVersion.current) setImage(data);
    } catch (reason) {
      if (version === fileVersion.current) setError(errorText(reason));
    } finally {
      if (version === fileVersion.current) setReading(false);
    }
  }

  async function recognize(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (work.current || !currentTarget || !image) return;
    const controller = new AbortController();
    work.current = controller;
    setBusy('shot');
    setError('');
    try {
      const result = await post<{ rules: RecognizedRule[]; month?: string | null }>('screenshot', { ...currentTarget, image }, controller);
      if (controller.signal.aborted) return;
      if (!Array.isArray(result?.rules) || !result.rules.length) throw new Error('На снимке не найдено категорий. Попробуйте другой снимок или введите условия вручную.');
      startReview('shot', result.rules, result.month);
    } catch (reason) {
      if (!controller.signal.aborted) {
        setError(errorText(reason));
        setRetryShot(true);
      }
    } finally {
      if (!controller.signal.aborted) setBusy(null);
      work.current = null;
    }
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (work.current || !currentTarget) return;
    const controller = new AbortController();
    try {
      const body = { ...currentTarget, month, mode: 'active', slots: null, rules: validateRules(rows, month) };
      const signature = JSON.stringify(body);
      if (replay.current?.signature !== signature) {
        const bytes = crypto.getRandomValues(new Uint8Array(16));
        replay.current = { signature, key: Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('') };
      }
      work.current = controller;
      setBusy('save');
      setError('');
      await post<unknown>('confirm', { ...body, requestId: replay.current.key }, controller);
    } catch (reason) {
      if (!controller.signal.aborted) setError(errorText(reason));
      return;
    } finally {
      if (!controller.signal.aborted) setBusy(null);
      work.current = null;
    }
    if (!controller.signal.aborted) {
      onClose();
      onSaved();
    }
  }

  return <dialog ref={dialog} id="catalogDialog" className="cashback-editor" aria-labelledby="dialogTitle" aria-busy={!!busy}
    onCancel={event => { event.preventDefault(); close(); }}
    onClick={event => { if (event.target === event.currentTarget) close(); }}>
    <div className="cashback-editor__body">
      <header className="cashback-editor__head">
        <h2 id="dialogTitle" ref={heading} tabIndex={-1}>{discard ? 'Выйти без сохранения?' : review === 'shot' ? 'Всё верно?' : review ? 'Ввести кэшбэк вручную' : 'Условия кэшбэка'}</h2>
        {!discard && <button type="button" id="closeCatalog" className="cashback-editor__close" aria-label="Закрыть" onClick={close} disabled={!!busy}>×</button>}
      </header>
      {discard ? <div id="discardDialog" className="cashback-editor__stack">
        <p>Черновик условий будет удалён.</p>
        <button type="button" id="discardStay" ref={stayButton} onClick={() => setDiscard(false)}>Продолжить проверку</button>
        <button type="button" id="discardLeave" className="cashback-editor__primary" onClick={onClose}>Выйти без сохранения</button>
      </div> : <div className="cashback-editor__stack">
        {!source ? (loadError ? <>
          <p role="alert" className="cashback-editor__error">{loadError}</p>
          <button type="button" onClick={() => { setLoadError(''); setAttempt(value => value + 1); }}>Повторить загрузку</button>
        </> : <p role="status">Загружаем банки…</p>) : !currentTarget ?
          <form id="decisionStep" className="cashback-editor__stack" onSubmit={event => {
            event.preventDefault();
            if (!bankId || (matches.length > 1 && !matchingCard)) return;
            setTarget({ bankId, cardId: matchingCard?.cardId });
          }}>
            <label>Банк<select id="bankId" value={bankId} onChange={event => { setPickedBank(event.currentTarget.value); setPickedCard(''); }}>
              <option value="" disabled>Выберите банк</option>
              {source.meta.banks.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select></label>
            {matches.length > 1 ? <label>Карта<select id="cashbackCard" value={pickedCard} onChange={event => setPickedCard(event.currentTarget.value)}>
              <option value="" disabled>Выберите карту</option>
              {matches.map((item, index) => <option key={item.cardId} value={item.cardId}>{cardName(item)} · карта {index + 1}</option>)}
            </select></label> : bank && <p className="cashback-editor__note">{matchingCard ? `Карта: ${cardName(matchingCard)}` : 'Карта будет создана при сохранении категорий.'}</p>}
            <p>Вы уже выбрали категории в банке?</p>
            <button id="chooseActive" className="cashback-editor__primary" type="submit" disabled={!bankId || (matches.length > 1 && !matchingCard)}>Да — добавить подключённые</button>
          </form> : !review ?
          <form id="screenshotForm" className="cashback-editor__stack" onSubmit={recognize}>
            <p>Прикрепите категории кэшбэка</p>
            <p id="entryContext" className="cashback-editor__note">{context} · {monthName(currentMonth())}</p>
            <label className="cashback-editor__upload">
              <input id="cashbackShot" type="file" accept="image/jpeg,image/png,image/webp" aria-label="Снимок из галереи" disabled={!!busy}
                onChange={event => { void selectFile(event.currentTarget.files?.[0]); }} />
              {image ? <img src={image} alt="Предпросмотр снимка" /> : <span>{reading ? 'Читаем снимок…' : 'Снимок из банка · JPG, PNG или WebP'}</span>}
            </label>
            <p className="cashback-editor__note">Снимок целиком отправится на распознавание. Обрежьте имя, баланс и другие личные данные перед загрузкой.</p>
            {image && <button id="confirmCard" type="submit" className="cashback-editor__primary" disabled={!!busy}>{busy === 'shot' ? 'Распознаём…' : retryShot ? 'Повторить распознавание' : 'Отправить на распознавание'}</button>}
            <button id="enterCashbackManually" type="button" disabled={!!busy} onClick={() => startReview('manual', [{}])}>Ввести вручную</button>
          </form> :
          <form id="reviewForm" className="cashback-editor__stack" noValidate onSubmit={save}>
            <p id="reviewContext" className="cashback-editor__note">{context}</p>
            <label>Месяц действия <span id="reviewMonthText" className="cashback-editor__note">{monthName(month)}</span>
              <input id="reviewMonth" type="month" value={month} disabled={!!busy} onChange={event => { setMonth(event.currentTarget.value); setDirty(true); setError(''); }} />
            </label>
            {review === 'manual' && <p className="cashback-editor__note">Укажите ставку. Лимит и даты в пределах выбранного месяца можно оставить пустыми.</p>}
            <datalist id="cbCategoryIds">{Object.entries(source.meta.categories).map(([id, name]) => <option key={id} value={id}>{name}</option>)}</datalist>
            <div id="reviewRows" className="cashback-editor__stack">{rows.map((row, index) => {
              const title = row.label.trim() || source.meta.categories[row.categoryId] || 'Новая категория';
              const fields = <div className="cashback-editor__fields">
                <label className="cashback-editor__wide">Название в банке<input ref={index === 0 && review === 'manual' ? initialName : undefined} data-key="label" maxLength={80} value={row.label} onChange={event => updateRow(row.id, { label: event.currentTarget.value })} /></label>
                <label className="cashback-editor__wide">Категория для расчёта<input data-key="categoryId" maxLength={80} list="cbCategoryIds" value={row.categoryId} onChange={event => updateRow(row.id, { categoryId: event.currentTarget.value })} /></label>
                <label>Ставка, %<input data-key="rateBps" inputMode="decimal" value={row.rate} onChange={event => updateRow(row.id, { rate: event.currentTarget.value })} /></label>
                <label>Лимит кэшбэка, ₽<input data-key="limitKopecks" inputMode="decimal" value={row.limit} onChange={event => updateRow(row.id, { limit: event.currentTarget.value })} /></label>
                <label className="cashback-editor__wide">Минимальная сумма покупки, ₽<input data-key="minAmountKopecks" inputMode="decimal" value={row.minimum} onChange={event => updateRow(row.id, { minimum: event.currentTarget.value })} /></label>
                <label>Действует с<input data-key="validFrom" type="date" value={row.validFrom} onChange={event => updateRow(row.id, { validFrom: event.currentTarget.value })} /></label>
                <label>Действует по включительно<input data-key="validThrough" type="date" value={row.validThrough} onChange={event => updateRow(row.id, { validThrough: event.currentTarget.value })} /></label>
              </div>;
              return <fieldset key={row.id} className="review-row" disabled={!!busy}>
                <legend>{title}{row.rate.trim() ? ` · ${row.rate.replace('.', ',')} %` : ' · ставка не указана'}</legend>
                <label className="cashback-editor__check"><input type="checkbox" data-key="include" checked={row.selected} onChange={event => updateRow(row.id, { selected: event.currentTarget.checked })} />Подключена</label>
                {row.uncertain && <p className="cashback-editor__warning">Проверьте распознанные поля.</p>}
                {review === 'shot' ? <details><summary>Изменить</summary>{fields}</details> : fields}
                {review === 'manual' && <button type="button" className="cashback-editor__remove" onClick={() => { setRows(previous => previous.filter(item => item.id !== row.id)); setDirty(true); setError(''); }}>Убрать строку</button>}
              </fieldset>;
            })}</div>
            {review === 'manual' && <button id="addRule" type="button" disabled={!!busy || rows.length >= MAX_ROWS} onClick={() => { const row = draft({}, true); setRows(previous => [...previous, row]); setDirty(true); setError(''); }}>Добавить строку</button>}
            <p id="reviewCount" className="cashback-editor__note" aria-live="polite">Выбрано: {selected.length}</p>
            {needs.length > 0 && <p id="reviewNeed" className="cashback-editor__note" role="status">Нужно: {needs.join(', ')}.</p>}
            <button id="saveReview" className="cashback-editor__primary" type="submit" disabled={!!busy || needs.length > 0}>{busy === 'save' ? 'Сохраняем…' : review === 'shot' ? 'Сохранить' : 'Сохранить категории'}</button>
          </form>}
        {error && <p id="shotError" role="alert" className="cashback-editor__error">{error}</p>}
      </div>}
    </div>
  </dialog>;
}
