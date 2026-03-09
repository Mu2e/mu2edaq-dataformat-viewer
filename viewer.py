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
from pathlib import Path

try:
    import yaml
except ImportError:
    print("PyYAML is required.  Install with:  pip install pyyaml")
    sys.exit(1)

try:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QSplitter,
        QGroupBox, QTreeWidget, QTreeWidgetItem, QPlainTextEdit, QTextEdit,
        QToolBar, QLabel, QComboBox, QRadioButton, QButtonGroup, QCheckBox,
        QPushButton, QSpinBox, QLineEdit, QFileDialog, QMessageBox,
        QVBoxLayout, QHBoxLayout, QSizePolicy, QMenu,
    )
    from PyQt6.QtCore import (
        Qt, QObject, pyqtSignal, QTimer, QMetaObject, Q_ARG,
    )
    from PyQt6.QtGui import (
        QFont, QColor, QBrush, QTextCharFormat, QTextCursor, QActionGroup,
    )
    from PyQt6.QtWidgets import QStyleFactory
except ImportError:
    print("PyQt6 is required.  Install with:  pip install PyQt6")
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


class _Receiver(QObject):
    """Helper QObject used to marshal data from TCP worker threads to the main thread."""
    data_received = pyqtSignal(bytes)


class Mu2eViewer(QMainWindow):
    def __init__(self, yaml_dir: str):
        super().__init__()
        self.setWindowTitle("Mu2e Data Format Viewer")
        self.resize(1280, 820)
        self.setMinimumSize(800, 600)

        self.yaml_dir = yaml_dir
        self.formats: dict = load_yaml_formats(yaml_dir)
        self.data_bytes: bytes = b""
        self._little_endian: bool = False
        self._field_details: dict = {}   # tree item id → field result dict
        self._server_socket: socket.socket | None = None

        # Cross-thread signal for TCP data
        self._receiver = _Receiver()
        self._receiver.data_received.connect(self._on_socket_data)

        self._font_size = 11
        self._build_ui()
        self._refresh_format_list()

    # ------------------------------------------------------------------
    # Font helpers
    # ------------------------------------------------------------------

    def _f(self, delta: int = 0, bold: bool = False) -> QFont:
        """Return a Courier font at the current size plus *delta*."""
        f = QFont("Courier", self._font_size + delta)
        if bold:
            f.setBold(True)
        return f

    def _on_font_size_changed(self):
        self._font_size_label.setText(str(self._font_size))
        QApplication.instance().setFont(self._f())
        self._refresh_display()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        self._build_menu()
        self._build_toolbar()
        self._build_central()

    def _build_menu(self):
        menu_bar = self.menuBar()

        # ── View menu ─────────────────────────────────────────────────
        view_menu = menu_bar.addMenu("View")

        style_menu = view_menu.addMenu("Style")
        style_group = QActionGroup(self)
        style_group.setExclusive(True)
        current_style = QApplication.instance().style().objectName().lower()
        for name in sorted(QStyleFactory.keys()):
            action = style_menu.addAction(name)
            action.setCheckable(True)
            action.setChecked(name.lower() == current_style)
            style_group.addAction(action)
            action.triggered.connect(
                lambda checked, s=name: QApplication.instance().setStyle(s)
            )

    def _build_toolbar(self):
        bar = self.addToolBar("Main")
        bar.setMovable(False)
        bar.setFloatable(False)

        # Format selector
        bar.addWidget(QLabel("  Packet format: "))
        self.format_combo = QComboBox()
        self.format_combo.setFont(self._f())
        self.format_combo.setMinimumWidth(300)
        self.format_combo.currentIndexChanged.connect(lambda _: self._refresh_display())
        bar.addWidget(self.format_combo)

        bar.addSeparator()

        # Display mode
        bar.addWidget(QLabel("  Values: "))
        self._display_mode_group = QButtonGroup(self)
        for label, val in (("Hex", "hex"), ("Binary", "bin"), ("Decimal", "dec")):
            rb = QRadioButton(label)
            rb.setProperty("mode_value", val)
            rb.setFont(self._f())
            if val == "hex":
                rb.setChecked(True)
            self._display_mode_group.addButton(rb)
            bar.addWidget(rb)
        self._display_mode_group.buttonClicked.connect(lambda _: self._refresh_display())

        bar.addSeparator()

        self._le_check = QCheckBox("Little-endian words")
        self._le_check.setFont(self._f())
        self._le_check.stateChanged.connect(lambda _: self._on_le_changed())
        bar.addWidget(self._le_check)

        bar.addSeparator()

        btn_load = QPushButton("Load file\u2026")
        btn_load.setFont(self._f())
        btn_load.clicked.connect(self._load_file)
        bar.addWidget(btn_load)

        btn_auto = QPushButton("Auto-detect type")
        btn_auto.setFont(self._f())
        btn_auto.clicked.connect(self._auto_detect)
        bar.addWidget(btn_auto)

        btn_clear = QPushButton("Clear")
        btn_clear.setFont(self._f())
        btn_clear.clicked.connect(self._clear)
        bar.addWidget(btn_clear)

        bar.addSeparator()

        # Decode offset
        bar.addWidget(QLabel("  Offset (bytes): "))
        self._offset_spin = QSpinBox()
        self._offset_spin.setFont(self._f())
        self._offset_spin.setRange(0, 65535)
        self._offset_spin.setValue(0)
        self._offset_spin.valueChanged.connect(lambda _: self._refresh_display())
        bar.addWidget(self._offset_spin)

        bar.addSeparator()

        # Socket listener
        bar.addWidget(QLabel("  TCP port: "))
        self._port_edit = QLineEdit("7755")
        self._port_edit.setFont(self._f())
        self._port_edit.setFixedWidth(60)
        bar.addWidget(self._port_edit)

        self._listen_btn = QPushButton("Start listening")
        self._listen_btn.setFont(self._f())
        self._listen_btn.clicked.connect(self._toggle_server)
        bar.addWidget(self._listen_btn)

        bar.addSeparator()

        self._status_label = QLabel("No data")
        self._status_label.setFont(self._f())
        self._status_label.setStyleSheet("color: gray;")
        bar.addWidget(self._status_label)

        bar.addSeparator()

        bar.addWidget(QLabel("  Font: "))

        btn_font_minus = QPushButton("A-")
        btn_font_minus.clicked.connect(lambda: (
            setattr(self, '_font_size', max(7, self._font_size - 1)),
            self._on_font_size_changed(),
        ))
        bar.addWidget(btn_font_minus)

        self._font_size_label = QLabel(str(self._font_size))
        bar.addWidget(self._font_size_label)

        btn_font_plus = QPushButton("A+")
        btn_font_plus.clicked.connect(lambda: (
            setattr(self, '_font_size', min(24, self._font_size + 1)),
            self._on_font_size_changed(),
        ))
        bar.addWidget(btn_font_plus)

    def _build_central(self):
        splitter = QSplitter(Qt.Orientation.Vertical)
        self.setCentralWidget(splitter)

        # ── Raw hex input ──────────────────────────────────────────────
        input_group = QGroupBox("Raw bytes  (hex input)")
        input_group.setFont(self._f())
        input_layout = QVBoxLayout(input_group)
        input_layout.setContentsMargins(4, 4, 4, 4)

        self.hex_input = QPlainTextEdit()
        self.hex_input.setFont(self._f())
        self.hex_input.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.hex_input.textChanged.connect(self._refresh_display)
        self.hex_input.mousePressEvent = self._on_hex_mouse_press
        input_layout.addWidget(self.hex_input)

        hint = QLabel(
            "Enter hex bytes separated by spaces (e.g.  10 00 80 50  or  0x10 0x00 \u2026)"
        )
        hint.setFont(self._f(-1))
        hint.setStyleSheet("color: gray;")
        input_layout.addWidget(hint)

        splitter.addWidget(input_group)

        # ── Field breakdown tree ───────────────────────────────────────
        breakdown_group = QGroupBox("Field breakdown")
        breakdown_group.setFont(self._f())
        breakdown_layout = QVBoxLayout(breakdown_group)
        breakdown_layout.setContentsMargins(4, 4, 4, 4)

        self.tree = QTreeWidget()
        self.tree.setFont(self._f(-1))
        self.tree.setColumnCount(7)
        self.tree.setHeaderLabels(
            ["Field Name", "Word", "Bits", "Hex", "Binary", "Dec", "Decoded / Description"]
        )

        # Right-align all column headers except the last (Decoded / Description)
        header = self.tree.header()
        header.setFont(self._f(-1))
        header.setDefaultAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.tree.headerItem().setTextAlignment(
            6, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )

        # Column widths
        for col, width in enumerate((220, 48, 60, 80, 160, 60, 500)):
            self.tree.setColumnWidth(col, width)

        self.tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self.tree.itemSelectionChanged.connect(self._on_tree_select)
        breakdown_layout.addWidget(self.tree)

        splitter.addWidget(breakdown_group)

        # ── Detail panel ───────────────────────────────────────────────
        detail_group = QGroupBox("Field detail")
        detail_group.setFont(self._f())
        detail_layout = QVBoxLayout(detail_group)
        detail_layout.setContentsMargins(4, 4, 4, 4)

        self.detail_text = QTextEdit()
        self.detail_text.setFont(self._f(-1))
        self.detail_text.setReadOnly(True)
        self.detail_text.setStyleSheet("background-color: #f8f8f8;")
        detail_layout.addWidget(self.detail_text)

        splitter.addWidget(detail_group)

        # Splitter proportions: hex input small, tree large, detail small
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)
        splitter.setStretchFactor(2, 1)

    # ------------------------------------------------------------------
    # Format list management
    # ------------------------------------------------------------------

    def _refresh_format_list(self):
        names = sorted(self.formats.keys())
        self.format_combo.blockSignals(True)
        self.format_combo.clear()
        for name in names:
            self.format_combo.addItem(name)
        self.format_combo.blockSignals(False)
        if names:
            self.format_combo.setCurrentIndex(0)

    # ------------------------------------------------------------------
    # Hex input: byte token positions and click handling
    # ------------------------------------------------------------------

    def _byte_token_positions(self) -> list[tuple[int, int]]:
        """
        Return a list of (start_char_pos, end_char_pos) absolute character
        offsets in the plain text, one entry per hex byte token.
        """
        text = self.hex_input.toPlainText()
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
                positions.append((token_start, token_end))
        return positions

    def _on_hex_mouse_press(self, event) -> None:
        """Override for hex_input.mousePressEvent — sets offset to clicked byte."""
        # Let the widget handle the click first (moves cursor)
        QPlainTextEdit.mousePressEvent(self.hex_input, event)

        cursor = self.hex_input.cursorForPosition(event.pos())
        click_pos = cursor.position()

        for byte_idx, (start, end) in enumerate(self._byte_token_positions()):
            if start <= click_pos < end:
                self._offset_spin.setValue(byte_idx)
                # _refresh_display will be called via valueChanged signal
                return

    def _highlight_offset(self, offset: int) -> None:
        """Colour the 16-bit word (two bytes) at *offset* red+bold in the hex input."""
        # Use ExtraSelections so we don't disturb the user's own cursor/selection
        selections = []

        if offset >= 0:
            positions = self._byte_token_positions()
            fmt = QTextCharFormat()
            fmt.setForeground(QColor("red"))
            fmt.setFontWeight(QFont.Weight.Bold)

            for byte_idx in (offset, offset + 1):
                if byte_idx < len(positions):
                    start, end = positions[byte_idx]
                    sel = QTextEdit.ExtraSelection()
                    cursor = self.hex_input.textCursor()
                    cursor.setPosition(start)
                    cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
                    sel.cursor = cursor
                    sel.format = fmt
                    selections.append(sel)

        self.hex_input.setExtraSelections(selections)

    # ------------------------------------------------------------------
    # Display / parsing
    # ------------------------------------------------------------------

    def _display_mode(self) -> str:
        """Return the currently selected display mode string: 'hex', 'bin', or 'dec'."""
        checked = self._display_mode_group.checkedButton()
        if checked is not None:
            return checked.property("mode_value")
        return "hex"

    def _on_le_changed(self):
        self._little_endian = self._le_check.isChecked()
        self._refresh_display()

    def _fmt(self, value: int, size_bits: int) -> str:
        """Format *value* according to the current display mode."""
        mode = self._display_mode()
        if mode == "hex":
            digits = max(1, (size_bits + 3) // 4)
            return f"0x{value:0{digits}X}"
        if mode == "bin":
            return f"{value:0{size_bits}b}"
        return str(value)

    def _set_status(self, text: str):
        self._status_label.setText(text)

    def _refresh_display(self):
        self.tree.clear()
        self._field_details.clear()

        raw_text = self.hex_input.toPlainText().strip()
        if not raw_text:
            self._set_status("No data")
            self.hex_input.setExtraSelections([])
            return

        try:
            data = hex_str_to_bytes(raw_text)
        except ValueError as exc:
            self._set_status(f"Parse error: {exc}")
            return

        self.data_bytes = data

        # Decode offset
        offset = max(0, self._offset_spin.value())
        self._highlight_offset(offset)
        data = data[offset:]

        self._set_status(
            f"{len(self.data_bytes)} bytes  |  decoding from offset {offset}"
        )

        fmt_name = self.format_combo.currentText()
        if not fmt_name or fmt_name not in self.formats:
            return

        fmt = self.formats[fmt_name]
        le = self._little_endian

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

        # Colours / brushes
        brush_white   = QBrush(QColor("white"))
        brush_green   = QBrush(QColor("#e8f5e9"))
        brush_red     = QBrush(QColor("#ffcccc"))
        brush_blue    = QBrush(QColor("#d0e8ff"))
        brush_grey_fg = QBrush(QColor("#888888"))

        align_right = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        align_left  = Qt.AlignmentFlag.AlignLeft  | Qt.AlignmentFlag.AlignVCenter
        bold_font   = self._f(-1, bold=True)
        normal_font = self._f(-1)

        for section_label, fields in sections:
            if section_label:
                sec_item = QTreeWidgetItem(self.tree)
                sec_item.setText(0, f"  {section_label}")
                sec_item.setFont(0, bold_font)
                for col in range(7):
                    sec_item.setTextAlignment(col, align_left if col == 6 else align_right)
                    sec_item.setBackground(col, brush_blue)
                    sec_item.setFont(col, bold_font)

            for item in parse_fields(data, fields, le):
                value     = item["value"]
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

                row_item = QTreeWidgetItem(self.tree)
                row_item.setText(0, item["name"])
                row_item.setText(1, str(item["word"]))
                row_item.setText(2, item["bits"])
                row_item.setText(3, hex_val)
                row_item.setText(4, bin_val)
                row_item.setText(5, dec_val)
                row_item.setText(6, decoded)

                for col in range(7):
                    row_item.setTextAlignment(col, align_left if col == 6 else align_right)
                    row_item.setFont(col, normal_font)

                # Apply row colouring
                if tag == "fixed_ok":
                    for col in range(7):
                        row_item.setBackground(col, brush_green)
                elif tag == "error":
                    for col in range(7):
                        row_item.setBackground(col, brush_red)
                elif tag == "reserved":
                    for col in range(7):
                        row_item.setForeground(col, brush_grey_fg)
                else:
                    for col in range(7):
                        row_item.setBackground(col, brush_white)

                # Store field detail, keyed by the item object id
                self._field_details[id(row_item)] = (row_item, item)

    def _on_tree_select(self):
        selected = self.tree.selectedItems()
        if not selected:
            return
        row_item = selected[0]
        entry = self._field_details.get(id(row_item))
        if not entry:
            return
        _, item = entry

        value     = item["value"]
        size_bits = item["size_bits"]
        decoded   = decode_value(value, item)

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
                lines.append(f"  {k!s:8s} \u2192 {v}")

        subs = item["subfields"]
        if subs:
            lines.append("")
            lines.append("Subfields:")
            for sf in subs:
                desc = str(sf.get("description", "")).strip()
                if len(desc) > 80:
                    desc = desc[:77] + "\u2026"
                lines.append(f"  [{sf.get('bits', ''):5s}]  {sf.get('name', '')}:  {desc}")

        self.detail_text.setPlainText("\n".join(lines))

    # ------------------------------------------------------------------
    # Packet-type auto-detection
    # ------------------------------------------------------------------

    def _auto_detect(self):
        if len(self.data_bytes) < 4:
            QMessageBox.information(self, "Auto-detect", "Need at least 4 bytes of data.")
            return
        le = self._little_endian
        w1 = get_word(self.data_bytes, 1, le)
        if w1 is None:
            return
        ptype = (w1 >> 4) & 0xF
        candidate = PACKET_TYPE_MAP.get(ptype)
        if candidate and candidate in self.formats:
            # Block signals to avoid double refresh, then set and refresh once
            self.format_combo.blockSignals(True)
            idx = self.format_combo.findText(candidate)
            if idx >= 0:
                self.format_combo.setCurrentIndex(idx)
            self.format_combo.blockSignals(False)
            self._refresh_display()
            self._set_status(f"Auto-detected: {candidate}  (type 0x{ptype:X})")
        else:
            self._set_status(f"Unknown packet type 0x{ptype:X}")

    # ------------------------------------------------------------------
    # File loading
    # ------------------------------------------------------------------

    def _load_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load binary data file",
            "",
            "Binary / raw files (*.bin *.dat *.raw);;All files (*.*)",
        )
        if not path:
            return
        with open(path, "rb") as fh:
            data = fh.read()
        self._set_bytes(data)

    def _set_bytes(self, data: bytes):
        hex_str = " ".join(f"{b:02X}" for b in data)
        # Block textChanged signal to avoid double refresh
        self.hex_input.blockSignals(True)
        self.hex_input.setPlainText(hex_str)
        self.hex_input.blockSignals(False)
        self._refresh_display()

    def _clear(self):
        self.hex_input.blockSignals(True)
        self.hex_input.clear()
        self.hex_input.blockSignals(False)
        self.hex_input.setExtraSelections([])
        self.data_bytes = b""
        self.tree.clear()
        self._field_details.clear()
        self.detail_text.clear()
        self._set_status("No data")

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
            port = int(self._port_edit.text())
        except ValueError:
            QMessageBox.critical(self, "Error", "Invalid port number.")
            return
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind(("0.0.0.0", port))
            srv.listen(5)
            self._server_socket = srv
            threading.Thread(target=self._accept_loop, daemon=True).start()
            self._listen_btn.setText("Stop listening")
            self._set_status(f"Listening on TCP port {port}\u2026")
        except OSError as exc:
            QMessageBox.critical(self, "Error", f"Could not start server:\n{exc}")

    def _stop_server(self):
        if self._server_socket:
            try:
                self._server_socket.close()
            except Exception:
                pass
            self._server_socket = None
        self._listen_btn.setText("Start listening")
        self._set_status("Server stopped.")

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
                # Emit signal — Qt marshals this safely to the main thread
                self._receiver.data_received.emit(payload)
        except Exception:
            pass
        finally:
            conn.close()

    def _on_socket_data(self, data: bytes):
        self._set_bytes(data)
        self._auto_detect()
        self._set_status(f"Received {len(data)} bytes via TCP")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    yaml_directory = sys.argv[1] if len(sys.argv) > 1 else YAML_DIR
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = Mu2eViewer(yaml_directory)
    window.show()
    sys.exit(app.exec())
