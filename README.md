# Internal CRM API — Задание Б (Software Developer)

REST API для внутренней CRM: учёт организаций, фиксация результатов звонков и назначение/перенос/отмена встреч с соблюдением рабочих часов `Asia/Almaty` и контролем пересечений.

## Стек

- Python 3.12+
- FastAPI + Pydantic v2
- SQLite (`sqlite3`, схема в `schema.sql`, автоинициализация и seed-данные менеджеров при старте)
- Стандартный модуль `zoneinfo` (`ZoneInfo("Asia/Almaty")`) + `tzdata`
- `pytest` + `httpx` для автотестов
- Docker / Docker Compose

## Быстрый запуск

### Вариант 1 — через Docker Compose (одной командой)

```bash
docker compose up --build
```

API поднимется на `http://localhost:8000` (Swagger UI доступен по адресу `http://localhost:8000/docs`).

### Вариант 2 — локально без Docker

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Переменные окружения

| Переменная | По умолчанию | Описание |
|---|---|---|
| `DATABASE_PATH` | `./crm.db` (в Docker: `/app/data/crm.db`) | Путь к файлу SQLite |

При первом запуске автоматически выполняется `schema.sql` и добавляются 3 тестовых менеджера (`id`: `1`, `2`, `3`), чтобы API можно было сразу проверять через `curl` или Swagger.

## Запуск автотестов

```bash
source .venv/bin/activate
pytest -v
```

Или без активации окружения:

```bash
.venv/bin/pytest -v
```

## Примеры запросов

- `examples.http` — коллекция запросов для IDE (VS Code REST Client / PyCharm HTTP Client).
- `requests.sh` — готовый bash-скрипт с `curl`-запросами:

```bash
chmod +x requests.sh
./requests.sh
```

## Эндпоинты

| Метод | Путь | Назначение |
|---|---|---|
| `GET` | `/health` | Проверка работоспособности |
| `GET` | `/managers` | Список менеджеров (seed-данные) |
| `POST` | `/companies` | Создать организацию (`name`, `bin` 12 цифр, `phone`) |
| `GET` | `/companies?status=&limit=20&offset=0` | Список организаций с фильтрацией по статусу и пагинацией |
| `POST` | `/meetings` | Назначить встречу (60 минут, пн–пт 09:00–18:00 `Asia/Almaty`) |
| `PATCH` | `/meetings/{id}` | Перенести (`scheduled_at`) или изменить статус (`cancelled` / `completed`) |
| `POST` | `/calls` | Зафиксировать результат звонка (`no_answer`, `refused`, `meeting_set`) |
| `GET` | `/managers/{id}/schedule?date=YYYY-MM-DD` | Расписание менеджера на календарный день `Asia/Almaty` (ответ в UTC) |

## Принятые решения и трактовка требований

1. **Связка `POST /calls` и `POST /meetings` для результата `meeting_set`:** в ТЗ указано, что звонок с результатом `meeting_set` без созданной встречи — ошибка валидации, но порядок вызовов не зафиксирован. Принято решение: сначала создаётся встреча через `POST /meetings`, затем в `POST /calls` передаётся `meeting_id` существующей активной (`status == "scheduled"`) встречи этой организации. Если `meeting_id` отсутствует, не существует, принадлежит другой компании или встреча отменена — возвращается `422`.
2. **Часовые пояса:** API принимает только timezone-aware ISO 8601 (`Z` или смещение), приводит время к UTC и всегда отдаёт даты в UTC (`...Z`). Naive datetime без таймзоны отклоняется с `422`. Проверки рабочих дней (пн–пт) и рабочего окна (`09:00–18:00` целиком, последний допустимый старт — `17:00`) выполняются в `Asia/Almaty`.
3. **Перенос встреч:** при `PATCH /meetings/{id}` с новым `scheduled_at` применяются те же проверки рабочего времени и пересечений (исключая саму встречу `id`). Поле `original_scheduled_at` не перезаписывается, а `reschedule_count` увеличивается на 1.
4. **Что сделано / что не делалось осознанно:** реализованы все эндпоинты, бизнес-правила, схема БД, Docker-сборка, 8 автотестов и примеры запросов. Авторизация, роли, очереди, уведомления и кэш не добавлялись в соответствии с ТЗ; перевод прошедших встреч в `completed` оставлен на ручной `PATCH`, без фонового воркера.
