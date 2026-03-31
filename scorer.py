import json
from datetime import datetime

with open('raw_data.json', 'r', encoding='utf-8') as f:
    raw = json.load(f)

stocks = raw['data']

INVALID_TICKERS = []

def flag_anomaly(s):
    flags = []
    if s['rsi'] >= 100 or s['vol_ratio'] == 0:
        flags.append('DATA_TIDAK_VALID')
    if s['days_to_cum'] is not None and s['days_to_cum'] < -365:
        flags.append('DIVIDEN_TIDAK_AKTIF')
    if s['roe'] < -10:
        flags.append('ROE_NEGATIF')
    if s['yield_bersih'] > 15:
        flags.append('YIELD_ABNORMAL')
    if s['der'] > 200 and s['sektor'] not in ['Financial Services']:
        flags.append('DER_SANGAT_TINGGI')
    return flags

def score_stock(s):
    skor  = {}
    total = 0

    # ── 1. Yield bersih ≥ 4% ─────────────────────────────────────────────
    skor['yield_bersih_4pct'] = 1 if s['yield_bersih'] >= 4 else 0

    # ── 2. Yield tidak abnormal > 8% tanpa alasan ────────────────────────
    # Jika yield > 8% DAN ada flag anomaly → minus
    # Jika yield > 8% tapi data valid → tetap lolos (bank BUMN memang tinggi)
    skor['yield_tidak_abnormal'] = 0 if s['yield_bersih'] > 15 else 1

    # ── 3. Div konsisten ≥ 3 tahun ────────────────────────────────────────
    skor['div_konsisten_3thn'] = 1 if s['div_years'] >= 3 else 0

    # ── 4. Div konsisten ≥ 5 tahun (bonus) ───────────────────────────────
    skor['div_konsisten_5thn'] = 1 if s['div_years'] >= 5 else 0

    # ── 5. Dividen aktif (days_to_cum tidak terlalu lama) ─────────────────
    dtc = s['days_to_cum']
    skor['dividen_aktif'] = 1 if (dtc is not None and dtc > -400) else 0

    # ── 6. PBV < 2.5x (atau < 3.5x untuk bank/BUMN) ──────────────────────
    pbv = s['pbv']
    is_bank = s['sektor'] == 'Financial Services'
    pbv_limit = 3.5 if is_bank else 2.5
    # PBV dari Yahoo Finance kadang error (nilai sangat besar) → skip jika > 1000
    skor['pbv_wajar'] = 1 if (0 < pbv < pbv_limit) else 0

    # ── 7. PER > 0 dan < 25x ──────────────────────────────────────────────
    per = s['per']
    skor['per_wajar'] = 1 if (0 < per < 25) else 0

    # ── 8. ROE > 10% ──────────────────────────────────────────────────────
    skor['roe_positif'] = 1 if s['roe'] >= 10 else 0

    # ── 9. DER tidak terlalu tinggi ───────────────────────────────────────
    der = s['der']
    if is_bank:
        skor['der_aman'] = 1  # bank memang leverage tinggi, skip check
    else:
        skor['der_aman'] = 1 if der < 100 else 0

    # ── 10. Harga di atas MA20 ────────────────────────────────────────────
    skor['above_ma20'] = 1 if s['above_ma20'] else 0

    # ── 11. Harga di atas MA50 ────────────────────────────────────────────
    skor['above_ma50'] = 1 if s['above_ma50'] else 0

    # ── 12. Golden cross MA20 > MA50 ──────────────────────────────────────
    skor['golden_cross'] = 1 if s['golden_cross'] else 0

    # ── 13. RSI antara 40–65 (zona entry ideal) ───────────────────────────
    rsi = s['rsi']
    skor['rsi_ideal'] = 1 if (40 <= rsi <= 65) else 0

    # ── 14. RSI tidak overbought (< 70) ──────────────────────────────────
    skor['rsi_tidak_overbought'] = 1 if rsi < 70 else 0

    # ── 15. MACD bullish ─────────────────────────────────────────────────
    skor['macd_bullish'] = 1 if s['macd_bullish'] else 0

    # ── 16. Volume ratio ≥ 1x (minimal normal) ────────────────────────────
    skor['volume_normal'] = 1 if s['vol_ratio'] >= 1.0 else 0

    # ── 17. Volume ratio ≥ 1.5x (bonus: momentum) ─────────────────────────
    skor['volume_momentum'] = 1 if s['vol_ratio'] >= 1.5 else 0

    # ── 18. Candle bullish ────────────────────────────────────────────────
    skor['candle_bullish'] = 1 if s['bullish_candle'] else 0

    # ── 19. Body candle ≥ 40% (bukan doji) ───────────────────────────────
    skor['candle_body_kuat'] = 1 if s['body_ratio'] >= 0.4 else 0

    # ── 20. Upcoming dividen dalam 1 tahun ke depan ───────────────────────
    # Ini estimasi: kalau pola historis tahunan, kemungkinan ada dividen berikutnya
    skor['upcoming_dividen'] = 1 if (s['div_years'] >= 3 and s['dps'] > 0) else 0

    # ── Hitung total ──────────────────────────────────────────────────────
    total = sum(skor.values())
    maks  = len(skor)

    # ── Klasifikasi ───────────────────────────────────────────────────────
    pct = total / maks
    if pct >= 0.75:
        klasifikasi = 'STRONG BUY'
    elif pct >= 0.60:
        klasifikasi = 'BUY'
    elif pct >= 0.45:
        klasifikasi = 'WATCH'
    else:
        klasifikasi = 'SKIP'

    return {
        'skor_detail': skor,
        'total_skor':  total,
        'skor_maks':   maks,
        'pct':         round(pct * 100, 1),
        'klasifikasi': klasifikasi,
    }

