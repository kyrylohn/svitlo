/**
 * svitlo-notify: повідомляє в Telegram, що сторінкою «Світло · група 17.1» користуються.
 * Токен бота живе лише тут (секрет BOT_TOKEN), CHAT_ID теж секрет.
 *
 * POST /visit  { visit }              -> { ok, ref }  нове повідомлення про відкриття сторінки
 * POST /update { ref, visit, activity }               дописує в нього, що людина робила (sendBeacon, text/plain)
 *
 * Що НЕ збираємо: IP, точну адресу, ім'я. Лише: новий / повторний (випадковий id у браузері), пристрій і браузер,
 * місто й провайдер (з Cloudflare), звідки прийшли, скільки була на сторінці і що натискала.
 * Боти й прев'ю посилань (Telegram, Viber…) пропускаються. Свої пристрої — ?me=1 на сторінці.
 */

const BOT_UA = /bot|crawl|spider|slurp|headless|preview|facebookexternalhit|embedly|curl|wget|python|go-http|java\/|monitor|lighthouse|telegram|viber|whatsapp/i;

const escapeHtml = (s) => String(s ?? '').replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
const clean = (s, max = 120) => escapeHtml(String(s ?? '').trim().slice(0, max));
const num = (n, min, max) => {
  const v = Math.round(Number(n));
  return Number.isFinite(v) ? Math.min(Math.max(v, min), max) : null;
};
const kyivTime = (iso) => {
  const t = Date.parse(iso);
  const d = Number.isFinite(t) && Math.abs(Date.now() - t) < 86400000 ? new Date(t) : new Date();
  return d.toLocaleString('uk-UA', { timeZone: 'Europe/Kyiv', dateStyle: 'short', timeStyle: 'short' });
};

function corsHeaders(origin, env) {
  const allowed = env.ALLOWED_ORIGINS.split(',').map((s) => s.trim());
  if (!allowed.includes(origin)) return null;
  return {
    'Access-Control-Allow-Origin': origin,
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400',
    Vary: 'Origin'
  };
}
const json = (body, status, headers) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json', ...headers } });
async function readJson(request) {
  try { return JSON.parse(await request.text()); } catch { return null; }
}

