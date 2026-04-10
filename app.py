"""
NAZ OMIC Scanner – Web App v4
Lean build for Render free tier. No startup scan.
Scans only when user requests. Background threads.
"""
import os, time, threading
from datetime import datetime
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

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
        "AVAXUSD":"AVAX-USD","LINKUSD":"LINK-USD","SHIBUSD":"SHIB-USD",
        "UNIUSD":"UNI-USD","LTCUSD":"LTC-USD","BCHUSD":"BCH-USD","ATOMUSD":"ATOM-USD",
        "XLMUSD":"XLM-USD","NEARUSD":"NEAR-USD","ICPUSD":"ICP-USD",
        "TRXUSD":"TRX-USD","ETCUSD":"ETC-USD","HBARUSD":"HBAR-USD",
        "AAVEUSD":"AAVE-USD","OPUSD":"OP-USD",
    },
    "Stocks": {
        "AAPL":"AAPL","MSFT":"MSFT","GOOGL":"GOOGL","AMZN":"AMZN","TSLA":"TSLA",
        "NVDA":"NVDA","META":"META","NFLX":"NFLX","AMD":"AMD","INTC":"INTC",
        "CRM":"CRM","ORCL":"ORCL","ADBE":"ADBE","CSCO":"CSCO","QCOM":"QCOM",
        "AVGO":"AVGO","TXN":"TXN","MU":"MU","PYPL":"PYPL",
        "UBER":"UBER","PLTR":"PLTR","COIN":"COIN",
        "JPM":"JPM","BAC":"BAC","GS":"GS","V":"V","MA":"MA",
        "JNJ":"JNJ","UNH":"UNH","PFE":"PFE","LLY":"LLY",
        "WMT":"WMT","KO":"KO","MCD":"MCD","DIS":"DIS",
        "BA":"BA","CAT":"CAT","GE":"GE",
        "XOM":"XOM","CVX":"CVX",
    },
}

TEMPLATES = {
    "Monthly": {"ctx":"1mo","entry":"1d","ctx_arrow":"1mo","val":"1wk",
                "ctx_period":"5y","entry_period":"1y","val_period":"2y",
                "label":"MN1 / D1 / MN1 / W1"},
    "Weekly":  {"ctx":"1wk","entry":"1d","ctx_arrow":"1wk","val":"1d",
                "ctx_period":"2y","entry_period":"6mo","val_period":"1y",
                "label":"W1 / H4 / W1 / D1"},
    "Daily":   {"ctx":"1d","entry":"1h","ctx_arrow":"1d","val":"1d",
                "ctx_period":"1y","entry_period":"30d","val_period":"6mo",
                "label":"D1 / H1 / D1 / H4"},
    "4HR":     {"ctx":"1d","entry":"30m","ctx_arrow":"1d","val":"1h",
                "ctx_period":"6mo","entry_period":"30d","val_period":"30d",
                "label":"H4 / M15 / H4 / M30"},
}

MENT_BARS = 30

# ═══════════════════════════════════════════════════════════════
# RESULTS STORE
# ═══════════════════════════════════════════════════════════════
results = {}
status = {}
lock = threading.Lock()

def get_res(a, t):
    with lock:
        return results.get(f"{a}_{t}")

def set_res(a, t, d):
    with lock:
        results[f"{a}_{t}"] = d
        status[f"{a}_{t}"] = {"scanning": False, "ts": time.time()}

def is_busy(a, t):
    with lock:
        return status.get(f"{a}_{t}", {}).get("scanning", False)

def is_old(a, t, age=180):
    with lock:
        ts = status.get(f"{a}_{t}", {}).get("ts", 0)
        return (time.time() - ts) > age

def mark_busy(a, t):
    with lock:
        status[f"{a}_{t}"] = {"scanning": True, "ts": status.get(f"{a}_{t}", {}).get("ts", 0)}

# ═══════════════════════════════════════════════════════════════
# DATA FETCH — lazy import yfinance (saves startup memory)
# ═══════════════════════════════════════════════════════════════
_yf = None

def get_yf():
    global _yf
    if _yf is None:
        import yfinance
        _yf = yfinance
    return _yf

def fetch(ticker, interval, period):
    try:
        yf = get_yf()
        df = yf.Ticker(ticker).history(period=period, interval=interval, timeout=10)
        if df is None or df.empty or len(df) < 5:
            return None
        df = df.reset_index()
        if 'Datetime' in df.columns:
            df = df.rename(columns={'Datetime': 'Date'})
        return df[['Date','Open','High','Low','Close','Volume']].copy()
    except:
        return None

