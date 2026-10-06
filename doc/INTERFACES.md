# mu2edaq-dataformat-viewer — interfaces

Line references are to the `mu2e-sept-mega-review` branch (HEAD `97d8b71`,
tag `t01.00.00`). Overlay references are to `artdaq-core-mu2e` at `cf86c07`
(headers, plus the pack/unpack functions those headers name).

## 1. Network input (viewer)

| Property | Value | Source |
|---|---|---|
| Start | only when the operator presses **Start listening** | `mu2edaq-dataformat-viewer.py:969-973` |
| Bind | `0.0.0.0:<port>`, `SO_REUSEADDR` | `:983-992` |
| Port | `viewer.port` (7755), overridden by `CRS_PORT_LISTEN`, editable in the toolbar | `config/config.py:111-113` |
| TCP framing | one connection = one packet; read with `recv(65536)` until the peer closes; no length limit, no timeout | `:1032-1047` |
| UDP framing | one datagram = one packet, up to 65536 bytes | `:1023-1030` |
| Concurrency | one daemon thread per TCP connection, unbounded | `:1013-1021` |
| Peer filter / auth | none | — |
| On receipt | bytes replace the display, then `_auto_detect()` picks a format | `:1049-1053` |

Payload is raw bytes, no header or envelope. Anything that can reach the
port replaces what the operator is looking at.

### Decoding bounds

`get_word` returns `None` when `2·word + 2 > len(data)` and `parse_fields`
skips that field (`:82-88`, `:115-116`). There is no out-of-range read, and
the offset spin box is clamped to 0–65535. The defect is silent truncation:
a 6-byte input against the 22-field Data Header shows 9 rows and no marker
that 13 are missing (verified by running `parse_fields` from the source on
2026-10-06). See DFV-004.

### Word order

Words are assembled big-endian unless **Little-endian words** is ticked
(`:82-88`, default `False` at `:193`), and `USAGE.md:139` calls big-endian
"standard". The overlays read the same packets little-endian:
`byteCount_ = in.GetData()[0] + (in.GetData()[1] << 8)`
(`DTC_DMAPacket.cpp:45`), and the packet type is the high nibble of byte 2
(`:39`). A DTC DMA dump or artdaq fragment therefore decodes correctly only
with the box ticked. `test/test.dat` is big-endian
(`00 10 80 10 …` = byte count 0x0010, word 1 0x8010). See DFV-003.

### Auto-detect

`_auto_detect` reads `(word1 >> 4) & 0xF` (`:893`) and maps 0x0–0x8 through
the built-in `PACKET_TYPE_MAP` (`:164-174`). Data payload packets carry no
type field in memory (the type travels only in the serial `D6.y` character,
`formats/data_payload_packet.yaml:12-20`), so auto-detect on a payload
packet selects a format from whatever its data bits are.

## 2. Network output (sender, `mu2e_send`)

| Sender | TCP | UDP |
|---|---|---|
| `mu2edaq-dataformat-sender.py` `_send` (`:724-760`) | `create_connection(timeout=5)`, `sendall`, close | IPv4 `sendto`, one datagram |
| `libmu2e_sender` / `mu2e_send` | `getaddrinfo` (v4/v6), connect first that accepts, loop `send`, close | `sendto` first address |

## 3. Discovery

`__main__` starts `Responder(name="Data Format Viewer", app="dataformat-viewer",
port=cfg["viewer"]["port"], scheme="tcp")` at launch (`:1087-1092`), whether
or not anything is listening and whatever protocol is selected.
`DAQ-ControlRoom-Testing.md:92` in the superproject says it "announces
**only while listening**"; the code does not do that (DFV-006). No `meta` is
passed, so the CONTRACT §9.5 string-only rule holds. Protocol details:
`mu2edaq-discovery/doc/INTERFACES.md`.

## 4. YAML layouts versus Mu2e-doc-4914 and artdaq-core-mu2e

`formats/*.yaml` and `artdaq-core-mu2e/Overlays` independently encode the
same wire layouts. The YAML says it is derived from Mu2e-doc-4914
(`formats/packet_type_index.yaml:4`), shipped here as
`doc/mu2e-dataformat.pdf` (V53, 21 Feb 2026). Nothing compares either
encoding to the other or to the PDF.

Notation: word *w* holds bytes 2*w* (bits 7:0) and 2*w*+1 (bits 15:8) in the
overlay's little-endian reading. "Spec" is the PDF table on the page given.

### 4.1 Data Header packet (type 0x5) — layouts agree

YAML `formats/data_header_packet.yaml`; spec p. 11; overlay
`RocDataHeaderPacket_t` (`DTC_Packets/DTC_RocDataHeaderPacket.h:6-31`, a
bit-field struct).

