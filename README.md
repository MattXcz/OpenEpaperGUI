# OpenEPaper GUI

A self-hosted, browser-based **drag & drop editor** that generates
[`drawcustom`](https://github.com/OpenEPaperLink/Home_Assistant_Integration/blob/main/docs/drawcustom/supported_types.md)
payloads for the [OpenEPaperLink](https://github.com/OpenEPaperLink/Home_Assistant_Integration)
Home Assistant integration — a visual builder for e-paper displays, similar in
spirit to Elementor.

You design a layout on a pixel-accurate canvas, and the app emits the Jinja
template that Home Assistant expects. No YAML or Jinja is written by hand.

```jinja
{% set spacing = 49 %}

[
  {
    "type": "text",
    "value": " ",
    "x": 0,
    "y": 0,
    "size": 1,
    "color": "yellow"
  }
  {% for i in range(8) %}
    ,{
      "type": "text",
      "value": "{{ times[i] }}",
      "x": {{ 15 + i*spacing }},
      "y": 5,
      "size": 10
    }
    ,{
      "type": "icon",
      "value": "{{ icon_map.get(forecast[i].condition,'mdi:emoticon-happy') }}",
      "x": {{ 5 + i*spacing }},
      "y": 10,
      "size": 50
    }
  {% endfor %}
]
```

---

## Quick start

```bash
git clone <this-repo> openepaper-gui
cd openepaper-gui

cp .env.example .env
# edit .env: set HA_URL and HA_TOKEN

docker compose up -d --build
```

Open **http://localhost:8099** (or whatever `APP_PORT` you set).

```bash
docker compose logs -f        # follow logs
docker compose down           # stop
docker compose down -v        # stop and wipe saved projects
```

### Development (hot reload)

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

The `backend/app` and `frontend` folders are bind-mounted, and uvicorn runs with
`--reload`.

---

## Configuration

Everything can be configured in the UI under **⚙️ Settings**, or via environment
variables in `.env`:

| Variable | Default | Description |
| --- | --- | --- |
| `APP_PORT` | `8099` | Host port the editor is served on |
| `HA_URL` | `http://homeassistant.local:8123` | Home Assistant base URL |
| `HA_TOKEN` | – | Long-lived access token |
| `LOG_LEVEL` | `info` | uvicorn log level |
| `DATA_DIR` | `/data` | Where projects and settings are stored |

Create a token in Home Assistant under **Profile → Security → Long-lived access
tokens**. Values saved in the UI take precedence over environment variables,
except that the environment token is used when none is saved.

---

## Using the editor

### Canvas

| Action | How |
| --- | --- |
| Add element | Drag from the left palette onto the canvas, or double-click it |
| Select | Click the element |
| Move | Drag it, or use the arrow keys (`Shift` = 10 px steps) |
| Resize | Drag the corner / edge handles |
| Duplicate | `Ctrl`/`Cmd` + `D` |
| Delete | `Delete` / `Backspace` |
| Centre horizontally | `C` |
| Deselect | `Esc` |

Toggle **Grid** and **Snap** in the toolbar. **Preview** hides the selection
chrome so you see the design as it will render.

### Display resolution

Pick a preset (2.9", 2.13", 4.2", 7.5" …) or enter a custom width/height. The
canvas resizes immediately and coordinates are always in display pixels, so the
generated payload matches the target panel.

### Element types

All types from the `drawcustom` documentation are supported:

| Category | Types |
| --- | --- |
| Content | `text`, `multiline`, `icon`, `icon_sequence`, `qrcode`, `dlimg` |
| Shapes | `line`, `rectangle`, `rectangle_pattern`, `polygon`, `circle`, `ellipse`, `arc` |
| Data | `progress_bar`, `plot` |
| Utility | `debug_grid` |

Every documented property is exposed in the Inspector, grouped into
**Content / Position / Style / Advanced**.

### Home Assistant templates

Any text or number field accepts Jinja. Type `{{ states('sensor.temp') }}` into
a value and it is emitted verbatim (unquoted) so Home Assistant evaluates it at
render time. Fields containing `{{` or `{%` are tagged with a **jinja** badge.

### Variables

The **Variables** tab emits project-level `{% set %}` statements:

```
spacing  = 49
temp     = states('sensor.living_room_temperature')
```

Then reference them anywhere, e.g. `{{ 15 + i*spacing }}`.

### Repeat groups (loops)

A **Repeat group** wraps its children in a `{% for %}` loop — this is how the
8-column forecast example is built.

1. Add a **Repeat group** from the palette (under *Structure*).
2. Drag the elements that should repeat onto the canvas.
3. Select the group and set the **loop variable** (`i`), **iterations** (`8`)
   and any **pre-loop statements** (e.g. `offsets = [offset_0, offset_1, ...]`).
4. Use `i` in child fields: `{{ 15 + i*spacing }}`.

The generator handles comma placement so the output is always valid JSON: a
group that is the first element emits `{% if not loop.first %},{% endif %}`
instead of a leading comma.

### Exporting

The **Code** tab shows the live output as **Jinja**, **YAML** or **JSON**.
**⬇️ Export** downloads the template as a `.jinja` file. **Copy template**
puts it on the clipboard for pasting into a script, automation or template
sensor.

### Sending to a display

**📤 Send to display** calls the configured Home Assistant service (default
`open_epaper_link.drawcustom`) with the rendered template as `payload`:

```yaml
service: open_epaper_link.drawcustom
data:
  device_id: "0011223344556677"
  payload: "{{ <generated template> }}"
  background: white
```

Enable **Dry run** to have Home Assistant render the image without pushing it to
the tag.

---

## Architecture

```
.
├── docker-compose.yml          # production stack
├── docker-compose.dev.yml      # dev override (bind mounts + reload)
├── .env.example
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py             # FastAPI app + static hosting
│       ├── schema.py           # single source of truth for element types
│       ├── generator.py        # visual model -> Jinja / YAML / JSON
│       ├── storage.py          # JSON-file project storage
│       ├── ha_client.py        # Home Assistant REST client
│       └── test_generator.py   # generator tests
└── frontend/
    ├── index.html
    ├── css/styles.css
    └── js/
        ├── app.js              # entry point, wiring
        ├── api.js              # REST client
        ├── state.js            # state store + node helpers
        ├── canvas.js           # drag & drop, move, resize
        ├── geometry.js         # bounding boxes per element type
        ├── renderer.js         # on-canvas previews
        ├── inspector.js        # schema-driven property editor
        ├── layers.js           # layer tree
        ├── variables.js        # {% set %} editor
        ├── code.js             # generated output panel
        ├── presets.js          # starter templates
        └── modals.js           # projects / settings / export / push
```

The backend serves the static frontend, so the whole app is a single container
on a single port.

`schema.py` drives three things at once: the Inspector UI, the canvas geometry
and the generator. Adding a new draw type means adding one entry there.

### Generation rules

* Required properties are always emitted.
* Optional properties are emitted only when they differ from the documented
  default — so the output stays as short as a hand-written template.
* Values containing `{{` / `{%` are emitted unquoted so Jinja evaluates them.
* Properties whose documented default is `null` are omitted unless explicitly
  set.

---

## Tests

```bash
cd backend
python -m app.test_generator
```

The suite renders generated templates with a real Jinja environment and asserts
the result is valid JSON — covering the weather example, groups in first
position, hidden elements, numeric types and shapes.

---

## API reference

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/health` | Health check |
| `GET` | `/api/schema` | Element type schema |
| `GET` | `/api/projects` | List saved projects |
| `GET` | `/api/projects/{id}` | Load a project |
| `POST` | `/api/projects` | Create a project |
| `PUT` | `/api/projects/{id}` | Update a project |
| `DELETE` | `/api/projects/{id}` | Delete a project |
| `POST` | `/api/generate/template` | Generate Jinja / YAML / JSON |
| `GET` | `/api/settings` | Read settings (token redacted) |
| `POST` | `/api/settings` | Save settings |
| `GET` | `/api/ha/status` | Test the Home Assistant connection |
| `GET` | `/api/ha/entities` | List entities (optional `?domain=`) |
| `POST` | `/api/ha/push` | Render and send to a display |

Interactive docs are available at `/docs`.

---

## Notes & limitations

* Projects are stored as JSON files in the `epaper-gui-data` volume. Back it up
  if you care about the layouts.
* The canvas is a **design-time approximation**. Home Assistant and Pillow do
  the real rendering, so exact font metrics and icon glyphs can differ slightly.
  Use **Send to display → Dry run** to check the true result.
* Icons in the editor use the MDI webfont from a CDN. Offline, elements fall
  back to a labelled placeholder — the generated payload is unaffected.
* The QR preview is a placeholder; the real code is generated by Home Assistant.
