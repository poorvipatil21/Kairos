import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import yfinance as yf
import pandas as pd
import numpy as np
import io, csv, time, json
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional
from pydantic import BaseModel

from api import quant as Q
from api import trading as T

from db.database import load_latest
try:
    from db.database import load_history
except ImportError:
    load_history = None

def _fix_metrics(r):
    """Recompute Sharpe and max drawdown from the stored equity curve so every
    strategy gets its own correct values (the engine was writing one shared Sharpe)."""
    eq = r.get("equity")
    if isinstance(eq, str):
        try: eq = json.loads(eq); r["equity"] = eq
        except Exception: eq = None
    if not eq or len(eq) < 3:
        return r
    vals = np.array([e[1] if isinstance(e, (list, tuple)) else e for e in eq], dtype=float)
    vals = vals[vals > 0]
    if len(vals) < 3:
        return r
    rets = np.diff(vals) / vals[:-1]
    sd = rets.std(ddof=1)
    r["sharpe_engine"] = r.get("sharpe")
    r["sharpe"] = float(rets.mean() / sd * np.sqrt(252)) if sd > 0 else 0.0
    peak = np.maximum.accumulate(vals)
    r["max_dd"] = float(((peak - vals) / peak).max())
    return r

def get_all_results():
    rows = load_latest()
    if isinstance(rows, dict):
        rows = list(rows.values())
    rows = [_fix_metrics(dict(r)) for r in (rows or [])]
    return sorted(rows, key=lambda x: x.get("sharpe", 0), reverse=True)

app = FastAPI(title="Kairos API")
T.init()
_DASH_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dashboard")
app.mount("/static", StaticFiles(directory=_DASH_DIR), name="static")

INDIA_LARGE_CAP = [
    "RELIANCE.NS","TCS.NS","HDFCBANK.NS","INFY.NS","ICICIBANK.NS",
    "HINDUNILVR.NS","ITC.NS","SBIN.NS","BAJFINANCE.NS","BHARTIARTL.NS",
    "KOTAKBANK.NS","AXISBANK.NS","LT.NS","WIPRO.NS","ULTRACEMCO.NS",
    "TITAN.NS","MARUTI.NS","NTPC.NS","POWERGRID.NS","ONGC.NS",
    "HCLTECH.NS","SUNPHARMA.NS","TATAMOTORS.NS","TATASTEEL.NS","NESTLEIND.NS",
    "ADANIPORTS.NS","ADANIENT.NS","JSWSTEEL.NS","INDUSINDBK.NS","GRASIM.NS",
    "DIVISLAB.NS","DRREDDY.NS","APOLLOHOSP.NS","CIPLA.NS","EICHERMOT.NS",
    "BPCL.NS","COALINDIA.NS","HEROMOTOCO.NS","BAJAJFINSV.NS","TECHM.NS",
]
INDIA_MID_CAP = [
    "PIDILITIND.NS","HAVELLS.NS","ZOMATO.NS","PAYTM.NS","NYKAA.NS",
    "DMART.NS","CHOLAFIN.NS","MUTHOOTFIN.NS","PERSISTENT.NS","LTIM.NS",
    "FEDERALBNK.NS","IDFCFIRSTB.NS","BANKBARODA.NS","CANBK.NS","PNB.NS",
    "TATAPOWER.NS","ADANIGREEN.NS","IRCTC.NS","HAL.NS","BEL.NS",
]
INDIA_SYMBOLS = INDIA_LARGE_CAP + INDIA_MID_CAP

USA_MEGA_CAP = ["AAPL","MSFT","GOOGL","AMZN","NVDA","META","TSLA","BRK-B","UNH","JPM"]
USA_LARGE_CAP = [
    "JNJ","V","PG","MA","HD","ADBE","CRM","AMD","INTC","CSCO",
    "VZ","T","ABBV","PFE","MRK","BAC","WFC","GS","MS","BLK",
    "XOM","CVX","LLY","TMO","ABT","DHR","AMGN","GILD","MDT","SYK",
]
USA_MID_CAP = [
    "SNAP","COIN","PLTR","HOOD","SOFI","RIVN","NIO","MARA","RIOT","NET",
    "DDOG","CRWD","ZS","OKTA","TWLO","SNOW","MDB","ABNB","DASH","RBLX",
]
USA_SYMBOLS = USA_MEGA_CAP + USA_LARGE_CAP + USA_MID_CAP