| Word | Field | YAML bits | Spec bits | Overlay | Agree? |
|---|---|---|---|---|---|
| 0 | byte count | 15:0 | 15:0 | `byteCount:16` | yes |
| 1 | reserved / packet type / link ID / DTC errors / valid | 3:0 / 7:4 / 10:8 / 14:11 / 15 | same | `unused:4`, `packetType:4`, `linkID:3`, `DtcErrors:4`, `valid:1` | yes |
| 2 | packet count / reserved / subsystem ID | 10:0 / 12:11 / 15:13 | same | `packetCount:11`, `unused2:2`, `subsystemID:3` | yes |
| 3–5 | event window tag, bytes 0–5 | 7:0, 15:8 per word | same | `eventTag[3]` | yes |
| 6 | status / format version | 7:0 / 15:8 | same | `status:8`, `version:8` | yes |
| 6 | status bits 0–4 (has data, invalid request, corrupt, timeout, overflow) | 0–4 | 0–4 | `empty()`…`overflow()` masks 0x01–0x10 | yes |
| 7 | DTC ID / on-spill / subrun / event mode | 7:0 / 8 / 10:9 / 15:11 | same | `dtcID:8`, `onSpill:1`, `subrun:2`, `eventMode:5` | yes |
| 8 | CRC | 15:0 | link-level row after the 8 words | absent (16-byte packet) | n/a |

Value table for **Subsystem ID** — disagrees:

| Value | YAML (`:115-123`) | Spec p. 11 | Overlay `DTC_Subsystem.h:10-17` |
|---|---|---|---|
| 3 | Reserved | (not listed) | `Other` |
| 6 | Reserved | (not listed) | `MobileSync` (has a `MobileSyncDataDecoder`) |
| 7 | TDAQ | TDAQ | `Unused` (implicit 7) |

### 4.2 Heartbeat packet (type 0x1) — layouts disagree

YAML `formats/heartbeat_packet.yaml`; spec p. 9; overlay
`DTC_HeartbeatPacket.cpp:36-41` (unpack) and `:79-80` (pack), with
`DTC_EventMode.h:26-28` for the flag bits.

| Word, bits | Spec | Overlay | YAML | Agree? |
|---|---|---|---|---|
| 0–4 | byte count, header, EWT | same | same | yes |
| 5, 7:0 | Event Mode byte 0: [7:3] reserved, Pattern Mode [2:1], **Injection Data Source [0]** | `mode0` = byte 10 | Event Mode Byte 0: Pattern Mode [2:1], **On-spill Flag [0]** (`:138-139`) | **no** — YAML calls bit 0 the on-spill flag |
| 5, 15:8 | Event Mode byte 1 (Trk) | `mode1` | same | yes |
| 6, 7:0 | Event Mode byte 2 (Calo) [7:1], Calo Laser Injection [0] | `mode2` | byte 2 with TEM [7:6] and STM [5:4] subfields (`:173-182`) | **no** — TEM/STM belong in word 7 |
| 6, 15:8 | Event Mode byte 3 (CRV) | `mode3` | same | yes |
| 7, 7:0 | TEM [7:6], STM [5:4], Subrun Handling [3:1], **On-spill Flag [0]** | `mode4` = byte 14; `isOnSpillFlagSet = mode4 & 1`, subrun `& 2`, predictive `& 4` | **not defined** | **no** |
| 7, 15:8 | **Delivery Ring RF-0 Marker TDC** | `deliveryRingTDC` = byte 15 | "Event Mode Byte 5 - Subrun Handling", subrun at 11:9 (`:194-207`) | **no** |
| 8 | CRC | (beyond 16 bytes) | **Delivery Ring TDC** [15:8] (`:212-214`) | **no** |
| 9 | — | — | CRC (`:223-225`) | **no** (YAML has 10 rows) |

