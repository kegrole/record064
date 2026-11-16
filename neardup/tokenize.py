"""Tokenization and term weighting.

Rules:
- Every CJK ideograph is a token of its own (Chinese is split by character).
- Every maximal run of ASCII letters/digits is one token (English words).
- Everything else (whitespace, punctuation, symbols) is a separator.
- A term's weight is its term frequency multiplied by its length in
  characters, so Chinese characters weigh 1 per occurrence and English
  words weigh len(word) per occurrence.
"""

import re

TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def tokenize(text):
    """Split text into tokens according to the rules above."""
    return TOKEN_RE.findall(text)


def term_frequencies(tokens):
    """Count raw term frequencies."""
    tf = {}
    for token in tokens:
        tf[token] = tf.get(token, 0) + 1
    return tf


def weighted_term_frequencies(text):
    """Return {term: tf * len(term)} for the given text."""
    weighted = {}
    for term, count in term_frequencies(tokenize(text)).items():
        weighted[term] = count * len(term)
    return weighted
