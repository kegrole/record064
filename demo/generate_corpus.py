"""Generate the demo corpus: 100000 titles with exactly 50 near-duplicates.

Rules: each record is a product-title-like mix of Chinese runs and English
words.  A near-duplicate is produced by replacing 2-3 Chinese characters of
an existing title in place (length and structure unchanged), keeping the
SimHash Hamming distance to its source at most 3 while the SHA-256 differs.
Everything is driven by a fixed seed, so regeneration is reproducible.

Usage: python demo/generate_corpus.py --out demo/corpus
"""

import argparse
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from neardup.simhash import hamming, simhash
from neardup.tokenize import weighted_term_frequencies

SEED = 20261116
TOTAL = 100000
NEAR_DUPLICATES = 50
RECORDS_PER_FILE = 1000

CJK_POOL = [chr(0x4E00 + i) for i in range(1500)]


def _build_words():
    rng = random.Random(424242)
    letters = "abcdefghijklmnopqrstuvwxyz"
    words = set()
    while len(words) < 20000:
        words.add("".join(rng.choice(letters) for _ in range(rng.randint(3, 8))))
    return sorted(words)


WORDS = _build_words()


def fingerprint(text):
    return simhash(weighted_term_frequencies(text))


def random_title(rng):
    parts = []
    parts.extend(rng.sample(WORDS, rng.randint(6, 10)))
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
        if candidate != text and hamming(source_fp, fingerprint(candidate)) <= 3:
            return candidate
    raise RuntimeError("could not build a near-duplicate")


def build_corpus(total=TOTAL, n_near=NEAR_DUPLICATES, seed=SEED):
    rng = random.Random(seed)
    texts, seen = [], set()
    while len(texts) < total - n_near:
        title = random_title(rng)
        if title not in seen:
            seen.add(title)
            texts.append(title)
    for index in rng.sample(range(len(texts)), n_near):
        mutant = make_near_duplicate(texts[index], rng)
        while mutant in seen:
            mutant = make_near_duplicate(texts[index], rng)
        seen.add(mutant)
        texts.append(mutant)
    rng.shuffle(texts)
    return texts


def write_corpus(texts, out_dir, per_file=RECORDS_PER_FILE):
    os.makedirs(out_dir, exist_ok=True)
    for start in range(0, len(texts), per_file):
        chunk = texts[start:start + per_file]
        path = os.path.join(out_dir, f"part-{start // per_file:03d}.txt")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(chunk) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "corpus"))
    args = parser.parse_args()
    texts = build_corpus()
    write_corpus(texts, args.out)
    print(f"wrote {len(texts)} records to {args.out}")


if __name__ == "__main__":
    main()
