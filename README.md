# Housing Bot — Klik voor Wonen

Bot do automatycznego monitorowania i aplikowania na mieszkania socjalne na [klikvoorwonen.nl](https://www.klikvoorwonen.nl).

## Co robi

- Sprawdza listę ogłoszeń co kilka minut
- Filtruje oferty według kryteria:
  - ✅ Tylko **Loting** (losowanie)
  - ✅ Energielabel: **A+++, A++, A+, A, B, C**
  - ❌ Pomija oferty z ograniczeniem **55+ / 65+**
  - ❌ Pomija oferty na które **już zaaplikowano**
- Automatycznie klikuje „Reageer" na kwalifikujących się ofertach

## Wymagania

- **Python 3.8+** — [pobierz tutaj](https://www.python.org/downloads/)
- **Google Chrome** — zainstalowany na systemie
- ChromeDriver jest pobierany automatycznie przez `webdriver-manager`

## Instalacja

**1. Sklonuj repozytoria:**

```bash
git clone https://github.com/TWOJA_NAZWA/housing-bot-klikvoorwonen.git
cd housing-bot-klikvoorwonen
```

**2. Zainstalluj zależności:**

```bash
pip install -r requirements.txt
```

## Konfiguracja

Otwórz `housing_bot_klikvoorwonen.py` i wypełnij swoje dane w funkcji `main()`:

```python
USERNAME = "twoj_login"   # ← zmień na swój
PASSWORD = "twoje_haslo"  # ← zmień na swoje
CHECK_INTERVAL = 300      # co 5 minut (w sekundach)
```

> ⚠️ **Nigdy nie wrzucaj pliku z prawdziwymi danymi na GitHub!** Wypełnij USERNAME i PASSWORD tylko lokalnie.

## Uruchomienie

```bash
python housing_bot_klikvoorwonen.py
```

Bot otwierka okno Chrome, loguje się i zaczyna monitorować oferty. Wszystko loguje do `housing_bot.log`.

Zatrzymaj bot: **Ctrl+C**

## Struktura projektu

```
housing-bot-klikvoorwonen/
├── housing_bot_klikvoorwonen.py   # główny skrypt bota
├── requirements.txt               # zależności Python
├── .gitignore
└── README.md
```
