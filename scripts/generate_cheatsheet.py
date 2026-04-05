#!/usr/bin/env python3
"""
roBa keymap cheatsheet generator
Parses a ZMK .keymap file (keymap-editor format) and generates an HTML cheatsheet.
Usage: python generate_cheatsheet.py <input.keymap> <output.html>
"""

import re
import sys
import json
from pathlib import Path
from datetime import datetime

# ---------------------------------------------------------------------------
# roBa physical layout (42 keys)
# Index order matches ZMK bindings left-to-right, top-to-bottom
# Each row: (key_index, col_span_class)
# ---------------------------------------------------------------------------
LAYOUT = {
    # roBa 43キー実態マッピング (keymap-editor形式)
    # bindingsはフラットリストで、サムキーが各行末に混在する
    #
    # [0-9]   上段 (左5 + 右5)
    # [10-14] 中段左5
    # [15-16] 中段サムL x2  ← 行末に混在
    # [17-21] 中段右5
    # [22-26] 下段左5
    # [27-28] 下段サムL x2  ← 行末に混在
    # [29-33] 下段右5
    # [34-42] サムクラスター残り9キー
    "row0": {"left": list(range(0, 5)),   "right": list(range(5, 10))},
    "row1": {"left": list(range(10, 15)), "thumb": [15, 16], "right": list(range(17, 22))},
    "row2": {"left": list(range(22, 27)), "thumb": [27, 28], "right": list(range(29, 34))},
    "thumb_row": list(range(34, 43)),
    # エンコーダーは sensor-bindings で別管理 → bindingsには含まれない
}

# ---------------------------------------------------------------------------
# Key label mapping
# ---------------------------------------------------------------------------
KEY_LABELS = {
    "SPACE": "SPC", "ENTER": "↵", "RETURN": "↵", "BSPC": "⌫", "DEL": "DEL",
    "TAB": "⇥", "ESC": "ESC", "GRAVE": "`", "TILDE": "~",
    "LSHIFT": "⇧", "RSHIFT": "⇧", "LCTRL": "Ctrl", "RCTRL": "Ctrl",
    "LALT": "Alt", "RALT": "Alt", "LGUI": "⌘", "RGUI": "⌘",
    "LMETA": "⌘", "RMETA": "⌘",
    "LEFT": "←", "RIGHT": "→", "UP": "↑", "DOWN": "↓",
    "HOME": "Home", "END": "End", "PG_UP": "PgUp", "PG_DN": "PgDn",
    "SEMI": ";", "COLON": ":", "SQT": "'", "DQT": '"',
    "COMMA": ",", "DOT": ".", "SLASH": "/", "FSLH": "/",
    "BSLH": "\\", "PIPE": "|", "MINUS": "-", "PLUS": "+", "EQUAL": "=",
    "LBKT": "[", "RBKT": "]", "LBRC": "{", "RBRC": "}",
    "LPAR": "(", "RPAR": ")", "LT": "<", "GT": ">",
    "EXCL": "!", "AT": "@", "HASH": "#", "DLLR": "$",
    "PRCNT": "%", "CARET": "^", "AMPS": "&", "STAR": "*",
    "UNDER": "_", "QMARK": "?",
    "N0": "0", "N1": "1", "N2": "2", "N3": "3", "N4": "4",
    "N5": "5", "N6": "6", "N7": "7", "N8": "8", "N9": "9",
    **{f"F{i}": f"F{i}" for i in range(1, 13)},
    "C_VOL_UP": "Vol+", "C_VOL_DN": "Vol-", "C_MUTE": "Mute",
    "C_PP": "⏯", "C_NEXT": "⏭", "C_PREV": "⏮",
    "PRINTSCREEN": "PrtSc", "CAPSLOCK": "Caps", "INS": "Ins",
    "KP_ENTER": "KP↵", "KP_DOT": "KP.", "KP_PLUS": "KP+",
    "KP_MINUS": "KP-", "KP_MULTIPLY": "KP*", "KP_DIVIDE": "KP/",
    **{f"KP_N{i}": str(i) for i in range(10)},
}

def fmt_label(s: str) -> str:
    s = s.strip().upper()
    if s in KEY_LABELS:
        return KEY_LABELS[s]
    if len(s) == 1:
        return s
    return s[:7] + "…" if len(s) > 7 else s

def fmt_bt(raw: str) -> tuple[str, str]:
    if "CLR_ALL" in raw:
        return "BT CLR ALL", "special"
    if "CLR" in raw:
        return "BT CLR", "special"
    m = re.search(r"BT_SEL\s+(\d+)", raw)
    if m:
        return f"BT {m.group(1)}", "special"
    return "BT", "special"

