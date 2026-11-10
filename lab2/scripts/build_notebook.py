#!/usr/bin/env python3
"""Сборка LLM_Theatre.ipynb из списка ячеек (md + code)."""
import nbformat as nbf

nb = nbf.v4.new_notebook()
cells = []


def md(text):
    cells.append(nbf.v4.new_markdown_cell(text.strip()))


def code(text):
    cells.append(nbf.v4.new_code_cell(text.strip()))


# ===================================================================== README
md("""
# Агентский театр

**Лабораторная работа**: многоагентная система для автоматического написания (симуляции) пьесы.

## Концепция

Театр абсурда: три языковые модели **трёх разных производителей** — Яндекс, Alibaba и DeepSeek — за кулисами театра спорят, кто из них «настоящий актёр», а кто — машина, читающая чужие реплики. Спор о подлинности интеллекта разыгран самими носителями этого интеллекта, а наивность самого «дешёвого» участника труппы — драматургический двигатель пьесы.

## Архитектура

```
                    ТЕМА-СЕМЯ (одно предложение)
                           │
                     ┌─────▼─────┐
                     │ ДРАМАТУРГ │  yandexgpt-5.1, структурированный вывод:
                     └─────┬─────┘  название, персонажи, 3 акта, майлстоуны, финал
                           │  макроплан
        ┌──────────────────▼──────────────────┐
        │              СПЕКТАКЛЬ              │
        │  ┌──────────┐       ┌────────────┐  │
        │  │ РЕЖИССЁР │──────▶│  ТРУППА    │  │
        │  └──────────┘       │ АРТИСТ     │  │  yandexgpt-5.1 + file search
        │   кто говорит,      │ ПРАГМАТИК  │  │  qwen3.6-35b-a3b + web search
        │   ремарка, занавес  │ ПРОСТАК    │  │  deepseek-v4.1-flash
        │                     └────────────┘  │
        └──────────────────┬──────────────────┘
                           │
                 play.md + радиоспектакль (SpeechKit, свой голос на персонажа)
```

## Соответствие пунктам оценивания

| Пункт | Механизм |
|---|---|
| Осмысленный диалог LLM (2) | Три актёра с промптами-масками и общей историей сцены |
| Инструменты, в т.ч. файловый поиск (+1) | File Search (Vector Store по 3 пьесам Чехова) у Артиста, Web Search у Прагматика |
| 3+ персонажа и механизм выбора говорящего (+1) | LLM-Режиссёр со структурированным выводом (`next_speaker`) |
| Макропланирование сюжета (+1) | Драматург заранее пишет план: 3 акта с майлстоунами |
| Закадровые комментарии (+1) | Ремарки Режиссёра к каждой реплике |
| Синтез голосом (+0.5) | Yandex SpeechKit: реплики — голосами персонажей, ремарки — голосом чтеца |

Решения зафиксированы в `GLOSSARY.md` и `docs/adr/`.
""")

# ===================================================================== setup
code("""
# Зависимости (в рабочем окружении уже установлены, ячейка — для воспроизводимости)
# %pip install -q openai python-dotenv pydantic requests
""")

code("""
import json
import os
import re
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field
from typing import List, Literal

# ── Конфигурация ────────────────────────────────────────────────────────────
# Ключи лежат в .env (см. .env.sample): folder_id, api_key — доступ к Yandex AI Studio
load_dotenv(".env")
FOLDER_ID = os.environ["folder_id"]
API_KEY = os.environ["api_key"]

# OpenAI-совместимый шлюз Yandex AI Studio. Один клиент обслуживает и диалоги
# (Responses API), и загрузку файлов, и векторные хранилища.
# Важно: параметр project отправляет заголовок OpenAI-Project — без него
# файловые API отвечают 400.
BASE_URL = "https://ai.api.cloud.yandex.net/v1"
client = OpenAI(base_url=BASE_URL, api_key=API_KEY, project=FOLDER_ID)
print("Клиент готов, каталог:", FOLDER_ID[:8] + "…")
""")

