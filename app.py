"""
NAZ OMIC Scanner – Standalone Web App v2
Scanning logic matches the MQL5 EA exactly.
Uses free yfinance data. Deploy to Render.com.
"""
import os, json, time, threading, traceback
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import yfinance as yf
import pandas as pd
import numpy as np

app = Flask(__name__, static_folder='static')
CORS(app)

# ═══════════════════════════════════════════════════════════════
# SYMBOLS — EXPANDED LISTS
# ═══════════════════════════════════════════════════════════════
SYMBOLS = {
    "Forex&Metals": {
        # Majors
        "EURUSD":"EURUSD=X","GBPUSD":"GBPUSD=X","USDJPY":"USDJPY=X","USDCHF":"USDCHF=X",
        "AUDUSD":"AUDUSD=X","NZDUSD":"NZDUSD=X","USDCAD":"USDCAD=X",
        # Crosses
        "EURJPY":"EURJPY=X","GBPJPY":"GBPJPY=X","EURGBP":"EURGBP=X","EURAUD":"EURAUD=X",
        "EURCAD":"EURCAD=X","EURCHF":"EURCHF=X","EURNZD":"EURNZD=X",
        "GBPAUD":"GBPAUD=X","GBPCAD":"GBPCAD=X","GBPCHF":"GBPCHF=X","GBPNZD":"GBPNZD=X",
        "AUDJPY":"AUDJPY=X","AUDCAD":"AUDCAD=X","AUDCHF":"AUDCHF=X","AUDNZD":"AUDNZD=X",
        "NZDJPY":"NZDJPY=X","NZDCAD":"NZDCAD=X","NZDCHF":"NZDCHF=X",
        "CADJPY":"CADJPY=X","CADCHF":"CADCHF=X","CHFJPY":"CHFJPY=X",
        # Exotics
        "USDZAR":"USDZAR=X","USDMXN":"USDMXN=X","USDTRY":"USDTRY=X",
        "USDSEK":"USDSEK=X","USDNOK":"USDNOK=X","USDSGD":"USDSGD=X",
        "USDHKD":"USDHKD=X","USDPLN":"USDPLN=X","USDCZK":"USDCZK=X",
        "USDHUF":"USDHUF=X","EURPLN":"EURPLN=X","EURTRY":"EURTRY=X",
        "EURSEK":"EURSEK=X","EURNOK":"EURNOK=X","EURHUF":"EURHUF=X",
        "GBPZAR":"GBPZAR=X","GBPSGD":"GBPSGD=X","GBPTRY":"GBPTRY=X",
        # Metals
        "XAUUSD":"GC=F","XAGUSD":"SI=F",
    },
    "Crypto": {
        "BTCUSD":"BTC-USD","ETHUSD":"ETH-USD","BNBUSD":"BNB-USD","SOLUSD":"SOL-USD",
        "XRPUSD":"XRP-USD","ADAUSD":"ADA-USD","DOGEUSD":"DOGE-USD","DOTUSD":"DOT-USD",
        "AVAXUSD":"AVAX-USD","LINKUSD":"LINK-USD","MATICUSD":"MATIC-USD","SHIBUSD":"SHIB-USD",
        "UNIUSD":"UNI-USD","LTCUSD":"LTC-USD","BCHUSD":"BCH-USD","ATOMUSD":"ATOM-USD",
        "XLMUSD":"XLM-USD","NEARUSD":"NEAR-USD","ALGOUSD":"ALGO-USD","ICPUSD":"ICP-USD",
        "FILUSD":"FIL-USD","VETUSD":"VET-USD","APEUSD":"APE-USD","MANAUSD":"MANA-USD",
        "SANDUSD":"SAND-USD","AABORUSD":"AAVE-USD","FTMUSD":"FTM-USD","TRXUSD":"TRX-USD",
        "ETCUSD":"ETC-USD","EOSUSD":"EOS-USD","AXSUSD":"AXS-USD","THETAUSD":"THETA-USD",
        "HBARUSD":"HBAR-USD","RUNEUSD":"RUNE-USD","SUIUSD":"SUI20947-USD",
        "PEPEUSD":"PEPE24478-USD","ARBUSD":"ARB11841-USD","OPUSD":"OP-USD",
    },
    "Stocks": {
        # Tech
        "AAPL":"AAPL","MSFT":"MSFT","GOOGL":"GOOGL","AMZN":"AMZN","TSLA":"TSLA",
        "NVDA":"NVDA","META":"META","NFLX":"NFLX","AMD":"AMD","INTC":"INTC",
        "CRM":"CRM","ORCL":"ORCL","ADBE":"ADBE","CSCO":"CSCO","QCOM":"QCOM",
        "AVGO":"AVGO","TXN":"TXN","MU":"MU","SHOP":"SHOP","SQ":"SQ",
        "PYPL":"PYPL","UBER":"UBER","ABNB":"ABNB","SNAP":"SNAP","PINS":"PINS",
        "PLTR":"PLTR","RBLX":"RBLX","U":"U","COIN":"COIN","MARA":"MARA",
        # Finance
        "JPM":"JPM","BAC":"BAC","WFC":"WFC","GS":"GS","MS":"MS","V":"V","MA":"MA","AXP":"AXP",
        # Healthcare
        "JNJ":"JNJ","UNH":"UNH","PFE":"PFE","ABBV":"ABBV","MRK":"MRK","LLY":"LLY",
        # Consumer
        "WMT":"WMT","KO":"KO","PEP":"PEP","MCD":"MCD","SBUX":"SBUX","NKE":"NKE","DIS":"DIS",
        # Industrial
        "BA":"BA","CAT":"CAT","GE":"GE","HON":"HON","UPS":"UPS","FDX":"FDX",
        # Energy
        "XOM":"XOM","CVX":"CVX","COP":"COP","OXY":"OXY",
    },
}

