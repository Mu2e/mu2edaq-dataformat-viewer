# Mu2e Data Format Viewer — Usage Guide

## Requirements

- Python 3.10 or later
- PyYAML (`pip install pyyaml`)
- Tkinter (included with most Python distributions)

## Starting the application

```bash
cd /path/to/mu2edaq-dataformat-viewer
python3 viewer.py
```

By default the viewer looks for YAML format files in the same directory as
`viewer.py`.  To point it at a different directory, pass the path as an
argument:

```bash
python3 viewer.py /path/to/yaml/formats/
```

---

## Overview of the interface

```
┌─────────────────────────────────────────────────────────────┐
│  Toolbar                                                    │
├─────────────────────────────────────────────────────────────┤
│  Raw bytes  (hex input)                                     │
├─────────────────────────────────────────────────────────────┤
│  Field breakdown  (table)                                   │
├─────────────────────────────────────────────────────────────┤
│  Field detail  (description panel)                          │
└─────────────────────────────────────────────────────────────┘
```

---

## Toolbar controls

### Packet format
Select the packet type from the drop-down list.  All 20 packet formats defined
in the YAML files are available.  Changing the selection immediately re-parses
the current byte data against the new format.

Use **Auto-detect type** to let the viewer read bits [7:4] of word 1 and
select the matching format automatically.  This works for all standard ROC
packet types.

### Values display mode
Choose how field values are shown in the breakdown table:

| Mode | Example |
|------|---------|
| Hex | `0x5A` |
| Binary | `01011010` |
| Decimal | `90` |

All three columns (hex, binary, decimal) are always visible in the table
regardless of this setting; the mode controls which column is highlighted /
wide by default.

### Little-endian words
When checked, each 16-bit word is read in little-endian byte order (low byte
first).  Leave unchecked (default) for standard big-endian Mu2e packets.

### Clear
Removes all byte data and resets the table.

---

## Loading data

### Paste hex bytes
Click in the **Raw bytes** panel and type or paste hex values.  The viewer
re-parses automatically after each keystroke.

Accepted formats — all of the following are equivalent:

```
10 00 80 10 AB CD EF 01
0x10 0x00 0x80 0x10 0xAB 0xCD 0xEF 0x01
1000 8010 ABCD EF01
```

Spaces, `0x` prefixes, and newlines are all ignored.

### Load a binary file
Click **Load file…** and select any `.bin`, `.dat`, or `.raw` file.  The
raw bytes are read and displayed as hex in the input panel, then parsed
against the currently selected format.

### Receive data over TCP
An external application can push byte arrays directly to the viewer over a
TCP connection.

1. Set the **TCP port** field to the desired port number (default `7755`).
2. Click **Start listening**.  The status bar confirms the viewer is listening.
3. The sending application connects, sends the raw bytes, and closes the
   connection.  The viewer automatically displays the received packet.
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

After receiving the data the viewer also runs auto-detect and selects the
appropriate packet format if the type is recognised.

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
| **Decoded / Description** | Human-readable meaning if the field has defined enumerated values; error message if a fixed-value field does not match its expected value |

### Row colour coding

| Colour | Meaning |
|--------|---------|
| White | Normal field |
| **Green** | Fixed-value field — value matches the expected constant (e.g. Packet Type) |
| **Red** | Fixed-value field — value does **not** match the expected constant; likely a corrupt or misidentified packet |
| **Grey text** | Reserved field — value should be zero but is not checked |

Packets with multiple sub-sections (e.g. Tracker Data Packet which spans two
16-byte payload packets) display a blue section header row between the two
halves.

### Field detail panel
Click any row to see the full field description in the **Field detail** panel
at the bottom, including:

- Byte offset within the packet
- Value in all three formats (hex, binary, decimal)
- Decoded enumerated value
- Full description from the format specification
- Complete enumeration table (all defined values and their meanings)
- Any subfields defined within this field

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

Each packet type is described by a YAML file in the same directory as
`viewer.py`.  To add a new format or correct an existing one, edit the
corresponding `.yaml` file and restart the viewer.

The required YAML structure for each field is:

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

Formats with multiple payload packets (e.g. tracker hits spanning two
16-byte packets) can use `packet_1` and `packet_2` sub-sections instead
of a top-level `fields` list.

---

## Reference

Format definitions are derived from **Mu2e-doc-4914** — *Mu2e Readout
Controller Packet Protocol*, last updated 21 February 2026.