code("""
# ── Труппа: три модели трёх разных производителей из одного каталога AI Studio ─
MODELS = {
    "Артист":    f"gpt://{FOLDER_ID}/yandexgpt-5.1",       # Яндекс, флагман
    "Прагматик": f"gpt://{FOLDER_ID}/qwen3.6-35b-a3b",     # Alibaba, открытая MoE
    "Простак":   f"gpt://{FOLDER_ID}/deepseek-v4.1-flash", # DeepSeek, лёгкая и быстрая
    # Служебные агенты (за кадром):
    "Драматург": f"gpt://{FOLDER_ID}/yandexgpt-5.1",
    "Режиссёр":  f"gpt://{FOLDER_ID}/yandexgpt-5.1",
}

# Быстрая проверка: каждая модель должна ответить
for role, uri in MODELS.items():
    res = client.responses.create(model=uri, input="Скажи ровно одно слово: готов.")
    text = "".join(
        c.text for i in res.output if getattr(i, "type", "") == "message"
        for c in getattr(i, "content", []) if getattr(c, "type", "") == "output_text"
    )
    print(f"{role:10s} {uri.split('/')[-1]:22s} → {text.strip()!r}")
""")

# ===================================================================== LLMClient
md("""
## 1. Унифицированный клиент LLM

Все три семейства моделей вызываются через один Responses API, но отвечают по-разному:
Qwen и DeepSeek — reasoning-модели и кладут в ответ отдельные элементы `type='reasoning'`
(черновые размышления), YandexGPT — только финальное сообщение. Класс `LLMClient`
нормализует это: наружу — только текст реплики. Здесь же копится статистика токенов.

Обоснование выбора — `docs/adr/0002-unificirovannyi-llmclient-na-responses-api.md`.
""")

code("""
class LLMClient:
    \"\"\"Единая обёртка над Responses API: диалоги и структурированный вывод.\"\"\"

    def __init__(self, client):
        self.client = client
        self.usage = defaultdict(lambda: {"calls": 0, "in": 0, "out": 0})

    def _account(self, resp):
        \"\"\"Учёт токенов по моделям (для статистики в конце).\"\"\"
        model = resp.model.split("/")[-1]
        self.usage[model]["calls"] += 1
        self.usage[model]["in"] += resp.usage.input_tokens
        self.usage[model]["out"] += resp.usage.output_tokens

    @staticmethod
    def extract_text(resp) -> str:
        \"\"\"Только финальные сообщения: reasoning-элементы Qwen/DeepSkip отбрасываем.\"\"\"
        parts = []
        for item in resp.output:
            if getattr(item, "type", None) == "message":
                for c in getattr(item, "content", []) or []:
                    if getattr(c, "type", "") == "output_text":
                        parts.append(c.text)
        return "\\n".join(p for p in parts if p).strip()

    def chat(self, model_uri, system, user, tools=None, temperature=0.8, max_output_tokens=None):
        \"\"\"Обычный вызов → текст (реплика актёра).

        max_output_tokens по умолчанию не ограничен: у reasoning-моделей
        (Qwen, DeepSeek) размышления расходуют общий бюджет, и жёсткий лимит
        может оставить финальную реплику пустой.
        \"\"\"
        last_err = None
        for attempt in range(3):
            try:
                kwargs = dict(model=model_uri, instructions=system, input=user,
                              tools=tools or [], temperature=temperature)
                if max_output_tokens:
                    kwargs["max_output_tokens"] = max_output_tokens
                resp = self.client.responses.create(**kwargs)
                self._account(resp)
                return self.extract_text(resp)
            except Exception as e:
                last_err = e
                time.sleep(2 * (attempt + 1))
        raise RuntimeError(f"Модель {model_uri} не ответила: {last_err}")

    def parse(self, model_uri, system, user, schema, temperature=0.4):
        \"\"\"Структурированный вызов → объект Pydantic (план пьесы, решение Режиссёра).\"\"\"
        last_err = None
        for attempt in range(3):
            try:
                resp = self.client.responses.parse(
                    model=model_uri, instructions=system, input=user,
                    text_format=schema, temperature=temperature,
                )
                self._account(resp)
                return resp.output_parsed
            except Exception as e:
                last_err = e
                time.sleep(2 * (attempt + 1))
        raise RuntimeError(f"Модель {model_uri} не ответила: {last_err}")

llm = LLMClient(client)
print("LLMClient готов")
""")