# Template configs
# Note: yfinance interval limitations:
#   1mo, 1wk, 1d  → up to many years
#   1h             → last 730 days
#   30m, 15m       → last 60 days
#   5m, 2m, 1m     → last 7 days
TEMPLATES = {
    "Monthly": {"ctx":"1mo","entry":"1d", "ctx_arrow":"1mo","val":"1wk",
                "ctx_period":"5y","entry_period":"1y","ctx_arrow_period":"5y","val_period":"2y",
                "label":"MN1 / D1 / MN1 / W1"},
    "Weekly":  {"ctx":"1wk","entry":"1d", "ctx_arrow":"1wk","val":"1d",
                "ctx_period":"2y","entry_period":"6mo","ctx_arrow_period":"2y","val_period":"1y",
                "label":"W1 / H4 / W1 / D1"},
    "Daily":   {"ctx":"1d", "entry":"1h", "ctx_arrow":"1d", "val":"1d",
                "ctx_period":"1y","entry_period":"30d","ctx_arrow_period":"1y","val_period":"6mo",
                "label":"D1 / H1 / D1 / H4"},
    "4HR":     {"ctx":"1d", "entry":"30m","ctx_arrow":"1d", "val":"1h",
                "ctx_period":"6mo","entry_period":"30d","ctx_arrow_period":"6mo","val_period":"30d",
                "label":"H4 / M15 / H4 / M30"},
}

MENT_BARS_BACK = 30

# ═══════════════════════════════════════════════════════════════
# CACHE
# ═══════════════════════════════════════════════════════════════
scan_cache = {}
cache_lock = threading.Lock()
CACHE_TTL = 120  # seconds

def get_cached(asset, template):
    key = f"{asset}_{template}"
    with cache_lock:
        if key in scan_cache:
            data, ts = scan_cache[key]
            if time.time() - ts < CACHE_TTL:
                return data
    return None

def set_cached(asset, template, data):
    key = f"{asset}_{template}"
    with cache_lock:
        scan_cache[key] = (data, time.time())

