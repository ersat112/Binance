from fastapi import FastAPI
import requests
import pandas as pd
import uvicorn

# --- Telegram Ayarları ---
BOT_TOKEN = "7304289957:AAEqNyrRlhzAupzDYCV8lFRcGfv82uKU174"
CHAT_ID = "1509047266"

# --- FastAPI Uygulaması ---
app = FastAPI()

# --- Binance Verisi Çekme ---
def fetch_binance_ohlcv(symbol="BTCUSDT", interval="5m", limit=100):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    response = requests.get(url)
    data = response.json()

    ohlcv = pd.DataFrame(data, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_asset_volume', 'number_of_trades',
        'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
    ])
    ohlcv['open'] = ohlcv['open'].astype(float)
    ohlcv['high'] = ohlcv['high'].astype(float)
    ohlcv['low'] = ohlcv['low'].astype(float)
    ohlcv['close'] = ohlcv['close'].astype(float)
    ohlcv['volume'] = ohlcv['volume'].astype(float)
    ohlcv['timestamp'] = pd.to_datetime(ohlcv['timestamp'], unit='ms')

    # İndikatörleri ekle
    ohlcv = enrich_data_with_indicators(ohlcv)

    return ohlcv

# --- RSI Hesaplama ---
def calculate_rsi(data, period=14):
    delta = data['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

# --- MACD Hesaplama ---
def calculate_macd(data, short_period=12, long_period=26, signal_period=9):
    exp1 = data['close'].ewm(span=short_period, adjust=False).mean()
    exp2 = data['close'].ewm(span=long_period, adjust=False).mean()
    macd = exp1 - exp2
    signal = macd.ewm(span=signal_period, adjust=False).mean()
    histogram = macd - signal
    return macd, signal, histogram

# --- Veriye İndikatör Ekleme ---
def enrich_data_with_indicators(data):
    data['RSI_7'] = calculate_rsi(data, 7)
    data['RSI_14'] = calculate_rsi(data, 14)
    data['RSI_21'] = calculate_rsi(data, 21)
    data['MACD'], data['MACD_Signal'], data['MACD_Histogram'] = calculate_macd(data)
    return data

# --- MACD Kesişim Analizi ---
def detect_macd_crossover(data):
    if len(data) < 2:
        return "No Signal"

    prev_row = data.iloc[-2]
    last_row = data.iloc[-1]

    prev_macd = prev_row['MACD']
    prev_signal = prev_row['MACD_Signal']
    last_macd = last_row['MACD']
    last_signal = last_row['MACD_Signal']

    if prev_macd < prev_signal and last_macd > last_signal:
        return "Buy"
    elif prev_macd > prev_signal and last_macd < last_signal:
        return "Sell"
    else:
        return "No Signal"

# --- Adaylık Belirleme ---
def is_buy_candidate(data):
    last_row = data.iloc[-1]
    rsi_14 = last_row['RSI_14']
    macd_signal = detect_macd_crossover(data)

    if rsi_14 < 35 and macd_signal == "Buy":
        return True
    else:
        return False

# --- Telegram Mesajı Gönderme ---
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }
    requests.post(url, data=payload)

def format_and_send_signal(symbol, rsi_value, macd_signal, price, is_candidate):
    candidate_text = "Evet" if is_candidate else "Hayır"

    message = (
        f"Coin: {symbol}\n"
        f"RSI(14): {rsi_value:.2f}\n"
        f"MACD Sinyali: {macd_signal}\n"
        f"Fiyat: {price:.2f} USDT\n"
        f"Alım Adayı: {candidate_text}"
    )
    send_telegram_message(message)

# --- FastAPI Route'ları ---
@app.get("/")
def read_root():
    return {"message": "RSI + MACD Signal API is running!"}

@app.get("/signals/{symbol}")
def get_signal(symbol: str):
    try:
        df = fetch_binance_ohlcv(symbol.upper(), interval="5m")
        rsi_14 = df.iloc[-1]['RSI_14']
        price = df.iloc[-1]['close']
        macd_signal = detect_macd_crossover(df)
        candidate = is_buy_candidate(df)

        # Telegrama gönder
        format_and_send_signal(symbol.upper(), rsi_14, macd_signal, price, candidate)

        return {
            "symbol": symbol.upper(),
            "rsi_14": round(rsi_14, 2),
            "price": round(price, 2),
            "macd_signal": macd_signal,
            "buy_candidate": candidate
        }

    except Exception as e:
        return {"error": str(e)}

# --- Lokalde çalıştırmak için ---
if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
