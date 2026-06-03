#!/usr/bin/env bash
# Запуск бота и health-проверки через админ-аккаунт
python -m app.bot &
python health.py