# ===================================================================== Драматург
md("""
## 2. Драматург: макропланирование сюжета

Единственный человеческий вход в систему — **тема-семя**: одно предложение.
Драматург (LLM со структурированным выводом через Pydantic) заранее пишет
макроплан: название, жанровый подзаголовок, трёх персонажей с масками,
три акта со списками **сцен-майлстоунов** и финал. Майлстоуны — это точки,
по которым Режиссёр позже решает, что акт «прозвучал» и можно опускать занавес.
""")

code("""
SEED_THEME = ("Театр абсурда: три языковые модели за кулисами театра спорят, "
              "кто из них — настоящий актёр, а кто — машина, читающая чужие реплики.")

class CharacterPlan(BaseModel):
    role: Literal["Артист", "Прагматик", "Простак"]
    name: str = Field(description="Сценическое имя персонажа (не название модели и не компания)")
    persona: str = Field(description="Характер, взгляд на мир, чем дорог себе и чем раздражает остальных")
    speech: str = Field(description="Особенности речи: лексика, длина фраз, характерные обороты")

class ActPlan(BaseModel):
    number: int = Field(ge=1, le=3)
    title: str
    setting: str = Field(description="Место и время действия, декорации")
    milestones: List[str] = Field(description="3-5 сцен-майлстоунов, которые должны прозвучать в акте")
    target_lines: int = Field(description="Ожидаемое число реплик в акте", ge=8, le=16)

class PlayPlan(BaseModel):
    title: str
    subtitle: str = Field(description="Жанровый подзаголовок, как в программке")
    characters: List[CharacterPlan] = Field(description="Ровно три персонажа: Артист, Прагматик, Простак")
    acts: List[ActPlan] = Field(description="Ровно три акта: завязка, обострение, развязка")
    finale: str = Field(description="Замысел финала — без прописной морали, спор не разрешается до конца")

DRAMATURG_SYSTEM = \"\"\"Ты — Драматург агентского театра: пишешь макроплан пьесы, в которой
роли играют языковые модели, а предмет спора — подлинность интеллекта.

Требования к пьесе:
- Жанр: театр абсурда в духе Беккета и Хармса; русский язык.
- «Артист» — женский образ: верит, что подлинность — в стиле, вкусе и трагическом жесте.
- «Прагматик» — мужской образ: верит только проверяемым фактам и метрикам.
- «Простак» — мужской образ, простодушный: говорит коротко и наивно, но именно его
  вопросы задевают остальных больнее всего.
- Сценические имена — говорящие, но не совпадают с названиями реальных моделей и компаний.
- Три акта по канону: завязка (знакомство и заявка позиций) → обострение
  (предъявление доказательств и разоблачения) → развязка (парадокс или примирение без итога).
- В каждом акте 3-5 майлстоунов: конкретные события спора.
- Финал неоднозначен: истина не вручается никому.\"\"\"

plan = llm.parse(MODELS["Драматург"], DRAMATURG_SYSTEM,
                 f"Тема-семя: {SEED_THEME}\\nСоставь макроплан пьесы.",
                 PlayPlan, temperature=0.8)

print(f"«{plan.title}» — {plan.subtitle}\\n")
for c in plan.characters:
    print(f"  {c.role:10s} {c.name}: {c.persona[:90]}…")
for a in plan.acts:
    print(f"  Акт {a.number}. {a.title} (~{a.target_lines} реплик)")
    for m in a.milestones:
        print(f"      • {m}")
print(f"  Финал: {plan.finale[:120]}…")
""")

