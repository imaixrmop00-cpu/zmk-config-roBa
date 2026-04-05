#!/usr/bin/env python3
"""
roBa keymap cheatsheet generator
Parses a ZMK .keymap file (keymap-editor format) and generates an HTML cheatsheet.
Usage: python generate_cheatsheet.py <input.keymap> <output.html>
"""

import re
import sys
from pathlib import Path
from datetime import datetime

# ---------------------------------------------------------------------------
# roBa physical layout (43 keys + sensor-bindings encoder)
#
# bindingsのフラットリストと物理配置のマッピング:
#
# [0-4]   上段左5キー
# [5-9]   上段右5キー
# [10-14] 中段左5キー
# [15-16] サムL上段2キー (行末混在)
# [17-21] 中段右5キー
# [22-26] 下段左5キー
# [27-28] サムL下段2キー (行末混在)
# [29-33] 下段右5キー
# [34-37] サムクラスター左4キー
# [38-42] サムクラスター右5キー (右端1キー含む)
#
# 物理的なサムクラスター配置:
#   左: [34][35][36][37]  右: [38][39][40][41]  右端: [42]
# ---------------------------------------------------------------------------

LAYOUT = {
    "row0_left":   list(range(0, 5)),
    "row0_right":  list(range(5, 10)),
    "row1_left":   list(range(10, 15)),
    "row1_right":  list(range(17, 22)),
    "row2_left":   list(range(22, 27)),
    "row2_right":  list(range(29, 34)),
    "thumb_left":  [34, 35, 36, 37],
    "thumb_right": [38, 39, 40, 41],
    "thumb_extra": [42],
    # エンコーダーは sensor-bindings で別管理
}

KEY_LABELS = {
    "SPACE": "SPC", "ENTER": "↵", "RETURN": "↵", "BSPC": "⌫", "DEL": "DEL",
    "TAB": "⇥", "ESC": "ESC", "GRAVE": "`", "TILDE": "~",
    "LSHIFT": "⇧", "RSHIFT": "⇧", "LCTRL": "Ctrl", "RCTRL": "Ctrl",
    "LEFT_SHIFT": "⇧", "RIGHT_SHIFT": "⇧", "LEFT_CONTROL": "Ctrl", "RIGHT_CONTROL": "Ctrl",
    "LALT": "Alt", "RALT": "Alt", "LEFT_ALT": "Alt", "RIGHT_ALT": "Alt",
    "LGUI": "⌘", "RGUI": "⌘", "LEFT_GUI": "⌘", "RIGHT_GUI": "⌘",
    "LMETA": "⌘", "RMETA": "⌘", "LEFT_WIN": "Win", "RIGHT_WIN": "Win",
    "LEFT": "←", "RIGHT": "→", "UP": "↑", "DOWN": "↓",
    "LEFT_ARROW": "←", "RIGHT_ARROW": "→", "UP_ARROW": "↑", "DOWN_ARROW": "↓",
    "HOME": "Home", "END": "End", "PG_UP": "PgUp", "PG_DN": "PgDn",
    "PAGE_UP": "PgUp", "PAGE_DOWN": "PgDn",
    "SEMI": ";", "COLON": ":", "SQT": "'", "DQT": '"', "DOUBLE_QUOTES": '"',
    "SINGLE_QUOTE": "'",
    "COMMA": ",", "DOT": ".", "SLASH": "/", "FSLH": "/",
    "BSLH": "\\", "PIPE": "|", "MINUS": "-", "PLUS": "+", "EQUAL": "=",
    "LBKT": "[", "RBKT": "]", "LEFT_BRACKET": "[", "RIGHT_BRACKET": "]",
    "LBRC": "{", "RBRC": "}", "LEFT_BRACE": "{", "RIGHT_BRACE": "}",
    "LPAR": "(", "RPAR": ")", "LEFT_PARENTHESIS": "(", "RIGHT_PARENTHESIS": ")",
    "LT": "<", "GT": ">", "LESS_THAN": "<", "GREATER_THAN": ">",
    "EXCL": "!", "AT": "@", "HASH": "#", "DLLR": "$",
    "PRCNT": "%", "CARET": "^", "AMPS": "&", "STAR": "*", "AMPERSAND": "&",
    "UNDER": "_", "QMARK": "?", "QUESTION": "?", "EXCLAMATION": "!",
    "N0": "0", "N1": "1", "N2": "2", "N3": "3", "N4": "4",
    "N5": "5", "N6": "6", "N7": "7", "N8": "8", "N9": "9",
    "NUMBER_0": "0", "NUMBER_1": "1", "NUMBER_2": "2", "NUMBER_3": "3",
    "NUMBER_4": "4", "NUMBER_5": "5", "NUMBER_6": "6", "NUMBER_7": "7",
    "NUMBER_8": "8", "NUMBER_9": "9",
    **{f"F{i}": f"F{i}" for i in range(1, 13)},
    "C_VOL_UP": "Vol+", "C_VOL_DN": "Vol-", "C_MUTE": "Mute",
    "C_PP": "⏯", "C_NEXT": "⏭", "C_PREV": "⏮",
    "C_BRIGHTNESS_INC": "Bri+", "C_BRIGHTNESS_DEC": "Bri-",
    "C_VOLUME_UP": "Vol+", "C_VOLUME_DOWN": "Vol-",
    "PRINTSCREEN": "PrtSc", "CAPSLOCK": "Caps", "INS": "Ins", "INSERT": "Ins",
    "SCROLLLOCK": "ScrLk", "DELETE": "Del",
    "KP_ENTER": "KP↵", "KP_DOT": "KP.", "KP_PLUS": "KP+",
    "KP_MINUS": "KP-", "KP_MULTIPLY": "KP*", "KP_DIVIDE": "KP/",
    "KP_PLUS": "KP+", "KP_ASTERISK": "KP*",
    "INT_MUHENKAN": "無変換", "INT_HENKAN": "変換", "INT_KATAKANAHIRAGANA": "かな",
    "CAPS": "Caps",
    "LCLK": "左click", "RCLK": "右click", "MCLK": "中click",
}