INDIA_SECTORS = {
    "RELIANCE.NS":"Energy","TCS.NS":"IT","HDFCBANK.NS":"Banking","INFY.NS":"IT",
    "ICICIBANK.NS":"Banking","HINDUNILVR.NS":"FMCG","ITC.NS":"FMCG","SBIN.NS":"Banking",
    "BAJFINANCE.NS":"Finance","BHARTIARTL.NS":"Telecom","KOTAKBANK.NS":"Banking",
    "AXISBANK.NS":"Banking","LT.NS":"Infra","WIPRO.NS":"IT","ULTRACEMCO.NS":"Cement",
    "TITAN.NS":"Consumer","MARUTI.NS":"Auto","NTPC.NS":"Energy","POWERGRID.NS":"Energy",
    "ONGC.NS":"Energy","HCLTECH.NS":"IT","SUNPHARMA.NS":"Pharma","TATAMOTORS.NS":"Auto",
    "TATASTEEL.NS":"Metals","NESTLEIND.NS":"FMCG","ADANIPORTS.NS":"Infra",
    "ADANIENT.NS":"Energy","JSWSTEEL.NS":"Metals","INDUSINDBK.NS":"Banking",
    "GRASIM.NS":"Cement","DIVISLAB.NS":"Pharma","DRREDDY.NS":"Pharma",
    "APOLLOHOSP.NS":"Healthcare","CIPLA.NS":"Pharma","EICHERMOT.NS":"Auto",
    "BPCL.NS":"Energy","COALINDIA.NS":"Energy","HEROMOTOCO.NS":"Auto",
    "BAJAJFINSV.NS":"Finance","TECHM.NS":"IT","PIDILITIND.NS":"Consumer",
    "HAVELLS.NS":"Consumer","ZOMATO.NS":"Consumer","PAYTM.NS":"Finance",
    "NYKAA.NS":"Consumer","DMART.NS":"Retail","CHOLAFIN.NS":"Finance",
    "MUTHOOTFIN.NS":"Finance","PERSISTENT.NS":"IT","LTIM.NS":"IT",
    "FEDERALBNK.NS":"Banking","IDFCFIRSTB.NS":"Banking","BANKBARODA.NS":"Banking",
    "CANBK.NS":"Banking","PNB.NS":"Banking","TATAPOWER.NS":"Energy",
    "ADANIGREEN.NS":"Energy","IRCTC.NS":"Travel","HAL.NS":"Defense","BEL.NS":"Defense",
}
USA_SECTORS = {
    "AAPL":"Technology","MSFT":"Technology","GOOGL":"Technology","AMZN":"Consumer",
    "NVDA":"Technology","META":"Technology","TSLA":"Auto","BRK-B":"Finance",
    "UNH":"Healthcare","JPM":"Finance","JNJ":"Healthcare","V":"Finance","PG":"Consumer",
    "MA":"Finance","HD":"Consumer","ADBE":"Technology","CRM":"Technology","AMD":"Technology",
    "INTC":"Technology","CSCO":"Technology","VZ":"Telecom","T":"Telecom","ABBV":"Healthcare",
    "PFE":"Healthcare","MRK":"Healthcare","BAC":"Finance","WFC":"Finance","GS":"Finance",
    "MS":"Finance","BLK":"Finance","XOM":"Energy","CVX":"Energy","LLY":"Healthcare",
    "TMO":"Healthcare","ABT":"Healthcare","DHR":"Healthcare","AMGN":"Healthcare",
    "GILD":"Healthcare","MDT":"Healthcare","SYK":"Healthcare","SNAP":"Technology",
    "COIN":"Finance","PLTR":"Technology","HOOD":"Finance","SOFI":"Finance",
    "RIVN":"Auto","NIO":"Auto","MARA":"Finance","RIOT":"Finance","NET":"Technology",
    "DDOG":"Technology","CRWD":"Technology","ZS":"Technology","OKTA":"Technology",
    "TWLO":"Technology","SNOW":"Technology","MDB":"Technology","ABNB":"Consumer",
    "DASH":"Consumer","RBLX":"Technology",
}

CATEGORIES_INDIA = {
    "All": INDIA_SYMBOLS,
    "Nifty 50": INDIA_LARGE_CAP[:20],
    "Large Cap": INDIA_LARGE_CAP,
    "Mid Cap": INDIA_MID_CAP,
    "Banking": ["HDFCBANK.NS","ICICIBANK.NS","SBIN.NS","KOTAKBANK.NS","AXISBANK.NS","INDUSINDBK.NS","FEDERALBNK.NS","IDFCFIRSTB.NS","BANKBARODA.NS","CANBK.NS"],
    "IT": ["TCS.NS","INFY.NS","WIPRO.NS","HCLTECH.NS","TECHM.NS","PERSISTENT.NS","LTIM.NS"],
    "Pharma": ["SUNPHARMA.NS","DRREDDY.NS","CIPLA.NS","DIVISLAB.NS","APOLLOHOSP.NS"],
    "Auto": ["MARUTI.NS","TATAMOTORS.NS","EICHERMOT.NS","HEROMOTOCO.NS"],
    "FMCG": ["HINDUNILVR.NS","ITC.NS","NESTLEIND.NS"],
    "Energy": ["RELIANCE.NS","NTPC.NS","POWERGRID.NS","ONGC.NS","BPCL.NS","COALINDIA.NS","ADANIENT.NS","TATAPOWER.NS","ADANIGREEN.NS"],
    "Finance": ["BAJFINANCE.NS","BAJAJFINSV.NS","CHOLAFIN.NS","MUTHOOTFIN.NS","PAYTM.NS"],
    "Metals": ["TATASTEEL.NS","JSWSTEEL.NS"],
    "Consumer": ["TITAN.NS","PIDILITIND.NS","HAVELLS.NS","ZOMATO.NS","NYKAA.NS","DMART.NS"],
}
CATEGORIES_USA = {
    "All": USA_SYMBOLS,
    "Mega Cap": USA_MEGA_CAP,
    "S&P Top 30": USA_MEGA_CAP + USA_LARGE_CAP[:20],
    "Dow 30": ["AAPL","MSFT","JPM","V","HD","PG","JNJ","CVX","MRK","AMGN","GS","CAT","AXP","IBM","TRV","MMM","BA","DIS","NKE","MCD","KO","WMT","INTC","VZ","CSCO","UNH","CRM","BA","HON","WBA"],
    "NASDAQ Tech": ["AAPL","MSFT","GOOGL","AMZN","NVDA","META","TSLA","ADBE","AMD","INTC","CSCO","CRWD","DDOG","ZS","SNOW","MDB","PLTR","NET","OKTA","TWLO","RBLX"],
    "Finance": ["JPM","BAC","WFC","GS","MS","BLK","V","MA","BRK-B","COIN","HOOD","SOFI"],
    "Healthcare": ["UNH","JNJ","ABBV","PFE","MRK","LLY","TMO","ABT","DHR","AMGN","GILD","MDT","SYK"],
    "Consumer": ["AMZN","HD","PG","ABNB","DASH","RBLX","NIO","RIVN"],
    "Energy": ["XOM","CVX"],
    "EV / Auto": ["TSLA","RIVN","NIO"],
    "Cloud / SaaS": ["CRM","ADBE","DDOG","CRWD","ZS","OKTA","TWLO","SNOW","MDB","NET","PLTR"],
    "Small / Spec": ["SNAP","COIN","HOOD","SOFI","MARA","RIOT","NIO","RIVN","RBLX","DASH"],
}

