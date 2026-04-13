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
    for attempt in range(3):
        try:
            req = urllib.request.Request(WEBHOOK, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except Exception as e:
            if attempt == 2:
                raise
            print(f'Sheets-haku yritys {attempt+1} epäonnistui: {e}, yritetään uudelleen...')
    return None

def parse_date(val):
    if not val: return None
    s = str(val).strip()
    if s in ('-', '', 'None'): return None
    # Google Sheets lähettää ajat UTC-muodossa, Suomi on UTC+3
    # Esim. "2026-05-18T21:00:00.000Z" = 19.5. Suomen aikaa
    if 'T' in s or 'Z' in s:
        try:
            s_clean = s.replace('Z', '').replace('T', ' ')
            d = datetime.strptime(s_clean[:19], '%Y-%m-%d %H:%M:%S')
            d = d + timedelta(hours=3)  # UTC → Suomi
            return d
        except:
            pass
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

def build_planning_tables():
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    keitto_to_ast = []
    d = today
    added = 0
    while added < 10:
        if d.weekday() in (2, 3):
            ast = next_after(d + timedelta(days=34), 1)
            p = 'ke' if d.weekday() == 2 else 'to'
            keitto_to_ast.append(f"Keitto {p} {fmt_date(d)} → arvioitu astiointi ti {fmt_date(ast)}")
            added += 1
        d += timedelta(days=1)

    ast_to_keitto = []
    d = today
    added = 0
    while added < 10:
        if d.weekday() == 1:
            ke = next_after(d - timedelta(days=36), 2)
            to = next_after(d - timedelta(days=36), 3)
            brew = min(ke, to)
            p = 'ke' if brew.weekday() == 2 else 'to'
            ast_to_keitto.append(f"Astiointi ti {fmt_date(d)} → arvioitu keitto {p} {fmt_date(brew)}")
            added += 1
        d += timedelta(days=1)

    return '\n'.join(keitto_to_ast), '\n'.join(ast_to_keitto)

def build_system_prompt(data):
    kalle = data.get('kalle', [])
    teemu = data.get('teemu', [])
    etusivu = data.get('etusivu', [])
    today = datetime.now()
    today_str = fmt_date(today)
    today_vko = today.isocalendar()[1]

    teemu_map = {}
    for r in teemu[1:]:
        if not r or not r[0]: continue
        try: era = str(int(float(str(r[0]))))
        except: continue
        teemu_map[era] = {
            'nimi':          r[2]  if len(r) > 2  else None,
            'tyyli':         r[3]  if len(r) > 3  else '-',
            'sitaatti':      r[4]  if len(r) > 4  else '-',
            'kollabo':       r[5]  if len(r) > 5  else '-',
            'olut_idea':     r[6]  if len(r) > 6  else '-',
            'etiketti_idea': r[7]  if len(r) > 7  else '-',
            'tolkit':        r[8]  if len(r) > 8  else '-',
            'keg20':         r[9]  if len(r) > 9  else '0',
            'keg30':         r[10] if len(r) > 10 else '0',
        }

    etusivu_map = {}
    for r in etusivu[1:]:
        if not r or not r[0]: continue
        try: era = str(int(float(str(r[0]))))
        except: continue
        etusivu_map[era] = {
            'parasta':          r[7]  if len(r) > 7  else '-',
            'etiketti_maara':   r[14] if len(r) > 14 else '-',
            'etiketti_tilanne': r[15] if len(r) > 15 else '-',
            'kalle_pct':        r[21] if len(r) > 21 else '-',
            'ean_tolk':         r[11] if len(r) > 11 else '-',
            'ean_keg20':        r[12] if len(r) > 12 else '-',
            'ean_keg30':        r[13] if len(r) > 13 else '-',
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
        tyyli         = t.get('tyyli') or '-'
        kollabo       = t.get('kollabo') or '-'
        sitaatti      = t.get('sitaatti') or '-'
        olut_idea     = t.get('olut_idea') or '-'
        etiketti_idea = t.get('etiketti_idea') or '-'
        keg20         = str(t.get('keg20') or '0').strip()
        keg30         = str(t.get('keg30') or '0').strip()
        parasta          = str(e.get('parasta') or '-').strip()
        etiketti_tilanne = str(e.get('etiketti_tilanne') or '-').strip()
        etiketti_maara   = str(e.get('etiketti_maara') or '-').strip()
        kalle_pct        = str(e.get('kalle_pct') or '-').strip()
        ean_tolk         = str(e.get('ean_tolk') or '-').strip()
        ean_keg20        = str(e.get('ean_keg20') or '-').strip()
        ean_keg30        = str(e.get('ean_keg30') or '-').strip()

        try: prim_t = int(float(str(r[6]))) if r[6] and str(r[6]) not in ('-','None') else None
        except: prim_t = None
        try: sek_t = int(float(str(r[8]))) if r[8] and str(r[8]) not in ('-','None') else None
        except: sek_t = None
        siirtopv_d  = parse_date(r[7]  if len(r) > 7  else None)
        keittopv_d  = parse_date(r[9]  if len(r) > 9  else None)
        astiointi_d = parse_date(r[10] if len(r) > 10 else None)
        abv         = r[12] if len(r) > 12 else '-'
        saanti      = r[13] if len(r) > 13 else '-'
        tolkit_arvio = t.get('tolkit') or saanti or '-'
        adjunkti    = r[5]  if len(r) > 5  else '-'
        omakust     = r[23] if len(r) > 23 else '-'
        status_raw  = r[26] if len(r) > 26 else '-'

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

    keitto_to_ast, ast_to_keitto = build_planning_tables()

    return f"""Olet Panimo Himon tuotantoassistentti. Vastaat aina suomeksi. Olet lyhyt, täsmällinen ja ammattimainen.

Tänään on {today_str} (viikko {today_vko}).
Data haettu suoraan Himo_Tuotanto Google Sheetistä.

PÄIVÄMÄÄRÄT OVAT PYHIÄ:
Toista Sheetsin päivämäärät AINA täsmälleen sellaisina kuin ne näkyvät alla. Älä koskaan muuta, korjaa, pyöristä tai keksi päivämääriä. Jos päivämäärä puuttuu, sano että se puuttuu.
Suunnittelutaulukoissa olevat ARVIOT ovat Pythonin laskemia — toista nekin täsmälleen sellaisina kuin ne näkyvät.

=== ERÄT ===

{chr(10).join(erat_lines)}

=== SUUNNITTELUTAULUKOT (Python-laskettu, ~35 pv valmistusaika) ===
Käytä näitä kun suunnitellaan tulevia eriä joilla ei vielä ole päivämääriä Sheetsissä.
Kerro aina että kyseessä on alustava arvio — todellinen päivä vahvistuu tilanteen mukaan.

Keitto → arvioitu astiointi:
{keitto_to_ast}

Astiointi → arvioitu keitto:
{ast_to_keitto}

=== PANIMON RYTMI ===
- Keittopäivät: yleensä ke ja to, 1 erä/päivä
- Astiointipäivät: yleensä tiistai, normaali 2 erää/päivä, max 3
- Lisäkapasiteetti tarvittaessa: keittoon pe, astiointiin ke — vaatii rytmin muutosta
- Tankkitilanne ja aikataulu: katso Tankkivaraus-välilehti Sheetsissä

=== PARASTA ENNEN -VAROITUKSET ===
Erä 248 Kateus: 12/26 | Erä 249 Katellaan: 12/26 | Erä 262 Sytytys: Micro: 1/27 (lyhyt!)

Vastaa täsmällisesti. Jos dataa ei ole, sano rehellisesti. Älä keksi tietoja."""

def get_system_prompt():
    try:
        data = fetch_sheet_data()
        return build_system_prompt(data)
    except Exception as e:
        print(f'Sheets-haku epäonnistui: {e}')
        return 'Olet Panimo Himon tuotantoassistentti. Sheets-data ei ole saatavilla juuri nyt.'

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
    HTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
