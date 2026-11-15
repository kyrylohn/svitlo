# Світло · група 5.1

Невелика сторінка для мешканців будинку: **чи є світло зараз**, графік відключень на сьогодні й завтра і статистика відключень (7 / 30 днів / весь час, смуги по днях, журнал).

- Наша сторінка: https://kyrylohn.github.io/svitlo/ (коротко — svitlo.deusops.net), ДТЕК Дніпровські електромережі, група 5.1.
- Один файл `index.html` без збірки й залежностей, налаштування — `config.js`, шрифт Onest (OFL) у `fonts/`.
- Безкоштовно: GitHub Pages + (необов'язково) будь-який пристрій удома.

Хочете таку для свого будинку? Нижче — три варіанти, від найпростішого.

---

## Як це влаштовано

```
                       ┌──────────── GitHub (ваш форк) ────────────┐
 outage-data-ua ──────▶│ гілка main:  index.html, config.js        │──▶ GitHub Pages ──▶ мешканці
 (графіки ДТЕК)        │ гілка data:  data.json  (+ og.png)        │
                       └───────────────────────▲───────────────────┘
                                               │ git push (раз на хв, коли щось змінилось,
 вдома: пристрій на ДБЖ ── exporter ───────────┘  і щонайменше раз на 15 хв)
        (Raspberry Pi / NAS / ноутбук / Home Assistant)
```

- Сторінка — статична. Вона читає `data.json` з гілки `data` через raw.githubusercontent.com і кешує його в браузері.
- Дім **сам надсилає** знімок у репозиторій. Нічого вдома не відкривається в інтернет, токенів на сторінці немає.
- Якщо вдома зник інтернет, сторінка показує останнє відоме і пише, що дані застаріли (після 20 хв).
- Графік береться з відкритих даних [Baskerville42/outage-data-ua](https://github.com/Baskerville42/outage-data-ua): Київ, Київська обл., Дніпро (та обл.), Одеса. Сторінка може читати його прямо в браузері, тож для графіка сервер не потрібен.

| Варіант | Що показує | Що потрібно вдома |
|---|---|---|
| **1. Лише графік** | графік на сьогодні/завтра, «за графіком зараз світло є / відключення» | нічого |
| **2. Без Home Assistant** | + чи є світло **насправді**, журнал і статистика | будь-який пристрій на ДБЖ, що працює 24/7 |
| **3. З Home Assistant** | те саме, стан світла береться з сутності HA | Home Assistant |

---

## Спершу: знайдіть свою чергу

1. Відкрийте файл свого регіону: [`dnipro.json`](https://raw.githubusercontent.com/Baskerville42/outage-data-ua/main/data/dnipro.json), [`kyiv.json`](https://raw.githubusercontent.com/Baskerville42/outage-data-ua/main/data/kyiv.json), [`kyiv-region.json`](https://raw.githubusercontent.com/Baskerville42/outage-data-ua/main/data/kyiv-region.json), [`odesa.json`](https://raw.githubusercontent.com/Baskerville42/outage-data-ua/main/data/odesa.json).
2. Черги там мають ключі `GPV<черга>.<підчерга>`: черга 3.1 — це `GPV3.1`.
3. Перевірте без жодних правок — відкрийте нашу сторінку з параметрами `r` (регіон) і `q` (черга):
   `https://kyrylohn.github.io/svitlo/?r=kyiv&q=GPV3.1`

   Покаже лише графік цієї черги (без даних нашого будинку).

> День, якого ще немає у файлі, сторінка показує як «графік ще не оприлюднено». День без жодного відключення — як «відключень за графіком немає».

---

## Варіант 1 — лише графік (без нічого вдома)

1. **Fork** цього репозиторію (кнопка Fork на GitHub). Репозиторій має бути публічним, щоб Pages були безкоштовні.
2. Відредагуйте `config.js` у своєму форку:
   ```js
   group: "3.1",
   provider: "ДТЕК Київські електромережі",
   region: "kyiv",
   groupKey: "GPV3.1",
   dataUrl: "",          // ← обов'язково очистіть, інакше сторінка покаже дані НАШОГО будинку
   emergencyName: "",
   notify: "",           // ← очистіть (це наш бот статистики)
   ```
   Внизу сторінки лишається посилання на цей репозиторій (`kyrylohn/svitlo`) — будь ласка, не прибирайте його: так інші будинки знайдуть інструкцію.
3. Відредагуйте meta-теги на початку `index.html` (`<title>`, `og:title`, `og:description`, `og:url`, `og:image`). Їх читають Telegram / Viber для прев'ю посилання, а вони JavaScript не виконують, тож ці теги задаються вручну. Рядки з `og:image` і `twitter:image` або видаліть, або вкажіть свою картинку.
4. **Settings → Pages → Deploy from a branch → `main` / `(root)`**. За хвилину сторінка буде на `https://<ваш-логін>.github.io/svitlo/`.

---

## Варіант 2 — без Home Assistant: реальний стан світла

Потрібен пристрій, який **працює і коли світла немає** (на ДБЖ / павербанку) і має інтернет у цей час: Raspberry Pi, NAS, старий ноутбук, міні-ПК. На ньому працює `exporter/svitlo_export.py` — один файл Python 3.9+, без сторонніх бібліотек.

**Як він дізнається, чи є світло.** Раз на хвилину перевіряє щось, що живиться **лише від мережі** (без ДБЖ):
- `ping` — пінгує такий пристрій у вашій мережі: розумну розетку, ТВ-приставку, другий роутер, комп'ютер без ДБЖ. Відповідає — світло є.
- `http` — запит на адресу такого пристрою.
- `command` — будь-яка ваша команда (код виходу 0 = світло є), наприклад, читання датчика напруги.

Щоб не реагувати на випадковий збій, «світла немає» фіксується лише після кількох невдалих перевірок поспіль (`off_after`), а час відключення береться з першої невдалої.

Скрипт сам веде журнал відключень, додає графік вашої черги з outage-data-ua і позначає тип: **за графіком** — якщо світло зникло в межах планового відключення, **поза графіком** — інакше.

### Налаштування

1. Зробіть варіант 1, але в `config.js` залиште `dataUrl` на свій форк:
   ```js
   dataUrl: "https://raw.githubusercontent.com/<ваш-логін>/svitlo/data/data.json",
   sensorNote: "пристрій у квартирі без ДБЖ",
   ```
2. Створіть гілку `data` (порожню, окрему від коду):
   ```bash
   git clone https://github.com/<ваш-логін>/svitlo.git ~/svitlo-data
   cd ~/svitlo-data
   git checkout --orphan data
   git rm -rf . && git commit --allow-empty -m "Дані сторінки"
   git push -u origin data
   ```
3. Дайте пристрою право пушити **лише в цей репозиторій**. Підходить будь-який із двох способів:
   - **Fine-grained token**: GitHub → Settings → Developer settings → Fine-grained tokens. Repository access — лише `svitlo`, Permissions → Contents: *Read and write*. Збережіть його в git: `git config credential.helper store`, потім один раз `git push` з токеном замість пароля.
   - **Deploy key**: Settings репозиторію → Deploy keys → *Allow write access*, і remote через SSH.
4. Налаштуйте скрипт:
   ```bash
   cd ~/svitlo-src/exporter            # будь-яка копія гілки main
   cp config.example.json config.json  # config.json у .gitignore
   nano config.json                    # repo_dir, region, group_key, source
   python3 svitlo_export.py --check    # «світло є» / «світла немає»
   python3 svitlo_export.py --dry      # покаже data.json, нічого не пушить
   python3 svitlo_export.py --once --force   # перший пуш
   ```
5. Запустіть постійно. Приклад для Linux / Raspberry Pi (systemd), файл `/etc/systemd/system/svitlo.service`:
   ```ini
   [Unit]
   Description=Svitlo exporter
   After=network-online.target

   [Service]
   User=pi
   ExecStart=/usr/bin/python3 -u /home/pi/svitlo-src/exporter/svitlo_export.py --config /home/pi/svitlo-src/exporter/config.json
   Restart=always
   RestartSec=30

   [Install]
   WantedBy=multi-user.target
   ```
   Потім `sudo systemctl enable --now svitlo` і `journalctl -u svitlo -f`. На macOS те саме робить LaunchAgent з `KeepAlive`.

Журнал зберігається в `<repo_dir>/.git/svitlo_state.json`, у git він не потрапляє. Гілка `data` завжди має **один** коміт (amend + force-push), тож історія не росте.

---

## Варіант 3 — з Home Assistant

Найпростіше — той самий exporter із джерелом `ha`. Він читає будь-яку `binary_sensor` (`on` = світло є), наприклад:
- пінг-сенсор пристрою без ДБЖ;
- датчик напруги розумної розетки чи лічильника, перетворений на `binary_sensor` шаблоном;
- стан ДБЖ / зарядної станції «живлення від мережі».

```json
"source": { "type": "ha", "url": "http://homeassistant.local:8123", "entity": "binary_sensor.svitlo", "token_env": "HA_TOKEN" }
```
Токен — **Long-lived access token** з профілю HA, лише в змінній середовища (`HA_TOKEN=… python3 svitlo_export.py`, або `Environment=HA_TOKEN=…` у systemd). У файли його не записуйте.

Exporter можна запускати на будь-якому комп'ютері в мережі з HA (зокрема на тому самому сервері). Коли HA недоступний, сторінка покаже «невідомо, чи є світло», а не «світла немає».

> На нашій сторінці замість цього працює власний експорт з HA. Він веде журнал у HA, об'єднує графіки ДТЕК і Yasno та додає екстрені відключення з Telegram-каналу. Формат `data.json` у нього такий самий (див. нижче), тому сторінка однакова.

---

## Формат `data.json` (v1)

Будь-що, що пише такий файл, підходить як джерело. Усі поля, крім `v`, необов'язкові: без `svitlo` сторінка працює як варіант 1, без `grafik` бере графік з outage-data-ua сама.

```jsonc
{
  "v": 1,
  "generated": 1794702637,          // коли сформовано (epoch, с) — для «дані на 02:30» і попередження про застарілі дані
  "svitlo": "on",                   // "on" | "off" | "unknown"
  "pochatok": 0,                    // коли зникло світло (epoch), 0 — якщо світло є
  "typ": "",                        // тип поточного відключення: "p" за графіком | "e" екстрене | "n" поза графіком | ""
  "zhurnal": [                      // завершені відключення
    { "s": 1794687748, "e": 1794700000, "t": "p" }   // початок, кінець (epoch), тип ("u" — невідомо)
  ],
  "grafik": {                       // графік черги; хвилини від півночі за Києвом
    "date": "2026-11-15",           // дата «сьогодні» для today
    "today":    [{ "s": 480, "e": 660, "t": "p" }],  // t: "p" — відключення, "i" — можливе
    "tomorrow": null,               // null — ще не оприлюднено
    "tomorrow_status": "waiting_for_schedule",
    "onovleno": "14.11.2026 19:46", // коли оновився графік (текст)
    "ok": true
  },
  "nastupne": "2026-11-15T08:00:00+02:00",      // початок наступного планового відключення (ISO) — інакше сторінка рахує з grafik
  "vkliuchennia": "2026-11-15T11:00:00+02:00",  // кінець поточного / наступного
  "avariika": { "do": null, "mozhlyve_podovzhennia": false }   // екстрені «до» (ISO) — якщо є своє джерело
}
```

Локальна перевірка сторінки: `python3 -m http.server`, покласти поруч `test-data.json` і відкрити `http://localhost:8000/?data=test-data.json`.

---

## Необов'язково

### Статистика відвідувань у Telegram
Папка `worker/` — Cloudflare Worker, який надсилає в групу Telegram «хтось відкрив сторінку»: новий чи повторний відвідувач, пристрій, звідки прийшли, місто, скільки був на сторінці й що натискав. IP не збирається. Боти та прев'ю посилань не рахуються. Свої пристрої виключаються відкриттям сторінки з `?me=1`.

1. Створіть бота в @BotFather, додайте його в окрему групу й дізнайтеся `chat_id` групи.
2. У `worker/wrangler.toml` змініть `name` і `ALLOWED_ORIGINS` на `https://<ваш-логін>.github.io`.
3. Розгорніть (потрібен безкоштовний акаунт Cloudflare):
   ```bash
   cd worker
   npx wrangler deploy
   npx wrangler secret put BOT_TOKEN
   npx wrangler secret put CHAT_ID
   ```
4. У `config.js`: `notify: "https://<name>.<ваш-субдомен>.workers.dev"`.

### Картинка-прев'ю посилання
Telegram показує картинку з `og:image`. У нас це `og.png`, який домашній експорт малює разом із `data.json` (статус + смуга графіка). Найпростіше для форку — статична картинка 1200×630 у гілці `main` і `og:image` на неї. Telegram кешує прев'ю: щоб оновити, надішліть посилання боту @WebpageBot.

### Свій домен
Як у нас: DNS-запис у Cloudflare (proxied) і правило Redirect на `https://<логін>.github.io/svitlo/…`. Або Custom domain у налаштуваннях Pages.

---

## Ліцензія

Код — MIT (`LICENSE`). Шрифт Onest — SIL OFL 1.1 (`fonts/OFL.txt`). Дані графіків — [outage-data-ua](https://github.com/Baskerville42/outage-data-ua); сторінка їх лише читає. Сторінка неофіційна: точний графік — на сайті вашого обленерго.
