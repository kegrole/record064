"""Tests for the neardup package.

The corpus fixtures are generated inside the tests (in temporary
directories) following the task rules: 100000 titles with exactly 50
near-duplicates, an exact-duplicate pair kept apart from that corpus, and
cross-bucket near-duplicate pairs whose high 16 fingerprint bits differ.
"""

import hashlib
import io
import json
import os
import random
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from neardup.buckets import band_layout
from neardup.cli import iter_records, main as cli_main
from neardup.matcher import DEFAULT_THRESHOLD, group_records
from neardup.report import MATCH_EXACT, MATCH_FINGERPRINT, build_report
from neardup.simhash import hamming, simhash
from neardup.tokenize import term_frequencies, tokenize, weighted_term_frequencies

CORPUS_SIZE = 100000
NEAR_DUPLICATE_COUNT = 50
CORPUS_SEED = 987654321

CJK_POOL = [chr(0x4E00 + i) for i in range(1500)]
HIGH_16_SHIFT = 48


def _build_words():
    rng = random.Random(777)
    letters = "abcdefghijklmnopqrstuvwxyz"
    words = set()
    while len(words) < 20000:
        words.add("".join(rng.choice(letters) for _ in range(rng.randint(3, 8))))
    return sorted(words)


WORDS = _build_words()


def fingerprint(text):
    return simhash(weighted_term_frequencies(text))


def sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def random_title(rng):
    parts = list(rng.sample(WORDS, rng.randint(6, 10)))
    for _ in range(rng.randint(4, 6)):
        parts.append("".join(rng.choice(CJK_POOL) for _ in range(rng.randint(4, 7))))
    rng.shuffle(parts)
    return " ".join(parts)


def mutate_title(text, rng):
    chars = list(text)
    positions = [i for i, ch in enumerate(chars) if "\u4e00" <= ch <= "\u9fff"]
    for pos in rng.sample(positions, rng.randint(2, 3)):
        replacement = rng.choice(CJK_POOL)
        while replacement == chars[pos]:
            replacement = rng.choice(CJK_POOL)
        chars[pos] = replacement
    return "".join(chars)


def make_near_duplicate(text, rng):
    source_fp = fingerprint(text)
    for _ in range(10000):
        candidate = mutate_title(text, rng)
        if candidate != text and hamming(source_fp, fingerprint(candidate)) <= DEFAULT_THRESHOLD:
            return candidate
    raise AssertionError("could not build a near-duplicate")


def make_cross_bucket_pair(rng):
    """A near-duplicate pair whose high 16 fingerprint bits differ."""
    while True:
        base = random_title(rng)
        base_fp = fingerprint(base)
        for _ in range(2000):
            candidate = mutate_title(base, rng)
            if candidate == base:
                continue
            candidate_fp = fingerprint(candidate)
            distance = hamming(base_fp, candidate_fp)
            high_bits_differ = (base_fp >> HIGH_16_SHIFT) != (candidate_fp >> HIGH_16_SHIFT)
            if distance <= DEFAULT_THRESHOLD and high_bits_differ:
                return base, candidate


def build_big_corpus():
    """100000 titles containing exactly 50 planted near-duplicate pairs."""
    rng = random.Random(CORPUS_SEED)
    texts, seen = [], set()
    while len(texts) < CORPUS_SIZE - NEAR_DUPLICATE_COUNT:
        title = random_title(rng)
        if title not in seen:
            seen.add(title)
            texts.append(title)
    planted = []
    for index in rng.sample(range(len(texts)), NEAR_DUPLICATE_COUNT):
        mutant = make_near_duplicate(texts[index], rng)
        while mutant in seen:
            mutant = make_near_duplicate(texts[index], rng)
        seen.add(mutant)
        planted.append((texts[index], mutant))
        texts.append(mutant)
    rng.shuffle(texts)
    return texts, planted


def write_corpus(texts, directory, per_file=2000):
    os.makedirs(directory, exist_ok=True)
    for start in range(0, len(texts), per_file):
        chunk = texts[start:start + per_file]
        path = os.path.join(directory, f"part-{start // per_file:03d}.txt")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(chunk) + "\n")


def expected_bucket_count(fingerprints, threshold=DEFAULT_THRESHOLD):
    layout = band_layout(64, threshold + 1)
    keys = set()
    for fp in fingerprints:
        for band_index, (low, high) in enumerate(layout):
            keys.add((band_index, (fp >> low) & ((1 << (high - low)) - 1)))
    return len(keys)

