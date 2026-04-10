"""
NAZ OMIC Scanner – Standalone Web App
No MT5 needed. Uses free yfinance data.
Deploy to Render.com, Railway, or any Python host.
"""
import os, json, time, threading
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import yfinance as yf
import pandas as pd
import numpy as np

app = Flask(__name__, static_folder='static')
CORS(app)

# ═══════════════════════════════════════════════════════════════
# SYMBOLS
# ═══════════════════════════════════════════════════════════════
SYMBOLS = {
    "Forex&Metals": {
        "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "USDJPY=X",
        "AUDUSD": "AUDUSD=X", "NZDUSD": "NZDUSD=X", "USDCAD": "USDCAD=X",
        "USDCHF": "USDCHF=X", "EURJPY": "EURJPY=X", "GBPJPY": "GBPJPY=X",
        "EURGBP": "EURGBP=X", "EURAUD": "EURAUD=X", "GBPAUD": "GBPAUD=X",
        "AUDJPY": "AUDJPY=X", "CADJPY": "CADJPY=X", "CHFJPY": "CHFJPY=X",
        "XAUUSD": "GC=F", "XAGUSD": "SI=F",
    },
    "Crypto": {
        "BTCUSD": "BTC-USD", "ETHUSD": "ETH-USD", "SOLUSD": "SOL-USD",
        "XRPUSD": "XRP-USD", "ADAUSD": "ADA-USD", "DOTUSD": "DOT-USD",
        "AVAXUSD": "AVAX-USD", "LINKUSD": "LINK-USD", "MATICUSD": "MATIC-USD",
        "DOGEUSD": "DOGE-USD",
    },
    "Stocks": {
        "AAPL": "AAPL", "MSFT": "MSFT", "GOOGL": "GOOGL", "AMZN": "AMZN",
        "TSLA": "TSLA", "NVDA": "NVDA", "META": "META", "NFLX": "NFLX",
        "AMD": "AMD", "BA": "BA", "DIS": "DIS", "JPM": "JPM",
        "V": "V", "MA": "MA", "PYPL": "PYPL",
    },
}

# Template timeframe configs (yfinance intervals)
TEMPLATES = {
    "Monthly":  {"ctx": "1mo", "entry": "1d",  "ctx_arrow": "1mo", "val": "1wk", "label": "MN1/D1/MN1/W1"},
    "Weekly":   {"ctx": "1wk", "entry": "1h",  "ctx_arrow": "1wk", "val": "1d",  "label": "W1/H4/W1/D1"},
    "Daily":    {"ctx": "1d",  "entry": "1h",  "ctx_arrow": "1d",  "val": "1h",  "label": "D1/H1/D1/H4"},
    "4HR":      {"ctx": "1h",  "entry": "15m", "ctx_arrow": "1h",  "val": "30m", "label": "H4/M15/H4/M30"},
}

# yfinance period mapping (how much history to fetch)
PERIOD_MAP = {
    "1mo": "2y", "1wk": "1y", "1d": "6mo", "1h": "30d", "30m": "30d", "15m": "7d", "5m": "5d",
}

# ═══════════════════════════════════════════════════════════════
# SCAN CACHE
# ═══════════════════════════════════════════════════════════════
scan_cache = {}
cache_lock = threading.Lock()

def get_cache_key(asset, template):
    return f"{asset}_{template}"

def get_cached(asset, template, max_age=120):
    key = get_cache_key(asset, template)
    with cache_lock:
        if key in scan_cache:
            data, ts = scan_cache[key]
            if time.time() - ts < max_age:
                return data
    return None

def set_cached(asset, template, data):
    key = get_cache_key(asset, template)
    with cache_lock:
        scan_cache[key] = (data, time.time())

