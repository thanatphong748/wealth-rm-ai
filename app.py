from flask import Flask, render_template, jsonify, request
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import re
import concurrent.futures
import time
import ssl # Added for Settrade

# AI Libraries (Optional - prevent crash if not installed)
# AI Libraries
try:
    import os
    from dotenv import load_dotenv
    from openai import OpenAI
    
    # Load environment variables
    load_dotenv()
    
    # Configure AI Provider (OpenAI or OpenRouter)
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    
    AI_MODEL = "gpt-4o"
    AI_MODEL_MINI = "gpt-4o-mini"
    client = None
    
    if OPENROUTER_API_KEY:
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=OPENROUTER_API_KEY,
        )
        AI_MODEL = os.getenv("OPENROUTER_MODEL") or "anthropic/claude-3.7-sonnet"
        AI_MODEL_MINI = os.getenv("OPENROUTER_MODEL_MINI") or "anthropic/claude-3.5-haiku"
        AI_AVAILABLE = True
        print(f"✅ AI Enabled: OpenRouter ({AI_MODEL})")
    elif OPENAI_API_KEY:
        client = OpenAI(api_key=OPENAI_API_KEY)
        AI_AVAILABLE = True
        print("✅ AI Enabled: OpenAI")
    else:
        AI_AVAILABLE = False
        print("⚠️ Warning: Neither OPENAI_API_KEY nor OPENROUTER_API_KEY found in .env")

except ImportError:
    print("⚠️ Warning: OpenAI library not installed. AI features disabled.")
    print("   Please run: pip install openai python-dotenv")
    AI_AVAILABLE = False
    client = None

app = Flask(__name__)
from flask_cors import CORS
CORS(app)

# ============================================================================
# LINE MESSAGING API CONFIGURATION
# ============================================================================
LINE_CHANNEL_ACCESS_TOKEN = "vBOOsELC5rAQhl97Q2o5S6DnM9Kl5t5XKaDyU2QKFnEukxINmz7YYwlS0TiXfS+W87hCqDguG2RHv4bIyYVgJdcOtiXKzFzY3gLj8rPqu9xJjFaznK7qA3RbJ9Me4TBT61u+EIeKd6wLT7/HMrQ/pwdB04t89/1O/w1cDnyilFU="

# ============================================================================
# TTB FUND MASTER LIST
# ============================================================================

TTB_FUNDS = {
    "equity_us": {
        "category": "หุ้นสหรัฐฯ",
        "accumulate": ["ES-USTECH", "ES-GTECH", "ES-USBLUECHIP", "SCBSEMI(A)"],
        "hold": ["SCBUSAA"],
        "ticker": "^GSPC"
    },
    "equity_china": {
        "category": "หุ้นจีน/ฮ่องกง",
        "accumulate": ["KF-HSHARE-INDX"],
        "hold": ["ES-CHINA-A", "SCBCHRA"],
        "ticker": "^HSI"
    },
    "equity_japan": {
        "category": "หุ้นญี่ปุ่น",
        "accumulate": [],
        "hold": ["ES-JPNAE-A"],
        "ticker": "^N225"
    },
    "equity_europe": {
        "category": "หุ้นยุโรป",
        "accumulate": ["ES-GER"],
        "hold": ["ONE-EUROEQ", "ES-GF-A"],
        "ticker": "^STOXX"
    },
    "equity_global": {
        "category": "หุ้นโลก",
        "accumulate": ["ES-GCORE"],
        "hold": ["ES-GDIV", "ES-PREMIUMBRAND"],
        "ticker": "^GSPC"
    },
    "equity_asia": {
        "category": "หุ้นเอเชีย",
        "accumulate": ["ES-ASIA-A", "TISCOHD-A"],
        "hold": [],
        "ticker": "^HSI"
    },
    "equity_india": {
        "category": "หุ้นอินเดีย",
        "accumulate": ["ES-INDAE"],
        "hold": [],
        "ticker": "^BSESN"
    },
    "gold": {
        "category": "ทองคำ",
        "accumulate": [],
        "hold": [],
        "take_profit": ["กองทุนทองคำ"],
        "ticker": "GC=F"
    },
    "bond_global": {
        "category": "ตราสารหนี้ต่างประเทศ",
        "accumulate": ["ES-GINCOME", "KT-CSBOND-A", "ES-GSBOND-A"],
        "hold": [],
        "ticker": "^TNX"
    }
}

# ============================================================================
# TTB INSURANCE MASTER LIST (Added per user request)
# ============================================================================
TTB_INSURANCE = {
    "savings_short": {
        "name": "Happy Life 10/5",
        "desc": "ออมสั้น ได้เงินคืนไว (ขอลดหย่อนภาษีได้)",
        "suitability": "ต้องการลดหย่อนภาษี, เก็บเงินระยะสั้น"
    },
    "savings_medium": {
        "name": "Happy Life 14/6",
        "desc": "ออมระยะกลาง ผลตอบแทนคุ้มค่า",
        "suitability": "ต้องการลดหย่อนภาษี, วางแผนการเงินระยะกลาง"
    },
    "retire_annuity": {
        "name": "The Treasure 88/8",
        "desc": "ประกันบำนาญ รับเงินคืนยาวถึงอายุ 88",
        "suitability": "วางแผนเกษียณ, ต้องการเงินคืนสม่ำเสมอหลังเกษียณ"
    },
    "legacy_transfer": {
        "name": "Wealthy Link 99/9",
        "desc": "ประกันควบการลงทุน ส่งต่อมรดก",
        "suitability": "สร้างหลักประกัน, ส่งต่อมรดก, รับความเสี่ยงการลงทุนได้"
    },
    "health_protection": {
        "name": "TTB Flexi / UL",
        "desc": "Unit Linked เน้นความคุ้มครองสุขภาพและลงทุน",
        "suitability": "ต้องการความคุ้มครองชีวิตสูง, ยืดหยุ่นปรับเปลี่ยนได้"
    },
    "long_term": {
        "name": "Happy Life 90/5",
        "desc": "ออมยาว คุ้มครองถึงอายุ 90 ชำระเบี้ยสั้น 5 ปี",
        "suitability": "คุ้มครองยาวนาน, เป็นมรดกให้ลูกหลาน"
    }
}

# ES-ULTIMATE GA Series - Separate funds with Finnomena data
ES_GA_FUNDS = {
    "ES-ULTIMATE GA1": {
        "finnomena_id": "ES-ULTIMATE GA1",
        "name": "ES-ULTIMATE GA1",
        "short_name": "GA1",
        "ticker": "^GSPC",  # Use S&P 500 as proxy for chart
        "nav": 10.7465,  # Updated from Finnomena
        "update_date": "8 ม.ค. 69"
    },
    "ES-ULTIMATE GA2": {
        "finnomena_id": "ES-ULTIMATE GA2", 
        "name": "ES-ULTIMATE GA2",
        "short_name": "GA2",
        "ticker": "^GSPC",
        "nav": 10.8500,  # Estimated
        "update_date": "8 ม.ค. 69"
    },
    "ES-ULTIMATE GA3": {
        "finnomena_id": "ES-ULTIMATE GA3",
        "name": "ES-ULTIMATE GA3", 
        "short_name": "GA3",
        "ticker": "^GSPC",
        "nav": 10.9200,  # Estimated
        "update_date": "8 ม.ค. 69"
    }
}

# Global Storage for Scraped Data
FUND_DATA = {}

# Initial seed data (optional, can be empty as we will fetch)
FUND_NAVS = {} # Deprecated, keeping for compatibility if needed, but will replace usage

# FX Pairs for LINE message
FX_PAIRS = {
    "USD/THB": "THB=X",
    "EUR/THB": "EURTHB=X", 
    "JPY/THB": "JPYTHB=X",
    "GBP/THB": "GBPTHB=X"
}

TICKERS = {
    "S&P 500": "^GSPC",
    "Nasdaq": "^IXIC",
    "Stoxx 600": "^STOXX",
    "Nikkei 225": "^N225",
    "Shanghai": "000001.SS",
    "Hang Seng": "^HSI",
    "SET": "^SET.BK",
    "India BSE": "^BSESN",
    "Gold": "GC=F",
    "Oil WTI": "CL=F",
    "DXY": "DX-Y.NYB",
    "US 10Y": "^TNX",
    "USD/THB": "THB=X"
}

# CACHE SYSTEM
MARKET_CACHE = {
    "data": None,
    "timestamp": 0,
    "expiry": 900 # 15 minutes
}

# ============================================================================
# ANALYSIS FUNCTIONS
# ============================================================================

def get_trend(close, sma50):
    if pd.isna(close) or pd.isna(sma50):
        return "N/A", "neutral"
    if close > sma50 * 1.02:
        return "ขาขึ้นชัดเจน", "bullish"
    elif close > sma50:
        return "ขาขึ้น", "bullish"
    elif close < sma50 * 0.98:
        return "ขาลงชัดเจน", "bearish"
    else:
        return "ขาลง", "bearish"

def get_momentum(change_pct):
    if pd.isna(change_pct):
        return "ทรงตัว", "neutral"
    if change_pct > 1.5:
        return "บวกแรง", "strong-bullish"
    elif change_pct > 0.3:
        return "บวก", "bullish"
    elif change_pct < -1.5:
        return "ลบแรง", "strong-bearish"
    elif change_pct < -0.3:
        return "ลบ", "bearish"
    else:
        return "ทรงตัว", "neutral"

