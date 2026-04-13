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

def build_calendar():
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    viikot = []
    for w in range(20):
        base = monday + timedelta(weeks=w)
        vnum = base.isocalendar()[1]
        ti = (base + timedelta(days=1)).strftime('%-d.%-m.')
        ke = (base + timedelta(days=2)).strftime('%-d.%-m.')
        to = (base + timedelta(days=3)).strftime('%-d.%-m.')
        pe = (base + timedelta(days=4)).strftime('%-d.%-m.')
        viikot.append(f"Viikko {vnum}: ti {ti}, ke {ke}, to {to}, pe {pe}")
    return '\n'.join(viikot)

def build_system_prompt(data):
    kalle = data.get('kalle', [])
    teemu = data.get('teemu', [])
    etusivu = data.get('etusivu', [])

    teemu_map = {}
    for r in teemu[1:]:
        if not r or not r[0]: continue
        try:
            era = str(int(float(str(r[0]))))
        except:
            continue
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
        try:
            era = str(int(float(str(r[0]))))
        except:
            continue
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
        try:
            era = str(int(float(str(r[0]))))
        except:
            continue
        if int(era) < 248: continue

        t = teemu_map.get(era, {})
        e = etusivu_map.get(era, {})

        nimi = (t.get('nimi') or '').strip() or (r[2] if len(r) > 2 else '') or '-'
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

        prim_tankki = r[6]  if len(r) > 6  else '-'
        siirtopv    = r[7]  if len(r) > 7  else '-'
        sek_tankki  = r[8]  if len(r) > 8  else '-'
        keittopv    = r[9]  if len(r) > 9  else '-'
        astiointi   = r[10] if len(r) > 10 else '-'
        abv         = r[12] if len(r) > 12 else '-'
        saanti      = r[13] if len(r) > 13 else '-'
        tolkit_arvio = t.get('tolkit') or saanti or '-'
        adjunkti    = r[5]  if len(r) > 5  else '-'
        omakust     = r[23] if len(r) > 23 else '-'
        status_raw  = r[26] if len(r) > 26 else '-'

        try:
            status = str(round(float(str(status_raw)) * 100)) + '%'
        except:
            status = str(status_raw)

        tankki_str = (
            f"{prim_tankki} → siirto tankkiin {sek_tankki} ({siirtopv})"
            if sek_tankki and str(sek_tankki).strip() and str(sek_tankki) != '-'
            else str(prim_tankki)
        )

        keg_str = ''
        try:
            if float(keg20) > 0: keg_str += f' + {int(float(keg20))} keg 20L'
        except: pass
        try:
            if float(keg30) > 0: keg_str += f' + {int(float(keg30))} keg 30L'
        except: pass

        try:
            omakust_str = f'{float(str(omakust)):.2f} €'
        except:
            omakust_str = ''

        # Muodostetaan astiointipäivä viikkonumerolla
        astiointi_str = str(astiointi)
        try:
            for fmt in ('%Y-%m-%d %H:%M:%S', '%d.%m.%Y', '%Y-%m-%d'):
                try:
                    ast_date = datetime.strptime(astiointi_str.split(' ')[0], fmt.split(' ')[0])
                    vko = ast_date.isocalendar()[1]
                    astiointi_str = f"{ast_date.strftime('%-d.%-m.%Y')} (vko {vko})"
                    break
                except:
                    continue
        except:
            pass

        lines = [
            f"Erä {era} | {nimi} | {tyyli}",
            f"  Tankki: {tankki_str}",
            f"  Keitto: {keittopv} | Astiointi: {astiointi_str} | Parasta ennen: {parasta}",
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

    today = datetime.now()
    today_str = today.strftime('%-d.%-m.%Y')
    today_viikko = today.isocalendar()[1]
    kalenteri = build_calendar()

    return f"""Olet Panimo Himon tuotantoassistentti. Vastaat aina suomeksi. Olet lyhyt, täsmällinen ja ammattimainen.

Tänään on {today_str} (viikko {today_viikko}).
Data haettu suoraan Himo_Tuotanto Google Sheetistä ({today_str}).

=== ERÄT ===

{chr(10).join(erat_lines)}

=== PANIMON RYTMI JA KAPASITEETTI ===
Normaali rytmi:
- Keittopäivät: keskiviikko ja torstai. 1 erä per päivä (sourit joskus 2 päivää).
- Astiointipäivät: tiistai. Normaali 2 erää/päivä, max 3 erää/päivä.

Jos tarvitaan enemmän kapasiteettia:
- Keitto: voi lisätä perjantain — mainitse että vaatii rytmin muutosta.
- Astiointi: voi lisätä keskiviikon — mainitse että vaatii rytmin muutosta.

Tankin vapautuminen:
- Tankki vapautuu astiointipäivänä. Erätiedoissa näkyy astiointipäivä ja viikkonumero.
- Kun tankki vapautuu, seuraava keittopäivä on sama viikko tai seuraava viikko — katso kalenterista kyseisen viikon ke tai to.
- ÄLÄ laske "astiointi + N päivää". Katso astiointiviikko erätiedoista ja etsi se kalenterista.
- Jos erällä ei ole astiointipäivää (suunnittelu): arvioi keittopäivä + noin 5 viikkoa → lähin tiistai kalenterista. Kerro että kyseessä on alustava arvio.

Päivämäärät:
- Käytä AINA alla olevaa kalenteria. Älä laske päivämääriä itse.
- Kun joku mainitsee viikonumeron, etsi se suoraan kalenterista.
- Käänteinen laskenta: jos haluttu astiointipäivä on tiedossa, etsi kalenterista noin 5 viikkoa aiempi ke tai to keittopäiväksi.

Esimerkkivastauksia:
- "Jos keitetään ke 15.4., astiointi olisi alustavasti ti 20.5. Todellinen päivä vahvistuu myöhemmin."
- "Jos erän pitää olla valmis 19.5., keitto pitäisi olla noin ke 15.4. tai to 16.4. paikkeilla."
- "5 erää viikolla 29 ei mahdu yhteen tiistaihin (max 3). Ehdotan ti 14.7. (3 erää) + ke 15.7. (2 erää) — keskiviikko vaatii rytmin muutosta."

=== KALENTERI (viikkonumeroittain) ===
{kalenteri}

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
