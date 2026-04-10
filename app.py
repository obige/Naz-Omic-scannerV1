"""
NAZ OMIC Scanner – Standalone Web App v3
Background scanning thread — no timeouts.
"""
import os, json, time, threading, traceback
from datetime import datetime
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
        "EURUSD":"EURUSD=X","GBPUSD":"GBPUSD=X","USDJPY":"USDJPY=X","USDCHF":"USDCHF=X",
        "AUDUSD":"AUDUSD=X","NZDUSD":"NZDUSD=X","USDCAD":"USDCAD=X",
        "EURJPY":"EURJPY=X","GBPJPY":"GBPJPY=X","EURGBP":"EURGBP=X","EURAUD":"EURAUD=X",
        "EURCAD":"EURCAD=X","EURCHF":"EURCHF=X","EURNZD":"EURNZD=X",
        "GBPAUD":"GBPAUD=X","GBPCAD":"GBPCAD=X","GBPCHF":"GBPCHF=X","GBPNZD":"GBPNZD=X",
        "AUDJPY":"AUDJPY=X","AUDCAD":"AUDCAD=X","AUDCHF":"AUDCHF=X","AUDNZD":"AUDNZD=X",
        "NZDJPY":"NZDJPY=X","NZDCAD":"NZDCAD=X","NZDCHF":"NZDCHF=X",
        "CADJPY":"CADJPY=X","CADCHF":"CADCHF=X","CHFJPY":"CHFJPY=X",
        "USDZAR":"USDZAR=X","USDMXN":"USDMXN=X","USDTRY":"USDTRY=X",
        "USDSEK":"USDSEK=X","USDNOK":"USDNOK=X","USDSGD":"USDSGD=X",
        "USDPLN":"USDPLN=X","EURPLN":"EURPLN=X","EURTRY":"EURTRY=X",
        "EURSEK":"EURSEK=X","EURNOK":"EURNOK=X",
        "XAUUSD":"GC=F","XAGUSD":"SI=F",
    },
    "Crypto": {
        "BTCUSD":"BTC-USD","ETHUSD":"ETH-USD","BNBUSD":"BNB-USD","SOLUSD":"SOL-USD",
        "XRPUSD":"XRP-USD","ADAUSD":"ADA-USD","DOGEUSD":"DOGE-USD","DOTUSD":"DOT-USD",
        "AVAXUSD":"AVAX-USD","LINKUSD":"LINK-USD","MATICUSD":"MATIC-USD","SHIBUSD":"SHIB-USD",
        "UNIUSD":"UNI-USD","LTCUSD":"LTC-USD","BCHUSD":"BCH-USD","ATOMUSD":"ATOM-USD",
        "XLMUSD":"XLM-USD","NEARUSD":"NEAR-USD","ALGOUSD":"ALGO-USD","ICPUSD":"ICP-USD",
        "FILUSD":"FIL-USD","TRXUSD":"TRX-USD","ETCUSD":"ETC-USD","EOSUSD":"EOS-USD",
        "HBARUSD":"HBAR-USD","AAVEUSD":"AAVE-USD","FTMUSD":"FTM-USD",
        "OPUSD":"OP-USD","SUIUSD":"SUI20947-USD","ARBUSD":"ARB11841-USD",
    },
    "Stocks": {
        "AAPL":"AAPL","MSFT":"MSFT","GOOGL":"GOOGL","AMZN":"AMZN","TSLA":"TSLA",
        "NVDA":"NVDA","META":"META","NFLX":"NFLX","AMD":"AMD","INTC":"INTC",
        "CRM":"CRM","ORCL":"ORCL","ADBE":"ADBE","CSCO":"CSCO","QCOM":"QCOM",
        "AVGO":"AVGO","TXN":"TXN","MU":"MU","SHOP":"SHOP","PYPL":"PYPL",
        "UBER":"UBER","ABNB":"ABNB","PLTR":"PLTR","COIN":"COIN",
        "JPM":"JPM","BAC":"BAC","WFC":"WFC","GS":"GS","MS":"MS","V":"V","MA":"MA",
        "JNJ":"JNJ","UNH":"UNH","PFE":"PFE","ABBV":"ABBV","MRK":"MRK","LLY":"LLY",
        "WMT":"WMT","KO":"KO","PEP":"PEP","MCD":"MCD","NKE":"NKE","DIS":"DIS",
        "BA":"BA","CAT":"CAT","GE":"GE","HON":"HON",
        "XOM":"XOM","CVX":"CVX","COP":"COP",
    },
}

