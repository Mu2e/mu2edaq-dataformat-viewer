#!/usr/bin/env python3
"""
Mu2e Data Format Sender
=======================
Companion to viewer.py.  Lets you construct a Mu2e ROC packet field-by-field
using the same YAML format definitions, then send the assembled bytes to the
viewer over a TCP socket.
"""

from __future__ import annotations

import argparse
import os
import sys
import socket
from pathlib import Path

import config as _config

try:
    import yaml
except ImportError:
    print("PyYAML is required.  Install with:  pip install pyyaml")
    sys.exit(1)

try:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QSplitter,
        QGroupBox, QTextEdit, QToolBar, QLabel, QComboBox, QCheckBox,
        QPushButton, QLineEdit, QMessageBox, QFileDialog,
        QScrollArea, QGridLayout, QVBoxLayout, QSizePolicy,
        QMenu, QStyleFactory,
    )
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QFont, QActionGroup
except ImportError:
    print("PyQt6 is required.  Install with:  pip install PyQt6")
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
# Per-field row
# ---------------------------------------------------------------------------

class FieldRow:
    """One row in the fields panel representing a single packet field."""

    COL_NAME  = 0
    COL_WORD  = 1
    COL_BITS  = 2
    COL_ENTRY = 3
    COL_DESC  = 4

    def __init__(self, grid: QGridLayout, row_idx: int, field: dict,
                 on_change, mono_font: QFont, mono_sm_font: QFont):
        self.field = field
        self._enum_map: dict[str, int] = {}  # display string → integer value
        self._widget = None

        name     = field.get("name", "?")
        bits     = str(field.get("bits", "?"))
        word     = str(field.get("word", "?"))
        desc     = str(field.get("description", "")).replace("\n", " ").strip()
        fv       = field.get("fixed_value")
        vals     = field.get("values") or {}
        size     = int(field.get("size_bits", 1))
        reserved = "reserved" in name.lower()

        fg_color = "#888888" if reserved else ""

        def _make_label(text, font=mono_sm_font):
            lbl = QLabel(text)
            lbl.setFont(font)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if fg_color:
                lbl.setStyleSheet(f"color: {fg_color};")
            return lbl

        grid.addWidget(_make_label(name), row_idx, self.COL_NAME)
        grid.addWidget(_make_label(word), row_idx, self.COL_WORD)
        grid.addWidget(_make_label(bits), row_idx, self.COL_BITS)

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

            widget = QComboBox()
            widget.setFont(mono_sm_font)
            widget.setEditable(False)
            for opt in display_opts:
                widget.addItem(opt)
            if display_opts:
                widget.setCurrentIndex(0)
            if fv is not None:
                widget.setEnabled(False)
            widget.currentIndexChanged.connect(lambda _: on_change())
            self._widget = widget
        else:
            widget = QLineEdit()
            widget.setFont(mono_sm_font)
            if fv is not None:
                try:
                    fv_int = parse_int(str(fv))
                except ValueError:
                    fv_int = 0
                hex_digits = max(1, (size + 3) // 4)
                widget.setText(f"0x{fv_int:0{hex_digits}X}")
                widget.setEnabled(False)
            widget.textChanged.connect(lambda _: on_change())
            self._widget = widget

        if fg_color and isinstance(self._widget, QLineEdit):
            self._widget.setStyleSheet(f"color: {fg_color};")

        grid.addWidget(self._widget, row_idx, self.COL_ENTRY)

        short_desc = desc if len(desc) <= 60 else desc[:57] + "\u2026"
        desc_lbl = QLabel(short_desc)
        desc_lbl.setFont(mono_sm_font)
        desc_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        desc_lbl.setStyleSheet("color: #555555;")
        grid.addWidget(desc_lbl, row_idx, self.COL_DESC)

    def get_value(self) -> int | None:
        """Return the integer value currently entered, or None on error."""
        if isinstance(self._widget, QComboBox):
            raw = self._widget.currentText().strip()
            if not raw:
                return 0
            return self._enum_map.get(raw, 0)
        else:
            raw = self._widget.text().strip()
            if not raw:
                return 0
            try:
                return parse_int(raw)
            except ValueError:
                return None


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

class Mu2eSender(QMainWindow):
    def __init__(self, cfg: dict):
        super().__init__()
        self.setWindowTitle("Mu2e Data Format Sender")
        self.resize(1100, 720)
        self.setMinimumSize(700, 500)

        self._cfg = cfg
        self.yaml_dir = cfg["formats_dir"]
        self.formats = load_yaml_formats(self.yaml_dir)
        self._little_endian: bool = False
        self._field_rows: list[FieldRow] = []
        self._current_fmt: dict = {}

        self._font_size = int(cfg.get("font_size", 11))

        self._build_ui()
        self._apply_config_defaults()
        self._load_format()

    # ------------------------------------------------------------------
    # Font helpers
    # ------------------------------------------------------------------

    def _f(self, delta: int = 0, bold: bool = False) -> QFont:
        """Return a Courier font at the current size plus *delta*."""
        f = QFont("Courier", self._font_size + delta)
        if bold:
            f.setBold(True)
        return f

    @property
    def _mono_font(self) -> QFont:
        return self._f()

    @property
    def _mono_sm_font(self) -> QFont:
        return self._f(-1)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        self._build_menu()
        self._build_toolbar()
        self._build_central()

    def _apply_config_defaults(self) -> None:
        """Apply config values that depend on the UI being fully built."""
        # Default format
        default = self._cfg.get("default_format", "")
        if default:
            idx = self.format_combo.findText(default)
            if idx >= 0:
                self.format_combo.blockSignals(True)
                self.format_combo.setCurrentIndex(idx)
                self.format_combo.blockSignals(False)

        # Sender host, port, and protocol
        sender_cfg = self._cfg.get("sender", {})
        self.host_edit.setText(str(sender_cfg.get("host", "localhost")))
        self.port_edit.setText(str(sender_cfg.get("port", 7755)))
        proto = sender_cfg.get("protocol", "TCP")
        idx = self._proto_combo.findText(proto.upper())
        if idx >= 0:
            self._proto_combo.setCurrentIndex(idx)

        # Font size label
        self._font_size_label.setText(str(self._font_size))

    def _build_menu(self):
        menu_bar = self.menuBar()

        # ── File menu ─────────────────────────────────────────────────
        file_menu = menu_bar.addMenu("File")
        file_menu.addAction("Load config…", self._load_config_file)
        file_menu.addAction("Save config…", self._save_config_file)

        # ── View menu ─────────────────────────────────────────────────
        view_menu = menu_bar.addMenu("View")

        style_menu = view_menu.addMenu("Style")
        self._style_group = QActionGroup(self)
        self._style_group.setExclusive(True)
        current_style = QApplication.instance().style().objectName().lower()
        for name in sorted(QStyleFactory.keys()):
            action = style_menu.addAction(name)
            action.setCheckable(True)
            action.setChecked(name.lower() == current_style)
            self._style_group.addAction(action)
            action.triggered.connect(
                lambda checked, s=name: QApplication.instance().setStyle(s)
            )

    def _load_config_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Load config file", "",
            "YAML files (*.yaml *.yml);;All files (*.*)",
        )
        if not path:
            return
        try:
            cfg = _config.load(path)
        except Exception as exc:
            QMessageBox.critical(self, "Load config", f"Could not load config:\n{exc}")
            return
        self._cfg = cfg
        self._apply_config(cfg)

    def _save_config_file(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save config file", "mu2e-viewer.yaml",
            "YAML files (*.yaml *.yml);;All files (*.*)",
        )
        if not path:
            return
        cfg = self._current_config_state()
        try:
            import yaml
            with open(path, "w") as fh:
                yaml.dump(cfg, fh, default_flow_style=False, sort_keys=False)
        except Exception as exc:
            QMessageBox.critical(self, "Save config", f"Could not save config:\n{exc}")
            return
        self._status_label.setText(f"Config saved to {path}")

    def _current_config_state(self) -> dict:
        """Return a dict of the current UI settings suitable for saving."""
        return {
            "formats_dir": self.yaml_dir,
            "default_format": self.format_combo.currentText(),
            "sender": {
                "host": self.host_edit.text(),
                "port": int(self.port_edit.text() or 7755),
                "protocol": self._proto_combo.currentText(),
            },
            "font_size": self._font_size,
            "qt_style": QApplication.instance().style().objectName(),
        }

    def _apply_config(self, cfg: dict) -> None:
        """Apply all settings from *cfg* to the live UI."""
        # Formats dir — reload if changed
        new_dir = cfg.get("formats_dir", self.yaml_dir)
        if new_dir != self.yaml_dir:
            self.yaml_dir = new_dir
            self.formats = load_yaml_formats(new_dir)
            fmt_names = sorted(self.formats.keys())
            self.format_combo.blockSignals(True)
            self.format_combo.clear()
            for name in fmt_names:
                self.format_combo.addItem(name)
            self.format_combo.blockSignals(False)

        # Default format
        default = cfg.get("default_format", "")
        if default:
            idx = self.format_combo.findText(default)
            if idx >= 0:
                self.format_combo.blockSignals(True)
                self.format_combo.setCurrentIndex(idx)
                self.format_combo.blockSignals(False)

        # Sender host, port, and protocol
        sender_cfg = cfg.get("sender", {})
        self.host_edit.setText(str(sender_cfg.get("host", self.host_edit.text())))
        self.port_edit.setText(str(sender_cfg.get("port", self.port_edit.text())))
        proto = sender_cfg.get("protocol", self._proto_combo.currentText())
        idx = self._proto_combo.findText(str(proto).upper())
        if idx >= 0:
            self._proto_combo.setCurrentIndex(idx)

        # Font size
        new_size = int(cfg.get("font_size", self._font_size))
        if new_size != self._font_size:
            self._font_size = new_size
            self._on_font_size_changed()

        # Qt style
        style = cfg.get("qt_style", "")
        if style:
            QApplication.instance().setStyle(style)
            for action in self._style_group.actions():
                action.setChecked(action.text().lower() == style.lower())

        # Rebuild field rows with any new format/font
        self._load_format()

    def _build_toolbar(self):
        # ── Row 1: packet format and endian ───────────────────────────
        bar1 = self.addToolBar("Format")
        bar1.setMovable(False)
        bar1.setFloatable(False)

        bar1.addWidget(QLabel("  Packet format: "))

        self.format_combo = QComboBox()
        self.format_combo.setFont(self._mono_font)
        self.format_combo.setMinimumWidth(300)
        fmt_names = sorted(self.formats.keys())
        for name in fmt_names:
            self.format_combo.addItem(name)
        if fmt_names:
            self.format_combo.setCurrentIndex(0)
        self.format_combo.currentIndexChanged.connect(lambda _: self._load_format())
        bar1.addWidget(self.format_combo)

        bar1.addSeparator()

        self._le_check = QCheckBox("Little-endian words")
        self._le_check.setFont(self._mono_font)
        self._le_check.stateChanged.connect(self._on_le_changed)
        bar1.addWidget(self._le_check)

        # ── Row 2: connection, send, status, font ─────────────────────
        bar2 = self.addToolBar("Send")
        bar2.setMovable(False)
        bar2.setFloatable(False)

        bar2.addWidget(QLabel("  Protocol: "))
        self._proto_combo = QComboBox()
        self._proto_combo.setFont(self._mono_font)
        self._proto_combo.addItems(["TCP", "UDP"])
        bar2.addWidget(self._proto_combo)

        bar2.addWidget(QLabel("  Viewer host: "))
        self.host_edit = QLineEdit("localhost")
        self.host_edit.setFont(self._mono_font)
        self.host_edit.setFixedWidth(120)
        bar2.addWidget(self.host_edit)

        bar2.addWidget(QLabel("  port: "))
        self.port_edit = QLineEdit("7755")
        self.port_edit.setFont(self._mono_font)
        self.port_edit.setFixedWidth(60)
        bar2.addWidget(self.port_edit)

        bar2.addSeparator()

        btn_send = QPushButton("Send to viewer")
        btn_send.setFont(self._mono_font)
        btn_send.clicked.connect(self._send)
        bar2.addWidget(btn_send)

        btn_reset = QPushButton("Reset fields")
        btn_reset.setFont(self._mono_font)
        btn_reset.clicked.connect(self._load_format)
        bar2.addWidget(btn_reset)

        bar2.addSeparator()

        self._status_label = QLabel("Ready")
        self._status_label.setFont(self._mono_font)
        self._status_label.setStyleSheet("color: gray;")
        bar2.addWidget(self._status_label)

        bar2.addSeparator()

        bar2.addWidget(QLabel("  Font: "))

        btn_font_dec = QPushButton("A-")
        btn_font_dec.setFont(self._mono_font)
        def _dec_font():
            if self._font_size > 7:
                self._font_size -= 1
            self._on_font_size_changed()
        btn_font_dec.clicked.connect(_dec_font)
        bar2.addWidget(btn_font_dec)

        self._font_size_label = QLabel(str(self._font_size))
        self._font_size_label.setFont(self._mono_font)
        bar2.addWidget(self._font_size_label)

        btn_font_inc = QPushButton("A+")
        btn_font_inc.setFont(self._mono_font)
        def _inc_font():
            if self._font_size < 24:
                self._font_size += 1
            self._on_font_size_changed()
        btn_font_inc.clicked.connect(_inc_font)
        bar2.addWidget(btn_font_inc)

    def _build_central(self):
        splitter = QSplitter(Qt.Orientation.Vertical)
        self.setCentralWidget(splitter)

        # ── Packet fields (scrollable) ─────────────────────────────────
        fields_group = QGroupBox("Packet fields")
        fields_group.setFont(self._mono_font)
        fields_layout = QVBoxLayout(fields_group)
        fields_layout.setContentsMargins(4, 4, 4, 4)

        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)

        self._fields_container = QWidget()
        self._fields_grid = QGridLayout(self._fields_container)
        self._fields_grid.setContentsMargins(4, 4, 4, 4)
        self._fields_grid.setSpacing(2)
        # Column stretch weights: name, word, bits, value, desc
        self._fields_grid.setColumnStretch(0, 3)
        self._fields_grid.setColumnStretch(1, 1)
        self._fields_grid.setColumnStretch(2, 1)
        self._fields_grid.setColumnStretch(3, 3)
        self._fields_grid.setColumnStretch(4, 5)

        self._scroll_area.setWidget(self._fields_container)
        fields_layout.addWidget(self._scroll_area)

        splitter.addWidget(fields_group)

        # ── Assembled bytes ────────────────────────────────────────────
        bytes_group = QGroupBox("Assembled bytes")
        bytes_group.setFont(self._mono_font)
        bytes_layout = QVBoxLayout(bytes_group)
        bytes_layout.setContentsMargins(4, 4, 4, 4)

        self.bytes_text = QTextEdit()
        self.bytes_text.setFont(self._f())
        self.bytes_text.setReadOnly(True)
        self.bytes_text.setStyleSheet("background-color: #f8f8f8;")
        bytes_layout.addWidget(self.bytes_text)

        splitter.addWidget(bytes_group)

        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)

    # ------------------------------------------------------------------
    # Little-endian toggle
    # ------------------------------------------------------------------

    def _on_le_changed(self):
        self._little_endian = self._le_check.isChecked()
        self._assemble()

    # ------------------------------------------------------------------
    # Font size change
    # ------------------------------------------------------------------

    def _on_font_size_changed(self):
        self._font_size_label.setText(str(self._font_size))
        QApplication.instance().setFont(self._f())
        self._load_format()

    # ------------------------------------------------------------------
    # Format loading — rebuild the field rows whenever format changes
    # ------------------------------------------------------------------

    def _load_format(self):
        # Clear existing widgets from grid
        while self._fields_grid.count():
            item = self._fields_grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._field_rows.clear()

        fmt_name = self.format_combo.currentText()
        if not fmt_name or fmt_name not in self.formats:
            return
        self._current_fmt = self.formats[fmt_name]

        bold_font = self._f(bold=True)

        # Column header row (row 0)
        headers = ["Field Name", "Word", "Bits", "Value  (hex or decimal)", "Description"]
        for col, heading in enumerate(headers):
            lbl = QLabel(heading)
            lbl.setFont(bold_font)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            lbl.setStyleSheet("background-color: #e0e0e0; padding: 2px;")
            self._fields_grid.addWidget(lbl, 0, col)

        row_idx = 1

        # Collect sections (mirrors viewer.py logic + hit_format)
        fmt = self._current_fmt
        sections: list[tuple[str, list]] = []
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
                # Section header spanning all 5 columns
                sec_lbl = QLabel(f"  {section_label}")
                sec_lbl.setFont(self._f(bold=True))
                sec_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                sec_lbl.setStyleSheet("background-color: #d0e8ff; padding: 2px;")
                self._fields_grid.addWidget(sec_lbl, row_idx, 0, 1, 5)
                row_idx += 1

            for field in fields:
                fr = FieldRow(
                    self._fields_grid, row_idx, field,
                    on_change=self._assemble,
                    mono_font=self._f(),
                    mono_sm_font=self._f(-1),
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
        le = self._little_endian

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

        # Display: offset-labelled rows of 16 bytes
        lines = []
        for i in range(0, len(buf), 16):
            offset_label = f"{i:04X}:  "
            chunk = buf[i:i + 16]
            hex_part = " ".join(f"{b:02X}" for b in chunk)
            lines.append(offset_label + hex_part)
        display = "\n".join(lines)

        self.bytes_text.setPlainText(display)
        if error:
            self.bytes_text.setStyleSheet(
                "background-color: #f8f8f8; color: red;"
            )
            self._status_label.setText("Input error \u2014 check field values")
            self._status_label.setStyleSheet("color: red;")
        else:
            self.bytes_text.setStyleSheet(
                "background-color: #f8f8f8; color: black;"
            )
            self._status_label.setText(f"Assembled  {len(buf)} bytes")
            self._status_label.setStyleSheet("color: gray;")

        return None if error else buf

    # ------------------------------------------------------------------
    # Send
    # ------------------------------------------------------------------

    def _send(self):
        buf = self._assemble()
        if buf is None:
            QMessageBox.critical(
                self, "Send error",
                "Cannot send \u2014 fix field value errors first."
            )
            return

        host = self.host_edit.text().strip()
        try:
            port = int(self.port_edit.text().strip())
        except ValueError:
            QMessageBox.critical(self, "Send error", "Invalid port number.")
            return

        proto = self._proto_combo.currentText()
        try:
            if proto == "UDP":
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                    sock.sendto(bytes(buf), (host, port))
            else:
                with socket.create_connection((host, port), timeout=5) as sock:
                    sock.sendall(bytes(buf))
            self._status_label.setText(
                f"Sent {len(buf)} bytes to {host}:{port} via {proto}"
            )
            self._status_label.setStyleSheet("color: gray;")
        except OSError as exc:
            QMessageBox.critical(
                self, "Send error",
                f"Could not send to {host}:{port} via {proto}\n\n{exc}"
            )
            self._status_label.setText("Send failed")
            self._status_label.setStyleSheet("color: red;")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mu2e Data Format Sender")
    parser.add_argument(
        "--config", metavar="FILE",
        help="Path to a YAML config file (default: mu2e-viewer.yaml in script dir)",
    )
    parser.add_argument(
        "formats_dir", nargs="?",
        help="Directory containing format YAML files (overrides config)",
    )
    args = parser.parse_args()

    cfg = _config.load(args.config, script_dir=YAML_DIR)
    if args.formats_dir:
        cfg["formats_dir"] = args.formats_dir

    app = QApplication(sys.argv)
    app.setStyle(cfg.get("qt_style", "Fusion"))
    app.setFont(QFont("Courier", cfg.get("font_size", 11)))
    window = Mu2eSender(cfg)
    window.show()
    sys.exit(app.exec())
