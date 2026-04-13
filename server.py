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
    """Muuntaa Sheetsin päivämäärän datetime-objektiksi."""
    if not val: return None
    s = str(val).strip()
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d.%m.%Y'):
        try:
            return datetime.strptime(s.split(' ')[0], fmt.split(' ')[0])
        except:
            continue
    return None

def fmt(d):
    """Muotoilee datetime suomalaiseksi päivämääräksi."""
    if not d: return '-'
    return d.strftime('%-d.%-m.%Y')

def fmt_vko(d):
    """Muotoilee datetime päivämäärä + viikkonumero."""
    if not d: return '-'
    return f"{d.strftime('%-d.%-m.%Y')} (vko {d.isocalendar()[1]})"

def next_weekday(d, weekday):
    """Palauttaa seuraavan tietyn viikonpäivän d:n jälkeen (0=ma...6=su)."""
    days_ahead = weekday - d.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    return d + timedelta(days=days_ahead)

def next_brew_day(after_date):
    """Palauttaa seuraavan keittopäivän (ke tai to) after_date jälkeen."""
    ke = next_weekday(after_date, 2)  # keskiviikko
    to = next_weekday(after_date, 3)  # torstai
    return min(ke, to)

def next_packaging_day(after_date):
    """Palauttaa seuraavan tiistain after_date jälkeen."""
    return next_weekday(after_date, 1)

def estimated_packaging(brew_date):
    """Arvioi astiointipäivän: keitto + 35 päivää → lähin tiistai."""
    target = brew_date + timedelta(days=35)
    return next_packaging_day(target - timedelta(days=1))

def estimated_brew(packaging_date):
    """Arvioi keittopäivän: astiointi - 35 päivää → lähin ke tai to."""
    target = packaging_date - timedelta(days=35)
    return next_brew_day(target - timedelta(days=1))

