# Staged issues — mu2edaq-dataformat-viewer

Findings from the September 2026 DAQ mega-review (`mu2e-sept-mega-review`),
2026-10-06.

**Why these are staged.** `Mu2e/mu2edaq-dataformat-viewer` is **public** with
issues enabled. Under CONTRACT.md §9.1 no GitHub write is attempted from a
package agent. Each finding below is in the §6 body format, ready to file
unchanged.

**Dedup.** `gh issue list --state all` returned three closed issues: #1
(start/stop scripts), #2 (discovery support), #6 (Python 3.9 PEP 604 unions).
None overlaps a finding below; DFV-006 concerns the code #2 added.

**Verification method.** The YAML-versus-overlay comparison reads
`artdaq-core-mu2e` at `cf86c07`: overlay headers, plus only the pack/unpack
functions those headers name (Tier B rule). The specification is the copy
shipped in this repository, `doc/mu2e-dataformat.pdf` (Mu2e-doc-4914 V53),
converted with `pdftotext -layout`. Decoder behaviour was checked by
executing the module's own `hex_str_to_bytes` and `parse_fields` (extracted
with `ast`, no Qt) and the config loader from a scratch directory. The C
library and CLI were built out of tree with CMake. No GUI was launched and no
network listener was opened.

**Fingerprints** are `sha1("Mu2e/mu2edaq-dataformat-viewer:<path>:<rule_id>")[:8]`;
the inputs are tabulated at the end.

10 findings: 1 × S2, 6 × S3, 3 × S4.

---

## DFV-001

**Title:** `[formats] heartbeat, data-request and debug-header YAML layouts disagree with Mu2e-doc-4914 V53 and with artdaq-core-mu2e; nothing checks consistency`

**Severity:** S2 — production breakage or silent wrong behaviour; workaround exists
**Category:** bug
**Location:** `formats/heartbeat_packet.yaml:108`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-10-06

## What
`formats/*.yaml` and `artdaq-core-mu2e/Overlays` encode the same ROC packet
layouts independently, and nothing compares them. For three packets the YAML
places fields in different bits from both the specification it was
transcribed from (`doc/mu2e-dataformat.pdf`, Mu2e-doc-4914 V53) and the
overlay. The spec and the overlay agree with each other.

- **Heartbeat:** the YAML labels word 5 bit 0 "On-spill Flag" (spec:
  Injection Data Source), puts TEM/STM in word 6 (spec: word 7 [7:6]/[5:4]),
  invents "Event Mode Byte 5 - Subrun Handling" at word 7 [15:8] (spec:
  Delivery Ring RF-0 Marker TDC), leaves word 7 [7:0] undefined (spec: TEM,
  STM, Subrun [3:1], **On-spill [0]**), and moves the TDC to word 8 and the
  CRC to word 9.
- **Data Request:** the YAML puts Debug Type at word 6 [15:12]; spec and
  overlay put it at [7:4].
- **Debug Header:** the YAML puts a fixed `0b00000` "Op Code" at word 1
  [7:3], overlapping ROC Link ID [3:0]; spec has Debug Type [7:4] there and
  the `0b00000` in word 2 [15:11]. The trailer rows are shifted down a word.

The Data Header layout agrees in all 8 words across all three sources.

## Evidence
```
# Heartbeat, word 7 low byte: spec p. 9
 Delivery Ring RF-0 Marker TDC [15:8]  TEM [7:6] STM [5:4] Subrun Handling [3:1] On-spill Flag [0]

# overlay (artdaq-core-mu2e cf86c07)
DTC_Packets/DTC_HeartbeatPacket.cpp:40   eventMode_.mode4 = arr[14];           // word 7 [7:0]
DTC_Packets/DTC_HeartbeatPacket.cpp:41   eventMode_.deliveryRingTDC = arr[15]; // word 7 [15:8]
DTC_Types/DTC_EventMode.h:26             bool isOnSpillFlagSet() const { return mode4 & 1; }

# YAML
formats/heartbeat_packet.yaml:138  - name: On-spill Flag      (subfield of word 5 [7:0], bits "0")
formats/heartbeat_packet.yaml:194  - name: Event Mode Byte 5 - Subrun Handling   bits "15:8" word 7
formats/heartbeat_packet.yaml:212  - name: Delivery Ring RF-0 Marker TDC         bits "15:8" word 8
formats/heartbeat_packet.yaml:223  - name: CRC                                   bits "15:0" word 9

# Data Request, word 6: spec p. 10 "Reserved [15:8] Debug Type [7:4] Reserved [3:1] Debug[0]"
DTC_Packets/DTC_DataRequestPacket.cpp:60  output.SetByte(12, (static_cast<uint8_t>(type_) << 4) + (debug_ ? 1 : 0));
formats/data_request_packet.yaml:103      - name: Debug Type   bits: "15:12"   word: 6

# Debug Header, word 1: spec p. 22 "Valid Reserved [14:11] Subsystem ID [10:8] Debug Type ROC Link ID [3:0]"
formats/debug_header_packet.yaml:59       - name: Op Code (fixed pattern)   bits: "7:3"   word: 1
```
Full tables: `doc/INTERFACES.md` §4.