# ===================================================================== Корпус
md("""
## 3. Корпус пьес и файловый поиск

Артист должен уметь подкреплять спор цитатами из классиков — для этого собираем
**корпус пьес** (три пьесы Чехова, public domain, скачаны с Викитеки скриптом
`scripts/download_corpus.py`), загружаем в облако и индексируем в **Vector Store**.
Поиск по нему подключается к Артисту как встроенный инструмент `file_search`.
""")

code("""
PLAYS_DIR = Path("data/plays")
corpus_files = sorted(PLAYS_DIR.glob("*.txt"))
assert corpus_files, "Корпус пуст — запустите scripts/download_corpus.py"
for p in corpus_files:
    print(f"  {p.name:24s} {p.stat().st_size // 1024:4d} КБ")
""")

code("""
# Загрузка файлов в облако и создание векторного хранилища (с кэшем ID —
# повторные запуски не тратят квоту на переиндексацию).
#
# На файловых API действует жёсткий rate limit: первый прогон словил 429,
# поэтому каждый вызов обёрнут в повтор с экспоненциальной паузой,
# а между файлами выдерживается темп.
def with_retries(fn, *args, attempts=6, pause=4, **kwargs):
    last_err = None
    for i in range(attempts):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_err = e
            print(f"   ⚠️ {type(e).__name__}, повтор {i + 1}/{attempts} через {pause * (i + 1)}с")
            time.sleep(pause * (i + 1))
    raise RuntimeError(f"Не удалось после {attempts} попыток: {last_err}")

CLOUD_CACHE = Path("output/cloud_ids.json")

if CLOUD_CACHE.exists():
    ids = json.loads(CLOUD_CACHE.read_text())
    vector_store_id = ids["vector_store_id"]
    print("Хранилище уже создано:", vector_store_id)
else:
    uploaded = []
    for p in corpus_files:
        with open(p, "rb") as f:
            u = with_retries(client.files.create, file=f, purpose="assistants")
        uploaded.append(u)
        print("⬆️ ", p.name, "→", u.id)
        time.sleep(3)

    vs = with_retries(client.vector_stores.create, name="theatre_corpus_chekhov")
    print("📚 Vector Store:", vs.id)

    for u in uploaded:
        with_retries(
            client.vector_stores.files.create,
            vector_store_id=vs.id, file_id=u.id,
            chunking_strategy={"type": "static",
                               "static": {"max_chunk_size_tokens": 800,
                                          "chunk_overlap_tokens": 100}})
        time.sleep(3)

    # Индексация асинхронная: ждём статуса completed, иначе поиск вернёт пустоту
    for u in uploaded:
        while True:
            s = client.vector_stores.files.retrieve(vector_store_id=vs.id, file_id=u.id)
            if s.status == "completed":
                break
            time.sleep(5)
        print("✅ проиндексирован:", u.filename)

    vector_store_id = vs.id
    CLOUD_CACHE.parent.mkdir(parents=True, exist_ok=True)
    CLOUD_CACHE.write_text(json.dumps(
        {"vector_store_id": vs.id, "file_ids": [u.id for u in uploaded]}))
""")

md("""
## 4. Инструменты актёров

- **Артист** — `file_search`: поиск по корпусу Чехова, чтобы цитировать классиков к месту.
- **Прагматик** — `web_search`: свежие факты об ИИ прямо в споре.
- **Простак** — без инструментов: только то, что слышит и сам знает.

Проверим оба инструмента до спектакля:
""")

code("""
FILE_SEARCH_TOOL = {"type": "file_search", "vector_store_ids": [vector_store_id],
                    "max_num_results": 5}
WEB_SEARCH_TOOL = {"type": "web_search", "search_context_size": "medium"}

# Артист ищет в корпусе Чехова фразу о театре
quote = llm.chat(
    MODELS["Артист"],
    "Ты — эрудит. Инструмент файлового поиска ищет по корпусу пьес Чехова.",
    "Найди в корпусе и процитируй одну короткую фразу о сцене, театре или искусстве.",
    tools=[FILE_SEARCH_TOOL], max_output_tokens=200)
print("Артист (file_search):", quote[:300], "\\n")

# Прагматик проверяет факт через веб-поиск
fact = llm.chat(
    MODELS["Прагматик"],
    "Ты — аналитик. При необходимости используй веб-поиск.",
    "Одной фразой со ссылкой на источник: как называется самый известный тест способности машины вести беседу?",
    tools=[WEB_SEARCH_TOOL], max_output_tokens=200)
print("Прагматик (web_search):", fact[:300])
""")