# ═══════════════════════════════════════════════════════════════
# DATA FETCHING
# ═══════════════════════════════════════════════════════════════
def fetch_ohlc(yf_ticker, interval, period):
    try:
        tk = yf.Ticker(yf_ticker)
        df = tk.history(period=period, interval=interval)
        if df is None or df.empty or len(df) < 5:
            return None
        df = df.reset_index()
        if 'Datetime' in df.columns:
            df = df.rename(columns={'Datetime': 'Date'})
        df = df[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']].copy()
        df['Date'] = pd.to_datetime(df['Date'])
        return df
    except:
        return None

# ═══════════════════════════════════════════════════════════════
# SCANNING LOGIC — MATCHES MQL5 EA EXACTLY
# ═══════════════════════════════════════════════════════════════

def check_arrow(df):
    """
    MQL5: Loop from bar 1 backwards (most recent closed bars).
    If close[i] > high[i+1] → UP
    If close[i] < low[i+1]  → DOWN
    (In pandas, latest bar is last row, so we go from second-to-last backwards)
    """
    if df is None or len(df) < 3:
        return "None"
    n = len(df)
    limit = min(n - 1, 100)
    for i in range(1, limit + 1):
        bar_idx = n - 1 - i      # current bar (closed)
        prev_idx = n - 1 - i - 1  # previous bar
        if bar_idx < 0 or prev_idx < 0:
            break
        cc = df['Close'].iloc[bar_idx]
        ph = df['High'].iloc[prev_idx]
        pl = df['Low'].iloc[prev_idx]
        if cc > ph:
            return "UP"
        if cc < pl:
            return "DOWN"
    return "None"


def check_ema_state(df, p1=10, p2=20):
    """
    MQL5: EMA10 > EMA20 → ACC, EMA10 < EMA20 → DISS
    Uses most recent bar values.
    """
    if df is None or len(df) < p2 + 5:
        return "N/A"
    closes = df['Close'].values
    # Calculate EMA
    ema_short = pd.Series(closes).ewm(span=p1, adjust=False).mean().values
    ema_long  = pd.Series(closes).ewm(span=p2, adjust=False).mean().values
    if ema_short[-1] == 0 or ema_long[-1] == 0:
        return "N/A"
    if ema_short[-1] > ema_long[-1]:
        return "ACC"
    if ema_short[-1] < ema_long[-1]:
        return "DISS"
    return "EQL"


def calc_ment_block(df, lookback=30):
    """
    MQL5 CalculateMentBlock — exact port.
    Returns trend: 1=bull, -1=bear, 0=flat
    """
    if df is None or len(df) < lookback + 10:
        return 0
    highs = df['High'].values
    lows = df['Low'].values
    closes = df['Close'].values
    n = len(df)

    # Initial block: find highest high and lowest low in first lookback bars
    lo_idx = 0
    hi_idx = 0
    for k in range(1, lookback):
        if k >= n:
            break
        if lows[k] < lows[lo_idx]:
            lo_idx = k
        if highs[k] > highs[hi_idx]:
            hi_idx = k

    ment_low = lows[lo_idx]
    ment_high = highs[hi_idx]
    trend = 0

    for i in range(lookback, n):
        # Bullish break
        if closes[i] >= ment_high:
            ment_high = highs[i]
            local_low = lows[i]
            for j in range(1, lookback):
                idx = i - j
                if idx < 0:
                    break
                if lows[idx] < local_low:
                    local_low = lows[idx]
                if idx - 1 >= 0 and closes[idx] < lows[idx - 1]:
                    ment_low = min(lows[idx], local_low)
                    break
            trend = 1

        # Bearish break
        if closes[i] <= ment_low:
            ment_low = lows[i]
            local_high = highs[i]
            for j in range(1, lookback):
                idx = i - j
                if idx < 0:
                    break
                if highs[idx] > local_high:
                    local_high = highs[idx]
                if idx - 1 >= 0 and closes[idx] > highs[idx - 1]:
                    ment_high = max(highs[idx], local_high)
                    break
            trend = -1

    return trend


def search_pattern(df, bullish):
    """
    MQL5 SearchForPattern — find arrow pattern confirmation.
    Search from newest bar backwards within the data.
    Bullish: close > prev high
    Returns: (found, pattern_line_price, pattern_bar_index)
    """
    if df is None or len(df) < 5:
        return False, 0, -1

    n = len(df)
    pb_idx = -1

    # Search from most recent closed bar backwards
    for i in range(n - 2, 0, -1):
        if i + 1 >= n or i < 1:
            continue
        cc = df['Close'].iloc[i]
        ph = df['High'].iloc[i - 1]
        pl = df['Low'].iloc[i - 1]

        if bullish and cc > ph:
            pb_idx = i
            break
        if not bullish and cc < pl:
            pb_idx = i
            break

    if pb_idx == -1:
        return False, 0, -1

    # Calculate pattern line
    if bullish:
        # Lowest low from start to pattern bar
        pattern_line = df['Low'].iloc[:pb_idx + 1].min()
    else:
        # Highest high from start to pattern bar
        pattern_line = df['High'].iloc[:pb_idx + 1].max()

    return True, float(pattern_line), pb_idx


def search_sweep(df, pattern_line, bullish, pattern_idx):
    """
    MQL5 SearchForSweep — find sweep of pattern line after pattern.
    """
    if df is None or pattern_idx < 0:
        return False, -1

    n = len(df)
    start = pattern_idx + 1  # Start searching after pattern

    for i in range(start, n):
        if bullish and df['Low'].iloc[i] < pattern_line:
            return True, i
        if not bullish and df['High'].iloc[i] > pattern_line:
            return True, i

    return False, -1


def search_entry_signal(df, sweep_idx, bullish):
    """
    MQL5 SearchForEntrySignalAndProtectedLevel — find entry after sweep.
    """
    if df is None or sweep_idx < 0:
        return False, -1

    n = len(df)
    for i in range(sweep_idx + 1, n):
        if i < 1:
            continue
        cc = df['Close'].iloc[i]
        ph = df['High'].iloc[i - 1]
        pl = df['Low'].iloc[i - 1]

        if bullish and cc > ph:
            return True, i
        if not bullish and cc < pl:
            return True, i

    return False, -1


def scan_symbol(name, yf_ticker, tpl):
    """Full NAZ OMIC scan for one symbol — matches MQL5 EA logic"""
    try:
        # Fetch data for all required timeframes
        ctx_df = fetch_ohlc(yf_ticker, tpl["ctx_arrow"], tpl["ctx_arrow_period"])
        val_df = fetch_ohlc(yf_ticker, tpl["val"], tpl["val_period"])
        entry_df = fetch_ohlc(yf_ticker, tpl["entry"], tpl["entry_period"])

        if ctx_df is None or val_df is None or entry_df is None:
            return None
        if len(ctx_df) < 10 or len(val_df) < 10 or len(entry_df) < (MENT_BARS_BACK + 20):
            return None

        # ── Step 1: Context bias (Arrow + EMA) ──
        ctx_arrow = check_arrow(ctx_df)
        ctx_ema = check_ema_state(ctx_df)

        bullish = (ctx_arrow == "UP" and ctx_ema == "ACC")
        bearish = (ctx_arrow == "DOWN" and ctx_ema == "DISS")

        if not bullish and not bearish:
            return None

        # ── Step 2: Validation EMA (Template 3 logic) ──
        val_ema = check_ema_state(val_df)
        if bullish and val_ema != "ACC":
            return None
        if bearish and val_ema != "DISS":
            return None

        # ── Step 3: Pattern search on entry TF ──
        found, pattern_line, pat_idx = search_pattern(entry_df, bullish)
        if not found or pattern_line <= 0:
            return None

        # ── Step 4: Sweep detection ──
        swept, sweep_idx = search_sweep(entry_df, pattern_line, bullish, pat_idx)
        if not swept:
            return None

        # ── Step 5: Entry signal after sweep ──
        entry_found, entry_idx = search_entry_signal(entry_df, sweep_idx, bullish)
        if not entry_found:
            return None

        # ── Step 6: Protected level ──
        if bullish:
            protected = float(entry_df['Low'].iloc[:entry_idx + 1].min())
            current_price = float(entry_df['Close'].iloc[-1])
            if current_price < protected:
                return None  # Protected level violated
        else:
            protected = float(entry_df['High'].iloc[:entry_idx + 1].max())
            current_price = float(entry_df['Close'].iloc[-1])
            if current_price > protected:
                return None  # Protected level violated

        # ── Step 7: Ment Block alignment ──
        ment_trend = calc_ment_block(entry_df, MENT_BARS_BACK)

        if bullish and ment_trend != 1:
            return None  # Ment not aligned
        if bearish and ment_trend != -1:
            return None  # Ment not aligned

        # ── QUALIFIED ──
        direction = "BUY" if bullish else "SELL"
        ment_label = "BULL" if ment_trend == 1 else "BEAR"
        digits = 5 if current_price < 10 else (3 if current_price < 1000 else 2)

        return {
            "symbol": name,
            "direction": direction,
            "ment": ment_label,
            "status": "READY",
            "price": round(current_price, digits),
            "protected_level": round(protected, digits),
        }

    except Exception as e:
        return None


def run_scan(asset_class, template_name):
    """Run full scan for an asset class and template"""
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
        try:
            result = scan_symbol(name, yf_ticker, tpl)
            if result:
                signals.append(result)
        except:
            errors += 1

    data = {
        "scanner_version": "3.15-web",
        "asset_class": asset_class,
        "template": template_name,
        "timeframes": tpl["label"],
        "total_symbols": len(symbols),
        "symbols_scanned": scanned,
        "qualifying_count": len(signals),
        "errors": errors,
        "last_scan": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "signals": signals,
    }

    set_cached(asset_class, template_name, data)
    return data


# ═══════════════════════════════════════════════════════════════
# API
# ═══════════════════════════════════════════════════════════════
@app.route('/api/scan')
def api_scan():
    asset = request.args.get('asset', 'Forex&Metals')
    template = request.args.get('template', 'Weekly')
    force = request.args.get('force', '')
    if force:
        key = f"{asset}_{template}"
        with cache_lock:
            scan_cache.pop(key, None)
    try:
        data = run_scan(asset, template)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e), "signals": []})

@app.route('/api/symbols')
def api_symbols():
    asset = request.args.get('asset', 'Forex&Metals')
    syms = list(SYMBOLS.get(asset, {}).keys())
    return jsonify({"asset": asset, "symbols": syms, "count": len(syms)})

@app.route('/api/status')
def api_status():
    counts = {k: len(v) for k, v in SYMBOLS.items()}
    return jsonify({"status": "running", "version": "3.15-web", "symbols": counts, "cache_entries": len(scan_cache)})

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('static', path)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5555))
    total = sum(len(v) for v in SYMBOLS.values())
    print(f"NAZ OMIC Scanner Web v2")
    print(f"Symbols: Forex&Metals={len(SYMBOLS['Forex&Metals'])}, Crypto={len(SYMBOLS['Crypto'])}, Stocks={len(SYMBOLS['Stocks'])} (Total: {total})")
    print(f"http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)
