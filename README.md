# NAZ OMIC Scanner – Standalone Web App

A public website anyone can access to scan Forex, Crypto, and Stocks.
No MT5 needed. No setup for users. Just share the link.

## What's Inside

```
naz_omic_web/
  ├── app.py              ← Python server (Flask + scanning logic)
  ├── requirements.txt    ← Dependencies
  ├── render.yaml         ← Auto-deploy config for Render.com
  └── static/
      └── index.html      ← The website
```

## How It Works

- **Backend (app.py)**: Fetches free market data from Yahoo Finance, runs the NAZ OMIC scanning algorithm, serves results via API
- **Frontend (index.html)**: Beautiful dashboard with asset/template buttons, TradingView charts embedded for free
- **Charts**: Real TradingView charts with all indicators, drawing tools, timeframes — no API key needed

## Deploy to Render.com (FREE – recommended)

1. **Create a GitHub account** (if you don't have one): https://github.com
2. **Create a new repository**: Click "New" → name it `naz-omic-scanner`
3. **Upload all files** from this folder to the repository
4. **Go to Render.com**: https://render.com → Sign up free with GitHub
5. **New → Web Service** → Connect your GitHub repo
6. Render auto-detects the `render.yaml` and configures everything
7. Click **Deploy** → Wait 2-3 minutes
8. You get a URL like `https://naz-omic-scanner.onrender.com`
9. **Share that link with anyone!**

## Deploy to Railway.app (alternative)

1. Go to https://railway.app → Sign in with GitHub
2. New Project → Deploy from GitHub repo
3. It auto-detects Python and deploys
4. You get a public URL

## Run Locally (for testing)

```bash
# Install Python 3.8+ from python.org
pip install -r requirements.txt
python app.py
# Open http://localhost:5555
```

## How Scanning Works

For each symbol, the scanner checks:
1. **Arrow condition** on Context TF (close breaks previous candle range)
2. **EMA 10/20 alignment** on Context TF (ACC = bullish, DISS = bearish)
3. **Validation EMA** must agree (Template 3 logic)
4. **Pattern confirmation** on Entry TF (liquidity grab)
5. **Sweep detection** (price takes out the pattern line)
6. **Entry signal** after sweep (close breaks previous candle)
7. **Protected level** not violated
8. **Ment Block** trend alignment

Only symbols passing ALL steps appear as qualifying.

## Templates

| Template | Context TF | Entry TF | Arrow/EMA | Validation |
|----------|-----------|----------|-----------|------------|
| Monthly  | MN1       | D1       | MN1       | W1         |
| Weekly   | W1        | H4       | W1        | D1         |
| Daily    | D1        | H1       | D1        | H4         |
| 4HR      | H4        | M15      | H4        | M30        |

## Notes

- Scan results are cached for 2 minutes to avoid rate limits
- Yahoo Finance free tier has some limitations on intraday data
- TradingView chart widget is completely free (embedded, not API)
- The free Render.com plan may sleep after 15 min of inactivity (first request takes ~30 sec to wake up)