def fmt_label(s: str) -> str:
    s = s.strip()
    upper = s.upper()
    if upper in KEY_LABELS:
        return KEY_LABELS[upper]
    if len(s) == 1:
        return s
    return s[:7] + "…" if len(s) > 7 else s

def fmt_bt(raw: str) -> str:
    if "CLR_ALL" in raw:
        return "BT CLR ALL"
    if "CLR" in raw:
        return "BT CLR"
    m = re.search(r"BT_SEL\s+(\d+)", raw)
    if m:
        return f"BT {m.group(1)}"
    return "BT"

def parse_binding(raw: str) -> dict:
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

    m = re.match(r"&lt\s+(\d+)\s+(.+)$", r)
    if m:
        return {"label": fmt_label(m.group(2)), "hold": f"L{m.group(1)}", "cls": "layer"}

    m = re.match(r"&lt_to_layer_0\s+(\d+)\s+(.+)$", r)
    if m:
        return {"label": fmt_label(m.group(2)), "hold": f"L{m.group(1)}", "cls": "layer"}

    m = re.match(r"&to_layer_0\s+(.+)$", r)
    if m:
        return {"label": fmt_label(m.group(1)), "hold": "→L0", "cls": "layer"}

    m = re.match(r"&mt\s+(\S+)\s+(.+)$", r)
    if m:
        return {"label": fmt_label(m.group(2)), "hold": fmt_label(m.group(1)), "cls": ""}

    m = re.match(r"&ht\s+(\S+)\s+(.+)$", r)
    if m:
        return {"label": fmt_label(m.group(2)), "hold": fmt_label(m.group(1)), "cls": ""}

    m = re.match(r"&mo\s+(\d+)$", r)
    if m:
        return {"label": f"Mo{m.group(1)}", "hold": "", "cls": "layer"}

    m = re.match(r"&to\s+(\d+)$", r)
    if m:
        return {"label": f"To{m.group(1)}", "hold": "", "cls": "layer"}

    m = re.match(r"&sk\s+(.+)$", r)
    if m:
        return {"label": "sk:" + fmt_label(m.group(1)), "hold": "", "cls": "special"}

    m = re.match(r"&mkp\s+(\S+)$", r)
    if m:
        return {"label": fmt_label(m.group(1)), "hold": "", "cls": "special"}

    if r.startswith("&bt "):
        return {"label": fmt_bt(r), "hold": "", "cls": "special"}

    if r.startswith("&out "):
        lbl = "USB" if "USB" in r else "BLE"
        return {"label": lbl, "hold": "", "cls": "special"}

    m = re.match(r"&kp\s+(.+)$", r)
    if m:
        return {"label": fmt_label(m.group(1)), "hold": "", "cls": ""}

    m = re.match(r"&(\S+)", r)
    if m:
        return {"label": m.group(1)[:7], "hold": "", "cls": "special"}

    return {"label": r[:7], "hold": "", "cls": ""}


