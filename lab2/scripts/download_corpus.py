#!/usr/bin/env python3
"""Скачивание корпуса русских пьес (Чехов) с Викитеки + очистка wikitext."""
import os
import re
import time
import urllib.request
import urllib.parse

OUT = os.path.join(os.path.dirname(__file__), "..", "data", "plays")
os.makedirs(OUT, exist_ok=True)

PLAYS = [
    ("chayka", "Антон Павлович Чехов. Чайка", "Чайка (Чехов)",
     ["Действие первое", "Действие второе", "Действие третье", "Действие четвёртое"]),
    ("vishnevyi_sad", "Антон Павлович Чехов. Вишнёвый сад", "Вишнёвый сад (Чехов)",
     ["Действие первое", "Действие второе", "Действие третье", "Действие четвёртое"]),
    ("dyadya_vanya", "Антон Павлович Чехов. Дядя Ваня", "Дядя Ваня (Чехов)",
     ["Действие первое", "Действие второе", "Действие третье", "Действие четвёртое"]),
]


def clean_wikitext(raw: str) -> str:
    """Грубая, но достаточная очистка wikitext пьесы до читаемого текста."""
    t = raw
    t = re.sub(r"<ref[^>]*>.*?</ref>", "", t, flags=re.S)
    t = re.sub(r"<ref[^/>]*/>", "", t)
    t = re.sub(r"<div[^>]*>|</div>|<span[^>]*>|</span>", "", t)
    t = re.sub(r"__NOTOC__|__NOEDITSECTION__", "", t)
    # Полезные шаблоны пьес: razr (имя персонажа) и rem (ремарка)
    t = re.sub(r"\{\{razr\|([^}]*)\}\}", r"\1", t)
    t = re.sub(r"\{\{rem\|([^}]*)\}\}", r"(\1)", t)
    # Остальные шаблоны выбрасываем (возможно, вложенные — в несколько проходов)
    for _ in range(5):
        t = re.sub(r"\{\{[^{}]*\}\}", "", t)
    # Вики-ссылки: [[a|b]] -> b, [[a]] -> a
    t = re.sub(r"\[\[[^]|]*\|([^\]]*)\]\]", r"\1", t)
    t = re.sub(r"\[\[([^\]]*)\]\]", r"\1", t)
    t = re.sub(r"\[https?://\S+\s+[^\]]*\]", "", t)   # внешние ссылки с текстом
    t = re.sub(r"https?://\S+", "", t)
    t = re.sub(r"'''+", "", t)                          # жирный/курсив
    t = re.sub(r"&nbsp;?", " ", t)
    t = re.sub(r"\{Категория.*?\}", "", t, flags=re.S)
    t = re.sub(r"\[\[Категория:.*?\]\]", "", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def fetch(title: str) -> str:
    url = ("https://ru.wikisource.org/w/index.php?title="
           + urllib.parse.quote(title) + "&action=raw")
    req = urllib.request.Request(url, headers={"User-Agent": "theatre-lab/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8")


for slug, header, base, actions in PLAYS:
    for i, act in enumerate(actions, 1):
        path = os.path.join(OUT, f"{slug}_d{i}.txt")
        if os.path.exists(path) and os.path.getsize(path) > 5000:
            print(f"skip (cached): {path}")
            continue
        raw = fetch(f"{base}/{act}")
        text = clean_wikitext(raw)
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"{header}. {act}.\n\n{text}\n")
        print(f"saved: {path} ({len(text)} chars)")
        time.sleep(0.5)

print("\nКорпус готов:", sorted(os.listdir(OUT)))
