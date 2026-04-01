from gnews import GNews
import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import json
from datetime import datetime, timedelta, timezone
import time

UNIVERSE = [
    'BBCA','BBRI','BMRI','BBNI','BBTN','BNGA','BTPS','BJTM','BFIN',
    'ADRO','PTBA','ITMG','MEDC','ELSA','PGAS','AKRA',
    'UNVR','SIDO','ICBP','INDF','HMSP','KLBF',
    'TLKM','EXCL','ISAT',
    'ASII','SMGR','INTP','CPIN',
    'ANTM','TINS','INCO',
    'SCMA','BSDE','PWON','JSMR','WIKA',
]

SEKTOR_MAP = {
    'ADRO':'batubara','PTBA':'batubara','ITMG':'batubara',
    'PGAS':'energi','ELSA':'energi','MEDC':'energi',
    'UNVR':'consumer','ICBP':'consumer','INDF':'consumer',
    'HMSP':'consumer','KLBF':'consumer','SIDO':'consumer',
    'BBCA':'bank','BBRI':'bank','BMRI':'bank',
    'BBNI':'bank','BBTN':'bank','BNGA':'bank',
    'BTPS':'bank','BJTM':'bank','BFIN':'finance',
    'ANTM':'tambang','TINS':'tambang','INCO':'tambang',
    'TLKM':'telko','EXCL':'telko','ISAT':'telko',
    'ASII':'otomotif','SMGR':'semen','INTP':'semen',
    'CPIN':'poultry','SCMA':'media',
    'BSDE':'properti','PWON':'properti',
    'JSMR':'infrastruktur','WIKA':'konstruksi',
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept-Language': 'id-ID,id;q=0.9',
}

CUTOFF_DAYS = 7  # hanya berita 7 hari terakhir

# ── Kategori korporasi ────────────────────────────────────────────────────
KATEGORI_KORPORASI = [
    {'id':1,'nama':'Dividen','keywords':['dividen','pembagian dividen','yield','dividend'],'sentimen':'bullish','bobot':+4},
    {'id':2,'nama':'Rights Issue','keywords':['rights issue','hmetd','penawaran umum terbatas','PUT'],'sentimen':'neutral','bobot':+1,'warning':'Bisa dilutif — analisis lebih lanjut'},
    {'id':3,'nama':'Laba Positif','keywords':['laba bersih naik','profit meningkat','eps tumbuh','laba tumbuh','kinerja positif','laba meningkat','pendapatan naik','revenue naik'],'sentimen':'bullish','bobot':+4},
    {'id':4,'nama':'Buyback','keywords':['buyback','pembelian kembali saham','buy back'],'sentimen':'bullish','bobot':+5},
    {'id':5,'nama':'Kontrak Baru','keywords':['kontrak baru','proyek baru','dapat proyek','menang tender','penandatanganan kontrak'],'sentimen':'bullish','bobot':+3},
    {'id':6,'nama':'Akuisisi','keywords':['akuisisi','merger','konsolidasi','ambil alih'],'sentimen':'bullish','bobot':+3,'warning':'Tergantung valuasi — cek detail'},
    {'id':7,'nama':'Rugi','keywords':['rugi','kerugian','net loss','merah','laba turun','pendapatan turun'],'sentimen':'bearish','bobot':-4},
    {'id':8,'nama':'Gagal Bayar','keywords':['gagal bayar','default','restrukturisasi utang','obligasi jatuh tempo','kredit macet'],'sentimen':'bearish','bobot':-5,'warning':'EXIT segera'},
    {'id':9,'nama':'Delisting/Suspensi','keywords':['delisting','suspend','suspensi','penghentian perdagangan','suspensi bei'],'sentimen':'bearish','bobot':-5,'warning':'EXIT segera'},
    {'id':10,'nama':'Direksi Mundur','keywords':['mundur','resign','pengunduran diri','direktur utama mundur','ceo mundur'],'sentimen':'bearish','bobot':-3},
]