def main():
    print("=" * 60)
    print("  DiviWatch Scorer — Dividend Screening")
    print("=" * 60)

    results = []

    for s in stocks:
        flags  = flag_anomaly(s)

        if 'DATA_TIDAK_VALID' in flags:
            print(f"  SKIP {s['kode']:6} — data tidak valid {flags}")
            continue

        scoring = score_stock(s)

        result = {
            **s,
            'flags':       flags,
            'skor_detail': scoring['skor_detail'],
            'total_skor':  scoring['total_skor'],
            'skor_maks':   scoring['skor_maks'],
            'pct':         scoring['pct'],
            'klasifikasi': scoring['klasifikasi'],
        }
        results.append(result)

    # Sort by score descending
    results.sort(key=lambda x: x['total_skor'], reverse=True)

    # Print hasil
    print(f"\n  {'Kode':<6} {'Klasifikasi':<12} {'Skor':<8} {'Yield':<8} {'RSI':<6} {'Flags'}")
    print(f"  {'-'*65}")
    for r in results:
        flag_str = ', '.join(r['flags']) if r['flags'] else '-'
        print(f"  {r['kode']:<6} {r['klasifikasi']:<12} "
              f"{r['total_skor']}/{r['skor_maks']} ({r['pct']}%)  "
              f"{r['yield_bersih']}%    "
              f"{r['rsi']:<6} {flag_str}")

    # Simpan candidates.json
    strong_buy = [r for r in results if r['klasifikasi'] == 'STRONG BUY']
    buy        = [r for r in results if r['klasifikasi'] == 'BUY']
    watch      = [r for r in results if r['klasifikasi'] == 'WATCH']
    skip       = [r for r in results if r['klasifikasi'] == 'SKIP']

    output = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'summary': {
            'total':      len(results),
            'strong_buy': len(strong_buy),
            'buy':        len(buy),
            'watch':      len(watch),
            'skip':       len(skip),
        },
        'strong_buy': strong_buy,
        'buy':        buy,
        'watch':      watch,
        'skip':       skip,
    }

    with open('candidates.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n  {'='*60}")
    print(f"  STRONG BUY : {len(strong_buy)} saham")
    print(f"  BUY        : {len(buy)} saham")
    print(f"  WATCH      : {len(watch)} saham")
    print(f"  SKIP       : {len(skip)} saham")
    print(f"  Output     : candidates.json")
    print(f"  {'='*60}")

if __name__ == '__main__':
    main()