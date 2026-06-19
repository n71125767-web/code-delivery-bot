# V47 — MTProxy Stock Fix

Причина бага: MTProxy отличался только названием товара и форматом выдачи, но покупка уходила в обычный Proxyline `new-order`, который работает с обычными dedicated/shared IPv4/IPv6 прокси. Поэтому покупателю выдавался обычный HTTP/SOCKS IPv4 вместо MTProxy.

Что изменено:

- MTProxy больше не покупается через обычный Proxyline `new-order`.
- Для MTProxy используется только реальный склад MTProxy-строк.
- Если MTProxy-склад пустой, счёт не создаётся, покупатель видит понятную ошибку.
- После оплаты MTProxy выдаётся в формате:
  - IP
  - порт
  - секретный ключ
  - ссылка подключения `tg://proxy?...`
- Добавлена команда загрузки MTProxy:

```text
/mtproxy_stock_add PRODUCT_ID ip:port:secret
```

Можно загрузить несколько строк сразу, каждая с новой строки:

```text
/mtproxy_stock_add 12 1.2.3.4:443:abcdef123456
5.6.7.8:443:abcdef987654
```

Также поддерживаются готовые ссылки:

```text
/mtproxy_stock_add 12 tg://proxy?server=1.2.3.4&port=443&secret=abcdef123456
```

Как применить:

1. Выполнить `/proxy_autofix 100 RUB`.
2. В ответе найти ID товара `🧩 MTProxy`.
3. Загрузить реальные MTProxy через `/mtproxy_stock_add ID ip:port:secret`.
4. Покупателю при оплате будет выдан именно MTProxy, а не обычный IPv4 proxy.
