import os
import json
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler

API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
PORT = int(os.environ.get('PORT', 8000))
WEBHOOK = 'https://script.google.com/macros/s/AKfycbzBifHtQj2ioS3S0714ANeiOQMiynwAN_0aAtKBV4m4E_L5JrRyFgDb_rcl9fgTyn0/exec'

def fetch_sheet_data():
    req = urllib.request.Request(WEBHOOK, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())

def parse_date(val):
    if not val: return None
    s = str(val).strip()
    if s in ('-', '', 'None'): return None
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d.%m.%Y'):
        try:
            return datetime.strptime(s[:10], fmt[:10])
        except:
            continue
    return None

def fmt_date(d):
    return d.strftime('%-d.%-m.%Y') if d else '-'

def fmt_vko(d):
    return f"{d.strftime('%-d.%-m.%Y')} (vko {d.isocalendar()[1]})" if d else '-'

def next_after(d, weekday):
    days = (weekday - d.weekday()) % 7
    if days == 0: days = 7
    return d + timedelta(days=days)

def next_brew_after(d):
    return min(next_after(d, 2), next_after(d, 3))

def next_tuesday_after(d):
    return next_after(d, 1)

def build_schedule(kalle_rows):
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    # Kerää kaikki tankkivaraukset
    # (tankki, era, nimi, astiointi, vapautuu_viimeistään)
    varaukset = []
    for r in kalle_rows[1:]:
        if not r or not r[0]: continue
        try: era = int(float(str(r[0])))
        except: continue
        if era < 248: continue

        nimi = str(r[2] if len(r) > 2 else '-').strip() or '-'
        ast_d = parse_date(r[10] if len(r) > 10 else None)
        siirto_d = parse_date(r[7] if len(r) > 7 else None)
        try: prim = int(float(str(r[6]))) if r[6] and str(r[6]) not in ('-','None') else None
        except: prim = None
        try: sek = int(float(str(r[8]))) if r[8] and str(r[8]) not in ('-','None') else None
        except: sek = None

        if not ast_d: continue

        if prim:
            vapautuu = siirto_d if siirto_d else ast_d
            varaukset.append((prim, era, nimi, ast_d, vapautuu))
        if sek and siirto_d:
            varaukset.append((sek, era, nimi, ast_d, ast_d))

    # Rakenna aikajana per tankki, järjestä vapautumispäivän mukaan
    tankki_aikajana = {}
    for tankki, era, nimi, ast_d, vapautuu in varaukset:
        tankki_aikajana.setdefault(tankki, []).append((vapautuu, ast_d, era, nimi))
    for t in tankki_aikajana:
        tankki_aikajana[t].sort()

    # Nykyinen erä per tankki = ensimmäinen jonka vapautuminen > tänään (ei sama päivä)
    tankki_nykyinen = {}
    for tankki, lista in tankki_aikajana.items():
        for vapautuu, ast_d, era, nimi in lista:
            if vapautuu > today:  # Muutettu >= → > jotta tänään siirtyvät vapautuvat heti
                tankki_nykyinen[tankki] = (ast_d, era, nimi)
                break

    # Tankkirivit
    tankki_lines = []
    for t in range(1, 11):
        if t in tankki_nykyinen:
            ast_d, era, nimi = tankki_nykyinen[t]
            seuraava = next_brew_after(ast_d)
            tankki_lines.append(
                f"Tankki {t}: Erä {era} ({nimi}) | Astiointi {fmt_vko(ast_d)} | Seuraava keitto {fmt_date(seuraava)}"
            )
        else:
            tankki_lines.append(f"Tankki {t}: Vapaa heti")

    # Seuraavat 20 keittopäivää
    brew_lines = []
    d = today
    count = 0
    while count < 20:
        if d.weekday() in (2, 3):
            vapaat = [t for t in range(1, 11)
                      if t not in tankki_nykyinen or tankki_nykyinen[t][0] <= d]
            p = 'ke' if d.weekday() == 2 else 'to'
            brew_lines.append(
                f"{p} {fmt_date(d)} (vko {d.isocalendar()[1]}) — {len(vapaat)} tankkia vapaana: {', '.join(map(str, vapaat)) if vapaat else 'ei vapaita'}"
            )
            count += 1
        d += timedelta(days=1)

    # Arviotaulukko keitto → astiointi
    arvio_lines = []
    d = today
    added = 0
    while added < 8:
        if d.weekday() in (2, 3):
            ast = next_tuesday_after(d + timedelta(days=34))
            p = 'ke' if d.weekday() == 2 else 'to'
            arvio_lines.append(f"Keitto {p} {fmt_date(d)} → arvioitu astiointi {fmt_date(ast)}")
            added += 1
        d += timedelta(days=1)

    return tankki_lines, brew_lines, arvio_lines

