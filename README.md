# KASTEMS HUB

KASTEMS HUB — локальный сайт со статистикой небольшой группы игроков Dota 2. Данные загружаются из OpenDota в SQLite, преобразуются в `data/dashboard.json` и отображаются React/Vite-приложением в виде Dashboard, коллекции карточек и профилей игроков.

## Быстрый старт

Требования:

- Node.js 20+ и npm;
- Python 3, доступный как `python`, `py -3` или `python3`;
- публичные Steam-профили и история матчей у отслеживаемых игроков.

Установка:

```bash
npm install
```

Локальная разработка запускается в двух терминалах:

```bash
npm run dev:auth
```

```bash
npm run dev
```

- Vite: `http://127.0.0.1:5173`
- auth/API server: `http://127.0.0.1:3001`
- корень сайта перенаправляется на `/dashboard/`

Production-проверка:

```bash
npm run build
npm start
```

## Маршруты

- `/dashboard/` — сводка, сезонный leaderboard, последние общие игры и feed.
- `/players/` — карточки игроков, переключение This Season / All Time и сортировка OVR / Rank.
- `/profile/<accountId>` — профиль конкретного игрока.
- `/profile/` — перенаправление на профиль авторизованного игрока или профиль по умолчанию.

Файлы `index.html` и `cards.html` в корне — старые референсы/редактор карточек. Они не являются публичными страницами сайта.

## Основные команды

```bash
npm run dev             # Vite frontend
npm run dev:auth        # Node auth/API server с watch
npm run build           # TypeScript + production Vite build
npm run start           # server.mjs, раздаёт dist и API
npm run data:build      # пересобрать dashboard.json из текущей SQLite
npm run data:refresh    # лёгкое обновление последних матчей
npm run data:refresh_full # матчи + profile + All Time агрегаты
```

`scripts/data_tasks.mjs` сам находит Python 3 и последовательно запускает нужные Python-скрипты без shell-зависимости от `&&`.

## Обновление данных

### Обычный refresh

```bash
npm run data:refresh
```

Для каждого игрока выполняется только `recentMatches`. Из ответа сначала удаляются матчи до начала сезона, затем сохраняется максимум 20 последних сезонных игр. Детали `/matches/<matchId>` загружаются только для новых или неполных матчей.

### Полный refresh

```bash
npm run data:refresh_full
```

Дополнительно обновляет endpoints, необходимые для профиля и All Time-карточек:

- `profile`
- `wl`
- `wl?game_mode=23`
- `totals`
- `totals?game_mode=23`
- `counts`

Endpoints `heroes`, `peers`, `pros`, `rankings`, `ratings`, `wardmap` и `wordcloud` приложением сейчас не используются и при refresh не запрашиваются.

### Ограничение OpenDota

Запросы идут последовательно с паузой. При HTTP 429 скрипт ждёт `Retry-After` или 65 секунд и повторяет запрос. Если хотя бы один критический запрос не выполнен, ingest завершается с ненулевым кодом: `dashboard.json` не пересобирается и очистка базы не запускается.

## Сезон и хранение матчей

Текущий сезон начинается `2026-07-01 00:00 UTC`.

Дата задана в двух местах, и при старте нового сезона необходимо изменить оба:

- `data/player-ids.json` → `since`
- `scripts/build_dashboard_data.py` → `SEASON_START_AT`

Тяжёлые подробности матчей хранятся только для объединения последних 20 сезонных игр каждого игрока — максимум 20 × количество игроков, обычно меньше из-за совместных матчей.

При этом нельзя удалять лёгкую сезонную историю:

- `player_match_index` хранит индекс всех увиденных сезонных игр;
- `recent_player_matches` хранит rolling window последних 20;
- `raw_matches` и `match_players` содержат подробности только recent-window;
- `season_mmr_events` хранит зафиксированные impact/MMR-события всего сезона;
- `recent_sync_state` подтверждает успешную синхронизацию каждого игрока.

Очистка подробностей выполняется только после записи MMR-ledger и успешной recent-синхронизации всех отслеживаемых игроков. Матчи до начала сезона удаляются из индекса, recent-кеша, подробностей и MMR-ledger.

## MMR

- Каждый игрок начинает сезон с `3000 MMR`.
- Учитываются Turbo и Ranked.
- Unranked отображает Win/Loss, но MMR не меняет.
- Impact рассчитывается внутри конкретного матча по процентилям десяти игроков и зависит от роли.
- Уже записанное MMR-событие неизменно: новый матч не пересчитывает задним числом impact старых игр.

Нормализованный impact:

```text
x = clamp((impactScore - 50) / 35, -1, 1)
i = sign(x) * abs(x) ^ 1.25
```

Изменение рейтинга:

```text
Turbo win:  round( 13 + 7i)
Turbo loss: round(-13 + 7i)
Ranked win: round(30 + (i >= 0 ? 30 : 20) * i)
Ranked loss: round(-20 + 10i)
```

Impact использует оси IMP, FRM, FGT, SUR, OBJ и UTL. Вес осей зависит от роли Carry / Mid / Offlane / Support.

## Карточки и статистика