TEMPLATES = {
    "Monthly": {"ctx":"1mo","entry":"1d", "ctx_arrow":"1mo","val":"1wk",
                "ctx_period":"5y","entry_period":"1y","val_period":"2y","label":"MN1 / D1 / MN1 / W1"},
    "Weekly":  {"ctx":"1wk","entry":"1d", "ctx_arrow":"1wk","val":"1d",
                "ctx_period":"2y","entry_period":"6mo","val_period":"1y","label":"W1 / H4 / W1 / D1"},
    "Daily":   {"ctx":"1d", "entry":"1h", "ctx_arrow":"1d", "val":"1d",
                "ctx_period":"1y","entry_period":"30d","val_period":"6mo","label":"D1 / H1 / D1 / H4"},
    "4HR":     {"ctx":"1d", "entry":"30m","ctx_arrow":"1d", "val":"1h",
                "ctx_period":"6mo","entry_period":"30d","val_period":"30d","label":"H4 / M15 / H4 / M30"},
}

MENT_BARS_BACK = 30

# ═══════════════════════════════════════════════════════════════
# SCAN RESULTS STORE (thread-safe)
# ═══════════════════════════════════════════════════════════════
scan_results = {}    # key: "asset_template" → result dict
scan_status = {}     # key: "asset_template" → {"scanning": bool, "last_scan": time}
store_lock = threading.Lock()

def get_result(asset, tpl):
    key = f"{asset}_{tpl}"
    with store_lock:
        return scan_results.get(key)

def set_result(asset, tpl, data):
    key = f"{asset}_{tpl}"
    with store_lock:
        scan_results[key] = data
        scan_status[key] = {"scanning": False, "last_scan": time.time()}

def is_scanning(asset, tpl):
    key = f"{asset}_{tpl}"
    with store_lock:
        st = scan_status.get(key, {})
        return st.get("scanning", False)

def is_stale(asset, tpl, max_age=180):
    key = f"{asset}_{tpl}"
    with store_lock:
        st = scan_status.get(key, {})
        last = st.get("last_scan", 0)
        return (time.time() - last) > max_age

def mark_scanning(asset, tpl):
    key = f"{asset}_{tpl}"
    with store_lock:
        scan_status[key] = {"scanning": True, "last_scan": scan_status.get(key, {}).get("last_scan", 0)}