INDEX_SYMBOLS = {
    "india": [("^NSEI","Nifty 50"),("^BSESN","Sensex")],
    "usa":   [("^GSPC","S&P 500"),("^DJI","Dow Jones"),("^IXIC","Nasdaq"),("^RUT","Russell 2k")],
}
CRYPTO_SYMS = ["BTC-USD","ETH-USD","BNB-USD","SOL-USD","XRP-USD"]

USA_SECTOR_ETFS = {
    "Technology":"XLK","Finance":"XLF","Healthcare":"XLV","Energy":"XLE",
    "Industrials":"XLI","Cons. Disc.":"XLY","Cons. Staples":"XLP",
    "Materials":"XLB","Utilities":"XLU","Real Estate":"XLRE","Comm.":"XLC",
}

# Official stats, verified Oct 2026. Update these by hand when new prints come out.
MACRO_OFFICIAL = {
    "india": [
        {"label":"Repo Rate","value":5.50,"unit":"%","period":"Oct 2026","prev":5.25,"src":"RBI MPC"},
        {"label":"CPI Inflation","value":4.82,"unit":"%","period":"Aug 2026","prev":None,"src":"MoSPI"},
        {"label":"GDP Growth QoQ","value":1.8,"unit":"%","period":"Jun 2026","prev":2.1,"src":"Trading Economics"},
        {"label":"RBI GDP Proj. FY27","value":7.1,"unit":"%","period":"Oct 2026","prev":6.7,"src":"RBI MPC"},
    ],
    "usa": [
        {"label":"Fed Funds (upper)","value":4.00,"unit":"%","period":"Sep 2026","prev":3.75,"src":"FOMC"},
        {"label":"CPI Inflation","value":3.4,"unit":"%","period":"Aug 2026","prev":3.4,"src":"BLS"},
        {"label":"Unemployment","value":4.2,"unit":"%","period":"Sep 2026","prev":4.1,"src":"BLS"},
        {"label":"GDP Growth QoQ","value":2.2,"unit":"%","period":"Jun 2026","prev":2.5,"src":"Trading Economics"},
    ],
}
# Market-priced indicators, fetched live from Yahoo
MACRO_LIVE = {
    "india": [("^INDIAVIX","India VIX",""),("INR=X","USD/INR",""),("^NSEBANK","Bank Nifty","")],
    "usa":   [("^VIX","VIX",""),("^TNX","10Y Treasury","%"),("DX-Y.NYB","Dollar Index","")],
}
GLOBAL_ASSETS = {
    "Commodities": [("GC=F","Gold"),("SI=F","Silver"),("CL=F","WTI Crude"),("BZ=F","Brent"),("NG=F","Nat Gas"),("HG=F","Copper")],
    "FX": [("INR=X","USD/INR"),("EURUSD=X","EUR/USD"),("JPY=X","USD/JPY"),("GBPUSD=X","GBP/USD")],
}

_cache = {}
CACHE_TTL = 1800

def cached(key, fn, ttl=CACHE_TTL):
    now = time.time()
    if key in _cache and now - _cache[key][0] < ttl:
        return _cache[key][1]
    v = fn()
    empty = not v or (isinstance(v, dict) and all(not x for x in v.values()))
    if not empty:
        _cache[key] = (now, v)
    return v

def fetch_quote(sym):
    try:
        h = yf.Ticker(sym).history(period="5d")
        if len(h) < 2: return None
        curr = float(h["Close"].iloc[-1])
        prev = float(h["Close"].iloc[-2])
        vol  = float(h["Volume"].iloc[-1])
        return {"symbol":sym,"price":curr,"change":(curr-prev)/prev*100,
                "volume":vol,"high":float(h["High"].iloc[-1]),"low":float(h["Low"].iloc[-1])}
    except: return None

DASH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dashboard")

@app.get("/")
def home():
    return FileResponse(os.path.join(DASH, "index.html"))

@app.get("/api/categories")
def categories(mkt: str = Query("india")):
    cats = CATEGORIES_INDIA if mkt=="india" else CATEGORIES_USA
    return {k:v for k,v in cats.items()}

@app.get("/api/symbols")
def symbols(mkt: str = Query("india")):
    return {"symbols": INDIA_SYMBOLS if mkt=="india" else USA_SYMBOLS}

@app.get("/api/latest")
def latest():
    return get_all_results()

@app.get("/api/history")
def history():
    return load_history() if load_history else []

