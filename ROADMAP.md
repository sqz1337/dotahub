# DotaFIFA Dashboard Roadmap

Работаем по одному этапу за раз. После выполнения этапа Codex:

1. обновляет статус в этом файле;
2. сам запускает проверку из блока "Как проверить";
3. сообщает результат;
4. ждет ручного подтверждения от пользователя перед следующим этапом.

## Статусы

- `[done]` - выполнено и проверено Codex;
- `[review]` - выполнено Codex, ожидает ручной проверки пользователя;
- `[todo]` - еще не начато;
- `[blocked]` - есть препятствие, без решения дальше нельзя.

## Этап 0. Роадмап

Статус: `[done]`

Что сделать:

- Создать `ROADMAP.md`.
- Зафиксировать порядок разработки первой dashboard-страницы.
- Для каждого этапа описать критерий готовности и проверку.

Как проверить:

```bash
test -f ROADMAP.md && sed -n '1,220p' ROADMAP.md
```

Критерий готовности:

- Файл существует.
- В нем есть этапы разработки, проверки и правило перехода к следующему этапу.

Результат проверки:

- Файл создан.

## Этап 1. Подготовить frontend-скелет

Статус: `[done]`

Что сделать:

- Добавить Vite + React + TypeScript приложение для dashboard.
- Не ломать текущие `index.html` и `cards.html`.
- Настроить dev server.
- Добавить базовые npm scripts: `dev`, `build`, `preview` или их эквивалент.

Как проверить:

```bash
npm install
npm run build
npm run dev
```

Критерий готовности:

- Проект собирается без ошибок.
- Dev server открывает пустую или минимальную dashboard-страницу.
- Старые карточные HTML-страницы остаются в проекте.

Результат проверки:

- `npm install` выполнен успешно, уязвимостей не найдено.
- `npm run build` выполнен успешно.
- `npx vite --host 127.0.0.1 --port 5173` поднял dev server.
- `curl -I http://127.0.0.1:5173/dashboard/` вернул `HTTP/1.1 200 OK`.
- `index.html` и `cards.html` остались на месте.

## Этап 2. Сформировать dashboard data layer

Статус: `[done]`

Что сделать:

- Добавить генератор `data/dashboard.json` из SQLite.
- Использовать `data/opendota.sqlite` как source of truth.
- Собрать минимальные секции:
  - `players`;
  - `squadPulse`;
  - `leaderboard`;
  - `recentPartyGames`;
  - `squadMeta`;
  - `feed`.
- Не считать сложные мем-события на этом этапе, только базовые заглушки на реальных данных.

Как проверить:

```bash
python3 scripts/build_dashboard_data.py
python3 -m json.tool data/dashboard.json >/dev/null
```

Критерий готовности:

- `data/dashboard.json` создается без ошибок.
- В JSON есть все основные секции.
- Количество матчей/игроков совпадает с SQLite.

Результат проверки:

- `python3 scripts/build_dashboard_data.py` выполнен успешно.
- `python3 -m json.tool data/dashboard.json >/dev/null` выполнен успешно.
- В JSON есть `players`, `squadPulse`, `leaderboard`, `recentPartyGames`, `squadMeta`, `feed`, `summary`.
- Counts совпали с SQLite: `trackedPlayers=3`, `playerMatches=35`, `rawMatches=25`.

## Этап 3. Подключить справочники и изображения героев

Статус: `[done]`

Что сделать:

- Добавить загрузку/кеширование OpenDota constants для heroes, game modes, lobby types.
- Расшифровывать `hero_id` и `game_mode` в человекочитаемые имена.
- Подобрать источник иконок героев:
  - локальный кеш;
  - либо CDN Valve/OpenDota.
- Сделать fallback, если у героя нет изображения.

Как проверить:

```bash
python3 scripts/build_dashboard_data.py
python3 - <<'PY'
import json
data = json.load(open("data/dashboard.json"))
assert data["recentPartyGames"]
game = data["recentPartyGames"][0]
assert "modeName" in game
assert all("heroName" in hero for hero in game["heroes"])
print("dashboard constants ok")
PY
```

Критерий готовности:

- В dashboard JSON нет голых `hero_id` там, где UI должен показывать героя.
- Recent games содержат имена и изображения героев.
- Режимы игры показываются как `Turbo`, `All Pick`, `Single Draft` и т.п.

Результат проверки:

- Созданы кеши `data/constants/heroes.json`, `data/constants/game_mode.json`, `data/constants/lobby_type.json`.
- `npm run data:build` выполнен успешно.
- `python3 -m json.tool data/dashboard.json >/dev/null` выполнен успешно.
- Проверено, что recent games содержат `modeName`, `heroes[].heroName`, `heroes[].heroImage`.
- `npm run build` выполнен успешно после изменений.

## Этап 4. Сверстать первый экран dashboard

Статус: `[review]`

Что сделать:

- Сверстать dashboard по `data/dashboard_draft.png`.
- Реализовать основные блоки:
  - top navigation;
  - season selector как статичный контрол;
  - squad pulse;
  - friends leaderboard;
  - recent party games;
  - squad meta;
  - squad feed.
- Подключить данные из `data/dashboard.json`.
- Сохранить темный стиль, красный акцент и плотную dashboard-композицию из макета.

Как проверить:

```bash
npm run build
npm run dev
```

Дополнительная визуальная проверка:

- открыть dashboard в браузере;
- проверить desktop viewport примерно `1728x969`;
- проверить mobile/tablet viewport;
- убедиться, что текст не налезает на соседние элементы.

Критерий готовности:

- Страница визуально похожа на макет.
- Все блоки заполнены реальными данными из JSON.
- UI не разваливается на desktop и narrow viewport.

Результат проверки:

