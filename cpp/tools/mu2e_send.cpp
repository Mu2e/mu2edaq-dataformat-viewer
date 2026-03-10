/**
 * mu2e_send — CLI utility for sending raw byte data to the Mu2e viewer.
 *
 * Usage:
 *   mu2e_send [OPTIONS] <host> <port> <hex-bytes...>
 *
 * Options:
 *   -u, --udp       Use UDP (default: TCP)
 *   -f, --file FILE Read packet bytes from binary FILE instead of hex args
 *   -h, --help      Show this help and exit
 *
 * Examples:
 *   # Send a 4-byte packet over TCP
 *   mu2e_send localhost 7755 10 00 80 10
 *
 *   # Send with 0x prefixes
 *   mu2e_send localhost 7755 0x10 0x00 0x80 0x10
 *
 *   # Send a binary file over UDP
 *   mu2e_send --udp -f packet.dat localhost 7755
 */

#include "mu2e_sender.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cerrno>
#include <vector>
#include <string>

#ifdef _WIN32
#  include <io.h>
#  include <fcntl.h>
#endif

/* -------------------------------------------------------------------------- */
/* Helpers                                                                     */
/* -------------------------------------------------------------------------- */

static void usage(const char *prog)
{
    std::fprintf(stderr,
        "Usage: %s [OPTIONS] <host> <port> <hex-bytes...>\n"
        "       %s [OPTIONS] -f <file> <host> <port>\n"
        "\n"
        "Options:\n"
        "  -u, --udp        Use UDP instead of TCP\n"
        "  -f, --file FILE  Read packet bytes from binary FILE\n"
        "  -h, --help       Show this help and exit\n"
        "\n"
        "Hex bytes may be separated by spaces and may include 0x prefixes.\n"
        "Examples:\n"
        "  %s localhost 7755 10 00 80 10 AB CD EF 01\n"
        "  %s --udp -f heartbeat.dat localhost 7755\n",
        prog, prog, prog, prog);
}

static bool parse_byte(const char *s, uint8_t &out)
{
    char *end = nullptr;
    long v = std::strtol(s, &end, 16);
    if (end == s || *end != '\0' || v < 0 || v > 255)
        return false;
    out = static_cast<uint8_t>(v);
    return true;
}

static std::vector<uint8_t> read_file(const char *path)
{
    std::FILE *fp = std::fopen(path, "rb");
    if (!fp) {
        std::fprintf(stderr, "Error: cannot open '%s': %s\n",
                     path, std::strerror(errno));
        std::exit(1);
    }
    std::vector<uint8_t> buf;
    uint8_t tmp[4096];
    size_t n;
    while ((n = std::fread(tmp, 1, sizeof(tmp), fp)) > 0)
        buf.insert(buf.end(), tmp, tmp + n);
    std::fclose(fp);
    return buf;
}

/* -------------------------------------------------------------------------- */
/* main                                                                        */
/* -------------------------------------------------------------------------- */

int main(int argc, char *argv[])
{
    mu2e_protocol_t proto   = MU2E_PROTO_TCP;
    const char      *infile = nullptr;
    int              argi   = 1;

    /* Parse flags */
    while (argi < argc && argv[argi][0] == '-') {
        std::string flag(argv[argi]);
        if (flag == "-u" || flag == "--udp") {
            proto = MU2E_PROTO_UDP;
            ++argi;
        } else if (flag == "-f" || flag == "--file") {
            if (argi + 1 >= argc) {
                std::fprintf(stderr, "Error: %s requires an argument.\n",
                             flag.c_str());
                return 1;
            }
            infile = argv[++argi];
            ++argi;
        } else if (flag == "-h" || flag == "--help") {
            usage(argv[0]);
            return 0;
        } else {
            std::fprintf(stderr, "Error: unknown option '%s'\n", argv[argi]);
            usage(argv[0]);
            return 1;
        }
    }

    /* Remaining positional args: host port [hex-bytes...] */
    if (argc - argi < 2) {
        std::fprintf(stderr, "Error: <host> and <port> are required.\n\n");
        usage(argv[0]);
        return 1;
    }

    const char *host     = argv[argi++];
    const char *port_str = argv[argi++];

    char *end = nullptr;
    long port = std::strtol(port_str, &end, 10);
    if (end == port_str || *end != '\0' || port < 1 || port > 65535) {
        std::fprintf(stderr, "Error: invalid port '%s'\n", port_str);
        return 1;
    }

    /* Build payload */
    std::vector<uint8_t> payload;

    if (infile) {
        if (argi < argc) {
            std::fprintf(stderr,
                "Error: unexpected hex bytes after -f FILE host port.\n");
            return 1;
        }
        payload = read_file(infile);
    } else {
        if (argi >= argc) {
            std::fprintf(stderr, "Error: no packet bytes specified.\n\n");
            usage(argv[0]);
            return 1;
        }
        while (argi < argc) {
            uint8_t b;
            if (!parse_byte(argv[argi], b)) {
                std::fprintf(stderr,
                    "Error: '%s' is not a valid hex byte.\n", argv[argi]);
                return 1;
            }
            payload.push_back(b);
            ++argi;
        }
    }

    if (payload.empty()) {
        std::fprintf(stderr, "Error: payload is empty.\n");
        return 1;
    }

    /* Send */
    const char *proto_str = (proto == MU2E_PROTO_UDP) ? "UDP" : "TCP";
    std::fprintf(stdout,
        "Sending %zu bytes to %s:%ld via %s...\n",
        payload.size(), host, port, proto_str);

    if (mu2e_send(proto, host, static_cast<int>(port),
                  payload.data(), payload.size()) != 0) {
        std::fprintf(stderr, "Send failed: %s\n", mu2e_strerror());
        return 1;
    }

    std::fprintf(stdout, "OK.\n");
    return 0;
}
