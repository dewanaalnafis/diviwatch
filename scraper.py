import yfinance as yf
import pandas as pd
import json
from datetime import datetime, date, timedelta
from ta.momentum import RSIIndicator
from ta.trend import MACD

UNIVERSE = [
    'BBCA.JK', 'BBRI.JK', 'BMRI.JK', 'BBNI.JK', 'BBTN.JK',
    'BNGA.JK', 'BTPS.JK', 'BJTM.JK', 'BFIN.JK',
    'ADRO.JK', 'PTBA.JK', 'ITMG.JK', 'MEDC.JK',
    'ELSA.JK', 'PGAS.JK', 'AKRA.JK',
    'UNVR.JK', 'SIDO.JK', 'ICBP.JK',
    'INDF.JK', 'HMSP.JK', 'KLBF.JK',
    'TLKM.JK', 'EXCL.JK', 'ISAT.JK',
    'ASII.JK', 'SMGR.JK', 'INTP.JK', 'CPIN.JK',
    'ANTM.JK', 'TINS.JK', 'INCO.JK',
    'SCMA.JK',
    'BSDE.JK', 'PWON.JK',
    'JSMR.JK', 'WIKA.JK',
]

def days_until(dt_str):
    if not dt_str:
        return None
    try:
        dt = datetime.strptime(dt_str, '%Y-%m-%d').date()
        return (dt - date.today()).days
    except:
        return None