# ═══════════════════════════════════════════════════════════════
# SCAN LOGIC — matches MQL5 EA
# ═══════════════════════════════════════════════════════════════
def arrow(df):
    if df is None or len(df) < 3:
        return "None"
    n = len(df)
    for i in range(1, min(n - 1, 100) + 1):
        bi = n - 1 - i
        pi = bi - 1
        if pi < 0:
            break
        cc = df['Close'].iloc[bi]
        if cc > df['High'].iloc[pi]:
            return "UP"
        if cc < df['Low'].iloc[pi]:
            return "DOWN"
    return "None"

def ema_state(df, s=10, l=20):
    if df is None or len(df) < l + 5:
        return "N/A"
    import pandas as pd
    c = df['Close'].values
    es = pd.Series(c).ewm(span=s, adjust=False).mean().values[-1]
    el = pd.Series(c).ewm(span=l, adjust=False).mean().values[-1]
    if es == 0 or el == 0:
        return "N/A"
    if es > el:
        return "ACC"
    if es < el:
        return "DISS"
    return "EQL"

def ment(df, lb=30):
    if df is None or len(df) < lb + 10:
        return 0
    H = df['High'].values
    L = df['Low'].values
    C = df['Close'].values
    n = len(df)
    lo = 0
    hi = 0
    for k in range(1, min(lb, n)):
        if L[k] < L[lo]:
            lo = k
        if H[k] > H[hi]:
            hi = k
    mL = L[lo]
    mH = H[hi]
    tr = 0
    for i in range(lb, n):
        if C[i] >= mH:
            mH = H[i]
            lL = L[i]
            for j in range(1, lb):
                x = i - j
                if x < 0:
                    break
                if L[x] < lL:
                    lL = L[x]
                if x > 0 and C[x] < L[x - 1]:
                    mL = min(L[x], lL)
                    break
            tr = 1
        if C[i] <= mL:
            mL = L[i]
            lH = H[i]
            for j in range(1, lb):
                x = i - j
                if x < 0:
                    break
                if H[x] > lH:
                    lH = H[x]
                if x > 0 and C[x] > H[x - 1]:
                    mH = max(H[x], lH)
                    break
            tr = -1
    return tr

def find_pattern(df, bull):
    if df is None or len(df) < 5:
        return False, 0, -1
    n = len(df)
    for i in range(n - 2, 0, -1):
        if i < 1:
            continue
        cc = df['Close'].iloc[i]
        ph = df['High'].iloc[i - 1]
        pl = df['Low'].iloc[i - 1]
        if bull and cc > ph:
            return True, float(df['Low'].iloc[:i + 1].min()), i
        if not bull and cc < pl:
            return True, float(df['High'].iloc[:i + 1].max()), i
    return False, 0, -1

def find_sweep(df, pl, bull, pi):
    if df is None or pi < 0:
        return False, -1
    for i in range(pi + 1, len(df)):
        if bull and df['Low'].iloc[i] < pl:
            return True, i
        if not bull and df['High'].iloc[i] > pl:
            return True, i
    return False, -1

def find_entry(df, si, bull):
    if df is None or si < 0:
        return False, -1
    for i in range(si + 1, len(df)):
        if i < 1:
            continue
        cc = df['Close'].iloc[i]
        if bull and cc > df['High'].iloc[i - 1]:
            return True, i
        if not bull and cc < df['Low'].iloc[i - 1]:
            return True, i
    return False, -1

