/**
 * mu2e_sender.h — Mu2e data packet sender library
 *
 * Provides TCP and UDP functions for sending raw byte arrays to the
 * Mu2e Data Format Viewer (or any other receiver).
 *
 * Build with CMakeLists.txt in the cpp/ directory.
 */

#pragma once

#include <stddef.h>   /* size_t */
#include <stdint.h>   /* uint8_t */

#ifdef __cplusplus
extern "C" {
#endif

/** Protocol selector. */
typedef enum {
    MU2E_PROTO_TCP = 0,
    MU2E_PROTO_UDP = 1,
} mu2e_protocol_t;

/**
 * mu2e_send() — Send *len* bytes from *data* to *host*:*port* using *proto*.
 *
 * For TCP the function opens a fresh connection, sends all bytes, and closes
 * the connection.  For UDP the datagram is sent with a single sendto(2) call.
 *
 * Returns 0 on success, or -1 on error (errno is set).
 */
int mu2e_send(mu2e_protocol_t proto,
              const char      *host,
              int              port,
              const uint8_t   *data,
              size_t           len);

/**
 * mu2e_send_tcp() — Convenience wrapper: TCP send.
 *
 * Equivalent to mu2e_send(MU2E_PROTO_TCP, host, port, data, len).
 */
int mu2e_send_tcp(const char    *host,
                  int            port,
                  const uint8_t *data,
                  size_t         len);

/**
 * mu2e_send_udp() — Convenience wrapper: UDP send.
 *
 * Equivalent to mu2e_send(MU2E_PROTO_UDP, host, port, data, len).
 */
int mu2e_send_udp(const char    *host,
                  int            port,
                  const uint8_t *data,
                  size_t         len);

/**
 * mu2e_strerror() — Return a human-readable description of the last error.
 *
 * The returned pointer is valid until the next call to any mu2e_send*()
 * function from the same thread.  Thread-safe on POSIX platforms.
 */
const char *mu2e_strerror(void);

#ifdef __cplusplus
} /* extern "C" */
#endif
