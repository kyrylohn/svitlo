/* Налаштування сторінки «Світло». Для своєї групи / будинку змініть лише цей файл (і meta-теги в index.html — див. README). */
window.SVITLO = {
  // Підписи
  title: "Світло",
  group: "17.1",                                   // номер черги / групи — лише для підписів
  provider: "ДТЕК Дніпровські електромережі",     // хто публікує графік (для підпису внизу)

  // Графік відключень: відкриті дані github.com/Baskerville42/outage-data-ua
  region: "dnipro",                               // dnipro | kyiv | kyiv-region | odesa
  groupKey: "GPV17.1",                             // ключ черги у файлі регіону (GPV<черга>.<підчерга>)

  // Стан світла з дому (data.json, який пушить exporter). "" — лише графік, без датчика й статистики.
  dataUrl: "https://raw.githubusercontent.com/kyrylohn/svitlo/data/data.json",
  sensorNote: "датчик у щитку будинку",           // звідки береться факт відключення (для підпису внизу)

  // Екстрені відключення (необов'язково; лише якщо ваш exporter заповнює поле avariika)
  emergencyName: "Дніпро Аварійка",
  emergencyUrl: "https://t.me/dniproavariyka",      // посилання на канал (унизу сторінки й біля «Екстрені до …»)

  // Чат будинку в Telegram (посилання під статусом і внизу сторінки). "" — не показувати.
  chatUrl: "https://t.me/pisarz22_22a",
  chatName: "Чат будинку в Telegram",

  // Сповіщення в Telegram, що сторінкою користуються (Worker з папки worker/). "" — вимкнено.
  notify: "https://svitlo-notify.kyrylohn.workers.dev",


  tz: "Europe/Kyiv",
};
