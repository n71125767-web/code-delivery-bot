handlers_code = """# полностью вставляем исправленный код handlers.py здесь, начиная с import logging ..."""

with open(r"C:\Users\Admin\Documents\code-delivery-bot\app\handlers.py", "w", encoding="utf-8", newline="\n") as f:
    f.write(handlers_code)

print("handlers.py создан и сохранён в UTF-8")