def build_schedule(kalle_rows):
    """Laskee tankki- ja aikataulutiedot suoraan datasta."""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    # Tankkien tilanne
    tankki_map = {}  # tankki_nro -> {era, nimi, astiointi}
    for r in kalle_rows[1:]:
        if not r or not r[0]: continue
        try:
            era = int(float(str(r[0])))
        except:
            continue
        if era < 248: continue

        astiointi = parse_date(r[10] if len(r) > 10 else None)
        nimi = str(r[2] if len(r) > 2 else '-').strip() or '-'

        # Primääri tankki
        try:
            prim = int(float(str(r[6])))
        except:
            prim = None

        # Sekundääri tankki
        try:
            sek = int(float(str(r[8])))
        except:
            sek = None

        siirtopv = parse_date(r[7] if len(r) > 7 else None)

        if prim:
            # Mikä erä on tankissa tänään?
            # Jos siirto on jo tapahtunut, primääri on vapaa
            if sek and siirtopv and siirtopv <= today:
                # Erä on jo sekundäärissä
                if sek not in tankki_map or tankki_map[sek].get('astiointi') is None or \
                   (astiointi and tankki_map[sek].get('astiointi') and astiointi > tankki_map[sek]['astiointi']):
                    tankki_map[sek] = {'era': era, 'nimi': nimi, 'astiointi': astiointi}
            else:
                # Erä on vielä primäärissä
                if prim not in tankki_map or tankki_map[prim].get('astiointi') is None or \
                   (astiointi and tankki_map[prim].get('astiointi') and astiointi > tankki_map[prim]['astiointi']):
                    tankki_map[prim] = {'era': era, 'nimi': nimi, 'astiointi': astiointi}
                # Merkitse myös sekundääri jos siirto tulevaisuudessa
                if sek and siirtopv and siirtopv > today:
                    if sek not in tankki_map:
                        tankki_map[sek] = {'era': era, 'nimi': nimi, 'astiointi': astiointi, 'tulossa': True}

    # Rakenna tankkilista
    tankki_lines = []
    for t in range(1, 11):
        info = tankki_map.get(t)
        if info:
            ast = info.get('astiointi')
            if ast and ast >= today:
                vapautuu = fmt_vko(ast)
                seuraava_keitto = fmt(next_brew_day(ast))
                tankki_lines.append(
                    f"Tankki {t}: Erä {info['era']} ({info['nimi']}) | "
                    f"Astiointi: {vapautuu} | "
                    f"Vapautuu, seuraava keitto: {seuraava_keitto}"
                )
            elif ast and ast < today:
                tankki_lines.append(f"Tankki {t}: Erä {info['era']} ({info['nimi']}) | Astiointi oli {fmt(ast)} — tankki vapaa")
            else:
                tankki_lines.append(f"Tankki {t}: Erä {info['era']} ({info['nimi']}) | Astiointipäivä ei tiedossa")
        else:
            tankki_lines.append(f"Tankki {t}: Tyhjä — vapaa heti")

    # Seuraavat vapaat keittopäivät (ke/to) seuraavalle 10 viikolle
    # ja montako tankkia vapautuu mihinkin mennessä
    brew_slots = []
    check = today
    for _ in range(70):  # 10 viikkoa * 7 päivää
        wd = check.weekday()
        if wd in (2, 3):  # ke tai to
            vapaat_tankit = [t for t in range(1, 11)
                           if t not in tankki_map or
                           not tankki_map[t].get('astiointi') or
                           tankki_map[t]['astiointi'] <= check]
            paiva_nimi = 'ke' if wd == 2 else 'to'
            brew_slots.append(f"{paiva_nimi} {fmt(check)} (vko {check.isocalendar()[1]}) — {len(vapaat_tankit)} tankkia vapaana: {', '.join(map(str, vapaat_tankit)) if vapaat_tankit else 'ei vapaita'}")
        check += timedelta(days=1)

    return '\n'.join(tankki_lines), '\n'.join(brew_slots[:20])

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
        astiointi_raw = r[10] if len(r) > 10 else None
        ast_date    = parse_date(astiointi_raw)
        astiointi   = fmt_vko(ast_date) if ast_date else '-'
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

        lines = [
            f"Erä {era} | {nimi} | {tyyli}",
            f"  Tankki: {tankki_str}",
            f"  Keitto: {keittopv} | Astiointi: {astiointi} | Parasta ennen: {parasta}",
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
    today_str = fmt(today)
    today_vko = today.isocalendar()[1]

    # Laskee Python-puolella tankkitilanne ja keittopäivät
    tankki_status, brew_slots = build_schedule(kalle)

    # Aikataulutusapufunktiot tekstinä promptiin
    def sched_info():
        lines = []
        lines.append("Arvioi keitto → astiointi (keitto + 35 pv → lähin ti):")
        test_dates = [today + timedelta(weeks=w) for w in range(1, 6)]
        for d in test_dates:
            # Etsi lähin ke
            ke = d - timedelta(days=d.weekday()) + timedelta(days=2)
            ast = estimated_packaging(ke)
            lines.append(f"  Jos keitto {fmt(ke)} → arvioitu astiointi {fmt(ast)}")
        lines.append("Arvioi astiointi → keitto (astiointi - 35 pv → lähin ke/to):")
        for d in test_dates:
            ti = d - timedelta(days=d.weekday()) + timedelta(days=1)
            brew = estimated_brew(ti)
            lines.append(f"  Jos astiointi {fmt(ti)} → arvioitu keitto {fmt(brew)}")
        return '\n'.join(lines)

    return f"""Olet Panimo Himon tuotantoassistentti. Vastaat aina suomeksi. Olet lyhyt, täsmällinen ja ammattimainen.

Tänään on {today_str} (viikko {today_vko}).
Data haettu suoraan Himo_Tuotanto Google Sheetistä ({today_str}).

=== ERÄT ===

{chr(10).join(erat_lines)}

=== TANKKITILANNE (laskettu Pythonilla Sheets-datasta) ===
{tankki_status}

=== SEURAAVAT VAPAAT KEITTOPÄIVÄT (laskettu Pythonilla) ===
{brew_slots}

=== PANIMON RYTMI JA KAPASITEETTI ===
- Keittopäivät: ke ja to. 1 erä/päivä (sourit joskus 2 päivää).
- Astiointipäivät: tiistai. Normaali 2 erää/päivä, max 3 erää/päivä.
- Jos tarvitaan lisää kapasiteettia: keittoon pe, astiointiin ke — mainitse että vaatii rytmin muutosta.

TÄRKEÄ SÄÄNTÖ: Älä koskaan laske päivämääriä itse. Käytä AINA yllä olevia Pythonilla laskettuja tietoja.
- Tankkien vapautumispäivät: katso TANKKITILANNE-osiosta.
- Seuraavat keittopäivät: katso SEURAAVAT VAPAAT KEITTOPÄIVÄT-osiosta.
- Arvioitu astiointi uudelle erälle (ei vielä Sheetsissä): keitto + 35 päivää → lähin tiistai. Kerro aina että kyseessä on alustava arvio.
- Arvioitu keitto jos astiointi tiedossa: astiointi - 35 päivää → lähin ke tai to. Kerro aina että kyseessä on alustava arvio.

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