## Why it matters
The viewer reports a heartbeat's on-spill state from the wrong bit and never
shows the real on-spill, subrun or delivery-ring TDC values. The sender
builds heartbeats and debug data requests the DTC software decodes
differently. An expert using the tool to diagnose beam-timing or
debug-request problems gets a plausible, wrong answer with no error. A
workaround exists (read the spec), so S2 rather than S1.

## Suggested fix
Correct the three files against V53. Then add a test that, for each packet
type the overlay implements, builds a packet with the overlay (or a small
pybind/ctypes shim, or golden byte strings captured from it), decodes it with
`parse_fields`, and compares every field. Run it in CI so the YAML cannot
drift again.

## Related
- DFV-002 (value-table drift and missing schema validation)
- Mu2e/artdaq-core-mu2e: see `doc/INTERFACES.md` §4.6 for an overlay-internal
  subsystem-ID round-trip mismatch found while comparing

<!-- mega-review-fingerprint: 8ab8722f -->

---

## DFV-002

**Title:** `[formats] YAML value tables drift from the overlay enums, three formats cannot be displayed, and nothing validates the YAML`

**Severity:** S3 — correctness or maintainability risk, no current outage
**Category:** bug
**Location:** `formats/packet_type_index.yaml:1`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-10-06

## What
- **Subsystem ID:** YAML (and spec) 3 = Reserved, 6 = Reserved, 7 = TDAQ;
  overlay `DTC_Subsystem` 3 = Other, 6 = MobileSync, 7 = Unused. The viewer
  labels MobileSync data "Reserved".
- **Debug Type:** YAML (and spec) reserve 3–F; overlay defines 3 = RAMTest,
  4 = DDRTest.
- **Schema:** the loader accepts any YAML dict. A 40-line check found one
  bit overlap (DFV-001, debug header) and 17 fields beyond `size_bytes` in 14
  files (CRC/trailer rows), which the sender silently drops (`set_bits`
  returns early) and the viewer decodes from the next packet's word 0.
- **Coverage:** calorimeter hit data, calorimeter hit debugging and CRV hit
  data use structures the viewer does not interpret (`hit_header`,
  `formats`, `hit_format`), so it shows an empty table for them; the sender
  handles only `hit_format`. README says "21 packet format definitions
  covering all Mu2e ROC packet types"; there are 20 plus the index.

## Evidence
```
# overlay DTC_Types/DTC_Subsystem.h
13:	DTC_Subsystem_Other = 3,
16:	DTC_Subsystem_MobileSync = 6,
17:	DTC_Subsystem_Unused
# formats/data_header_packet.yaml
119:      0x3: "Reserved"
122:      0x6: "Reserved"
123:      0x7: "TDAQ (Trigger and Data Acquisition)"
# overlay DTC_Types/DTC_DebugType.h
14:	DTC_DebugType_RAMTest = 3,
15:	DTC_DebugType_DDRTest = 4,

# consistency check over formats/*.yaml
TOTALS {'width': 0, 'beyond': 17, 'overlap': 1}
calorimeter_hit_data_packet.yaml viewer: False sender: False
calorimeter_hit_debugging_data_packet.yaml viewer: False sender: False
crv_hit_data_packet.yaml viewer: False sender: True
```

## Why it matters
Value labels and layouts will keep drifting between the hand-written YAML,
the spec and the C++ with nothing to catch it; three of the advertised
formats are unusable in the viewer.

## Suggested fix
Add a JSON-Schema (or pydantic) check for the YAML run in CI, flag fields
beyond `size_bytes`, generate the subsystem and debug-type tables from one
source shared with artdaq-core-mu2e, and either teach the viewer the
calorimeter/CRV structures or remove those files.

## Related
- DFV-001

<!-- mega-review-fingerprint: cb12ee48 -->

---

## DFV-003

**Title:** `[viewer] default big-endian word order is the opposite of the DTC byte order, and auto-detect misreads payload and little-endian packets`

