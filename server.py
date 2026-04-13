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
            return datetime.strptime(s[:10], fmt[:8] if 'H' not in fmt else fmt)
        except:
            continue
    return None

def fmt_date(d):
    if not d: return '-'
    return d.strftime('%-d.%-m.%Y')

def fmt_vko(d):
    if not d: return '-'
    return f"{d.strftime('%-d.%-m.%Y')} (vko {d.isocalendar()[1]})"

def next_weekday_after(d, weekday):
    """Seuraava tietty viikonpäivä d:n JÄLKEEN (ei samana päivänä)."""
    days = (weekday - d.weekday()) % 7
    if days == 0: days = 7
    return d + timedelta(days=days)

def next_brew_day_after(d):
    """Lähin ke tai to d:n jälkeen."""
    ke = next_weekday_after(d, 2)
    to = next_weekday_after(d, 3)
    return min(ke, to)

def next_tuesday_after(d):
    return next_weekday_after(d, 1)

def build_system_prompt(data):
    kalle = data.get('kalle', [])
    teemu = data.get('teemu', [])
    etusivu = data.get('etusivu', [])
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    # --- Teemu lookup ---
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

    # --- ETUSIVU lookup ---
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

    # --- Erätiedot + tankkikartta ---
    erat_lines = []
    # tankki -> (astiointi_date, era, nimi)
    tankki_astiointi = {}

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

        try: prim_t = int(float(str(r[6])))
        except: prim_t = None
        try: sek_t = int(float(str(r[8])))
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

        # Tankki jossa erä on NYT
        current_tank = None
        if sek_t and siirtopv_d and siirtopv_d <= today:
            current_tank = sek_t
        elif prim_t:
            current_tank = prim_t

        # Tallenna tankkikarttaan
        if current_tank and astiointi_d:
            if current_tank not in tankki_astiointi or (astiointi_d > tankki_astiointi[current_tank][0]):
                tankki_astiointi[current_tank] = (astiointi_d, era, nimi)

        # Muotoile tankki-tieto
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

    # --- Tankkiyhteenveto Pythonilla ---
    tankki_lines = []
    for t in range(1, 11):
        if t in tankki_astiointi:
            ast_d, era, nimi = tankki_astiointi[t]
            if ast_d >= today:
                seuraava_keitto = next_brew_day_after(ast_d)
                tankki_lines.append(
                    f"Tankki {t}: Erä {era} ({nimi}) | "
                    f"Astiointi {fmt_vko(ast_d)} | "
                    f"Vapautuu → seuraava keitto {fmt_date(seuraava_keitto)}"
                )
            else:
                tankki_lines.append(f"Tankki {t}: Astiointi oli {fmt_date(ast_d)} — vapaa")
        else:
            tankki_lines.append(f"Tankki {t}: Vapaa heti")

    # --- Seuraavat keittopäivät + vapaat tankit ---
    brew_slot_lines = []
    d = today
    count = 0
    while count < 20:
        if d.weekday() in (2, 3):  # ke=2, to=3
            vapaat = [t for t in range(1, 11)
                      if t not in tankki_astiointi or tankki_astiointi[t][0] <= d]
            paiva = 'ke' if d.weekday() == 2 else 'to'
            vko = d.isocalendar()[1]
            brew_slot_lines.append(
                f"{paiva} {fmt_date(d)} (vko {vko}) — {len(vapaat)} tankkia vapaana: {', '.join(map(str, vapaat))}"
            )
            count += 1
        d += timedelta(days=1)

    # --- Arviotaulukko keitto→astiointi ---
    arvio_lines = []
    d = today
    added = 0
    while added < 8:
        if d.weekday() in (2, 3):
            ast = next_tuesday_after(d + timedelta(days=34))
            paiva = 'ke' if d.weekday() == 2 else 'to'
            arvio_lines.append(f"Keitto {paiva} {fmt_date(d)} → arvioitu astiointi {fmt_date(ast)}")
            added += 1
        d += timedelta(days=1)

    today_str = fmt_date(today)
    today_vko = today.isocalendar()[1]

    return f"""Olet Panimo Himon tuotantoassistentti. Vastaat aina suomeksi. Olet lyhyt, täsmällinen ja ammattimainen.

Tänään on {today_str} (viikko {today_vko}).
Data haettu suoraan Himo_Tuotanto Google Sheetistä.

=== ERÄT ===

{chr(10).join(erat_lines)}

=== TANKKITILANNE (laskettu Pythonilla) ===
{chr(10).join(tankki_lines)}

=== SEURAAVAT KEITTOPÄIVÄT JA VAPAAT TANKIT (laskettu Pythonilla) ===
{chr(10).join(brew_slot_lines)}

=== KEITTO → ARVIOITU ASTIOINTI (laskettu Pythonilla, keitto + 35 pv → lähin ti) ===
HUOM: Nämä ovat arvioita suunnittelua varten. Todellinen astiointipäivä syötetään aina Sheetsiin erikseen.
{chr(10).join(arvio_lines)}

=== PANIMON RYTMI JA KAPASITEETTI ===
- Keittopäivät: ke ja to, 1 erä/päivä (sourit joskus 2 päivää)
- Astiointipäivät: tiistai, normaali 2 erää/päivä, max 3 erää/päivä
- Jos tarvitaan lisää: keittoon pe, astiointiin ke — mainitse että vaatii rytmin muutosta

SÄÄNTÖ: Käytä AINA yllä olevia Pythonilla laskettuja tietoja. Älä laske päivämääriä itse.
- Tankkien vapautuminen: katso TANKKITILANNE
- Keittopäivät ja vapaat tankit: katso SEURAAVAT KEITTOPÄIVÄT
- Arvioitu astiointi uudelle erälle: katso KEITTO → ARVIOITU ASTIOINTI -taulukko
- Jos kysytään keittopäivää tiettyä astiointia varten: laske noin 35 pv taaksepäin ja etsi lähin ke tai to SEURAAVAT KEITTOPÄIVÄT -listalta

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