def tokenize_bindings(text: str) -> list:
    text = re.sub(r'\s+', ' ', text).strip()
    parts = text.split('&')
    return ['&' + p.strip() for p in parts if p.strip()]


def parse_keymap(text: str) -> list:
    layers = []
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
        tokens = tokenize_bindings(m.group(2))
        keys = [parse_binding(t) for t in tokens]
        layers.append({"name": name, "keys": keys})

    return layers


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

    def row_html(indices_left, indices_right):
        h = '<div class="kb-row">'
        for i in indices_left:
            h += key_html(g(i))
        h += '<div class="gap"></div>'
        for i in indices_right:
            h += key_html(g(i))
        h += '</div>\n'
        return h

    rows = ""
    # 上段
    rows += row_html(LAYOUT["row0_left"], LAYOUT["row0_right"])
    # 中段 (行末混在のサムキー[15,16]は除外して描画)
    rows += row_html(LAYOUT["row1_left"], LAYOUT["row1_right"])
    # 下段 (行末混在のサムキー[27,28]は除外して描画)
    rows += row_html(LAYOUT["row2_left"], LAYOUT["row2_right"])

    # サムクラスター
    rows += '<div class="split-label">thumb cluster</div>\n'
    rows += '<div class="kb-row thumb-row">'
    for i in LAYOUT["thumb_left"]:
        rows += key_html(g(i))
    rows += '<div class="gap"></div>'
    for i in LAYOUT["thumb_right"]:
        rows += key_html(g(i))
    rows += '</div>\n'

    # サム行末の混在キー[15,16,27,28]をサム行の下に補足表示
    mixed = [15, 16, 27, 28]
    mixed_keys = [g(i) for i in mixed]
    if any(k["label"] not in ("", "▽") for k in mixed_keys):
        rows += '<div class="split-label" style="opacity:0.6">行末混在キー (中段: L1×2 / 下段: L3, RAlt)</div>\n'
        rows += '<div class="kb-row" style="justify-content:center;gap:8px">'
        for i in mixed:
            rows += key_html(g(i))
        rows += '</div>\n'

    rows += '<div class="split-label" style="opacity:0.4;margin-top:4px">encoder: sensor-bindings</div>\n'

    return f'''
<section class="layer" id="layer-{idx}">
  <h2 class="layer-title">Layer {idx} <span class="layer-name">{layer["name"]}</span></h2>
  <div class="keyboard">
{rows}  </div>
</section>
'''