@app.get("/api/stock/{symbol}")
def stock(symbol:str, period:str=Query("1y")):
    try:
        h = yf.Ticker(symbol).history(period=period)
        if h.empty: return []
        return [{"date":str(d.date()),"open":round(float(o),2),"high":round(float(hi),2),
                 "low":round(float(lo),2),"close":round(float(c),2),"volume":int(v)}
                for d,o,hi,lo,c,v in zip(h.index,h["Open"],h["High"],h["Low"],h["Close"],h["Volume"])]
    except Exception:
        return []

@app.get("/api/stock/{symbol}/info")
def stock_info(symbol:str):
    try:
        info = yf.Ticker(symbol).info
        return {
            "name":      info.get("longName",symbol),
            "sector":    info.get("sector", INDIA_SECTORS.get(symbol, USA_SECTORS.get(symbol,"N/A"))),
            "pe":        info.get("trailingPE"),
            "pb":        info.get("priceToBook"),
            "hi52":      info.get("fiftyTwoWeekHigh"),
            "lo52":      info.get("fiftyTwoWeekLow"),
            "mktCap":    info.get("marketCap"),
            "divYield":  info.get("dividendYield"),
            "beta":      info.get("beta"),
            "avgVol":    info.get("averageVolume"),
            "eps":       info.get("trailingEps"),
        }
    except Exception as e: return {"error":str(e)}

@app.get("/api/forecast/{symbol}")
def forecast(symbol:str):
    try:
        info = yf.Ticker(symbol).info
        curr   = info.get("currentPrice") or info.get("regularMarketPrice")
        target = info.get("targetMeanPrice")
        upside = round((target-curr)/curr*100,1) if target and curr else None
        return {
            "targetMean":   target,
            "targetHigh":   info.get("targetHighPrice"),
            "targetLow":    info.get("targetLowPrice"),
            "targetMedian": info.get("targetMedianPrice"),
            "recommendation":info.get("recommendationKey","").upper(),
            "numAnalysts":  info.get("numberOfAnalystOpinions"),
            "currentPrice": curr,
            "upside":       upside,
        }
    except Exception as e: return {"error":str(e)}

@app.get("/api/news/{symbol}")
def news(symbol:str):
    try:
        import datetime as dt
        items = yf.Ticker(symbol).news or []
        out=[]
        for n in items[:8]:
            c = n.get("content") or n
            title = c.get("title","")
            url = (c.get("canonicalUrl") or {}).get("url") or (c.get("clickThroughUrl") or {}).get("url") or c.get("link","")
            pub = (c.get("provider") or {}).get("displayName") or c.get("publisher","")
            date = (c.get("pubDate") or "")[:10]
            if not date and c.get("providerPublishTime"):
                date = str(dt.datetime.fromtimestamp(c["providerPublishTime"]).date())
            if title: out.append({"title":title,"url":url,"publisher":pub,"date":date})
        return out[:6]
    except: return []

@app.get("/api/alerts")
def alerts(mkt:str=Query("india")):
    syms=(INDIA_SYMBOLS if mkt=="india" else USA_SYMBOLS)[:20]
    result=[]
    def chk(s):
        try:
            h=yf.Ticker(s).history(period="30d")
            if len(h)<14: return
            c=h["Close"].values
            chg=(c[-1]-c[-2])/c[-2]*100
            if abs(chg)>3: result.append({"symbol":s,"type":"move","msg":f"{chg:+.1f}% today","change":float(chg)})
            elif c[-1]>=max(c)*0.99: result.append({"symbol":s,"type":"high","msg":"Near 30-day high","change":float(chg)})
        except: pass
    with ThreadPoolExecutor(max_workers=8) as ex: list(ex.map(chk,syms))
    return result[:15]

@app.get("/api/heatmap")
def heatmap(mkt:str=Query("india"), period:str=Query("1mo"), category:str=Query("All")):
    cats  = CATEGORIES_INDIA if mkt=="india" else CATEGORIES_USA
    syms  = cats.get(category,cats["All"])
    sects = INDIA_SECTORS if mkt=="india" else USA_SECTORS
    p_map = {"5d":"5d","1W":"5d","1mo":"1mo","1M":"1mo","3mo":"3mo","3M":"3mo"}
    per   = p_map.get(period,"1mo")
    result=[]
    def fetch(s):
        try:
            h=yf.Ticker(s).history(period=per)
            if len(h)<2: return
            ret=(h["Close"].iloc[-1]-h["Close"].iloc[0])/h["Close"].iloc[0]*100
            result.append({"symbol":s,"sector":sects.get(s,"Other"),"change":round(float(ret),2)})
        except: pass
    with ThreadPoolExecutor(max_workers=10) as ex: list(ex.map(fetch,syms))
    return result