def scrape_stock(ticker_code):
    print(f'  Scraping {ticker_code}...', end=' ')
    try:
        ticker = yf.Ticker(ticker_code)
        kode   = ticker_code.replace('.JK', '')

        hist = ticker.history(period='90d')
        if hist.empty or len(hist) < 20:
            print('❌ Data tidak cukup')
            return None

        close  = hist['Close']
        volume = hist['Volume']

        harga_sekarang = round(float(close.iloc[-1]), 0)
        harga_kemarin  = round(float(close.iloc[-2]), 0)
        change_pct     = round(((harga_sekarang - harga_kemarin) / harga_kemarin) * 100, 2)

        ma20 = round(float(close.rolling(20).mean().iloc[-1]), 0)
        ma50 = round(float(close.rolling(50).mean().iloc[-1]), 0) if len(close) >= 50 else None

        rsi = round(float(RSIIndicator(close=close, window=14).rsi().iloc[-1]), 1)

        macd_obj     = MACD(close=close)
        macd_line    = round(float(macd_obj.macd().iloc[-1]), 2)
        macd_signal  = round(float(macd_obj.macd_signal().iloc[-1]), 2)
        macd_bullish = macd_line > macd_signal

        avg_vol_20 = float(volume.rolling(20).mean().iloc[-1])
        vol_today  = float(volume.iloc[-1])
        vol_ratio  = round(vol_today / avg_vol_20, 2) if avg_vol_20 > 0 else 0

        above_ma20   = harga_sekarang > ma20
        above_ma50   = (harga_sekarang > ma50) if ma50 else None
        golden_cross = (ma20 > ma50) if ma50 else None

        open_last    = float(hist['Open'].iloc[-1])
        high_last    = float(hist['High'].iloc[-1])
        low_last     = float(hist['Low'].iloc[-1])
        close_last   = float(hist['Close'].iloc[-1])
        body         = abs(close_last - open_last)
        candle_range = high_last - low_last
        body_ratio   = round(body / candle_range, 2) if candle_range > 0 else 0
        bullish_candle = close_last > open_last

        info   = ticker.info or {}
        nama   = info.get('longName', kode)
        sektor = info.get('sector', 'Unknown')
        pbv    = round(info.get('priceToBook',    0) or 0, 2)
        per    = round(info.get('trailingPE',     0) or 0, 2)
        roe    = round((info.get('returnOnEquity',0) or 0) * 100, 2)
        der    = round(info.get('debtToEquity',   0) or 0, 2)
        net_income         = info.get('netIncomeToCommon', 0) or info.get('netIncome', 0) or 0
        shares_outstanding = info.get('sharesOutstanding', 0) or 0

        div_hist = ticker.dividends
        dps_list = []
        if not div_hist.empty:
            for dt, amt in div_hist.tail(6).items():
                dps_list.append({
                    'tanggal': str(dt.date()),
                    'dps':     round(float(amt), 0)
                })

        dps_terakhir = dps_list[-1]['dps'] if dps_list else 0

        ex_date  = None
        cum_date = None
        cal = ticker.calendar or {}
        if 'Ex-Dividend Date' in cal:
            ex_raw = cal['Ex-Dividend Date']
            if isinstance(ex_raw, (datetime, date)):
                ex_dt    = ex_raw if isinstance(ex_raw, date) else ex_raw.date()
                ex_date  = str(ex_dt)
                cum_date = str(ex_dt - timedelta(days=1))

        days_to_cum  = days_until(cum_date)
        yield_kotor  = round((dps_terakhir / harga_sekarang) * 100, 2) if harga_sekarang > 0 and dps_terakhir > 0 else 0
        yield_bersih = round(yield_kotor * 0.9, 2)
        div_years    = len(set([d['tanggal'][:4] for d in dps_list]))

        price_history = []
        for idx_dt, row in hist.tail(30).iterrows():
            price_history.append({
                'date':  str(idx_dt.date()),
                'open':  round(float(row['Open']), 0),
                'high':  round(float(row['High']), 0),
                'low':   round(float(row['Low']), 0),
                'close': round(float(row['Close']), 0),
                'vol':   int(row['Volume']),
            })

        ma20_series = close.rolling(20).mean().tail(30)
        ma50_series = close.rolling(50).mean().tail(30) if len(close) >= 50 else None

        ma20_history = [round(v, 0) if not pd.isna(v) else None for v in ma20_series]
        ma50_history = [round(v, 0) if not pd.isna(v) else None for v in ma50_series] if ma50_series is not None else []

        print(f'✅ Rp{harga_sekarang:,.0f} | RSI {rsi} | Yield bersih {yield_bersih}%')

        return {
            'kode':           kode,
            'nama':           nama,
            'sektor':         sektor,
            'harga':          harga_sekarang,
            'change_pct':     change_pct,
            'ma20':           ma20,
            'ma50':           ma50,
            'rsi':            rsi,
            'macd_line':      macd_line,
            'macd_signal':    macd_signal,
            'macd_bullish':   macd_bullish,
            'vol_ratio':      vol_ratio,
            'above_ma20':     above_ma20,
            'above_ma50':     above_ma50,
            'golden_cross':   golden_cross,
            'bullish_candle': bullish_candle,
            'body_ratio':     body_ratio,
            'pbv':            pbv,
            'per':            per,
            'roe':            roe,
            'der':            der,
            'dps':            dps_terakhir,
            'yield_kotor':    yield_kotor,
            'yield_bersih':   yield_bersih,
            'div_history':    dps_list,
            'div_years':      div_years,
            'div_konsisten':  div_years >= 3,
            'ex_date':        ex_date,
            'cum_date':       cum_date,
            'days_to_cum':    days_to_cum,
            'price_history':  price_history,
            'ma20_history':   ma20_history,
            'ma50_history':   ma50_history,
            'net_income':         net_income,
            'shares_outstanding': shares_outstanding,
            'last_updated':   datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }

    except Exception as e:
        print(f'❌ Error: {e}')
        return None

def main():
    print('=' * 55)
    print('  DiviWatch Scraper — 40 saham IDX')
    print('=' * 55)

    results, errors = [], []

    for ticker_code in UNIVERSE:
        data = scrape_stock(ticker_code)
        if data:
            results.append(data)
        else:
            errors.append(ticker_code)

    output = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total':        len(results),
        'errors':       errors,
        'data':         results,
    }

    with open('raw_data.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print()
    print('=' * 55)
    print(f'  Selesai : {len(results)} berhasil, {len(errors)} error')
    if errors:
        print(f'  Error   : {", ".join([e.replace(".JK","") for e in errors])}')
    print(f'  Output  : raw_data.json')
    print('=' * 55)

if __name__ == '__main__':
    main()