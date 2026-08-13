from datetime import datetime
import os
from pathlib import Path

from flask import Flask, render_template, request, session, redirect, url_for
import sqlite3
import hashlib
import yaml
import ccxt
import math
import requests

from backend.bot import HFTBot
from backend.cms_core import CMSEngine
from backend.modules.strategy_manager import StrategyManager
from backend.exchange_service import ExchangeService
from backend.market_history import ensure_table, load_history, refresh_history

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'development-only-change-me')

BASE_DIR = Path(__file__).resolve().parent
DATABASE = str(BASE_DIR / 'cms_v12.db')
cmse = CMSEngine()
bot = HFTBot()
strategy_manager = StrategyManager(config_path='backend/config.yaml')
exchange_service = ExchangeService()

EXCHANGES = ['binance', 'kraken', 'okx', 'bybit', 'bitfinex', 'pionex']
WALLETS = ['Metamask', 'Trust Wallet', 'Coinbase', 'Phantom', 'Ledger']
TRADING_PAIRS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT']
INTERNAL_CURRENCY = 'CMS Credits (CMSC)'
CRYPTO_PAYOUT_ASSETS = ('USDT', 'USDC', 'BTC')
CARD_PAYOUT_SERVICES = ('Stripe', 'PayPal', 'Adyen', 'Revolut Business')
CMSC_EUR_RATE = 1.0
CMSC_PAYMENT_CURRENCIES = ('EUR', 'USD', 'GBP', 'RUB', 'CHF')