def parse_binding(raw: str) -> dict:
    """Return {label, hold, cls} for a single binding token."""
    r = raw.strip()

    if r == "&trans":
        return {"label": "▽", "hold": "", "cls": "trans"}
    if r == "&none":
        return {"label": "✕", "hold": "", "cls": "trans"}
    if r == "&gresc":
        return {"label": "ESC/~", "hold": "", "cls": "special"}
    if r.startswith("&bootloader"):
        return {"label": "BOOT", "hold": "", "cls": "special"}
    if r.startswith("&reset") or r.startswith("&sys_reset"):
        return {"label": "RST", "hold": "", "cls": "special"}

    # Layer-tap  &lt <layer> <key>
    m = re.match(r"&lt\s+(\d+)\s+(.+)$", r)
    if m:
        return {"label": fmt_label(m.group(2)), "hold": f"L{m.group(1)}", "cls": "layer"}

    # Mod-tap  &mt <mod> <key>
    m = re.match(r"&mt\s+(\S+)\s+(.+)$", r)
    if m:
        return {"label": fmt_label(m.group(2)), "hold": fmt_label(m.group(1)), "cls": ""}

    # Hold-tap custom  &ht <hold> <tap>
    m = re.match(r"&ht\s+(\S+)\s+(.+)$", r)
    if m:
        return {"label": fmt_label(m.group(2)), "hold": fmt_label(m.group(1)), "cls": ""}

    # Momentary layer  &mo <n>
    m = re.match(r"&mo\s+(\d+)$", r)
    if m:
        return {"label": f"Mo{m.group(1)}", "hold": "", "cls": "layer"}

    # To layer  &to <n>
    m = re.match(r"&to\s+(\d+)$", r)
    if m:
        return {"label": f"To{m.group(1)}", "hold": "", "cls": "layer"}

    # Sticky key  &sk
    m = re.match(r"&sk\s+(.+)$", r)
    if m:
        return {"label": "sk:" + fmt_label(m.group(1)), "hold": "", "cls": "special"}

    # Bluetooth
    if r.startswith("&bt "):
        lbl, cls = fmt_bt(r)
        return {"label": lbl, "hold": "", "cls": cls}

    # Output select
    if r.startswith("&out "):
        lbl = "USB" if "USB" in r else "BLE"
        return {"label": lbl, "hold": "", "cls": "special"}

    # Regular keypress  &kp <key>
    m = re.match(r"&kp\s+(.+)$", r)
    if m:
        return {"label": fmt_label(m.group(1)), "hold": "", "cls": ""}

    # Fallback: strip & and show behavior name
    m = re.match(r"&(\S+)", r)
    if m:
        name = m.group(1)
        return {"label": name[:7], "hold": "", "cls": "special"}

    return {"label": r[:7], "hold": "", "cls": ""}


def tokenize_bindings(bindings_text: str) -> list[str]:
    """
    Split bindings block into individual binding tokens.
    Each token starts with & and may contain multiple whitespace-separated parts.
    Handles multi-word behaviors like &lt 1 SPACE, &mt LSHIFT A, etc.
    """
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', bindings_text).strip()
    tokens = []
    parts = text.split('&')
    for part in parts:
        part = part.strip()
        if not part:
            continue
        tokens.append('&' + part.rstrip())
    return tokens


def parse_keymap(text: str) -> list[dict]:
    """Extract all layers from a ZMK .keymap file."""
    layers = []

    # Match each layer block: <name> { ... bindings = <...>; ... }
    # We look inside the keymap { } block
    keymap_m = re.search(r'keymap\s*\{([\s\S]*?)\};\s*\};', text)
    src = keymap_m.group(1) if keymap_m else text

    layer_re = re.compile(
        r'([A-Za-z0-9_]+)\s*\{[^{}]*?bindings\s*=\s*<([\s\S]*?)>;',
        re.MULTILINE
    )

    skip = {"keymap", "behaviors", "combos", "macros", "conditional_layers"}

    for m in layer_re.finditer(src):
        name = m.group(1)
        if name in skip:
            continue
        raw_bindings = m.group(2)
        tokens = tokenize_bindings(raw_bindings)
        keys = [parse_binding(t) for t in tokens]
        layers.append({"name": name, "keys": keys})

    return layers


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------