@app.get("/api/pairs")
def pairs_data(mkt:str=Query("india"), category:str=Query("All"),
               limit:int=Query(50), threshold:float=Query(0.65), sort:str=Query("corr")):
    cats  = CATEGORIES_INDIA if mkt=="india" else CATEGORIES_USA
    syms  = cats.get(category,cats["All"])
    sects = INDIA_SECTORS if mkt=="india" else USA_SECTORS
    closes={}
    def fetch(s):
        try:
            h=yf.Ticker(s).history(period="1y")
            if len(h)>=60: closes[s]=h["Close"].values
        except: pass
    with ThreadPoolExecutor(max_workers=12) as ex: list(ex.map(fetch,syms))
    valid=list(closes.keys())
    if len(valid)<2: return []
    ml=min(len(closes[s]) for s in valid)
    df=pd.DataFrame({s:closes[s][-ml:] for s in valid})
    corr=df.corr()
    pairs=[]
    for i,s1 in enumerate(valid):
        for s2 in valid[i+1:]:
            r=corr.loc[s1,s2]
            if r>=threshold:
                try:
                    ct=Q.coint_test(df[s1].values, df[s2].values)
                except Exception:
                    ct={"adf":0.0,"pbucket":">10%","pvalue":None,"half_life":float("inf"),"beta":None}
                hl=ct["half_life"]
                pairs.append({"sym1":s1,"sym2":s2,"correlation":round(float(r),3),
                              "sector1":sects.get(s1,"Other"),"sector2":sects.get(s2,"Other"),
                              "adf":round(ct["adf"],2),"pbucket":ct["pbucket"],"pvalue":ct["pvalue"],
                              "half_life":None if not np.isfinite(hl) else round(hl,1),
                              "beta":None if ct["beta"] is None else round(ct["beta"],3)})
    if sort=="coint": pairs.sort(key=lambda x:x["adf"])
    else: pairs.sort(key=lambda x:-x["correlation"])
    return pairs[:limit]

@app.get("/api/export/trades")
def export_trades():
    rows=get_all_results()
    flat=[{k:v for k,v in r.items() if not isinstance(v,(list,dict))} for r in rows]
    buf=io.StringIO()
    w=csv.DictWriter(buf,fieldnames=flat[0].keys() if flat else [])
    w.writeheader(); w.writerows(flat); buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]),media_type="text/csv",
                             headers={"Content-Disposition":"attachment; filename=trades.csv"})

# ── NEW Market Overview endpoints ──────────────────────────────────────────────

@app.get("/api/indices")
def indices_data():
    def _f():
        result={"india":[],"usa":[]}
        all_s=[s for mkt in INDEX_SYMBOLS.values() for s,_ in mkt]
        quotes={}
        def fq(sym):
            q=fetch_quote(sym)
            if q: quotes[sym]=q
        with ThreadPoolExecutor(max_workers=8) as ex: list(ex.map(fq,all_s))
        for mkt,pairs in INDEX_SYMBOLS.items():
            for sym,name in pairs:
                if sym in quotes:
                    q=quotes[sym]
                    result[mkt].append({"name":name,"symbol":sym,"price":q["price"],"change":round(q["change"],2)})
        return result
    return cached("indices",_f)

@app.get("/api/crypto")
def crypto_data():
    def _f():
        out=[]
        order=["BTC","ETH","BNB","SOL","XRP"]
        def fq(sym):
            q=fetch_quote(sym)
            if q: out.append({"symbol":sym.replace("-USD",""),"price":q["price"],"change":round(q["change"],2)})
        with ThreadPoolExecutor(max_workers=6) as ex: list(ex.map(fq,CRYPTO_SYMS))
        out.sort(key=lambda x:order.index(x["symbol"]) if x["symbol"] in order else 99)
        return out
    return cached("crypto",_f)

@app.get("/api/macro")
def macro(mkt:str=Query("india")):
    def _f():
        live=[]
        def fq(t):
            sym,label,unit=t
            q=fetch_quote(sym)
            if q: live.append({"label":label,"value":round(q["price"],2),"unit":unit,
                               "change":round(q["change"],2),"period":"Live","src":"Yahoo"})
        with ThreadPoolExecutor(max_workers=4) as ex: list(ex.map(fq,MACRO_LIVE.get(mkt,[])))
        return live
    return {"official":MACRO_OFFICIAL.get(mkt,[]),"live":cached(f"macrolive_{mkt}",_f)}

@app.get("/api/global")
def global_assets():
    def _f():
        out={}
        for grp,items in GLOBAL_ASSETS.items():
            res=[]
            def fq(t):
                sym,name=t
                q=fetch_quote(sym)
                if q: res.append({"symbol":sym,"name":name,"price":q["price"],"change":round(q["change"],2)})
            with ThreadPoolExecutor(max_workers=6) as ex: list(ex.map(fq,items))
            order=[n for _,n in items]
            out[grp]=sorted(res,key=lambda x:order.index(x["name"]))
        return out
    return cached("global",_f)

FORECAST_GROUPS = {
    "india":[("Indices",[("^NSEI","Nifty 50"),("^BSESN","Sensex"),("^NSEBANK","Bank Nifty")]),
             ("Stocks",[(s,s.replace(".NS","")) for s in INDIA_LARGE_CAP[:12]])],
    "usa":  [("Indices",[("^GSPC","S&P 500"),("^DJI","Dow Jones"),("^IXIC","Nasdaq")]),
             ("Stocks",[(s,s) for s in USA_MEGA_CAP])],
    "global":[("Crypto",[("BTC-USD","Bitcoin"),("ETH-USD","Ether"),("BNB-USD","Binance"),("SOL-USD","Solana"),("XRP-USD","XRP")]),
              ("Commodities",[("GC=F","Gold"),("SI=F","Silver"),("CL=F","WTI Crude"),("BZ=F","Brent")])],
}

@app.get("/api/forecast-table")
def forecast_table(mkt:str=Query("india")):
    def _f():
        groups=[]
        for gname,items in FORECAST_GROUPS.get(mkt,[]):
            rows={}
            def fq(t):
                sym,name=t
                try:
                    h=yf.Ticker(sym).history(period="10y")
                    pr=Q.forecast_bands(h["Close"].values)
                    if pr: rows[sym]={"symbol":sym,"name":name,**pr}
                except Exception: pass
            with ThreadPoolExecutor(max_workers=8) as ex: list(ex.map(fq,items))
            groups.append({"group":gname,"rows":[rows[s] for s,_ in items if s in rows]})
        return {"quarters":[q for q,_ in Q._quarter_ends()],"groups":groups}
    return cached(f"fctable_{mkt}",_f)