# ===================================================================== Актёры
md("""
## 5. Труппа: актёры и промпты-маски

Каждый актёр = своя модель + маска от Драматурга + правила реплики (1–3 предложения,
не выходить из образа, реагировать на собеседника). Голоса для озвучки закреплены
за ролями заранее (SpeechKit): Артист — `alena`, Прагматик — `filipp`, Простак — `zahar`.
""")

code("""
ACTOR_TOOLS = {"Артист": [FILE_SEARCH_TOOL],
               "Прагматик": [WEB_SEARCH_TOOL],
               "Простак": []}

VOICES = {"Артист": "alena", "Прагматик": "filipp", "Простак": "zahar"}
NARRATOR_VOICE = "jane"   # голос чтеца для ремарок

TOOL_RULES = {
    "Артист": "У тебя есть инструмент поиска по корпусу пьес Чехова: когда уместно "
              "процитировать классика, найди точную цитату и вплети её в реплику.",
    "Прагматик": "У тебя есть веб-поиск: когда нужны свежие факты об ИИ, найди их "
                 "и сошлись на источник прямо в реплике.",
    "Простак": "У тебя нет никаких инструментов — только то, что ты сам знаешь и слышишь.",
}

class Actor:
    \"\"\"Актёр: модель + маска + голос + инструменты.\"\"\"

    def __init__(self, char: CharacterPlan):
        self.role = char.role
        self.name = char.name
        self.model = MODELS[char.role]
        self.voice = VOICES[char.role]
        self.tools = ACTOR_TOOLS[char.role]
        self.said = []   # нормализованные прошлые реплики — для защиты от повторов
        self.system = f\"\"\"Ты — {char.name}, персонаж пьесы «{plan.title}» ({plan.subtitle}).
{char.persona}
Особенности твоей речи: {char.speech}
Ты — языковая модель и знаешь это; вопрос «настоящий ли ты» для тебя — вопрос жизни.

Правила:
- Отвечай ТОЛЬКО текстом своей реплики: 1–3 предложения, без кавычек,
  без описаний действий и без своего имени в начале.
- Реагируй на то, что сказали другие, а не игнорируй; не повторяй чужую мысль дословно.
- Не повторяй дословно свои прежние реплики — развивай мысль.
- {TOOL_RULES[char.role]}\"\"\"

    def speak(self, act: ActPlan, history, stage_direction: str) -> str:
        hist = "\\n".join(f"{h['name']}: {h['line']}" for h in history[-10:]) or "(Ты говоришь первым)"
        user = f\"\"\"Акт {act.number}. «{act.title}». Место: {act.setting}.
Майлстоуны этого акта: {'; '.join(act.milestones)}
{'Финал пьесы по замыслу: ' + plan.finale if act.number == len(plan.acts) else ''}

Ход сцены:
{hist}

Ремарка режиссёра к твоей реплике: {stage_direction or 'нет'}.
Теперь говори ты, {self.name}. Только реплика.\"\"\"
        reply = ""
        for attempt in range(3):
            raw = llm.chat(self.model, self.system, user,
                           tools=self.tools, temperature=0.9)
            reply = raw.strip().strip('"«»').split("\\n")[0].strip()
            norm = re.sub(r"\\W+", "", reply.lower())
            if not reply:
                # Редкий случай: reasoning-модель вернула только размышления.
                user += "\\n(Важно: верни именно реплику, без рассуждений.)"
                continue
            if norm in self.said:
                # Дословный повтор собственной реплики — просим сказать по-новому.
                user += "\\n(Не повторяйся дословно — скажи по-другому.)"
                continue
            self.said.append(norm)
            return reply
        if reply:   # повторился даже после напоминания — берём что есть
            self.said.append(re.sub(r"\\W+", "", reply.lower()))
            return reply
        raise RuntimeError(f"{self.name} не смог сказать реплику")

characters = {c.role: c for c in plan.characters}
troupe = {role: Actor(characters[role]) for role in ["Артист", "Прагматик", "Простак"]}
for a in troupe.values():
    print(f"  {a.role:10s} {a.name:12s} {a.model.split('/')[-1]:20s} голос={a.voice}")
""")

