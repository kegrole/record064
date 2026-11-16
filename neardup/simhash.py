"""64-bit SimHash fingerprints.

Each term is hashed with SHA-256 and the first 8 digest bytes are read as a
big-endian 64-bit integer.  For every bit position the term's weight is
added to that position's running sum when the bit is set and subtracted
otherwise.  A fingerprint bit is 1 exactly when its final sum is positive.

The accumulation is bit-sliced into a single big integer: each of the 64
columns owns a 32-bit field, so adding one term is one big-int addition
instead of 64 Python-level updates.  Column sums cannot overflow because a
record's total weight is far below 2**31.  The result is bit-for-bit
identical to the naive per-column loop.
"""

import hashlib

BITS = 64
_FIELD_BITS = 32
_FIELD_MASK = (1 << _FIELD_BITS) - 1

_SPREAD_CACHE = {}


def _spread(hash64):
    value = 0
    for bit in range(BITS):
        if (hash64 >> bit) & 1:
            value |= 1 << (_FIELD_BITS * bit)
    return value


def _token_spread(token):
    spread = _SPREAD_CACHE.get(token)
    if spread is None:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        spread = _spread(int.from_bytes(digest[:8], "big"))
        _SPREAD_CACHE[token] = spread
    return spread


def simhash(weighted_terms):
    """Compute the 64-bit SimHash fingerprint of {term: weight}."""
    acc = 0
    total = 0
    for term, weight in weighted_terms.items():
        acc += weight * _token_spread(term)
        total += weight
    fingerprint = 0
    doubled = acc << 1
    for bit in range(BITS):
        column = (doubled >> (_FIELD_BITS * bit)) & _FIELD_MASK
        if column > total:
            fingerprint |= 1 << bit
    return fingerprint


def hamming(left, right):
    """Hamming distance between two 64-bit fingerprints."""
    return bin(left ^ right).count("1")
