# PATCH V55 — UI Self-check feedback hotfix

Исправлено:

- Render больше не падает с `UI self-check failed: missing buyer callbacks: [\'buyer:feedback\']`.
- Self-check больше не требует кнопку `buyer:feedback`, потому что в актуальном главном меню покупателя обратная связь не является обязательной кнопкой.
- Меню покупателя остаётся в формате V53/V54: товары, корзина, номера, прокси, кошелёк, мои заказы, FAQ.

Проверка:

```bash
python -m compileall -q app
```