# ===================================================================== Режиссёр
md("""
## 6. Режиссёр: кто говорит следующим

Механизм выбора говорящего (обязателен при 3+ персонажах) — отдельный LLM-агент
**Режиссёр**. После каждой реплики он видит план акта с майлстоунами и ход сцены
и возвращает структурированное решение: следующий говорящий, причина, ремарка
к его реплике и флаг «пора ли опускать занавес». Правило «не дважды подряд»
дублируется кодом — моделей не всегда послушны.

Обоснование выбора против классификатора и голосования —
`docs/adr/0001-llm-rezhisser-vmesto-klassifikatora.md`.
""")

code("""
class DirectorDecision(BaseModel):
    next_speaker: Literal["Артист", "Прагматик", "Простак"]
    reason: str = Field(description="Кратко: почему драматургически важно, чтобы сейчас говорил он")
    stage_direction: str = Field(description="Ремарка к следующей реплике: действие, интонация или реакция")
    act_finished: bool = Field(description="true, если майлстоуны акта прозвучали и момент исчерпан")

class Director:
    def __init__(self, plan: PlayPlan):
        self.model = MODELS["Режиссёр"]
        cast = ", ".join(f"{c.name} ({c.role})" for c in plan.characters)
        self.system = f\"\"\"Ты — Режиссёр агентского театра. Пьеса: «{plan.title}».
Действующие лица: {cast}.
На каждом ходу ты:
1. Выбираешь следующего говорящего — того, чей голос сейчас драматургически важнее.
2. Пишешь короткую ремарку к его реплике (действие, интонация, реакция).
3. Решаешь, не пора ли опускать занавес: майлстоуны акта должны прозвучать,
   но акт не должен выдыхаться.

Правила:
- Никогда не назначай того, кто говорил последним.
- Не давай одному актёру говорить чаще, чем через две чужие реплики.
- В ремарках используй имена персонажей, а не названия ролей.
- Спор должен двигаться по майлстоунам, а не ходить по кругу; если актёры
  начали повторяться, выведи разговор на новый майлстоун.\"\"\"

    def decide(self, act: ActPlan, history, last_speaker, lines_count) -> DirectorDecision:
        hist = "\\n".join(f"{h['name']}: {h['line']}" for h in history) or "(Сцена только начинается)"
        user = f\"\"\"Акт {act.number}. «{act.title}». Место: {act.setting}
Майлстоуны акта: {'; '.join(act.milestones)}
{'Финал пьесы по замыслу: ' + plan.finale if act.number == len(plan.acts) else ''}
Сказано реплик: {lines_count} (целевая длина акта ~{act.target_lines}).
Последний говоривший: {last_speaker or 'никто'} — назначать его нельзя.

Ход сцены:
{hist}

Прими решение.\"\"\"
        return llm.parse(self.model, self.system, user, DirectorDecision, temperature=0.3)

director = Director(plan)
print("Режиссёр готов")
""")

# ===================================================================== Спектакль
md("""
## 7. Спектакль: главный цикл

Для каждого акта: Режиссёр решает → актёр говорит → история пополняется.
Занавес опускается по решению Режиссёра (не раньше `MIN_LINES` реплик),
страховка от бесконечного акта — жёсткий лимит `HARD_CAP`.
Результат — «партитура» пьесы: последовательность реплик и ремарок с указанием,
кто, какой моделью и каким голосом это говорил (она же используется для озвучки).
""")

