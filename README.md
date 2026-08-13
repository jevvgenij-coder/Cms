# Daily Compound Harvester CMS

## Описание
Daily Compound Harvester — модульная CMS-платформа для тестовой HFT-торговли с AI-движком, управлением юзерами и выбором стратегий.

## Структура проекта
- `backend/` — FastAPI backend
- `backend/cms_core.py` — центральная база данных и модель пользователя/плагина
- `backend/admin.py` — API для управления пользователями и плагинами
- `backend/bot.py` — базовый HFT-блок для старта/стопа
- `backend/hft_brain.py` — AI Brain + production HFT-модуль
- `backend/modules/` — стратегия торгового движка
- `frontend/` — простая UI-страница для подключения бирж
- `requirements.txt` — зависимости проекта
- `Dockerfile` / `Procfile` — конфигурация для развертывания
- `ADVANCED_TEST_REPORT.md` — сохраненные показатели тестирования

## Быстрый старт

```bash
pip install -r requirements.txt
python run.py
```

Откройте в браузере:

```
http://127.0.0.1:8000
```

## Vercel Speed Insights

Проект настроен для использования Vercel Speed Insights для мониторинга производительности веб-приложения.

### Настройка Speed Insights

1. Разверните проект на Vercel
2. В панели управления Vercel перейдите в раздел **Speed Insights**
3. Выберите ваш проект и нажмите кнопку **Enable**
4. Переменная окружения `VERCEL_ANALYTICS_ID` будет автоматически добавлена при развертывании

Speed Insights автоматически отслеживает:
- First Input Delay (FID)
- Largest Contentful Paint (LCP)
- Cumulative Layout Shift (CLS)
- Time to First Byte (TTFB)
- First Contentful Paint (FCP)

Метрики доступны в панели управления Vercel после развертывания и первых посещений пользователей.

## Облачный деплой

- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
- Главная точка входа: `run.py`

## Основные API

- `GET /api/report` — получить тестовый отчет `ADVANCED_TEST_REPORT.md`
- `GET /api/metrics` — получить текущее состояние бота и AI Brain
- `POST /api/strategy/execute` — выполнить стратегию на основе `news_sentiment`, `price_change`, `current_balance`
- `POST /api/bot/simulate` — запустить HFT-симуляцию
- `POST /api/user/connect-exchange` — подключить биржу через CCXT
- `GET /api/strategies` — каталог стратегий и доступ пользователя
- `POST /api/strategies/purchase` — добавить стратегию в покупки (для прототипа без платежного провайдера)
- `POST /api/strategies/activate` — активировать купленную стратегию
- `POST /api/chat` — чат с рекомендациями на основе сохраненной памяти тестов

Память обучения хранится в таблице `learning_memory`, поэтому результаты тестов и
запросы чата не теряются после перезапуска. После нескольких прибыльных тестов
система добавляет в каталог предложенную адаптивную стратегию; платные стратегии
сначала нужно приобрести и затем активировать. Это экспериментальный механизм
обучения, а не гарантия доходности.

## Годовая история для тестов

`GET /api/market/history?pair=BTC/USDT&exchange=binance` загружает реальные
дневные OHLCV-свечи из публичного API и сохраняет их в `market_history`.
Хранилище ограничено последними 365 днями: при обновлении новые дни добавляются,
а записи старше 365 дней удаляются. Backtest использует депозит из запроса
(например, `10`) и формирует сигнал только по текущей и предыдущим свечам;
следующая свеча используется исключительно для расчёта результата сделки.

Для анализа и обучения доступны закрытые свечи от 1 минуты:
`GET /api/market/history?pair=BTC/USDT&exchange=binance&timeframe=1m`.
Поддерживаются `1m`, `5m`, `15m`, `1h` и `1d`; последние 30 дней
внутридневных данных сохраняются в `market_candles`. Endpoint
`GET /api/market/signal` рассчитывает информационный сигнал на ближайшие часы
и следующий день по часовым и дневным данным. Чат также возвращает такой сигнал
по запросам о рынке, прогнозе или BTC/ETH; это не финансовая рекомендация.

История новостей загружается из публичного CoinDesk RSS и сохраняется локально:
`GET /api/market/news`. Анализ сентимента работает без платного AI-сервиса,
а новости с датой в будущем отбрасываются. В backtest сигнал формируется только
из свечей, доступных на момент сделки; следующая свеча используется только для
расчёта результата.

## Реальная торговля через API

Подключение хранится только в памяти процесса; API-секреты не записываются в базу данных.
По умолчанию все ордера работают в `dry_run`. Для отправки ордера на биржу необходимо:

1. Подключить API-ключ с правами **trade**, без права вывода средств.
2. Сначала проверить подключение через sandbox/testnet (`POST /api/exchange/connect` с `sandbox: true`).
3. Явно включить `LIVE_TRADING_ENABLED=true`.
4. Передать одновременно `live: true` и `confirm_live: true` в `POST /api/trading/order`.

Лимит номинала одной live-сделки задается `MAX_ORDER_NOTIONAL` и по умолчанию равен `1000`.

Основные endpoints:

- `POST /api/exchange/connect` — подключение и проверка ключей (`exchange_name`, `api_key`, `api_secret`, опционально `api_password`, `sandbox`)
- `GET /api/exchange/status` — состояние подключения
- `GET /api/exchange/balance` — баланс подключенного аккаунта
- `POST /api/trading/order` — market/limit ордер; без `live` только проверка параметров
- `DELETE /api/trading/order/<id>?symbol=BTC/USDT` — отмена ордера

Для live-ордера на любой поддерживаемой бирже без поля `amount` автоматически
используется минимальный размер, который сообщает биржа для выбранной пары
(включая минимальную стоимость ордера). Явно указанное количество ниже
биржевого минимума отклоняется.

Поддерживается подключение Pionex через CCXT. Ключи принимаются только на время
подключения и хранятся в памяти процесса; в базе данных сохраняется только
название биржи и маскированная подсказка ключа.

Для live-режима используйте отдельный production secret и HTTPS. Никогда не передавайте ключи
через URL и не включайте право вывода средств.

## Тестовые метрики

- Initial Capital: €100.00
- Final Capital: €109.20
- Total Net ROI: 9.20%
- Total Memory-Guided Trades: 444
- Win Rate: 93.9%
- Leverage: 4.0x
- Active Trading Knowledge: VSA, Order Flow, Liquidity Sweeps, Compound