@app.get("/api/options/{symbol}")
def options(symbol:str, expiry:str=Query(None)):
    try:
        tk=yf.Ticker(symbol)
        exps=list(tk.options or [])
        if not exps: return {"error":"No listed options for this symbol on the free feed (NSE option chains are not available via Yahoo)."}
        exp=expiry if expiry in exps else exps[0]
        ch=tk.option_chain(exp)
        calls,puts=ch.calls.fillna(0),ch.puts.fillna(0)
        spot=fetch_quote(symbol)
        spot=spot["price"] if spot else None
        coi,poi=float(calls["openInterest"].sum()),float(puts["openInterest"].sum())
        cv,pv=float(calls["volume"].sum()),float(puts["volume"].sum())
        strikes=sorted(set(calls["strike"]).union(set(puts["strike"])))
        cmap=dict(zip(calls["strike"],calls["openInterest"])); pmap=dict(zip(puts["strike"],puts["openInterest"]))
        pain=[(k,sum(max(0,k-s)*cmap.get(s,0) for s in strikes)+sum(max(0,s-k)*pmap.get(s,0) for s in strikes)) for k in strikes]
        max_pain=min(pain,key=lambda x:x[1])[0] if pain else None
        if spot:
            near=[k for k in strikes if 0.8*spot<=k<=1.2*spot]
        else: near=strikes
        civ=dict(zip(calls["strike"],calls["impliedVolatility"])); piv=dict(zip(puts["strike"],puts["impliedVolatility"]))
        chain=[{"strike":k,"callOI":int(cmap.get(k,0)),"putOI":int(pmap.get(k,0)),
                "callIV":round(float(civ.get(k,0))*100,1),"putIV":round(float(piv.get(k,0))*100,1)} for k in near]
        return {"expiry":exp,"expiries":exps[:8],"spot":spot,"pcrOI":round(poi/coi,2) if coi else None,
                "pcrVol":round(pv/cv,2) if cv else None,"maxPain":max_pain,"callOI":int(coi),"putOI":int(poi),"chain":chain}
    except Exception as e: return {"error":str(e)}

@app.get("/api/movers")
def movers(mkt:str=Query("india"), type:str=Query("gainers")):
    def _f():
        syms=INDIA_SYMBOLS if mkt=="india" else USA_SYMBOLS
        data=[]
        def fq(s):
            q=fetch_quote(s)
            if q: data.append(q)
        with ThreadPoolExecutor(max_workers=16) as ex: list(ex.map(fq,syms))
        return data
    data=cached(f"movers_{mkt}",_f)
    if type=="gainers":  s=sorted([d for d in data if d["change"]>0],key=lambda x:-x["change"])
    elif type=="losers": s=sorted([d for d in data if d["change"]<0],key=lambda x: x["change"])
    else:                s=sorted(data,key=lambda x:-x["volume"]*x["price"])
    return s[:10]

@app.get("/api/market-breadth")
def market_breadth(mkt:str=Query("india")):
    def _f():
        syms=INDIA_SYMBOLS if mkt=="india" else USA_SYMBOLS
        adv=dec=unch=0
        def chk(s):
            nonlocal adv,dec,unch
            q=fetch_quote(s)
            if q:
                if q["change"]>0.1: adv+=1
                elif q["change"]<-0.1: dec+=1
                else: unch+=1
        with ThreadPoolExecutor(max_workers=12) as ex: list(ex.map(chk,syms))
        return {"advancing":adv,"declining":dec,"unchanged":unch,"total":adv+dec+unch}
    return cached(f"breadth_{mkt}",_f)

@app.get("/api/sector-perf")
def sector_perf(mkt:str=Query("india"), period:str=Query("1M")):
    p_map={"1W":"5d","1M":"1mo","3M":"3mo"}
    per=p_map.get(period,"1mo")
    if mkt=="usa":
        def _f():
            result=[]
            def fq(kv):
                name,sym=kv
                try:
                    h=yf.Ticker(sym).history(period=per)
                    if len(h)>=2:
                        ret=(h["Close"].iloc[-1]-h["Close"].iloc[0])/h["Close"].iloc[0]*100
                        result.append({"sector":name,"return":round(float(ret),2)})
                except: pass
            with ThreadPoolExecutor(max_workers=6) as ex: list(ex.map(fq,USA_SECTOR_ETFS.items()))
            return sorted(result,key=lambda x:-x["return"])
        return cached(f"sectorperf_usa_{period}",_f)
    else:
        def _f():
            sec_stocks={}
            for s,sec in INDIA_SECTORS.items(): sec_stocks.setdefault(sec,[]).append(s)
            result=[]
            def calc(sec):
                rets=[]
                for s in sec_stocks.get(sec,[])[:5]:
                    try:
                        h=yf.Ticker(s).history(period=per)
                        if len(h)>=2: rets.append((h["Close"].iloc[-1]-h["Close"].iloc[0])/h["Close"].iloc[0]*100)
                    except: pass
                if rets: result.append({"sector":sec,"return":round(float(np.mean(rets)),2)})
            with ThreadPoolExecutor(max_workers=6) as ex: list(ex.map(calc,list(sec_stocks.keys())))
            return sorted(result,key=lambda x:-x["return"])
        return cached(f"sectorperf_india_{period}",_f)