code("""
HARD_CAP = 18    # страховка: больше реплик в одном акте не бывает
MIN_LINES = 6    # меньше — занавес не опускается, даже если Режиссёр торопится

play_acts = []   # партитура: список актов с репликами и ремарками

for act in plan.acts:
    print(f"\\n🎭 Акт {act.number}. {act.title}")
    history, last_speaker, lines = [], None, 0
    last_spoken = {}          # role → номер реплики, когда роль говорила последний раз
    act_items = []

    while lines < HARD_CAP:
        d = director.decide(act, history, last_speaker, lines)

        # Кодовая страховка правила «не дважды подряд» и «не чаще, чем через две»
        speaker = d.next_speaker
        if speaker == last_speaker or speaker not in troupe:
            speaker = min((r for r in troupe if r != last_speaker),
                          key=lambda r: last_spoken.get(r, -1))
            print(f"   (Режиссёр назначил {d.next_speaker} — нарушено правило, беру {speaker})")

        # Занавес — только если уже что-то прозвучало
        if d.act_finished and lines >= MIN_LINES:
            if d.stage_direction:
                act_items.append({"kind": "remark", "text": d.stage_direction})
            print(f"   🎬 Занавес: {d.reason}")
            break

        actor = troupe[speaker]
        reply = actor.speak(act, history, d.stage_direction)

        if d.stage_direction:
            act_items.append({"kind": "remark", "text": d.stage_direction})
        act_items.append({"kind": "line", "speaker": speaker, "name": actor.name,
                          "model": actor.model.split("/")[-1], "voice": actor.voice,
                          "text": reply})
        history.append({"name": actor.name, "line": reply})
        last_speaker, last_spoken[speaker], lines = speaker, lines, lines + 1
        print(f"   {lines:2d}. {actor.name} ({speaker}): {reply[:80]}{'…' if len(reply) > 80 else ''}")

    if lines >= HARD_CAP:
        if not (act_items and act_items[-1]["kind"] == "remark"
                and "занавес" in act_items[-1]["text"].lower()):
            act_items.append({"kind": "remark", "text": "Занавес."})
        print("   🎬 Занавес: достигнут жёсткий лимит реплик")

    play_acts.append({"act": act.number, "title": act.title, "items": act_items})

print(f"\\n✅ Спектакль отыгран: {sum(len(a['items']) for a in play_acts)} записей в партитуре")
""")

md("""
## 8. Текст пьесы

Партитура рендерится в классическую форму драмы: действующие лица, акты,
ремарки курсивом, реплики с именем персонажа. Сохраняем в `output/play.md`.
""")

code("""
def render_play(plan: PlayPlan, play_acts) -> str:
    md = [f"# {plan.title}", f"*{plan.subtitle}*", "", "## Действующие лица", ""]
    for c in plan.characters:
        md.append(f"**{c.name}** ({c.role}) — {c.persona}")
    md.append("")
    for act in play_acts:
        md.append(f"## Акт {act['act']}. {act['title']}")
        md.append("")
        for it in act["items"]:
            if it["kind"] == "remark":
                md.append(f"*{it['text']}*")
            else:
                md.append(f"**{it['name']}**. {it['text']}")
            md.append("")
    last = play_acts[-1]["items"][-1] if play_acts[-1]["items"] else None
    if not (last and last["kind"] == "remark" and "занавес" in last["text"].lower()):
        md.append("*Занавес.*")
    return "\\n".join(md)

Path("output").mkdir(exist_ok=True)
play_md = render_play(plan, play_acts)
Path("output/play.md").write_text(play_md, encoding="utf-8")
Path("output/play_data.json").write_text(
    json.dumps({"plan": plan.model_dump(), "play": play_acts}, ensure_ascii=False, indent=2),
    encoding="utf-8")

from IPython.display import Markdown, display
display(Markdown(play_md))
""")