# ═══════════════════════════════════════════════════════════════
# DATA FETCHING (with timeout per symbol)
# ═══════════════════════════════════════════════════════════════
def fetch_ohlc(yf_ticker, interval, period):
    try:
        tk = yf.Ticker(yf_ticker)
        df = tk.history(period=period, interval=interval, timeout=10)
        if df is None or df.empty or len(df) < 5:
            return None
        df = df.reset_index()
        if 'Datetime' in df.columns:
            df = df.rename(columns={'Datetime': 'Date'})
        return df[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']].copy()
    except:
        return None

# ═══════════════════════════════════════════════════════════════
# SCANNING LOGIC — MATCHES MQL5 EA
# ═══════════════════════════════════════════════════════════════
def check_arrow(df):
    if df is None or len(df) < 3:
        return "None"
    n = len(df)
    limit = min(n - 1, 100)
    for i in range(1, limit + 1):
        bi = n - 1 - i
        pi = bi - 1
        if bi < 0 or pi < 0:
            break
        cc = df['Close'].iloc[bi]
        ph = df['High'].iloc[pi]
        pl = df['Low'].iloc[pi]
        if cc > ph: return "UP"
        if cc < pl: return "DOWN"
    return "None"

def check_ema_state(df, p1=10, p2=20):
    if df is None or len(df) < p2 + 5:
        return "N/A"
    closes = df['Close'].values
    es = pd.Series(closes).ewm(span=p1, adjust=False).mean().values
    el = pd.Series(closes).ewm(span=p2, adjust=False).mean().values
    if es[-1] == 0 or el[-1] == 0: return "N/A"
    if es[-1] > el[-1]: return "ACC"
    if es[-1] < el[-1]: return "DISS"
    return "EQL"

def calc_ment_block(df, lookback=30):
    if df is None or len(df) < lookback + 10:
        return 0
    H = df['High'].values; L = df['Low'].values; C = df['Close'].values; n = len(df)
    lo_i = 0; hi_i = 0
    for k in range(1, min(lookback, n)):
        if L[k] < L[lo_i]: lo_i = k
        if H[k] > H[hi_i]: hi_i = k
    mL = L[lo_i]; mH = H[hi_i]; trend = 0
    for i in range(lookback, n):
        if C[i] >= mH:
            mH = H[i]; lL = L[i]
            for j in range(1, lookback):
                idx = i - j
                if idx < 0: break
                if L[idx] < lL: lL = L[idx]
                if idx > 0 and C[idx] < L[idx-1]: mL = min(L[idx], lL); break
            trend = 1
        if C[i] <= mL:
            mL = L[i]; lH = H[i]
            for j in range(1, lookback):
                idx = i - j
                if idx < 0: break
                if H[idx] > lH: lH = H[idx]
                if idx > 0 and C[idx] > H[idx-1]: mH = max(H[idx], lH); break
            trend = -1
    return trend

def search_pattern(df, bullish):
    if df is None or len(df) < 5: return False, 0, -1
    n = len(df)
    for i in range(n - 2, 0, -1):
        if i < 1: continue
        cc = df['Close'].iloc[i]; ph = df['High'].iloc[i-1]; pl = df['Low'].iloc[i-1]
        if bullish and cc > ph:
            return True, float(df['Low'].iloc[:i+1].min()), i
        if not bullish and cc < pl:
            return True, float(df['High'].iloc[:i+1].max()), i
    return False, 0, -1

def search_sweep(df, pline, bullish, pidx):
    if df is None or pidx < 0: return False, -1
    for i in range(pidx + 1, len(df)):
        if bullish and df['Low'].iloc[i] < pline: return True, i
        if not bullish and df['High'].iloc[i] > pline: return True, i
    return False, -1

def search_entry(df, sidx, bullish):
    if df is None or sidx < 0: return False, -1
    for i in range(sidx + 1, len(df)):
        if i < 1: continue
        cc = df['Close'].iloc[i]; ph = df['High'].iloc[i-1]; pl = df['Low'].iloc[i-1]
        if bullish and cc > ph: return True, i
        if not bullish and cc < pl: return True, i
    return False, -1

def scan_symbol(name, yf_ticker, tpl):
    try:
        ctx_df = fetch_ohlc(yf_ticker, tpl["ctx_arrow"], tpl["ctx_period"])
        val_df = fetch_ohlc(yf_ticker, tpl["val"], tpl["val_period"])
        entry_df = fetch_ohlc(yf_ticker, tpl["entry"], tpl["entry_period"])
        if ctx_df is None or val_df is None or entry_df is None: return None
        if len(ctx_df) < 10 or len(val_df) < 10 or len(entry_df) < (MENT_BARS_BACK + 20): return None

        ca = check_arrow(ctx_df); ce = check_ema_state(ctx_df)
        bull = (ca == "UP" and ce == "ACC"); bear = (ca == "DOWN" and ce == "DISS")
        if not bull and not bear: return None

        ve = check_ema_state(val_df)
        if bull and ve != "ACC": return None
        if bear and ve != "DISS": return None

        found, pline, pidx = search_pattern(entry_df, bull)
        if not found or pline <= 0: return None

        swept, sidx = search_sweep(entry_df, pline, bull, pidx)
        if not swept: return None

        efound, eidx = search_entry(entry_df, sidx, bull)
        if not efound: return None

        if bull:
            prot = float(entry_df['Low'].iloc[:eidx+1].min())
            price = float(entry_df['Close'].iloc[-1])
            if price < prot: return None
        else:
            prot = float(entry_df['High'].iloc[:eidx+1].max())
            price = float(entry_df['Close'].iloc[-1])
            if price > prot: return None

        mt = calc_ment_block(entry_df, MENT_BARS_BACK)
        if bull and mt != 1: return None
        if bear and mt != -1: return None

        d = 5 if price < 10 else (3 if price < 1000 else 2)
        return {"symbol": name, "direction": "BUY" if bull else "SELL",
                "ment": "BULL" if mt == 1 else "BEAR", "status": "READY",
                "price": round(price, d), "protected_level": round(prot, d)}
    except:
        return None

# ═══════════════════════════════════════════════════════════════
# BACKGROUND SCANNER THREAD
# ═══════════════════════════════════════════════════════════════
def scan_in_background(asset_class, template_name):
    """Run scan in a separate thread — never blocks the web server"""
    if is_scanning(asset_class, template_name):
        return  # Already scanning

    def _run():
        mark_scanning(asset_class, template_name)
        symbols = SYMBOLS.get(asset_class, {})
        tpl = TEMPLATES.get(template_name)
        if not tpl:
            set_result(asset_class, template_name, {"error": "Invalid template", "signals": []})
            return

        signals = []
        scanned = 0
        print(f"[SCAN] Starting {asset_class}/{template_name} ({len(symbols)} symbols)...")

        for name, yf_ticker in symbols.items():
            scanned += 1
            try:
                result = scan_symbol(name, yf_ticker, tpl)
                if result:
                    signals.append(result)
                    print(f"  ✓ {name} → {result['direction']}")
            except:
                pass

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
        set_result(asset_class, template_name, data)
        print(f"[SCAN] Done {asset_class}/{template_name}: {len(signals)} qualifying out of {scanned}")

    t = threading.Thread(target=_run, daemon=True)
    t.start()

# ═══════════════════════════════════════════════════════════════
# API
# ═══════════════════════════════════════════════════════════════
@app.route('/api/scan')
def api_scan():
    asset = request.args.get('asset', 'Forex&Metals')
    template = request.args.get('template', 'Weekly')
    force = request.args.get('force', '')

    # Force clear cache
    if force:
        key = f"{asset}_{template}"
        with store_lock:
            scan_results.pop(key, None)
            scan_status.pop(key, None)

    # Check if we have cached results
    result = get_result(asset, template)

    if result and not is_stale(asset, template):
        # Return cached, trigger background refresh if getting old (>90s)
        key = f"{asset}_{template}"
        with store_lock:
            st = scan_status.get(key, {})
            age = time.time() - st.get("last_scan", 0)
        if age > 90:
            scan_in_background(asset, template)
        return jsonify(result)

    # No cache or stale — start background scan
    if not is_scanning(asset, template):
        scan_in_background(asset, template)

    # If we have old results, return them while new scan runs
    if result:
        result["_note"] = "Refreshing in background..."
        return jsonify(result)

    # No results at all yet — return scanning status
    return jsonify({
        "scanner_version": "3.15-web",
        "asset_class": asset,
        "template": template,
        "total_symbols": len(SYMBOLS.get(asset, {})),
        "qualifying_count": 0,
        "scanning": True,
        "last_scan": "Scanning now...",
        "signals": [],
        "_note": "First scan in progress. Refresh in 30-60 seconds."
    })

@app.route('/api/symbols')
def api_symbols():
    asset = request.args.get('asset', 'Forex&Metals')
    return jsonify({"asset": asset, "symbols": list(SYMBOLS.get(asset, {}).keys()), "count": len(SYMBOLS.get(asset, {}))})

@app.route('/api/status')
def api_status():
    counts = {k: len(v) for k, v in SYMBOLS.items()}
    active = []
    with store_lock:
        for k, v in scan_status.items():
            if v.get("scanning"):
                active.append(k)
    return jsonify({"status": "running", "version": "3.15-web", "symbols": counts,
                    "total": sum(counts.values()), "active_scans": active,
                    "cached_results": len(scan_results)})

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('static', path)

# ═══════════════════════════════════════════════════════════════
# STARTUP — pre-scan popular combinations
# ═══════════════════════════════════════════════════════════════
def startup_scans():
    """Pre-scan the most popular combinations on startup"""
    time.sleep(5)  # Let the server start first
    print("[STARTUP] Pre-scanning popular combinations...")
    for tpl in ["Weekly", "Daily"]:
        for asset in ["Forex&Metals", "Crypto", "Stocks"]:
            scan_in_background(asset, tpl)
            time.sleep(2)  # Stagger to avoid overwhelming yfinance

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5555))
    total = sum(len(v) for v in SYMBOLS.values())
    print(f"NAZ OMIC Scanner Web v3")
    print(f"Forex&Metals: {len(SYMBOLS['Forex&Metals'])} | Crypto: {len(SYMBOLS['Crypto'])} | Stocks: {len(SYMBOLS['Stocks'])} | Total: {total}")
    print(f"http://localhost:{port}")
    # Start background pre-scan
    threading.Thread(target=startup_scans, daemon=True).start()
    app.run(host='0.0.0.0', port=port, debug=False)
else:
    # Running under gunicorn
    total = sum(len(v) for v in SYMBOLS.values())
    print(f"NAZ OMIC Scanner Web v3 | {total} symbols")
    threading.Thread(target=startup_scans, daemon=True).start()