async function telegram(env, method, payload) {
  const res = await fetch(`https://api.telegram.org/bot${env.BOT_TOKEN}/${method}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chat_id: env.CHAT_ID, parse_mode: 'HTML', disable_web_page_preview: true, disable_notification: true, ...payload })
  });
  const data = await res.json().catch(() => ({}));
  if (!data.ok && !/not modified/.test(data.description || '')) console.error('Telegram error', method, res.status, data.description);
  return data;
}

/* Підписаний ref: редагувати повідомлення може лише сторінка, що його створила */
async function hmac(env, text) {
  const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(env.BOT_TOKEN), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(text));
  return btoa(String.fromCharCode(...new Uint8Array(sig))).replace(/[+/=]/g, '').slice(0, 22);
}
const makeRef = async (env, id) => `${id}.${await hmac(env, String(id))}`;
async function readRef(env, ref) {
  const [id, sig] = String(ref || '').split('.');
  if (!/^\d+$/.test(id || '') || !sig) return null;
  return (await hmac(env, id)) === sig ? Number(id) : null;
}

function device(ua) {
  let os = 'інша ОС';
  if (/iPhone|iPad|iPod/.test(ua)) os = /iPad/.test(ua) ? 'iPad' : 'iPhone';
  else if (/Android/.test(ua)) os = 'Android';
  else if (/Windows/.test(ua)) os = 'Windows';
  else if (/Mac OS X|Macintosh/.test(ua)) os = 'Mac';
  else if (/Linux/.test(ua)) os = 'Linux';
  const browsers = [['Edge', /Edg\//], ['Opera', /OPR\//], ['Samsung', /SamsungBrowser\//], ['Firefox', /Firefox|FxiOS/], ['Chrome', /Chrome|CriOS/], ['Safari', /Safari/]];
  const inApp = /Telegram/i.test(ua) ? 'у Telegram' : /Viber/i.test(ua) ? 'у Viber' : '';
  const b = (browsers.find(([, re]) => re.test(ua)) || ['браузер'])[0];
  return `${/Mobi|Android|iPhone|iPod/.test(ua) ? '📱' : '💻'} ${os}, ${inApp || b}`;
}

function source(visit) {
  const ref = String(visit.referrer || '');
  let from = 'пряме посилання або закладка';
  if (/t\.me|telegram/i.test(ref)) from = 'Telegram';
  else if (/viber/i.test(ref)) from = 'Viber';
  else if (/deusops\.net/i.test(ref)) from = 'svitlo.deusops.net';
  else if (ref) { try { from = new URL(ref).hostname; } catch { from = clean(ref, 60); } }
  const tag = clean(visit.from, 30);
  return tag ? `${escapeHtml(from)} · мітка «${tag}»` : escapeHtml(from);
}

function visitText(request, visit) {
  const cf = request.cf || {};
  const n = num(visit.visitNo, 1, 100000) || 1;
  const head = n > 1
    ? `🔁 <b>Знову відкрили «Світло»</b> (${n}-й раз${visit.firstSeen ? `, вперше ${clean(visit.firstSeen, 20)}` : ''})`
    : '👀 <b>Новий відвідувач «Світла»</b>';
  const place = [cf.city, cf.country && cf.country !== 'UA' ? cf.country : ''].filter(Boolean).map(escapeHtml).join(', ');
  const org = cf.asOrganization ? escapeHtml(cf.asOrganization) : '';
  const state = visit.state ? `\n💡 На сторінці: ${clean(visit.state, 80)}` : '';
  return [
    head,
    '',
    `${device(request.headers.get('User-Agent') || '')}`,
    `🔗 Звідки: ${source(visit)}`,
    `📍 ${[place, org].filter(Boolean).join(' · ') || 'невідомо'}`,
    `🕐 ${kyivTime(visit.openedAt)}${state}`
  ].join('\n');
}

const CLICK_LABELS = {
  tomorrow: 'графік на завтра',
  p30: '30 днів',
  pall: 'усе',
  day: 'день у журналі',
  cal: 'день у календарі',
  more: 'увесь журнал',
  refresh: 'оновити',
  chat: 'перейшли в чат будинку',
  avariika: 'перейшли в «Дніпро Аварійка»',
  contact: '💼 написали автору (налаштувати свій)',
  donate: '💛 перейшли підтримати (Base by mono)'
};
function activityText(activity = {}) {
  const sec = num(activity.seconds, 0, 86400) ?? 0;
  const t = sec < 60 ? `${sec} с` : `${Math.floor(sec / 60)} хв${sec % 60 ? ` ${sec % 60} с` : ''}`;
  const scroll = num(activity.scroll, 0, 100) ?? 0;
  const clicks = [...new Set((Array.isArray(activity.clicks) ? activity.clicks : []).map(String))].filter((c) => CLICK_LABELS[c]).map((c) => CLICK_LABELS[c]);
  return ['', '—', `⏱ ${t} на сторінці, догорнули до ${scroll}%`, clicks.length ? `👆 ${clicks.join(', ')}` : 'Нічого не натискали'].join('\n');
}

async function handleVisit(request, env, cors) {
  const data = (await readJson(request)) || {};
  if (BOT_UA.test(request.headers.get('User-Agent') || '')) return json({ ok: true, skipped: 'bot' }, 200, cors);
  const res = await telegram(env, 'sendMessage', { text: visitText(request, data.visit || {}) });
  if (!res.ok) return json({ ok: false }, 502, cors);
  return json({ ok: true, ref: await makeRef(env, res.result.message_id) }, 200, cors);
}

async function handleUpdate(request, env, cors) {
  const data = await readJson(request);
  const id = data && (await readRef(env, data.ref));
  if (!id) return json({ ok: false, error: 'bad_ref' }, 400, cors);
  const res = await telegram(env, 'editMessageText', { message_id: id, text: `${visitText(request, data.visit || {})}\n${activityText(data.activity)}` });
  return json({ ok: !!res.ok }, 200, cors);
}

export default {
  async fetch(request, env) {
    const cors = corsHeaders(request.headers.get('Origin') || '', env);
    if (!cors) return new Response('Forbidden', { status: 403 });
    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors });
    if (request.method !== 'POST') return json({ ok: false, error: 'method' }, 405, cors);
    const { pathname } = new URL(request.url);
    if (pathname === '/visit') return handleVisit(request, env, cors);
    if (pathname === '/update') return handleUpdate(request, env, cors);
    return json({ ok: false, error: 'not_found' }, 404, cors);
  }
};