def build_system_prompt(data):
    kalle = data.get('kalle', [])
    teemu = data.get('teemu', [])
    etusivu = data.get('etusivu', [])
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    teemu_map = {}
    for r in teemu[1:]:
        if not r or not r[0]: continue
        try: era = str(int(float(str(r[0]))))
        except: continue
        teemu_map[era] = {
            'nimi': r[2] if len(r) > 2 else None,
            'tyyli': r[3] if len(r) > 3 else '-',
            'sitaatti': r[4] if len(r) > 4 else '-',
            'kollabo': r[5] if len(r) > 5 else '-',
            'olut_idea': r[6] if len(r) > 6 else '-',
            'etiketti_idea': r[7] if len(r) > 7 else '-',
            'tolkit': r[8] if len(r) > 8 else '-',
            'keg20': r[9] if len(r) > 9 else '0',
            'keg30': r[10] if len(r) > 10 else '0',
        }

    etusivu_map = {}
    for r in etusivu[1:]:
        if not r or not r[0]: continue
        try: era = str(int(float(str(r[0]))))
        except: continue
        etusivu_map[era] = {
            'parasta': r[7] if len(r) > 7 else '-',
            'etiketti_maara': r[14] if len(r) > 14 else '-',
            'etiketti_tilanne': r[15] if len(r) > 15 else '-',
            'kalle_pct': r[21] if len(r) > 21 else '-',
            'ean_tolk': r[11] if len(r) > 11 else '-',
            'ean_keg20': r[12] if len(r) > 12 else '-',
            'ean_keg30': r[13] if len(r) > 13 else '-',
        }

    erat_lines = []
    for r in kalle[1:]:
        if not r or not r[0]: continue
        try: era = str(int(float(str(r[0]))))
        except: continue
        if int(era) < 248: continue

        t = teemu_map.get(era, {})
        e = etusivu_map.get(era, {})

        nimi = (str(t.get('nimi') or '')).strip() or str(r[2] if len(r) > 2 else '').strip() or '-'
        tyyli = t.get('tyyli') or '-'
        kollabo = t.get('kollabo') or '-'
        sitaatti = t.get('sitaatti') or '-'
        olut_idea = t.get('olut_idea') or '-'
        etiketti_idea = t.get('etiketti_idea') or '-'
        keg20 = str(t.get('keg20') or '0').strip()
        keg30 = str(t.get('keg30') or '0').strip()
        parasta = str(e.get('parasta') or '-').strip()
        etiketti_tilanne = str(e.get('etiketti_tilanne') or '-').strip()
        etiketti_maara = str(e.get('etiketti_maara') or '-').strip()
        kalle_pct = str(e.get('kalle_pct') or '-').strip()
        ean_tolk = str(e.get('ean_tolk') or '-').strip()
        ean_keg20 = str(e.get('ean_keg20') or '-').strip()
        ean_keg30 = str(e.get('ean_keg30') or '-').strip()

        try: prim_t = int(float(str(r[6]))) if r[6] and str(r[6]) not in ('-','None') else None
        except: prim_t = None
        try: sek_t = int(float(str(r[8]))) if r[8] and str(r[8]) not in ('-','None') else None
        except: sek_t = None
        siirtopv_d = parse_date(r[7] if len(r) > 7 else None)
        keittopv_d = parse_date(r[9] if len(r) > 9 else None)
        astiointi_d = parse_date(r[10] if len(r) > 10 else None)
        abv = r[12] if len(r) > 12 else '-'
        saanti = r[13] if len(r) > 13 else '-'
        tolkit_arvio = t.get('tolkit') or saanti or '-'
        adjunkti = r[5] if len(r) > 5 else '-'
        omakust = r[23] if len(r) > 23 else '-'
        status_raw = r[26] if len(r) > 26 else '-'

        try: status = str(round(float(str(status_raw)) * 100)) + '%'
        except: status = str(status_raw)

        if sek_t and siirtopv_d:
            tankki_str = f"{prim_t} → siirto tankkiin {sek_t} ({fmt_date(siirtopv_d)})"
        elif prim_t:
            tankki_str = str(prim_t)
        else:
            tankki_str = '-'

        keg_str = ''
        try:
            if float(keg20) > 0: keg_str += f' + {int(float(keg20))} keg 20L'
        except: pass
        try:
            if float(keg30) > 0: keg_str += f' + {int(float(keg30))} keg 30L'
        except: pass

        try: omakust_str = f'{float(str(omakust)):.2f} €'
        except: omakust_str = ''

        lines = [
            f"Erä {era} | {nimi} | {tyyli}",
            f"  Tankki: {tankki_str}",
            f"  Keitto: {fmt_date(keittopv_d)} | Astiointi: {fmt_vko(astiointi_d)} | Parasta ennen: {parasta}",
            f"  ABV: {abv}% | Tölkit: {tolkit_arvio}{keg_str}",
        ]
        if adjunkti and str(adjunkti).strip() not in ('-', ''):
            lines.append(f"  Adjunkti: {adjunkti}")
        if kollabo and str(kollabo).strip() not in ('-', ''):
            lines.append(f"  Kollabo: {kollabo}")
        if omakust_str:
            lines.append(f"  Tölkki omakust: {omakust_str}")
        if ean_tolk not in ('-', ''):
            lines.append(f"  EAN tölkki: {ean_tolk}")
        if ean_keg20 not in ('-', ''):
            lines.append(f"  EAN keg 20L: {ean_keg20}")
        if ean_keg30 not in ('-', ''):
            lines.append(f"  EAN keg 30L: {ean_keg30}")
        lines.append(f"  Etiketti: {etiketti_tilanne} | Tilausmäärä: {etiketti_maara} kpl")
        lines.append(f"  Tiimin valmius: {kalle_pct}")
        if sitaatti and str(sitaatti).strip() not in ('-', ''):
            lines.append(f"  Sitaatti: {sitaatti}")
        if olut_idea and str(olut_idea).strip() not in ('-', ''):
            lines.append(f"  Olut idea: {olut_idea}")
        if etiketti_idea and str(etiketti_idea).strip() not in ('-', ''):
            lines.append(f"  Etiketti-idea: {str(etiketti_idea)[:300]}")
        lines.append(f"  Status: {status}")
        erat_lines.append('\n'.join(lines))

    tankki_lines, brew_lines, arvio_lines = build_schedule(kalle)

    today_str = fmt_date(today)
    today_vko = today.isocalendar()[1]

    return f"""Olet Panimo Himon tuotantoassistentti. Vastaat aina suomeksi. Olet lyhyt, täsmällinen ja ammattimainen.

Tänään on {today_str} (viikko {today_vko}).

PÄIVÄMÄÄRÄSÄÄNTÖ:
Kaikki alla olevat päivämäärät on laskettu Pythonilla suoraan Sheets-datasta ja ovat ehdottoman oikeita.
Toista ne TÄSMÄLLEEN sellaisina kuin ne näkyvät — älä muuta, pyöristä tai korjaa mitään.

=== ERÄT ===

{chr(10).join(erat_lines)}

=== TANKKITILANNE ===
{chr(10).join(tankki_lines)}

=== SEURAAVAT KEITTOPÄIVÄT JA VAPAAT TANKIT ===
{chr(10).join(brew_lines)}

=== ARVIOITU ASTIOINTI UUSILLE ERILLE (vain suunnittelua varten) ===
Käytä vain jos erällä ei ole astiointipäivää Sheetsissä. Kerro aina että kyseessä on arvio.
{chr(10).join(arvio_lines)}

=== PANIMON RYTMI JA KAPASITEETTI ===
- Keittopäivät: ke ja to, 1 erä/päivä (sourit joskus 2 päivää)
- Astiointipäivät: tiistai, normaali 2 erää/päivä, max 3 erää/päivä
- Lisäkapasiteetti: keittoon pe, astiointiin ke — mainitse että vaatii rytmin muutosta

=== PARASTA ENNEN -VAROITUKSET ===
Erä 248 Kateus: 12/26 | Erä 249 Katellaan: 12/26 | Erä 262 Sytytys: Micro: 1/27 (lyhyt!)

Vastaa täsmällisesti. Jos dataa ei ole, sano rehellisesti. Älä keksi tietoja."""

