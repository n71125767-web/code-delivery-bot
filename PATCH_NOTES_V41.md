# PATCH V41 — proxy price/autofix PostgreSQL fix

## Исправлено

- Исправлена ошибка PostgreSQL `null value in column "name" of relation "shop_products" violates not-null constraint` при `/proxy_price` и `/proxy_autofix`.
- Новый proxy-autofix товар теперь создаётся сразу с обязательными полями:
  - `name`
  - `description`
  - `price`
  - `currency`
  - `product_type`
  - `fulfillment_type=proxyline`
  - `provider_key`
  - `is_active=True`
- Убран промежуточный `session.flush()` для полупустого `ShopProduct`.

## После деплоя

Выполнить от админа:

```text
/proxy_autofix 100 RUB
/proxy_markup 1.77
```

Если нужно поменять базовую цену:

```text
/proxy_price 150 RUB
```
