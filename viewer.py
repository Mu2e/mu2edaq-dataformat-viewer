#!/usr/bin/env python3
"""
Mu2e Data Format Viewer
=======================
Displays Mu2e ROC packet byte data broken out field-by-field using YAML format
definitions.  Data can be entered manually as hex bytes, loaded from a binary
file, or received over a TCP socket from an external application.
"""

import os
import sys
import socket
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

try:
    import yaml
except ImportError:
    print("PyYAML is required.  Install with:  pip install pyyaml")
    sys.exit(1)

# ---------------------------------------------------------------------------
# YAML loading
# ---------------------------------------------------------------------------

YAML_DIR = os.path.dirname(os.path.abspath(__file__))


def load_yaml_formats(yaml_dir: str) -> dict:
    """Load all packet format definitions from *.yaml files in yaml_dir."""
    formats = {}
    for path in sorted(Path(yaml_dir).glob("*.yaml")):
        if path.stem == "packet_type_index":
            continue
        try:
            with open(path) as fh:
                data = yaml.safe_load(fh)
            if isinstance(data, dict):
                name = data.get("name", path.stem)
                formats[name] = data
        except Exception as exc:
            print(f"Warning: could not load {path.name}: {exc}")
    return formats


# ---------------------------------------------------------------------------
# Bit / byte helpers
# ---------------------------------------------------------------------------

def get_word(data: bytes, word_idx: int, little_endian: bool = False) -> int | None:
    """Return a 16-bit word from *data* at *word_idx*.  Returns None if out of range."""
    offset = word_idx * 2
    if offset + 2 > len(data):
        return None
    b0, b1 = data[offset], data[offset + 1]
    return (b1 << 8) | b0 if little_endian else (b0 << 8) | b1


def extract_bits(word_val: int, bits_str: str) -> tuple[int, int]:
    """
    Extract a bit field from a 16-bit word value.

    *bits_str* is like ``"15:8"`` (range) or ``"3"`` (single bit).
    Returns ``(value, width_in_bits)``.
    """
    bits_str = str(bits_str).strip()
    if ":" in bits_str:
        high, low = (int(x) for x in bits_str.split(":"))
    else:
        high = low = int(bits_str)
    width = high - low + 1
    mask = (1 << width) - 1
    return (word_val >> low) & mask, width


def parse_fields(data: bytes, fields: list, little_endian: bool = False) -> list[dict]:
    """Parse a list of field definitions against *data*.  Returns a list of result dicts."""
    results = []
    for field in fields:
        word_idx = field.get("word", 0)
        bits_str = str(field.get("bits", "15:0"))
        word_val = get_word(data, word_idx, little_endian)
        if word_val is None:
            continue
        value, width = extract_bits(word_val, bits_str)
        results.append(
            {
                "name": field.get("name", "?"),
                "word": word_idx,
                "byte_offset": word_idx * 2,
                "bits": bits_str,
                "size_bits": width,
                "value": value,
                "description": str(field.get("description", "")).strip(),
                "values": field.get("values") or {},
                "fixed_value": field.get("fixed_value"),
                "subfields": field.get("subfields") or [],
            }
        )
    return results


def hex_str_to_bytes(text: str) -> bytes:
    """Convert a hex string (spaces / 0x prefixes allowed) to bytes."""
    cleaned = (
        text.replace("0x", "")
        .replace("0X", "")
        .replace(",", " ")
        .replace("\n", " ")
        .replace("\r", " ")
    )
    tokens = cleaned.split()
    return bytes(int(t, 16) for t in tokens if t)


def decode_value(value: int, field_def: dict) -> str:
    """Return a human-readable decoded string for *value* given *field_def*."""
    vals = field_def.get("values") or {}
    if not vals:
        return ""
    # Try several key formats
    for k in (value, f"0x{value:X}", f"0x{value:02X}", f"0x{value:04X}", str(value)):
        if k in vals:
            return str(vals[k])
    return ""


# ---------------------------------------------------------------------------
# Main GUI
# ---------------------------------------------------------------------------

PACKET_TYPE_MAP = {
    0x0: "DCS Request Packet",
    0x1: "Heartbeat Packet",
    0x2: "Data Request Packet",
    0x3: "Prefetch Request Packet",
    0x4: "DCS Reply Packet",
    0x5: "Data Header Packet",
    0x6: "Data Payload Packet",
    0x7: "DCS Request Additional Block Write Payload Packet",
    0x8: "DCS Reply Additional Block Read Payload Packet",
}