- This Season использует максимум 20 последних сезонных матчей.
- All Time строится из `wl`, `totals`, Turbo-вариантов и `counts`.
- Turbo GPM приводится к обычному темпу делением на `2.4`.
- Turbo XPM делится на `3.0`.
- Turbo Last Hits для FRM приводится коэффициентом `0.75`.
- Play Style radar визуально снимает встроенный нижний порог FIFA-подобных рейтингов, поэтому FRM 60–70 не выглядит как высокий процент шкалы.

Steam avatar из `dashboard.json` является основным источником изображения карточки. Локальный `/assets/players/<accountId>.jpg` используется только как fallback.

## Ранги Friends Leaderboard

Leaderboard сортируется по сезонному MMR. Медаль рассчитывается по MMR, а не по реальному OpenDota rank tier:

- ниже 2310 — Archon I;
- Archon: 2310 / 2450 / 2610 / 2770 / 2930;
- Legend: 3080 / 3230 / 3390 / 3540 / 3700;
- Ancient: 3850 / 4000 / 4150 / 4300 / 4460;
- Divine: 4620 / 4820 / 5020 / 5220 / 5420;
- выше 5620 — Immortal.

Под ником показывается вычисленная роль карточки и KDA.

## Игроки и ручные настройки

- Список отслеживаемых Steam Account ID: `data/player-ids.json`.
- Ручная роль: `data/player-role-overrides.json` (`CRY`, `MID`, `OFF`, `SUP`, `FLX`).
- Редактируемые поля профиля: `data/profile-overrides.json`.

После добавления нового игрока нужен `npm run data:refresh_full`. При удалении игрока необходимо удалить его не только из `player-ids.json`, но и из SQLite-таблиц `tracked_players`, `raw_player_endpoints`, `player_match_index`, `recent_player_matches`, `recent_sync_state` и `season_mmr_events`, затем выполнить `npm run data:build`.

## Steam-аутентификация

`server.mjs` реализует Steam OpenID без стороннего backend-фреймворка. Войти могут только игроки, присутствующие в `data/dashboard.json`.

Переменные окружения описаны в `.env.example`:

```env
PUBLIC_ORIGIN=https://your-domain.example
AUTH_SESSION_SECRET=replace-with-a-long-random-secret
```

В production `AUTH_SESSION_SECRET` обязателен. Callback Steam должен возвращаться на тот же origin, что указан в `PUBLIC_ORIGIN`.

## Фоны

Переключатель в Header выбирает Red, Green, Purple, Gold или отсутствие фона. Выбор хранится в `localStorage` под ключом `kastems-hub-background` и применяется ко всем страницам.

Исходные изображения находятся в `assets/backgrounds/`, конфигурация — в `dashboard/src/backgrounds.ts`.

## Структура проекта

```text
dashboard/src/
  App.tsx                    выбор страницы по pathname
  main.tsx                   React entrypoint
  data.ts                    типизированный импорт dashboard.json
  auth/useAuthUser.ts        состояние Steam-сессии
  components/                Header, Panel, BackgroundPicker
  pages/                     DashboardPage, PlayersPage, ProfilePage
  styles/                    foundation/dashboard/players/profile/responsive
  utils/player.ts            карточки, ранги, роли, форматирование

scripts/
  ingest_opendota.py         OpenDota → SQLite
  build_dashboard_data.py    SQLite → dashboard.json, MMR и агрегаты
  data_tasks.mjs             кроссплатформенный запуск Python-команд

data/
  opendota.sqlite            исходные и производные данные
  dashboard.json             frontend payload
  player-ids.json            состав и дата сезона
  player-role-overrides.json ручные роли
  profile-overrides.json     редактируемые поля профилей

server.mjs                   Steam OpenID, profile API, static dist server
vite.config.ts               multi-page build, redirects и profile rewrite
```

## Автоматическое обновление данных

GitHub Actions workflow `.github/workflows/data-refresh.yml` обновляет OpenDota-данные и публикует их через обычный Vercel Git deployment:

- `data:refresh` — каждый час в `:17`, кроме полуночи;
- `data:refresh_full` — ежедневно в `00:00 Europe/Moscow`;
- ручной запуск доступен через **Actions → Refresh Dota data → Run workflow**;
- одна concurrency-группа не позволяет hourly и daily refresh изменять SQLite одновременно;
- если данные изменились, workflow коммитит только `data/opendota.sqlite`, `data/dashboard.json` и `data/matches.json` в `main`; Vercel автоматически создаёт новый production deployment.

Опциональный repository secret `OPENDOTA_API_KEY` используется автоматически. Без него workflow работает через публичный OpenDota API и его стандартные ограничения.

## Важные инварианты

Перед завершением изменений желательно проверить:

```bash
python -m py_compile scripts/ingest_opendota.py scripts/build_dashboard_data.py
node --check scripts/data_tasks.mjs
npm run data:build
npm run build
git diff --check
```

Дополнительно:

- в данных не должно быть матчей раньше `SEASON_START_AT`;
- у каждого игрока не больше 20 записей в `recent_player_matches`;
- каждый рейтинговый сезонный матч должен иметь запись в `season_mmr_events` до очистки подробностей;
- `raw_matches` должен совпадать с объединением recent-window;
- профиль рейтингового матча должен иметь `mmrAfter` и `mmrChange`;
- изменения стилей проверяются на Dashboard, Players и Profile, включая отсутствие горизонтального overflow.
