# Mu2e Data Format Viewer — Usage Guide

## Requirements

- Python 3.10 or later
- PyYAML (`pip install pyyaml`)
- PyQt6 (`pip install PyQt6`)

Install all dependencies at once:

```bash
pip install -r requirements.txt
```

---

## Directory layout

```
mu2edaq-dataformat-viewer/
├── viewer.py            # Data format viewer application
├── sender.py            # Packet construction and sending application
├── config/
│   ├── config.py        # Configuration loader module
│   └── mu2e-viewer.yaml # Default configuration file
├── formats/             # Packet format YAML definitions (21 files)
├── test/                # Test data files
│   ├── test.dat         # 16-byte Heartbeat Packet sample
│   └── test2.dat        # 2048 bytes of random data
├── doc/
│   └── mu2e-dataformat.pdf  # Source format specification
├── requirements.txt
└── USAGE.md
```

---

## Starting the applications

### Viewer

```bash
cd /path/to/mu2edaq-dataformat-viewer
python3 viewer.py
```

### Sender

```bash
python3 sender.py
```

### Command-line options (both applications)

```
python3 viewer.py [--config FILE] [formats_dir]
python3 sender.py [--config FILE] [formats_dir]
```

| Argument | Description |
|----------|-------------|
| `--config FILE` | Path to a YAML configuration file |
| `formats_dir` | Directory containing format YAML files (overrides config) |

---

## Configuration file

Both applications read a YAML configuration file on startup.  The file is
searched in the following locations (first match wins):

1. `./mu2e-viewer.yaml`
2. `./config.yaml`
3. `./config/mu2e-viewer.yaml`
4. `./config/config.yaml`

An explicit `--config /path/to/file.yaml` always takes precedence.

### All configuration options

```yaml
# Directory containing the packet-format *.yaml files.
# Relative paths are resolved relative to this config file.
formats_dir: "../formats"

# Packet format selected on startup.
# Must match a format name exactly (e.g. "Heartbeat Packet").
# Leave empty to select the first format alphabetically.
default_format: ""

# Viewer settings
viewer:
  port: 7755          # TCP port the viewer listens on for incoming data

# Sender settings
sender:
  host: localhost     # Default destination host
  port: 7755          # Default destination port

# Appearance
font_size: 11         # Base font size in points (range 7–24)
qt_style:  Fusion     # Qt style: Fusion | Windows | macOS
```

### Loading and saving config at runtime

Both applications have a **File** menu with:

- **Load config…** — opens a file picker, loads a YAML config file, and
  applies all settings to the running UI immediately (formats directory,
  default format, connection ports, font size, Qt style).
- **Save config…** — captures the current UI state and writes it to a YAML
  file of your choice, preserving any in-session changes for next time.

---

## Viewer interface

```
┌─────────────────────────────────────────────────────────────────┐
│  Menu bar:  File  |  View                                       │
├─────────────────────────────────────────────────────────────────┤
│  Toolbar                                                        │
├─────────────────────────────────────────────────────────────────┤
│  Raw bytes  (hex input)                                         │
├─────────────────────────────────────────────────────────────────┤
│  Field breakdown  (table)                                       │
├─────────────────────────────────────────────────────────────────┤
│  Field detail  (description panel)                              │
└─────────────────────────────────────────────────────────────────┘
```

### Toolbar controls

| Control | Description |
|---------|-------------|
| **Packet format** | Drop-down list of all available packet formats.  Changing the selection immediately re-parses the current byte data. |
| **Values: Hex / Binary / Decimal** | Controls the display mode for all value columns in the breakdown table.  All three columns (hex, binary, decimal) are always visible. |
| **Little-endian words** | When checked, each 16-bit word is read low-byte-first.  Leave unchecked (default) for standard big-endian Mu2e packets. |
| **Load file…** | Load a binary file (`.bin`, `.dat`, `.raw`) as the input data. |
| **Auto-detect type** | Reads bits [7:4] of word 1 and selects the matching packet format automatically. |
| **Clear** | Removes all byte data and resets the table. |
| **Offset (bytes)** | Byte offset into the raw data at which decoding begins.  The 16-bit word at the offset is highlighted in red in the hex input panel.  Can also be set by clicking any byte in the hex panel. |
| **TCP port / Start listening** | Listens on the given port for incoming raw byte data from an external application.  Click again to stop. |
| **Font: A- / size / A+** | Decrease or increase the base font size (range 7–24 pt). |