def key_html(k: dict) -> str:
    cls = "key"
    if k["cls"] == "trans":
        cls += " key-trans"
    elif k["cls"] == "layer":
        cls += " key-layer"
    elif k["cls"] == "special":
        cls += " key-special"

    hold_html = f'<span class="hold">{k["hold"]}</span>' if k["hold"] else ""
    return f'<div class="{cls}">{k["label"]}{hold_html}</div>'


def render_layer(layer: dict, idx: int) -> str:
    keys = layer["keys"]

    def g(i):
        return keys[i] if i < len(keys) else {"label": "", "hold": "", "cls": ""}

    rows_html = ""

    # 上段 (インデックス 0-9)
    rows_html += '<div class="kb-row">'
    for i in LAYOUT["row0"]["left"]:
        rows_html += key_html(g(i))
    rows_html += '<div class="gap"></div>'
    for i in LAYOUT["row0"]["right"]:
        rows_html += key_html(g(i))
    rows_html += '</div>\n'

    # 中段: 左5 + サムL2(行末混在) | 右5
    rows_html += '<div class="kb-row">'
    for i in LAYOUT["row1"]["left"]:
        rows_html += key_html(g(i))
    for i in LAYOUT["row1"]["thumb"]:
        rows_html += key_html(g(i))
    rows_html += '<div class="gap"></div>'
    for i in LAYOUT["row1"]["right"]:
        rows_html += key_html(g(i))
    rows_html += '</div>\n'

    # 下段: 左5 + サムL2(行末混在) | 右5
    rows_html += '<div class="kb-row">'
    for i in LAYOUT["row2"]["left"]:
        rows_html += key_html(g(i))
    for i in LAYOUT["row2"]["thumb"]:
        rows_html += key_html(g(i))
    rows_html += '<div class="gap"></div>'
    for i in LAYOUT["row2"]["right"]:
        rows_html += key_html(g(i))
    rows_html += '</div>\n'

    # サムクラスター行 (インデックス 34-42)
    rows_html += '<div class="split-label">thumb cluster</div>\n'
    rows_html += '<div class="kb-row">'
    for i in LAYOUT["thumb_row"]:
        rows_html += key_html(g(i))
    rows_html += '</div>\n'

    # エンコーダーは sensor-bindings で別管理 (bindingsには含まれない)
    rows_html += '<div class="split-label" style="margin-top:4px;opacity:0.5">encoder: sensor-bindings</div>\n'

    return f'''
<section class="layer" id="layer-{idx}">
  <h2 class="layer-title">Layer {idx} <span class="layer-name">{layer["name"]}</span></h2>
  <div class="keyboard">
{rows_html}  </div>
</section>
'''


