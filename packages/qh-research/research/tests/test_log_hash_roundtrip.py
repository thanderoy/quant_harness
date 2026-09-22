"""The chain's hash must survive the round-trip it is stored through.

`verify()` recomputes each entry's hash from the entry as *read back from
JSONL* and compares it to the hash computed when the entry was *written*. So
the canonical form has to be invariant under `json.dumps` followed by
`json.loads`. It was not.

`json.dumps` coerces non-string mapping keys to strings. With
`sort_keys=True`, `{20: .., 50: .., 100: ..}` serialises in numeric order
(20, 50, 100) but reads back as string keys that sort lexicographically
("100", "20", "50"). Two different canonical strings, two different hashes,
and `verify()` reporting "contents tampered" on an entry nobody had touched.

This survived 108 entries because no caller had passed a non-string key, and
it needs a *third* key that reorders under string sort to show up at all —
{20, 50} alone hashes identically both ways. The first caller to pass
horizon-keyed metrics tripped it immediately.

These tests are about the invariant, not that one caller: a hash chain whose
canonical form depends on how a caller happened to type its keys cannot
detect tampering, because it cannot tell tampering from serialisation.
"""

from __future__ import annotations

import json

import pytest

from research.log import _canonical, _hash, _stringify_keys


def roundtrip(payload: dict) -> dict:
    """Exactly what the store does to an entry between write and read."""
    return json.loads(json.dumps(payload))


# -- the invariant ----------------------------------------------------------

@pytest.mark.parametrize("metrics", [
    {"pooled": {20: 1.0, 50: 2.0, 100: 3.0}},          # the case that broke
    {"pooled": {1: "a", 2: "b", 10: "c"}},             # 10 sorts before 2
    {"by_n": {100: 0.1, 2000: 0.2, 30: 0.3}},
    {"nested": {"inner": {5: {7: [1, 2]}}}},
    {"mixed": {"a": 1, 2: "b"}},
    {"floats": {1.5: "x", 10.5: "y"}},
])
def test_hash_is_stable_across_the_jsonl_roundtrip(metrics):
    payload = {"seq": 1, "metrics": metrics}
    assert _hash(payload) == _hash(roundtrip(payload)), (
        "an entry hashes differently after being written and read back, so "
        "verify() would call it tampered")


def test_the_specific_ordering_that_caused_it():
    """Named so the regression is recognisable, not just covered."""
    ints = {"m": {20: 1.0, 50: 2.0, 100: 3.0}}
    assert _canonical(ints) == _canonical(roundtrip(ints))
    # and the order is the string order in both
    assert _canonical(ints).index('"100"') < _canonical(ints).index('"20"')


# -- the helper -------------------------------------------------------------

def test_keys_are_stringified_at_every_depth():
    out = _stringify_keys({1: {2: {3: "deep"}}, "already": {4: [{"5": 6}]}})
    assert list(out) == ["1", "already"]
    assert list(out["1"]) == ["2"]
    assert list(out["1"]["2"]) == ["3"]
    assert list(out["already"]["4"][0]) == ["5"]


def test_values_are_left_alone():
    v = {"a": [1, 2.5, "x", None, True]}
    assert _stringify_keys(v) == v


def test_tuples_become_lists_as_json_would_make_them():
    """A tuple value survives dumps as a list; the canonical form must agree
    so a tuple-valued metric does not break the chain either."""
    payload = {"m": {"panel": ("EURUSD", "GBPUSD")}}
    assert _hash(payload) == _hash(roundtrip(payload))


# -- what must not have changed ---------------------------------------------

def test_string_keyed_entries_hash_exactly_as_before():
    """Every existing entry has string keys. If stringifying changed their
    canonical form this would be a chain migration rather than a fix, and all
    109 stored hashes would have to be rewritten."""
    payload = {"seq": 3, "metrics": {"dsr": 0.61, "n_trials": 26},
               "note": "unchanged"}
    assert _canonical(payload) == json.dumps(
        {k: v for k, v in payload.items() if k != "entry_hash"},
        sort_keys=True, separators=(",", ":"))


def test_entry_hash_is_still_excluded():
    a = {"seq": 1, "metrics": {}, "entry_hash": "aaa"}
    b = {"seq": 1, "metrics": {}, "entry_hash": "bbb"}
    assert _hash(a) == _hash(b)


def test_the_live_chain_still_verifies():
    from research.log import verify
    ok, msg = verify()
    assert ok, msg