### View menu

**View → Style** lists all available Qt styles (Fusion, Windows, macOS, …).
The active style has a checkmark.  Selecting a style applies it immediately.

---

## Loading data into the viewer

### Paste hex bytes

Click in the **Raw bytes** panel and type or paste hex values.  The viewer
re-parses automatically on each keystroke.

Accepted formats — all of the following are equivalent:

```
10 00 80 10 AB CD EF 01
0x10 0x00 0x80 0x10 0xAB 0xCD 0xEF 0x01
1000 8010 ABCD EF01
```

Spaces, `0x` prefixes, and newlines are all ignored.

### Click to set decode offset

Click any hex byte token in the **Raw bytes** panel to set the decode offset
to that byte position.  The spinbox updates to match, and the two bytes
forming the 16-bit word at that position are highlighted in red.

### Load a binary file

Click **Load file…** and select a binary file.  The raw bytes are displayed
as hex and parsed against the currently selected format.

### Receive data over TCP

An external application can push byte arrays directly to the viewer over TCP.

1. Set the **TCP port** field (default `7755`).
2. Click **Start listening**.
3. The sending application connects, sends the raw bytes, and closes the
   connection.  The viewer displays and auto-detects the received packet.
4. Click **Stop listening** when done.

**Example sender (Python):**

```python
import socket

packet_bytes = bytes([0x10, 0x00, 0x80, 0x10, 0xAB, 0xCD,
                      0xEF, 0x01, 0x23, 0x45, 0x67, 0x89,
                      0x00, 0x11, 0xCA, 0xFE])

with socket.create_connection(("localhost", 7755)) as sock:
    sock.sendall(packet_bytes)
```

**Example sender (C):**

```c
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>

uint8_t pkt[] = { 0x10, 0x00, 0x80, 0x10, /* ... */ };

int fd = socket(AF_INET, SOCK_STREAM, 0);
struct sockaddr_in addr = {
    .sin_family = AF_INET,
    .sin_port   = htons(7755),
    .sin_addr   = { .s_addr = inet_addr("127.0.0.1") }
};
connect(fd, (struct sockaddr *)&addr, sizeof(addr));
send(fd, pkt, sizeof(pkt), 0);
close(fd);
```

---

## Reading the field breakdown table

Each row represents one field defined in the YAML format file.

| Column | Description |
|--------|-------------|
| **Field Name** | Name of the field as defined in the format spec |
| **Word** | Zero-indexed 16-bit word within the packet |
| **Bits** | Bit range within that word, e.g. `15:8` or `3` |
| **Hex** | Extracted field value in hexadecimal |
| **Binary** | Extracted field value in binary |
| **Dec** | Extracted field value in decimal |
| **Decoded / Description** | Human-readable meaning for enumerated fields; error message if a fixed-value field does not match its expected value |

### Row colour coding

| Colour | Meaning |
|--------|---------|
| White | Normal field |
| Green | Fixed-value field — value matches the expected constant (e.g. Packet Type) |
| Red background | Fixed-value field mismatch — likely a corrupt or misidentified packet |
| Blue background | Section header row (multi-packet formats such as Tracker) |
| Grey text | Reserved field |

### Field detail panel

Click any row to see the full field description in the **Field detail** panel,
including:

- Byte offset within the packet
- Value in all three formats (hex, binary, decimal)
- Decoded enumerated value
- Full description from the format specification
- Complete enumeration table (all defined values and their meanings)
- Any subfields defined within this field

---

## Sender interface

The sender lets you construct a packet field-by-field and transmit it to the
viewer over TCP.