**Severity:** S3 — correctness or maintainability risk, no current outage
**Category:** bug
**Location:** `mu2edaq-dataformat-viewer.py:82`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-10-06

## What
`get_word` assembles words big-endian unless "Little-endian words" is
ticked, the default is unticked, and `USAGE.md:139` calls big-endian
"standard". The DTC software reads the same 16-byte packets little-endian
(byte 0 is the low byte of the byte count, the packet type is the high
nibble of byte 2). The sample `test/test.dat` is big-endian. Auto-detect
reads word 1 bits 7:4 under the current setting, so on a DMA dump with the
default setting it reads the wrong nibble, and on a data payload packet,
which carries no type field, it picks a format from data bits.

## Evidence
```
$ sed -n 87,88p mu2edaq-dataformat-viewer.py
    b0, b1 = data[offset], data[offset + 1]
    return (b1 << 8) | b0 if little_endian else (b0 << 8) | b1
# artdaq-core-mu2e Overlays/DTC_Packets/DTC_DMAPacket.cpp
39:	uint8_t packetType = (word2 >> 4) & 0xF;          // word2 = GetData()[2]
45:	byteCount_ = in.GetData()[0] + (in.GetData()[1] << 8);
$ xxd test/test.dat | head -1
00000000: 0010 8010 cdef 00ab 0000 0001 a020 0000  ............. ..
$ sed -n 139p USAGE.md
| **Little-endian words** | ... Leave unchecked (default) for standard big-endian Mu2e packets. |
```

## Why it matters
Pasting or receiving real DTC data with the default setting decodes every
field from swapped bytes. It is not silent, because the fixed Packet Type
check turns red, which keeps this at S3, but it costs the expert time and
the documentation points the wrong way.

## Suggested fix
Default to little-endian, or decide per input source (file and network:
little-endian), correct `USAGE.md`, and skip auto-detect for formats with no
type field.

## Related
- DFV-001

<!-- mega-review-fingerprint: 2d48a561 -->

---

## DFV-004

**Title:** `[viewer] the listener accepts unbounded input from any host and truncated packets decode silently`

**Severity:** S3 — correctness or maintainability risk, no current outage
**Category:** bug
**Location:** `mu2edaq-dataformat-viewer.py:1032`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-10-06

## What
"Start listening" binds `0.0.0.0` with no peer filter. For TCP, every
connection gets its own thread and is read until the peer closes, with no
size cap and no timeout; the whole stream becomes one packet and is rendered
as hex text in the GUI. Any host that can reach the port replaces the
operator's display. Decoding itself is bounds-safe, but a field past the end
of the data is skipped with no indication that the packet was short.

## Evidence
```
$ sed -n 1032,1040p mu2edaq-dataformat-viewer.py
    def _handle_conn(self, conn: socket.socket):
        try:
            chunks = []
            while True:
                chunk = conn.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
$ sed -n 115,116p mu2edaq-dataformat-viewer.py
        if word_val is None:
            continue
# executing parse_fields from the source on 6 bytes against the Data Header layout:
6-byte input: 9 of 22 fields shown, no truncation marker
```

## Why it matters
A peer that sends a large stream, or holds connections open, freezes or
exhausts the viewer on a shared control-room desktop. A short packet looks
like a complete one with fewer fields.

## Suggested fix
Bind to a configurable address (default loopback), cap a TCP packet at a few
kB with a receive timeout, limit concurrent connections, and show a
"truncated: N of M fields" row when fields are skipped.

## Related
- DFV-006

<!-- mega-review-fingerprint: 834a9779 -->

---

## DFV-005

**Title:** `[viewer] word size 2 or 4 bytes makes every decode fail with "Parse error"`

**Severity:** S3 — correctness or maintainability risk, no current outage
**Category:** bug
**Location:** `mu2edaq-dataformat-viewer.py:135`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-10-06

## What
With "Word size" set to 2 or 4 bytes, `_format_hex_rows` writes the hex
panel as multi-byte tokens (`0010 8010 …`). `_refresh_display` re-parses
that text with `hex_str_to_bytes`, which turns each token into one integer
and passes it to `bytes()`, raising for any value above 0xFF. Every file
load, received packet, offset or format change then shows "Parse error" and
an empty table.

## Evidence
```
# executing the module's hex_str_to_bytes on _format_hex_rows output for word size 2:
display text (word size 2): 0010 8010 CDEF 00AB 0000 0001 A020 0000
hex_str_to_bytes -> ValueError bytes must be in range(0, 256)
ws=1 round trip ok: True
```

