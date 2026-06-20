# V58 Old Buttons + Proxy Split

Изменения:

- Сохранена логика V57: `PROXYS_PROVIDER_MODE=proxys_io` для стандартных/default прокси через общий ключ PROXYS.IO.
- Откатан визуал прокси-раздела к старому понятному стилю.
- MTProxy и Premium снова разделены отдельными кнопками:
  - `🔐 MTProxy`
  - `🏆 PREMIUM`
  - `💯 STANDART`
  - `🏠 Главное меню`
- Исправлена фильтрация прокси-товаров по категориям:
  - `proxy_autofix:mtproxy` открывается только в MTProxy;
  - `proxy_autofix:premium` открывается только в Premium;
  - `proxy_autofix:standard` открывается только в STANDART / PROXYS.IO;
  - больше нет fallback-а, который мог подставить не тот тариф.
- Кнопки админ-меню оставлены в старом clean-стиле из предыдущих патчей, без изменения логики.

Проверка:

```bash
python -m compileall -q app
```

успешно.
