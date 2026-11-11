import os, re, time, requests, base64
from datetime import datetime, date
from playwright.sync_api import sync_playwright

URL = "https://kbw-personal-services.butlerapp2.de/demo#/courses?fcourses=yaounde_deutsch_b2"
BOT_TOKEN = os.getenv("TG_TOKEN", "")
CHAT_IDS = ["8806922221", "-5434725968"]

notifie_libre_aujourdhui = {}

def notify(text):
    for cid in CHAT_IDS:
        try:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                          json={"chat_id": cid, "text": text, "parse_mode": "HTML"}, timeout=15)
        except: pass
    print(text)

# Heartbeat toutes les 4h sur l'heure absolue, pas sur le début du run
# Comme ça il ne dérive pas même quand on chaîne les runs
HEARTBEAT_BLOCK = [int(time.time() // 14400)]

def maybe_heartbeat():
    cur = int(time.time() // 14400)
    if cur != HEARTBEAT_BLOCK[0]:
        HEARTBEAT_BLOCK[0] = cur
        notify(f"💓 KBW Bot toujours en cours - {datetime.now().strftime('%d/%m %H:%M')} - Recherche active, aucune réservation pour l'instant")
        return True
    return False

def parse_date(slot_txt):
    try:
        m = re.search(r'(\d{2})\.(\d{2})\.(\d{4})', slot_txt)
        if m:
            return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except: return None
    return None

def scan_with_dates(page):
    libres = []
    for pnum in range(1,5):
        page.wait_for_timeout(1200)
        cnt = page.locator('text=/\\d{1,2}:\\d{2} Uhr.*\\d{2}\\.\\d{2}\\.\\d{4}/').count()
        for i in range(cnt):
            try:
                h = page.locator('text=/\\d{1,2}:\\d{2} Uhr.*\\d{2}\\.\\d{2}\\.\\d{4}/').nth(i)
                txt = h.inner_text().strip()
                if not txt: continue
                h.click(); page.wait_for_timeout(700)
                has_b = page.locator('button, a').filter(has_text=re.compile(r'Buchen', re.I)).count() > 0
                full = page.locator('text=/ausgebucht|Warteliste/i').count() > 0
                dis = page.locator('button[disabled]').filter(has_text=re.compile(r'Buchen', re.I)).count()
                if has_b and not full and dis == 0:
                    d = parse_date(txt)
                    libres.append((txt, h, d))
                try: h.click(); page.wait_for_timeout(150)
                except: pass
            except: continue
        if pnum < 4:
            try:
                nxt = page.locator(f'text="{pnum+1}"').first
                if nxt.count()>0: nxt.click()
                else: page.locator('text=">"').last.click()
                page.wait_for_timeout(2500)
            except: break
    return libres

def remplir_formulaire(page):
    print("  Remplissage...")
    try:
        b64_1 = os.getenv("KBW_PASS_B64_1","")
        b64_2 = os.getenv("KBW_PASS_B64_2","")
        b64 = b64_1 + b64_2
        if not b64:
            b64 = os.getenv("KBW_PASS_B64","")
        if b64 and not os.path.exists("pass.jpg"):
            with open("pass.jpg","wb") as f:
                f.write(base64.b64decode(b64.strip()))
            print("  Passeport reconstruit")
    except Exception as e:
        print(f"  Erreur passeport: {e}")

    def try_fill(selectors, value):
        if not value: return False
        for sel in selectors:
            try:
                el = page.locator(sel).first
                if el.count()>0:
                    el.fill(value)
                    return True
            except: continue
        return False

    try:
        anrede = os.getenv("KBW_ANREDE","Herr")
        sel = page.locator('select').filter(has_text=re.compile(r'Anrede', re.I)).first
        if sel.count()>0:
            sel.select_option(label=anrede)
    except: pass

    try_fill(['input[name*="vorname" i]'], os.getenv("KBW_VORNAME",""))
    try_fill(['input[name*="nachname" i]'], os.getenv("KBW_NACHNAME",""))
    try_fill(['input[type="email"]'], os.getenv("KBW_EMAIL",""))
    try_fill(['input[type="tel"]'], os.getenv("KBW_TELEFON",""))
    try_fill(['input[name*="geburt" i]'], os.getenv("KBW_GEBURTSDATUM",""))
    try_fill(['input[name*="strasse" i]'], os.getenv("KBW_STRASSE",""))
    try_fill(['input[name*="plz" i]'], os.getenv("KBW_PLZ",""))
    try_fill(['input[name*="ort" i]'], os.getenv("KBW_ORT",""))
    try:
        land = os.getenv("KBW_LAND","Cameroun")
        sel_land = page.locator('select').filter(has_text=re.compile(r'Land', re.I)).first
        if sel_land.count()>0:
            sel_land.select_option(label=land)
    except: pass

    try:
        if os.path.exists("pass.jpg"):
            page.locator('input[type="file"]').first.set_input_files("pass.jpg")
            print("  Passeport uploadé")
    except: pass
    page.wait_for_timeout(1000)

def auto_book_infini(page, slot_text, header_el):
    tentative = 0
    while True:
        tentative += 1
        maybe_heartbeat()
        print(f"\nAUTO-BOOK #{tentative} : {slot_text}")
        notify(f"🤖 Tentative #{tentative}\n{slot_text}")
        try:
            try:
                header_el.click(); page.wait_for_timeout(1000)
                buchen = page.locator('button, a').filter(has_text=re.compile(r'Buchen', re.I)).first
                if buchen.count()>0:
                    buchen.click(); page.wait_for_timeout(4000)
                else: return False
            except:
                time.sleep(2); continue

            remplir_formulaire(page)
            try:
                page.get_by_role("button", name=re.compile(r'Suivant|Weiter', re.I)).first.click()
                page.wait_for_timeout(4000)
            except: pass

            while True:
                try:
                    cb = page.locator('input[type="checkbox"]').first
                    if cb.count()>0 and not cb.is_checked():
                        cb.check()
                    final_btn = page.locator('button').filter(has_text=re.compile(r'abschicken|Anmelden', re.I)).last
                    if final_btn.count()==0:
                        final_btn = page.locator('button').filter(has_text=re.compile(r'Suivant|Bezahlen', re.I)).last
                    if final_btn.count()>0:
                        final_btn.click()
                    page.wait_for_timeout(6000)
                    err = page.locator('text=/Une erreur technique|technical error/i')
                    if err.count()>0:
                        print(f"Erreur technique - retry #{tentative}")
                        time.sleep(3)
                        continue
                    else:
                        notify(f"✅ INSCRIPTION REUSSIE - {slot_text} - Bot s'arrete")
                        with open("SUCCESS.txt","w") as f:
                            f.write(slot_text)
                        return True
                except:
                    time.sleep(2); continue
        except:
            time.sleep(3); continue

notify("BOT DEMARRE - Fin Fevrier prioritaire sinon apres - 24h/24")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
    page = browser.new_page()
    memo = set()
    first = True
    start = time.time()
    max_dur = 21000 if os.getenv("GITHUB_ACTIONS")=="true" else 999999999

    while time.time() - start < max_dur:
        maybe_heartbeat()
        print(f"\nPHASE 1 : INIT")
        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(4000)
        except:
            try: browser.close()
            except: pass
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            page = browser.new_page()
            continue

        print(f"PHASE 2 : DETECTION")
        all_libres = scan_with_dates(page)
        all_valid = [x for x in all_libres if x[2]]
        fin_fev = [x for x in all_valid if x[2].month == 2 and x[2].day >= 20]
        print(f"  -> {len(all_valid)} libres, {len(fin_fev)} en fin fevrier")

        if first:
            memo = set([t for t,_,_ in all_libres])
            first = False
            continue

        actuelles_txt = set([t for t,_,_ in all_libres])
        for slot in actuelles_txt:
            if slot in notifie_libre_aujourdhui and notifie_libre_aujourdhui[slot] == date.today(): continue
            if slot not in memo:
                notify(f"LIBRE {slot}")
                notifie_libre_aujourdhui[slot] = date.today()
        memo = actuelles_txt

        if not all_valid:
            page.wait_for_timeout(1000)
            continue

        if fin_fev:
            fin_fev.sort(key=lambda x: x[2])
            cible = fin_fev[-1]
            print(f"CIBLE FIN FEVRIER : {cible[0]}")
        else:
            apres_fev = [x for x in all_valid if x[2] > datetime(2027, 2, 28)]
            if not apres_fev:
                apres_fev = [x for x in all_valid if x[2] > datetime(2026, 2, 28)]
            apres_fev.sort(key=lambda x: x[2])
            if not apres_fev: continue
            cible = apres_fev[0]
            print(f"CIBLE APRES FEVRIER : {cible[0]}")

        txt, el, dobj = cible
        if auto_book_infini(page, txt, el):
            break