KATEGORI_MAKRO = [
    {'id':11,'nama':'BI Rate Turun','keywords':['bi rate turun','suku bunga turun','pemangkasan suku bunga','bi pangkas','penurunan bunga'],'sentimen':'bullish','bobot':+3},
    {'id':12,'nama':'Inflasi Terkendali','keywords':['inflasi terkendali','deflasi','inflasi rendah','inflasi sesuai target'],'sentimen':'bullish','bobot':+2},
    {'id':13,'nama':'Investasi Asing Naik','keywords':['fdi naik','investasi asing masuk','bkpm','rekor investasi','penanaman modal asing'],'sentimen':'bullish','bobot':+2},
    {'id':14,'nama':'BI Rate Naik','keywords':['bi rate naik','kenaikan suku bunga','bi naikkan','suku bunga naik'],'sentimen':'bearish','bobot':-3},
    {'id':15,'nama':'Rupiah Melemah','keywords':['rupiah melemah','kurs dollar naik tajam','rupiah tembus','pelemahan rupiah','dolar menguat'],'sentimen':'bearish','bobot':-3},
    {'id':16,'nama':'Regulasi Baru','keywords':['kebijakan baru','peraturan ojk','aturan baru','regulasi baru'],'sentimen':'neutral','bobot':0,'warning':'Analisis manual diperlukan'},
]

KATEGORI_SEKTORAL = [
    {'id':17,'nama':'Komoditas Naik','keywords':['harga batu bara naik','cpo rally','harga nikel naik','komoditas naik','harga minyak naik','coal rally'],'sentimen':'bullish','bobot':+3,'sektor':['batubara','tambang','energi']},
    {'id':18,'nama':'PHK Massal','keywords':['phk massal','layoff','efisiensi karyawan','pengurangan karyawan'],'sentimen':'bearish','bobot':-2},
]

def is_recent(date_str, days=CUTOFF_DAYS):
    """Cek apakah artikel masih dalam batas hari"""
    if not date_str:
        return True  # kalau tidak ada tanggal, tetap masuk
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        # Format gnews: 'Thu, 28 Mar 2026 10:00:00 GMT'
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(date_str)
        return dt >= cutoff
    except:
        return True  # kalau parse gagal, tetap masuk

def match_keywords(text, keywords):
    text = text.lower()
    return any(kw.lower() in text for kw in keywords)

def analyze_article(title, desc, kode):
    text   = (title + ' ' + (desc or '')).lower()
    sektor = SEKTOR_MAP.get(kode, '')
    matches = []
    for kat in KATEGORI_KORPORASI:
        if match_keywords(text, kat['keywords']):
            matches.append({'id':kat['id'],'nama':kat['nama'],'sentimen':kat['sentimen'],'bobot':kat['bobot'],'warning':kat.get('warning',''),'level':'korporasi'})
    for kat in KATEGORI_SEKTORAL:
        if match_keywords(text, kat['keywords']):
            sektor_rel = kat.get('sektor',[])
            if not sektor_rel or sektor in sektor_rel:
                matches.append({'id':kat['id'],'nama':kat['nama'],'sentimen':kat['sentimen'],'bobot':kat['bobot'],'warning':kat.get('warning',''),'level':'sektoral'})
    return matches

# ── SOURCE 1: Google News ─────────────────────────────────────────────────
def fetch_gnews(kode, max_results=5):
    try:
        gn = GNews(language='id', country='ID', max_results=max_results, period='7d')
        articles = gn.get_news(f'saham {kode} BEI')
        result = []
        for a in articles:
            pub = a.get('published date','')
            if not is_recent(pub):
                continue
            result.append({
                'title':     a.get('title',''),
                'published': pub,
                'source':    a.get('publisher',{}).get('title',''),
                'url':       a.get('url',''),
                'origin':    'Google News',
            })
        return result
    except Exception as e:
        return []

