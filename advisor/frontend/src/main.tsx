import { useEffect, useState, type FormEvent } from 'react';
import { createRoot } from 'react-dom/client';
import { api, json } from './api';
import Wallet from './Wallet';
import Checkout from './Checkout';
import Cashback from './Cashback';
import CashbackEditor from './CashbackEditor';
import './shell.css';

const routes = ['home', 'cards', 'buy', 'cashback', 'history', 'account'] as const;
type Route = typeof routes[number];
type EditorCard = { cardId: string; bankId?: string | null; name?: string; cardName?: string };
function routeFromHash(): Route {
  return routes.find(route => route === location.hash.slice(1)) ?? 'home';
}
const message = (error: unknown) => error instanceof Error ? error.message : 'Не удалось выполнить запрос.';

function App() {
  const [route, setRoute] = useState(routeFromHash);
  const [login, setLogin] = useState<string | null | undefined>();
  const [mode, setMode] = useState<'welcome' | 'register' | 'login'>('welcome');
  const [retry, setRetry] = useState(0);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [dark, setDark] = useState(() => localStorage.getItem('advisor-theme') === 'dark');
  const [editor, setEditor] = useState<{ card: EditorCard | null } | null>(null);
  const demo = new URLSearchParams(location.search).get('demo') === 'cards';

  useEffect(() => {
    if (demo) return;
    const controller = new AbortController();
    api<{ authenticated: boolean; login: string | null }>('/api/auth/me', { signal: controller.signal })
      .then(session => setLogin(session.authenticated ? session.login : null))
      .catch(error => { if (!controller.signal.aborted) setError(message(error)); });
    return () => controller.abort();
  }, [demo, retry]);
  useEffect(() => {
    const change = () => { setRoute(routeFromHash()); setEditor(null); };
    window.addEventListener('hashchange', change);
    return () => window.removeEventListener('hashchange', change);
  }, []);
  useEffect(() => {
    document.documentElement.dataset.theme = dark ? 'dark' : 'light';
    localStorage.setItem('advisor-theme', dark ? 'dark' : 'light');
  }, [dark]);
  useEffect(() => { window.scrollTo(0, 0); }, [route]);

  function navigate(target: Route) {
    if (route === target) return;
    location.hash = target;
    setRoute(target);
    setEditor(null);
  }
  async function authenticate(path: 'register' | 'login' | 'guest', credentials?: FormData) {
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      const result = await api<{ login: string }>(`/api/auth/${path}`, credentials
        ? json('POST', { login: credentials.get('login'), password: credentials.get('password') }) : { method: 'POST' });
      setLogin(result.login);
      navigate('home');
    } catch (error) { setError(message(error)); }
    finally { setBusy(false); }
  }
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void authenticate(mode === 'login' ? 'login' : 'register', new FormData(event.currentTarget));
  }
  async function logout() {
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      await api('/api/auth/logout', { method: 'POST' });
      setLogin(null);
      setMode('welcome');
      navigate('home');
    } catch (error) { setError(message(error)); }
    finally { setBusy(false); }
  }

  if (demo) return <main className="page" id="appScreen"><section className="content" id="content"><Wallet /></section></main>;
  if (login === undefined) return <main className="session-gate" aria-live="polite">
    <p role="status">{error || 'Проверяем вход…'}</p>
    {error && <button onClick={() => { setError(''); setRetry(value => value + 1); }}>Повторить</button>}
  </main>;
  if (login === null && mode === 'welcome') return <main className="react-welcome">
    <span className="brand"><img src="/static/kopicash-logo.png" alt="" width="34" height="34" />КопиКэш</span>
    <h1>Больше кэшбэка<br />за каждую покупку</h1>
    <p>Узнайте, какой картой выгоднее заплатить.</p>
    <img className="welcome-art" src="/pocket.webp" alt="" />
    <button className="buy-primary" onClick={() => setMode('register')}>Начать</button>
    <button className="buy-secondary" onClick={() => setMode('login')}>Войти</button>
  </main>;
  if (login === null) return <main className="auth-screen" id="authScreen"><div className="auth-card">
    <span className="brand"><img src="/static/kopicash-logo.png" alt="" width="34" height="34" />КопиКэш</span>
    <h1 id="authTitle">{mode === 'login' ? 'Войдите в кошелёк' : 'Создайте кошелёк'}</h1>
    <form className="auth-form" id="authForm" onSubmit={submit}>
      <label htmlFor="authLogin">Логин<input id="authLogin" name="login" autoComplete="username" required minLength={3} maxLength={32} /></label>
      <label htmlFor="authPassword">Пароль</label>
      <div className="password-field"><input id="authPassword" name="password" type={showPassword ? 'text' : 'password'}
        autoComplete={mode === 'login' ? 'current-password' : 'new-password'} required minLength={4} maxLength={72} />
        <button type="button" className="password-toggle" aria-label={showPassword ? 'Скрыть пароль' : 'Показать пароль'}
          aria-pressed={showPassword} onClick={() => setShowPassword(value => !value)}>◉</button></div>
      <button id="authSubmit" disabled={busy}>{mode === 'login' ? 'Войти' : 'Создать кошелёк'}</button>
    </form>
    {error && <p className="auth-error" role="alert">{error}</p>}
    <button className="auth-switch" onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError(''); }}>
      {mode === 'login' ? 'Нет кошелька? Создать' : 'Уже есть кошелёк? Войти'}
    </button>
    <button id="authGuest" className="auth-guest" disabled={busy} onClick={() => void authenticate('guest')}>Войти как гость</button>
  </div></main>;

  return <main className="page" id="appScreen">
    <header className="topbar">
      <button id="brandHome" type="button" className="brand" onClick={() => navigate('home')} aria-label="КопиКэш, на главную">
        <img className="brand-logo" src="/static/kopicash-logo.png" width="34" height="34" alt="" /><span>КопиКэш</span>
      </button>
      <div className="topbar-actions">
        <button className="icon-btn" id="themeToggle" type="button" aria-label="Тёмная тема" aria-pressed={dark} onClick={() => setDark(value => !value)}>{dark ? '☀' : '☾'}</button>
        <button className="icon-btn" id="settingsOpen" type="button" aria-label="Профиль" onClick={() => navigate('account')}><svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><circle cx="12" cy="8" r="3.5"/><path d="M5 21v-2a4 4 0 0 1 4-4h6a4 4 0 0 1 4 4v2"/></svg></button>
      </div>
    </header>
    {route === 'home' ? <section className="hero home-hero" id="hero" aria-label="Главная">
      <div className="ask-block"><h1 id="homeTitle">Какой картой выгоднее заплатить?</h1>
        <button type="button" id="openBuy" onClick={() => navigate('buy')}>Сравнить карты</button></div>
      <section className="home-wallet"><h2>Карты в кошельке</h2>
        <button type="button" className="buy-secondary" onClick={() => navigate('cards')}>Открыть кошелёк</button></section>
    </section> : <section className="content" id="content">
      {route === 'cards' && <Wallet onEdit={card => setEditor({ card })} />}
      {route === 'buy' && <Checkout />}
      {(route === 'cashback' || route === 'history' || route === 'account') && <>
        {route === 'account' && <div className="account-head"><span>{login}</span><button type="button" disabled={busy} onClick={() => void logout()}>Выйти</button></div>}
        <Cashback view={route} />
      </>}
      {error && <p role="alert">{error}</p>}
    </section>}
    <nav className="wallet-nav" aria-label="Основная навигация">
      {([['home', 'Главная', 'openHome'], ['cards', 'Мои карты', 'openCards'], ['cashback', 'Кэшбэк', 'openCashback']] as const).map(([key, label, id]) =>
        <button id={id} key={key} type="button" data-route={key} aria-current={route === key || (key === 'cashback' && route === 'history') ? 'page' : undefined} onClick={() => navigate(key)}>{label}</button>)}
    </nav>
    {editor && <CashbackEditor card={editor.card} onClose={() => setEditor(null)} onSaved={() => { setEditor(null); document.dispatchEvent(new Event('wallet-updated')); }} />}
  </main>;
}

createRoot(document.getElementById('root')!).render(<App />);
