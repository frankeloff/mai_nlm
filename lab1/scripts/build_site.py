#!/usr/bin/env python3
"""Сборка сайта-галереи (site/index.html) из output/collection.json.

Сайт рассчитан на размещение index.html в КОРНЕ репозитория mai_nlm и публикацию
через GitHub Pages из ветки main (как в эталонном примере лабораторной):
картины подключаются относительными путями lab1/output/paintings/…,
поэтому сам файл site/index.html нужно скопировать в корень репозитория.
"""
import html
import json
from pathlib import Path

OUT = Path("output")
SITE = Path("site")
IMG_PREFIX = "lab1/"          # пути от корня репозитория mai_nlm
ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI"}

c = json.loads((OUT / "collection.json").read_text(encoding="utf-8"))
school = c["school"]


def esc(t: str) -> str:
    return html.escape(str(t or ""))


def img(path: str, alt: str, width="100%") -> str:
    return (f'<img src="{IMG_PREFIX}{esc(path)}" alt="{esc(alt)}" '
            f'style="width:{width}" loading="lazy">')


# ── счётчики для футера ──────────────────────────────────────────────────────
n_iters = sum(len(p["iterations"]) for p in c["paintings"])
n_accept = sum(1 for p in c["paintings"] if p["accepted_clean"])
n_censor = sum(len(p.get("censor_events", [])) for p in c["paintings"])

CSS = """
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body { margin: 0; background: #101014; color: #d8d4cc;
       font: 16px/1.65 Georgia, 'Times New Roman', serif; }
header, main, footer { max-width: 900px; margin: 0 auto; padding: 24px 20px; }
header { text-align: center; padding-top: 64px; }
h1 { font-size: 34px; letter-spacing: .5px; margin: 0 0 6px; }
.slogan { font-style: italic; color: #b8a97e; font-size: 19px; margin: 0 0 18px; }
.meta { color: #8e8a80; font-size: 14px; }
.badge { display: inline-block; border: 1px solid #4a463d; border-radius: 20px;
         padding: 2px 12px; margin: 3px; font-size: 13px; color: #b8b2a4; }
hr { border: 0; border-top: 1px solid #33302a; margin: 40px 0; }
h2 { font-size: 25px; margin: 34px 0 4px; }
h3 { font-size: 17px; color: #b8a97e; margin: 24px 0 8px; font-weight: normal;
     text-transform: uppercase; letter-spacing: 2px; }
.painting { margin-bottom: 56px; }
.role { font-style: italic; color: #8e8a80; margin: 2px 0 14px; }
figure { margin: 14px 0; }
figure img { border-radius: 4px; display: block; }
figcaption { font-size: 13.5px; color: #8e8a80; margin-top: 6px; font-style: italic; }
details { background: #18181d; border: 1px solid #2c2c33; border-radius: 6px;
          padding: 10px 16px; margin: 14px 0; }
summary { cursor: pointer; color: #b8a97e; font-size: 15px; }
.speech { margin: 12px 0; }
.who { color: #b8a97e; font-style: italic; }
blockquote { border-left: 3px solid #4a463d; margin: 8px 0 8px 4px;
             padding: 2px 0 2px 14px; color: #c4bfb5; font-size: 15px; }
code { font: 13px/1.5 ui-monospace, Menlo, Consolas, monospace; color: #9fbf9f; }
.score { font-size: 14px; color: #b8b2a4; }
.verdict-accept { color: #8fc97e; font-weight: bold; }
.verdict-revise { color: #d99a6c; font-weight: bold; }
.censor { color: #d97e7e; font-size: 14px; font-style: italic; }
.epitaph { font-size: 21px; font-style: italic; text-align: center;
           color: #d8d4cc; margin: 32px 40px; }
footer { color: #8e8a80; font-size: 13.5px; padding-bottom: 60px; }
table { border-collapse: collapse; font-size: 14px; margin: 10px 0; }
td, th { border: 1px solid #33302a; padding: 4px 12px; text-align: left; }
a { color: #b8a97e; }
"""

