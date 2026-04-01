import csv
import json
import os
from datetime import datetime

CSV_FILE        = 'dividen_manual.csv'
CANDIDATES_FILE = 'candidates.json'

def parse_pct(val):
    """Convert string persen ke float. '5,48%' → 5.48"""
    if not val or str(val).strip() == '':
        return None
    s = str(val).replace('%','').replace(',','.').strip()
    try:
        return float(s)
    except:
        return None

def parse_num(val):
    """Convert string angka ke float. Handle: 1,390 / 3,200 / 151.77"""
    if not val or str(val).strip() == '':
        return None
    s = str(val).replace('Rp','').strip()
    # Deteksi format: kalau ada koma diikuti 3 digit di akhir → pemisah ribuan
    import re
    # Hapus koma pemisah ribuan (1,390 → 1390)
    s = re.sub(r',(\d{3})(?!\d)', r'\1', s)
    # Hapus titik pemisah ribuan (1.390 → 1390) kalau bukan desimal
    s = re.sub(r'\.(\d{3})(?!\d)', r'\1', s)
    s = s.replace(',', '.').strip()
    try:
        return float(s)
    except:
        return None

def parse_date(val):
    """Parse tanggal dari berbagai format ke YYYY-MM-DD."""
    if not val or str(val).strip() == '':
        return None
    s = str(val).strip()
    for fmt in ['%d/%m/%Y','%Y-%m-%d','%d-%m-%Y','%m/%d/%Y']:
        try:
            return datetime.strptime(s, fmt).strftime('%Y-%m-%d')
        except:
            pass
    return s

def load_csv():
    """Baca dividen_manual.csv dan return list of dict."""
    if not os.path.exists(CSV_FILE):
        print(f'  ❌ File {CSV_FILE} tidak ditemukan')
        print(f'     Download template → isi → save as CSV → taruh di folder ini')
        return []

    rows = []
    with open(CSV_FILE, 'r', encoding='utf-8-sig') as f:
        # Skip 3 baris header template
        for _ in range(3):
            next(f)
            
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=4): # Start disesuaikan karena sudah skip 3 baris
            kode = str(row.get('Kode','')).strip().upper()
            if not kode:
                continue  # skip baris kosong

            div   = parse_num(row.get('Dividen','') or row.get('Dividen (Rp)',''))
            harga = parse_num(row.get('Harga_CumDate','') or row.get('Harga CumDate',''))
            dpr   = parse_pct(row.get('DPR','') or row.get('DPR (%)',''))
            exdate= parse_date(row.get('Tanggal_ExDate','') or row.get('Tanggal ExDate',''))
            y1th  = parse_pct(row.get('Yield_1Tahun','') or row.get('Yield 1 Tahun',''))

            # Hitung yield otomatis kalau ada dividen dan harga
            yld_raw = parse_pct(row.get('Div_Yield','') or row.get('Div. Yield',''))
            if yld_raw is None and div and harga and harga > 0:
                yld_raw = round((div / harga) * 100, 2)

            # Cum date = ExDate - 1 hari
            cum_date = None
            if exdate:
                try:
                    ex_dt    = datetime.strptime(exdate, '%Y-%m-%d')
                    from datetime import timedelta
                    cum_date = (ex_dt - timedelta(days=1)).strftime('%Y-%m-%d')
                except:
                    pass

            tipe = str(row.get('Tipe','')).strip().upper()
            if tipe not in ['TAHUNAN','INTERIM','FINAL']:
                tipe = 'TAHUNAN'

            rows.append({
                'kode':      kode,
                'tahun':     str(row.get('Tahun','')).strip(),
                'tipe':      tipe,
                'dps':       div,
                'harga_cum': harga,
                'div_yield': yld_raw,
                'dpr':       dpr,
                'ex_date':   exdate,
                'cum_date':  cum_date,
                'yield_1th': y1th,
            })

    return rows

def group_by_kode(rows):
    """Group rows by kode saham."""
    result = {}
    for r in rows:
        k = r['kode']
        if k not in result:
            result[k] = []
        result[k].append(r)
    return result