def get_signal(trend, change_pct):
    if "ขาขึ้นชัดเจน" in trend and change_pct > 0.5:
        return "ทยอยสะสม", "accumulate"
    elif "ขาขึ้น" in trend:
        return "ถือครอง", "hold"
    elif "ขาลงชัดเจน" in trend or change_pct < -1.0:
        return "ระวังความเสี่ยง", "caution"
    else:
        return "รอจังหวะ", "wait"

# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/market-data')
def get_market_data():
    global MARKET_CACHE
    
    # Check Cache
    if MARKET_CACHE["data"] and (time.time() - MARKET_CACHE["timestamp"] < MARKET_CACHE["expiry"]):
        print("Using Cached Market Data")
        return jsonify(MARKET_CACHE["data"])
    
    results = []
    last_trading_date = None
    
    # Define a helper function for single fetch
    def fetch_ticker(name, symbol):
        try:
            ticker = yf.Ticker(symbol)
            # cache-control? yfinance checks cache.
            hist = ticker.history(period="3mo")
            if hist.empty:
                return None
            
            current_close = hist['Close'].iloc[-1]
            prev_close = hist['Close'].iloc[-2]
            change_pct = ((current_close - prev_close) / prev_close) * 100
            sma50 = hist['Close'].rolling(window=50).mean().iloc[-1]
            
            # Trend logic
            trend_text, trend_class = get_trend(current_close, sma50)
            momentum_text, momentum_class = get_momentum(change_pct)
            signal_text, signal_class = get_signal(trend_text, change_pct)
            
            return {
                "name": name,
                "price": round(current_close, 2),
                "change_pct": round(change_pct, 2),
                "trend": trend_text,
                "trend_class": trend_class,
                "momentum": momentum_text,
                "momentum_class": momentum_class,
                "signal": signal_text,
                "signal_class": signal_class,
                "date": hist.index[-1].strftime('%d/%m/%Y')
            }
        except Exception as e:
            print(f"Error fetching {name}: {e}")
            return None

    # Parallel Execution
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_name = {executor.submit(fetch_ticker, name, symbol): name for name, symbol in TICKERS.items()}
        
        for future in concurrent.futures.as_completed(future_to_name):
            res = future.result()
            if res:
                results.append(res)
                if last_trading_date is None:
                    last_trading_date = res['date']

    # Sort output for consistency
    results.sort(key=lambda x: x['name'])
    
    final_response = {
        "timestamp": datetime.now().strftime('%d/%m/%Y %H:%M'),
        "data_date": last_trading_date or datetime.now().strftime('%d/%m/%Y'),
        "data": results
    }
    
    # Update Cache
    if results:
        MARKET_CACHE["data"] = final_response
        MARKET_CACHE["timestamp"] = time.time()
        
    return jsonify(final_response)

@app.route('/api/fund-signals')
def get_fund_signals():
    results = []
    
    for key, fund_group in TTB_FUNDS.items():
        try:
            ticker = yf.Ticker(fund_group["ticker"])
            hist = ticker.history(period="3mo")
            
            if hist.empty:
                continue
            
            current_close = hist['Close'].iloc[-1]
            prev_close = hist['Close'].iloc[-2]
            change_pct = ((current_close - prev_close) / prev_close) * 100
            sma50 = hist['Close'].rolling(window=50).mean().iloc[-1]
            
            trend_text, trend_class = get_trend(current_close, sma50)
            # Market signal is calculated but specific fund recommendation overrides it for the list location
            
            # Helper to add funds
            def add_funds(fund_list, signal_text, signal_class):
                for fund_name in fund_list:
                    # Lookup NAV from FUND_DATA which contains live Finnomena results
                    # Try exact match first
                    fund_info = FUND_DATA.get(fund_name)
                    
                    # If not found, try stripping suffixes like (A) if common
                    if not fund_info:
                         # Try mapping known aliases if needed or just fallback
                         pass

                    if fund_info:
                        nav_val = fund_info['nav']
                        nav_date = fund_info['date']
                        # change_pct override if we want to use nav change instead of market price change?
                        # User wants NAV. So let's use NAV change if available?
                        # But get_fund_signals calculates change based on Ticker (Market Proxy).
                        # Let's keep Ticker change for "Market Trend" but show NAV date.
                    else:
                        # Fallback to hardcoded if available
                        nav_val = FUND_NAVS.get(fund_name, 0.0)
                        nav_date = datetime.now().strftime('%d/%m/%y') # Fallback date

                    results.append({
                        "name": fund_name,
                        "category": fund_group["category"],
                        "change_pct": round(change_pct, 2),
                        "market_trend": trend_text,
                        "signal": signal_text,
                        "signal_class": signal_class,
                        "nav": nav_val, 
                        "updated": nav_date
                    })

            # Add funds from each list
            add_funds(fund_group.get("accumulate", []), "ทยอยสะสม", "accumulate")
            add_funds(fund_group.get("hold", []), "ถือครอง", "hold")
            add_funds(fund_group.get("take_profit", []), "ทยอยขายทำกำไร", "wait") # Use 'wait' style (red) for sell
            
        except Exception as e:
            print(f"Error processing {key}: {e}")
            
    # Sort results: Accumulate first, then Hold, then Sell
    def sort_key(item):
        order = {"accumulate": 0, "hold": 1, "wait": 2}
        return order.get(item["signal_class"], 3)
    
    results.sort(key=sort_key)
    
    return jsonify(results)

def fetch_page(page_num=1):
    """Fetch a single page for fallback/seeding"""
    try:
        url = f"https://www.finnomena.com/fn3/api/fund/public/filter/overview?page={page_num}&size=100"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
            return data.get('data', {}).get('funds', [])
    except:
        return []

def fetch_settrade_nav(fund_code):
    """Fetch NAV directly from Settrade (More stable for Thai funds)"""
    try:
        # Bypass SSL verification for Settrade script access
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        # Try variations: "ES-CHINA-A" -> "ES-CHINA-A" or "ES-CHINA-A(A)"
        # Also try "ES-ULTIMATE-GA1" -> "ES-ULTIMATE GA1" (Settrade often uses spaces)
        targets = [
            fund_code, 
            fund_code + "(A)",
            fund_code + "-A",     # Add -A if missing
            fund_code.replace("-A", ""), # Remove -A if present
            fund_code.replace("-", " "), # Try space instead of dash
            fund_code.replace("-", "")   # Try compressed
        ]
        
        for t in targets:
            # properly encode spaces
            safe_t = urllib.parse.quote(t)
            url = f"https://www.settrade.com/api/settrade/mutual-fund/quote/{safe_t}"
            req = urllib.request.Request(
                url, 
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            try:
                with urllib.request.urlopen(req, context=ctx, timeout=3) as response:
                    if response.status == 200:
                        data = json.loads(response.read().decode('utf-8'))
                        if 'nav' in data and data['nav']:
                            # Map Settrade fields to our format
                            return {
                                "nav": data['nav'],
                                "date": data.get('navDate'), # YYYY-MM-DDT...
                                "change": data.get('diff', 0), # Check filed name
                                "short_code": t
                            }
            except: 
                continue # Try next variation
                
        return None
    except Exception as e:
        print(f"Settrade fetch error for {fund_code}: {e}")
        return None

def fetch_yahoo_nav(fund_code):
    """Fetch NAV from Yahoo Finance (fallback for global funds)"""
    try:
        # Try appending .BK (common for Thai funds on Yahoo)
        # e.g. ES-CHINA-A.BK
        symbol = f"{fund_code}.BK"
        ticker = yf.Ticker(symbol)
        
        # Fast info approach
        price = ticker.fast_info.last_price
        # If we got a price (and not None/0)
        if price and price > 0:
            return {
                "nav": price,
                "date": datetime.now().strftime('%Y-%m-%d'), # Yahoo fast_info doesn't clearly give date, assume latest
                "change": 0, # Difficult to get exact 1d change reliably in fast mode
                "short_code": symbol
            }
        return None
    except:
        return None

def fetch_fund_direct(fund_code):
    """Fetch fund data DIRECTLY from Finnomena fund detail page (More Reliable)"""
    # Try multiple code variations
    variations = [
        fund_code,
        fund_code.upper(),
        fund_code.replace("-", ""),
        fund_code.replace(" ", "-"),
        fund_code + "-A" if not fund_code.endswith("-A") else fund_code,
        fund_code.replace("-A", "") if fund_code.endswith("-A") else fund_code,
    ]
    
    for code in variations:
        try:
            # Finnomena Direct Fund API - more stable than search
            safe_code = urllib.parse.quote(code)
            url = f"https://www.finnomena.com/fn3/api/fund/public/detail/{safe_code}"
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json'
            })
            
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode('utf-8'))
                    fund_data = data.get('data', {})
                    
                    if fund_data and fund_data.get('nav'):
                        print(f"DEBUG: Direct fetch SUCCESS for {code}: NAV={fund_data.get('nav')}")
                        return {
                            'nav': float(fund_data.get('nav', 0)),
                            'nav_date': fund_data.get('nav_date', ''),
                            'return_1d': float(fund_data.get('return_1d', 0) or 0),
                            'short_code': fund_data.get('short_code', code),
                            'name_th': fund_data.get('name_th', '')
                        }
        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue  # Try next variation
            print(f"DEBUG: HTTP Error for {code}: {e.code}")
        except Exception as e:
            print(f"DEBUG: Direct fetch error for {code}: {str(e)[:50]}")
            continue
    
    return None