# ── SOURCE 2: Kontan RSS ──────────────────────────────────────────────────
_kontan_cache = None
def fetch_kontan_rss():
    global _kontan_cache
    if _kontan_cache is not None:
        return _kontan_cache
    try:
        urls = [
            'https://investasi.kontan.co.id/rss',
            'https://keuangan.kontan.co.id/rss',
        ]
        items = []
        for url in urls:
            r = requests.get(url, headers=HEADERS, timeout=8)
            root = ET.fromstring(r.content)
            for item in root.iter('item'):
                pub = item.findtext('pubDate','')
                if not is_recent(pub):
                    continue
                items.append({
                    'title':     item.findtext('title','').strip(),
                    'published': pub,
                    'source':    'Kontan',
                    'url':       item.findtext('link',''),
                    'desc':      item.findtext('description',''),
                    'origin':    'Kontan RSS',
                })
        _kontan_cache = items
        return items
    except Exception as e:
        _kontan_cache = []
        return []

# ── SOURCE 3: Bisnis.com RSS ──────────────────────────────────────────────
_bisnis_cache = None
def fetch_bisnis_rss():
    global _bisnis_cache
    if _bisnis_cache is not None:
        return _bisnis_cache
    try:
        urls = [
            'https://rss.bisnis.com/feed/rss2/ekonomi-bisnis',
            'https://rss.bisnis.com/feed/rss2/pasar-modal',
        ]
        items = []
        for url in urls:
            r = requests.get(url, headers=HEADERS, timeout=8)
            root = ET.fromstring(r.content)
            for item in root.iter('item'):
                pub = item.findtext('pubDate','')
                if not is_recent(pub):
                    continue
                items.append({
                    'title':     item.findtext('title','').strip(),
                    'published': pub,
                    'source':    'Bisnis.com',
                    'url':       item.findtext('link',''),
                    'desc':      item.findtext('description',''),
                    'origin':    'Bisnis RSS',
                })
        _bisnis_cache = items
        return items
    except Exception as e:
        _bisnis_cache = []
        return []

# ── SOURCE 4: IDX Keterbukaan Informasi ───────────────────────────────────
_idx_cache = None
def fetch_idx_disclosure():
    global _idx_cache
    if _idx_cache is not None:
        return _idx_cache
    try:
        url = 'https://www.idx.co.id/id/perusahaan-tercatat/keterbukaan-informasi/'
        r = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(r.content, 'html.parser')

        items = []
        # IDX render via JS, coba ambil dari API internal
        api_url = 'https://www.idx.co.id/primary/NewsAnnouncement/GetLatestNewsAndAnnouncement?indexFrom=0&pageSize=50&language=id'
        r2 = requests.get(api_url, headers=HEADERS, timeout=10)
        data = r2.json()
        for item in data.get('Results', []):
            pub = item.get('NewsDate','')
            try:
                dt = datetime.strptime(pub[:10], '%Y-%m-%d')
                if dt < datetime.now() - timedelta(days=CUTOFF_DAYS):
                    continue
            except:
                pass
            items.append({
                'title':     item.get('Title','').strip(),
                'published': pub,
                'source':    'IDX',
                'url':       'https://www.idx.co.id' + item.get('Url',''),
                'desc':      item.get('Summary',''),
                'kode_ref':  item.get('StockCode',''),
                'origin':    'IDX Keterbukaan',
            })
        _idx_cache = items
        return items
    except Exception as e:
        # Fallback: scrape HTML biasa
        try:
            r = requests.get('https://www.idx.co.id/id/berita/', headers=HEADERS, timeout=10)
            soup = BeautifulSoup(r.content, 'html.parser')
            items = []
            for article in soup.select('article, .news-item, .card')[:20]:
                title = article.get_text(strip=True)[:200]
                if title:
                    items.append({'title':title,'published':'','source':'IDX','url':'','desc':'','origin':'IDX Berita'})
            _idx_cache = items
            return items
        except:
            _idx_cache = []
            return []

