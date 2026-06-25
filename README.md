# FitFood — Telegram «общий стол» 🍽

Бот для **группового** чата: участники скидывают фото еды, а бот узнаёт, **кто** прислал,
распознаёт блюдо, прикидывает **калории/БЖУ**, отвечает коротким **эмпатичным разбором**
(что хорошего + одна мягкая идея, что улучшить) и вечером шлёт **сводку дня** по всем.

Главное отличие от обычных калорийных ботов — групповой формат с атрибуцией по людям и тон
**друга-нутрициолога**, а не счётчика-надзирателя. Оценки приблизительные (это ориентир для
привычек, не медицинский сервис).

## Как это работает

```
фото в группе
   └─► узнаём отправителя (tg_user_id)         services/attribution (repo)
   └─► ресайз ≤1024px + base64                 services/images
   └─► Gemma vision (alem.ai): еда? + КБЖУ + коуч  llm/client.analyze_photo
        ├─ не еда  → бот молчит
        └─ еда     → сохраняем приём + reply в тред
вечером (cron) ─► одна тёплая сводка дня на группу   llm/client.daily_summary
```

LLM-промпты (`bot/llm/prompts.py`) жёстко задают тон и **запреты**: никакого языка вины,
суточных лимитов, публичных сравнений людей; калории — всегда диапазоном.

## Установка

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows;  source .venv/bin/activate на *nix
pip install -r requirements.txt
copy .env.example .env            # cp на *nix — и заполните токены
```

### 1. Создать бота
1. В Telegram откройте **@BotFather** → `/newbot` → скопируйте токен в `TELEGRAM_BOT_TOKEN`.
2. **Обязательно** отключите Privacy Mode, иначе бот не увидит фото в группе:
   `@BotFather` → `/mybots` → ваш бот → **Bot Settings → Group Privacy → Turn off**.
3. (Опц.) `/setcommands`:
   ```
   help - справка
   goal - цель: lose|gain|maintain
   report - сводка за сегодня
   stop - перестать анализировать меня
   resume - снова анализировать
   delete - удалить мои данные
   ```

### 2. LLM (alem.ai / Gemma)
Используется OpenAI-совместимый эндпоинт `https://llm.alem.ai/v1`, модель `gemma4`
(поддерживает vision). Ключ — в `LLM_API_KEY`. Чтобы сменить провайдера, достаточно поменять
`LLM_BASE_URL` / `LLM_MODEL` на любой другой OpenAI-совместимый сервис.

### 3. Запуск
```bash
python -m bot
```
Добавьте бота в группу (после отключения Privacy Mode). При добавлении он пришлёт
приветствие с дисклеймером. Скиньте фото еды — получите разбор.

## Конфигурация (`.env`)

| Переменная | Назначение | По умолчанию |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | токен от @BotFather | — |
| `LLM_BASE_URL` | OpenAI-совместимый эндпоинт | `https://llm.alem.ai/v1` |
| `LLM_API_KEY` | ключ LLM | — |
| `LLM_MODEL` | модель (vision) | `gemma4` |
| `ALLOWED_CHAT_ID` | ограничить одной группой (пусто = любая) | пусто |
| `TZ` | таймзона сводки | `Asia/Almaty` |
| `DAILY_REPORT_HOUR` | час вечерней сводки (0-23) | `22` |
| `DB_PATH` | файл SQLite | `data/fitfood.db` |

## Команды

- `/help` — справка
- `/goal lose|gain|maintain` — личная цель (учитывается мягко)
- `/report` — прислать сводку прямо сейчас
- `/stop` / `/resume` — выключить/включить анализ своих фото
- `/delete` — удалить все свои данные

## Структура

```
bot/
├── __main__.py          # точка входа: bot + роутеры + планировщик
├── config.py            # настройки из .env (pydantic-settings)
├── db/                  # модели, сессия, запросы (SQLAlchemy async + SQLite)
├── services/            # ресайз фото, определение приёма пищи по времени
├── llm/                 # промпты + вызовы Gemma/alem.ai (vision-анализ, сводка)
├── handlers/            # фото, команды, онбординг в группе
└── scheduler/           # вечерняя сводка по cron (APScheduler)
```

## Деплой на сервер (always-on, supervisor)

Бот работает как **один long-polling процесс** под supervisor — самый лёгкий вариант
постоянной работы: ни веб-сервера, ни отдельной БД (только файл SQLite). Автоперезапуск,
ротация логов, после простоя backlog старых фото сбрасывается (`drop_pending_updates`),
а Telegram шлёт только нужные апдейты (`allowed_updates`).

Первый раз (на сервере, под root):
```bash
git clone https://github.com/Bernando0/fitnfood.git /var/www/fitnfood
cd /var/www/fitnfood
cp .env.example .env && nano .env          # вписать TELEGRAM_BOT_TOKEN и LLM_API_KEY
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
cp deploy/fitnfood.conf /etc/supervisor/conf.d/fitnfood.conf
supervisorctl reread && supervisorctl update    # стартует автоматически
supervisorctl status fitnfood
```

Последующие обновления — одной командой:
```bash
cd /var/www/fitnfood && bash update.sh
```

Логи: `bot.log` / `bot-error.log` в каталоге проекта (ротация 10MB×3).
Управление: `supervisorctl restart|stop|start fitnfood`.

## Что дальше (V2)

MVP реализует петлю «фото → разбор → вечерняя сводка». Заложено под расширение:
- **Триггерный коучинг**: детект паттернов (поздний сахар, фастфуд в спешке) и адресные
  микро-цели вместо запретов; вопрос «почему» (стресс/удобно/хотелось) кнопками, редко.
- **Личная аналитика в ЛС** (тренды, недельный отчёт) — чувствительное вне группы.
- **Inline-коррекция порции** (×0.5/×2), голос/текст-ввод, цели и геймификация.
- Монетизация: «один платит за весь чат» / one-time-unlock аналитики.

⚠️ Не является медицинским сервисом. Оценки калорий приблизительные (±15-20%).