The YAML inserts a non-existent "Event Mode Byte 5" row at word 7, shifting
the TDC and CRC down a word, and labels a different bit as the on-spill flag.
The viewer therefore reports the on-spill state of a heartbeat from word 5
bit 0 (the spec's Injection Data Source bit) and never shows the real flag in
word 7 bit 0. The sender builds heartbeats the DTC software would read with
on-spill and subrun bits clear. The overlay and the spec agree.

### 4.3 Data Request packet (type 0x2) — layouts disagree

YAML `formats/data_request_packet.yaml`; spec p. 10; overlay
`DTC_DataRequestPacket.cpp:60-62` (pack) and `DTC_DebugType.h:11-16`.

| Word, bits | Spec | Overlay | YAML | Agree? |
|---|---|---|---|---|
| 0–4 | byte count, header, EWT | same | same | yes |
| 5 | reserved | bytes 10–11 unset | reserved | yes |
| 6, 0 | Debug | `byte12 bit0 = debug_` | Debug [0] | yes |
| 6, 7:4 | **Debug Type** | `byte12 = type << 4` | reserved (inside 11:1) | **no** |
| 6, 15:12 | reserved | 0 | **Debug Type** (`:103-106`) | **no** |
| 7 | reserved [15:11], Debug Packet Count [10:0] | bytes 14–15 = 16-bit count | reserved [15:11], count [10:0] | width differs (11 vs 16 bits); compatible below 2048 |
| 8 | CRC | — | CRC | link-level |

Debug Type values: spec and YAML define 0–2 and reserve 3–F; the overlay
adds `RAMTest = 3` and `DDRTest = 4`.

### 4.4 Debug Header packet (type 0x5) — YAML disagrees with the spec

Overlay has no Debug Header class, so this is YAML against spec only
(`formats/debug_header_packet.yaml`; spec p. 22).

| Word | Spec | YAML |
|---|---|---|
| 1 | Valid, reserved [14:11], Subsystem ID [10:8], **Debug Type [7:4]**, ROC Link ID [3:0] | "Op Code (fixed pattern) 0b00000" at **7:3** (`:59-65`), overlapping ROC Link ID [3:0] at bit 3; no Debug Type |
| 2 | `0b00000` [15:11], Packet Count [10:0] | Packet Count [10:0] |
| 7 | filled / empty buffer-entry counts | — |
| 8 | CRC | filled / empty counts |
| 9 | — | CRC |

### 4.5 Packet types

| Type | Spec / YAML / viewer `PACKET_TYPE_MAP` | Overlay `DTC_PacketType.h:13-18` |
|---|---|---|
| 0 DCS Request, 1 Heartbeat, 2 Data Request, 4 DCS Reply, 5 Data Header | defined | defined |
| 3 Prefetch, 6 Data Payload, 7 DCS block write, 8 DCS block read | defined | not in the enum (payload has no DMA header) |
| 0x10 | — | `Invalid` |

### 4.6 Observation outside this package (not filed here)

`DTC_DMAPacket::ConvertToDataPacket` writes the subsystem ID into byte 3
bits 6:4, i.e. word 1 bits 14:12 (`DTC_DMAPacket.cpp:21`), while the
`DTC_DMAPacket(const DTC_DataPacket)` constructor reads it from byte 5 bits
7:5, i.e. word 2 bits 15:13 (`:43`). The spec and `RocDataHeaderPacket_t`
both put it in word 2 bits 15:13. A packet the overlay builds therefore does
not round-trip its subsystem ID. Passed to the `artdaq-core-mu2e` reviewer;
Tier B, not reviewed further.

### 4.7 Internal consistency of the YAML set

A 40-line check over all 20 layouts (2026-10-06) found: `size_bits` always
equals the `bits` width; one overlap (Debug Header word 1 bit 3, §4.4); and
17 fields placed beyond `size_bytes` (the CRC or trailer row in 14 files),
which the sender silently does not write and the viewer decodes from the
next packet's first word when more data follows. Three layouts
(calorimeter hit data, calorimeter hit debugging, CRV hit data) use
structures the viewer does not interpret and display as an empty table;
the sender handles only the last of the three. See DFV-002.

## 5. C API (`cpp/`)

```c
int mu2e_send(mu2e_protocol_t proto, const char *host, int port, const uint8_t *data, size_t len);
int mu2e_send_tcp(const char *host, int port, const uint8_t *data, size_t len);
int mu2e_send_udp(const char *host, int port, const uint8_t *data, size_t len);
const char *mu2e_strerror(void);   /* thread-local message */
```

`cpp/include/mu2e_sender.h:33-65`. Target `mu2e_sender`, static unless
`BUILD_SHARED_LIBS`, `SOVERSION 1`; installs the library, `mu2e_send` and
the header via `GNUInstallDirs` (`cpp/CMakeLists.txt:13-47`). No CMake
package config is exported. Man pages: `libmu2e_sender(3)`, `mu2e_send(1)`.

## 6. Command-line and configuration

| Item | Man page |
|---|---|
| viewer, sender (`[--config FILE] [formats_dir]`) | `man/man1/mu2edaq-dataformat-viewer.py.1`, `…-sender.py.1` |
| `start-`/`stop-mu2edaq-dataformat-viewer.sh`, `bootstrap.sh` | `man/man1/` |
| `mu2e_send` | `man/man1/mu2e_send.1` |
| `config/mu2e-viewer.yaml` | `man/man5/mu2e-viewer.yaml.5` |
| `formats/*.yaml` schema | `man/man5/mu2edaq-dataformat-formats.yaml.5` |

Control room: `mu2edaq-controlroom-setup/config/apps.yaml:117-125`
(`ports: {listen: 7755}`, session `daq-aux`, exports `CRS_PORT_LISTEN`).