def filter_by_kode(articles, kode):
    """Filter artikel dari RSS/IDX yang relevan dengan kode saham"""
    relevant = []
    for a in articles:
        text = (a.get('title','') + ' ' + a.get('desc','')).lower()
        # Cek nama saham atau kode
        if kode.lower() in text:
            relevant.append({
                'title':     a.get('title',''),
                'published': a.get('published',''),
                'source':    a.get('source',''),
                'url':       a.get('url',''),
                'origin':    a.get('origin',''),
            })
    return relevant

# ── Makro scraper ─────────────────────────────────────────────────────────
def scrape_makro(kontan_articles, bisnis_articles):
    print('  Scraping berita makro...', end=' ')
    try:
        # Gabungkan semua sumber untuk analisis makro
        all_articles = []

        # gnews makro
        gn = GNews(language='id', country='ID', max_results=8, period='7d')
        for q in ['Bank Indonesia suku bunga','inflasi Indonesia','rupiah dollar','investasi asing Indonesia']:
            try:
                arts = gn.get_news(q)
                all_articles.extend([{'title':a.get('title',''),'desc':a.get('description','')} for a in arts if is_recent(a.get('published date',''))])
            except:
                pass
            time.sleep(0.3)

        # RSS makro
        for a in kontan_articles + bisnis_articles:
            all_articles.append({'title':a.get('title',''),'desc':a.get('desc','')})

        makro_matches = []
        for a in all_articles:
            text = (a.get('title','') + ' ' + a.get('desc','')).lower()
            for kat in KATEGORI_MAKRO:
                if match_keywords(text, kat['keywords']):
                    makro_matches.append({'id':kat['id'],'nama':kat['nama'],'sentimen':kat['sentimen'],'bobot':kat['bobot'],'warning':kat.get('warning',''),'title':a.get('title','')})

        # Deduplicate per kategori
        seen = {}
        for m in makro_matches:
            if m['id'] not in seen:
                seen[m['id']] = m

        result     = list(seen.values())
        skor_makro = max(-5, min(5, sum(m['bobot'] for m in result)))
        print(f'✅ {len(result)} kategori | skor {skor_makro}')
        return result, skor_makro
    except Exception as e:
        print(f'❌ {e}')
        return [], 0

# ── Per saham ─────────────────────────────────────────────────────────────
def scrape_news_stock(kode, makro_matches, skor_makro, kontan_articles, bisnis_articles, idx_articles):
    print(f'  News {kode}...', end=' ')
    try:
        news_items = []

        # Source 1: Google News (max 5, 7 hari)
        gn_articles = fetch_gnews(kode, max_results=5)
        news_items.extend(gn_articles)
        time.sleep(0.2)

        # Source 2: Kontan RSS (filter by kode)
        kontan_rel = filter_by_kode(kontan_articles, kode)
        news_items.extend(kontan_rel[:3])

        # Source 3: Bisnis RSS (filter by kode)
        bisnis_rel = filter_by_kode(bisnis_articles, kode)
        news_items.extend(bisnis_rel[:3])

        # Source 4: IDX Keterbukaan (filter by kode langsung)
        idx_rel = [a for a in idx_articles if kode.lower() in (a.get('title','') + a.get('kode_ref','')).lower()]
        news_items.extend(idx_rel[:3])

        # Deduplicate by title
        seen_titles = set()
        unique_items = []
        for item in news_items:
            t = item.get('title','')[:60]
            if t and t not in seen_titles:
                seen_titles.add(t)
                unique_items.append(item)
        news_items = unique_items[:8]  # max 8 artikel per saham

        # Analyze
        all_kat_match = []
        enriched_items = []
        for item in news_items:
            matches = analyze_article(item.get('title',''), item.get('desc','') or item.get('source',''), kode)
            enriched_items.append({**item, 'matches': matches})
            all_kat_match.extend(matches)

        # Skor
        skor_korporasi = max(-5, min(5, sum(m['bobot'] for m in all_kat_match)))
        skor_total     = max(-8, min(8, skor_korporasi + skor_makro))
        skor_normalized = round((skor_total + 8) / 16 * 10, 1)

        has_exit    = any(m['bobot'] <= -5 for m in all_kat_match)
        if has_exit:            overall = 'major_negative'
        elif skor_total >= 4:   overall = 'strong_positive'
        elif skor_total >= 1:   overall = 'positive'
        elif skor_total <= -4:  overall = 'strong_negative'
        elif skor_total <= -1:  overall = 'negative'
        else:                   overall = 'neutral'

        warnings = list(set([m['warning'] for m in all_kat_match if m.get('warning')]))

        # Sumber yang berhasil
        sources_used = list(set([item.get('origin','') for item in news_items if item.get('origin')]))

        print(f'✅ {len(news_items)} berita [{", ".join(sources_used) or "—"}] | {overall} | {skor_normalized}/10')

        return {
            'kode':             kode,
            'overall':          overall,
            'skor_korporasi':   skor_korporasi,
            'skor_makro':       skor_makro,
            'skor_total':       skor_total,
            'skor_normalized':  skor_normalized,
            'warnings':         warnings,
            'kategori_match':   all_kat_match,
            'makro_match':      makro_matches,
            'sources_used':     sources_used,
            'total_berita':     len(news_items),
            'items':            enriched_items,
            'last_updated':     datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }

    except Exception as e:
        print(f'❌ {e}')
        return {
            'kode':kode,'overall':'no_data','skor_korporasi':0,
            'skor_makro':skor_makro,'skor_total':skor_makro,
            'skor_normalized':5.0,'warnings':[],'kategori_match':[],
            'makro_match':makro_matches,'sources_used':[],'total_berita':0,
            'items':[],'last_updated':datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }

