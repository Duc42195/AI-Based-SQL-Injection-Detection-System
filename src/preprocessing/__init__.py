"""Preprocessing: canonicalization and tokenization/feature extraction.

The canonicalization step normalises evasion-prone input *before* tokenizing:
decode common encodings (URL-encode, hex, ``CHAR()``/``ASCII()``), fold SQL
keyword case, and *mark* (not strip) ``/* */`` and ``--`` comments as an
explicit feature. This reduces the risk of syntactic-equivalence evasion.
"""