def main():
    print('=' * 55)
    print('  DiviWatch Merger — Dividen Manual → candidates.json')
    print('=' * 55)

    # 1. Load CSV
    rows = load_csv()
    if not rows:
        return
    print(f'  CSV loaded: {len(rows)} baris dari {len(set(r["kode"] for r in rows))} saham')

    # 2. Group by kode
    div_by_kode = group_by_kode(rows)
    print(f'  Saham: {", ".join(sorted(div_by_kode.keys()))}')

    # 3. Load candidates.json
    if not os.path.exists(CANDIDATES_FILE):
        print(f'  ❌ {CANDIDATES_FILE} tidak ditemukan — jalankan scorer.py dulu')
        return

    with open(CANDIDATES_FILE, 'r', encoding='utf-8') as f:
        candidates = json.load(f)

    # 4. Merge ke setiap saham
    updated = 0
    not_found = []

    all_stocks = (
        candidates.get('strong_buy', []) +
        candidates.get('buy',        []) +
        candidates.get('watch',      []) +
        candidates.get('skip',       [])
    )

    for stock in all_stocks:
        kode = stock.get('kode','')
        if kode not in div_by_kode:
            continue

        div_rows = div_by_kode[kode]

        # Sort by tahun + tipe
        tipe_order = {'TAHUNAN': 0, 'INTERIM': 1, 'FINAL': 2}
        div_rows.sort(key=lambda x: (x['tahun'], tipe_order.get(x['tipe'], 0)))

        # Simpan history lengkap
        stock['div_history_manual'] = div_rows

        # Ambil data terbaru (entry terakhir yang punya DPS)
        valid_rows = [r for r in div_rows if r['dps']]
        if valid_rows:
            latest = valid_rows[-1]
            stock['ex_date_manual']  = latest['ex_date']
            stock['cum_date_manual'] = latest['cum_date']
            stock['dps_manual']      = latest['dps']
            stock['harga_cum']       = latest['harga_cum']
            stock['div_yield_cum']   = latest['div_yield']  # yield saat cum date
            stock['dpr_manual']      = latest['dpr']

            # Yield bersih dari harga cum date
            if latest['dps'] and latest['harga_cum'] and latest['harga_cum'] > 0:
                stock['yield_bersih_cum'] = round((latest['dps'] / latest['harga_cum']) * 0.9, 2)
            # ── Estimasi dividen berikutnya ───────────────────────────────
            valid_dpr = [r['dpr'] for r in div_rows if r['dpr'] and r['dpr'] > 0]
            if valid_dpr:
             # Rata-rata DPR 3 tahun terakhir
                dpr_avg = sum(valid_dpr[-3:]) / len(valid_dpr[-3:])
                net_income         = stock.get('net_income', 0) or 0
                shares_outstanding = stock.get('shares_outstanding', 0) or 0
                harga              = stock.get('harga', 0) or 0

                if net_income > 0 and shares_outstanding > 0:
                    est_total_div = net_income * (dpr_avg / 100)
                    est_dps       = round(est_total_div / shares_outstanding, 2)
                    est_yield_kotor  = round((est_dps / harga) * 100, 2) if harga > 0 else 0
                    est_yield_bersih = round(est_yield_kotor * 0.9, 2)

                    stock['est_dpr']          = round(dpr_avg, 2)
                    stock['est_dps']          = est_dps
                    stock['est_yield_kotor']  = est_yield_kotor
                    stock['est_yield_bersih'] = est_yield_bersih
                    stock['est_net_income']   = net_income
                    stock['est_shares']       = shares_outstanding

        updated += 1
        print(f'  ✅ {kode}: {len(div_rows)} periode dividen dimerge')

    # Saham di CSV tapi tidak ada di candidates
    for kode in div_by_kode:
        if not any(s.get('kode') == kode for s in all_stocks):
            not_found.append(kode)

    # 5. Update timestamp
    candidates['generated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    candidates['div_manual_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 6. Save
    with open(CANDIDATES_FILE, 'w', encoding='utf-8') as f:
        json.dump(candidates, f, ensure_ascii=False, indent=2)

    print()
    print('=' * 55)
    print(f'  Berhasil dimerge : {updated} saham')
    if not_found:
        print(f'  Tidak ada di screening: {", ".join(not_found)}')
    print(f'  Output : {CANDIDATES_FILE}')
    print('=' * 55)
    print()
    print('  Langkah berikutnya:')
    print('  git add -f candidates.json')
    print('  git commit -m "update: data dividen manual"')
    print('  git push')

if __name__ == '__main__':
    main()