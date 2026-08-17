"""NFSN's X-NFSN-Authentication header.

The scheme is:

    salt      = 16 random alphanumeric characters
    body_hash = sha1(request body)
    digest    = sha1("login;timestamp;salt;api_key;request_uri;body_hash")
    header    = "login;timestamp;salt;digest"

SHA-1 is not a choice we get to make -- it is what the API specifies.
"""

from __future__ import annotations

import hashlib
import secrets
import time

SALT_ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
SALT_LENGTH = 16


def make_salt(length: int = SALT_LENGTH) -> str:
    return "".join(secrets.choice(SALT_ALPHABET) for _ in range(length))


def _sha1(value: str) -> str:
    """SHA-1 as required by NFSN's authentication scheme.

    This is not a choice this library gets to make. NFSN's API/Introduction page specifies
    SHA-1 for both the body hash and the header digest, and the server rejects anything else,
    so substituting a stronger hash would simply make every request fail.

    What limits the exposure:

    * The API key is never transmitted -- it is an input to the digest, not a value in the
      header, so a preimage attack on SHA-1 is what an attacker would need, not a collision.
      SHA-1 collision attacks (SHAttered, 2017) do not translate into preimage attacks.
    * Every request carries a fresh 16-character random salt and a Unix timestamp, and NFSN
      rejects timestamps more than 5 seconds from its own clock while refusing to accept a
      repeated (login, salt, timestamp) triple. That bounds any replay window to seconds.
    * All traffic is HTTPS, so the digest is not observable in transit to begin with.

    See SECURITY.md. If NFSN ever offers a stronger algorithm, this is the only place to change.
    """
    # nosemgrep: python.lang.security.insecure-hash-algorithms.insecure-hash-algorithm-sha1
    return hashlib.sha1(value.encode("utf-8")).hexdigest()


def auth_header(
    login: str,
    api_key: str,
    request_uri: str,
    body: str = "",
    *,
    timestamp: int | None = None,
    salt: str | None = None,
) -> str:
    """Build the value for the X-NFSN-Authentication header.

    ``request_uri`` is the path only, e.g. ``/dns/example.com/listRRs``.
    ``timestamp`` and ``salt`` are injectable so the result can be asserted in tests.
    """
    stamp = int(time.time()) if timestamp is None else timestamp
    nonce = make_salt() if salt is None else salt
    message = f"{login};{stamp};{nonce};{api_key};{request_uri};{_sha1(body)}"
    return f"{login};{stamp};{nonce};{_sha1(message)}"