def fetch_fund_by_name(fund_name):
    """Fetch specific fund data using Finnomena Search API with retries/variations"""
    
    # Variations to try: "ES-CASH", "ES CASH", "ESCASH"
    variations = [fund_name]
    if "-" in fund_name:
        variations.append(fund_name.replace("-", " "))
        variations.append(fund_name.replace("-", ""))
    
    # Try fetching with each variation until success
    for query in variations:
        try:
            encoded_name = urllib.parse.quote(query)
            url = f"https://www.finnomena.com/fn3/api/fund/public/filter/overview?search={encoded_name}&page=1&size=20"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'})
            
            with urllib.request.urlopen(req, timeout=5) as response:
                raw = response.read().decode('utf-8')
                data = json.loads(raw)
                funds = data.get('data', {}).get('funds', [])
                print(f"DEBUG: Search '{query}' -> Found {len(funds)} items. First: {funds[0].get('short_code') if funds else 'None'}")
                
                # VALIDATION: The result MUST look like the query
                # Finnomena returns "Top Funds" if no match found, causing KT-PRECIOUS bug
                valid_funds = []
                for f in funds:
                    code = f.get('short_code', '').lower()
                    name = f.get('name_th', '').lower()
                    q_clean = query.lower().replace("-", "")
                    c_clean = code.replace("-", "")
                    
                    # Strict check: Query must be part of Code or Code part of Query
                    if q_clean in c_clean or c_clean in q_clean:
                        valid_funds.append(f)
                
                if valid_funds:
                     return valid_funds # Return filtered list
                     
        except Exception as e:
            print(f"Error searching {query}: {e}")
            
    return []

def update_fund_data_deprecated(target_names=None):
    """Concurrently fetch specific funds and update FUND_DATA"""
    global FUND_DATA
    print("Starting Targeted Finnomena sync...")
    start_time = time.time()
    
    # 1. Determine funds to fetch
    funds_to_fetch = set()
    
    if target_names:
        # Use provided list (from frontend)
        for n in target_names:
            funds_to_fetch.add(n)
    else:
        # Fallback to internal lists if no frontend list provided
        # Add all known funds from TTB_FUNDS
        for cat in TTB_FUNDS.values():
            funds_to_fetch.update(cat.get("accumulate", []))
            funds_to_fetch.update(cat.get("hold", []))
            funds_to_fetch.update(cat.get("take_profit", []))
        
        # Add GA Funds
        funds_to_fetch.update(ES_GA_FUNDS.keys())
        
        # Add Explicit Extras
        funds_to_fetch.update(["ES-GOVCP", "ES-GOVCP6M2", "ES-GOVCP6M43", "ES-CASH", "TMBGOLD"])

    funds_list = list(funds_to_fetch)
    print(f"Fetching {len(funds_list)} funds: {funds_list}")

    # 2. Concurrent Fetch (Targeted)
    fetched_data = []

    # OPTIONAL: Fetch Page 1 as seed data (Top 100 funds often cover 80% of needs)
    print("Fetching Page 1 seed data...")
    seed_funds = fetch_page(1)
    fetched_data.append({"query": "SEED", "results": seed_funds})
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        future_to_fund = {executor.submit(fetch_fund_by_name, name): name for name in funds_list}
        for future in concurrent.futures.as_completed(future_to_fund):
            fund_name = future_to_fund[future]
            try:
                results = future.result()
                # Store the search results along with the query name
                fetched_data.append({"query": fund_name, "results": results})
            except Exception as e:
                print(f"Failed to fetch {fund_name}: {e}")
            
    # 3. Process Data
    cnt = 0
    # Create valid Thai Months map
    thai_months = [
        "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
        "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."
    ]

    for item in fetched_data:
        query_name = item["query"]
        candidates = item["results"]
        
        if query_name == "SEED":
            # Process seed data: just add to FUND_DATA
            for f in candidates:
                code = f.get('short_code', '')
                try:
                     # Add to FUND_DATA directly
                     nav = float(f.get('nav', 0))
                     date_iso = f.get('nav_date', '')
                     change_1d = f.get('return_1d', 0)
                     
                     # Check date formatting
                     try:
                        if 'T' in date_iso: dt = datetime.strptime(date_iso.split('T')[0], '%Y-%m-%d')
                        else: dt = datetime.strptime(date_iso, '%Y-%m-%d')
                        thai_year = dt.year + 543
                        date_str = f"{dt.day} {thai_months[dt.month-1]} {str(thai_year)[2:]}"
                     except: date_str = date_iso
                     
                     FUND_DATA[code] = {
                        "nav": nav, "date": date_str, "change": change_1d, "raw_date": date_iso, "real_code": code
                     }
                except: pass
            continue

        # Find the best match for targeted search
        # 1. Exact Name/Code Match (Case Insensitive)
        match = None
        for f in candidates:
            if f.get('short_code', '').lower() == query_name.lower() or f.get('name_th', '').lower() == query_name.lower():
                match = f
                break
        
        # 2. If no exact match, take the first result if query is contained in code
        if not match and candidates:
             for f in candidates:
                if query_name.lower() in f.get('short_code', '').lower():
                    match = f
                    break
        
        if match:
            # Extract data
            code = match.get('short_code', '')
            nav = float(match.get('nav', 0))
            date_iso = match.get('nav_date', '')
            
            # Format Date
            try:
                if 'T' in date_iso:
                     dt = datetime.strptime(date_iso.split('T')[0], '%Y-%m-%d')
                else:
                     dt = datetime.strptime(date_iso, '%Y-%m-%d')
                
                thai_year = dt.year + 543
                date_str = f"{dt.day} {thai_months[dt.month-1]} {str(thai_year)[2:]}"
            except:
                date_str = date_iso or datetime.now().strftime('%d/%m/%y')

            change_1d = match.get('return_1d', 0)
            
            # Update FUND_DATA
            # Use the QUERY NAME as key too, to ensure we can look it up easily
            FUND_DATA[query_name] = { # Key by requested name
                "nav": nav,
                "date": date_str,
                "change": change_1d,
                "raw_date": date_iso,
                "real_code": code
            }
            # Also store by real code if different
            if code != query_name:
                 FUND_DATA[code] = FUND_DATA[query_name]

            cnt += 1
        else:
            print(f"No data found for {query_name}")
        
    print(f"Synced {cnt} funds in {time.time() - start_time:.2f}s")
    return cnt