- `npm run build` выполнен успешно.
- Dev server поднят на `http://127.0.0.1:5173/dashboard/`.
- `curl -I http://127.0.0.1:5173/dashboard/` вернул `HTTP/1.1 200 OK`.
- Проверен desktop viewport `1728x969`: горизонтального overflow нет, 4 dashboard-панели отображаются, изображения загружены.
- Проверен mobile viewport `390x844`: горизонтального overflow нет, основные секции отображаются, изображения загружены.
- Browser console: ошибок и warning-сообщений нет.

Результат доработки после ручной проверки:

- Recent party games теперь показывает аватарки игроков из матча, а не иконки героев.
- Layout переведен на `100svh`: на `1440x900`, `1470x956` и `1920x1080` общего vertical/horizontal scroll нет.
- `Squad Feed` скроллится внутри своего блока, когда события не помещаются.
- Устранен overflow в leaderboard и recent party games.
- Повторно выполнен `npm run build`, сборка успешна.

Результат второй доработки (приведение к макету `data/dashboard_draft.png`):

- Добавлен Squad Pulse тикер под шапкой: рекорд сезона, доля Turbo, Best duo (вычисляется по совместным матчам), Cursed pick.
- Возвращена красная идентичность: активный пункт навигации с красным подчеркиванием, статичный селектор Season 1, красные маркеры заголовков панелей.
- В Recent Games колонка Heroes заменена на Highlight: лучший игрок матча, его герой, KDA и корона MVP при победе.
- Squad Meta дополнена строкой Fastest Win.
- Squad Feed получил цветные иконки типов событий (crown/skull/eye) и анимацию появления.
- Панели Leaderboard и Recent Games получили футеры "View all ...".
- Заголовки и крупные цифры переведены на Barlow Condensed.
- Проверены viewport 1728x969, 1440x900 и 375x812: горизонтального overflow нет, добавлен брейкпоинт 1580px.
- `npm run build` выполнен успешно, ошибок в browser console нет.

## Страница Players (вне исходного роадмапа)

Статус: `[review]`

Результат итерации "витрина карточек":

- Исправлено смещение статов на карточках: `statsGap` из пресета (px для эталонной карты 424px из `cards.html`) теперь масштабируется от фактической ширины карты.
- Имя на карточке возвращено к пресетной типографике (`nameSize`, `nameSpacing`, шрифт из `--font-family`), как в `cards.html`.
- Шапка сайта теперь лежит поверх фонового арта с градиентным затемнением - страница стала цельной.
- Новый hero: красный kicker "Kastems Hub · Season 1" + крупный заголовок с золотым градиентом.
- Карточки отсортированы по OVR, до 10 штук (5 в ряд, 2 ряда).
- WOW-эффекты: 3D-tilt за курсором + световой блик (маскируется формой карты), отражения карточек на полу (`-webkit-box-reflect`), staggered-появление карт, медленный световой sweep по сцене. Всё отключается при `prefers-reduced-motion`.
- Переключатель "All time" помечен бейджем `soon` и отключен до появления агрегации за все время.
- Карточки получили `role="button"` и курсор - клик в профиль игрока будет следующим этапом.
- Проверено: 1728x969, 1470x956, 375x812; `npm run build` успешен; ошибок в консоли нет.

## Этап 5. Реализовать генератор мем-событий

Статус: `[todo]`

Что сделать:

- Создать правила для `feed` на основе parsed match JSON:
  - много смертей;
  - streak/MVP;
  - rampage/multikill;
  - bad buyback;
  - stomp/comeback/throw;
  - warding/support impact;
  - cursed pick.
- Каждому событию дать:
  - `type`;
  - `severity`;
  - `player`;
  - `matchId`;
  - `message`;
  - `icon`;
  - `createdAt`.

Как проверить:

```bash
python3 scripts/build_dashboard_data.py
python3 - <<'PY'
import json
data = json.load(open("data/dashboard.json"))
assert data["feed"]
for event in data["feed"]:
    assert event["message"]
    assert event["matchId"]
print(f"feed events: {len(data['feed'])}")
PY
```

Критерий готовности:

- Лента состоит из событий, полученных из реальных матчей.
- У каждого события есть ссылка на матч/игрока.
- Сообщения выглядят как мемная лента, а не сухая статистика.

## Этап 6. Добавить фильтры и состояния

Статус: `[todo]`

Что сделать:

- Добавить фильтр режима игры: `All`, `Turbo`, `Ranked`, `Other`.
- Добавить фильтр периода/сезона, пока статичный `Season 1`.
- Добавить пустые состояния для случаев, когда данных нет.
- Добавить loading/error состояния для загрузки JSON.

Как проверить:

```bash
npm run build
```

Ручная проверка:

- переключить фильтр режима;
- убедиться, что leaderboard/recent games/meta/feed меняются согласованно;
- проверить состояние без матчей через временный пустой JSON fixture.

Критерий готовности:

- Фильтры меняют данные без перезагрузки страницы.
- Нет JS-ошибок в консоли.
- Пустые состояния выглядят намеренно, а не как поломка.

## Этап 7. Финальная проверка первой версии

Статус: `[todo]`

Что сделать:

- Прогнать полный data refresh.
- Пересобрать dashboard JSON.
- Собрать frontend production build.
- Проверить страницу в браузере.
- Зафиксировать команды запуска для пользователя.

Как проверить:

```bash
python3 scripts/ingest_opendota.py
python3 scripts/build_dashboard_data.py
npm run build
npm run dev
```

Критерий готовности:

- Dashboard открывается локально.
- Данные обновляются из OpenDota -> SQLite -> dashboard JSON -> UI.
- Визуально первая версия готова для просмотра и обсуждения следующей итерации.
