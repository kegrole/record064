"""Build the final duplicate report.

Two kinds of duplicates are distinguished:
- ``exact``: at least two members share the same SHA-256, i.e. their
  content is byte-identical.
- ``fingerprint``: all members have distinct SHA-256 digests; they are
  grouped only because their SimHash fingerprints are close.
"""

from .matcher import DEFAULT_THRESHOLD, group_records
from .simhash import simhash
from .tokenize import weighted_term_frequencies

MATCH_EXACT = "exact"
MATCH_FINGERPRINT = "fingerprint"


def fingerprint_records(records):
    return [simhash(weighted_term_frequencies(record["text"])) for record in records]


def build_report(records, threshold=DEFAULT_THRESHOLD):
    """records: list of dicts with keys id, source, text, sha256."""
    fingerprints = fingerprint_records(records)
    groups, bucket_count = group_records(fingerprints, threshold)

    report_groups = []
    for group_id, member_ids in enumerate(groups):
        members = [
            {
                "id": record_id,
                "source": records[record_id]["source"],
                "sha256": records[record_id]["sha256"],
            }
            for record_id in member_ids
        ]
        distinct_digests = {member["sha256"] for member in members}
        match_type = MATCH_EXACT if len(distinct_digests) < len(members) else MATCH_FINGERPRINT
        report_groups.append(
            {
                "group_id": group_id,
                "size": len(members),
                "match_type": match_type,
                "members": members,
            }
        )

    return {
        "processed": len(records),
        "groups": report_groups,
        "buckets": bucket_count,
    }