## Why it matters
A display option silently disables the tool's only function. Workaround:
keep word size at 1 byte.

## Suggested fix
Keep `self.data_bytes` as the source of truth and decode from it instead of
re-parsing the display text, or split multi-byte tokens back into bytes in
`hex_str_to_bytes`.

## Related
- none

<!-- mega-review-fingerprint: 76f66c90 -->

---

## DFV-006

**Title:** `[discovery] the viewer announces its port at launch, before anything listens`

**Severity:** S3 — correctness or maintainability risk, no current outage
**Category:** bug
**Location:** `mu2edaq-dataformat-viewer.py:1090`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-10-06

## What
`__main__` starts the discovery responder right after the window opens,
announcing `scheme="tcp"` and the configured port. The listener only exists
after the operator presses "Start listening", may be UDP, and may be on a
port edited in the toolbar. The superproject's
`DAQ-ControlRoom-Testing.md:92` says the viewer "announces **only while
listening**". `meta` is not passed, so the CONTRACT §9.5 string-only rule
is satisfied.

## Evidence
```
$ sed -n 1089,1092p mu2edaq-dataformat-viewer.py
        from mu2edaq_discovery import Responder
        responder = Responder(name="Data Format Viewer", app="dataformat-viewer",
                              port=cfg["viewer"]["port"], scheme="tcp")
        responder.start()
$ sed -n 92p ../DAQ-ControlRoom-Testing.md
| dataformat-viewer | GUI — announces **only while listening** | `--config` | 7755 |
```