class BigCorpusTest(unittest.TestCase):
    """Criteria 1, 2, 3, 5 and the fingerprint half of criterion 4."""

    @classmethod
    def setUpClass(cls):
        texts, cls.planted = build_big_corpus()
        cls.tmp = tempfile.TemporaryDirectory()
        write_corpus(texts, cls.tmp.name)
        cls.records = list(iter_records(cls.tmp.name))
        cls.report = build_report(cls.records)
        cls.text_by_id = {record["id"]: record["text"] for record in cls.records}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def group_pairs(self):
        pairs = set()
        for group in self.report["groups"]:
            pair = frozenset(self.text_by_id[member["id"]] for member in group["members"])
            pairs.add(pair)
        return pairs

    def test_processed_equals_100000(self):
        """Criterion 5: every record is processed, none dropped."""
        self.assertEqual(self.report["processed"], CORPUS_SIZE)
        self.assertEqual(len(self.records), CORPUS_SIZE)

    def test_exactly_50_groups_of_exactly_2(self):
        """Criteria 1 and 2: exactly 50 near-duplicate groups of size 2."""
        groups = self.report["groups"]
        self.assertEqual(len(groups), NEAR_DUPLICATE_COUNT)
        for group in groups:
            self.assertEqual(group["size"], 2)
            self.assertEqual(len(group["members"]), 2)
        planted_pairs = {frozenset(pair) for pair in self.planted}
        self.assertEqual(self.group_pairs(), planted_pairs)

    def test_group_members_have_distinct_sha256(self):
        """Criterion 3: near-duplicate members really differ in content."""
        for group in self.report["groups"]:
            digests = [member["sha256"] for member in group["members"]]
            self.assertEqual(len(set(digests)), len(digests))
            self.assertEqual(group["match_type"], MATCH_FINGERPRINT)

    def test_report_structure(self):
        """Criterion 7: top-level fields and per-group details."""
        for key in ("processed", "groups", "buckets"):
            self.assertIn(key, self.report)
        self.assertIsInstance(self.report["processed"], int)
        self.assertIsInstance(self.report["buckets"], int)
        for group in self.report["groups"]:
            self.assertIn("size", group)
            self.assertIn("match_type", group)
            self.assertIn("members", group)
            self.assertEqual(group["size"], len(group["members"]))
            for member in group["members"]:
                self.assertIn("id", member)
                self.assertIn("source", member)
                self.assertIn("sha256", member)

    def test_buckets_matches_actual_bucket_count(self):
        """Criterion 6 (second half): buckets equals the real bucket count."""
        fingerprints = [fingerprint(record["text"]) for record in self.records]
        self.assertEqual(self.report["buckets"], expected_bucket_count(fingerprints))


class ExactDuplicateTest(unittest.TestCase):
    """Criterion 4: identical content is reported as exact, not fingerprint."""

    def test_identical_texts_grouped_as_exact(self):
        text = "纯棉 短袖 T恤 summer cotton 宽松 大码 新款 男装"
        with tempfile.TemporaryDirectory() as directory:
            for name in ("a.txt", "b.txt"):
                with open(os.path.join(directory, name), "w", encoding="utf-8") as handle:
                    handle.write(text + "\n")
            records = list(iter_records(directory))
            report = build_report(records)
        self.assertEqual(report["processed"], 2)
        self.assertEqual(len(report["groups"]), 1)
        group = report["groups"][0]
        self.assertEqual(group["size"], 2)
        self.assertEqual(group["match_type"], MATCH_EXACT)
        digests = {member["sha256"] for member in group["members"]}
        self.assertEqual(len(digests), 1)


class CrossBucketTest(unittest.TestCase):
    """Criterion 6: pairs in different high-bit buckets are still found."""

    PAIR_COUNT = 24

    @classmethod
    def setUpClass(cls):
        rng = random.Random(13579)
        cls.pairs = []
        seen = set()
        while len(cls.pairs) < cls.PAIR_COUNT:
            base, mutant = make_cross_bucket_pair(rng)
            if base in seen or mutant in seen:
                continue
            seen.add(base)
            seen.add(mutant)
            cls.pairs.append((base, mutant))
        texts = [text for pair in cls.pairs for text in pair]
        rng.shuffle(texts)
        cls.tmp = tempfile.TemporaryDirectory()
        write_corpus(texts, cls.tmp.name, per_file=16)
        cls.records = list(iter_records(cls.tmp.name))
        cls.report = build_report(cls.records)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_pairs_really_land_in_different_high_bit_buckets(self):
        self.assertGreaterEqual(len(self.pairs), 20)
        for base, mutant in self.pairs:
            base_high = fingerprint(base) >> HIGH_16_SHIFT
            mutant_high = fingerprint(mutant) >> HIGH_16_SHIFT
            self.assertNotEqual(base_high, mutant_high)
            self.assertLessEqual(hamming(fingerprint(base), fingerprint(mutant)), DEFAULT_THRESHOLD)

    def test_all_cross_bucket_pairs_are_found(self):
        self.assertEqual(self.report["processed"], 2 * self.PAIR_COUNT)
        self.assertEqual(len(self.report["groups"]), self.PAIR_COUNT)
        text_by_id = {record["id"]: record["text"] for record in self.records}
        found = set()
        for group in self.report["groups"]:
            self.assertEqual(group["size"], 2)
            found.add(frozenset(text_by_id[member["id"]] for member in group["members"]))
        self.assertEqual(found, {frozenset(pair) for pair in self.pairs})

    def test_buckets_matches_actual_bucket_count(self):
        fingerprints = [fingerprint(record["text"]) for record in self.records]
        self.assertEqual(self.report["buckets"], expected_bucket_count(fingerprints))