@app.get("/api/earnings")
def earnings(mkt:str=Query("india")):
    return cached(f"earnings_{mkt}", lambda: _earnings(mkt))

def _earnings(mkt):
    syms=(INDIA_SYMBOLS if mkt=="india" else USA_SYMBOLS)[:40]
    result=[]
    import datetime as dt
    def fetch(s):
        try:
            info=yf.Ticker(s).info
            ed=info.get("earningsTimestamp")
            name=info.get("shortName",s)
            if ed and isinstance(ed,(int,float)):
                d=dt.datetime.fromtimestamp(ed)
                if d.timestamp()>time.time():
                    result.append({"symbol":s,"name":name,"date":str(d.date()),"eps":info.get("epsForward")})
        except: pass
    with ThreadPoolExecutor(max_workers=10) as ex: list(ex.map(fetch,syms))
    result.sort(key=lambda x:x["date"])
    return result[:15]


# ══════════════════════════════════════════════════════════════════════
# v4: Strategy Lab, quant research, screener, paper trading, alerts
# ══════════════════════════════════════════════════════════════════════
def hist(sym, period="2y"):
    """(dates, close) for a symbol, cached 30 min."""
    def _f():
        h = yf.Ticker(sym).history(period=period)
        if h.empty: return None
        h = h[h["Close"] > 0]
        return ([str(d.date()) for d in h.index], h["Close"].to_numpy(dtype=float))
    return cached(f"hist_{sym}_{period}", _f)

def live_quote(sym):
    return cached(f"lq_{sym}", lambda: fetch_quote(sym), ttl=60)

def _num(x):
    if x is None: return None
    try:
        x = float(x)
        return x if np.isfinite(x) else None
    except Exception: return None

