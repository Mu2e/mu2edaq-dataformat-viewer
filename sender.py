#!/usr/bin/env python3
"""
Mu2e Data Format Sender
=======================
Companion to viewer.py.  Lets you construct a Mu2e ROC packet field-by-field
using the same YAML format definitions, then send the assembled bytes to the
viewer over a TCP socket.
"""

import os
import sys
import socket
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

try:
    import yaml
except ImportError:
    print("PyYAML is required.  Install with:  pip install pyyaml")
    sys.exit(1)

YAML_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# YAML loading  (identical to viewer.py)
# ---------------------------------------------------------------------------

def load_yaml_formats(yaml_dir: str) -> dict:
    formats = {}
    for path in sorted(Path(yaml_dir).glob("*.yaml")):
        if path.stem == "packet_type_index":
            continue
        try:
            with open(path) as fh:
                data = yaml.safe_load(fh)
            if isinstance(data, dict):
                formats[data.get("name", path.stem)] = data
        except Exception as exc:
            print(f"Warning: could not load {path.name}: {exc}")
    return formats


# ---------------------------------------------------------------------------
# Byte-assembly helpers
# ---------------------------------------------------------------------------

def _parse_bits(bits_str: str) -> tuple[int, int]:
    """Return (high, low) from a bits spec like '15:8' or '3'."""
    bits_str = str(bits_str).strip()
    if ":" in bits_str:
        high, low = (int(x) for x in bits_str.split(":"))
    else:
        high = low = int(bits_str)
    return high, low


def set_bits(buf: bytearray, word_idx: int, bits_str: str,
             value: int, little_endian: bool = False) -> None:
    """Write *value* into the bit field described by *bits_str* inside *buf*."""
    offset = word_idx * 2
    if offset + 2 > len(buf):
        return
    if little_endian:
        word_val = buf[offset] | (buf[offset + 1] << 8)
    else:
        word_val = (buf[offset] << 8) | buf[offset + 1]

    high, low = _parse_bits(bits_str)
    width = high - low + 1
    mask = (1 << width) - 1
    word_val &= ~(mask << low)
    word_val |= (value & mask) << low
    word_val &= 0xFFFF

    if little_endian:
        buf[offset]     = word_val & 0xFF
        buf[offset + 1] = (word_val >> 8) & 0xFF
    else:
        buf[offset]     = (word_val >> 8) & 0xFF
        buf[offset + 1] = word_val & 0xFF


def buf_size_for_format(fmt: dict) -> int:
    """Return the packet buffer size in bytes for a format definition."""
    if "size_bytes" in fmt:
        return int(fmt["size_bytes"])
    # Derive from max word index across all field sections
    max_word = 0
    for fields in _all_field_lists(fmt):
        for f in fields:
            max_word = max(max_word, int(f.get("word", 0)))
    return (max_word + 1) * 2


def _all_field_lists(fmt: dict) -> list[list]:
    """Return all lists of fields found in *fmt*, across every sub-section."""
    lists = []
    if "fields" in fmt:
        lists.append(fmt["fields"])
    for key in ("packet_1", "packet_2", "hit_format"):
        sub = fmt.get(key)
        if isinstance(sub, dict) and "fields" in sub:
            lists.append(sub["fields"])
    return lists


def parse_int(text: str) -> int:
    """Parse a decimal or hex (0x…) integer string."""
    text = text.strip()
    if text.lower().startswith("0x"):
        return int(text, 16)
    return int(text, 10)


# ---------------------------------------------------------------------------
# Scrollable frame helper
# ---------------------------------------------------------------------------

