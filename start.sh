#!/usr/bin/env bash

# Запуск Telegram-бота
python -m app.bot &

# Запуск health сервера для Render
python health.py