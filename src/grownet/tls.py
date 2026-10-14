"""Certificates: every HTTPS request grownet makes is verified against the operating system's trust store.

Python's own `ssl` reads a certificate file, and which file depends on how Python was installed. The
Python that uv installs reads macOS's `/etc/ssl/cert.pem`, which does not hold HARICA TLS RSA Root CA 2021,
the root behind mGrowthDB's certificate since 23 July 2026, so a copy installed the way the README says
could not read mGrowthDB at all on a Mac (measured 2026-10-14; the keychain trusts that root, and curl and
a browser use the keychain). `truststore` asks the operating system instead, as pip does: the keychain on
macOS, the certificate store on Windows (which fetches a root it has not needed before, where reading the
store as a file misses it), and the system's bundle on Linux. It is grownet's one runtime dependency
(Karoline, 2026-10-14: "Add truststore").

The hostname is still checked and a certificate is still required: only where the trusted roots come from
changes.
"""
from __future__ import annotations

import ssl

import truststore


def context() -> ssl.SSLContext:
    """A client context that verifies the server's certificate and name against the system's roots."""
    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
