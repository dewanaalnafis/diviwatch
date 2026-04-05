import csv
import json
import os
import re
from datetime import datetime, timedelta

CSV_FILE        = 'dividen_manual.csv'
CANDIDATES_FILE = 'candidates.json'

def parse_pct(val):
    if not val or str(val).strip() in ('', 'None', 'null', '-'):
        return None
    s = str(val).replace('%','').replace(',','.').strip()
    try:
        return float(s)
    except:
        return None

def parse_num(val):
    if not val or str(val).strip() in ('', 'None', 'null', '-'):
        return None
    s = str(val).replace('Rp','').strip()
    s = re.sub(r',(\d{3})(?!\d)', r'\1', s)
    s = re.sub(r'\.(\d{3})(?!\d)', r'\1', s)
    s = s.replace(',', '.').strip()
    try:
        return float(s)
    except:
        return None

def parse_date(val):
    if not val or str(val).strip() in ('', 'None', 'null', '-'):
        return None
    s = str(val).strip()
    for fmt in ['%d/%m/%Y','%Y-%m-%d','%d-%m-%Y','%m/%d/%Y']:
        try:
            return datetime.strptime(s, fmt).strftime('%Y-%m-%d')
        except:
            pass
    return s

def load_csv():
    if not os.path.exists(CSV_FILE):
        print(f'  ❌ File {CSV_FILE} tidak ditemukan')
        return []

    # Baca raw dulu untuk deteksi header
    with open(CSV_FILE, 'r', encoding='utf-8-sig') as f:
        raw_lines = f.readlines()

    # Cari baris header (Kode,Tahun,Tipe,...)
    header_idx = None
    for i, line in enumerate(raw_lines):
        if line.strip().startswith('Kode') or line.strip().startswith('kode'):
            header_idx = i
            break

    # Kalau tidak ada header, buat header manual
    COLS = ['Kode','Tahun','Tipe','Dividen','Harga_CumDate','Div_Yield','DPR','Tanggal_ExDate','Yield_1Tahun']

    rows = []
    if header_idx is not None:
        # Ada header — skip sampai header
        data_lines = raw_lines[header_idx:]
        reader = csv.DictReader(data_lines)
        data_rows = list(reader)
    else:
        # Tidak ada header — pakai COLS manual
        data_rows = []
        for line in raw_lines:
            line = line.strip()
            if not line:
                continue
            parts = line.split(',')
            # Pad sampai 9 kolom
            while len(parts) < len(COLS):
                parts.append('')
            row = dict(zip(COLS, parts[:len(COLS)]))
            data_rows.append(row)

    for row in data_rows:
        kode = str(row.get('Kode', row.get('kode', ''))).strip().upper()
        if not kode or kode in ('KODE', 'None', ''):
            continue

        div    = parse_num(row.get('Dividen','') or row.get('Dividen (Rp)',''))
        harga  = parse_num(row.get('Harga_CumDate','') or row.get('Harga CumDate',''))
        dpr    = parse_pct(row.get('DPR','') or row.get('DPR (%)',''))
        exdate = parse_date(row.get('Tanggal_ExDate','') or row.get('Tanggal ExDate',''))
        y1th   = parse_pct(row.get('Yield_1Tahun','') or row.get('Yield 1 Tahun',''))
        yld_raw= parse_pct(row.get('Div_Yield','') or row.get('Div. Yield',''))

        if yld_raw is None and div and harga and harga > 0:
            yld_raw = round((div / harga) * 100, 2)

        cum_date = None
        if exdate:
            try:
                ex_dt    = datetime.strptime(exdate, '%Y-%m-%d')
                cum_date = (ex_dt - timedelta(days=1)).strftime('%Y-%m-%d')
            except:
                pass

        tipe = str(row.get('Tipe', row.get('tipe', ''))).strip().upper()
        if tipe not in ['TAHUNAN','INTERIM','FINAL']:
            tipe = 'TAHUNAN'

        tahun = str(row.get('Tahun', row.get('tahun', ''))).strip()
        # Skip baris yang tidak punya data penting
        if not div and not exdate and not tahun:
            continue

        rows.append({
            'kode':      kode,
            'tahun':     tahun,
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

    rows = load_csv()
    if not rows:
        return
    print(f'  CSV loaded: {len(rows)} baris dari {len(set(r["kode"] for r in rows))} saham')

    div_by_kode = group_by_kode(rows)
    print(f'  Saham: {", ".join(sorted(div_by_kode.keys()))}')

    if not os.path.exists(CANDIDATES_FILE):
        print(f'  ❌ {CANDIDATES_FILE} tidak ditemukan — jalankan scorer.py dulu')
        return

    with open(CANDIDATES_FILE, 'r', encoding='utf-8') as f:
        candidates = json.load(f)

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
        tipe_order = {'TAHUNAN': 0, 'INTERIM': 1, 'FINAL': 2}
        div_rows.sort(key=lambda x: (x['tahun'] or '', tipe_order.get(x['tipe'], 0)))

        stock['div_history_manual'] = div_rows

        valid_rows = [r for r in div_rows if r['dps']]
        if valid_rows:
            latest = valid_rows[-1]
            stock['ex_date_manual']  = latest['ex_date']
            stock['cum_date_manual'] = latest['cum_date']
            stock['dps_manual']      = latest['dps']
            stock['harga_cum']       = latest['harga_cum']
            stock['div_yield_cum']   = latest['div_yield']
            stock['dpr_manual']      = latest['dpr']

            if latest['dps'] and latest['harga_cum'] and latest['harga_cum'] > 0:
                stock['yield_bersih_cum'] = round((latest['dps'] / latest['harga_cum']) * 0.9, 2)

            valid_dpr = [r['dpr'] for r in div_rows if r['dpr'] and r['dpr'] > 0]
            if valid_dpr:
                dpr_avg            = sum(valid_dpr[-3:]) / len(valid_dpr[-3:])
                net_income         = stock.get('net_income', 0) or 0
                shares_outstanding = stock.get('shares_outstanding', 0) or 0
                harga              = stock.get('harga', 0) or 0

                if net_income > 0 and shares_outstanding > 0:
                    est_total_div    = net_income * (dpr_avg / 100)
                    est_dps          = round(est_total_div / shares_outstanding, 2)
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

    for kode in div_by_kode:
        if not any(s.get('kode') == kode for s in all_stocks):
            not_found.append(kode)

    candidates['generated_at']       = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    candidates['div_manual_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

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