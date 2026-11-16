"""Near-duplicate matching on top of SimHash fingerprints and band buckets."""

from .buckets import BucketIndex
from .simhash import hamming

DEFAULT_THRESHOLD = 3


class _UnionFind:
    def __init__(self, size):
        self.parent = list(range(size))

    def find(self, node):
        parent = self.parent
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if ra < rb:
            self.parent[rb] = ra
        else:
            self.parent[ra] = rb


def group_records(fingerprints, threshold=DEFAULT_THRESHOLD):
    """Group record ids whose fingerprints are within ``threshold`` bits.

    Returns (groups, bucket_count) where groups is a list of member-id
    lists (each of size >= 2) sorted by smallest member id, so identical
    input always yields identical group ordering.
    """
    bands = threshold + 1
    index = BucketIndex(bits=64, bands=bands)
    for record_id, fingerprint in enumerate(fingerprints):
        index.add(record_id, fingerprint)

    union_find = _UnionFind(len(fingerprints))
    for a, b in index.candidate_pairs():
        if hamming(fingerprints[a], fingerprints[b]) <= threshold:
            union_find.union(a, b)

    members_by_root = {}
    for record_id in range(len(fingerprints)):
        root = union_find.find(record_id)
        members_by_root.setdefault(root, []).append(record_id)

    groups = [sorted(m) for m in members_by_root.values() if len(m) > 1]
    groups.sort(key=lambda members: (members[0], len(members)))
    return groups, index.bucket_count()
