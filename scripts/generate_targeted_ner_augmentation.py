#!/usr/bin/env python3
"""Generate train-only synthetic augmentation traced to ALM019-A02.

The generator encodes structural findings (sparse school-style addresses,
abbreviations, typos, RT/RW, fused administrative markers, and landmarks), but
does not read or copy any real_dev or sealed-test record.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import random
import re
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "configs" / "ner-v2-targeted-data.json"

STREET_NAMES: tuple[str, ...] = (
    "Mawar", "Melati", "Kenanga", "Anggrek", "Flamboyan", "Cempaka",
    "Pahlawan", "Pemuda", "Harapan", "Sejahtera", "Sukamaju",
    "Cahaya", "Karya Bakti", "Tunas Baru", "Bukit Asri", "Nusa Indah",
)
LANDMARKS: tuple[str, ...] = (
    "dekat Masjid Al-Ikhlas", "belakang Pasar Baru", "sebelah SDN 1",
    "depan Kantor Desa", "samping Puskesmas", "dekat Jembatan Merah",
)
PATTERNS: tuple[str, ...] = (
    "short_kampung",
    "short_jalan",
    "bare_location",
    "typo_admin",
    "fused_admin",
    "rt_rw",
    "landmark",
    "district_only",
)


def canonical_json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _add(tokens: list[str], labels: list[str], text: str, entity: str) -> None:
    for index, token in enumerate(text.split()):
        tokens.append(token)
        labels.append(f"{'B' if index == 0 else 'I'}-{entity}")


def _add_separator(tokens: list[str], labels: list[str], value: str = ",") -> None:
    tokens.append(value)
    labels.append("O")


def _strip_city_prefix(value: str) -> str:
    return re.sub(r"^(KAB\.|KABUPATEN|KOTA)\s+", "", value, flags=re.IGNORECASE).title()


def _typo(value: str, rng: random.Random) -> str:
    words = value.split()
    candidates = [index for index, word in enumerate(words) if len(word) >= 5]
    if not candidates:
        return value
    word_index = rng.choice(candidates)
    word = words[word_index]
    position = rng.randrange(1, len(word) - 1)
    operation = rng.choice(("drop", "swap"))
    if operation == "drop":
        words[word_index] = word[:position] + word[position + 1 :]
    else:
        chars = list(word)
        chars[position], chars[position + 1] = chars[position + 1], chars[position]
        words[word_index] = "".join(chars)
    return " ".join(words)


def render_example(
    example_id: int,
    chain: dict[str, str],
    pattern: str,
    rng: random.Random,
) -> dict[str, Any]:
    """Render one valid train-only augmentation example."""

    if pattern not in PATTERNS:
        raise ValueError(f"unknown targeted pattern: {pattern}")
    street = rng.choice(STREET_NAMES)
    district = chain["district_name"].title()
    city = _strip_city_prefix(chain["city_name"])
    tokens: list[str] = []
    labels: list[str] = []
    categories = {"alm019_a02", "sparse_address", pattern}

    if pattern == "short_kampung":
        _add(tokens, labels, f"Kp. {street}", "JALAN")
        _add_separator(tokens, labels)
        _add(tokens, labels, f"Kec. {district}", "KECAMATAN")
        _add_separator(tokens, labels)
        _add(tokens, labels, f"Kab. {city}", "KOTA_KABUPATEN")
        categories.add("abbreviation")
    elif pattern == "short_jalan":
        _add(tokens, labels, f"Jl. {street}", "JALAN")
        _add_separator(tokens, labels)
        _add(tokens, labels, f"Kecamatan {district}", "KECAMATAN")
        _add_separator(tokens, labels)
        _add(tokens, labels, f"Kab {city}", "KOTA_KABUPATEN")
        categories.add("abbreviation")
    elif pattern == "bare_location":
        _add(tokens, labels, street, "JALAN")
        _add_separator(tokens, labels)
        _add(tokens, labels, f"Kec {district}", "KECAMATAN")
        _add_separator(tokens, labels)
        _add(tokens, labels, f"Kb {city}", "KOTA_KABUPATEN")
        categories.add("abbreviation")
    elif pattern == "typo_admin":
        _add(tokens, labels, f"Kp {street}", "JALAN")
        _add_separator(tokens, labels)
        _add(tokens, labels, f"Kec {_typo(district, rng)}", "KECAMATAN")
        _add_separator(tokens, labels)
        _add(tokens, labels, f"Kab {_typo(city, rng)}", "KOTA_KABUPATEN")
        categories.update(("abbreviation", "typo"))
    elif pattern == "fused_admin":
        _add(tokens, labels, f"jl.{street}", "JALAN")
        _add_separator(tokens, labels)
        _add(tokens, labels, f"kecamatan{district.replace(' ', '')}", "KECAMATAN")
        _add_separator(tokens, labels)
        _add(tokens, labels, f"kab{city.replace(' ', '')}", "KOTA_KABUPATEN")
        categories.update(("abbreviation", "fused_token"))
    elif pattern == "rt_rw":
        _add(tokens, labels, f"Kp. {street}", "JALAN")
        _add(tokens, labels, f"RT {rng.randint(1, 15):02d}", "RT")
        _add(tokens, labels, f"RW {rng.randint(1, 15):02d}", "RW")
        _add_separator(tokens, labels)
        _add(tokens, labels, f"Kec. {district}", "KECAMATAN")
        _add_separator(tokens, labels)
        _add(tokens, labels, f"Kab. {city}", "KOTA_KABUPATEN")
        categories.update(("abbreviation", "rt_rw"))
    elif pattern == "landmark":
        _add(tokens, labels, f"Kp. {street}", "JALAN")
        _add(tokens, labels, rng.choice(LANDMARKS), "DETAIL_LOKASI")
        _add_separator(tokens, labels)
        _add(tokens, labels, f"Kec {district}", "KECAMATAN")
        _add_separator(tokens, labels)
        _add(tokens, labels, f"Kab {city}", "KOTA_KABUPATEN")
        categories.update(("abbreviation", "landmark"))
    else:
        _add(tokens, labels, f"Kp {street}", "JALAN")
        _add_separator(tokens, labels)
        _add(tokens, labels, f"Kec {district}", "KECAMATAN")
        categories.update(("abbreviation", "missing_city"))

    case = rng.choice(("none", "lower", "upper"))
    if case == "lower":
        tokens = [token.lower() for token in tokens]
        categories.add("case_lower")
    elif case == "upper":
        tokens = [token.upper() for token in tokens]
        categories.add("case_upper")

    return {
        "id": f"TGT-{example_id:07d}",
        "categories": sorted(categories),
        "tokens": tokens,
        "labels": labels,
    }


def build_examples(
    chains: Sequence[dict[str, str]], count: int, seed: int
) -> list[dict[str, Any]]:
    if not chains or count < 1:
        raise ValueError("at least one chain and one example are required")
    rng = random.Random(seed)
    patterns = [PATTERNS[index % len(PATTERNS)] for index in range(count)]
    rng.shuffle(patterns)
    return [
        render_example(index, rng.choice(chains), pattern, rng)
        for index, pattern in enumerate(patterns)
    ]


def load_chains(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    required = {"village_code", "city_name", "district_name"}
    if not rows or any(not required <= row.keys() for row in rows):
        raise ValueError("reference has no usable administrative chains")
    return rows


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.part")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    reference = ROOT / config["reference"]
    output = ROOT / config["output"]
    examples = build_examples(
        load_chains(reference), int(config["example_count"]), int(config["seed"])
    )
    distribution = Counter(
        category for example in examples for category in example["categories"]
    )
    payload = {
        "schema_version": "1.0.0",
        "generator_version": config["generator_version"],
        "split": "train_augmentation_only",
        "source_finding": config["source_finding"],
        "action_id": config["action_id"],
        "seed": config["seed"],
        "reference": config["reference"],
        "reference_sha256": hashlib.sha256(reference.read_bytes()).hexdigest(),
        "example_count": len(examples),
        "category_counts": dict(sorted(distribution.items())),
        "constraints": config["constraints"],
        "examples": examples,
    }
    payload["canonical_json_sha256_without_self"] = canonical_json_sha256(payload)
    write_json(output, payload)
    print(json.dumps({key: value for key, value in payload.items() if key != "examples"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
