# Агентский театр

Лабораторная работа: многоагентная система для автоматического написания (симуляции) пьесы — три LLM-персонажа трёх разных производителей (YandexGPT, Qwen, DeepSeek) спорят, кто из них «настоящий актёр».

## Запуск

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

cp .env.sample .env        # вписать folder_id и api_key из Yandex AI Studio
python scripts/download_corpus.py   # корпус пьес Чехова (data/plays/)

jupyter lab LLM_Theatre.ipynb      # и выполнить все ячейки сверху вниз
```

## Артефакты

- `LLM_Theatre.ipynb` — вся система с пояснениями по принципам реализации;
- `output/play.md` — текст пьесы;
- `output/audio/radio_play.mp3` — радиоспектакль (SpeechKit, голос актёра на персонажа);
- `REPORT.md` — отчёт по шаблону задания;
- `GLOSSARY.md` — терминология проекта;
- `docs/adr/` — принятые архитектурные решения.