@app.route('/api/sync-funds', methods=['POST'])
def sync_funds():
    """Trigger update from Finnomena with specific fund list"""
    try:
        # Get fund list from request body
        data = request.get_json()
        target_funds = data.get('funds', []) if data else []
        
        updated_data = update_fund_data(target_funds)
        
        return jsonify({
            "status": "success", 
            "message": f"Updated {len(updated_data)} funds", 
            "timestamp": datetime.now().strftime('%H:%M:%S'),
            "data": updated_data
        })
    except Exception as e:
        print(f"Sync error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


# ============================================================================
# AI ANALYSIS API (Account Plan 4 Por)
# ============================================================================
@app.route('/api/analyze-customer', methods=['POST'])
def analyze_customer():
    if not AI_AVAILABLE or not client:
        return jsonify({"success": False, "error": "AI Service Unavailable"}), 503
        
    try:
        data = request.json
        customer_profile = data.get('profile', {})
        portfolio = data.get('portfolio', {})
        
        # Construct Prompt with Product Knowledge
        
        # Serialize Product Data for Context
        funds_context = json.dumps(TTB_FUNDS, ensure_ascii=False)
        insurance_context = json.dumps(TTB_INSURANCE, ensure_ascii=False)

        prompt = f"""
You are a top-tier financial advisor assistant (Line BA) for TTB Bank. 
Your goal is to analyze the customer and proposed a 'Solution' that matches their profile perfectly using TTB Products.

**Customer Profile:**
- Name: {customer_profile.get('name', 'N/A')}
- Age: {customer_profile.get('age', 'N/A')}
- Occupation: {customer_profile.get('occupation', 'N/A')}
- Risk Level: {customer_profile.get('risk_level', 'N/A')}
- Marital Status: {customer_profile.get('marital_status', 'N/A')}
- Number of Children: {customer_profile.get('children', '0')}
- Monthly Income: {customer_profile.get('income', 'N/A')}
- Other Banks Used: {customer_profile.get('other_banks', 'N/A')}
- Deposits at Other Banks: {customer_profile.get('other_deposits', 'N/A')}
- Financial Goals: {customer_profile.get('financial_goals', 'N/A')}

**Current Portfolio:**
- Insurance: {', '.join(portfolio.get('insurance', [])) or 'None'}
- Mutual Funds: {', '.join(portfolio.get('funds', [])) or 'None'}
- Deposits: {', '.join(portfolio.get('deposits', [])) or 'None'}

**Available TTB Products (Reference Only):**
[Mutual Funds]
{funds_context}

[Insurance]
{insurance_context}

**Task:**
Generate a response in Thai following the "4 Por" structure. 
CRITICAL: You MUST include **TWO Tables** in the 'Solution' section.

1. **เปิด (Open)**: Friendly greeting personalized to their Age/Occupation/Life Stage.
2. **ปัญหา (Problem)**: Identify a gap (Tax, Health, Retirement, Inflation) relevant to them.
3. **ประโคม (Agitate)**: Show the negative impact if ignored (use numbers/scenarios if possible).
4. **ประโยชน์ (Solution)**: 
    - Recommend 1-2 Specific Products (Fund or Insurance) that fit them best.
    - **TABLE 1 (MANDATORY)**: Feature Comparison Table (ตาราง 1: เปรียบเทียบคุณสมบัติ)
    - **TABLE 2 (MANDATORY)**: Return Projection Table (ตาราง 2: เปรียบเทียบผลตอบแทนจนครบกำหนด)

📊 **TABLE 1 - เปรียบเทียบคุณสมบัติ:**
| 📋 หัวข้อเปรียบเทียบ | 🏦 บัญชีออมทรัพย์ เบสิก | 🛡️ **[ชื่อประกันที่แนะนำ]** |
|---------------------|----------------------|---------------------------|
| 💰 ผลตอบแทน (IRR) | 0.25% - 0.5% ต่อปี | ~2% - 3% ต่อปี |
| 🧾 สิทธิลดหย่อนภาษี | ❌ ไม่ได้รับ | ✅ สูงสุด 100,000 บาท |
| 🛡️ ความคุ้มครองชีวิต | ❌ ไม่มี | ✅ คุ้มครองตามทุนประกัน |
| 📈 การันตีเงินต้น | ❌ ไม่การันตี (ภาวะเงินเฟ้อ) | ✅ การันตีเงินคืน |
| 🎁 เงินปันผล | ❌ ไม่มี | ✅ มีโอกาสได้รับเพิ่ม |

📈 **TABLE 2 - เปรียบเทียบผลตอบแทนจนครบกำหนดสัญญา:**

**IMPORTANT: Adjust the projection years based on the specific insurance product recommended:**
- **ttb 16/2**: แสดงปีที่ 1, 3, 5, 8, 10, 14, **16 (ครบกำหนด)**
- **ttb 14/6 (Happy Life 14/6)**: แสดงปีที่ 1, 3, 5, 7, 10, **14 (ครบกำหนด)**
- **ttb 12/5**: แสดงปีที่ 1, 3, 5, 8, 10, **12 (ครบกำหนด)**
- **ttb 11/3**: แสดงปีที่ 1, 3, 5, 8, **11 (ครบกำหนด)**
- **ttb 10/5**: แสดงปีที่ 1, 3, 5, 7, **10 (ครบกำหนด)**
- **Smart Bonus 10/6**: แสดงปีที่ 1, 3, 5, 7, **10 (ครบกำหนด)**

Example table format (adjust years based on product):
| ปีที่ | 🏦 ฝากออมทรัพย์ (0.5%/ปี) | 🛡️ ประกัน [ชื่อแบบ] (IRR ~X%) | 💵 ส่วนต่าง |
|-------|--------------------------|-------------------------------|------------|
| 1 | xxx,xxx บาท | xxx,xxx บาท | +xx,xxx บาท |
| 3 | xxx,xxx บาท | xxx,xxx บาท | +xx,xxx บาท |
| ... | ... | ... | ... |
| **XX (ครบกำหนด)** | **xxx,xxx บาท** | **xxx,xxx บาท** | **+xxx,xxx บาท** |

**สรุปท้ายตาราง (MANDATORY - Add after Table 2):**
✅ รวมเงินคืน (ณ ปีครบกำหนด): XXX,XXX บาท
✅ รวมสิทธิลดหย่อนภาษี (ตลอดสัญญา): XXX,XXX บาท  
✅ รวมความคุ้มครองชีวิตที่ได้รับ: X,XXX,XXX บาท
📊 **ผลตอบแทนรวมมากกว่าฝากออมทรัพย์: +XXX,XXX บาท**

**Calculation Notes:**
- สมมติเงินลงทุนต่อเดือน = รายได้ลูกค้า x 10-15% หรือ 5,000-10,000 บาท/เดือน
- เงินฝากออมทรัพย์: ดอกเบี้ย 0.5%/ปี หักภาษี 15% ถ้าดอกเบี้ย >= 20,000 บาท
- ประกันสะสมทรัพย์: ใช้ IRR ตามแบบประกัน + รวมสิทธิลดหย่อนภาษี
- แสดงเป็นเลขจริงที่เป็นไปได้ เช่น 1,234,567 บาท

**Important:** Use realistic Thai Baht amounts formatted with commas. Use emojis in table headers.

**Tone:** Professional, Caring, Persuasive but Sincere.
**Constraint:** Focus on clarity and visual impact. Make tables easy to read.
"""
        # Retry logic for OpenAI
        max_retries = 3
        retry_delay = 2 # seconds

        for attempt in range(max_retries):
            try:
                response = client.chat.completions.create(
                    model=AI_MODEL,
                    messages=[
                        {"role": "system", "content": "You are a professional financial advisor assistant (Line BA). You excel at creating clear comparison tables with actual calculated numbers."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=2000 # Increased for two tables
                )
                
                analysis_text = response.choices[0].message.content
                
                return jsonify({
                    "success": True, 
                    "analysis": analysis_text
                })
            except Exception as e:
                error_str = str(e)
                if "rate_limit" in error_str.lower() and attempt < max_retries - 1:
                    print(f"Rate limit exceeded, retrying in {retry_delay}s... (Attempt {attempt+1}/{max_retries})")
                    time.sleep(retry_delay)
                    retry_delay *= 2 # Exponential backoff
                else:
                    raise e
        
    except Exception as e:
        print(f"AI Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

# ============================================================================
# NEW: Idle Money AI Recommendation API
# ============================================================================
@app.route('/api/analyze-idle-money', methods=['POST'])
def analyze_idle_money():
    if not AI_AVAILABLE or not client:
        return jsonify({"success": False, "error": "AI Service Unavailable"}), 503
        
    try:
        data = request.json
        customer_profile = data.get('profile', {})
        allocations = data.get('allocations', {})
        
        # Serialize Product Data for Context
        funds_context = json.dumps(TTB_FUNDS, ensure_ascii=False)
        insurance_context = json.dumps(TTB_INSURANCE, ensure_ascii=False)

        prompt = f"""
คุณคือที่ปรึกษาการเงินอาวุโสของ ttb reserve
ภารกิจของคุณคือวิเคราะห์โปรไฟล์ลูกค้าและ "ออกแบบการจัดสรรเงินลงทุน (Asset Allocation)" พร้อมทั้งแนะนำผลิตภัณฑ์ที่เหมาะสมที่สุด

**ข้อมูลลูกค้า:**
- อายุ: {customer_profile.get('age', 'N/A')} ปี
- อาชีพ: {customer_profile.get('occupation', 'N/A')}
- ระดับความเสี่ยงที่รับได้: {customer_profile.get('risk_level', 'ปานกลาง')}
- ระดับกลุ่มลูกค้า (ttb privilege): {customer_profile.get('privilege', 'Basic')}

**เป้าหมายการวิเคราะห์:**
1. **ออกแบบสัดส่วนการลงทุน (Time-based Allocation):**
   - คุณต้องปรับอัตราส่วน (%) ของเงิน ระยะสั้น (1-2 ปี), ระยะกลาง (3-5 ปี) และ ระยะยาว (5 ปีขึ้นไป) ใหม่ทั้งหมดตามความเหมาะสมของอายุและความเสี่ยง
   - **หลักการคิด:** 
     - หากลูกค้ายังหนุ่มสาว/วัยทำงาน และรับความเสี่ยงได้สูง -> ควรมี Long-term % และ Medium-term % ที่สูง (เช่น 20/40/40 หรือ 10/40/50)
     - หากลูกค้าใกล้เกษียณ หรือรับความเสี่ยงได้ต่ำ -> ควรเน้น Short-term % เพื่อรักษาสภาพคล่อง (เช่น 50/30/20 หรือ 60/20/20)
     - ผลรวมของทั้ง 3 ระยะต้องเท่ากับ 100% เป๊ะๆ

2. **แนะนำผลิตภัณฑ์ (Product Selection):**
   - แนะนำผลิตภัณฑ์ 1 ตัวต่อ 1 ระยะเวลา โดยใช้ชื่อตามเงื่อนไขต่อไปนี้:
     - **ระยะสั้น:** ให้แนะนำ "TTB No Fixed และ ES-IPlus แบ่งสัดส่วนตามความเหมาะสม" (หรือ Term Fund ถ้าเห็นว่าลูกค้าเน้นผลตอบแทนที่แน่นอน)
     - **ระยะกลาง:** ให้แนะนำ "ES-GA1 หรือ ES-GA2 ตามความเสี่ยงที่ลูกค้ารับได้ และ ES-GCORE แบ่งสัดส่วนตามความเหมาะสม"
     - **ระยะยาว:** ให้แนะนำเป็นประกัน "ttb US multi-asset 15/5" เท่านั้น

**รูปแบบการส่งคำตอบ (JSON Only):**
{{
  "allocations": {{ 
    "short_pct": [ตัวเลขเท่านั้น], 
    "medium_pct": [ตัวเลขเท่านั้น], 
    "long_pct": [ตัวเลขเท่านั้น] 
  }},
  "short": {{"name": "...", "return_rate": [float], "reason": "[เหตุผลสั้นๆ ที่จูงใจและเหมาะสมกับโปรไฟล์]"}},
  "medium": {{"name": "...", "return_rate": [float], "reason": "..."}},
  "long": {{"name": "ttb US multi-asset 15/5", "return_rate": 9.07, "reason": "..."}}
}}

[ข้อมูลผลิตภัณฑ์สำหรับอ้างอิง]:
{funds_context}
{insurance_context}
"""
        response = client.chat.completions.create(
            model=AI_MODEL,
            messages=[
                {"role": "system", "content": "You are a professional financial advisor. Output only valid JSON."},
                {"role": "user", "content": prompt}
            ],
            response_format={ "type": "json_object" },
            max_tokens=1000
        )
        
        analysis_text = response.choices[0].message.content
        return jsonify({
            "success": True, 
            "recommendation": json.loads(analysis_text)
        })
    except Exception as e:
        print(f"AI Idle Money Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

# ============================================================================
# NEW: Market Sentiment & Analysis API (User Requested)
# ============================================================================
@app.route('/api/market-sentiment')
def get_market_sentiment_api():
    try:
        # 1. Define Tickers
        tickers = {
            'SET': '^SET.BK',
            'S&P500': '^GSPC',
            'NASDAQ': '^IXIC',
            'GOLD': 'GC=F',
            'OIL': 'CL=F',
            'USD': 'THB=X',
            'EUR': 'EURTHB=X',
            'JPY': 'JPYTHB=X',
            'GBP': 'GBPTHB=X',
            'AUD': 'AUDTHB=X'
        }
        
        data = {}
        
        def fetch_ticker_data(key, symbol):
            try:
                t = yf.Ticker(symbol)
                hist = t.history(period="5d")
                
                if len(hist) < 2: return key, None
                
                curr = hist['Close'].iloc[-1]
                prev = hist['Close'].iloc[-2]
                day_open = hist['Open'].iloc[-1] # For FX open desc
                
                change = curr - prev
                percent = (change / prev) * 100
                
                return key, {
                    'price': curr,
                    'change': change,
                    'percent': percent,
                    'open': day_open,
                    'prev_close': prev
                }
            except Exception as e:
                return key, None

        # Parallel Fetch Data
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            future_to_key = {executor.submit(fetch_ticker_data, k, v): k for k, v in tickers.items()}
            for future in concurrent.futures.as_completed(future_to_key):
                k, res = future.result()
                if res: data[k] = res

        # 2. Fetch News (RSS) for "News of the Day"
        news_headlines = []
        try:
            rss_url = "https://th.investing.com/rss/news.rss"
            req = urllib.request.Request(rss_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=4) as response:
                xml_data = response.read().decode('utf-8')
                root = ET.fromstring(xml_data)
                for item in root.findall('.//item')[:3]:
                    title = item.find('title').text.strip()
                    news_headlines.append(f"• {title}")
        except:
            news_headlines = ["• [รออัพเดตข่าวเศรษฐกิจสำคัญวันนี้]", "• [รออัพเดตข่าวตลาดหุ้นต่างประเทศ]"]

        # 3. Generate Analysis Text
        if AI_AVAILABLE and client:
            try:
                # Prepare data for AI (use percentage for 'change' as expected by generate_market_analysis)
                ai_data = {}
                for k, v in data.items():
                    ai_data[k] = {
                        'price': v['price'],
                        'change': v['percent']
                    }
                analysis_text = generate_market_analysis(ai_data, news_headlines)
            except Exception as e:
                print(f"AI Market Sentiment Generation Error: {e}")
                analysis_text = "⚠️ ระบบ AI ขัดข้องในการสร้างบทวิเคราะห์"
        else:
            # Fallback for when AI is not configured
            dt = datetime.now()
            month_map_en = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
            date_str = f"{dt.day}-{month_map_en[dt.month-1]}-{dt.year+543}"
            
            usd = data.get('USD', {'price': 31.34, 'change': 0, 'percent': 0})
            sp500 = data.get('S&P500', {'price': 0, 'percent': 0})
            set_idx = data.get('SET', {'price': 0, 'percent': 0})
            gold = data.get('GOLD', {'price': 0, 'percent': 0})
            oil = data.get('OIL', {'price': 0, 'percent': 0})
            
            usd_change_desc = "แข็งค่า" if usd.get('change', 0) < 0 else "อ่อนค่า"
            
            analysis_text = f"""📅 {date_str}

💱 ค่าเงินบาทวันนี้: {usd['price']:.2f} ({usd_change_desc})
📈 ตลาดหุ้น S&P 500: {sp500['price']:,.0f} ({sp500['percent']:+.2f}%)
🇹🇭 SET Index: {set_idx['price']:,.2f} ({set_idx['percent']:+.2f}%)
🟡 ทองคำ: ${gold['price']:,.0f} | ⚫ น้ำมัน: ${oil['price']:.2f}

📰 ข่าวเด่น:
{chr(10).join(news_headlines[:2])}

(กรุณาตั้งค่า AI Key ใน .env เพื่อรับบทวิเคราะห์เชิงลึกจาก Claude)"""

        return jsonify({
            "success": True,
            "data": data,
            "analysisText": analysis_text
        })

    except Exception as e:
        print(f"Error in market-sentiment: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/ga-funds')
def get_ga_funds():
    """Get ES-ULTIMATE GA Series fund data with NAV from Finnomena"""
    results = []
    
    for fund_name, fund in ES_GA_FUNDS.items():
        try:
            # Try to fetch live NAV from Finnomena page
            # MATCH LOGIC: Check FUND_DATA for fund_name OR finnomena_id
            fund_info = FUND_DATA.get(fund_name) or FUND_DATA.get(fund.get("finnomena_id"))
            
            if fund_info:
                nav = fund_info['nav']
                nav_change = fund_info['change']
                update_date = fund_info['date']
            else:
                nav = fund.get("nav", 0)
                nav_change = 0 # Default if no live data
                update_date = fund.get("update_date", "")
            
            # Determine signal
            if nav_change > 0.5:
                signal = "ทยอยสะสม"
                signal_class = "accumulate"
            elif nav_change < -0.5:
                signal = "รอจังหวะ"
                signal_class = "wait"
            else:
                signal = "ถือครอง"
                signal_class = "hold"
            
            results.append({
                "name": fund_name,
                "short_name": fund.get("short_name", ""),
                "nav": nav,
                "nav_change": nav_change,
                "update_date": update_date,
                "signal": signal,
                "signal_class": signal_class,
                "ticker": fund.get("ticker", "^GSPC")
            })
            
        except Exception as e:
            print(f"Error fetching {fund_name}: {e}")
            results.append({
                "name": fund_name,
                "short_name": fund.get("short_name", ""),
                "nav": fund.get("nav", 0),
                "nav_change": 0,
                "update_date": fund.get("update_date", ""),
                "signal": "ถือครอง",
                "signal_class": "hold",
                "ticker": fund.get("ticker", "^GSPC")
            })
    
    return jsonify(results)


# ============================================================================
# AI MARKET ANALYSIS
# ============================================================================
def generate_market_analysis(market_data, news_headlines):
    """
    Generate "Analyst Grade" market analysis using OpenAI API.
    """
    if not AI_AVAILABLE or not client:
        return "⚠️ ระบบ AI ไม่สามารถใช้งานได้ (ขาด API Key)\nกรุณาตั้งค่า API Key ในไฟล์ .env"

    try:
        # Format data for prompt
        market_summary = "\n".join([
            f"- {k}: {v.get('price', 0):,.2f} (Change: {v.get('change', 0):+.2f}%)" 
            for k, v in market_data.items()
        ])
        
        news_summary = "\n".join([f"- {h}" for h in news_headlines])

        # Thai date formatting
        thai_months = [
            "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
            "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"
        ]
        month_idx = datetime.now().month - 1
        year_th = datetime.now().year + 543
        today_thai = f"{datetime.now().day} {thai_months[month_idx]} {year_th}"

        prompt = f"""
        คุณคือผู้เชี่ยวชาญด้านกลยุทธ์การลงทุนอาวุโส (Senior Investment Strategist) ของ ttb reserve
        ภารกิจของคุณคือเขียน "บทวิเคราะห์สภาวะตลาดประจำวัน" (Daily Market Insight) เพื่อส่งให้กลุ่มลูกค้า High Net Worth ผ่าน Social Media/LINE

        เงื่อนไขสำคัญที่สุด:
        1. **ข้อมูลในสรุปภาวะตลาดโลก (ข้อ 1) ต้องตรงตามข้อมูลจริงที่ให้มา 100% ห้ามแต่งตัวเลขเอง**
        2. การวิเคราะห์ (ข้อ 2-3) ต้องสอดคล้องกับตัวเลขจริงและข่าวที่ได้รับ
        3. น้ำเสียง (Tone) ต้องมีความน่าเชื่อถือ มืออาชีพ แต่เข้าใจง่าย (Smart & Insightful)
        4. ใช้ Emoji เพื่อความสวยงามแต่อย่าให้ดูเล่นจนเกินไป (Professional Look)

        วันที่: {today_thai}
        
        [ข้อมูลตลาดล่าสุด]:
        {market_summary}
        
        [หัวข้อข่าวเศรษฐกิจสำคัญ]:
        {news_summary}
        
        โครงสร้างเนื้อหา (จัดรูปแบบ Markdown สำหรับ Social Messaging):
        หัวข้อ: 📅 **บทวิเคราะห์สภาวะตลาด ประจำวันที่ {today_thai}**
        
        1. 📊 **สรุปภาวะตลาดโลก** (Major Indices)
           - แสดงรายการดัชนีสำคัญ: S&P 500, SET Index, ทองคำ, น้ำมัน WTI
           - รูปแบบ: • [ไอคอน] [ชื่อดัชนี]: [ราคา] ([+/-] [เปอร์ตเซ็นต์]%)
        
        2. 🌏 **สรุปภาพรวมตลาด** (Market Summary)
           - วิเคราะห์ความเชื่อมโยงระหว่างตัวเลขตลาดและข่าววันนี้ 
           - สรุปทิศทางค่าเงินบาท (เทียบดอลลาร์) และปัจจัยกดดัน/หนุน
            
        3. 📈 **แนวโน้มและปัจจัยที่ต้องจับตา** (Outlook & Key Events)
           - ประเมินทิศทางตลาดในระยะสั้น (วันนี้-พรุ่งนี้)
           - ระบุ Event สำคัญที่นักลงทุนควรเตรียมตัว (เช่น ตัวเลขเงินเฟ้อ, การประชุมเฟด ฯลฯ ตามข่าว)
            
        4. 🎯 **กลยุทธ์แนะนำเบื้องต้น** (Investment Strategy)
           - ให้มุมมองกรอบค่าเงิน (USD/THB, EUR/THB, JPY/THB) จากแนวโน้มตลาด
           - คำแนะนำ Action สั้นๆ สำหรับลูกค้า (เช่น ทยอยสะสม, ถือครองเพื่อดูทิศทาง หรือขายทำกำไร)
        """

        response = client.chat.completions.create(
            model=AI_MODEL,
            messages=[
                {"role": "system", "content": "You are a professional financial strategist at ttb reserve. You provide accurate, factual, and insightful market analysis. You must use the provided data strictly and avoid making up numbers."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1500
        )
        
        return response.choices[0].message.content.strip()
    
    except Exception as e:
        print(f"AI Generation Error: {e}")
        return f"ระบบ AI ขัดข้อง: {str(e)} (แสดงข้อมูลดิบแทน)"

@app.route('/api/line-message')
def get_line_message():
    """Generate detailed LINE message in TTB FX style"""
    today = datetime.now().strftime('%d-%b-%Y')
    
    # Fetch THB rate
    thb_rate = 34.50  # Default
    thb_change = "แข็งค่า"
    try:
        ticker = yf.Ticker("THB=X")
        hist = ticker.history(period="5d")
        if not hist.empty:
            thb_rate = hist['Close'].iloc[-1]
            prev_rate = hist['Close'].iloc[-2]
            # If current rate (e.g. 34.5) is < prev (34.6), it means THB is STRONGER (fewer Baht per USD)
            thb_change = "แข็งค่า" if thb_rate < prev_rate else "อ่อนค่า"
    except:
        pass
    
    # Fetch key market data
    # Fetch key market data in parallel
    market_data = {}
    
    def fetch_market_item(name, symbol):
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="5d")
            if not hist.empty:
                current = hist['Close'].iloc[-1]
                prev = hist['Close'].iloc[-2]
                change = ((current - prev) / prev) * 100
                return name, {"price": current, "change": change}
        except:
            return name, None
            
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        items_to_fetch = [("S&P 500", "^GSPC"), ("Gold", "GC=F"), ("SET", "^SET.BK"), ("Nasdaq", "^IXIC"), ("Oil WTI", "CL=F")]
        future_to_item = {executor.submit(fetch_market_item, name, symbol): name for name, symbol in items_to_fetch}
        
        for future in concurrent.futures.as_completed(future_to_item):
            name, res = future.result()
            if res:
                market_data[name] = res
    
    # Determine sentiment
    positive_markets = sum(1 for d in market_data.values() if d.get("change", 0) > 0)
    if positive_markets >= 3:
        sentiment = "เชิงบวก"
        sentiment_emoji = "🟢"
    elif positive_markets >= 2:
        sentiment = "ผสมผสาน"
        sentiment_emoji = "🟡"
    else:
        sentiment = "ระมัดระวัง"
        sentiment_emoji = "🔴"
    
    # Build message in TTB FX style
    sp500_info = market_data.get("S&P 500", {})
    gold_info = market_data.get("Gold", {})
    set_info = market_data.get("SET", {})
    oil_info = market_data.get("Oil WTI", {})
    
    # Fetch news headlines for summary - Use Thai financial news
    news_headlines = []
    thai_rss_sources = [
        "https://th.investing.com/rss/news.rss",  # Investing.com Thailand
        "https://www.bangkokbiznews.com/rss/feed/news.xml",  # Bangkok Biz News
    ]
    
    for rss_url in thai_rss_sources:
        if len(news_headlines) >= 3:
            break
        try:
            req = urllib.request.Request(rss_url, headers={'User-Agent': 'Mozilla/5.0'})
            response = urllib.request.urlopen(req, timeout=5)
            xml_data = response.read().decode('utf-8')
            root = ET.fromstring(xml_data)
            items = root.findall('.//item')[:3]
            for item in items:
                title = item.find('title')
                if title is not None and title.text:
                    # Clean title - remove source suffix
                    clean_title = re.sub(r'\s*[-|]\s*[A-Za-z\s]+$', '', title.text)[:80]
                    if clean_title and clean_title not in news_headlines:
                        news_headlines.append(clean_title)
        except:
            pass
    
    # Fallback if no news fetched
    if not news_headlines:
        news_headlines = [
            "ตลาดหุ้นปรับตัวตามทิศทางตลาดโลก",
            "นักลงทุนจับตาตัวเลขเศรษฐกิจสหรัฐ",
            "ทองคำยังคงได้รับแรงหนุนจากปัจจัยเสี่ยง"
        ]
    
    # Build news section
    # Build news section
    news_section = "\n".join([f"• {h}" for h in news_headlines[:3]])

    # Generate Analysis using AI
    try:
        market_data_for_ai = {
            "THB Rate": {"price": thb_rate, "change": 0}, 
            "S&P 500": sp500_info,
            "SET Index": set_info,
            "Gold": gold_info,
            "Oil": oil_info
        }
        ai_analysis = generate_market_analysis(market_data_for_ai, news_headlines)
    except Exception as e:
        ai_analysis = f"Error generating analysis: {e}"

    
    message = ai_analysis # Use AI result as the main message
    
    # Keeping old logic comment out or removed
    # message = f"""..."""
    
    # Build SHORT message for LINE URL (to avoid HTTP 400)
    short_message = f"""📅 {today}

💼 กองทุนแนะนำ:
🟢 ทยอยสะสม: (ดูในรูป)
📈 ตลาด: S&P {sp500_info.get('change', 0):+.2f}% | ทองคำ {gold_info.get('change', 0):+.2f}%"""

    
    # URL Encoded message
    encoded_msg = urllib.parse.quote(short_message)

    return jsonify({
        "message": message,
        "line_url": f"https://line.me/R/msg/text/?{encoded_msg}",
        "line_app_url": "line://msg/text/Paste_Report_Here" 
    })

@app.route('/api/send-line-notify', methods=['POST'])
def send_line_notify():
    """Send message directly to LINE via LINE Messaging API (Broadcast)"""
    if not LINE_CHANNEL_ACCESS_TOKEN:
        return jsonify({"success": False, "error": "LINE Channel Access Token not configured."}), 400
    
    try:
        # Get the message from line-message endpoint
        from flask import current_app
        with current_app.test_client() as client:
            response = client.get('/api/line-message')
            data = response.get_json()
            message = data.get('message', '')
        
        if not message:
            return jsonify({"success": False, "error": "Failed to generate message"}), 500
        
        # Send via LINE Messaging API Broadcast
        headers = {
            'Authorization': f'Bearer {LINE_CHANNEL_ACCESS_TOKEN}',
            'Content-Type': 'application/json'
        }
        
        # LINE Messaging API uses JSON format
        payload = json.dumps({
            "messages": [
                {
                    "type": "text",
                    "text": message
                }
            ]
        }).encode('utf-8')
        
        req = urllib.request.Request(
            'https://api.line.me/v2/bot/message/broadcast',
            data=payload,
            headers=headers,
            method='POST'
        )
        
        response = urllib.request.urlopen(req, timeout=10)
        
        # Broadcast returns empty body on success (HTTP 200)
        if response.status == 200:
            return jsonify({"success": True, "message": "ส่ง LINE สำเร็จ! ข้อความถูกส่งไปยังผู้ติดตามทุกคน"})
        else:
            return jsonify({"success": False, "error": "Failed to send"}), 400
            
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        return jsonify({"success": False, "error": f"LINE API Error: {error_body}"}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/news')
def get_news():
    """Fetch financial news from multiple RSS sources"""
    news_items = []
    
    # News sources with RSS feeds - Use English keywords to avoid encoding issues
    rss_feeds = [
        {
            "name": "Thai Stock News",
            "url": "https://news.google.com/rss/search?q=SET+index+Thailand+stock&hl=en&gl=TH&ceid=TH:en",
            "category": "ตลาดไทย"
        },
        {
            "name": "Thailand Economy",
            "url": "https://news.google.com/rss/search?q=Thailand+economy+investment&hl=en&gl=TH&ceid=TH:en",
            "category": "เศรษฐกิจ"
        },
        {
            "name": "Global Markets",
            "url": "https://news.google.com/rss/search?q=stock+market+wall+street+S%26P500&hl=en&gl=US&ceid=US:en",
            "category": "ตลาดโลก"
        },
        {
            "name": "Gold Oil News",
            "url": "https://news.google.com/rss/search?q=gold+price+OR+oil+price+commodity&hl=en&gl=US&ceid=US:en",
            "category": "สินค้าโภคภัณฑ์"
        },
        {
            "name": "Forex THB",
            "url": "https://news.google.com/rss/search?q=Thai+baht+exchange+rate+USD&hl=en&gl=TH&ceid=TH:en",
            "category": "ค่าเงิน"
        }
    ]
    
    for feed in rss_feeds:
        try:
            req = urllib.request.Request(
                feed["url"],
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            response = urllib.request.urlopen(req, timeout=5)
            xml_data = response.read().decode('utf-8')
            root = ET.fromstring(xml_data)
            
            # Parse RSS items
            items = root.findall('.//item')[:3]  # Get top 3 from each source
            
            for item in items:
                title = item.find('title')
                link = item.find('link')
                pub_date = item.find('pubDate')
                
                if title is not None:
                    # Clean up title
                    title_text = title.text or ""
                    # Remove source suffix like " - Reuters"
                    title_text = re.sub(r'\s*-\s*[A-Za-z\s]+$', '', title_text)
                    
                    news_items.append({
                        "title": title_text[:100],
                        "link": link.text if link is not None else "#",
                        "date": pub_date.text[:16] if pub_date is not None else "",
                        "category": feed["category"],
                        "source": feed["name"]
                    })
                    
        except Exception as e:
            # Use ASCII-safe representation to avoid console encoding issues on Windows
            feed_name_safe = feed['name'].encode('ascii', 'replace').decode('ascii')
            print(f"Error fetching news from {feed_name_safe}: {e}")
    
    # Sort by date (newest first) and limit to 12 items
    return jsonify({
        "timestamp": datetime.now().strftime('%d/%m/%Y %H:%M'),
        "news": news_items[:12]
    })

@app.route('/api/chart/<ticker_name>')
@app.route('/api/chart/<ticker_name>/<period>')
def get_chart_data(ticker_name, period="6mo"):
    """Get historical price data for chart display"""
    # Find the ticker symbol from TICKERS or TTB_FUNDS or ES_GA_FUNDS
    symbol = TICKERS.get(ticker_name)
    
    # If not found in TICKERS, check TTB_FUNDS
    if not symbol:
        for fund_key, fund_data in TTB_FUNDS.items():
            if fund_data.get("category") == ticker_name:
                symbol = fund_data.get("ticker")
                break
    
    # If still not found, check ES_GA_FUNDS
    if not symbol:
        if ticker_name in ES_GA_FUNDS:
            symbol = ES_GA_FUNDS[ticker_name].get("ticker")
    
    if not symbol:
        return jsonify({"error": "Ticker not found"}), 404
    
    # Map period parameter to yfinance period
    period_map = {
        "1d": "5d",      # 5 days for daily view
        "1w": "1mo",     # 1 month for weekly
        "1mo": "3mo",    # 3 months for monthly
        "6mo": "6mo",    # 6 months
        "1y": "1y",      # 1 year
        "5y": "5y"       # 5 years
    }
    yf_period = period_map.get(period, "6mo")
    
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=yf_period)
        
        if hist.empty:
            return jsonify({"error": "No data available"}), 404
        
        # Date format based on period
        if period in ["1d", "1w"]:
            date_format = '%d/%m'
        elif period in ["1mo", "6mo"]:
            date_format = '%d/%m'
        else:
            date_format = '%b %y'
        
        # Prepare data for Chart.js
        dates = [d.strftime(date_format) for d in hist.index]
        prices = [round(p, 2) for p in hist['Close'].tolist()]
        
        # OHLC data for candlestick chart
        ohlc = []
        for i, (idx, row) in enumerate(hist.iterrows()):
            ohlc.append({
                "x": i,
                "o": round(row['Open'], 2),
                "h": round(row['High'], 2),
                "l": round(row['Low'], 2),
                "c": round(row['Close'], 2)
            })
        
        # Calculate moving averages
        sma20 = hist['Close'].rolling(window=min(20, len(hist))).mean().fillna(method='bfill').tolist()
        sma50 = hist['Close'].rolling(window=min(50, len(hist))).mean().fillna(method='bfill').tolist()
        
        # Calculate min/max for scale
        min_price = min(prices) * 0.95
        max_price = max(prices) * 1.05
        
        # Volume data
        volumes = hist['Volume'].tolist() if 'Volume' in hist.columns else [0] * len(prices)
        volume_colors = []
        for i, row in enumerate(hist.iterrows()):
            if i == 0:
                volume_colors.append('rgba(100, 100, 100, 0.5)')
            else:
                if prices[i] >= prices[i-1]:
                    volume_colors.append('rgba(40, 167, 69, 0.6)')  # Green for up
                else:
                    volume_colors.append('rgba(220, 53, 69, 0.6)')  # Red for down
        
        return jsonify({
            "name": ticker_name,
            "symbol": symbol,
            "period": period,
            "dates": dates,
            "prices": prices,
            "ohlc": ohlc,
            "volumes": volumes,
            "volume_colors": volume_colors,
            "sma20": [round(s, 2) for s in sma20],
            "sma50": [round(s, 2) for s in sma50],
            "min_price": round(min_price, 2),
            "max_price": round(max_price, 2),
            "current_price": prices[-1] if prices else 0,
            "change_pct": round(((prices[-1] - prices[-2]) / prices[-2]) * 100, 2) if len(prices) > 1 else 0,
            "last_ohlc": ohlc[-1] if ohlc else None
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================================
# NEW FUND SYNC LOGIC (BULK DOWNLOAD - ROBUST)
# ============================================================================

def fetch_all_funds_bulk():
    """Fetch ALL funds from Finnomena using safe pagination"""
    all_funds = []
    page = 1
    # size = 100 # Still ask for 100, but don't rely on it
    
    while True:
        try:
            # print(f"DEBUG: Fetching Bulk Funds Page {page}...", end='\r')
            url = f"https://www.finnomena.com/fn3/api/fund/public/filter/overview?page={page}&size=100"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                 data = json.loads(response.read().decode('utf-8'))
                 funds = data.get('data', {}).get('funds', [])
                 all_funds.extend(funds)
                 
                 # New Logic: Get total pages from metadata
                 pagination = data.get('data', {}).get('pagination', {})
                 total_pages = pagination.get('page_total')
                 
                 # Loop control
                 if total_pages:
                     if page >= total_pages:
                         break
                 else:
                     # Fallback: if no metadata, stop when no data
                     if len(funds) == 0:
                         break
                 
                 # Safety limit (increased for small page sizes)
                 if page > 500:
                     break
                     
                 page += 1
                 # Fast enough to not timeout, slow enough to be nice
                 # time.sleep(0.05) 
                 
        except Exception as e:
            print(f"Error fetching bulk page {page}: {e}")
            break
            
    print(f"DEBUG: Total funds fetched globally: {len(all_funds)}")
    return all_funds

def update_fund_data(target_names=None):
    """Update fund data using BULK DOWNLOAD Strategy"""
    global FUND_DATA
    FUND_DATA = {} # FORCE CLEAR OLD DATA
    

    
    # 1. Fetch ALL funds
    try:
        raw_funds = fetch_all_funds_bulk()
    except Exception as e:
        print(f"Error in bulk fetch: {e}")
        raw_funds = []
        
    if not raw_funds:
        print("DEBUG: Bulk fetch returned empty. Proceeding to limited targeted fetch...")
        
    # print(f"DEBUG: Processing {len(raw_funds)} raw funds for lookup...")
        
    # 2. Build Lookup Map
    fund_lookup = {}
    thai_months = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]

    for f in raw_funds:
        # Key 1: Short Code (e.g. "K-USA-A(A)")
        code = f.get('short_code', '').upper().strip()
        nav_date = f.get('nav_date', '')
        nav = float(f.get('nav', 0) or 0)
        
        # --- GARBAGE FILTER: Ignore Default/Junk Data ---
        # KT-PRECIOUS (14.4373) often appears endlessly in bugged pagination
        if code == 'KT-PRECIOUS' or nav == 14.4373:
             continue 

        # Parse Date
        date_str = ""
        try:
             if 'T' in nav_date: dt = datetime.strptime(nav_date.split('T')[0], '%Y-%m-%d')
             else: dt = datetime.strptime(nav_date, '%Y-%m-%d')
             thai_year = dt.year + 543
             date_str = f"{dt.day} {thai_months[dt.month-1]} {str(thai_year)[2:]}"
        except:
             date_str = nav_date

        clean_data = {
            "nav": nav,
            "date": date_str,
            "change": float(f.get('return_1d', 0) or 0),
            "raw_date": nav_date,
            "real_code": f.get('short_code', '')
        }
        
        # Add to lookup
        if code:
            fund_lookup[code] = clean_data
            # Key 2: Normalized (no hyphens) e.g. "KUSAA(A)"
            fund_lookup[code.replace("-", "")] = clean_data
            # Key 3: Normalized (no spaces)
            fund_lookup[code.replace(" ", "")] = clean_data
            
    # 3. Determine Targets
    if target_names:
        targets = set(target_names)
    else:
        # Default Targets
        targets = set(ES_GA_FUNDS.keys())
        for f in ES_GA_FUNDS.values():
            if f.get("finnomena_id"): targets.add(f.get("finnomena_id"))
            
        for cat in TTB_FUNDS.values():
            targets.update(cat.get("accumulate", []))
            targets.update(cat.get("hold", []))
            targets.update(cat.get("take_profit", []))
            
    # 4. Match Targets
    found_count = 0
    for t in targets:
        if not t: continue
        t_upper = t.upper().strip()
        
        # Try finding in lookup
        match = fund_lookup.get(t_upper)
        if not match: match = fund_lookup.get(t_upper.replace("-", ""))
        if not match: match = fund_lookup.get(t_upper.replace(" ", ""))
        
        # 0. Manual Mapping (Fix specific issues)
        if not match:
             manual_map = {
                 "ES-CHINA-A": "ES-CHINAA", # From Image: No hyphen
                 "ES-GCORE": "ES-GCORE-A", # Trying -A suffix
                 "ES-GGREEN": "ES-GGREEN-A", # Trying -A suffix
                 "ES-GINNO-A": "ES-GINNO-A", # Matches image, keep exact
                 "ES-PROP": "ES-PROP",
                 "SCBSEMI": "SCBSEMI(A)",
                 "ONE-UGG-RA": "ONE-UGG-RA",
                 "ES-IPLUS": "ES-IPLUS",
                 "TSP3": "T-SP3",
                 "ES-USBLUECHIP": "ES-USBLUECHIP-A", # Guessing
                 "ES-GF-A": "ES-GF-A",
                 "ES-INDONESIA": "ES-INDONESIA",
                 "ES-GDIV": "ES-GDIV",
                 "ES-GQG": "ES-GQG",
                 "ES-GCG-A": "ES-GCG-A",
                 "UCI": "UCI",
                 "ES-EAE": "ES-EAE",
                 "ES-VIETNAM": "ES-VIETNAM"
             }
             mapped_code = manual_map.get(t_upper)
             if mapped_code:
                 match = fund_lookup.get(mapped_code.upper()) or fund_lookup.get(mapped_code.upper().replace("-", ""))
                 if match: print(f"DEBUG: Manual Map '{t}' -> '{mapped_code}'")

        # Fallback: Fuzzy Match (Disabled for debugging "Same Price" issue)
        # if not match:
        #    for code, data in fund_lookup.items():
        #        if code.startswith(t_upper):
        #             if len(code) - len(t_upper) < 5: 
        #                match = data
        #                break
            
        # Logging to file for debugging
        with open("sync_debug.log", "a", encoding="utf-8") as f:
            if match:
                 # f.write(f"Target: {t} | Matched: {match['real_code']} | NAV: {match['nav']}\n")
                 pass
            else:
                 f.write(f"[{datetime.now()}] Target: {t} | NOT FOUND in Bulk Data\n")
        
        if match:
            FUND_DATA[t] = match # Store using the requested name as key
            found_count += 1
        else:
            print(f"DEBUG: Fund {t} not found in lookup.")
            
            # --- Check Manual Map for Fallbacks ---
            search_target = t
            t_upper = t.upper().strip()
            # If t is in manual map keys, use the mapped value for API calls
            manual_map = {
                 # EASTSPRING Ultimate GA Series
                 "ES-ULTIMATE-GA1": "ES-ULTIMATE GA1",
                 "ES-ULTIMATE-GA2": "ES-ULTIMATE GA2", 
                 "ES-ULTIMATE-GA3": "ES-ULTIMATE GA3",
                 # EASTSPRING Fixed Income
                 "ES-CASH": "ES-CASH",
                 "ES-IPLUS": "ES-IPLUS",
                 "ES-TM": "ES-TM",
                 # EASTSPRING Equity
                 "ES-GQG": "ES-GQG",
                 "ES-GCORE": "ES-GCORE",
                 "ES-US500": "ES-US500",
                 "ES-USTECH": "ES-USTECH",
                 "ES-CHINA-A": "ES-CHINAA",
                 "ES-GINO": "ES-GINO",
                 "ES-GGREEN": "ES-GGREEN",
                 "ES-SMART-BETA": "ES-SMARTBETA",
                 "ES-PROPINFRAFLEX": "ES-PROPINFRAFLEX",
                 # SCBAM
                 "SCBASF1YAE": "SCBASF1YAE",
                 "SCBSFF": "SCBSFF",
                 "SCBASF1YAC": "SCBASF1YAC",
                 # ONEAM
                 "ONE-LS4-UI": "ONE-LS4-UI",
                 # TISCOASSET  
                 "TISCOHD-A": "TISCOHD-A",
                 # KASSET
                 "KGSTEP-A": "KGSTEP-A",
                 "KGSTEP-B": "KGSTEP-B",
                 # Other
                 "TSP3": "TSP3",
                 "6M22": "6M22"
            }
            if t_upper in manual_map:
                search_target = manual_map[t_upper]
                print(f"DEBUG: Using mapped name '{search_target}' for fallback APIs (was '{t}')")

            # --- Fallback 0: Finnomena DIRECT API (NEW - Most Reliable) ---
            print(f"DEBUG: Attempting Finnomena DIRECT API for {search_target}...")
            direct_data = fetch_fund_direct(search_target)
            if direct_data:
                nav = float(direct_data.get('nav', 0))
                nav_date = direct_data.get('nav_date', '')
                # Format Date
                try:
                    if 'T' in nav_date: dt = datetime.strptime(nav_date.split('T')[0], '%Y-%m-%d')
                    else: dt = datetime.strptime(nav_date, '%Y-%m-%d')
                    thai_year = dt.year + 543
                    date_str = f"{dt.day} {thai_months[dt.month-1]} {str(thai_year)[2:]}"
                except: date_str = nav_date
                
                FUND_DATA[t] = {
                    "nav": nav,
                    "date": date_str,
                    "change": direct_data.get('return_1d', 0),
                    "raw_date": nav_date,
                    "real_code": direct_data.get('short_code', t)
                }
                found_count += 1
                print(f"DEBUG: Finnomena DIRECT SUCCESS for {t}")
                continue  # Skip other fallbacks

            # --- Fallback 1: Settrade API (Primary Fallback - Very Stable) ---
            print(f"DEBUG: Attempting Settrade fallback for {search_target}...")
            st_data = fetch_settrade_nav(search_target)
            if st_data:
                 nav = float(st_data.get('nav', 0))
                 nav_date = st_data.get('date', '')
                 # Format Date
                 try:
                     if 'T' in nav_date: dt = datetime.strptime(nav_date.split('T')[0], '%Y-%m-%d')
                     else: dt = datetime.strptime(nav_date, '%Y-%m-%d')
                     thai_year = dt.year + 543
                     date_str = f"{dt.day} {thai_months[dt.month-1]} {str(thai_year)[2:]}"
                 except: date_str = nav_date
                 
                 FUND_DATA[t] = {
                     "nav": nav,
                     "date": date_str,
                     "change": st_data.get('change', 0),
                     "raw_date": nav_date,
                     "real_code": st_data.get('short_code', '')
                 }
                 found_count += 1
                 print(f"DEBUG: Settrade search SUCCESS for {t}")
                 continue # Skip others

            # --- Fallback 2: Yahoo Finance (Great for global funds) ---
            print(f"DEBUG: Attempting Yahoo Finance fallback for {search_target}...")
            yf_data = fetch_yahoo_nav(search_target)
            if yf_data:
                 FUND_DATA[t] = {
                     "nav": float(yf_data['nav']),
                     "date": datetime.now().strftime('%d %b %y'), # Approximate
                     "change": 0,
                     "raw_date": datetime.now().strftime('%Y-%m-%d'),
                     "real_code": yf_data['short_code']
                 }
                 found_count += 1
                 print(f"DEBUG: Yahoo search SUCCESS for {t}")
                 continue

            # --- Fallback 3: Finnomena Targeted Search API (SAFE MODE) ---
            # Re-enabled but with STRICT validation to avoid "KT-PRECIOUS" / Page 1 defaults
            print(f"DEBUG: Attempting Finnomena fallback search (SAFE) for {search_target}...")
            try:
                search_results = fetch_fund_by_name(search_target)
                if search_results:
                     # Take the first best match
                     best = search_results[0]
                     best_code = best.get('short_code', '').upper()
                     
                     # VALIDATION: Check if result actually matches the query
                     # Prevent garbage return (like KT-PRECIOUS for everything)
                     target_clean = search_target.upper().replace("-", "").replace(" ", "")
                     result_clean = best_code.replace("-", "").replace(" ", "")
                     
                     if target_clean in result_clean or result_clean in target_clean:
                         nav = float(best.get('nav', 0))
                         nav_date = best.get('nav_date', '')
                         
                         # Format Date
                         try:
                             if 'T' in nav_date: dt = datetime.strptime(nav_date.split('T')[0], '%Y-%m-%d')
                             else: dt = datetime.strptime(nav_date, '%Y-%m-%d')
                             thai_year = dt.year + 543
                             date_str = f"{dt.day} {thai_months[dt.month-1]} {str(thai_year)[2:]}"
                         except: date_str = nav_date
                         
                         FUND_DATA[t] = {
                             "nav": nav,
                             "date": date_str,
                             "change": best.get('return_1d', 0),
                             "raw_date": nav_date,
                             "real_code": best.get('short_code', '')
                         }
                         found_count += 1
                         print(f"DEBUG: Finnomena SAFE search SUCCESS for {t} -> {best.get('short_code')}")
                     else:
                         print(f"DEBUG: Finnomena search REJECTED: '{best_code}' does not match target '{search_target}'")
            except Exception as e:
                print(f"DEBUG: Fallback search failed for {t}: {e}")



        # --- FORCE INITIALIZATION (The Nuclear Option) ---
        # If still not found after all fallbacks, create a placeholder entry
        # This prevents the "No Matching Data" error in the UI
        if t not in FUND_DATA:
            print(f"DEBUG: FORCE INIT for {t} (All sources failed)")
            FUND_DATA[t] = {
                "nav": 0.0000,
                "date": datetime.now().strftime('%d %b %y'),
                "change": 0.0,
                "raw_date": datetime.now().strftime('%Y-%m-%d'),
                "real_code": t + " (Offline)"
            }
            # found_count += 1 # Don't count as 'found' but it is now in data

    print(f"Synced {found_count} requested funds out of {len(targets)} targets.")
    
    # Return the simple list of updated fund info for the frontend
    result_list = []
    for t in targets:
        if t in FUND_DATA:
            idata = FUND_DATA[t]
            result_list.append({
                "name": t,
                "nav": idata['nav'],
                "change_pct": idata['change'], 
                "updated": idata['date'],
                "nav_change": idata['change'] 
            })
            
    return result_list

if __name__ == '__main__':
    import socket
    def get_local_ip():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "localhost"
    
    local_ip = get_local_ip()
    print("=" * 50)
    print("   TTB Market Analysis Dashboard")
    print(f"   Computer : http://localhost:5000")
    print(f"   Phone/iPad: http://{local_ip}:5000")
    print("=" * 50)
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
