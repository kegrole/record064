"""Band-based bucketing used to avoid O(n^2) pairwise comparison.

The 64-bit fingerprint is split into ``bands`` contiguous bands counted
from the most significant bit.  With the default threshold of 3 there are
4 bands of 16 bits: band 0 is bits 63..48 (the high bits), band 3 is bits
15..0.  A record is placed into one bucket per band, keyed by
``(band_index, band_value)``.

Recall guarantee: if two fingerprints differ in at most ``threshold`` bit
positions, those differing positions can touch at most ``threshold``
distinct bands, so with ``bands = threshold + 1`` at least one band is
bit-identical and the pair shares that band's bucket.  Comparing only
pairs that share a bucket therefore never misses a near-duplicate pair,
even when the two fingerprints have different high-bit prefixes.
"""


def band_layout(bits=64, bands=4):
    """Return [(low, high), ...] bit ranges, band 0 covering the high bits."""
    base, extra = divmod(bits, bands)
    layout = []
    high = bits
    for index in range(bands):
        width = base + (1 if index < extra else 0)
        layout.append((high - width, high))
        high -= width
    return layout


class BucketIndex:
    """Maps (band_index, band_value) -> list of record ids."""

    def __init__(self, bits=64, bands=4):
        self.layout = band_layout(bits, bands)
        self.buckets = {}

    def add(self, record_id, fingerprint):
        for band_index, (low, high) in enumerate(self.layout):
            value = (fingerprint >> low) & ((1 << (high - low)) - 1)
            key = (band_index, value)
            bucket = self.buckets.get(key)
            if bucket is None:
                self.buckets[key] = [record_id]
            else:
                bucket.append(record_id)

    def candidate_pairs(self):
        """Yield each unordered pair of ids sharing at least one bucket."""
        seen = set()
        for members in self.buckets.values():
            size = len(members)
            if size < 2:
                continue
            for i in range(size):
                for j in range(i + 1, size):
                    a, b = members[i], members[j]
                    pair = (a, b) if a < b else (b, a)
                    if pair not in seen:
                        seen.add(pair)
                        yield pair

    def bucket_count(self):
        """Number of distinct (band, value) buckets actually used."""
        return len(self.buckets)