```
┌─────────────────────────────────────────────────────────────────┐
│  Menu bar:  File  |  View                                       │
├─────────────────────────────────────────────────────────────────┤
│  Toolbar                                                        │
├─────────────────────────────────────────────────────────────────┤
│  Packet fields  (scrollable grid)                               │
├─────────────────────────────────────────────────────────────────┤
│  Assembled bytes  (live hex dump)                               │
└─────────────────────────────────────────────────────────────────┘
```

### Toolbar controls

| Control | Description |
|---------|-------------|
| **Packet format** | Selects the packet type; rebuilds the field grid immediately. |
| **Little-endian words** | Matches the viewer's endian toggle. |
| **Viewer host / port** | Destination for the **Send to viewer** action. |
| **Send to viewer** | Assembles the packet bytes and sends them to the viewer over TCP. |
| **Reset fields** | Restores all field values to their defaults for the current format. |
| **Font: A- / size / A+** | Adjust base font size. |

### Packet fields grid

Each row in the scrollable grid corresponds to one packet field:

| Column | Content |
|--------|---------|
| Field Name | Name from the YAML definition |
| Word | 16-bit word index |
| Bits | Bit range within the word |
| Value | Free-entry box (hex `0x1A` or decimal), or a drop-down for enumerated fields |
| Description | Abbreviated description from the YAML definition |

- Fields with a `fixed_value` are pre-filled and locked (e.g. Packet Type).
- Enumerated fields show a drop-down of all valid options with their meanings.
- Reserved fields are shown in grey.
- Multi-section packets display a blue section divider row.

### Assembled bytes panel

Shows a live hex dump of the current packet, updated after every field change.
Bytes are displayed in rows of 16 with a byte-offset label on the left.
The panel turns red if any field contains an invalid value.

---

## Supported packet types

| Packet | Type code | DMA channel |
|--------|-----------|-------------|
| DCS Request Packet | `0x0` | 1 |
| Heartbeat Packet | `0x1` | 0 |
| Data Request Packet | `0x2` | 0 |
| Prefetch Request Packet | `0x3` | 0 |
| DCS Reply Packet | `0x4` | 1 |
| Data Header Packet | `0x5` | 0 |
| Data Payload Packet | `0x6` | 0 |
| DCS Request Additional Block Write Payload | `0x7` | 1 |
| DCS Reply Additional Block Read Payload | `0x8` | 1 |
| Tracker Data Packet | — | subsystem 0x0 |
| Calorimeter Hit Data Packet | — | subsystem 0x1 |
| Calorimeter Hit Debugging Data Packet | — | subsystem 0x1 |
| Calorimeter Footer Packet | — | subsystem 0x1 |
| CRV ROC Status Packet | — | subsystem 0x2 |
| CRV Hit Data Packet | — | subsystem 0x2 |
| CRV Global Run Info Packet | — | subsystem 0x2 |
| STM Trigger Header Packet | — | subsystem 0x4 |
| STM Slice Header Packet | — | subsystem 0x4 |
| Debug Header Packet | — | — |
| Debug Data Packet | — | — |

---

## Adding or modifying packet formats

Each packet type is described by a YAML file in the `formats/` directory.
To add a new format or correct an existing one, edit the corresponding `.yaml`
file and restart the application (or use **File → Load config…** to reload).

The required YAML structure for each field:

```yaml
name: My Packet
description: What this packet is for.
size_bytes: 16
fields:
  - name: Transfer Byte Count
    word: 0          # zero-indexed 16-bit word
    bits: "15:0"     # bit range within the word (15 = MSB)
    size_bits: 16
    description: Total byte count of the transfer.

  - name: Packet Type
    word: 1
    bits: "7:4"
    size_bits: 4
    description: Always 0x1 for this packet.
    fixed_value: 0x1   # viewer flags a mismatch in red

  - name: Status
    word: 1
    bits: "3:0"
    size_bits: 4
    description: Status flags.
    values:
      0: "Idle"
      1: "Busy"
      2: "Error"
```

Formats with multiple payload packets (e.g. tracker hits spanning two 16-byte
packets) use `packet_1` and `packet_2` sub-sections instead of a top-level
`fields` list.

---

## Reference

Format definitions are derived from **Mu2e-doc-4914** — *Mu2e Readout
Controller Packet Protocol*, last updated 21 February 2026.