def scan_one(name, ticker, tpl):
    try:
        ctx = fetch(ticker, tpl["ctx_arrow"], tpl["ctx_period"])
        val = fetch(ticker, tpl["val"], tpl["val_period"])
        ent = fetch(ticker, tpl["entry"], tpl["entry_period"])
        if ctx is None or val is None or ent is None:
            return None
        if len(ctx) < 10 or len(val) < 10 or len(ent) < MENT_BARS + 20:
            return None

        ca = arrow(ctx)
        ce = ema_state(ctx)
        bull = ca == "UP" and ce == "ACC"
        bear = ca == "DOWN" and ce == "DISS"
        if not bull and not bear:
            return None

        ve = ema_state(val)
        if bull and ve != "ACC":
            return None
        if bear and ve != "DISS":
            return None

        ok, pl, pi = find_pattern(ent, bull)
        if not ok or pl <= 0:
            return None

        ok2, si = find_sweep(ent, pl, bull, pi)
        if not ok2:
            return None

        ok3, ei = find_entry(ent, si, bull)
        if not ok3:
            return None

        price = float(ent['Close'].iloc[-1])
        if bull:
            prot = float(ent['Low'].iloc[:ei + 1].min())
            if price < prot:
                return None
        else:
            prot = float(ent['High'].iloc[:ei + 1].max())
            if price > prot:
                return None

        mt = ment(ent, MENT_BARS)
        if bull and mt != 1:
            return None
        if bear and mt != -1:
            return None

        d = 5 if price < 10 else (3 if price < 1000 else 2)
        return {
            "symbol": name,
            "direction": "BUY" if bull else "SELL",
            "ment": "BULL" if mt == 1 else "BEAR",
            "status": "READY",
            "price": round(price, d),
            "protected_level": round(prot, d),
        }
    except:
        return None

# ═══════════════════════════════════════════════════════════════
# BACKGROUND SCANNER
# ═══════════════════════════════════════════════════════════════
def scan_bg(asset, template):
    if is_busy(asset, template):
        return

    def _run():
        mark_busy(asset, template)
        syms = SYMBOLS.get(asset, {})
        tpl = TEMPLATES.get(template)
        if not tpl:
            set_res(asset, template, {"error": "Bad template", "signals": []})
            return

        sigs = []
        count = 0
        print(f"[SCAN] {asset}/{template} ({len(syms)} symbols)...")

        for name, ticker in syms.items():
            count += 1
            try:
                r = scan_one(name, ticker, tpl)
                if r:
                    sigs.append(r)
                    print(f"  + {name} {r['direction']}")
            except:
                pass

        data = {
            "scanner_version": "3.15-web",
            "asset_class": asset,
            "template": template,
            "timeframes": tpl["label"],
            "total_symbols": len(syms),
            "symbols_scanned": count,
            "qualifying_count": len(sigs),
            "last_scan": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            "signals": sigs,
        }
        set_res(asset, template, data)
        print(f"[DONE] {asset}/{template}: {len(sigs)}/{count} qualifying")

    threading.Thread(target=_run, daemon=True).start()

# ═══════════════════════════════════════════════════════════════
# API
# ═══════════════════════════════════════════════════════════════
@app.route('/api/scan')
def api_scan():
    asset = request.args.get('asset', 'Forex&Metals')
    template = request.args.get('template', 'Weekly')
    force = request.args.get('force', '')

    if force:
        with lock:
            results.pop(f"{asset}_{template}", None)
            status.pop(f"{asset}_{template}", None)

    res = get_res(asset, template)

    # Have fresh results
    if res and not is_old(asset, template):
        # Trigger background refresh if > 90s old
        with lock:
            ts = status.get(f"{asset}_{template}", {}).get("ts", 0)
        if time.time() - ts > 90 and not is_busy(asset, template):
            scan_bg(asset, template)
        return jsonify(res)

    # Start scan if not already running
    if not is_busy(asset, template):
        scan_bg(asset, template)

    # Return old results while scanning
    if res:
        res["_note"] = "Refreshing in background..."
        return jsonify(res)

    # Nothing yet
    return jsonify({
        "scanner_version": "3.15-web",
        "asset_class": asset,
        "template": template,
        "total_symbols": len(SYMBOLS.get(asset, {})),
        "qualifying_count": 0,
        "scanning": True,
        "last_scan": "Scanning now...",
        "signals": [],
        "_note": "First scan in progress. Results appear in 30-60 seconds."
    })

@app.route('/api/symbols')
def api_symbols():
    asset = request.args.get('asset', 'Forex&Metals')
    return jsonify({"asset": asset, "symbols": list(SYMBOLS.get(asset, {}).keys()),
                    "count": len(SYMBOLS.get(asset, {}))})

@app.route('/api/status')
def api_status():
    counts = {k: len(v) for k, v in SYMBOLS.items()}
    busy = []
    with lock:
        for k, v in status.items():
            if v.get("scanning"):
                busy.append(k)
    return jsonify({"status": "running", "version": "3.15-web-v4",
                    "symbols": counts, "total": sum(counts.values()),
                    "active_scans": busy, "cached": len(results)})

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('static', path)

# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
total = sum(len(v) for v in SYMBOLS.values())
print(f"NAZ OMIC Scanner v4 | {total} symbols | Ready")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5555))
    print(f"http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)
