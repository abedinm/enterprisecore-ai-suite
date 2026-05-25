/*!
 * EnterpriseCore AI embeddable chat widget
 * Single-file vanilla JS, no deps, ~17KB.
 * Ported from LinguaBot widget (Shadow DOM, RTL for Urdu, EN/BN/HI/UR auto-detect, mobile responsive).
 *
 * Embed:
 *   <script
 *     src="https://your-domain/widget.js"
 *     data-bot-id="xxxxxxx"
 *     data-api-base="https://your-domain"   (optional; falls back to script's origin)
 *     data-accent="#6366F1"                  (optional; overrides bot's saved color)
 *     data-welcome="..."                     (optional; overrides bot's welcome message)
 *   ></script>
 */
(function () {
  'use strict';

  // ---------- Config from the <script> tag ----------
  const scriptEl = document.currentScript || (function () {
    const list = document.getElementsByTagName('script');
    return list[list.length - 1];
  })();
  if (!scriptEl) return;

  const BOT_ID = scriptEl.getAttribute('data-bot-id');
  if (!BOT_ID) {
    console.warn('[EnterpriseCore] data-bot-id is required.');
    return;
  }

  // API base: explicit override -> same origin as the script src -> current page origin
  let API_BASE = scriptEl.getAttribute('data-api-base') || '';
  if (!API_BASE) {
    try {
      API_BASE = new URL(scriptEl.src).origin;
    } catch (_) {
      API_BASE = window.location.origin;
    }
  }
  API_BASE = API_BASE.replace(/\/+$/, '');

  const ATTR_ACCENT = scriptEl.getAttribute('data-accent');
  const ATTR_WELCOME = scriptEl.getAttribute('data-welcome');

  // ---------- Localized UI strings ----------
  const I18N = {
    en: {
      placeholder: 'Type your message…',
      send: 'Send',
      retry: 'Retry',
      error: 'Something went wrong. Try again?',
      typing: 'Typing…',
      header: 'Chat',
      poweredBy: 'Powered by EnterpriseCore AI',
    },
    bn: {
      placeholder: 'আপনার বার্তা লিখুন…',
      send: 'পাঠান',
      retry: 'আবার চেষ্টা করুন',
      error: 'কিছু একটা ভুল হয়েছে। আবার চেষ্টা করবেন?',
      typing: 'লিখছে…',
      header: 'চ্যাট',
      poweredBy: 'EnterpriseCore AI দ্বারা চালিত',
    },
    hi: {
      placeholder: 'अपना संदेश लिखें…',
      send: 'भेजें',
      retry: 'पुनः प्रयास',
      error: 'कुछ गड़बड़ हो गई। फिर से प्रयास करें?',
      typing: 'टाइप कर रहा है…',
      header: 'चैट',
      poweredBy: 'EnterpriseCore AI द्वारा संचालित',
    },
    ur: {
      placeholder: 'اپنا پیغام لکھیں…',
      send: 'بھیجیں',
      retry: 'دوبارہ کوشش کریں',
      error: 'کچھ غلط ہو گیا۔ دوبارہ کوشش کریں؟',
      typing: 'لکھ رہا ہے…',
      header: 'چیٹ',
      poweredBy: 'EnterpriseCore AI کے ذریعے',
    },
  };

  const LANG_LABEL = { en: 'English', bn: 'বাংলা', hi: 'हिन्दी', ur: 'اردو' };
  const RTL_LANGS = new Set(['ur']);
  const STORAGE_PREFIX = 'enterprisecore:webchat:';

  // ---------- State ----------
  const state = {
    open: false,
    sending: false,
    sessionId: localStorage.getItem(STORAGE_PREFIX + BOT_ID + ':session') || null,
    language: pickInitialLanguage(),
    accent: ATTR_ACCENT || '#6366F1',
    welcome: ATTR_WELCOME || null,
    name: 'Chat',
    supported: ['en', 'bn', 'hi', 'ur'],
    messages: [],
  };

  function pickInitialLanguage() {
    const saved = localStorage.getItem(STORAGE_PREFIX + BOT_ID + ':lang');
    if (saved && ['en', 'bn', 'hi', 'ur'].includes(saved)) return saved;
    const browser = (navigator.language || 'en').toLowerCase();
    if (browser.startsWith('bn')) return 'bn';
    if (browser.startsWith('hi')) return 'hi';
    if (browser.startsWith('ur')) return 'ur';
    return 'en';
  }

  function saveSession(id) {
    state.sessionId = id;
    try { localStorage.setItem(STORAGE_PREFIX + BOT_ID + ':session', id); } catch (_) {}
  }

  function saveLanguage(l) {
    state.language = l;
    try { localStorage.setItem(STORAGE_PREFIX + BOT_ID + ':lang', l); } catch (_) {}
  }

  // ---------- Shadow-DOM host + styles ----------
  const host = document.createElement('div');
  host.setAttribute('data-enterprisecore-webchat', '');
  host.style.cssText = 'all:initial;position:fixed;z-index:2147483600;';
  document.body.appendChild(host);
  const root = host.attachShadow({ mode: 'open' });

  const styleEl = document.createElement('style');
  styleEl.textContent = `
    :host { all: initial; }
    *, *::before, *::after { box-sizing: border-box; }
    .container {
      position: fixed;
      bottom: 20px;
      right: 20px;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Inter, 'Helvetica Neue', sans-serif;
      color: #18181B;
      line-height: 1.5;
      direction: ltr;
    }
    .container.rtl { direction: rtl; }
    .container.rtl .panel { direction: rtl; }

    .bubble {
      width: 60px; height: 60px;
      border-radius: 50%;
      background: var(--accent, #6366F1);
      color: white;
      box-shadow: 0 10px 30px rgba(0,0,0,0.18);
      display: flex; align-items: center; justify-content: center;
      cursor: pointer;
      transition: transform .15s, box-shadow .15s;
      border: none;
      outline: none;
    }
    .bubble:hover { transform: translateY(-2px); box-shadow: 0 14px 36px rgba(0,0,0,0.22); }
    .bubble svg { width: 28px; height: 28px; }

    .panel {
      position: fixed;
      bottom: 96px;
      right: 20px;
      width: 380px;
      height: 560px;
      max-height: calc(100vh - 120px);
      background: #FFFFFF;
      border-radius: 18px;
      box-shadow: 0 20px 60px rgba(0,0,0,0.20);
      display: none;
      flex-direction: column;
      overflow: hidden;
      border: 1px solid rgba(0,0,0,0.06);
    }
    .panel.open { display: flex; animation: ec-pop .18s ease-out; }
    @keyframes ec-pop {
      from { transform: translateY(8px); opacity: 0; }
      to { transform: translateY(0); opacity: 1; }
    }

    @media (max-width: 480px) {
      .panel {
        right: 0; bottom: 0; left: 0;
        width: 100vw; height: 100vh; max-height: 100vh;
        border-radius: 0;
      }
      .bubble { bottom: 16px; right: 16px; }
    }

    .header {
      background: var(--accent, #6366F1);
      color: white;
      padding: 14px 16px;
      display: flex; align-items: center; justify-content: space-between;
      gap: 8px;
    }
    .header-title { font-weight: 600; font-size: 15px; }
    .header-actions { display: flex; align-items: center; gap: 6px; }
    .lang-select {
      background: rgba(255,255,255,0.18);
      color: white;
      border: 1px solid rgba(255,255,255,0.30);
      padding: 4px 8px;
      border-radius: 8px;
      font-size: 12px;
      cursor: pointer;
      font-family: inherit;
      direction: ltr;
    }
    .lang-select option { color: #18181B; }
    .close-btn {
      background: transparent;
      border: none;
      color: white;
      cursor: pointer;
      padding: 4px;
      border-radius: 6px;
    }
    .close-btn:hover { background: rgba(255,255,255,0.15); }
    .close-btn svg { width: 18px; height: 18px; }

    .messages {
      flex: 1 1 auto;
      overflow-y: auto;
      padding: 16px;
      background: #FAFAFA;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .msg {
      max-width: 82%;
      padding: 10px 14px;
      border-radius: 14px;
      font-size: 14px;
      word-wrap: break-word;
      white-space: pre-wrap;
    }
    .msg.user {
      background: var(--accent, #6366F1);
      color: white;
      align-self: flex-end;
      border-bottom-right-radius: 4px;
    }
    .container.rtl .msg.user { align-self: flex-start; border-bottom-right-radius: 14px; border-bottom-left-radius: 4px; }
    .msg.bot {
      background: white;
      color: #18181B;
      border: 1px solid rgba(0,0,0,0.06);
      align-self: flex-start;
      border-bottom-left-radius: 4px;
    }
    .container.rtl .msg.bot { align-self: flex-end; border-bottom-left-radius: 14px; border-bottom-right-radius: 4px; }
    .msg.bot.error { background: #FEF2F2; color: #991B1B; border-color: #FECACA; }
    .typing {
      display: inline-flex; gap: 4px; align-self: flex-start;
      padding: 10px 14px; background: white; border-radius: 14px;
      border: 1px solid rgba(0,0,0,0.06); color: #71717A; font-size: 13px;
      align-items: center;
    }
    .typing .dot {
      display: inline-block; width: 6px; height: 6px; background: #A1A1AA;
      border-radius: 50%; animation: ec-blink 1.2s infinite;
    }
    .typing .dot:nth-child(2) { animation-delay: .15s; }
    .typing .dot:nth-child(3) { animation-delay: .30s; }
    @keyframes ec-blink {
      0%, 80%, 100% { opacity: .25; }
      40% { opacity: 1; }
    }

    .composer {
      border-top: 1px solid rgba(0,0,0,0.06);
      background: white;
      padding: 10px;
      display: flex;
      gap: 8px;
      align-items: flex-end;
    }
    .composer textarea {
      flex: 1;
      resize: none;
      border: 1px solid rgba(0,0,0,0.10);
      border-radius: 10px;
      padding: 10px 12px;
      font-family: inherit;
      font-size: 14px;
      max-height: 120px;
      min-height: 40px;
      outline: none;
      line-height: 1.4;
      color: #18181B;
      background: white;
    }
    .composer textarea:focus { border-color: var(--accent, #6366F1); }
    .send-btn {
      background: var(--accent, #6366F1);
      color: white;
      border: none;
      width: 40px; height: 40px;
      border-radius: 10px;
      cursor: pointer;
      display: flex; align-items: center; justify-content: center;
      transition: opacity .15s, transform .15s;
    }
    .send-btn:hover { transform: translateY(-1px); }
    .send-btn:disabled { opacity: .5; cursor: not-allowed; transform: none; }
    .send-btn svg { width: 18px; height: 18px; }

    .footer-credit {
      text-align: center;
      font-size: 11px;
      color: #A1A1AA;
      padding: 6px 0 10px;
      background: white;
    }
    .footer-credit a { color: inherit; text-decoration: none; }
  `;
  root.appendChild(styleEl);

  // ---------- DOM ----------
  const container = document.createElement('div');
  container.className = 'container';
  if (RTL_LANGS.has(state.language)) container.classList.add('rtl');

  const bubble = document.createElement('button');
  bubble.className = 'bubble';
  bubble.style.setProperty('--accent', state.accent);
  bubble.setAttribute('aria-label', 'Open chat');
  bubble.innerHTML = `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
    </svg>
  `;
  bubble.addEventListener('click', toggle);
  container.appendChild(bubble);

  const panel = document.createElement('div');
  panel.className = 'panel';
  panel.style.setProperty('--accent', state.accent);
  container.appendChild(panel);

  const header = document.createElement('div');
  header.className = 'header';
  panel.appendChild(header);

  const headerTitle = document.createElement('div');
  headerTitle.className = 'header-title';
  headerTitle.textContent = I18N[state.language].header;
  header.appendChild(headerTitle);

  const headerActions = document.createElement('div');
  headerActions.className = 'header-actions';
  header.appendChild(headerActions);

  const langSelect = document.createElement('select');
  langSelect.className = 'lang-select';
  ['en', 'bn', 'hi', 'ur'].forEach((l) => {
    const opt = document.createElement('option');
    opt.value = l;
    opt.textContent = LANG_LABEL[l];
    if (l === state.language) opt.selected = true;
    langSelect.appendChild(opt);
  });
  langSelect.addEventListener('change', () => {
    saveLanguage(langSelect.value);
    applyDirection();
    headerTitle.textContent = I18N[state.language].header;
    textarea.placeholder = I18N[state.language].placeholder;
    creditEl.textContent = I18N[state.language].poweredBy;
  });
  headerActions.appendChild(langSelect);

  const closeBtn = document.createElement('button');
  closeBtn.className = 'close-btn';
  closeBtn.setAttribute('aria-label', 'Close chat');
  closeBtn.innerHTML = `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line>
    </svg>
  `;
  closeBtn.addEventListener('click', toggle);
  headerActions.appendChild(closeBtn);

  const messagesEl = document.createElement('div');
  messagesEl.className = 'messages';
  panel.appendChild(messagesEl);

  const composer = document.createElement('div');
  composer.className = 'composer';
  panel.appendChild(composer);

  const textarea = document.createElement('textarea');
  textarea.rows = 1;
  textarea.placeholder = I18N[state.language].placeholder;
  textarea.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  });
  textarea.addEventListener('input', () => {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
  });
  composer.appendChild(textarea);

  const sendBtn = document.createElement('button');
  sendBtn.className = 'send-btn';
  sendBtn.setAttribute('aria-label', I18N[state.language].send);
  sendBtn.innerHTML = `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <line x1="22" y1="2" x2="11" y2="13"></line>
      <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
    </svg>
  `;
  sendBtn.addEventListener('click', send);
  composer.appendChild(sendBtn);

  const creditEl = document.createElement('div');
  creditEl.className = 'footer-credit';
  creditEl.textContent = I18N[state.language].poweredBy;
  panel.appendChild(creditEl);

  root.appendChild(container);

  // ---------- Helpers ----------
  function applyDirection() {
    container.classList.toggle('rtl', RTL_LANGS.has(state.language));
  }

  function toggle() {
    state.open = !state.open;
    panel.classList.toggle('open', state.open);
    if (state.open) {
      setTimeout(() => textarea.focus(), 50);
    }
  }

  function renderMessage(role, content, opts) {
    opts = opts || {};
    const m = document.createElement('div');
    m.className = 'msg ' + role + (opts.error ? ' error' : '');
    // XSS-safe: textContent never interprets HTML.
    m.textContent = content;
    messagesEl.appendChild(m);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return m;
  }

  function renderTyping() {
    const t = document.createElement('div');
    t.className = 'typing';
    t.innerHTML = `<span class="dot"></span><span class="dot"></span><span class="dot"></span>`;
    const label = document.createElement('span');
    label.textContent = ' ' + I18N[state.language].typing;
    t.appendChild(label);
    messagesEl.appendChild(t);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return t;
  }

  async function fetchBotMeta() {
    try {
      const r = await fetch(API_BASE + '/api/v1/webchat/bots/public/' + encodeURIComponent(BOT_ID));
      if (!r.ok) return;
      const meta = await r.json();
      if (!ATTR_ACCENT && meta.accent_color) {
        state.accent = meta.accent_color;
        bubble.style.setProperty('--accent', state.accent);
        panel.style.setProperty('--accent', state.accent);
      }
      if (meta.supported_languages) {
        state.supported = meta.supported_languages.split(',').map((s) => s.trim()).filter(Boolean);
      }
      if (meta.name) state.name = meta.name;
      // welcome
      const welcome = ATTR_WELCOME || meta.welcome_message || '';
      if (welcome) renderMessage('bot', welcome);
    } catch (_) { /* widget keeps working even if meta fails */ }
  }

  async function send() {
    const text = textarea.value.trim();
    if (!text || state.sending) return;
    state.sending = true;
    sendBtn.disabled = true;
    renderMessage('user', text);
    textarea.value = '';
    textarea.style.height = 'auto';
    const typingEl = renderTyping();

    try {
      const r = await fetch(API_BASE + '/api/v1/webchat/chat/' + encodeURIComponent(BOT_ID), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          session_id: state.sessionId || undefined,
          language_hint: state.language,
        }),
      });
      typingEl.remove();
      if (!r.ok) {
        let detail = I18N[state.language].error;
        try { const j = await r.json(); if (j.detail) detail = j.detail; } catch (_) {}
        renderMessage('bot', detail, { error: true });
      } else {
        const data = await r.json();
        if (data.session_id) saveSession(data.session_id);
        if (data.language && data.language !== state.language) {
          // The server detected a different language than the UI; reflect it.
          state.language = data.language;
          langSelect.value = data.language;
          applyDirection();
        }
        renderMessage('bot', data.reply || '');
      }
    } catch (e) {
      typingEl.remove();
      renderMessage('bot', I18N[state.language].error, { error: true });
    } finally {
      state.sending = false;
      sendBtn.disabled = false;
      textarea.focus();
    }
  }

  // ---------- Boot ----------
  fetchBotMeta();
})();