def main():
    print('=' * 60)
    print(f'  DiviWatch News Scraper — 4 Sumber, {CUTOFF_DAYS} hari terakhir')
    print('=' * 60)

    # Pre-load RSS & IDX (sekali untuk semua saham)
    print('  [1/4] Loading Kontan RSS...', end=' ')
    kontan = fetch_kontan_rss()
    print(f'✅ {len(kontan)} artikel' if kontan else '⚠️  gagal/kosong')

    print('  [2/4] Loading Bisnis RSS... ', end=' ')
    bisnis = fetch_bisnis_rss()
    print(f'✅ {len(bisnis)} artikel' if bisnis else '⚠️  gagal/kosong')

    print('  [3/4] Loading IDX Keterbukaan...', end=' ')
    idx = fetch_idx_disclosure()
    print(f'✅ {len(idx)} artikel' if idx else '⚠️  gagal/kosong')

    print('  [4/4] Analisis makro...', end=' ')
    makro_matches, skor_makro = scrape_makro(kontan, bisnis)

    print()
    print('  Scraping per saham:')
    results = {}
    for kode in UNIVERSE:
        data = scrape_news_stock(kode, makro_matches, skor_makro, kontan, bisnis, idx)
        results[kode] = data

    output = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'cutoff_days':  CUTOFF_DAYS,
        'total':        len(results),
        'skor_makro':   skor_makro,
        'makro_match':  makro_matches,
        'data':         results,
    }

    with open('news_data.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print()
    print('=' * 60)
    sp  = sum(1 for v in results.values() if v['overall']=='strong_positive')
    p   = sum(1 for v in results.values() if v['overall']=='positive')
    n   = sum(1 for v in results.values() if v['overall']=='neutral')
    ng  = sum(1 for v in results.values() if v['overall']=='negative')
    sn  = sum(1 for v in results.values() if v['overall']=='strong_negative')
    mn  = sum(1 for v in results.values() if v['overall']=='major_negative')
    nd  = sum(1 for v in results.values() if v['overall']=='no_data')
    print(f'  Strong Positive  : {sp}')
    print(f'  Positive         : {p}')
    print(f'  Neutral          : {n}')
    print(f'  Negative         : {ng}')
    print(f'  Strong Negative  : {sn}')
    print(f'  Major Negative   : {mn} ⚠️')
    print(f'  No Data          : {nd}')
    print(f'  Output           : news_data.json')
    print('=' * 60)

if __name__ == '__main__':
    main()