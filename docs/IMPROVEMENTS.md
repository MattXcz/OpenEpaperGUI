# Návrhy vylepšení — otevřené body

Hotové body (P0, P1, revalidace N1–N7, backend drobnosti, anchor, autosave,
potvrzení mazání, a11y) jsou odstraněné. Zůstává jen to, co ještě není
uděláno.

---

## Bezpečnost

* Volitelný `APP_TOKEN` (jednoduchá autentizace) a/nebo podpora Home Assistant
  ingress, pokud z toho má být add-on. Aplikace pořád nemá žádné přihlášení —
  kdokoli v LAN může číst/mazat projekty a posílat na displeje.

---

## Generátor

### Uvozovka, která vznikne až za runtime [částečně pokryto validací]

`POST /api/validate` takový template odhalí (render → `json.loads` → parse
stage), ale staticky se ošetřit nedá: `| tojson` by u výrazů vracejících číslo
změnil typ a rozbilo `drawcustom`. Zbývá jen případné zlepšení hlášky.

---

## Funkce

### Undo/redo
Pro editor absolutní jednička. Stav je čistý JSON strom, takže stack snapshotů
+ `Cmd+Z`/`Cmd+Shift+Z` je otázka ~30 řádků.

### Autocomplete entit — kód už existuje, ale nikdo ho nevolá
`GET /api/ha/entities` je implementovaný a `api.haEntities()` je v
[api.js](../frontend/js/api.js) exportovaný, ale ve frontendu se nikde
nepoužívá. Napojit ho na textová pole a na výběr entity v plot editoru.

### Pixel-perfect preview
Hotovo (`app/render/`, `POST /api/preview`). Zbývá:

* `plot` kreslí jen rám a osy — data by šla dotáhnout z HA
  `/api/history/period` a dokreslit skutečné křivky.
* `dlimg` s remote URL kreslí placeholder; šlo by stáhnout a vykreslit.
* Preview je jen v modalu; mohlo by být i jako vrstva nad canvasem.

### Další
* **Import projektu** — export existuje, import ne. S ním galerie layoutů od
  komunity (sdílení jednoho JSON souboru). Pozor: importovaná data pak jdou do
  `innerHTML` a `<img src>` — před tím projít escapování.
* **Multi-select** na canvasu + zarovnání/rozprostření a snap na hrany
  ostatních elementů.
* **Pointer events** místo `mousedown`/`mousemove` → funguje to i na tabletu.
* MDI font **vendorovat** místo CDN (offline fallback je degradovaný).
* Přejmenování a duplikace projektu.
* Jen 3 šablony v presetech. Přidat sadu pro 4.2" a 7.5".

---

## Hygiena a architektura

* **CI nasazeno** (`.github/workflows/ci.yml`): backend (ruff + pytest),
  frontend (syntax + kontrola relativních importů), docker build. Lint je
  připnutý v `backend/ruff.toml`.
* **Testy** — pytest nasazen (108 testů). Zbývá property test „libovolný
  projekt → template → renderuje se → validní JSON" (hypothesis). Frontend
  testy nula, přitom `geometry.js` jsou čisté funkce ideální na `node:test`.
* **Docker** — kontejner běží jako root. Non-root uživatel potřebuje
  entrypoint, který opraví vlastnictví `/data` (stávající volumes vlastní
  root). Base image je 3.12, dev venv 3.14 — sjednotit.
* **Předpřipravený image na ghcr.io** + HA add-on manifest.
* **Fonty pro preview** se stahují při Docker buildu a nejsou v repu. Kdo
  vyvíjí bez Dockeru, musí spustit `backend/scripts/fetch_assets.py`.
* `render()` přestavuje celý DOM (`innerHTML = ''`) při každém `mousemove`
  během tažení. Během dragu stačí měnit `style` taženého elementu.
* Preview hodnoty se mutují na node jako `__display`/`__resolvedProps` a pak se
  zase mažou. Čistší je samostatná `Map` podle `id`.
* `geometry.js` používá `Function()` na vyhodnocení výrazů (za whitelistem
  identifikátorů). Malý vlastní parser by to riziko odstranil a umožnil
  podporovat i závorky, `|int` a `loop.index`.

---

## Co je na projektu dobré

* `schema.py` jako jeden zdroj pravdy pro inspektor, geometrii i generátor.
* Pravidlo „optional property se emituje jen když se liší od defaultu" —
  výstup je krátký jako ručně psaný template.
* Poctivost dokumentace: README samo píše, že canvas je aproximace a co
  preview neumí (plot bez dat, remote obrázky).
* Vyhodnocování `{{ }}` výrazů v preview s loop proměnnou na první iteraci
  a explicitní označení nevyhodnotitelných elementů jako `dynamic`.
* Celá appka je jeden kontejner na jednom portu, žádný build step na frontendu.
* Pixel-perfect preview se ověřuje testy nad skutečnými pixely, ne nad
  „nespadlo to" — barvy, souřadnice, rotace, izolace chyby jednoho elementu.
* Fonty se ověřují velikostí i git blob SHA-1, takže posunutý tag nebo
  podvržené zrcadlo shodí build místo toho, aby se tiše vykreslily špatné
  glyfy.
* `theme.js` sjednotil barvy a glyfy, `geometry.js` bere metriky textu ze
  `schema.py` — jeden zdroj pravdy i pro frontend.
