# Adding Custom Sprite Sheets

CLI Avatars uses the **Stream Avatars row convention** — the same format used by the popular Twitch streaming app. Any sprite sheet in this format works out of the box.

---

## Sprite Sheet Format

Each row of the sheet is one animation. Each column in that row is one frame.

```
┌──────┬──────┬──────┬──────┐  ← Row 0: IDLE
│ fr 0 │ fr 1 │ fr 2 │      │    (trailing blank cells are auto-skipped)
├──────┼──────┼──────┼──────┤
│ fr 0 │ fr 1 │ fr 2 │ fr 3 │  ← Row 1: RUN / WALK
├──────┼──────┼──────┼──────┤
│ fr 0 │ fr 1 │      │      │  ← Row 2: SIT
├──────┼──────┼──────┼──────┤
│ fr 0 │ fr 1 │ fr 2 │      │  ← Row 3: STAND
├──────┼──────┼──────┼──────┤
│ fr 0 │ fr 1 │ fr 2 │ fr 3 │  ← Row 4: JUMP
└──────┴──────┴──────┴──────┘
```

| Row | Animation name | When the overlay uses it |
|-----|---------------|--------------------------|
| 0 | idle | Agent is waiting between turns |
| 1 | run / walk | Agent is using a tool (busy) |
| 2 | sit | Agent is thinking / generating a response |
| 3 | stand | Turn complete / error |
| 4 | jump | Sub-agent is active |
| 5+ | custom | Not currently mapped — safe to include |

### Requirements

- **Format:** PNG with transparency (RGBA). JPEG is not supported (no alpha channel).
- **Cell size:** All cells must be the same width and height. Common sizes: 32×32, 40×40, 48×48, 60×60.
- **Cell height:** Can differ from width — e.g. `meowatar` uses 60 wide × 50 tall cells.
- **Background:** Must be transparent. Solid white/colored backgrounds will render as a colored box on screen.

---

## Adding a Sheet in 3 Steps

### Step 1 — Place the PNG in `Sprites/`

```
cli-avatars/
└── Sprites/
    └── MyCharacter.png   ← put it here
```

### Step 2 — Register it in `overlay.py`

Open `overlay.py` and find the `_load_sprites()` method. Add one line to the `sheets` list:

```python
sheets = [
    ("meowatar",  "meowatar.png",  60, 50),
    ("michimaru", "Michimaru.png", 40, 51),
    ("ponmi",     "ponmi.png",     48, 48),
    ("mychar",    "MyCharacter.png", 48, 48),   # ← add this
]
```

The four values are: `(name, filename, frame_width, frame_height)`.

- `name` — the identifier used in the skin picker. Use lowercase, no spaces.
- `filename` — exact filename inside `Sprites/`, including capitalisation.
- `frame_width` — width of one cell in pixels (before scaling).
- `frame_height` — height of one cell in pixels. Set to the same as `frame_width` if cells are square.

### Step 3 — Restart

```bash
python overlay.py
```

Open the skin picker (right-click → **Skins**). Your skin appears in the list.

---

## Inspecting a Sheet

Not sure of the cell size? Use the built-in info command:

```bash
python sprite_loader.py info Sprites/MyCharacter.png 48 48
```

Output:

```
SpriteSheet 'MyCharacter.png'
  Image   : 192x240 px
  Cell    : 48x48 px  (scale=1.0x)
  Grid    : 4 cols x 5 rows
  Animations:
    row 0  [idle    ]  2 frame(s)
    row 1  [run     ]  4 frame(s)
    row 2  [sit     ]  2 frame(s)
    row 3  [stand   ]  3 frame(s)
    row 4  [jump    ]  3 frame(s)
```

Try different cell sizes if the layout looks wrong (the frame count per row should match your sheet's design).

---

## Converting from JPEG

If you only have a JPEG source, convert it first — but note that you will still need to manually remove the background in an image editor (GIMP, Aseprite, Photoshop) since JPEG has no transparency:

```bash
python sprite_loader.py convert source.jpg Sprites/MyCharacter.png
```

This creates a PNG with all pixels fully opaque (alpha = 255). Open the PNG in an editor and remove the background before using it.

---

## Hue Shifting

The skin picker includes a **hue slider** that rotates all colors of the sprite sheet without modifying the file. This means one sprite sheet can produce many color variants — assign different hues to different agents.

Hue shifting requires `numpy`:

```bash
pip install numpy
```

Without numpy, the overlay still runs but hue shifting is skipped.

---

## Creating Sheets from Scratch

Recommended tools:
- **[Aseprite](https://www.aseprite.org/)** — dedicated pixel art + animation tool. Export sprite sheets directly. Set canvas to your cell size (e.g. 48×48), animate each row, then File → Export Sprite Sheet with horizontal strip layout.
- **GIMP** — free alternative. Use Filters → Animation for frames.
- **Libresprite** — free fork of an older Aseprite version.

The minimum viable sheet is just Row 0 (idle) with 1–2 frames. All other rows are optional — the overlay falls back to row 0 if a row is missing.