class ScrollableFrame(ttk.Frame):
    """A ttk.Frame with a vertical scrollbar, usable like a normal Frame."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        canvas = tk.Canvas(self, highlightthickness=0)
        vsb = ttk.Scrollbar(self, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.inner = ttk.Frame(canvas)
        self._window_id = canvas.create_window((0, 0), window=self.inner, anchor=tk.NW)

        self.inner.bind("<Configure>",
                        lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfigure(self._window_id, width=e.width))
        # Mouse-wheel scrolling
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))
        self._canvas = canvas


# ---------------------------------------------------------------------------
# Per-field entry row
# ---------------------------------------------------------------------------

class FieldRow:
    """One row in the fields panel representing a single packet field."""

    COL_NAME  = 0
    COL_WORD  = 1
    COL_BITS  = 2
    COL_ENTRY = 3
    COL_DESC  = 4

    def __init__(self, parent: tk.Widget, row_idx: int, field: dict,
                 on_change, mono: tuple):
        self.field = field
        self.on_change = on_change
        self._var = tk.StringVar()
        self._enum_map: dict[str, int] = {}  # display string → integer value

        name     = field.get("name", "?")
        bits     = str(field.get("bits", "?"))
        word     = str(field.get("word", "?"))
        desc     = str(field.get("description", "")).replace("\n", " ").strip()
        fv       = field.get("fixed_value")
        vals     = field.get("values") or {}
        size     = int(field.get("size_bits", 1))
        reserved = "reserved" in name.lower()

        fg = "#888888" if reserved else "black"

        ttk.Label(parent, text=name,  font=mono, foreground=fg,
                  anchor=tk.E).grid(row=row_idx, column=self.COL_NAME,
                                    sticky=tk.EW, padx=(4, 2), pady=1)
        ttk.Label(parent, text=word,  font=mono, foreground=fg,
                  anchor=tk.E).grid(row=row_idx, column=self.COL_WORD,
                                    sticky=tk.EW, padx=2, pady=1)
        ttk.Label(parent, text=bits,  font=mono, foreground=fg,
                  anchor=tk.E).grid(row=row_idx, column=self.COL_BITS,
                                    sticky=tk.EW, padx=2, pady=1)

        if vals:
            # Enum combobox — build display options sorted by integer key
            options = []
            for k, v in vals.items():
                try:
                    int_key = parse_int(str(k))
                except ValueError:
                    int_key = 0
                label = f"0x{int_key:0{max(1,(size+3)//4)}X}  {v}"
                self._enum_map[label] = int_key
                options.append((int_key, label))
            options.sort()
            display_opts = [lbl for _, lbl in options]
            self._widget = ttk.Combobox(parent, textvariable=self._var,
                                        values=display_opts, state="readonly",
                                        font=mono, width=36)
            if display_opts:
                self._var.set(display_opts[0])
        else:
            self._widget = ttk.Entry(parent, textvariable=self._var,
                                     font=mono, width=20)

        if fv is not None:
            try:
                fv_int = parse_int(str(fv))
            except ValueError:
                fv_int = 0
            hex_digits = max(1, (size + 3) // 4)
            self._var.set(f"0x{fv_int:0{hex_digits}X}")
            self._widget.configure(state="disabled")

        self._widget.grid(row=row_idx, column=self.COL_ENTRY,
                          sticky=tk.EW, padx=2, pady=1)

        short_desc = desc if len(desc) <= 60 else desc[:57] + "…"
        ttk.Label(parent, text=short_desc, font=mono, foreground="#555555",
                  anchor=tk.E).grid(row=row_idx, column=self.COL_DESC,
                                    sticky=tk.EW, padx=(2, 4), pady=1)

        self._var.trace_add("write", lambda *_: on_change())

    def get_value(self) -> int | None:
        """Return the integer value currently entered, or None on error."""
        raw = self._var.get().strip()
        if not raw:
            return 0
        # Enum combobox
        if self._enum_map:
            return self._enum_map.get(raw, 0)
        try:
            return parse_int(raw)
        except ValueError:
            return None


# ---------------------------------------------------------------------------
# Section header row
# ---------------------------------------------------------------------------

def _section_header(parent: tk.Widget, row_idx: int, label: str, mono: tuple):
    ttk.Label(
        parent, text=f"  {label}",
        font=(mono[0], mono[1], "bold"),
        background="#d0e8ff", anchor=tk.E,
    ).grid(row=row_idx, column=0, columnspan=5, sticky=tk.EW,
           padx=2, pady=(6, 2))


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

MONO = ("Courier", 11)
MONO_SM = ("Courier", 10)


class Mu2eSender(tk.Tk):
    def __init__(self, yaml_dir: str):
        super().__init__()
        self.title("Mu2e Data Format Sender")
        self.geometry("1100x720")
        self.minsize(700, 500)

        self.yaml_dir = yaml_dir
        self.formats = load_yaml_formats(yaml_dir)
        self.little_endian = tk.BooleanVar(value=False)
        self._field_rows: list[FieldRow] = []
        self._current_fmt: dict = {}

        self._apply_fonts()
        self._build_ui()
        self._load_format()

    # ------------------------------------------------------------------
    # Fonts / style
    # ------------------------------------------------------------------

    def _apply_fonts(self):
        style = ttk.Style(self)
        style.configure(".",                 font=MONO)
        style.configure("Treeview",          font=MONO_SM)
        style.configure("Treeview.Heading",  font=(MONO[0], MONO[1], "bold"))
        self.option_add("*TCombobox*Listbox.font", MONO)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        # ── Toolbar ───────────────────────────────────────────────────
        bar = ttk.Frame(self, padding=(4, 4))
        bar.pack(fill=tk.X, side=tk.TOP)

        ttk.Label(bar, text="Packet format:", font=MONO).pack(side=tk.LEFT)
        self.format_var = tk.StringVar()
        fmt_names = sorted(self.formats.keys())
        self.format_combo = ttk.Combobox(
            bar, textvariable=self.format_var, values=fmt_names,
            width=36, state="readonly", font=MONO,
        )
        if fmt_names:
            self.format_combo.set(fmt_names[0])
        self.format_combo.pack(side=tk.LEFT, padx=(2, 8))
        self.format_combo.bind("<<ComboboxSelected>>", lambda _e: self._load_format())

        _sep(bar)

        ttk.Checkbutton(bar, text="Little-endian words",
                        variable=self.little_endian,
                        command=self._assemble).pack(side=tk.LEFT)

        _sep(bar)

        ttk.Label(bar, text="Viewer host:", font=MONO).pack(side=tk.LEFT)
        self.host_var = tk.StringVar(value="localhost")
        ttk.Entry(bar, textvariable=self.host_var, width=14,
                  font=MONO).pack(side=tk.LEFT, padx=2)

        ttk.Label(bar, text="port:", font=MONO).pack(side=tk.LEFT)
        self.port_var = tk.StringVar(value="7755")
        ttk.Entry(bar, textvariable=self.port_var, width=6,
                  font=MONO).pack(side=tk.LEFT, padx=2)

        ttk.Button(bar, text="Send to viewer",
                   command=self._send).pack(side=tk.LEFT, padx=(8, 2))
        ttk.Button(bar, text="Reset fields",
                   command=self._load_format).pack(side=tk.LEFT, padx=2)

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(bar, textvariable=self.status_var,
                  foreground="gray", font=MONO).pack(side=tk.LEFT, padx=8)

        # ── Paned area ────────────────────────────────────────────────
        paned = ttk.PanedWindow(self, orient=tk.VERTICAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 4))

        # ── Field entries ─────────────────────────────────────────────
        fields_outer = ttk.LabelFrame(paned, text="Packet fields", padding=4)
        paned.add(fields_outer, weight=4)

        self._scroll = ScrollableFrame(fields_outer)
        self._scroll.pack(fill=tk.BOTH, expand=True)

        self._fields_frame = self._scroll.inner
        for col, weight in ((0, 3), (1, 1), (1, 1), (2, 3), (4, 5)):
            self._fields_frame.columnconfigure(col, weight=weight)

        # ── Assembled bytes ───────────────────────────────────────────
        bytes_frame = ttk.LabelFrame(paned, text="Assembled bytes", padding=4)
        paned.add(bytes_frame, weight=1)

        self.bytes_text = tk.Text(
            bytes_frame, height=4, font=MONO, wrap=tk.WORD,
            state=tk.DISABLED, background="#f8f8f8",
        )
        sb = ttk.Scrollbar(bytes_frame, command=self.bytes_text.yview)
        self.bytes_text.config(yscrollcommand=sb.set)
        self.bytes_text.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

    # ------------------------------------------------------------------
    # Format loading — rebuild the field rows whenever format changes
    # ------------------------------------------------------------------

    def _load_format(self):
        # Destroy existing rows
        for w in self._fields_frame.winfo_children():
            w.destroy()
        self._field_rows.clear()

        fmt_name = self.format_var.get()
        if not fmt_name or fmt_name not in self.formats:
            return
        self._current_fmt = self.formats[fmt_name]

        # Column headings
        for col, heading in (
            (FieldRow.COL_NAME,  "Field Name"),
            (FieldRow.COL_WORD,  "Word"),
            (FieldRow.COL_BITS,  "Bits"),
            (FieldRow.COL_ENTRY, "Value  (hex or decimal)"),
            (FieldRow.COL_DESC,  "Description"),
        ):
            ttk.Label(
                self._fields_frame, text=heading,
                font=(MONO[0], MONO[1], "bold"),
                anchor=tk.E, background="#e0e0e0",
            ).grid(row=0, column=col, sticky=tk.EW, padx=2, pady=(0, 4))

        row_idx = 1

        # Collect sections (mirrors viewer.py logic + hit_format)
        sections: list[tuple[str, list]] = []
        fmt = self._current_fmt
        if "fields" in fmt:
            sections.append(("", fmt["fields"]))
        for key in ("packet_1", "packet_2"):
            sub = fmt.get(key)
            if isinstance(sub, dict) and "fields" in sub:
                label = sub.get("description", key.replace("_", " ").title())
                sections.append((label, sub["fields"]))
        sub = fmt.get("hit_format")
        if isinstance(sub, dict) and "fields" in sub:
            sections.append(("Hit Format", sub["fields"]))

        for section_label, fields in sections:
            if section_label:
                _section_header(self._fields_frame, row_idx, section_label, MONO)
                row_idx += 1
            for field in fields:
                fr = FieldRow(
                    self._fields_frame, row_idx, field,
                    on_change=self._assemble,
                    mono=MONO_SM,
                )
                self._field_rows.append(fr)
                row_idx += 1

        self._assemble()

    # ------------------------------------------------------------------
    # Byte assembly
    # ------------------------------------------------------------------

    def _assemble(self) -> bytearray | None:
        """Build the packet bytearray from current field values and display it."""
        fmt = self._current_fmt
        if not fmt:
            return None

        size = buf_size_for_format(fmt)
        buf = bytearray(size)
        le = self.little_endian.get()

        # Collect all fields in definition order (mirrors _load_format)
        all_fields: list[dict] = []
        if "fields" in fmt:
            all_fields.extend(fmt["fields"])
        for key in ("packet_1", "packet_2"):
            sub = fmt.get(key)
            if isinstance(sub, dict) and "fields" in sub:
                all_fields.extend(sub["fields"])
        sub = fmt.get("hit_format")
        if isinstance(sub, dict) and "fields" in sub:
            all_fields.extend(sub["fields"])

        error = False
        for field_def, row in zip(all_fields, self._field_rows):
            val = row.get_value()
            if val is None:
                error = True
                continue
            set_bits(buf, int(field_def.get("word", 0)),
                     str(field_def.get("bits", "15:0")), val, le)

        # Display
        hex_str = " ".join(f"{b:02X}" for b in buf)
        # Group into 16-byte rows for readability
        lines = []
        for i in range(0, len(buf), 16):
            offset_label = f"{i:04X}:  "
            chunk = buf[i:i + 16]
            hex_part = " ".join(f"{b:02X}" for b in chunk)
            lines.append(offset_label + hex_part)
        display = "\n".join(lines)

        self.bytes_text.config(state=tk.NORMAL)
        self.bytes_text.delete("1.0", tk.END)
        self.bytes_text.insert("1.0", display)
        self.bytes_text.config(state=tk.DISABLED,
                               foreground="red" if error else "black")

        if error:
            self.status_var.set("Input error — check field values")
        else:
            self.status_var.set(f"Assembled  {len(buf)} bytes")

        return None if error else buf

    # ------------------------------------------------------------------
    # Send
    # ------------------------------------------------------------------

    def _send(self):
        buf = self._assemble()
        if buf is None:
            messagebox.showerror("Send error", "Cannot send — fix field value errors first.")
            return

        host = self.host_var.get().strip()
        try:
            port = int(self.port_var.get().strip())
        except ValueError:
            messagebox.showerror("Send error", "Invalid port number.")
            return

        try:
            with socket.create_connection((host, port), timeout=5) as sock:
                sock.sendall(bytes(buf))
            self.status_var.set(
                f"Sent {len(buf)} bytes to {host}:{port}"
            )
        except OSError as exc:
            messagebox.showerror("Send error",
                                 f"Could not connect to {host}:{port}\n\n{exc}")
            self.status_var.set("Send failed")


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _sep(parent):
    ttk.Separator(parent, orient=tk.VERTICAL).pack(
        side=tk.LEFT, fill=tk.Y, padx=6, pady=2
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    yaml_directory = sys.argv[1] if len(sys.argv) > 1 else YAML_DIR
    app = Mu2eSender(yaml_directory)
    app.mainloop()