## Why it matters
A scan offers a TCP endpoint that refuses connections, and the control-room
testing guide describes behaviour the code does not have. This is the
pattern the discovery integration request (closed #2) asked to avoid
("never advertise a port that isn't accepting").

## Suggested fix
Start the responder in `_start_server` with the bound port and protocol, and
stop it in `_stop_server`.

## Related
- Mu2e/mu2edaq-dataformat-viewer#2 (closed)

<!-- mega-review-fingerprint: 020cbe29 -->

---

## DFV-007

**Title:** `[tests] test/ holds sample data but no tests, and there is no CI`

**Severity:** S3 — correctness or maintainability risk, no current outage
**Category:** enhancement
**Location:** `test`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-10-06

## What
`test/` contains `test.dat` (a 20-byte heartbeat) and `test2.dat` (2048
bytes of apparently random data). There is no test code, `bootstrap.sh
--dev` installs pytest for nothing, and there is no `.github/workflows`.

## Evidence
```
$ git ls-files test .github
test/test.dat
test/test2.dat
```

## Why it matters
DFV-001, DFV-002 and DFV-005 are each one assertion away from being caught.
The decoding helpers are pure functions and easy to test without Qt.

## Suggested fix
Add pytest tests for `extract_bits`, `parse_fields`, `hex_str_to_bytes`,
`set_bits` round trips for every format, a YAML schema check, and the
overlay comparison of DFV-001. Run them in GitHub Actions on Python 3.9 with
`QT_QPA_PLATFORM=offscreen`.

## Related
- DFV-001, DFV-002, DFV-005

<!-- mega-review-fingerprint: 5297c4b1 -->

---

## DFV-008

**Title:** `[config] config search is relative to the current directory; launched elsewhere the viewer loads no formats`

**Severity:** S4 — cosmetic, stale, hygiene
**Category:** bug
**Location:** `config/config.py:52`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-10-06

## What
Without `--config`, the loader tries `./mu2e-viewer.yaml`, `./config.yaml`,
`./config/mu2e-viewer.yaml`, `./config/config.yaml` relative to the current
directory. If none exists, the built-in `formats_dir: "."` resolves to the
checkout root, which has no format files. The `--help` text says "default:
mu2e-viewer.yaml in script dir". A generic `./config.yaml` belonging to
something else is picked up if present.

## Evidence
```
# config.load(None, script_dir=<checkout>) from a scratch directory:
cwd=scratch -> formats_dir .../mu2edaq-dataformat-viewer yaml files: 0
cwd=repo -> formats_dir .../mu2edaq-dataformat-viewer/formats yaml files: 21
```

## Why it matters
Started from a shell anywhere but the checkout, the viewer opens with an
empty format list. The start script `cd`s first, so the control-room path
is unaffected.

## Suggested fix
Search the script directory's `config/` after the cwd, set the built-in
`formats_dir` to the `formats/` directory next to the scripts, and drop the
generic `config.yaml` name.

## Related
- none

<!-- mega-review-fingerprint: e5ffd8f8 -->

---

## DFV-009

**Title:** `[cpp] libmu2e_sender is POSIX-only and lets SIGPIPE kill the caller`

**Severity:** S4 — cosmetic, stale, hygiene
**Category:** bug
**Location:** `cpp/src/mu2e_sender.cpp:103`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-10-06

## What
The library includes `<sys/socket.h>`, `<netdb.h>` and `<unistd.h>` with no
Winsock path, although `mu2e_send.cpp` carries `_WIN32` includes. TCP `send`
uses flags 0, so writing to a peer that has closed raises SIGPIPE in the
calling process. On a `getaddrinfo` failure `errno` is not set although the
header says it is. No CMake package config is exported.

## Evidence
```
$ sed -n 103p cpp/src/mu2e_sender.cpp
            ssize_t n = ::send(fd, data + sent, len - sent, 0);
$ grep -n '_WIN32' cpp/src/mu2e_sender.cpp cpp/tools/mu2e_send.cpp
cpp/tools/mu2e_send.cpp:32:#ifdef _WIN32
```

## Why it matters
A DAQ process linking the library to push packets dies on SIGPIPE if the
viewer is closed mid-send.

## Suggested fix
Use `MSG_NOSIGNAL` (Linux) / `SO_NOSIGPIPE` (macOS), set `errno` or document
`mu2e_strerror()` as the only error source, and add `install(EXPORT ...)`.

## Related
- none

<!-- mega-review-fingerprint: 35d6bcf7 -->

---

## DFV-010

**Title:** `[docs] README format count, sample path and the "standard big-endian" claim are wrong`

**Severity:** S4 — cosmetic, stale, hygiene
**Category:** documentation
**Location:** `README.md:31`
**Found by:** mega-review (`mu2e-sept-mega-review`), 2026-10-06

## What
`README.md:31` and `:170` say 21 packet format definitions; there are 20 plus
the index. `README.md:52` runs `./build/mu2e_send --udp -f test/test.dat`
from `cpp/`, where `test/test.dat` does not exist (it is `../test/test.dat`).
`USAGE.md:139` calls big-endian the standard word order (DFV-003). There were
no man pages (added on the review branch).

## Evidence
```
$ grep -n '21 packet' README.md
31:- 21 packet format definitions covering all Mu2e ROC packet types
170:├── formats/                       # 21 packet format YAML definitions
$ ls formats | grep -v packet_type_index | wc -l
20
```

## Why it matters
Small, but the README is the entry point and the byte-order claim steers
users wrong.

## Suggested fix
Correct the count and path; fix the byte-order guidance with DFV-003; link
the man pages.

## Related
- DFV-002, DFV-003

<!-- mega-review-fingerprint: 004a7282 -->

---

## Fingerprint inputs

| ID | Input to `sha1(...)[:8]` | Fingerprint |
|---|---|---|
| DFV-001 | `Mu2e/mu2edaq-dataformat-viewer:formats/heartbeat_packet.yaml:yaml-overlay-layout-disagreement` | 8ab8722f |
| DFV-002 | `Mu2e/mu2edaq-dataformat-viewer:formats/packet_type_index.yaml:yaml-schema-drift-unvalidated` | cb12ee48 |
| DFV-003 | `Mu2e/mu2edaq-dataformat-viewer:mu2edaq-dataformat-viewer.py:default-word-order-autodetect` | 2d48a561 |
| DFV-004 | `Mu2e/mu2edaq-dataformat-viewer:mu2edaq-dataformat-viewer.py:listener-unbounded-silent-truncation` | 834a9779 |
| DFV-005 | `Mu2e/mu2edaq-dataformat-viewer:mu2edaq-dataformat-viewer.py:word-size-parse-error` | 76f66c90 |
| DFV-006 | `Mu2e/mu2edaq-dataformat-viewer:mu2edaq-dataformat-viewer.py:discovery-announce-before-listen` | 020cbe29 |
| DFV-007 | `Mu2e/mu2edaq-dataformat-viewer:test:no-tests-no-ci` | 5297c4b1 |
| DFV-008 | `Mu2e/mu2edaq-dataformat-viewer:config/config.py:cwd-relative-config-search` | e5ffd8f8 |
| DFV-009 | `Mu2e/mu2edaq-dataformat-viewer:cpp/src/mu2e_sender.cpp:posix-only-sigpipe` | 35d6bcf7 |
| DFV-010 | `Mu2e/mu2edaq-dataformat-viewer:README.md:docs-count-path-endian` | 004a7282 |
