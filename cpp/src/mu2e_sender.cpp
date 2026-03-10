/**
 * mu2e_sender.cpp — Implementation of the Mu2e packet sender library.
 */

#include "mu2e_sender.h"

#include <cerrno>
#include <cstring>
#include <cstdio>

#include <sys/types.h>
#include <sys/socket.h>
#include <netdb.h>
#include <unistd.h>

/* Thread-local storage for error message string. */
static thread_local char tl_errbuf[512];

static void set_err(const char *context, int err_no)
{
    std::snprintf(tl_errbuf, sizeof(tl_errbuf),
                  "%s: %s", context, std::strerror(err_no));
}

const char *mu2e_strerror(void)
{
    return tl_errbuf;
}

/* Resolve host:port into a connected/targetable socket.
 * For TCP (SOCK_STREAM) the socket is connect()ed.
 * For UDP (SOCK_DGRAM)  the socket is NOT connect()ed; addr_out is filled.
 *
 * Returns the fd on success, or -1 on failure (errno set, tl_errbuf updated).
 */
static int resolve_socket(mu2e_protocol_t proto,
                           const char *host,
                           int port,
                           struct sockaddr_storage *addr_out,
                           socklen_t *addrlen_out)
{
    char port_str[16];
    std::snprintf(port_str, sizeof(port_str), "%d", port);

    struct addrinfo hints{};
    hints.ai_family   = AF_UNSPEC;
    hints.ai_socktype = (proto == MU2E_PROTO_TCP) ? SOCK_STREAM : SOCK_DGRAM;
    hints.ai_flags    = AI_NUMERICSERV;

    struct addrinfo *res = nullptr;
    int rc = ::getaddrinfo(host, port_str, &hints, &res);
    if (rc != 0) {
        std::snprintf(tl_errbuf, sizeof(tl_errbuf),
                      "getaddrinfo(%s:%d): %s", host, port, ::gai_strerror(rc));
        return -1;
    }

    int fd = -1;
    for (struct addrinfo *ai = res; ai; ai = ai->ai_next) {
        fd = ::socket(ai->ai_family, ai->ai_socktype, ai->ai_protocol);
        if (fd < 0)
            continue;

        if (proto == MU2E_PROTO_TCP) {
            if (::connect(fd, ai->ai_addr, ai->ai_addrlen) == 0) {
                ::freeaddrinfo(res);
                return fd;           /* connected TCP socket */
            }
            ::close(fd);
            fd = -1;
        } else {
            /* UDP — just copy the address for later use with sendto */
            std::memcpy(addr_out, ai->ai_addr, ai->ai_addrlen);
            *addrlen_out = static_cast<socklen_t>(ai->ai_addrlen);
            ::freeaddrinfo(res);
            return fd;               /* unconnected UDP socket */
        }
    }

    ::freeaddrinfo(res);
    set_err("connect", errno);
    return -1;
}

int mu2e_send(mu2e_protocol_t proto,
              const char      *host,
              int              port,
              const uint8_t   *data,
              size_t           len)
{
    struct sockaddr_storage addr{};
    socklen_t addrlen = 0;

    int fd = resolve_socket(proto, host, port, &addr, &addrlen);
    if (fd < 0)
        return -1;

    int ret = 0;
    if (proto == MU2E_PROTO_TCP) {
        /* Send all bytes; loop in case of partial write. */
        size_t sent = 0;
        while (sent < len) {
            ssize_t n = ::send(fd, data + sent, len - sent, 0);
            if (n < 0) {
                set_err("send", errno);
                ret = -1;
                break;
            }
            sent += static_cast<size_t>(n);
        }
    } else {
        /* UDP — single datagram. */
        ssize_t n = ::sendto(fd, data, len, 0,
                             reinterpret_cast<struct sockaddr *>(&addr),
                             addrlen);
        if (n < 0) {
            set_err("sendto", errno);
            ret = -1;
        }
    }

    ::close(fd);
    return ret;
}

int mu2e_send_tcp(const char    *host,
                  int            port,
                  const uint8_t *data,
                  size_t         len)
{
    return mu2e_send(MU2E_PROTO_TCP, host, port, data, len);
}

int mu2e_send_udp(const char    *host,
                  int            port,
                  const uint8_t *data,
                  size_t         len)
{
    return mu2e_send(MU2E_PROTO_UDP, host, port, data, len);
}