parts = []
parts.append(f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(school['school_name'])} — галерея агентского художника</title>
<style>{CSS}</style>
</head>
<body>
<header>
  <h1>{esc(school['school_name'])}</h1>
  <p class="slogan">«{esc(school['slogan'])}»</p>
  <p class="meta">Вымышленная художественная школа, основанная многоагентной системой
  на тему «{esc(c['theme'])}».<br>
  Куратор <b>{esc(school['curator_name'])}</b> · художник <b>{esc(school['artist_name'])}</b> ·
  критик <b>{esc(school['critic_name'])}</b></p>
  <p>
    <span class="badge">Куратор — yandexgpt-5.1</span>
    <span class="badge">Художник — aliceai-llm</span>
    <span class="badge">Критик (VLM) — qwen3.6-35b-a3b</span>
    <span class="badge">Холсты — YandexART</span>
  </p>
</header>
<main>

<h3>Как устроена школа</h3>
<p>Единственный человеческий вход — заданная тема, одна строка. Всё остальное порождает
система: Куратор открывает школу — пишет манифест из пяти принципов и выдаёт бриф на каждую
картину. Художник сочиняет промпт для YandexART. Критик — единственный, кто действительно
<em>видит</em> готовый холст (мультимодальная модель), — выносит вердикт: оценки, замечания,
«принять» или «доработать». Художник перерабатывает промпт — и так до принятия или до трёх
итераций.</p>
<p>Эволюция школы формализована догматом <b>«наследуй всё — сломай один»</b>: после каждой
принятой картины Куратор пишет поправку — школа усваивает новый принцип, а следующая картина
обязана сохранить все принципы и <em>нарушить ровно один</em>, назначенный поправкой.
Картина №1 — ортодоксия, дальше — нарастающий раскол.</p>
""")

# ── манифест, редакция 1 ─────────────────────────────────────────────────────
parts.append('<h3>Манифест, редакция первая</h3>')
parts.append(f'<blockquote>{esc(school["speech"])}</blockquote>')
parts.append('<ul>')
for p in school["principles"]:
    parts.append(f'<li><b>{esc(p["pid"])}</b>. {esc(p["text"])}</li>')
parts.append('</ul>')

# ── картины ──────────────────────────────────────────────────────────────────
parts.append("<hr>")
parts.append("<h3>Коллекция</h3>")

for p in c["paintings"]:
    b = p["brief"]
    num = ROMAN.get(p["number"], str(p["number"]))
    parts.append(f'<div class="painting" id="p{p["number"]}">')
    parts.append(f'<h2>Полотно {num}. {esc(b["title"])}</h2>')
    parts.append(f'<p class="role">{esc(b["role_in_story"])}'
                 + (f' — нарушает принцип <b>{esc(p["broken_pid"])}</b>'
                    if p.get("broken_pid") else ' — ортодоксия')
                 + '</p>')

    # финальный холст
    parts.append(f'<figure>{img(p["final_image"], b["title"])}'
                 f'<figcaption>Финальный холст · итерация {p["final_iter"]} — '
                 + ('принято критиком' if p["accepted_clean"] else 'принято волей куратора')
                 + '</figcaption></figure>')

    # свёрнутый диалог
    parts.append('<details><summary>Диалог агентов: как рождалась картина</summary>')
    parts.append(f'<p class="speech"><span class="who">{esc(school["curator_name"])} (куратор)</span>: '
                 f'{esc(b["speech"])}</p>')
    parts.append(f'<blockquote><b>Бриф</b>: {esc(b["scene"])}</blockquote>')
    for ce in p.get("censor_events", []):
        parts.append(f'<p class="censor">🚫 Цензор платформы отклонил промпт к итерации '
                     f'{ce["iter"]} — художник переписал, сохранив замысел.</p>')
    for it in p["iterations"]:
        a, v = it["artist"], it["verdict"]
        parts.append(f'<p class="speech"><span class="who">{esc(school["artist_name"])} '
                     f'(художник)</span>: {esc(a["speech"])}</p>')
        parts.append(f'<blockquote><b>Замысел</b>: {esc(a["rationale"])}<br>'
                     f'<b>Промпт</b>: <code>{esc(a["prompt"])}</code></blockquote>')
        parts.append(f'{img(it["image"], f"итерация {it['iter']}", "70%")}')
        vcls = "verdict-accept" if v["verdict"] == "accept" else "verdict-revise"
        parts.append(f'<p class="speech"><span class="who">{esc(school["critic_name"])} '
                     f'(критик)</span>: {esc(v["speech"])}</p>')
        parts.append(f'<p class="score">бриф {v["brief_match"]}/10 · манифест '
                     f'{v["manifesto_match"]}/10 · ремесло {v["craft"]}/10 — '
                     f'<span class="{vcls}">{v["verdict"]}</span></p>')
        parts.append('<blockquote><b>Замечания</b>: ' + '; '.join(esc(i) for i in v["issues"])
                     + '</blockquote>')
    parts.append(f'<p class="score">Принята итерация {p["final_iter"]} — '
                 + ('вердикт критика' if p["accepted_clean"] else 'волей куратора: лучший холст')
                 + '</p>')
    am = p.get("amendment")
    if am:
        parts.append(f'<p class="speech"><span class="who">{esc(school["curator_name"])}</span>: '
                     f'{esc(am["speech"])}</p>')
        parts.append(f'<blockquote><b>Поправка к манифесту</b>: + <b>{esc(am["new_principle"]["pid"])}</b> '
                     f'{esc(am["new_principle"]["text"])}<br>'
                     f'Следующая картина обязана нарушить <b>{esc(am["break_next"])}</b> — '
                     f'{esc(am["rationale"])}</blockquote>')
    parts.append('</details>')
    parts.append('</div>')

# ── эпилог ───────────────────────────────────────────────────────────────────
cl = c["paintings"][-1].get("closing") if c["paintings"] else None
if cl:
    parts.append('<hr>')
    parts.append('<h3>Эпилог школы</h3>')
    parts.append(f'<p class="speech"><span class="who">{esc(school["curator_name"])}</span>: '
                 f'{esc(cl["speech"])}</p>')

# финальная редакция манифеста: принципы из поправок + исходные
final_pids = []
final_principles = {p["pid"]: p["text"] for p in school["principles"]}
for p in c["paintings"]:
    am = p.get("amendment")
    if am:
        final_principles[am["new_principle"]["pid"]] = am["new_principle"]["text"]
parts.append(f'<details><summary>Финальная редакция манифеста — {len(final_principles)} принципов</summary><ul>')
for pid in sorted(final_principles, key=lambda x: int(x[1:])):
    parts.append(f'<li><b>{esc(pid)}</b>. {esc(final_principles[pid])}</li>')
parts.append('</ul></details>')
if cl:
    parts.append(f'<p class="epitaph">«{esc(cl["epitaph"])}»</p>')

# ── футер ────────────────────────────────────────────────────────────────────
parts.append(f"""</main>
<footer>
<p>Многоагентная система «Агент-художник»: {len(c['paintings'])} картин, {n_iters} итераций
VLM-контура, принято критиком — {n_accept}, волей куратора — {len(c['paintings']) - n_accept},
промптов отклонено цензором платформы — {n_censor}.</p>
<p>Куратор — yandexgpt-5.1 (Yandex) · Художник — aliceai-llm (Yandex) ·
Критик — qwen3.6-35b-a3b (Alibaba) · холсты — YandexART (aliceai-image-art-3.0).
Все диалоги и реплики сгенерированы моделями; система написана в паре с кодинг-агентом.</p>
<p>Код и полный протокол — <a href="https://github.com/frankeloff/mai_nlm/tree/main/lab1">frankeloff/mai_nlm/lab1</a>.
Лабораторная работа «АХ: Агент-художник», курс «Современный NLP и большие языковые модели», МАИ, 2026.</p>
</footer>
</body>
</html>""")

SITE.mkdir(exist_ok=True)
page = "\n".join(parts)
# f-строка с вложенными кавычками в img(...) не подходит для старых python — просто склеили
(SITE / "index.html").write_text(page, encoding="utf-8")
print(f"Сайт собран: site/index.html ({len(page) // 1024} КБ), "
      f"картин: {len(c['paintings'])}, итераций: {n_iters}")