class Mu2eViewer(tk.Tk):
    def __init__(self, yaml_dir: str):
        super().__init__()
        self.title("Mu2e Data Format Viewer")
        self.geometry("1280x820")
        self.minsize(800, 600)

        self.yaml_dir = yaml_dir
        self.formats: dict = load_yaml_formats(yaml_dir)
        self.data_bytes: bytes = b""
        self.little_endian = tk.BooleanVar(value=False)
        self._field_details: dict = {}   # treeview iid → field result dict
        self._server_socket: socket.socket | None = None

        self._apply_fonts()
        self._build_ui()
        self._refresh_format_list()

    # ------------------------------------------------------------------
    # Fonts
    # ------------------------------------------------------------------

    def _apply_fonts(self):
        """Apply a fixed-width font to all ttk widgets and the root window."""
        style = ttk.Style(self)
        # "." is the root style — all ttk widgets inherit from it
        style.configure(".",              font=("Courier", 11))
        style.configure("Treeview",       font=("Courier", 10))
        style.configure("Treeview.Heading", font=("Courier", 10, "bold"))
        # Combobox drop-down list uses the Listbox widget (not ttk); set via option_add
        self.option_add("*TCombobox*Listbox.font", ("Courier", 11))

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        self._build_toolbar()
        self._build_panes()

    def _build_toolbar(self):
        bar = ttk.Frame(self, padding=(4, 2))
        bar.pack(fill=tk.X, side=tk.TOP)

        # Format selector
        ttk.Label(bar, text="Packet format:").pack(side=tk.LEFT)
        self.format_var = tk.StringVar()
        self.format_combo = ttk.Combobox(
            bar, textvariable=self.format_var, width=38, state="readonly"
        )
        self.format_combo.pack(side=tk.LEFT, padx=(2, 8))
        self.format_combo.bind("<<ComboboxSelected>>", lambda _e: self._refresh_display())

        _sep(bar)

        # Display mode
        ttk.Label(bar, text="Values:").pack(side=tk.LEFT)
        self.display_mode = tk.StringVar(value="hex")
        for label, val in (("Hex", "hex"), ("Binary", "bin"), ("Decimal", "dec")):
            ttk.Radiobutton(
                bar, text=label, variable=self.display_mode, value=val,
                command=self._refresh_display
            ).pack(side=tk.LEFT)

        _sep(bar)

        ttk.Checkbutton(
            bar, text="Little-endian words",
            variable=self.little_endian, command=self._refresh_display
        ).pack(side=tk.LEFT)

        _sep(bar)

        ttk.Button(bar, text="Load file…", command=self._load_file).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="Auto-detect type", command=self._auto_detect).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="Clear", command=self._clear).pack(side=tk.LEFT, padx=2)

        _sep(bar)

        # Decode offset
        ttk.Label(bar, text="Offset (bytes):").pack(side=tk.LEFT)
        self.offset_var = tk.StringVar(value="0")
        offset_spin = ttk.Spinbox(
            bar, textvariable=self.offset_var, from_=0, to=65535,
            width=6, command=self._refresh_display,
        )
        offset_spin.pack(side=tk.LEFT, padx=2)
        offset_spin.bind("<Return>",   lambda _e: self._refresh_display())
        offset_spin.bind("<FocusOut>", lambda _e: self._refresh_display())

        _sep(bar)

        # Socket listener
        ttk.Label(bar, text="TCP port:").pack(side=tk.LEFT)
        self.port_var = tk.StringVar(value="7755")
        ttk.Entry(bar, textvariable=self.port_var, width=6).pack(side=tk.LEFT, padx=2)
        self.listen_btn = ttk.Button(bar, text="Start listening", command=self._toggle_server)
        self.listen_btn.pack(side=tk.LEFT, padx=2)

        self.status_var = tk.StringVar(value="No data")
        ttk.Label(bar, textvariable=self.status_var, foreground="gray").pack(
            side=tk.LEFT, padx=8
        )

    def _build_panes(self):
        paned = ttk.PanedWindow(self, orient=tk.VERTICAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 4))

        # ── Raw hex input ──────────────────────────────────────────────
        input_frame = ttk.LabelFrame(paned, text="Raw bytes  (hex input)", padding=4)
        paned.add(input_frame, weight=1)

        ttk.Label(
            input_frame,
            text="Enter hex bytes separated by spaces (e.g.  10 00 80 50  or  0x10 0x00 …)",
            foreground="gray", font=("Courier", 10),
        ).pack(side=tk.BOTTOM, anchor=tk.W)

        sb_in = ttk.Scrollbar(input_frame, orient=tk.VERTICAL)
        sb_in.pack(side=tk.RIGHT, fill=tk.Y)

        self.hex_input = tk.Text(
            input_frame, height=4, font=("Courier", 11), wrap=tk.WORD,
            undo=True, yscrollcommand=sb_in.set,
        )
        sb_in.config(command=self.hex_input.yview)
        self.hex_input.pack(fill=tk.BOTH, expand=True)
        self.hex_input.bind("<KeyRelease>", lambda _e: self._refresh_display())
        self.hex_input.bind("<Button-1>", self._on_hex_click)
        self.hex_input.tag_configure(
            "offset_mark", foreground="red", font=("Courier", 11, "bold")
        )

        # ── Field breakdown tree ───────────────────────────────────────
        breakdown_frame = ttk.LabelFrame(paned, text="Field breakdown", padding=4)
        paned.add(breakdown_frame, weight=4)

        cols = ("field", "word", "bits", "hex", "binary", "decimal", "decoded")
        self.tree = ttk.Treeview(
            breakdown_frame, columns=cols, show="headings", selectmode="browse"
        )
        for col, heading, width, anchor in (
            ("field",   "Field Name",             220, tk.E),
            ("word",    "Word",                    48, tk.E),
            ("bits",    "Bits",                    60, tk.E),
            ("hex",     "Hex",                     80, tk.E),
            ("binary",  "Binary",                 160, tk.E),
            ("decimal", "Dec",                     60, tk.E),
            ("decoded", "Decoded / Description",  500, tk.E),
        ):
            self.tree.heading(col, text=heading, anchor=tk.E, command=lambda c=col: None)
            self.tree.column(col, width=width, minwidth=40, anchor=anchor)

        vsb = ttk.Scrollbar(breakdown_frame, orient=tk.VERTICAL, command=self.tree.yview)
        hsb = ttk.Scrollbar(breakdown_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        breakdown_frame.rowconfigure(0, weight=1)
        breakdown_frame.columnconfigure(0, weight=1)

        # Row colour tags
        self.tree.tag_configure("section",  background="#d0e8ff", font=("Courier", 10, "bold"))
        self.tree.tag_configure("ok",       background="white")
        self.tree.tag_configure("fixed_ok", background="#e8f5e9")
        self.tree.tag_configure("error",    background="#ffcccc")
        self.tree.tag_configure("reserved", foreground="#888888")

        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        # ── Detail panel ───────────────────────────────────────────────
        detail_frame = ttk.LabelFrame(paned, text="Field detail", padding=4)
        paned.add(detail_frame, weight=1)

        self.detail_text = tk.Text(
            detail_frame, height=6, wrap=tk.WORD,
            font=("Courier", 10), state=tk.DISABLED,
            background="#f8f8f8"
        )
        sb_det = ttk.Scrollbar(detail_frame, command=self.detail_text.yview)
        self.detail_text.config(yscrollcommand=sb_det.set)
        self.detail_text.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        sb_det.pack(side=tk.RIGHT, fill=tk.Y)

    # ------------------------------------------------------------------
    # Format list management
    # ------------------------------------------------------------------

    def _byte_token_positions(self) -> list[tuple[str, str]]:
        """
        Return a list of (start_index, end_index) tk text widget indices,
        one entry per hex byte token in self.hex_input.
        Handles wrapped lines correctly by walking the raw character string.
        """
        text = self.hex_input.get("1.0", tk.END)
        positions = []
        i = 0
        while i < len(text):
            # skip whitespace
            while i < len(text) and text[i] in " \t\n\r":
                i += 1
            if i >= len(text):
                break
            token_start = i
            while i < len(text) and text[i] not in " \t\n\r":
                i += 1
            token_end = i
            if token_end > token_start:
                # Convert absolute char offsets → "line.col" tk indices
                before_start = text[:token_start]
                line_s = before_start.count("\n") + 1
                col_s  = token_start - (before_start.rfind("\n") + 1)

                before_end = text[:token_end]
                line_e = before_end.count("\n") + 1
                col_e  = token_end - (before_end.rfind("\n") + 1)

                positions.append((f"{line_s}.{col_s}", f"{line_e}.{col_e}"))
        return positions

    def _on_hex_click(self, event: tk.Event) -> None:
        """Set the decode offset to whichever byte token the user clicked."""
        click_idx = self.hex_input.index(f"@{event.x},{event.y}")
        for byte_idx, (start, end) in enumerate(self._byte_token_positions()):
            if (self.hex_input.compare(click_idx, ">=", start) and
                    self.hex_input.compare(click_idx, "<", end)):
                self.offset_var.set(str(byte_idx))
                self._refresh_display()
                return

    def _highlight_offset(self, offset: int) -> None:
        """Colour the 16-bit word (two bytes) at *offset* red in the hex input."""
        self.hex_input.tag_remove("offset_mark", "1.0", tk.END)
        if offset < 0:
            return
        positions = self._byte_token_positions()
        # Highlight the two bytes that form the 16-bit word at the offset
        for byte_idx in (offset, offset + 1):
            if byte_idx < len(positions):
                start, end = positions[byte_idx]
                self.hex_input.tag_add("offset_mark", start, end)

    def _refresh_format_list(self):
        names = sorted(self.formats.keys())
        self.format_combo["values"] = names
        if names:
            self.format_combo.set(names[0])

    # ------------------------------------------------------------------
    # Display / parsing
    # ------------------------------------------------------------------

    def _fmt(self, value: int, size_bits: int) -> str:
        """Format *value* according to the current display mode."""
        mode = self.display_mode.get()
        if mode == "hex":
            digits = max(1, (size_bits + 3) // 4)
            return f"0x{value:0{digits}X}"
        if mode == "bin":
            return f"{value:0{size_bits}b}"
        return str(value)

    def _refresh_display(self):
        self.tree.delete(*self.tree.get_children())
        self._field_details.clear()

        raw_text = self.hex_input.get("1.0", tk.END).strip()
        if not raw_text:
            self.status_var.set("No data")
            return

        try:
            data = hex_str_to_bytes(raw_text)
        except ValueError as exc:
            self.status_var.set(f"Parse error: {exc}")
            return

        self.data_bytes = data

        # Decode offset
        try:
            offset = max(0, int(self.offset_var.get()))
        except ValueError:
            offset = 0
        self._highlight_offset(offset)
        data = data[offset:]

        self.status_var.set(
            f"{len(self.data_bytes)} bytes  |  decoding from offset {offset}"
        )

        fmt_name = self.format_var.get()
        if not fmt_name or fmt_name not in self.formats:
            return

        fmt = self.formats[fmt_name]
        le = self.little_endian.get()

        # Collect sections to display.  Some formats have top-level 'fields';
        # others (e.g. tracker) have 'packet_1', 'packet_2' sub-dicts.
        sections: list[tuple[str, list]] = []
        if "fields" in fmt:
            sections.append(("", fmt["fields"]))
        for key in ("packet_1", "packet_2"):
            sub = fmt.get(key)
            if isinstance(sub, dict) and "fields" in sub:
                label = sub.get("description", key.replace("_", " ").title())
                sections.append((label, sub["fields"]))

        for section_label, fields in sections:
            if section_label:
                self.tree.insert(
                    "", tk.END,
                    values=(f"  {section_label}", "", "", "", "", "", ""),
                    tags=("section",),
                )

            for item in parse_fields(data, fields, le):
                value = item["value"]
                size_bits = item["size_bits"]

                hex_val = f"0x{value:0{max(1,(size_bits+3)//4)}X}"
                bin_val = f"{value:0{size_bits}b}"
                dec_val = str(value)

                decoded = decode_value(value, item)

                # Tag / error checking
                tag = "ok"
                fv = item["fixed_value"]
                if fv is not None:
                    try:
                        expected = int(str(fv), 0) if isinstance(fv, str) else int(fv)
                    except (ValueError, TypeError):
                        expected = fv
                    if value != expected:
                        tag = "error"
                        decoded = f"ERROR: expected 0x{expected:X}"
                    else:
                        tag = "fixed_ok"
                elif "reserved" in item["name"].lower():
                    tag = "reserved"

                iid = self.tree.insert(
                    "", tk.END,
                    values=(
                        item["name"], item["word"], item["bits"],
                        hex_val, bin_val, dec_val,
                        decoded,
                    ),
                    tags=(tag,),
                )
                self._field_details[iid] = item

    def _on_tree_select(self, _event):
        sel = self.tree.selection()
        if not sel:
            return
        item = self._field_details.get(sel[0])
        if not item:
            return

        value = item["value"]
        size_bits = item["size_bits"]
        decoded = decode_value(value, item)

        lines = [
            f"Field:      {item['name']}",
            f"Location:   Word {item['word']}  (byte offset {item['byte_offset']} / "
            f"0x{item['byte_offset']:02X}),  bits [{item['bits']}],  {size_bits} bit(s)",
            f"Value:      0x{value:0{max(1,(size_bits+3)//4)}X}"
            f"  =  {value}  =  {value:0{size_bits}b}b",
        ]
        if decoded:
            lines.append(f"Decoded:    {decoded}")
        lines.append("")
        if item["description"]:
            lines.append(item["description"])

        vals = item["values"]
        if vals:
            lines.append("")
            lines.append("Defined values:")
            for k, v in vals.items():
                lines.append(f"  {k!s:8s} → {v}")

        subs = item["subfields"]
        if subs:
            lines.append("")
            lines.append("Subfields:")
            for sf in subs:
                desc = str(sf.get("description", "")).strip()
                if len(desc) > 80:
                    desc = desc[:77] + "…"
                lines.append(f"  [{sf.get('bits', ''):5s}]  {sf.get('name', '')}:  {desc}")

        self.detail_text.config(state=tk.NORMAL)
        self.detail_text.delete("1.0", tk.END)
        self.detail_text.insert("1.0", "\n".join(lines))
        self.detail_text.config(state=tk.DISABLED)

    # ------------------------------------------------------------------
    # Packet-type auto-detection
    # ------------------------------------------------------------------

    def _auto_detect(self):
        if len(self.data_bytes) < 4:
            messagebox.showinfo("Auto-detect", "Need at least 4 bytes of data.")
            return
        le = self.little_endian.get()
        w1 = get_word(self.data_bytes, 1, le)
        if w1 is None:
            return
        ptype = (w1 >> 4) & 0xF
        candidate = PACKET_TYPE_MAP.get(ptype)
        if candidate and candidate in self.formats:
            self.format_var.set(candidate)
            self._refresh_display()
            self.status_var.set(f"Auto-detected: {candidate}  (type 0x{ptype:X})")
        else:
            self.status_var.set(f"Unknown packet type 0x{ptype:X}")

    # ------------------------------------------------------------------
    # File loading
    # ------------------------------------------------------------------

    def _load_file(self):
        path = filedialog.askopenfilename(
            title="Load binary data file",
            filetypes=[
                ("Binary / raw files", "*.bin *.dat *.raw"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        with open(path, "rb") as fh:
            data = fh.read()
        self._set_bytes(data)

    def _set_bytes(self, data: bytes):
        hex_str = " ".join(f"{b:02X}" for b in data)
        self.hex_input.delete("1.0", tk.END)
        self.hex_input.insert("1.0", hex_str)
        self._refresh_display()

    def _clear(self):
        self.hex_input.delete("1.0", tk.END)
        self.data_bytes = b""
        self.tree.delete(*self.tree.get_children())
        self._field_details.clear()
        self.detail_text.config(state=tk.NORMAL)
        self.detail_text.delete("1.0", tk.END)
        self.detail_text.config(state=tk.DISABLED)
        self.status_var.set("No data")

    # ------------------------------------------------------------------
    # TCP socket server (receives raw bytes from external application)
    # ------------------------------------------------------------------

    def _toggle_server(self):
        if self._server_socket:
            self._stop_server()
        else:
            self._start_server()

    def _start_server(self):
        try:
            port = int(self.port_var.get())
        except ValueError:
            messagebox.showerror("Error", "Invalid port number.")
            return
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind(("0.0.0.0", port))
            srv.listen(5)
            self._server_socket = srv
            threading.Thread(target=self._accept_loop, daemon=True).start()
            self.listen_btn.config(text="Stop listening")
            self.status_var.set(f"Listening on TCP port {port}…")
        except OSError as exc:
            messagebox.showerror("Error", f"Could not start server:\n{exc}")

    def _stop_server(self):
        if self._server_socket:
            try:
                self._server_socket.close()
            except Exception:
                pass
            self._server_socket = None
        self.listen_btn.config(text="Start listening")
        self.status_var.set("Server stopped.")

    def _accept_loop(self):
        while self._server_socket:
            try:
                conn, _addr = self._server_socket.accept()
                threading.Thread(
                    target=self._handle_conn, args=(conn,), daemon=True
                ).start()
            except Exception:
                break

    def _handle_conn(self, conn: socket.socket):
        try:
            chunks = []
            while True:
                chunk = conn.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
            payload = b"".join(chunks)
            if payload:
                # Schedule UI update on the main thread
                self.after(0, lambda d=payload: self._on_socket_data(d))
        except Exception:
            pass
        finally:
            conn.close()

    def _on_socket_data(self, data: bytes):
        self._set_bytes(data)
        self._auto_detect()
        self.status_var.set(f"Received {len(data)} bytes via TCP")


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _sep(parent):
    ttk.Separator(parent, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6, pady=2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    yaml_directory = sys.argv[1] if len(sys.argv) > 1 else YAML_DIR
    app = Mu2eViewer(yaml_directory)
    app.mainloop()