def generate_html(layers: list[dict], source_path: str = "") -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    nav_items = "".join(
        f'<a href="#layer-{i}" class="nav-item">L{i}: {l["name"]}</a>'
        for i, l in enumerate(layers)
    )
    layers_html = "".join(render_layer(l, i) for i, l in enumerate(layers))
    source_note = f'<span class="source">source: {source_path}</span>' if source_path else ""

    return f'''<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>roBa keymap cheatsheet</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

  :root {{
    --bg: #ffffff;
    --bg2: #f5f5f4;
    --border: rgba(0,0,0,0.12);
    --border2: rgba(0,0,0,0.22);
    --text: #1c1c1a;
    --text2: #6b6b67;
    --blue-bg: #dbeafe;
    --blue-fg: #1e40af;
    --amber-bg: #fef3c7;
    --amber-fg: #92400e;
    --radius: 7px;
    --key-w: 44px;
    --key-h: 40px;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #1e1e1c;
      --bg2: #2a2a28;
      --border: rgba(255,255,255,0.1);
      --border2: rgba(255,255,255,0.2);
      --text: #e8e6e0;
      --text2: #9a9893;
      --blue-bg: #1e3a5f;
      --blue-fg: #93c5fd;
      --amber-bg: #451a03;
      --amber-fg: #fcd34d;
    }}
  }}

  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: var(--bg);
    color: var(--text);
    padding: 24px 20px 48px;
    max-width: 780px;
    margin: 0 auto;
  }}

  header {{
    margin-bottom: 24px;
    border-bottom: 0.5px solid var(--border2);
    padding-bottom: 16px;
  }}
  header h1 {{ font-size: 20px; font-weight: 500; margin-bottom: 4px; }}
  .meta {{ font-size: 12px; color: var(--text2); display: flex; gap: 16px; flex-wrap: wrap; }}

  nav {{
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-bottom: 28px;
  }}
  .nav-item {{
    font-size: 12px;
    padding: 4px 12px;
    border-radius: var(--radius);
    border: 0.5px solid var(--border2);
    color: var(--text2);
    text-decoration: none;
  }}
  .nav-item:hover {{ background: var(--bg2); color: var(--text); }}

  .layer {{ margin-bottom: 36px; }}
  .layer-title {{
    font-size: 15px;
    font-weight: 500;
    margin-bottom: 12px;
    display: flex;
    align-items: center;
    gap: 8px;
  }}
  .layer-name {{
    font-size: 12px;
    font-weight: 400;
    color: var(--text2);
    background: var(--bg2);
    padding: 2px 8px;
    border-radius: 99px;
    border: 0.5px solid var(--border);
  }}

  .keyboard {{ display: flex; flex-direction: column; gap: 4px; }}
  .kb-row {{ display: flex; gap: 4px; align-items: center; }}

  .key {{
    width: var(--key-w);
    height: var(--key-h);
    flex-shrink: 0;
    border-radius: 6px;
    border: 0.5px solid var(--border2);
    background: var(--bg);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    font-size: 11px;
    color: var(--text);
    position: relative;
    text-align: center;
    line-height: 1.25;
    padding: 2px 3px;
  }}
  .key-trans {{ opacity: 0.25; }}
  .key-layer {{
    background: var(--amber-bg);
    color: var(--amber-fg);
    border-color: transparent;
  }}
  .key-special {{
    background: var(--blue-bg);
    color: var(--blue-fg);
    border-color: transparent;
  }}
  .hold {{
    font-size: 9px;
    color: var(--text2);
    position: absolute;
    bottom: 2px;
    right: 3px;
    line-height: 1;
  }}
  .key-layer .hold, .key-special .hold {{ color: inherit; opacity: 0.7; }}

  .gap {{ width: 14px; flex-shrink: 0; }}
  .spacer {{ flex: 1; }}
  .spacer-wide {{ flex: 3; }}

  .split-label {{
    font-size: 10px;
    color: var(--text2);
    text-align: center;
    margin: 2px 0;
    letter-spacing: 0.04em;
  }}

  .kb-row.extras {{
    margin-top: 6px;
    justify-content: center;
    gap: 8px;
  }}
  .extra-key {{
    width: 58px;
    height: 36px;
    font-size: 9px;
  }}
  .extra-key small {{ font-size: 10px; font-weight: 500; }}

  .legend {{
    display: flex;
    gap: 14px;
    flex-wrap: wrap;
    font-size: 11px;
    color: var(--text2);
    margin-bottom: 20px;
  }}
  .legend-item {{ display: flex; align-items: center; gap: 5px; }}
  .legend-dot {{
    width: 11px; height: 11px;
    border-radius: 3px;
    border: 0.5px solid var(--border2);
  }}
  .legend-dot.layer {{ background: var(--amber-bg); border-color: transparent; }}
  .legend-dot.special {{ background: var(--blue-bg); border-color: transparent; }}
  .legend-dot.normal {{ background: var(--bg); }}

  hr {{ border: none; border-top: 0.5px solid var(--border); margin: 32px 0; }}

  @media print {{
    body {{ padding: 12px; }}
    .layer {{ page-break-inside: avoid; }}
  }}
</style>
</head>
<body>
<header>
  <h1>roBa keymap cheatsheet</h1>
  <div class="meta">
    <span>generated: {now}</span>
    {source_note}
    <span>{len(layers)} layers</span>
  </div>
</header>

<nav>{nav_items}</nav>

<div class="legend">
  <div class="legend-item"><div class="legend-dot normal"></div>通常キー</div>
  <div class="legend-item"><div class="legend-dot layer"></div>レイヤーキー</div>
  <div class="legend-item"><div class="legend-dot special"></div>特殊/システム</div>
</div>

{layers_html}
</body>
</html>
'''


def main():
    if len(sys.argv) < 3:
        print("Usage: generate_cheatsheet.py <input.keymap> <output.html>")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])

    if not input_path.exists():
        print(f"Error: {input_path} not found")
        sys.exit(1)

    text = input_path.read_text(encoding="utf-8")
    layers = parse_keymap(text)

    if not layers:
        print("Error: no layers found in keymap file")
        sys.exit(1)

    print(f"Found {len(layers)} layer(s): {[l['name'] for l in layers]}")

    html = generate_html(layers, source_path=str(input_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    print(f"Cheatsheet written to: {output_path}")


if __name__ == "__main__":
    main()