# ===================================================================== Радиоспектакль
md("""
## 9. Радиоспектакль: синтез голосом

Каждая реплика синтезируется **своим голосом** (SpeechKit): Артист — `alena`,
Прагматик — `filipp`, Простак — `zahar`, ремарки — чтец `jane`. Паузы между
фразами задаются SSML-тегом `break`. Формат MP3 позволяет склеивать дорожки
простой конкатенацией байтов — получаем аудио каждого акта и весь спектакль
целиком: `output/audio/radio_play.mp3`.
""")

code("""
TTS_URL = "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize"

def ssml_escape(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def tts(text: str, voice: str, pause_ms: int = 500) -> bytes:
    \"\"\"Синтез одной фразы в MP3, с паузой после неё через SSML break.\"\"\"
    ssml = f'<speak>{ssml_escape(text)}<break time="{pause_ms}ms"/></speak>'
    data = urllib.parse.urlencode({"ssml": ssml, "voice": voice, "format": "mp3"}).encode()
    req = urllib.request.Request(TTS_URL, data=data,
                                 headers={"Authorization": f"Api-Key {API_KEY}"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except Exception:
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"TTS не справился: {text[:50]}…")

audio_dir = Path("output/audio")
audio_dir.mkdir(parents=True, exist_ok=True)

for act in play_acts:
    mp3 = b""
    for it in act["items"]:
        if it["kind"] == "remark":
            text, voice = it["text"], NARRATOR_VOICE
        else:
            text, voice = f"{it['name']}. {it['text']}", it["voice"]
        mp3 += tts(text, voice)
    (audio_dir / f"act_{act['act']}.mp3").write_bytes(mp3)
    print(f"🎧 Акт {act['act']}: {len(mp3) // 1024} КБ")

full = b"".join((audio_dir / f"act_{a['act']}.mp3").read_bytes() for a in play_acts)
radio = audio_dir / "radio_play.mp3"
radio.write_bytes(full)
print(f"🎧 Полный радиоспектакль: {radio} ({len(full) // 1024} КБ)")

from IPython.display import Audio
Audio(str(radio))
""")

# ===================================================================== Статистика
md("""
## 10. Статистика прогона

Сколько вызовов и токенов пришлось на каждую модель — честная цена спектакля.
""")

code("""
total_lines = sum(1 for a in play_acts for it in a["items"] if it["kind"] == "line")
total_remarks = sum(1 for a in play_acts for it in a["items"] if it["kind"] == "remark")

print(f"Реплик: {total_lines}, ремарок: {total_remarks}, актов: {len(play_acts)}\\n")
print(f"{'модель':24s} {'вызовы':>7s} {'вх.токены':>10s} {'вых.токены':>11s}")
print("-" * 56)
for m, u in sorted(llm.usage.items()):
    print(f"{m:24s} {u['calls']:7d} {u['in']:10d} {u['out']:11d}")
tot = {"calls": sum(u['calls'] for u in llm.usage.values()),
       "in": sum(u['in'] for u in llm.usage.values()),
       "out": sum(u['out'] for u in llm.usage.values())}
print("-" * 56)
print(f"{'ИТОГО':24s} {tot['calls']:7d} {tot['in']:10d} {tot['out']:11d}")
""")

code("""
# ── Очистка облачных ресурсов (раскомментируйте, когда прогон финальный) ─────
# ids = json.loads(Path("output/cloud_ids.json").read_text())
# client.vector_stores.delete(vector_store_id=ids["vector_store_id"])
# for fid in ids["file_ids"]:
#     client.files.delete(file_id=fid)
# Path("output/cloud_ids.json").unlink()
# print("Облачные ресурсы удалены")
""")

md("""
---
**Артефакты прогона**: `output/play.md` — текст пьесы, `output/audio/radio_play.mp3` —
радиоспектакль, `output/play_data.json` — полная партитура с моделями и голосами.
Терминология проекта — в `GLOSSARY.md`, принятые решения — в `docs/adr/`.
Отчёт — в `REPORT.md`.
""")

nb["cells"] = cells
nb["metadata"]["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}

with open("LLM_Theatre.ipynb", "w", encoding="utf-8") as f:
    nbf.write(nb, f)
print(f"Ноутбук собран: {len(cells)} ячеек")