def generate_html(layers: list, source_path: str = "") -> str:
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
    --bg: #ffffff; --bg2: #f5f5f4;
    --border: rgba(0,0,0,0.12); --border2: rgba(0,0,0,0.22);
    --text: #1c1c1a; --text2: #6b6b67;
    --blue-bg: #dbeafe; --blue-fg: #1e40af;
    --amber-bg: #fef3c7; --amber-fg: #92400e;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #1e1e1c; --bg2: #2a2a28;
      --border: rgba(255,255,255,0.1); --border2: rgba(255,255,255,0.2);
      --text: #e8e6e0; --text2: #9a9893;
      --blue-bg: #1e3a5f; --blue-fg: #93c5fd;
      --amber-bg: #451a03; --amber-fg: #fcd34d;
    }}
  }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); color: var(--text); padding: 24px 20px 48px; max-width: 820px; margin: 0 auto; }}
  header {{ margin-bottom: 24px; border-bottom: 0.5px solid var(--border2); padding-bottom: 16px; }}
  header h1 {{ font-size: 20px; font-weight: 500; margin-bottom: 4px; }}
  .meta {{ font-size: 12px; color: var(--text2); display: flex; gap: 16px; flex-wrap: wrap; }}
  nav {{ display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 28px; }}
  .nav-item {{ font-size: 12px; padding: 4px 12px; border-radius: 8px; border: 0.5px solid var(--border2); color: var(--text2); text-decoration: none; }}
  .nav-item:hover {{ background: var(--bg2); color: var(--text); }}
  .layer {{ margin-bottom: 40px; }}
  .layer-title {{ font-size: 15px; font-weight: 500; margin-bottom: 12px; display: flex; align-items: center; gap: 8px; }}
  .layer-name {{ font-size: 12px; font-weight: 400; color: var(--text2); background: var(--bg2); padding: 2px 8px; border-radius: 99px; border: 0.5px solid var(--border); }}
  .keyboard {{ display: flex; flex-direction: column; gap: 3px; }}
  .kb-row {{ display: flex; gap: 3px; align-items: center; }}
  .key {{
    width: 48px; height: 42px; flex-shrink: 0;
    border-radius: 6px; border: 0.5px solid var(--border2);
    background: var(--bg);
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    font-size: 11px; color: var(--text);
    position: relative; text-align: center; line-height: 1.25; padding: 2px 3px;
  }}
  .key-trans {{ opacity: 0.2; }}
  .key-layer {{ background: var(--amber-bg); color: var(--amber-fg); border-color: transparent; }}
  .key-special {{ background: var(--blue-bg); color: var(--blue-fg); border-color: transparent; }}
  .hold {{ font-size: 9px; color: var(--text2); position: absolute; bottom: 2px; right: 3px; line-height: 1; }}
  .key-layer .hold, .key-special .hold {{ color: inherit; opacity: 0.7; }}
  .gap {{ width: 16px; flex-shrink: 0; }}
  .split-label {{ font-size: 10px; color: var(--text2); text-align: center; margin: 4px 0 2px; letter-spacing: 0.04em; }}
  .thumb-row .key {{ background: var(--bg2); }}
  .legend {{ display: flex; gap: 14px; flex-wrap: wrap; font-size: 11px; color: var(--text2); margin-bottom: 20px; }}
  .legend-item {{ display: flex; align-items: center; gap: 5px; }}
  .legend-dot {{ width: 11px; height: 11px; border-radius: 3px; border: 0.5px solid var(--border2); }}
  .legend-dot.layer {{ background: var(--amber-bg); border-color: transparent; }}
  .legend-dot.special {{ background: var(--blue-bg); border-color: transparent; }}
  .legend-dot.normal {{ background: var(--bg); }}
  @media print {{ body {{ padding: 12px; }} .layer {{ page-break-inside: avoid; }} }}
</style>
</head>
<body>
<header>
  <h1>roBa keymap cheatsheet</h1>
  <div class="meta"><span>generated: {now}</span>{source_note}<span>{len(layers)} layers</span></div>
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
        print("Error: no layers found")
        sys.exit(1)
    print(f"Found {len(layers)} layer(s): {[l['name'] for l in layers]}")
    html = generate_html(layers, source_path=str(input_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    print(f"Cheatsheet written to: {output_path}")

if __name__ == "__main__":
    main()
