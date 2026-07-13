# Vlastní RSS pro vybrané ACS časopisy

Projekt každé 3 hodiny načte nová DOI metadata z Crossref a vytvoří standardní RSS 2.0. Nespoléhá na neaktualizující se RSS kanály ACS ani na parsování webových stránek.

## Zahrnuté časopisy

- Journal of Medicinal Chemistry
- ACS Infectious Diseases
- ACS Medicinal Chemistry Letters
- ACS Bio & Med Chem Au
- společný kanál se všemi čtyřmi

## Zprovoznění na GitHubu

1. Vytvoř nový veřejný repozitář, například `acs-rss`.
2. Nahraj do něj celý obsah této složky a nastav větev `main`.
3. V repozitáři otevři **Settings → Pages**.
4. U položky **Build and deployment → Source** vyber **GitHub Actions**.
5. Otevři záložku **Actions**, workflow **Update RSS feeds** a spusť **Run workflow**. Workflow se pak spustí automaticky každé 3 hodiny.

Při uživatelském jménu `novak` a názvu repozitáře `acs-rss` budou adresy:

```text
https://novak.github.io/acs-rss/jmedchem.xml
https://novak.github.io/acs-rss/acs-infectious-diseases.xml
https://novak.github.io/acs-rss/acs-medicinal-chemistry-letters.xml
https://novak.github.io/acs-rss/acs-bio-med-chem-au.xml
https://novak.github.io/acs-rss/all-acs-medchem.xml
```

Tyto adresy vlož přímo do Inoreaderu nebo The Old Readeru.

## Lokální test

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
FEED_BASE_URL=http://localhost python src/generate_feeds.py
```

Vygenerované soubory budou v `docs/`.

## Přidání dalšího časopisu

Doplň položku do `journals.json`. Potřebuješ název, slug, ISSN a domovskou stránku. ISSN je vhodnější použít elektronické, pokud ho časopis má.

## Poznámky

- Zdroj metadat je Crossref, takže nový článek se objeví poté, co ACS metadata u Crossrefu uloží nebo aktualizuje.
- Kanál odkazuje přes DOI na ACS stránku článku.
- Projekt neobchází paywall a neposkytuje plné texty.
- Workflow skončí chybou, když se některý kanál nepodaří načíst; ostatní XML soubory se přesto vygenerují, ale GitHub Pages se při chybě nenasadí. To brání nahrazení funkčních feedů neúplnou sadou.