DEFAULT_PLUGINS = [
    {'name': 'Sentiment Analyzer', 'price': 29.99, 'description': 'AI-модуль для анализа новостей и торговых сигналов.'},
    {'name': 'Auto-Rebalancer', 'price': 39.99, 'description': 'Автоматическая ребалансировка портфеля по стратегии.'},
    {'name': 'Risk Guard', 'price': 19.99, 'description': 'Защита позиций и контроль риска по правилам.'},
]


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def init_db():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE,
                        email TEXT UNIQUE,
                        password TEXT,
                        role TEXT DEFAULT 'user',
                        theme TEXT DEFAULT 'light')''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS wallets (
                        user_id INTEGER PRIMARY KEY,
                        balance REAL,
                        provider TEXT,
                        address TEXT,
                        exchange_provider TEXT,
                        exchange_address TEXT,
                        telegram TEXT,
                        telegram_token TEXT,
                        credits REAL DEFAULT 0)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS plugin_purchases (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        plugin_name TEXT,
                        purchased_at TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS trade_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        mode TEXT NOT NULL,
                        pair TEXT NOT NULL,
                        strategy TEXT NOT NULL,
                        signal INTEGER NOT NULL,
                        price REAL,
                        amount REAL,
                        pnl REAL NOT NULL,
                        balance REAL NOT NULL,
                        created_at TEXT NOT NULL)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS admin_payout_settings (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        crypto_asset TEXT NOT NULL DEFAULT 'USDT',
                        crypto_network TEXT,
                        crypto_address TEXT,
                        card_provider TEXT NOT NULL DEFAULT 'Stripe',
                        card_recipient TEXT,
                        card_currency TEXT NOT NULL DEFAULT 'EUR',
                        updated_at TEXT NOT NULL)''')
    ensure_table(DATABASE)
    conn.commit()
    cursor.execute("PRAGMA table_info('users')")
    user_columns = [row[1] for row in cursor.fetchall()]
    if 'role' not in user_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user'")
    if 'theme' not in user_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN theme TEXT DEFAULT 'light'")
    cursor.execute("PRAGMA table_info('wallets')")
    columns = [row[1] for row in cursor.fetchall()]
    for column, definition in (
        ('provider', 'TEXT'),
        ('address', 'TEXT'),
        ('telegram', 'TEXT'),
        ('telegram_token', 'TEXT'),
        ('credits', 'REAL DEFAULT 0'),
    ):
        if column not in columns:
            cursor.execute(f'ALTER TABLE wallets ADD COLUMN {column} {definition}')
    if 'exchange_provider' not in columns:
        cursor.execute('ALTER TABLE wallets ADD COLUMN exchange_provider TEXT')
    if 'exchange_address' not in columns:
        cursor.execute('ALTER TABLE wallets ADD COLUMN exchange_address TEXT')
    conn.commit()
    cursor.execute('SELECT id FROM users WHERE username = ?', ('admin',))
    if cursor.fetchone() is None:
        password = hash_password('admin123')
        cursor.execute('INSERT INTO users (username, email, password, role) VALUES (?, ?, ?, ?)',
                       ('admin', 'admin@cms.local', password, 'admin'))
        admin_id = cursor.lastrowid
        cursor.execute('INSERT OR IGNORE INTO wallets (user_id, balance, credits) VALUES (?, ?, ?)', (admin_id, 1000.0, 500.0))
        conn.commit()
    conn.close()


def get_admin_payout_settings():
    conn = sqlite3.connect(DATABASE)
    row = conn.execute(
        '''SELECT crypto_asset, crypto_network, crypto_address, card_provider,
                  card_recipient, card_currency
           FROM admin_payout_settings WHERE id = 1'''
    ).fetchone()
    conn.close()
    if row is None:
        return {
            'crypto_asset': 'USDT',
            'crypto_network': '',
            'crypto_address': '',
            'card_provider': 'Stripe',
            'card_recipient': '',
            'card_currency': 'EUR',
        }
    return {
        'crypto_asset': row[0],
        'crypto_network': row[1] or '',
        'crypto_address': row[2] or '',
        'card_provider': row[3],
        'card_recipient': row[4] or '',
        'card_currency': row[5],
    }


def save_admin_payout_settings(settings):
    conn = sqlite3.connect(DATABASE)
    conn.execute(
        '''INSERT INTO admin_payout_settings
           (id, crypto_asset, crypto_network, crypto_address, card_provider,
            card_recipient, card_currency, updated_at)
           VALUES (1, ?, ?, ?, ?, ?, 'EUR', ?)
           ON CONFLICT(id) DO UPDATE SET
             crypto_asset=excluded.crypto_asset,
             crypto_network=excluded.crypto_network,
             crypto_address=excluded.crypto_address,
             card_provider=excluded.card_provider,
             card_recipient=excluded.card_recipient,
             card_currency='EUR',
             updated_at=excluded.updated_at''',
        (
            settings['crypto_asset'],
            settings['crypto_network'],
            settings['crypto_address'],
            settings['card_provider'],
            settings['card_recipient'],
            datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def load_plugins():
    if not cmse.list_plugins():
        for plugin in DEFAULT_PLUGINS:
            cmse.create_plugin(plugin['name'], plugin['price'], plugin['description'])


def cmsc_price_in_currency(amount, currency):
    """Return the payment quote for CMSC, pegged 1:1 to EUR."""
    currency = (currency or 'EUR').upper()
    if currency not in CMSC_PAYMENT_CURRENCIES:
        raise ValueError('Непод��ерживаемая валюта оплаты.')
    if not math.isfinite(amount) or amount <= 0:
        raise ValueError('Введите положительное количество CMSC.')
    if currency == 'EUR':
        return amount * CMSC_EUR_RATE
    try:
        response = requests.get(
            'https://api.frankfurter.app/latest',
            params={'from': 'EUR', 'to': currency},
            timeout=5,
        )
        response.raise_for_status()
        rate = float(response.json()['rates'][currency])
        if not math.isfinite(rate) or rate <= 0:
            raise ValueError
    except (requests.RequestException, KeyError, TypeError, ValueError) as exc:
        raise ValueError('Не удалось получить актуальный курс валюты.') from exc
    return amount * rate


def get_user(user_id):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT id, username, email, role, COALESCE(theme, "light") FROM users WHERE id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row


def get_wallet(user_id):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT balance, provider, address, exchange_provider, exchange_address, telegram, telegram_token, COALESCE(credits, 0) FROM wallets WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            'balance': row[0],
            'provider': row[1],
            'address': row[2],
            'exchange_provider': row[3],
            'exchange_address': row[4],
            'telegram': row[5],
            'telegram_token': row[6],
            'credits': row[7],
        }
    return {
        'balance': 0.0,
        'provider': None,
        'address': None,
        'exchange_provider': None,
        'exchange_address': None,
        'telegram': None,
        'telegram_token': None,
        'credits': 0.0,
    }


def update_wallet(user_id, balance=None, provider=None, address=None, exchange_provider=None, exchange_address=None, telegram=None, telegram_token=None, credits=None):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM wallets WHERE user_id = ?', (user_id,))
    if cursor.fetchone() is None:
        cursor.execute('INSERT INTO wallets (user_id, balance, provider, address, exchange_provider, exchange_address, telegram, telegram_token, credits) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                       (user_id, balance or 0.0, provider, address, exchange_provider, exchange_address, telegram, telegram_token, credits or 0.0))
    else:
        if balance is not None:
            cursor.execute('UPDATE wallets SET balance = ? WHERE user_id = ?', (balance, user_id))
        if provider is not None:
            cursor.execute('UPDATE wallets SET provider = ? WHERE user_id = ?', (provider, user_id))
        if address is not None:
            cursor.execute('UPDATE wallets SET address = ? WHERE user_id = ?', (address, user_id))
        if exchange_provider is not None:
            cursor.execute('UPDATE wallets SET exchange_provider = ? WHERE user_id = ?', (exchange_provider, user_id))
        if exchange_address is not None:
            cursor.execute('UPDATE wallets SET exchange_address = ? WHERE user_id = ?', (exchange_address, user_id))
        if telegram is not None:
            cursor.execute('UPDATE wallets SET telegram = ? WHERE user_id = ?', (telegram, user_id))
        if telegram_token is not None:
            cursor.execute('UPDATE wallets SET telegram_token = ? WHERE user_id = ?', (telegram_token, user_id))
        if credits is not None:
            cursor.execute('UPDATE wallets SET credits = ? WHERE user_id = ?', (credits, user_id))
    conn.commit()
    conn.close()


def save_plugin_purchase(user_id, plugin_name):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO plugin_purchases (user_id, plugin_name, purchased_at) VALUES (?, ?, ?)',
                   (user_id, plugin_name, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()


def get_purchases(user_id):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT plugin_name, purchased_at FROM plugin_purchases WHERE user_id = ?', (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [{'name': row[0], 'when': row[1]} for row in rows]


def record_trade(user_id, mode, pair, strategy, signal, price, amount, pnl, balance):
    conn = sqlite3.connect(DATABASE)
    conn.execute(
        '''INSERT INTO trade_history
           (user_id, mode, pair, strategy, signal, price, amount, pnl, balance, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (user_id, mode, pair, strategy, int(signal), price, amount, pnl, balance,
         datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def get_trade_history(user_id, limit=100):
    conn = sqlite3.connect(DATABASE)
    rows = conn.execute(
        '''SELECT mode, pair, strategy, signal, price, amount, pnl, balance, created_at
           FROM trade_history WHERE user_id = ? ORDER BY id DESC LIMIT ?''',
        (user_id, limit),
    ).fetchall()
    conn.close()
    return [
        {'mode': row[0], 'pair': row[1], 'strategy': row[2], 'signal': row[3],
         'price': row[4], 'amount': row[5], 'pnl': row[6], 'balance': row[7],
         'created_at': row[8]}
        for row in rows
    ]


def get_all_users():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT id, username, email, role FROM users')
    rows = cursor.fetchall()
    conn.close()
    return rows


def update_user_theme(user_id, theme):
    conn = sqlite3.connect(DATABASE)
    conn.execute('UPDATE users SET theme = ? WHERE id = ?', (theme, user_id))
    conn.commit()
    conn.close()


def get_all_purchases():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, plugin_name, purchased_at FROM plugin_purchases')
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_all_wallets():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, balance, provider, address, exchange_provider, exchange_address, telegram FROM wallets')
    rows = cursor.fetchall()
    conn.close()
    return rows


init_db()
load_plugins()


@app.context_processor
def inject_user():
    return {
        'user_id': session.get('user_id'),
        'user_name': session.get('user_name'),
        'user_email': session.get('user_email'),
        'is_admin': session.get('is_admin', False),
        'theme': session.get('theme', 'light'),
        'vercel_analytics_id': os.getenv('VERCEL_ANALYTICS_ID'),
    }


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/home')
def home():
    return render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user_id'):
        return redirect(url_for('dashboard'))
    message = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        hashed_pw = hash_password(password)

        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('SELECT id, username, email, role, COALESCE(theme, "light") FROM users WHERE (username = ? OR email = ?) AND password = ?',
                   (username, username, hashed_pw))
        row = cursor.fetchone()
        conn.close()

        if row:
            session['user_id'] = row[0]
            session['user_name'] = row[1]
            session['user_email'] = row[2]
            session['is_admin'] = row[3] == 'admin'
            session['theme'] = row[4] or 'light'
            return redirect(url_for('dashboard'))
        message = 'Неверный логин или пароль.'

    return render_template('login.html', message=message)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if session.get('user_id'):
        return redirect(url_for('dashboard'))
    message = None
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if password != confirm_password:
            message = 'Пароли не совпадают.'
        else:
            hashed_pw = hash_password(password)
            try:
                conn = sqlite3.connect(DATABASE)
                cursor = conn.cursor()
                cursor.execute('INSERT INTO users (username, email, password) VALUES (?, ?, ?)',
                               (username, email, hashed_pw))
                user_id = cursor.lastrowid
                cursor.execute('INSERT INTO wallets (user_id, balance, credits) VALUES (?, ?, ?)', (user_id, 100.0, 100.0))
                conn.commit()
                conn.close()
                session['user_id'] = user_id
                session['user_name'] = username
                session['user_email'] = email
                session['is_admin'] = False
                session['theme'] = 'light'
                return redirect(url_for('dashboard'))
            except sqlite3.IntegrityError:
                message = 'Пользователь с таким именем или email уже существует.'
            except Exception as e:
                message = f'Ошибка регистрации: {e}'

    return render_template('register.html', message=message)


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if session.get('user_id'):
        return redirect(url_for('dashboard'))
    message = None
    if request.method == 'POST':
        email = request.form.get('email')
        message = 'Инструкции по восстановлению пароля отправлены на указанный email.'
    return render_template('forgot_password.html', message=message)


@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = get_user(session['user_id'])
    wallet = get_wallet(session['user_id'])
    message = None
    if request.method == 'POST' and request.form.get('action') == 'save_theme':
        theme = request.form.get('theme', 'light')
        if theme in {'light', 'dark'}:
            update_user_theme(session['user_id'], theme)
            session['theme'] = theme
            user = get_user(session['user_id'])
            message = 'Тема оформления сохранена.'

    return render_template(
        'dashboard.html',
        username=user[1],
        email=user[2],
        balance=wallet['balance'],
        wallet=wallet,
        selected_theme=user[4] or 'light',
        message=message,
    )


@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    message = None
    if request.method == 'POST':
        theme = request.form.get('theme', 'light')
        if theme in {'light', 'dark'}:
            update_user_theme(session['user_id'], theme)
            session['theme'] = theme
            message = 'Настройки аккаунта сохранены.'
        else:
            message = 'Выберите доступную тему оформления.'

    user = get_user(session['user_id'])
    return render_template(
        'settings.html',
        username=user[1],
        email=user[2],
        selected_theme=user[4] or 'light',
        message=message,
    )


def save_strategy_config(strategy: str, leverage: float, risk_tolerance: float):
    cfg = {
        'strategy': strategy,
        'leverage': leverage,
        'risk_tolerance': risk_tolerance,
    }
    with (BASE_DIR / 'backend' / 'config.yaml').open('w', encoding='utf-8') as handle:
        yaml.safe_dump(cfg, handle)
    strategy_manager.config = cfg


@app.route('/marketplace', methods=['GET', 'POST'])
def marketplace():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    message = None
    exchange_info = None
    plugin_message = None
    wallet = get_wallet(session['user_id'])
    purchases = get_purchases(session['user_id'])
    plugins = cmse.list_plugins()

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'connect_exchange':
            provider = request.form.get('exchange_name')
            api_key = request.form.get('api_key', '')
            api_secret = request.form.get('api_secret', '')
            try:
                status = exchange_service.connect(
                    session['user_id'], provider, api_key, api_secret,
                    request.form.get('api_password'), request.form.get('sandbox') == 'on',
                )
                exchange_info = (
                    f"Подключено {provider}. "
                    f"{'Sandbox' if status['sandbox'] else 'Основной аккаунт'}."
                )
                update_wallet(session['user_id'], exchange_provider=provider, exchange_address=api_key[:6] + '...' if api_key else None)
                wallet = get_wallet(session['user_id'])
            except Exception as e:
                message = f'Ошибка подключения: {e}'
        elif action == 'connect_wallet':
            provider = request.form.get('wallet_provider')
            address = request.form.get('wallet_address')
            if provider and address:
                update_wallet(session['user_id'], provider=provider, address=address)
                wallet = get_wallet(session['user_id'])
                message = f'Кошелек {provider} подключен.'
        elif action == 'connect_telegram':
            telegram = request.form.get('telegram_username')
            telegram_token = request.form.get('telegram_token')
            if telegram:
                update_wallet(session['user_id'], telegram=telegram, telegram_token=telegram_token)
                wallet = get_wallet(session['user_id'])
                message = f'Telegram @{telegram} подключен.'
        elif action == 'buy_credits':
            try:
                amount = float(request.form.get('amount', 0))
                currency = request.form.get('currency', 'EUR')
                quote = cmsc_price_in_currency(amount, currency)
                update_wallet(session['user_id'], credits=wallet['credits'] + amount)
                wallet = get_wallet(session['user_id'])
                message = f'Куплено {amount:.0f} CMSC. К оплате: {quote:.2f} {currency}.'
            except ValueError as exc:
                message = str(exc)
        elif action == 'buy_plugin':
            plugin_name = request.form.get('plugin_name')
            plugin = next((p for p in plugins if p.name == plugin_name), None)
            if plugin:
                if wallet['credits'] >= plugin.price:
                    new_balance = wallet['credits'] - plugin.price
                    update_wallet(session['user_id'], credits=new_balance)
                    save_plugin_purchase(session['user_id'], plugin_name)
                    wallet = get_wallet(session['user_id'])
                    plugin_message = f'Плагин {plugin_name} куплен. Баланс: {new_balance:.2f} CMSC.'
                else:
                    plugin_message = 'Недостаточно средств для покупки плагина.'
            else:
                plugin_message = 'Плагин не найден.'

    return render_template(
        'marketplace.html',
        exchanges=EXCHANGES,
        trading_pairs=TRADING_PAIRS,
        internal_currency=INTERNAL_CURRENCY,
        wallets=WALLETS,
        wallet=wallet,
        plugins=plugins,
        message=message,
        exchange_info=exchange_info,
        plugin_message=plugin_message,
        purchases=purchases,
    )


@app.route('/bot-management', methods=['GET', 'POST'])
def bot_management():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    message = None
    manual_trade_result = None
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'start_bot':
            bot.start()
            message = 'Бот запущен.'
        elif action == 'stop_bot':
            bot.stop()
            message = 'Бот остановлен.'
        elif action == 'save_strategy':
            strategy = request.form.get('strategy')
            leverage = max(0.1, min(float(request.form.get('leverage', 1.5)), 10))
            risk_tolerance = max(0.0, min(float(request.form.get('risk_tolerance', 0.03)), 1))
            save_strategy_config(strategy, leverage, risk_tolerance)
            message = 'Настройки стратегии сохранены.'
        elif action == 'manual_trade':
            news_sentiment = float(request.form.get('news_sentiment', 0.0))
            price_change = float(request.form.get('price_change', 0.0))
            current_balance = float(request.form.get('current_balance', 100.0))
            pair = request.form.get('pair', TRADING_PAIRS[0])
            manual_trade_result = strategy_manager.execute(news_sentiment, price_change, current_balance)
            manual_trade_result['pair'] = pair
            trade = bot.simulate(pair, strategy_manager.current_strategy(), manual_trade_result)
            record_trade(
                session['user_id'], 'manual', pair, strategy_manager.current_strategy(),
                manual_trade_result['signal'], None, None, trade['pl'],
                manual_trade_result['next_balance'],
            )
            message = 'Ручная сделка выполнена.'

    bot_status = bot.status()
    current_strategy = strategy_manager.current_strategy()
    config = strategy_manager.config
    balance_history = [
        {'time': item['time'], 'value': 100 + idx * 3}
        for idx, item in enumerate(bot_status.get('stats', []))
    ]
    if not balance_history:
        balance_history = [{'time': 'start', 'value': 100}]

    return render_template(
        'bot_management.html',
        bot_status=bot_status,
        current_strategy=current_strategy,
        config=config,
        message=message,
        manual_trade_result=manual_trade_result,
        balance_history=balance_history,
        trade_history=get_trade_history(session['user_id']),
        trading_pairs=TRADING_PAIRS,
    )


@app.post('/api/trading/test')
def trading_test():
    if 'user_id' not in session:
        return {'error': 'Требуется авторизация.'}, 401
    try:
        payload = request.get_json(silent=True) or {}
        pair = payload.get('pair', TRADING_PAIRS[0])
        if pair not in TRADING_PAIRS:
            return {'error': 'Недоступная торговая пара.'}, 400
        news_sentiment = float(payload.get('news_sentiment', 0))
        price_change = float(payload.get('price_change', 0))
        current_balance = max(0.0, float(payload.get('current_balance', 100)))
        result = strategy_manager.execute(news_sentiment, price_change, current_balance)
        result['pair'] = pair
        result['trade'] = bot.simulate(pair, strategy_manager.current_strategy(), result)
        record_trade(
            session['user_id'], 'manual', pair, strategy_manager.current_strategy(),
            result['signal'], None, None, result['trade']['pl'], result['next_balance'],
        )
        return result
    except (TypeError, ValueError):
        return {'error': 'Проверьте числовые параметры сделки.'}, 400


@app.get('/api/trading/status')
def trading_status():
    if 'user_id' not in session:
        return {'error': 'Требуется авторизация.'}, 401
    return bot.status()


@app.get('/api/exchange/status')
def exchange_status():
    if 'user_id' not in session:
        return {'error': 'Требуется авторизация.'}, 401
    return exchange_service.status(session['user_id'])


@app.post('/api/exchange/connect')
def connect_exchange_api():
    if 'user_id' not in session:
        return {'error': 'Требуется авторизация.'}, 401
    payload = request.get_json(silent=True) or {}
    try:
        return exchange_service.connect(
            session['user_id'],
            payload.get('exchange_name'),
            payload.get('api_key'),
            payload.get('api_secret'),
            payload.get('api_password'),
            bool(payload.get('sandbox', True)),
        )
    except (TypeError, ValueError, ccxt.BaseError) as exc:
        return {'error': f'Ошибка подключения: {exc}'}, 400


@app.post('/api/exchange/disconnect')
def disconnect_exchange_api():
    if 'user_id' not in session:
        return {'error': 'Требуется авторизация.'}, 401
    exchange_service.disconnect(session['user_id'])
    return {'status': 'disconnected'}


@app.get('/api/exchange/balance')
def exchange_balance():
    if 'user_id' not in session:
        return {'error': 'Требуется авторизация.'}, 401
    try:
        balance = exchange_service.balance(session['user_id'])
        return {
            'free': balance.get('free', {}),
            'used': balance.get('used', {}),
            'total': balance.get('total', {}),
        }
    except (LookupError, ccxt.BaseError) as exc:
        return {'error': str(exc)}, 400


def _public_exchange(name):
    if name not in EXCHANGES:
        raise ValueError('Неизвестная биржа.')
    exchange_class = getattr(ccxt, name, None)
    if exchange_class is None:
        raise ValueError('Биржа не поддерживается установленной версией CCXT.')
    return exchange_class({'enableRateLimit': True, 'timeout': 10000})


def _configured_fee_rate():
    rate = float(os.getenv('SIMULATION_FEE_RATE', '0.001'))
    if not math.isfinite(rate) or rate < 0:
        raise ValueError('SIMULATION_FEE_RATE должен быть неотрицательным числом.')
    return rate


def _exchange_fee_rate(exchange, symbol):
    if not exchange.markets:
        exchange.load_markets()
    market = exchange.markets.get(symbol) or {}
    rate = market.get('taker') or market.get('maker')
    return float(rate) if rate is not None else _configured_fee_rate()


def _order_fee(order, fallback_notional, fallback_rate):
    fees = order.get('fees') or []
    if not fees and order.get('fee'):
        fees = [order['fee']]
    total = sum(float(item.get('cost', 0)) for item in fees if item.get('cost') is not None)
    return total if total > 0 else fallback_notional * fallback_rate


@app.get('/api/market/data')
def market_data():
    if 'user_id' not in session:
        return {'error': 'Требуется авторизация.'}, 401
    exchange_name = request.args.get('exchange', 'binance').lower()
    pair = request.args.get('pair', TRADING_PAIRS[0])
    if pair not in TRADING_PAIRS:
        return {'error': 'Недоступная торговая пара.'}, 400
    try:
        exchange = _public_exchange(exchange_name)
        ticker = exchange.fetch_ticker(pair)
        order_book = exchange.fetch_order_book(pair, limit=10)
        candles = exchange.fetch_ohlcv(pair, timeframe='1h', limit=48)
        return {
            'exchange': exchange_name, 'pair': pair,
            'ticker': {'last': ticker.get('last'), 'change': ticker.get('percentage'),
                       'high': ticker.get('high'), 'low': ticker.get('low'),
                       'timestamp': ticker.get('timestamp')},
            'order_book': {'bids': order_book.get('bids', [])[:10],
                           'asks': order_book.get('asks', [])[:10]},
            'candles': candles,
            'source': 'public exchange API', 'live': True,
        }
    except Exception as exc:
        return {'error': f'Не удалось получить данные биржи: {exc}', 'live': False}, 502


@app.get('/api/market/history')
def market_history():
    if 'user_id' not in session:
        return {'error': 'Требуется авторизация.'}, 401
    exchange_name = request.args.get('exchange', 'binance').lower()
    pair = request.args.get('pair', TRADING_PAIRS[0])
    if pair not in TRADING_PAIRS:
        return {'error': 'Недоступная торговая пара.'}, 400
    try:
        exchange = _public_exchange(exchange_name)
        history = refresh_history(DATABASE, exchange, exchange_name, pair)
        return {
            'exchange': exchange_name, 'pair': pair, 'days': len(history),
            'history': history, 'retention_days': 365,
            'analysis_policy': 'Каждое решение использует только текущую и предыдущие свечи.',
        }
    except Exception as exc:
        return {'error': f'Не удалось обновить историю: {exc}'}, 502


@app.get('/api/trading/history')
def trading_history():
    if 'user_id' not in session:
        return {'error': 'Требуется авторизация.'}, 401
    return {'trades': get_trade_history(session['user_id'])}


@app.post('/api/trading/manual')
def manual_trade():
    if 'user_id' not in session:
        return {'error': 'Требуется авторизация.'}, 401
    payload = request.get_json(silent=True) or {}
    try:
        pair = payload.get('pair', TRADING_PAIRS[0])
        side = payload.get('side', 'buy')
        price = float(payload['price'])
        amount = float(payload['amount'])
        balance = max(0.0, float(payload.get('balance', 100)))
        if pair not in TRADING_PAIRS or side not in {'buy', 'sell'}:
            raise ValueError('Проверьте пару и направление сделки.')
        if not all(math.isfinite(value) for value in (price, amount, balance)) or price <= 0 or amount <= 0:
            raise ValueError('Цена, количество и баланс должны быть положительными числами.')
        notional = price * amount
        if notional > balance:
            raise ValueError('Недостаточно баланса для сделки.')
        fee_rate = _configured_fee_rate()
        fee = notional * fee_rate
        next_balance = balance - fee
        record_trade(session['user_id'], 'manual', pair, 'manual', 1 if side == 'buy' else -1,
                     price, amount, -fee, next_balance)
        return {'status': 'filled', 'pair': pair, 'side': side, 'price': price,
                'amount': amount, 'fee_rate': fee_rate, 'fee': fee, 'pnl': -fee,
                'balance': next_balance}
    except (KeyError, TypeError, ValueError) as exc:
        return {'error': str(exc)}, 400


@app.post('/api/trading/order')
def create_exchange_order():
    if 'user_id' not in session:
        return {'error': 'Требуется авторизация.'}, 401
    payload = request.get_json(silent=True) or {}
    live = bool(payload.get('live', False))
    if live and (
        os.getenv('LIVE_TRADING_ENABLED', 'false').lower() != 'true'
        or payload.get('confirm_live') is not True
    ):
        return {
            'error': (
                'Реальная торговля отключена. Установите LIVE_TRADING_ENABLED=true '
                'и передайте confirm_live=true.'
            )
        }, 403
    try:
        symbol = payload.get('symbol')
        side = payload.get('side', '').lower()
        order_type = payload.get('type', 'market').lower()
        amount_value = payload.get('amount')
        amount = float(amount_value) if amount_value is not None else None
        price = payload.get('price')
        price = float(price) if price is not None else None
        if side not in {'buy', 'sell'} or order_type not in {'market', 'limit'}:
            raise ValueError('Допустимы только buy/sell и market/limit.')
        if not symbol or symbol not in TRADING_PAIRS:
            raise ValueError('Недоступная торговая пара.')
        if amount is not None and (not math.isfinite(amount) or amount <= 0):
            raise ValueError('Количество должно быть положительным числом.')
        if price is not None and (not math.isfinite(price) or price <= 0):
            raise ValueError('Цена должна быть положительным числом.')
        if not live:
            if amount is None:
                raise ValueError('Укажите количество для dry-run ордера.')
            return {
                'status': 'dry_run',
                'symbol': symbol,
                'type': order_type,
                'side': side,
                'amount': amount,
                'price': price,
            }
        reference_price = price
        if reference_price is None:
            ticker = exchange_service.ticker(session['user_id'], symbol)
            reference_price = ticker.get('last')
        if amount is None:
            amount = exchange_service.minimum_order_amount(
                session['user_id'], symbol, reference_price
            )
        max_notional = float(os.getenv('MAX_ORDER_NOTIONAL', '1000'))
        if not math.isfinite(max_notional) or max_notional <= 0:
            raise ValueError('MAX_ORDER_NOTIONAL должен быть положительным числом.')
        if not reference_price or amount * reference_price > max_notional:
            raise ValueError(
                f'Номинал сделки превышает лимит {max_notional:.2f} или цена недоступна.'
            )
        order = exchange_service.create_order(
            session['user_id'], symbol, order_type, side, amount, price, payload.get('params'),
        )
        filled = order.get('filled') or amount
        execution_price = order.get('average') or order.get('price') or reference_price
        notional = float(execution_price) * float(filled)
        fee_rate = exchange_service.trading_fee(session['user_id'], symbol)
        fee = _order_fee(order, notional, fee_rate)
        record_trade(
            session['user_id'], 'live', symbol, 'manual', 1 if side == 'buy' else -1,
            execution_price, filled, -fee, -fee,
        )
        return {'status': 'submitted', 'order': order, 'fee': fee, 'fee_rate': fee_rate,
                'pnl': -fee}
    except (KeyError, TypeError, ValueError, LookupError, ccxt.BaseError) as exc:
        return {'error': str(exc)}, 400


@app.delete('/api/trading/order/<order_id>')
def cancel_exchange_order(order_id):
    if 'user_id' not in session:
        return {'error': 'Требуется авторизация.'}, 401
    if (
        os.getenv('LIVE_TRADING_ENABLED', 'false').lower() != 'true'
        or request.args.get('confirm_live', '').lower() != 'true'
    ):
        return {'error': 'Операции с реальным аккаунтом отключены.'}, 403
    symbol = request.args.get('symbol')
    if not symbol:
        return {'error': 'Укажите symbol.'}, 400
    try:
        return exchange_service.cancel_order(session['user_id'], order_id, symbol)
    except (LookupError, ccxt.BaseError) as exc:
        return {'error': str(exc)}, 400


@app.post('/api/bot/backtest')
def backtest():
    if 'user_id' not in session:
        return {'error': 'Требуется авторизация.'}, 401
    payload = request.get_json(silent=True) or {}
    try:
        initial = max(0.0, float(payload.get('initial_balance', 100)))
        pair = payload.get('pair', TRADING_PAIRS[0])
        exchange_name = payload.get('exchange', 'binance').lower()
        if pair not in TRADING_PAIRS:
            raise ValueError('Недоступная торговая пара.')
        exchange = _public_exchange(exchange_name)
        history = refresh_history(DATABASE, exchange, exchange_name, pair)
        prices = [row['close'] for row in history]
        if len(prices) < 3 or initial <= 0:
            raise ValueError('Нужно минимум 2 дневные свечи и положительный депозит.')
        strategies = {
            'pure_harvester': strategy_manager.module.process_tick,
            'high_frequency_momentum': strategy_manager.module.process_high_frequency,
            'compound_defender': strategy_manager.module.process_defender,
        }
        results = []
        for name, processor in strategies.items():
            balance, wins, total_fees = initial, 0, 0.0
            for index in range(1, len(prices) - 1):
                previous_change = ((prices[index] - prices[index - 1]) / prices[index - 1] * 100
                                   if prices[index - 1] else 0)
                # The signal is formed at candle[index] close; candle[index + 1]
                # is the first price that was unknown when the decision was made.
                sentiment = 1.0 if previous_change > 0 else -1.0
                _, signal = processor(sentiment, previous_change, balance, 1.5)
                next_change = ((prices[index + 1] - prices[index]) / prices[index] * 100
                               if prices[index] else 0)
                gross_balance = balance * (1 + signal * next_change / 100 * 1.5)
                fee_rate = _exchange_fee_rate(exchange, pair)
                fee = balance * 1.5 * fee_rate * 2
                total_fees += fee
                next_balance = max(0.0, gross_balance - fee)
                wins += next_balance > balance
                balance = max(0.0, next_balance)
            results.append({
                'strategy': name, 'initial_balance': initial,
                'final_balance': round(balance, 8), 'pnl': round(balance - initial, 8),
                'roi': round((balance / initial - 1) * 100, 4),
                'trades': len(prices) - 2, 'wins': wins,
                'fee_rate': fee_rate,
                'fees_paid': round(total_fees, 8),
            })
        return {'results': results, 'source': 'stored public daily OHLCV',
                'pair': pair, 'exchange': exchange_name, 'tested_points': len(prices),
                'retention_days': 365, 'lookahead_bias': False}
    except (TypeError, ValueError) as exc:
        return {'error': str(exc)}, 400


@app.route('/admin', methods=['GET', 'POST'])
def admin_panel():
    if not session.get('is_admin'):
        return redirect(url_for('dashboard'))

    message = None
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'create_plugin':
            name = request.form.get('plugin_name')
            try:
                price = float(request.form.get('plugin_price', 0.0))
            except (TypeError, ValueError):
                price = 0.0
            description = request.form.get('plugin_description', '')
            if name and price > 0:
                cmse.create_plugin(name, price, description)
                message = f'Плагин {name} добавлен.'
            else:
                message = 'Укажите название и положительную цену плагина.'
        elif action == 'save_admin_settings':
            strategy = request.form.get('strategy', strategy_manager.current_strategy())
            try:
                leverage = max(0.1, min(float(request.form.get('leverage', 1.5)), 10))
                risk_tolerance = max(0.0, min(float(request.form.get('risk_tolerance', 0.03)), 1))
                save_strategy_config(strategy, leverage, risk_tolerance)
                message = 'Настройки торговой платформы сохранены.'
            except (TypeError, ValueError):
                message = 'Проверьте значения левериджа и риска.'
        elif action == 'save_payout_settings':
            crypto_asset = request.form.get('crypto_asset', '')
            card_provider = request.form.get('card_provider', '')
            crypto_address = request.form.get('crypto_address', '').strip()
            card_recipient = request.form.get('card_recipient', '').strip()
            if crypto_asset not in CRYPTO_PAYOUT_ASSETS:
                message = 'Выберите поддерживаемую криптовалюту для выплат.'
            elif card_provider not in CARD_PAYOUT_SERVICES:
                message = 'Выберите поддерживаемый платёжный сервис.'
            elif not crypto_address or not card_recipient:
                message = 'Укажите криптоадрес и реквизит аккаунта платёжного сервиса.'
            else:
                save_admin_payout_settings({
                    'crypto_asset': crypto_asset,
                    'crypto_network': request.form.get('crypto_network', '').strip(),
                    'crypto_address': crypto_address,
                    'card_provider': card_provider,
                    'card_recipient': card_recipient,
                })
                message = 'Настройки выплат сохранены.'

    users = get_all_users()
    plugins = cmse.list_plugins()
    wallets = get_all_wallets()
    purchases = get_all_purchases()
    return render_template(
        'admin.html',
        users=users,
        plugins=plugins,
        purchases=purchases,
        wallets=wallets,
        message=message,
        current_strategy=strategy_manager.current_strategy(),
        config=strategy_manager.config,
        payout_settings=get_admin_payout_settings(),
        crypto_payout_assets=CRYPTO_PAYOUT_ASSETS,
        card_payout_services=CARD_PAYOUT_SERVICES,
    )


@app.route('/wallet', methods=['GET', 'POST'])
def wallet_page():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    wallet = get_wallet(session['user_id'])
    message = None
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'buy_credits':
            try:
                amount = float(request.form.get('amount', '0'))
                currency = request.form.get('currency', 'EUR')
                quote = cmsc_price_in_currency(amount, currency)
                update_wallet(session['user_id'], credits=wallet['credits'] + amount)
                wallet = get_wallet(session['user_id'])
                message = f'Куплено {amount:.0f} CMSC. К оплате: {quote:.2f} {currency}.'
            except ValueError as exc:
                message = str(exc)
        elif action == 'buy_usdt':
            try:
                amount = float(request.form.get('amount', '0'))
                if amount <= 0:
                    message = 'Введите положительную сумму.'
                else:
                    # Простая симуляция покупки USDT (1 USD = 1 USDT)
                    new_balance = wallet['balance'] + amount
                    update_wallet(session['user_id'], balance=new_balance)
                    wallet = get_wallet(session['user_id'])
                    message = f'Куплено {amount:.2f} USDT. Новый баланс: {wallet["balance"]:.2f}.'
            except ValueError:
                message = 'Неверная сумма.'

    return render_template(
        'wallet.html',
        wallet=wallet,
        message=message,
        payment_currencies=CMSC_PAYMENT_CURRENCIES,
    )


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(
        host='0.0.0.0',
        port=int(os.getenv('PORT', '5000')),
        debug=os.getenv('FLASK_DEBUG', 'false').lower() == 'true',
    )
