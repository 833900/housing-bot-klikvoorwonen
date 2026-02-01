#!/usr/bin/env python3
"""
Bot do automatycznego monitorowania i aplikowania na mieszkania socjalne
ZAKTUALIZOWANY DLA: Klik voor Wonen (www.klikvoorwonen.nl)
"""

import time
import logging
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

# Konfiguracja logowania
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('housing_bot.log'),
        logging.StreamHandler()
    ]
)

class KlikVoorWonenBot:
    def __init__(self, username, password):
        """
        Inicjalizacja bota dla Klik voor Wonen
        
        Args:
            username: Twój login
            password: Twoje hasło
        """
        self.username = username
        self.password = password
        self.base_url = "https://www.klikvoorwonen.nl"
        self.login_url = f"{self.base_url}/portaal/inloggen"
        self.aanbod_url = f"{self.base_url}/aanbod"
        self.applied_offers = set()
        self.driver = None
        
    def setup_driver(self):
        """Konfiguracja przeglądarki Chrome"""
        chrome_options = Options()
        # Odkomentuj poniższą linię dla trybu headless (bez okna)
        # chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.driver.maximize_window()
        logging.info("Przeglądarka uruchomiona")
        
    def dismiss_cookies(self):
        """Zamknij banner cookiesa jeśli się pojawi"""
        try:
            # Szukamy przycisku "Cookies accepteren"
            cookie_btn = self.driver.execute_script("""
                const btns = document.querySelectorAll('button');
                for (let btn of btns) {
                    if (btn.innerText && btn.innerText.includes('Cookies accepteren')) {
                        btn.click();
                        return true;
                    }
                }
                return false;
            """)
            if cookie_btn:
                logging.info("✓ Cookie banner zamknięty")
                time.sleep(1)
        except:
            pass

    def _focus_shadow_input(self, name):
        """
        Znajdź <input> w Shadow DOM tego zds-input-text[name=X]
        który jest WIDOCZNY (ma niezerowy rect) i daj mu focus.
        Zwraca True jeśli focus się powiodł.
        """
        result = self.driver.execute_script("""
            const components = document.querySelectorAll('zds-input-text[name="' + arguments[0] + '"]');
            for (const comp of components) {
                if (!comp.shadowRoot) continue;
                const input = comp.shadowRoot.querySelector('input');
                if (!input) continue;
                const rect = input.getBoundingClientRect();
                // Weź tylko ten który jest widoczny (height > 0)
                if (rect.height > 0) {
                    input.focus();
                    input.click();
                    return { found: true, x: rect.x, y: rect.y, w: rect.width, h: rect.height };
                }
            }
            return { found: false };
        """, name)
        if result and result.get('found'):
            logging.info(f"  ✓ focus na input[name={name}] — rect: x={result['x']}, y={result['y']}, w={result['w']}, h={result['h']}")
            return True
        logging.error(f"  ✗ nie znaleziono widocznego input[name={name}]")
        return False

    def _set_shadow_input_value(self, name, value):
        """
        Wpisz wartość do <input> w Shadow DOM i wystrzel events,
        żeby React/framework zauważył zmianę.
        """
        done = self.driver.execute_script("""
            const components = document.querySelectorAll('zds-input-text[name="' + arguments[0] + '"]');
            for (const comp of components) {
                if (!comp.shadowRoot) continue;
                const input = comp.shadowRoot.querySelector('input');
                if (!input) continue;
                const rect = input.getBoundingClientRect();
                if (rect.height > 0) {
                    // Native input value setter — ominija React controlled component
                    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                    nativeInputValueSetter.call(input, arguments[1]);
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                    return true;
                }
            }
            return false;
        """, name, value)
        return done

    def _click_submit_button(self):
        """
        Kliknij <button> wewnątrz Shadow DOM tego zds-button[type=submit]
        który jest widoczny.
        """
        done = self.driver.execute_script("""
            const buttons = document.querySelectorAll('zds-button[type="submit"]');
            for (const btn of buttons) {
                if (!btn.shadowRoot) continue;
                const inner = btn.shadowRoot.querySelector('button');
                if (!inner) continue;
                const rect = inner.getBoundingClientRect();
                if (rect.height > 0) {
                    inner.click();
                    return true;
                }
            }
            return false;
        """)
        return done

    def login(self):
        """
        Logowanie na Klik voor Wonen.

        Struktura DOM (z debugu):
        - Są DWA formularze na stronie (mobile + desktop). Mobile ma rect=0 (ukryty).
        - Każde pole to <zds-input-text> z Shadow DOM w środku.
        - Wewnątrz shadowRoot jest prawdziwy <input>.
        - Przycisk "Inloggen" to <zds-button type=submit> z <button> w shadowRoot.
        - zds-form też ma shadowRoot, więc normalne form.submit() nie działa.

        Strategia:
        1. JS: focus() + click() na <input> w shadowRoot (widocznego)
        2. Selenium send_keys na active_element (idzie do sfokusowanego input)
        3. JS: kliknąć <button> w shadowRoot submit button
        """
        from selenium.webdriver.common.keys import Keys

        try:
            logging.info("Rozpoczynam logowanie do Klik voor Wonen...")
            self.driver.get(self.login_url)
            time.sleep(5)

            # Zamknij cookie banner
            self.dismiss_cookies()
            time.sleep(1)

            # --- USERNAME ---
            logging.info("Wypełniam pole username...")
            if not self._focus_shadow_input('username'):
                self.driver.save_screenshot('login_error.png')
                return False
            time.sleep(0.5)

            # Pisz do sfokusowanego elementu
            active = self.driver.switch_to.active_element
            active.send_keys(self.username)
            time.sleep(0.5)
            logging.info(f"  ✓ username wpisany")

            # --- PASSWORD ---
            logging.info("Wypełniam pole password...")
            if not self._focus_shadow_input('password'):
                self.driver.save_screenshot('login_error.png')
                return False
            time.sleep(0.5)

            active = self.driver.switch_to.active_element
            active.send_keys(self.password)
            time.sleep(0.5)
            logging.info(f"  ✓ password wpisany")

            # Screenshot przed wysyłaniem
            self.driver.save_screenshot('login_before_submit.png')
            logging.info("Screenshot: login_before_submit.png")

            # --- KLIKNIJ INLOGGEN ---
            logging.info("Klikam przycisk Inloggen...")
            if not self._click_submit_button():
                logging.warning("Nie znaleziono przycisku submit — spróbuję Enter")
                active = self.driver.switch_to.active_element
                active.send_keys(Keys.ENTER)

            time.sleep(6)

            # Screenshot po wysyłaniu
            self.driver.save_screenshot('login_after_submit.png')

            # Sprawdź czy zalogowano
            current_url = self.driver.current_url
            logging.info(f"URL po logowaniu: {current_url}")

            if 'inloggen' not in current_url:
                logging.info("✓ Zalogowano pomyślnie!")
                return True
            else:
                logging.error("✗ Logowanie się nie powiodło")
                logging.error("Sprawdź: login_before_submit.png i login_after_submit.png")
                return False

        except Exception as e:
            logging.error(f"Błąd podczas logowania: {e}")
            import traceback
            traceback.print_exc()
            try:
                self.driver.save_screenshot('login_exception.png')
            except:
                pass
            return False
    
    # ----------------------------------------------------------
    # OFERTY: pobieranie listy z strony aanbod
    # ----------------------------------------------------------
    # URL ofert:
    OFFERS_URL = "https://www.klikvoorwonen.nl/aanbod/nu-te-huur/huurwoningen#?gesorteerd-op=zoekprofiel"
    # Dozwolone energielabels (wielkie litery)
    ALLOWED_ENERGIELABELS = {"A+++", "A++", "A+", "A", "B", "C"}

    def get_all_offer_urls(self):
        """
        Idź na stronę ofert, czekaj na Angular, wyciąg wszystkie linki
        do szczegółów ofert (pattern /details/NUMER-...).
        Zwraca listę unikalnych URL.
        """
        logging.info("Otwieram stronę ofert...")
        self.driver.get(self.OFFERS_URL)
        time.sleep(12)  # Angular potrzebuje ~10 sek żeby zarendeować oferty
        self.dismiss_cookies()
        time.sleep(1)

        urls = self.driver.execute_script("""
            const container = document.querySelector('.woningaanbod-container');
            if (!container) return [];
            const links = container.querySelectorAll('a[href*="/details/"]');
            const seen = new Set();
            const result = [];
            links.forEach(a => {
                const href = a.getAttribute('href');
                // Weź tylko linki z numerem oferty (pattern: /details/NUMER-...)
                if (href && /\\/details\\/\\d+/.test(href) && !seen.has(href)) {
                    seen.add(href);
                    result.push(window.location.origin + href);
                }
            });
            return result;
        """)

        logging.info(f"  Znaleziono {len(urls)} ofert na stronie")
        return urls

    # ----------------------------------------------------------
    # DETAIL OFERTY: analiza + aplikowanie
    # ----------------------------------------------------------
    def analyze_offer(self, offer_url):
        """
        Otwórz ofertę, sprawdź:
          1. czy już zaaplikowano (input.reageer-button value="Verwijder reactie")
          2. czy model to "Loting"
          3. czy nie ma "Voorrang voor 55+" (lub inne ograniczenia wiekowe)
          4. jaki jest Energielabel

        Zwraca dict:
          { already_applied: bool, is_loting: bool, has_age_restriction: bool, energielabel: str|None }
        """
        logging.info(f"  Analizuję ofertę: {offer_url}")
        self.driver.get(offer_url)
        time.sleep(8)  # Angular detail potrzebuje czasu
        self.dismiss_cookies()
        time.sleep(1)

        # Scroll do sekcji Reageren żeby Angular zrenderowało reageer-form
        # (input.reageer-button pojawia się dopiero po scrollowaniu)
        self.driver.execute_script("""
            const section = document.querySelector('#object-details-reageren');
            if (section) section.scrollIntoView({ behavior: 'instant', block: 'center' });
        """)
        time.sleep(3)

        info = self.driver.execute_script("""
            const result = { already_applied: false, is_loting: false, has_age_restriction: false, energielabel: null };

            // 0. ALREADY APPLIED — Angular renderuje <input class="reageer-button" value="Verwijder reactie">
            //    jeśli oferta jest już zaaplikowana. Sprawdzamy to PRZED wszystkim.
            const reageerBtn = document.querySelector('input.reageer-button');
            if (reageerBtn && reageerBtn.value === 'Verwijder reactie') {
                result.already_applied = true;
            }

            // 1. LOTING — sekcja #object-details-reageren zawiera <strong> z "Loting"
            const reagerenSection = document.querySelector('#object-details-reageren');
            if (reagerenSection) {
                const strongs = reagerenSection.querySelectorAll('strong');
                strongs.forEach(s => {
                    if (s.innerText.trim() === 'Loting') result.is_loting = true;
                });
            }

            // 2. AGE RESTRICTION — .voorrangsregels zawiera tekst "55+" lub "65+"
            const voorrang = document.querySelector('.voorrangsregels');
            if (voorrang) {
                const txt = voorrang.innerText;
                if (txt.includes('55+') || txt.includes('65+')) {
                    result.has_age_restriction = true;
                }
            }

            // 3. ENERGIELABEL — table.summary, szukamy row gdzie td.label = "Energielabel"
            const rows = document.querySelectorAll('table.summary tr');
            rows.forEach(tr => {
                const label = tr.querySelector('td.label');
                const value = tr.querySelector('td.value');
                if (label && value && label.innerText.trim() === 'Energielabel') {
                    const txt = value.innerText.trim();  // "Energielabel A"
                    const match = txt.match(/Energielabel\\s+([A-G][+]*)/i);
                    if (match) result.energielabel = match[1].toUpperCase();
                }
            });

            return result;
        """)

        logging.info(f"    AlreadyApplied={info['already_applied']}, Loting={info['is_loting']}, 55+={info['has_age_restriction']}, Energielabel={info['energielabel']}")
        return info

    def click_reageer(self):
        """
        Kliknij przycisk "Reageer".
        Z debugu wiemy że Angular renderuje go jako:
          <input type="submit" class="reageer-button" value="Reageer">
        wewnątrz <form name="reactForm"> w <div reageer-form>.
        Scroll już zrobiony w analyze_offer, więc form powinien być w DOM.
        Zwraca True jeśli kliknięto.
        """
        # Dodatkowy scroll + wait na wypadek
        self.driver.execute_script("""
            const section = document.querySelector('#object-details-reageren');
            if (section) section.scrollIntoView({ behavior: 'instant', block: 'center' });
        """)
        time.sleep(2)

        clicked = self.driver.execute_script("""
            // PRIORITET 1: input.reageer-button z value="Reageer" (tak jak jest w DOM)
            const reageerInput = document.querySelector('input.reageer-button');
            if (reageerInput && reageerInput.value === 'Reageer') {
                reageerInput.click();
                return 'input.reageer-button';
            }

            // PRIORITET 2: Fallback — szukaj po value="Reageer" na wszystkich input[type=submit]
            const submits = document.querySelectorAll('input[type="submit"]');
            for (const inp of submits) {
                if (inp.value === 'Reageer') {
                    inp.click();
                    return 'input[type=submit]';
                }
            }

            // PRIORITET 3: Fallback — zds-button lub button z tekstem "Reageer"
            const allBtns = document.querySelectorAll('zds-button, button');
            for (const btn of allBtns) {
                const text = (btn.innerText || '').trim();
                if (text === 'Reageer') {
                    if (btn.shadowRoot) {
                        const inner = btn.shadowRoot.querySelector('button');
                        if (inner) { inner.click(); return 'zds-button-shadow'; }
                    }
                    btn.click();
                    return 'button';
                }
            }

            return null;
        """)

        if clicked:
            logging.info(f"    ✓ Kliknięto Reageer (typ: {clicked})")
            return True
        else:
            logging.warning(f"    ✗ Nie znaleziono przycisku Reageer")
            return False

    def close_reageer_modal(self):
        """
        Po kliknięciu Reageer pojawia się modal/popup z potwierdzeniem.
        Zamknij go — mogą być różne warianty:
          - zds-modal z zds-button[zds-modal-action=dismiss]
          - modal z przyciskiem X
          - colorbox (#colorbox)
        """
        time.sleep(2)

        closed = self.driver.execute_script("""
            // Wariant 1: zds-modal — kliknij dismiss button
            const zdsMod = document.querySelector('zds-modal');
            if (zdsMod && zdsMod.shadowRoot) {
                // zds-modal może mieć close button w shadowRoot
                const closeBtn = zdsMod.shadowRoot.querySelector('button[class*="close"], .zds-modal__close');
                if (closeBtn) { closeBtn.click(); return 'zds-modal-shadow-close'; }
            }
            // Dismiss button jako child zds-modal (w light DOM)
            const dismissBtns = document.querySelectorAll('zds-button[zds-modal-action="dismiss"]');
            for (const btn of dismissBtns) {
                const rect = btn.getBoundingClientRect();
                if (rect.height > 0) {
                    if (btn.shadowRoot) {
                        const inner = btn.shadowRoot.querySelector('button');
                        if (inner) { inner.click(); return 'dismiss-shadow'; }
                    }
                    btn.click();
                    return 'dismiss-direct';
                }
            }

            // Wariant 2: colorbox — zamknij
            const cbox = document.querySelector('#colorbox');
            if (cbox && cbox.style.display !== 'none') {
                const cboxClose = document.querySelector('#cboxClose');
                if (cboxClose) { cboxClose.click(); return 'colorbox'; }
                // Albo kliknij overlay
                const overlay = document.querySelector('#cboxOverlay');
                if (overlay) { overlay.click(); return 'colorbox-overlay'; }
            }

            // Wariant 3: jakikolwiek modal z role=dialog
            const dialogs = document.querySelectorAll('[role="dialog"]');
            for (const d of dialogs) {
                const rect = d.getBoundingClientRect();
                if (rect.height > 0 && d.tagName !== 'IFRAME') {
                    const closeBtn = d.querySelector('button[class*="close"], .close, [aria-label="close"]');
                    if (closeBtn) { closeBtn.click(); return 'dialog-close'; }
                }
            }

            return null;
        """)

        if closed:
            logging.info(f"    ✓ Modal zamknięty (typ: {closed})")
            time.sleep(1)
            return True
        else:
            logging.warning(f"    ⚠ Nie znaleziono modalu do zamknięcia (może nie było?)")
            return False

    def go_back_to_offers(self):
        """Wróć do listy ofert klikając link 'Overzicht'"""
        clicked = self.driver.execute_script("""
            const links = document.querySelectorAll('a');
            for (const a of links) {
                if (a.href && a.href.includes('aanbod/nu-te-huur/huurwoningen')
                    && !a.href.includes('/details/')) {
                    const rect = a.getBoundingClientRect();
                    if (rect.height > 0) {
                        a.click();
                        return true;
                    }
                }
            }
            return false;
        """)
        if clicked:
            logging.info("  ✓ Kliknięto 'Overzicht' — wracam do listy")
            time.sleep(10)  # Czekaj na Angular reload listy
        else:
            logging.info("  Cofam się via driver.back()")
            self.driver.back()
            time.sleep(10)

    # ----------------------------------------------------------
    # GŁÓWNA LOGIKA
    # ----------------------------------------------------------
    def process_offers(self):
        """
        Jeden cykl:
          1. Pobierz wszystkie URL ofert
          2. Filtruj te już zaaplikowane
          3. Dla każdej nowej: analyze → jeśli Loting + brak 55+ + dobry energielabel → Reageer
          4. Po Reageer zamknij modal, wróć do listy
        """
        all_urls = self.get_all_offer_urls()
        new_urls = [u for u in all_urls if u not in self.applied_offers]
        logging.info(f"  Nowych ofert do sprawdzenia: {len(new_urls)}")

        applied_count = 0
        for i, url in enumerate(new_urls, 1):
            logging.info(f"\n  --- Oferta {i}/{len(new_urls)} ---")

            info = self.analyze_offer(url)

            # Sprawdź czy już zaaplikowano (input.reageer-button = "Verwijder reactie")
            if info['already_applied']:
                logging.info(f"    POMIJAM — już zaaplikowano wcześniej")
                self.applied_offers.add(url)
                continue

            # Sprawdź kryteria
            if not info['is_loting']:
                logging.info(f"    POMIJAM — nie jest Loting")
                self.applied_offers.add(url)  # Pamiętaj żeby nie sprawdzać ponownie
                continue

            if info['has_age_restriction']:
                logging.info(f"    POMIJAM — ma ograniczenie wiekowe (55+/65+)")
                self.applied_offers.add(url)
                continue

            if info['energielabel'] is None:
                logging.info(f"    POMIJAM — brak Energielabel na stronie")
                self.applied_offers.add(url)
                continue

            if info['energielabel'] not in self.ALLOWED_ENERGIELABELS:
                logging.info(f"    POMIJAM — Energielabel {info['energielabel']} nie w dozwolonych {self.ALLOWED_ENERGIELABELS}")
                self.applied_offers.add(url)
                continue

            # Wszystkie kryteria spełnione!
            logging.info(f"    ✓✓ SPEŁNIA KRYTERIA — Loting, Energielabel {info['energielabel']}, brak 55+")

            # Kliknij Reageer
            if not self.click_reageer():
                logging.warning(f"    ✗ Nie udało się kliknąć Reageer")
                continue

            # Zamknij modal
            self.close_reageer_modal()

            # Zapamiętaj
            self.applied_offers.add(url)
            applied_count += 1
            logging.info(f"    ★★★ ZAAPLIKOWANO! ({url})")

            # Wróć do listy ofert
            self.go_back_to_offers()
            time.sleep(2)

        logging.info(f"\n  Cykl zakończony. Zaaplikowano: {applied_count}")
        return applied_count

    def run(self, check_interval=300):
        """
        Główna pętla bota.
        check_interval: sekundy między sprawdzeniami (domyślnie 5 minut)
        """
        try:
            self.setup_driver()

            if not self.login():
                logging.error("Nie udało się zalogować. Kończę.")
                return

            logging.info("✓✓✓ Bot uruchomiony pomyślnie! ✓✓✓")
            logging.info(f"Sprawdzanie co {check_interval} sek ({check_interval//60} min)")
            logging.info(f"Dozwolone Energielabels: {self.ALLOWED_ENERGIELABELS}")
            logging.info(f"Szuka tylko ofert z 'Loting', bez ograniczeń 55+/65+")

            iteration = 0
            while True:
                iteration += 1
                logging.info(f"\n{'='*60}")
                logging.info(f"ITERACJA #{iteration} — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                logging.info(f"{'='*60}")

                try:
                    self.process_offers()
                except Exception as e:
                    logging.error(f"Błąd w cyklu: {e}")
                    import traceback
                    traceback.print_exc()
                    # Spróbuj zalogować ponownie
                    try:
                        self.login()
                    except:
                        pass

                logging.info(f"\nCzekam {check_interval} sek... Następne sprawdzenie: {datetime.fromtimestamp(time.time() + check_interval).strftime('%H:%M:%S')}")
                time.sleep(check_interval)

        except KeyboardInterrupt:
            logging.info("\n✓ Bot zatrzymany (Ctrl+C)")
        finally:
            if self.driver:
                self.driver.quit()
                logging.info("Przeglądarka zamknięta")


def main():
    """Funkcja główna"""
    
    print("="*60)
    print("BOT DO MIESZKAŃ - KLIK VOOR WONEN")
    print("="*60)
    print()
    
    # KONFIGURACJA - WYPEŁNIJ SWOIMI DANYMI
    USERNAME = "twoj_login"  # Twój username na Klik voor Wonen
    PASSWORD = "twoje_haslo"  # Twoje hasło
    CHECK_INTERVAL = 300  # 5 minut w sekundach
    
    # Walidacja konfiguracji
    if USERNAME == "twoj_login" or PASSWORD == "twoje_haslo":
        print("❌ BŁĄD: Musisz wypełnić USERNAME i PASSWORD w pliku!")
        print()
        print("Edytuj plik housing_bot_klikvoorwonen.py i wprowadź swoje dane:")
        print(f'  USERNAME = "twoj_login"  ← Zmień to')
        print(f'  PASSWORD = "twoje_haslo"  ← Zmień to')
        print()
        input("Naciśnij Enter aby zakończyć...")
        return
    
    print(f"✓ Username: {USERNAME}")
    print(f"✓ Sprawdzanie co {CHECK_INTERVAL//60} minut")
    print(f"✓ Szukam mieszkań z Energielabel: A+++, A++, A+, A, B, C")
    print(f"✓ Tylko oferty z opcją: Loting (losowanie)")
    print(f"✓ Pomijam oferty z ograniczeniem 55+/65+")
    print()
    print("Uruchamiam bota...")
    print("Naciśnij Ctrl+C aby zatrzymać")
    print("="*60)
    print()
    
    # Uruchom bota
    bot = KlikVoorWonenBot(USERNAME, PASSWORD)
    bot.run(check_interval=CHECK_INTERVAL)


if __name__ == "__main__":
    main()