cached_prompt = None

def get_system_prompt():
    global cached_prompt
    try:
        data = fetch_sheet_data()
        cached_prompt = build_system_prompt(data)
        print('Sheets-data haettu onnistuneesti.')
    except Exception as e:
        print(f'Sheets-haku epäonnistui: {e}')
        if not cached_prompt:
            cached_prompt = 'Olet Panimo Himon tuotantoassistentti. Sheets-data ei ole saatavilla juuri nyt.'
    return cached_prompt

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()

    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
        elif self.path == '/api/refresh':
            try:
                data = fetch_sheet_data()
                global cached_prompt
                cached_prompt = build_system_prompt(data)
                self.send_response(200)
                self.send_cors_headers()
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"status":"refreshed"}')
            except Exception as e:
                self.send_response(500)
                self.send_cors_headers()
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        else:
            try:
                with open('index.html', 'rb') as f:
                    content = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(content)
            except FileNotFoundError:
                self.send_response(404)
                self.end_headers()

    def do_POST(self):
        if self.path == '/api/chat':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            try:
                payload = json.loads(body)
                payload['system'] = get_system_prompt()
                req = urllib.request.Request(
                    'https://api.anthropic.com/v1/messages',
                    data=json.dumps(payload).encode('utf-8'),
                    headers={
                        'Content-Type': 'application/json',
                        'x-api-key': API_KEY,
                        'anthropic-version': '2023-06-01'
                    },
                    method='POST'
                )
                with urllib.request.urlopen(req) as resp:
                    result = resp.read()
                self.send_response(200)
                self.send_cors_headers()
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(result)
            except urllib.error.HTTPError as e:
                error_body = e.read()
                self.send_response(e.code)
                self.send_cors_headers()
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(error_body)
            except Exception as e:
                self.send_response(500)
                self.send_cors_headers()
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def send_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

if __name__ == '__main__':
    print(f'Himo AI server käynnissä portissa {PORT}')
    print('Haetaan Sheets-data...')
    get_system_prompt()
    HTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
