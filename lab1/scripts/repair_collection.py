#!/usr/bin/env python3
"""Правка архива школы после прогона (одноразовая процедура).

Прогон выявил две «ослышки» Куратора (yandexgpt-5.1), которые не ловятся
паттернами Pydantic, но портят витрину:
1. название картины №3 записано служебной фразой «Бриф для картины №3»;
2. в поле role_in_story («место картины в истории школы») для всех картин
   Куратор вписал свою собственную роль («бессменный куратор…») — утечка
   персона-промпта в данные.

Скрипт просит КУРАТОРА исправить собственный архив (один structured-вызов),
нормализует тексты принципов (убирает дубль «P6: P6: …» — pid уже вынесен
в отдельное поле) и перерендеривает manifest.md / dialogue.md из
collection.json — тех же данных, тем же форматом, что и ноутбук.
"""
import base64
import io
import json
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field
from typing import List

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
import os  # noqa: E402

FOLDER_ID, API_KEY = os.environ["folder_id"], os.environ["api_key"]
client = OpenAI(base_url="https://ai.api.cloud.yandex.net/v1",
                api_key=API_KEY, project=FOLDER_ID)

OUT = ROOT / "output"
c = json.loads((OUT / "collection.json").read_text(encoding="utf-8"))
school, paintings = c["school"], c["paintings"]


# ── 1. Куратор исправляет названия и роли картин ─────────────────────────────
class Fix(BaseModel):
    number: int = Field(description="Номер картины: 1–5")
    title: str = Field(description="Художественное название картины, как в каталоге выставки; если текущее название уже художественное — верни его без изменений")
    role_in_story: str = Field(description="Одно предложение о том, чем ЭТА картина важна в истории школы — о картине, не о кураторе")


class ArchiveFix(BaseModel):
    fixes: List[Fix] = Field(description="Ровно 5 исправлений — по одному на каждую картину, в порядке номеров 1–5")


def principles_lines():
    lines = [f"  {p['pid']}: {p['text']}" for p in school["principles"]]
    for p in paintings:
        am = p.get("amendment")
        if am:
            lines.append(f"  {am['new_principle']['pid']}: {am['new_principle']['text']} "
                         f"(добавлен после картины №{p['number']})")
    return "\n".join(lines)


user = f"""Ты — {school['curator_name']}, куратор школы «{school['school_name']}»
(тема: «{c['theme']}»). После закрытия школы ты вычитываешь архив — и находишь ошибки записи.

Принципы манифеста (в порядке появления):
{principles_lines()}

Картины коллекции (текущая запись: название · роль в истории · что нарушает):
"""
for p in paintings:
    b = p["brief"]
    user += (f"№{p['number']} «{b['title']}» · роль: «{b['role_in_story']}» · "
             f"{'нарушает ' + p['broken_pid'] if p['broken_pid'] else 'ортодоксия'}\n"
             f"   сцена по брифу: {b['scene']}\n")

user += """
Ошибки записи, которые нужно исправить:
1. Название картины №3 записано служебной фразой «Бриф для картины №3» — это не название.
2. В графе «роль в истории школы» для ВСЕХ картин по ошибке вписана твоя собственная роль
   («бессменный куратор художественной школы») — а должно быть место КАРТИНЫ в летописи школы.

Исправь архив: для каждой из пяти картин верни художественное название
(хорошие названия не меняй) и её настоящее место в истории школы."""

resp = client.responses.parse(
    model=f"gpt://{FOLDER_ID}/yandexgpt-5.1",
    instructions=(f"Ты — {school['curator_name']}, властный визионер с искусствоведческим пафосом. "
                  "Пиши по-русски, образно, без канцелярита."),
    input=user, text_format=ArchiveFix, temperature=0.5, max_output_tokens=4096)
fix = resp.output_parsed
assert fix is not None, "структурированный вывод не собрался"
assert [f.number for f in fix.fixes] == [p["number"] for p in paintings], "картины перепутаны"

for f, p in zip(fix.fixes, paintings):
    b = p["brief"]
    print(f"№{p['number']}: «{b['title']}» → «{f.title}»")
    if b["role_in_story"] != f.role_in_story:
        print(f"    роль: «{b['role_in_story']}» → «{f.role_in_story}»")
    b["title"], b["role_in_story"] = f.title, f.role_in_story