# ═══════════════════════════════════════════════════════════════
# DATA FETCHING
# ═══════════════════════════════════════════════════════════════
def fetch_ohlc(yf_ticker, interval, period):
    try:
        tk = yf.Ticker(yf_ticker)
        df = tk.history(period=period, interval=interval)
        if df is None or df.empty:
            return None
        df = df.reset_index()
        # Normalize column names
        if 'Datetime' in df.columns:
            df = df.rename(columns={'Datetime': 'Date'})
        df = df[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']].copy()
        df['Date'] = pd.to_datetime(df['Date'])
        return df
    except Exception as e:
        print(f"Error fetching {yf_ticker} {interval}: {e}")
        return None

# ═══════════════════════════════════════════════════════════════
# SCANNING LOGIC (ported from MQL5)
# ═══════════════════════════════════════════════════════════════
def calc_ema(closes, period):
    if len(closes) < period:
        return None
    ema = [closes.iloc[0]]
    k = 2.0 / (period + 1)
    for i in range(1, len(closes)):
        ema.append(closes.iloc[i] * k + ema[-1] * (1 - k))
    return ema

def check_arrow(df):
    """Check arrow condition: most recent close vs previous candle range"""
    if df is None or len(df) < 3:
        return "None"
    for i in range(len(df) - 2, 0, -1):
        cc = df['Close'].iloc[i]
        ph = df['High'].iloc[i - 1]
        pl = df['Low'].iloc[i - 1]
        if cc > ph:
            return "UP"
        if cc < pl:
            return "DOWN"
    return "None"

def check_ema_state(df, p1=10, p2=20):
    """Check EMA 10 vs EMA 20"""
    if df is None or len(df) < p2 + 5:
        return "N/A"
    ema10 = calc_ema(df['Close'], p1)
    ema20 = calc_ema(df['Close'], p2)
    if ema10 is None or ema20 is None:
        return "N/A"
    if ema10[-1] > ema20[-1]:
        return "ACC"
    if ema10[-1] < ema20[-1]:
        return "DISS"
    return "EQL"

def calc_ment_block(df, lookback=30):
    """Calculate Ment Block trend"""
    if df is None or len(df) < lookback + 10:
        return 0, 0, 0  # trend, high, low
    highs = df['High'].values
    lows = df['Low'].values
    closes = df['Close'].values
    n = len(df)

    lo_idx = np.argmin(lows[:lookback])
    hi_idx = np.argmax(highs[:lookback])
    ment_low = lows[lo_idx]
    ment_high = highs[hi_idx]
    trend = 0

    for i in range(lookback, n):
        if closes[i] >= ment_high:
            ment_high = highs[i]
            local_low = lows[i]
            for j in range(1, min(lookback, i)):
                idx = i - j
                if lows[idx] < local_low:
                    local_low = lows[idx]
                if idx > 0 and closes[idx] < lows[idx - 1]:
                    ment_low = min(lows[idx], local_low)
                    break
            trend = 1
        if closes[i] <= ment_low:
            ment_low = lows[i]
            local_high = highs[i]
            for j in range(1, min(lookback, i)):
                idx = i - j
                if highs[idx] > local_high:
                    local_high = highs[idx]
                if idx > 0 and closes[idx] > highs[idx - 1]:
                    ment_high = max(highs[idx], local_high)
                    break
            trend = -1

    return trend, ment_high, ment_low

def find_pattern(df, bullish):
    """Find arrow pattern confirmation in entry TF data"""
    if df is None or len(df) < 5:
        return False, 0, -1
    # Search from most recent backwards
    for i in range(len(df) - 2, max(0, len(df) - 100), -1):
        if i + 1 >= len(df):
            continue
        cc = df['Close'].iloc[i]
        ph = df['High'].iloc[i - 1] if i > 0 else df['High'].iloc[0]
        pl = df['Low'].iloc[i - 1] if i > 0 else df['Low'].iloc[0]
        if bullish and cc > ph:
            # Find lowest low from start of context period to pattern
            ll = df['Low'].iloc[:i+1].min()
            return True, ll, i
        if not bullish and cc < pl:
            hh = df['High'].iloc[:i+1].max()
            return True, hh, i
    return False, 0, -1

def find_sweep(df, pattern_line, bullish, start_idx):
    """Find sweep of pattern line"""
    if df is None or start_idx < 0 or start_idx >= len(df):
        return False, -1
    for i in range(start_idx, len(df)):
        if bullish and df['Low'].iloc[i] < pattern_line:
            return True, i
        if not bullish and df['High'].iloc[i] > pattern_line:
            return True, i
    return False, -1

def find_entry_signal(df, sweep_idx, bullish):
    """Find entry signal after sweep"""
    if df is None or sweep_idx < 0 or sweep_idx + 1 >= len(df):
        return False, -1
    for i in range(sweep_idx + 1, len(df)):
        if i + 1 >= len(df) or i < 1:
            continue
        cc = df['Close'].iloc[i]
        ph = df['High'].iloc[i - 1]
        pl = df['Low'].iloc[i - 1]
        if bullish and cc > ph:
            return True, i
        if not bullish and cc < pl:
            return True, i
    return False, -1

def scan_symbol(name, yf_ticker, tpl_config):
    """Full NAZ OMIC scan for one symbol"""
    try:
        ctx_interval = tpl_config["ctx_arrow"]
        val_interval = tpl_config["val"]
        entry_interval = tpl_config["entry"]

        # Fetch data
        ctx_df = fetch_ohlc(yf_ticker, ctx_interval, PERIOD_MAP.get(ctx_interval, "6mo"))
        val_df = fetch_ohlc(yf_ticker, val_interval, PERIOD_MAP.get(val_interval, "3mo"))
        entry_df = fetch_ohlc(yf_ticker, entry_interval, PERIOD_MAP.get(entry_interval, "1mo"))

        if ctx_df is None or val_df is None or entry_df is None:
            return None
        if len(ctx_df) < 10 or len(val_df) < 10 or len(entry_df) < 30:
            return None

        # Step 1: Arrow + EMA on context TF
        ctx_arrow = check_arrow(ctx_df)
        ctx_ema = check_ema_state(ctx_df)

        bullish = (ctx_arrow == "UP" and ctx_ema == "ACC")
        bearish = (ctx_arrow == "DOWN" and ctx_ema == "DISS")

        if not bullish and not bearish:
            return None

        # Step 2: Template 3 check - Validation EMA must align
        val_ema = check_ema_state(val_df)
        if bullish and val_ema != "ACC":
            return None
        if bearish and val_ema != "DISS":
            return None

        # Step 3: Find pattern on entry TF
        found, pattern_line, pat_idx = find_pattern(entry_df, bullish)
        if not found:
            return None

        # Step 4: Find sweep
        swept, sweep_idx = find_sweep(entry_df, pattern_line, bullish, pat_idx)
        if not swept:
            return None

        # Step 5: Entry signal after sweep
        entry_found, entry_idx = find_entry_signal(entry_df, sweep_idx, bullish)
        if not entry_found:
            return None

        # Step 6: Protected level
        if bullish:
            protected = entry_df['Low'].iloc[:entry_idx+1].min()
            current = entry_df['Close'].iloc[-1]
            if current < protected:
                return None
        else:
            protected = entry_df['High'].iloc[:entry_idx+1].max()
            current = entry_df['Close'].iloc[-1]
            if current > protected:
                return None

        # Step 7: Ment block check
        ment_trend, _, _ = calc_ment_block(entry_df)
        if bullish and ment_trend != 1:
            return None
        if bearish and ment_trend != -1:
            return None

        direction = "BUY" if bullish else "SELL"
        ment_label = "BULL" if ment_trend == 1 else "BEAR" if ment_trend == -1 else "FLAT"
        price = float(entry_df['Close'].iloc[-1])

        return {
            "symbol": name,
            "direction": direction,
            "ment": ment_label,
            "status": "READY",
            "price": round(price, 5 if price < 10 else 2),
            "protected_level": round(float(protected), 5 if price < 10 else 2),
        }

    except Exception as e:
        print(f"Scan error {name}: {e}")
        return None

def run_scan(asset_class, template_name):
    """Run full scan for an asset class and template"""
    # Check cache first
    cached = get_cached(asset_class, template_name)
    if cached:
        return cached

    symbols = SYMBOLS.get(asset_class, {})
    tpl = TEMPLATES.get(template_name)
    if not tpl:
        return {"error": "Invalid template", "signals": []}

    signals = []
    scanned = 0
    errors = 0

    for name, yf_ticker in symbols.items():
        scanned += 1
        result = scan_symbol(name, yf_ticker, tpl)
        if result:
            signals.append(result)

    data = {
        "scanner_version": "3.15-web",
        "asset_class": asset_class,
        "template": template_name,
        "timeframes": tpl["label"],
        "total_symbols": len(symbols),
        "symbols_scanned": scanned,
        "qualifying_count": len(signals),
        "last_scan": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "signals": signals,
    }

    set_cached(asset_class, template_name, data)
    return data

# ═══════════════════════════════════════════════════════════════
# API ENDPOINTS
# ═══════════════════════════════════════════════════════════════
@app.route('/api/scan')
def api_scan():
    asset = request.args.get('asset', 'Forex&Metals')
    template = request.args.get('template', 'Weekly')
    try:
        data = run_scan(asset, template)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e), "signals": []})

@app.route('/api/symbols')
def api_symbols():
    asset = request.args.get('asset', 'Forex&Metals')
    symbols = list(SYMBOLS.get(asset, {}).keys())
    return jsonify({"asset": asset, "symbols": symbols, "count": len(symbols)})

@app.route('/api/status')
def api_status():
    return jsonify({"status": "running", "version": "3.15-web", "cache_size": len(scan_cache)})

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('static', path)

# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5555))
    print(f"NAZ OMIC Scanner Web – http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)