def _clean(o):
    """Make numpy/inf values JSON-safe."""
    if isinstance(o, dict): return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)): return [_clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return float(o) if np.isfinite(o) else None
    if isinstance(o, np.integer): return int(o)
    if isinstance(o, np.bool_): return bool(o)
    return o

@app.get("/api/search-index")
def search_index():
    rows = [{"symbol": s, "mkt": "india", "sector": INDIA_SECTORS.get(s, "")} for s in INDIA_SYMBOLS]
    rows += [{"symbol": s, "mkt": "usa", "sector": USA_SECTORS.get(s, "")} for s in USA_SYMBOLS]
    return rows

# ── Strategy Lab ───────────────────────────────────────────────────────
@app.get("/api/lab/strategies")
def lab_strategies():
    return {"strategies": Q.STRATEGIES, "has_cpp": Q.HAS_CPP}

@app.get("/api/lab/backtest")
def lab_backtest(symbol: str, strategy: str = "ma_cross", period: str = "2y", cost: float = 5.0,
                 oos: float = 0.3, short: bool = False, capital: float = 100000.0, params: str = "{}"):
    if strategy not in Q.STRATEGIES: return {"error": "unknown strategy"}
    hc = hist(symbol, period)
    if not hc or len(hc[1]) < 80: return {"error": f"not enough price history for {symbol}"}
    try: prm = json.loads(params) if params else {}
    except Exception: prm = {}
    res = Q.backtest(hc[0], hc[1], strategy, prm, cost_bps=cost, oos_frac=oos, allow_short=short, capital=capital)
    res["symbol"] = symbol
    return _clean(res)

@app.get("/api/lab/grid")
def lab_grid(symbol: str, strategy: str = "ma_cross", period: str = "2y", cost: float = 5.0,
             oos: float = 0.3, short: bool = False):
    if strategy not in Q.STRATEGIES: return {"error": "unknown strategy"}
    hc = hist(symbol, period)
    if not hc or len(hc[1]) < 120: return {"error": f"not enough price history for {symbol}"}
    return _clean(Q.param_grid(hc[0], hc[1], strategy, cost_bps=cost, oos_frac=oos, allow_short=short))

@app.get("/api/lab/benchmark")
def lab_benchmark(symbol: str = "^GSPC", period: str = "5y"):
    hc = hist(symbol, period)
    if not hc or len(hc[1]) < 300: return {"error": "not enough history for the benchmark"}
    out = Q.benchmark(hc[1]); out["symbol"] = symbol
    return _clean(out)

# ── Pairs analysis ─────────────────────────────────────────────────────
@app.get("/api/pairs/analyze")
def pairs_analyze(s1: str, s2: str, entry: float = 2.0, exit: float = 0.5, window: int = 30,
                  cost: float = 5.0, period: str = "1y"):
    a, b = hist(s1, period), hist(s2, period)
    if not a or not b: return {"error": "missing price data"}
    sa = pd.Series(a[1], index=a[0]); sb = pd.Series(b[1], index=b[0])
    df = pd.concat([sa, sb], axis=1, join="inner").dropna()
    if len(df) < window + 30: return {"error": "not enough overlapping history"}
    res = Q.pairs_backtest(list(df.index), df.iloc[:, 0].values, df.iloc[:, 1].values,
                           entry=entry, exit_=exit, window=window, cost_bps=cost)
    res["s1"], res["s2"] = s1, s2
    res["p1"] = [round(float(v), 4) for v in df.iloc[:, 0].values]
    res["p2"] = [round(float(v), 4) for v in df.iloc[:, 1].values]
    res["has_statsmodels"] = Q.HAS_SM
    return _clean(res)

# ── Portfolio optimiser ────────────────────────────────────────────────
class OptReq(BaseModel):
    symbols: List[str]
    weights: Optional[Dict[str, float]] = None
    period: str = "1y"
    capital: float = 100000.0

@app.post("/api/portfolio/optimize")
def portfolio_optimize(req: OptReq):
    syms = list(dict.fromkeys(req.symbols))[:20]
    if len(syms) < 2: return {"error": "add at least 2 stocks"}
    series = {}
    def f(s):
        hc = hist(s, req.period)
        if hc: series[s] = pd.Series(hc[1], index=pd.to_datetime(hc[0]))
    with ThreadPoolExecutor(max_workers=10) as ex: list(ex.map(f, syms))
    if len(series) < 2: return {"error": "could not load prices"}
    prices = pd.concat(series, axis=1, join="inner").dropna()
    prices = prices[[s for s in syms if s in prices.columns]]
    if len(prices) < 60: return {"error": "not enough overlapping history"}
    bsym = "^NSEI" if all(s.endswith(".NS") for s in prices.columns) else "^GSPC"
    bh = hist(bsym, req.period)
    bench = None
    if bh:
        bench = pd.Series(bh[1], index=pd.to_datetime(bh[0])).pct_change()
    res = Q.optimize_portfolio(prices, bench=bench, user_weights=req.weights, capital=req.capital)
    res["benchmark"] = bsym
    return _clean(res)

# ── Screener ───────────────────────────────────────────────────────────
@app.get("/api/screener")
def screener(mkt: str = Query("india")):
    def _f():
        syms = INDIA_SYMBOLS if mkt == "india" else USA_SYMBOLS
        sects = INDIA_SECTORS if mkt == "india" else USA_SECTORS
        rows = []
        def one(s):
            try:
                hc = hist(s, "1y")
                if not hc or len(hc[1]) < 60: return
                c = hc[1]
                r = {"symbol": s, "sector": sects.get(s, ""), "price": float(c[-1]),
                     "chg1d": float(c[-1] / c[-2] - 1) * 100,
                     "chg1m": float(c[-1] / c[-22] - 1) * 100 if len(c) > 22 else None,
                     "chg3m": float(c[-1] / c[-64] - 1) * 100 if len(c) > 64 else None,
                     "chg1y": float(c[-1] / c[0] - 1) * 100,
                     "rsi": float(Q.rsi(c, 14)[-1]),
                     "from_high": float(c[-1] / c.max() - 1) * 100,
                     "from_low": float(c[-1] / c.min() - 1) * 100,
                     "above_sma50": bool(c[-1] > c[-50:].mean()),
                     "above_sma200": bool(c[-1] > c[-200:].mean()) if len(c) >= 200 else None,
                     "vol": float(np.std(np.diff(np.log(c[-63:])), ddof=1) * np.sqrt(252) * 100)}
                info = cached(f"info_{s}", lambda: yf.Ticker(s).info)
                r["pe"] = _num(info.get("trailingPE")); r["mcap"] = _num(info.get("marketCap"))
                r["div"] = _num(info.get("dividendYield")); r["name"] = info.get("shortName") or s
                rows.append(r)
            except Exception: pass
        with ThreadPoolExecutor(max_workers=16) as ex: list(ex.map(one, syms))
        return sorted(rows, key=lambda x: -(x.get("mcap") or 0))
    return _clean(cached(f"screener_{mkt}", _f))

# ── Paper trading ──────────────────────────────────────────────────────
class OrderReq(BaseModel):
    symbol: str
    side: str
    qty: float

@app.get("/api/paper/account")
def paper_account(mkt: str = Query("india")):
    return _clean(T.account(mkt, live_quote))

@app.post("/api/paper/order")
def paper_order(o: OrderReq):
    return _clean(T.place_order(o.symbol, o.side, o.qty, live_quote))

@app.post("/api/paper/reset")
def paper_reset(mkt: str = Query("india")):
    return T.reset(mkt)

# ── Watchlist ──────────────────────────────────────────────────────────
@app.get("/api/watchlist")
def watchlist_get():
    syms = T.watchlist()
    out = []
    def f(s):
        q = live_quote(s)
        out.append({"symbol": s, "price": q["price"] if q else None, "change": q["change"] if q else None,
                    "mkt": T.mkt_of(s)})
    with ThreadPoolExecutor(max_workers=8) as ex: list(ex.map(f, syms))
    order = {s: i for i, s in enumerate(syms)}
    return _clean(sorted(out, key=lambda x: order[x["symbol"]]))

@app.post("/api/watchlist/{symbol}")
def watchlist_add(symbol: str):
    return T.watch_add(symbol)

@app.delete("/api/watchlist/{symbol}")
def watchlist_del(symbol: str):
    return T.watch_remove(symbol)

# ── Price alerts ───────────────────────────────────────────────────────
class AlertReq(BaseModel):
    symbol: str
    cond: str
    price: float

@app.get("/api/alerts/rules")
def alert_rules():
    return T.alerts_list()

@app.post("/api/alerts/rules")
def alert_rule_add(a: AlertReq):
    return T.alert_add(a.symbol, a.cond, a.price)

@app.delete("/api/alerts/rules/{aid}")
def alert_rule_del(aid: int):
    return T.alert_delete(aid)

@app.get("/api/alerts/check")
def alert_check():
    return _clean(T.alerts_check(live_quote))