# ── 2. Нормализация текстов принципов: «P6: P6: …» → «P6: …» ────────────────
for src in [school["principles"]] + [[p["amendment"]["new_principle"]]
                                     for p in paintings if p.get("amendment")]:
    for pr in src:
        clean = re.sub(rf"^{re.escape(pr['pid'])}\s*:\s*", "", pr["text"]).strip()
        if clean != pr["text"]:
            print(f"нормализация {pr['pid']}: «{pr['text'][:50]}…» → «{clean[:50]}…»")
            pr["text"] = clean


# ── 3. Перерендер manifest.md и dialogue.md (формат ячейки 6 ноутбука) ──────
principles = list(school["principles"]) + [
    p["amendment"]["new_principle"] for p in paintings if p.get("amendment")]


def render_manifest() -> str:
    m = [f"# {school['school_name']} — «{school['slogan']}»",
         f"*Школа живописи на тему «{c['theme']}»*", "",
         f"Куратор: **{school['curator_name']}** · художник: **{school['artist_name']}** · "
         f"критик: **{school['critic_name']}**", "",
         "## Речь открытия", "", school["speech"], "",
         "## Манифест, редакция 1", ""]
    m += [f"- **{p['pid']}**: {p['text']}" for p in school["principles"]]
    for p in paintings:
        am = p["amendment"]
        if am:
            m += ["", f"## Поправка после картины №{p['number']} «{p['brief']['title']}»", "",
                  f"> {am['speech']}", "",
                  f"- **{am['new_principle']['pid']}**: {am['new_principle']['text']}",
                  f"- Следующая картина (№{p['number'] + 1}) обязана нарушить: "
                  f"**{am['break_next']}** — {am['rationale']}"]
    m += ["", f"## Финальная редакция манифеста ({len(principles)} принципов)", ""]
    m += [f"- **{p['pid']}**: {p['text']}" for p in principles]
    cl = paintings[-1]["closing"]
    if cl:
        m += ["", "## Эпилог", "", cl["speech"], "", f"> **{cl['epitaph']}**"]
    return "\n".join(m)


def render_dialogue() -> str:
    m = [f"# {school['school_name']}: протокол школы", "",
         f"Тема: «{c['theme']}». Полный протокол диалогов агентов.", ""]
    for p in paintings:
        b = p["brief"]
        m += [f"## Картина №{p['number']}. «{b['title']}»", "",
              f"*{b['role_in_story']}*", "",
              f"**{school['curator_name']} (куратор)**: {b['speech']}", "",
              f"> Бриф: {b['scene']}",
              f"> Сохранить: {', '.join(b['keep'])}"
              + (f"; нарушить: **{b['break_pid']}**" if b["break_pid"] else "; ортодоксия"), ""]
        for it in p["iterations"]:
            a, v = it["artist"], it["verdict"]
            m += [f"### Итерация {it['iter']}",
                  "",
                  f"**{school['artist_name']} (художник)**: {a['speech']}", "",
                  f"> Замысел: {a['rationale']}", f"> Промпт: `{a['prompt']}`", "",
                  f"**{school['critic_name']} (критик)**: {v['speech']}", "",
                  f"> бриф {v['brief_match']}/10 · манифест {v['manifesto_match']}/10 · "
                  f"ремесло {v['craft']}/10 — **{v['verdict']}**",
                  "> Замечания: " + "; ".join(v["issues"]), "",
                  f"![итерация {it['iter']}]({it['image']})", ""]
        for ce in p.get("censor_events", []):
            m += [f"> 🚫 *Цензор платформы отклонил промпт к итерации {ce['iter']} — "
                  f"художник переписал, сохранив замысел.*", ""]
        m += [f"**Принята итерация {p['final_iter']}**"
              + (" — вердикт критика" if p["accepted_clean"] else " — волей куратора, лучший холст"), ""]
        am = p["amendment"]
        if am:
            m += [f"**{school['curator_name']}**: {am['speech']}", "",
                  f"> Поправка к манифесту: +**{am['new_principle']['pid']}** «{am['new_principle']['text']}»;",
                  f"> следующая картина ломает **{am['break_next']}** — {am['rationale']}", ""]
        cl = p["closing"]
        if cl:
            m += [f"**{school['curator_name']}, эпилог**: {cl['speech']}", "",
                  f"> **{cl['epitaph']}**", ""]
    return "\n".join(m)


(OUT / "manifest.md").write_text(render_manifest(), encoding="utf-8")
(OUT / "dialogue.md").write_text(render_dialogue(), encoding="utf-8")
(OUT / "collection.json").write_text(
    json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
print("\nАрхив исправлен: collection.json, manifest.md, dialogue.md перезаписаны")
