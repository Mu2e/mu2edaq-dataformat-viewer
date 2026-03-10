# Mu2e Data Format Viewer

A graphical tool for inspecting and constructing Mu2e ROC (Readout Controller)
packet data.  Raw byte arrays are decoded field-by-field using YAML format
definitions derived from the Mu2e ROC Packet Protocol specification
(Mu2e-doc-4914).

---

## Features

### Viewer (`mu2edaq-dataformat-viewer.py`)

- Paste hex bytes, load a binary file, or receive raw bytes over a TCP socket
- Automatic packet-type detection from the packet type field
- Field-by-field breakdown showing hex, binary, and decimal values for every field
- Decoded enumeration values and full field descriptions on click
- Click any byte in the hex panel to set the decode offset; the target word is highlighted in red
- Configurable decode offset spinbox for non-zero-aligned data
- Colour-coded rows: green for correct fixed-value fields, red for mismatches, blue for section headers

### Sender (`mu2edaq-dataformat-sender.py`)

- Construct any packet type field-by-field using the same format definitions
- Drop-downs for enumerated fields; free entry for numeric fields
- Live hex dump of the assembled packet, updated on every keystroke
- Send the assembled bytes directly to a running viewer instance over TCP

### Both applications

- 21 packet format definitions covering all Mu2e ROC packet types
- PyQt6 GUI with Fusion, Windows, and macOS style options (View → Style)
- Adjustable font size (A− / A+ toolbar buttons, range 7–24 pt)
- YAML configuration file for ports, protocol, font size, Qt style, default format, and format file path
- File → Load config… and File → Save config… for runtime config management
- Selectable transport protocol: **TCP** or **UDP**

### C++ sender library (`cpp/`)

A small C library (`libmu2e_sender`) and a companion CLI tool (`mu2e_send`) for
sending raw packet bytes from C/C++ programs or shell scripts.

```bash
cd cpp
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build

# Send hex bytes over TCP (default)
./build/mu2e_send localhost 7755 10 00 80 10 AB CD EF 01

# Send a binary file over UDP
./build/mu2e_send --udp -f test/test.dat localhost 7755
```

The library exposes a simple C API:

```c
#include "mu2e_sender.h"

// TCP send
mu2e_send_tcp("localhost", 7755, data, len);

// UDP send
mu2e_send_udp("localhost", 7755, data, len);

// Protocol-selectable
mu2e_send(MU2E_PROTO_TCP, "localhost", 7755, data, len);
```

---

## Supported packet types

| Subsystem | Packets |
|-----------|---------|
| **Infrastructure** | Heartbeat, Data Request, Prefetch Request, Data Header, Data Payload |
| **DCS** | DCS Request, DCS Reply, Block Write Payload, Block Read Payload |
| **Tracker** (subsystem 0x0) | Tracker Data Packet |
| **Calorimeter** (subsystem 0x1) | Hit Data, Hit Debugging Data, Footer |
| **CRV** (subsystem 0x2) | ROC Status, Hit Data, Global Run Info |
| **STM** (subsystem 0x4) | Trigger Header, Slice Header |
| **Debug** | Debug Header, Debug Data |

---

## Requirements

- Python 3.10+
- [PyQt6](https://pypi.org/project/PyQt6/)
- [PyYAML](https://pypi.org/project/PyYAML/)

```bash
pip install -r requirements.txt
```

---

## Quick start

```bash
git clone <repo-url>
cd mu2edaq-dataformat-viewer
pip install -r requirements.txt

# Launch the viewer
python3 mu2edaq-dataformat-viewer.py

# Launch the sender (in a second terminal)
python3 mu2edaq-dataformat-sender.py
```

In the viewer, click **Start listening** (default port 7755).
In the sender, select a packet format, fill in the fields, and click **Send to viewer**.

---

## Command-line options

```
python3 mu2edaq-dataformat-viewer.py [--config FILE] [formats_dir]
python3 mu2edaq-dataformat-sender.py [--config FILE] [formats_dir]
```

| Argument | Description |
|----------|-------------|
| `--config FILE` | Path to a YAML configuration file |
| `formats_dir` | Directory containing format YAML files (overrides config) |

---

## Configuration

A YAML configuration file is searched automatically on startup:

1. `./mu2e-viewer.yaml`
2. `./config.yaml`
3. `./config/mu2e-viewer.yaml`
4. `./config/config.yaml`

The default configuration is at `config/mu2e-viewer.yaml`.  All keys are
optional — omitted keys fall back to built-in defaults.

```yaml
formats_dir:    "../formats"   # path to format YAML files
default_format: ""             # format selected on startup
viewer:
  port: 7755
sender:
  host: localhost
  port: 7755
font_size: 11                  # 7–24 pt
qt_style:  Fusion              # Fusion | Windows | macOS
```

---

## Project layout

```
mu2edaq-dataformat-viewer/
├── mu2edaq-dataformat-viewer.py   # Viewer application
├── mu2edaq-dataformat-sender.py   # Sender application
├── config/
│   ├── config.py                  # Configuration loader module
│   └── mu2e-viewer.yaml           # Default configuration
├── formats/                       # 21 packet format YAML definitions
├── test/                          # Sample binary data files
├── doc/
│   └── mu2e-dataformat.pdf        # Mu2e-doc-4914 source specification
├── cpp/                           # C++ sender library and CLI tool
│   ├── CMakeLists.txt
│   ├── include/
│   │   └── mu2e_sender.h          # Public C API
│   ├── src/
│   │   └── mu2e_sender.cpp        # Library implementation
│   └── tools/
│       └── mu2e_send.cpp          # CLI utility
├── requirements.txt
├── README.md
└── USAGE.md                       # Detailed usage guide
```

---

## Adding packet formats

Each format is a YAML file in the `formats/` directory.  A minimal example:

```yaml
name: My Packet
description: What this packet is for.
size_bytes: 16
fields:
  - name: Transfer Byte Count
    word: 0
    bits: "15:0"
    size_bits: 16
    description: Total byte count of the transfer.

  - name: Packet Type
    word: 1
    bits: "7:4"
    size_bits: 4
    description: Always 0x1 for this packet type.
    fixed_value: 0x1

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

Add the file to `formats/` and restart — it will appear in both the viewer
and sender format drop-downs immediately.

---

## Reference

Format definitions are derived from **Mu2e-doc-4914** — *Mu2e Readout
Controller Packet Protocol*, last updated 21 February 2026.