class DeterminismTest(unittest.TestCase):
    """Requirement 6: identical input yields identical group numbering."""

    def test_group_ids_are_stable_across_runs(self):
        rng = random.Random(24680)
        texts, seen = [], set()
        while len(texts) < 4000:
            title = random_title(rng)
            if title not in seen:
                seen.add(title)
                texts.append(title)
        for index in rng.sample(range(len(texts)), 5):
            mutant = make_near_duplicate(texts[index], rng)
            while mutant in seen:
                mutant = make_near_duplicate(texts[index], rng)
            seen.add(mutant)
            texts.append(mutant)
        rng.shuffle(texts)
        with tempfile.TemporaryDirectory() as directory:
            write_corpus(texts, directory)
            first = build_report(list(iter_records(directory)))
            second = build_report(list(iter_records(directory)))
        self.assertEqual(
            json.dumps(first["groups"], sort_keys=True),
            json.dumps(second["groups"], sort_keys=True),
        )
        self.assertEqual(
            [group["group_id"] for group in first["groups"]],
            [group["group_id"] for group in second["groups"]],
        )
        self.assertEqual(first["buckets"], second["buckets"])


class CliTest(unittest.TestCase):
    """The demo entry point prints a one-line summary and writes a report."""

    def test_cli_summary_and_report_file(self):
        rng = random.Random(112233)
        texts, seen = [], set()
        while len(texts) < 2000:
            title = random_title(rng)
            if title not in seen:
                seen.add(title)
                texts.append(title)
        mutant = make_near_duplicate(texts[0], rng)
        while mutant in seen:
            mutant = make_near_duplicate(texts[0], rng)
        texts.append(mutant)
        rng.shuffle(texts)
        with tempfile.TemporaryDirectory() as directory:
            write_corpus(texts, directory)
            out_path = os.path.join(directory, "out", "report.json")
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                cli_main(["--dir", directory, "--out", out_path])
            summary = stdout.getvalue().strip()
            with open(out_path, encoding="utf-8") as handle:
                report = json.load(handle)
        self.assertIn("processed=2001", summary)
        self.assertIn("near_duplicate_groups=1", summary)
        self.assertIn("buckets=", summary)
        self.assertEqual(report["processed"], 2001)
        self.assertEqual(len(report["groups"]), 1)


class TokenizeTest(unittest.TestCase):
    def test_chinese_split_by_character_english_by_word(self):
        self.assertEqual(tokenize("纯棉T恤 summer 2024"),
                         ["纯", "棉", "T", "恤", "summer", "2024"])

    def test_punctuation_and_whitespace_are_separators(self):
        self.assertEqual(tokenize("你好, world!  再见。"),
                         ["你", "好", "world", "再", "见"])

    def test_weight_is_tf_times_token_length(self):
        weighted = weighted_term_frequencies("棉 棉 summer summer")
        self.assertEqual(weighted["棉"], 2)
        self.assertEqual(weighted["summer"], 2 * len("summer"))
        self.assertEqual(term_frequencies(["a", "a", "b"]), {"a": 2, "b": 1})


class SimhashTest(unittest.TestCase):
    def test_identical_text_has_identical_fingerprint(self):
        text = "纯棉 T恤 宽松 大码 新款"
        self.assertEqual(hamming(fingerprint(text), fingerprint(text)), 0)

    def test_similar_text_is_closer_than_unrelated_text(self):
        base = "纯棉 短袖 T恤 宽松 大码 夏季 新款 男装 透气 吸汗"
        similar = "纯棉 短袖 T恤 宽松 大码 夏季 新款 男装 透气 排汗"
        other = "laptop stand aluminum adjustable ergonomic desk"
        self.assertLess(
            hamming(fingerprint(base), fingerprint(similar)),
            hamming(fingerprint(base), fingerprint(other)),
        )

    def test_fingerprint_uses_64_bits(self):
        self.assertLess(fingerprint(random_title(random.Random(5))), 1 << 64)


class BucketLayoutTest(unittest.TestCase):
    def test_default_layout_is_four_bands_of_16_starting_high(self):
        self.assertEqual(band_layout(64, 4), [(48, 64), (32, 48), (16, 32), (0, 16)])

    def test_layout_covers_all_bits_without_overlap(self):
        for bands in (1, 2, 3, 4, 5, 8):
            layout = band_layout(64, bands)
            self.assertEqual(layout[0][1], 64)
            self.assertEqual(layout[-1][0], 0)
            for (low, high), (next_low, next_high) in zip(layout, layout[1:]):
                self.assertEqual(low, next_high)

    def test_band_count_exceeds_threshold_for_recall(self):
        layout = band_layout(64, DEFAULT_THRESHOLD + 1)
        self.assertGreater(len(layout), DEFAULT_THRESHOLD)


if __name__ == "__main__":
    unittest.main()
