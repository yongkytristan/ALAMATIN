#!/usr/bin/env python3
"""Generate reproducible synthetic Indonesian addresses for NER training.

Every address is assembled from a valid Jawa Barat administrative chain
(``data/final/jabar-postal-app-lookup.csv``) plus synthetic, non-private
street/landmark/name components -- never a real or scraped address. Labels
are produced directly from the pieces used to build each token sequence, so
annotation is exact by construction; noise is applied afterwards and never
changes label boundaries.

Multiple noisy renderings of the same underlying ("base") address share a
``base_id`` and are always assigned to the same split, so no near-duplicate
address ever leaks across train/dev/test_synth.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from alamatin.label_schema import (  # noqa: E402
    BIO_LABELS,
    SCHEMA_VERSION as LABEL_SCHEMA_VERSION,
    validate_bio_sequence,
)
from build_source_review_workbook import file_sha256, read_csv  # noqa: E402


GENERATOR_VERSION = "1.0.0"
TEMPLATE_VERSION = "1.0.0"
DEFAULT_REFERENCE = ROOT / "data" / "final" / "jabar-postal-app-lookup.csv"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "synthetic"

# ---------------------------------------------------------------------------
# Synthetic component pools. None of these are derived from OSM, a scraped
# gazetteer, or any real customer/household address; they are generic,
# reusable name fragments so the generator never needs a real street or
# landmark dataset (ALM-009 remains an optional future enhancement).
# ---------------------------------------------------------------------------

STREET_DESIGNATORS: tuple[str, ...] = ("Jalan", "Jl.", "Jln.", "Jln", "JL", "jl.")
STREET_DESIGNATOR_CANONICAL: frozenset[str] = frozenset({"Jalan"})
STREET_NAMES: tuple[str, ...] = (
    "Merdeka", "Sudirman", "Diponegoro", "Asia Afrika", "Cihampelas",
    "Cendrawasih", "Mawar", "Melati", "Anggrek", "Kenanga", "Flamboyan",
    "Kartini", "Veteran", "Pahlawan", "Pemuda", "Sriwijaya", "Gatot Subroto",
    "Ahmad Yani", "Ir. H. Juanda", "Soekarno Hatta", "Cempaka Putih",
    "Cempaka Sari", "Cisitu", "Dago", "Pasteur", "Setiabudi", "Suci",
    "Terusan Buah Batu", "Cikutra", "Antapani", "Riau", "Cikapayang",
    "Aster", "Bougenville", "Kamboja", "Teratai", "Nusa Indah", "Kenari",
    "Kelapa Gading", "Manggis", "Rambutan", "Durian", "Sawo", "Kecapi",
)
NOMOR_DESIGNATORS: tuple[str, ...] = ("No.", "No", "Nomor", "Nomer")
GANG_DESIGNATORS: tuple[str, ...] = ("Gang", "Gg.", "Gg")
GANG_DESIGNATOR_CANONICAL: frozenset[str] = frozenset({"Gang"})

KELURAHAN_DESIGNATORS: tuple[str, ...] = ("Kel.", "Kelurahan", "Desa", "Ds.")
KELURAHAN_DESIGNATOR_CANONICAL: frozenset[str] = frozenset({"Kelurahan", "Desa"})
KECAMATAN_DESIGNATORS: tuple[str, ...] = ("Kec.", "Kecamatan")
KECAMATAN_DESIGNATOR_CANONICAL: frozenset[str] = frozenset({"Kecamatan"})
KOTA_PREFIX_FORMS: dict[str, tuple[str, ...]] = {
    "KOTA": ("Kota",),
    "KAB.": ("Kabupaten", "Kab.", "Kab"),
}
KOTA_MARKER_CANONICAL: frozenset[str] = frozenset({"Kota", "Kabupaten"})

PROVINCE_FORMS: dict[str, tuple[str, ...]] = {
    "JAWA BARAT": ("Jawa Barat", "Provinsi Jawa Barat", "Jabar"),
}
PROVINCE_FORM_CANONICAL: frozenset[str] = frozenset({"Jawa Barat", "Provinsi Jawa Barat"})

LANDMARK_DIRECTIONS: tuple[str, ...] = ("depan", "belakang", "dekat", "samping", "seberang")
# Category "" means the name is already a self-contained landmark (SDN/SD
# Negeri/Kantor Pos/Puskesmas already say what kind of place it is), so no
# extra category word is prefixed.
LANDMARK_CATEGORIES: dict[str, tuple[str, ...]] = {
    "Masjid": ("Al-Ikhlas", "Al-Falah", "An-Nur", "Al-Hidayah", "Baiturrahman"),
    "Gereja": ("Santo Yusuf", "Kristus Raja", "Immanuel"),
    "": (
        "SDN 1", "SMPN 2", "SMAN 3", "SD Negeri 4", "MI Nurul Iman",
        "Kantor Pos", "Puskesmas",
    ),
    "Minimarket": ("Indomaret", "Alfamart", "Alfamidi"),
    "Pasar": ("Baru", "Minggu", "Cikapundung"),
    "Taman": ("Kota", "Lansia", "Bermain"),
}
DETAIL_BLOK_PATTERNS: tuple[str, ...] = ("Blok", "Blok")
DETAIL_APARTMENT_TEMPLATES: tuple[tuple[str, ...], ...] = (
    ("Apartemen", "{name}", "Tower", "{tower}", "Lantai", "{floor}", "Unit", "{unit}"),
    ("Perumahan", "{name}", "Blok", "{blok}"),
    ("Komplek", "{name}", "Blok", "{blok}", "No.", "{unit}"),
)
COMPLEX_NAMES: tuple[str, ...] = (
    "Griya Asri", "Bumi Indah", "Sentra Timur", "Green Bay", "Puri Cipageran",
    "Taman Melati", "Vila Bandung Indah", "Buah Batu Regency",
)

PREFIX_JUNK: tuple[str, ...] = (
    "Alamat:", "Kirim ke:", "Alamat Pengiriman:", "Tujuan:",
)
SUFFIX_INSTRUCTIONS: tuple[str, ...] = (
    "kirim setelah jam 5 sore",
    "titip tetangga jika tidak ada orang",
    "hubungi dulu sebelum sampai",
    "hati-hati barang pecah",
    "tolong telepon jika sudah dekat",
)

TYPO_RNG_WEIGHT = 0.15
CASE_VARIANTS = ("upper", "lower", "title", "none")

# ---------------------------------------------------------------------------
# Slot order templates. Each template is a list of slot keys; the pipeline
# skips a slot when the base address did not include that optional field.
# ---------------------------------------------------------------------------

ORDER_TEMPLATES: tuple[tuple[str, ...], ...] = (
    ("JALAN", "NOMOR", "RT_RW", "KELURAHAN", "KECAMATAN", "KOTA", "PROVINSI", "KODEPOS"),
    ("JALAN", "NOMOR", "DETAIL", "RT_RW", "LANDMARK", "KELURAHAN", "KECAMATAN", "KOTA", "KODEPOS", "PROVINSI"),
    ("LANDMARK", "JALAN", "NOMOR", "KELURAHAN", "KECAMATAN", "KOTA", "PROVINSI", "KODEPOS"),
    ("DETAIL", "JALAN", "NOMOR", "RT_RW", "KELURAHAN", "KECAMATAN", "KOTA", "KODEPOS"),
    ("JALAN", "NOMOR", "LANDMARK", "RT_RW", "KELURAHAN", "KECAMATAN", "KOTA", "PROVINSI"),
    ("RT_RW", "JALAN", "NOMOR", "KELURAHAN", "KECAMATAN", "KOTA", "PROVINSI", "KODEPOS"),
    ("JALAN", "RT_RW", "NOMOR", "DETAIL", "KELURAHAN", "KECAMATAN", "KOTA", "PROVINSI", "KODEPOS"),
    ("NOMOR", "JALAN", "LANDMARK", "KELURAHAN", "KECAMATAN", "KOTA", "KODEPOS", "PROVINSI"),
)


class GeneratorError(ValueError):
    """Raised when the generator input or output is inconsistent."""


def _add(tokens: list[str], labels: list[str], text: str, label: str) -> None:
    """Split ``text`` on whitespace and append BIO-tagged tokens."""

    pieces = text.split()
    for index, piece in enumerate(pieces):
        tokens.append(piece)
        labels.append("O" if label == "O" else f"{'B' if index == 0 else 'I'}-{label}")


def _apply_typo(word: str, rng: random.Random) -> str:
    if len(word) < 4:
        return word
    letters = [c for c in word if c.isalpha()]
    if not letters:
        return word
    kind = rng.choice(("swap", "drop", "double"))
    position = rng.randrange(1, len(word) - 1)
    if kind == "drop":
        return word[:position] + word[position + 1 :]
    if kind == "double":
        return word[: position + 1] + word[position] + word[position + 1 :]
    if position + 1 < len(word):
        chars = list(word)
        chars[position], chars[position + 1] = chars[position + 1], chars[position]
        return "".join(chars)
    return word


def _apply_case(text: str, variant: str) -> str:
    if variant == "upper":
        return text.upper()
    if variant == "lower":
        return text.lower()
    if variant == "title":
        return text.title()
    return text


def _load_chains(rows: Sequence[dict[str, str]]) -> list[dict[str, str]]:
    chains = []
    for row in rows:
        for field in (
            "village_code", "province_name", "city_name", "district_name",
            "village_name", "postal_code",
        ):
            if not row.get(field):
                raise GeneratorError(f"reference row missing {field}: {row}")
        chains.append(dict(row))
    if not chains:
        raise GeneratorError("reference file has no administrative chains")
    return chains


def _build_kota_component(city_name: str, rng: random.Random) -> tuple[str, str]:
    for prefix, forms in KOTA_PREFIX_FORMS.items():
        if city_name.startswith(prefix):
            name = city_name[len(prefix) :].strip()
            marker = rng.choice(forms)
            return marker, name.title()
    return "", city_name.title()


def _build_landmark(rng: random.Random) -> str:
    category = rng.choice(list(LANDMARK_CATEGORIES))
    names = LANDMARK_CATEGORIES[category]
    name = rng.choice(names)
    direction = rng.choice(LANDMARK_DIRECTIONS)
    label = f"{category} {name}".strip()
    return f"{direction} {label}"


def _build_detail(rng: random.Random) -> str:
    if rng.random() < 0.4:
        return f"{rng.choice(DETAIL_BLOK_PATTERNS)} {rng.choice('ABCDEFGH')}{rng.randint(1, 12)}"
    template = rng.choice(DETAIL_APARTMENT_TEMPLATES)
    values = {
        "name": rng.choice(COMPLEX_NAMES),
        "tower": rng.choice("ABCD"),
        "floor": str(rng.randint(1, 20)),
        "unit": f"{rng.randint(1, 20):02d}",
        "blok": f"{rng.choice('ABCDEFGH')}{rng.randint(1, 20)}",
    }
    return " ".join(part.format(**values) for part in template)


def build_base_address(base_id: int, chain: dict[str, str], rng: random.Random) -> dict[str, Any]:
    """Choose the substantive content of one base (pre-noise) address."""

    street = rng.choice(STREET_NAMES)
    is_gang = rng.random() < 0.15
    number = f"{rng.randint(1, 250)}" + (rng.choice(("", "A", "B", "C")) if rng.random() < 0.2 else "")
    include_rt_rw = rng.random() >= 0.30
    include_provinsi = rng.random() >= 0.50
    include_kodepos = rng.random() >= 0.40
    include_landmark = rng.random() < 0.25
    include_detail = rng.random() < 0.20
    include_pii = rng.random() < 0.30
    admin_conflict = include_kodepos and rng.random() < 0.08

    real_postal = chain["postal_code"]
    if admin_conflict:
        digits = list(real_postal)
        digits[-1] = str((int(digits[-1]) + rng.randint(1, 8)) % 10)
        digits[-2] = str((int(digits[-2]) + rng.randint(1, 8)) % 10)
        postal_value = "".join(digits)
    else:
        postal_value = real_postal

    return {
        "base_id": base_id,
        "village_code": chain["village_code"],
        "province_name": chain["province_name"],
        "city_name": chain["city_name"],
        "district_name": chain["district_name"],
        "village_name": chain["village_name"],
        "postal_code": postal_value,
        "admin_conflict": admin_conflict,
        "street": street,
        "is_gang": is_gang,
        "number": number,
        "rt": f"{rng.randint(1, 15):02d}" if include_rt_rw else None,
        "rw": f"{rng.randint(1, 15):02d}" if include_rt_rw else None,
        "landmark_text": _build_landmark(rng) if include_landmark else None,
        "detail_text": _build_detail(rng) if include_detail else None,
        "include_provinsi": include_provinsi,
        "include_kodepos": include_kodepos,
        "include_pii": include_pii,
    }


def render_variant(base: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    """Render one noisy token/label sequence for ``base``."""

    tokens: list[str] = []
    labels: list[str] = []
    noise: list[str] = []

    if rng.random() < 0.15:
        _add(tokens, labels, rng.choice(PREFIX_JUNK), "O")
        noise.append("prefix_junk")

    if base["include_pii"]:
        if rng.random() < 0.85:
            _add(tokens, labels, "[NAME]", "O")
        if rng.random() < 0.7:
            _add(tokens, labels, "[PHONE]", "O")
        noise.append("pii_mixed")

    typo_applied = False

    def typo(word: str) -> str:
        nonlocal typo_applied
        if not typo_applied and rng.random() < TYPO_RNG_WEIGHT:
            typo_applied = True
            return _apply_typo(word, rng)
        return word

    def add_jalan() -> None:
        pool = GANG_DESIGNATORS if base["is_gang"] else STREET_DESIGNATORS
        canonical = GANG_DESIGNATOR_CANONICAL if base["is_gang"] else STREET_DESIGNATOR_CANONICAL
        chosen = rng.choice(pool)
        if chosen not in canonical:
            noise.append("abbreviation")
        designator = typo(chosen)
        street = typo(base["street"])
        _add(tokens, labels, f"{designator} {street}", "JALAN")

    def add_nomor() -> None:
        designator = rng.choice(NOMOR_DESIGNATORS)
        _add(tokens, labels, f"{designator} {base['number']}", "NOMOR")

    def add_rt_rw() -> None:
        if base["rt"] is None:
            return
        _add(tokens, labels, f"RT {base['rt']}", "RT")
        _add(tokens, labels, f"RW {base['rw']}", "RW")

    def add_landmark() -> None:
        if base["landmark_text"] is None:
            return
        _add(tokens, labels, base["landmark_text"], "DETAIL_LOKASI")

    def add_detail() -> None:
        if base["detail_text"] is None:
            return
        _add(tokens, labels, base["detail_text"], "DETAIL_LOKASI")

    def add_kelurahan() -> None:
        name = typo(base["village_name"].title())
        if rng.random() < 0.7:
            chosen = rng.choice(KELURAHAN_DESIGNATORS)
            if chosen not in KELURAHAN_DESIGNATOR_CANONICAL:
                noise.append("abbreviation")
            designator = typo(chosen)
            _add(tokens, labels, f"{designator} {name}", "KELURAHAN")
        else:
            _add(tokens, labels, name, "KELURAHAN")

    def add_kecamatan() -> None:
        name = typo(base["district_name"].title())
        if rng.random() < 0.7:
            chosen = rng.choice(KECAMATAN_DESIGNATORS)
            if chosen not in KECAMATAN_DESIGNATOR_CANONICAL:
                noise.append("abbreviation")
            designator = typo(chosen)
            _add(tokens, labels, f"{designator} {name}", "KECAMATAN")
        else:
            _add(tokens, labels, name, "KECAMATAN")

    def add_kota() -> None:
        marker, name = _build_kota_component(base["city_name"], rng)
        if marker:
            if marker not in KOTA_MARKER_CANONICAL:
                noise.append("abbreviation")
            _add(tokens, labels, f"{marker} {name}", "KOTA_KABUPATEN")
        else:
            _add(tokens, labels, name, "KOTA_KABUPATEN")

    def add_provinsi() -> None:
        if not base["include_provinsi"]:
            return
        forms = PROVINCE_FORMS.get(base["province_name"], (base["province_name"].title(),))
        chosen = rng.choice(forms)
        if chosen not in PROVINCE_FORM_CANONICAL:
            noise.append("abbreviation")
        _add(tokens, labels, chosen, "PROVINSI")

    def add_kodepos() -> None:
        if not base["include_kodepos"]:
            return
        _add(tokens, labels, base["postal_code"], "KODEPOS")
        if base["admin_conflict"]:
            noise.append("admin_conflict")

    slot_actions = {
        "JALAN": add_jalan,
        "NOMOR": add_nomor,
        "RT_RW": add_rt_rw,
        "LANDMARK": add_landmark,
        "DETAIL": add_detail,
        "KELURAHAN": add_kelurahan,
        "KECAMATAN": add_kecamatan,
        "KOTA": add_kota,
        "PROVINSI": add_provinsi,
        "KODEPOS": add_kodepos,
    }
    template = rng.choice(ORDER_TEMPLATES)
    for slot in template:
        if rng.random() < 0.5 and tokens:
            noise_candidate = ","
            if slot in ("KELURAHAN", "KECAMATAN", "KOTA") and tokens[-1] != ",":
                tokens.append(noise_candidate)
                labels.append("O")
                if "separator" not in noise:
                    noise.append("separator")
        slot_actions[slot]()

    if rng.random() < 0.10:
        _add(tokens, labels, rng.choice(SUFFIX_INSTRUCTIONS), "O")
        noise.append("instruksi")

    case_variant = rng.choice(CASE_VARIANTS)
    if case_variant != "none":
        tokens = [_apply_case(token, case_variant) for token in tokens]
        noise.append(f"case_{case_variant}")

    if typo_applied:
        noise.append("typo")
    if not base["include_provinsi"]:
        noise.append("missing_provinsi")
    if not base["include_kodepos"]:
        noise.append("missing_kodepos")
    if base["rt"] is None:
        noise.append("missing_rt_rw")
    if base["is_gang"]:
        noise.append("gang")

    valid, reason = validate_bio_sequence(labels)
    if not valid:
        raise GeneratorError(f"generated invalid BIO sequence: {reason}")

    return {
        "base_id": base["base_id"],
        "village_code": base["village_code"],
        "tokens": tokens,
        "labels": labels,
        "categories": sorted(set(noise)),
    }


def generate_split(
    chains: Sequence[dict[str, str]],
    base_count: int,
    variants_per_base: int,
    rng: random.Random,
    next_base_id: list[int],
) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    for _ in range(base_count):
        chain = rng.choice(chains)
        base = build_base_address(next_base_id[0], chain, rng)
        next_base_id[0] += 1
        for variant_index in range(variants_per_base):
            example = render_variant(base, rng)
            example["id"] = f"SYN-{base['base_id']:07d}-{variant_index:02d}"
            examples.append(example)
    return examples


def build_dataset(
    chains: Sequence[dict[str, str]],
    seed: int,
    train_bases: int,
    dev_bases: int,
    test_bases: int,
    variants_per_base: int,
) -> dict[str, list[dict[str, Any]]]:
    rng = random.Random(seed)
    next_base_id = [0]
    return {
        "train": generate_split(chains, train_bases, variants_per_base, rng, next_base_id),
        "dev": generate_split(chains, dev_bases, variants_per_base, rng, next_base_id),
        "test_synth": generate_split(chains, test_bases, variants_per_base, rng, next_base_id),
    }


def _check_no_leakage(splits: dict[str, list[dict[str, Any]]]) -> None:
    owner: dict[int, str] = {}
    for split_name, examples in splits.items():
        for example in examples:
            base_id = example["base_id"]
            if base_id in owner and owner[base_id] != split_name:
                raise GeneratorError(
                    f"base_id {base_id} leaked across splits: "
                    f"{owner[base_id]} and {split_name}"
                )
            owner[base_id] = split_name


def _write_split(path: Path, examples: Sequence[dict[str, Any]]) -> None:
    payload = {
        "schema_version": LABEL_SCHEMA_VERSION,
        "generator_version": GENERATOR_VERSION,
        "template_version": TEMPLATE_VERSION,
        "label_order": list(BIO_LABELS),
        "examples": [
            {
                "id": example["id"],
                "categories": example["categories"],
                "tokens": example["tokens"],
                "labels": example["labels"],
            }
            for example in examples
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.part")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _noise_distribution(examples: Sequence[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for example in examples:
        counts.update(example["categories"])
    return dict(sorted(counts.items()))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--seed", type=int, default=20260813)
    parser.add_argument("--train-bases", type=int, default=1500)
    parser.add_argument("--dev-bases", type=int, default=250)
    parser.add_argument("--test-bases", type=int, default=250)
    parser.add_argument("--variants-per-base", type=int, default=3)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        _, rows = read_csv(args.reference)
        chains = _load_chains(rows)
        splits = build_dataset(
            chains,
            args.seed,
            args.train_bases,
            args.dev_bases,
            args.test_bases,
            args.variants_per_base,
        )
        _check_no_leakage(splits)

        output_paths = {
            "train": args.output_dir / "train.json",
            "dev": args.output_dir / "dev.json",
            "test_synth": args.output_dir / "test_synth.json",
        }
        for split_name, path in output_paths.items():
            _write_split(path, splits[split_name])

        summary = {
            "schema_version": LABEL_SCHEMA_VERSION,
            "generator_version": GENERATOR_VERSION,
            "template_version": TEMPLATE_VERSION,
            "seed": args.seed,
            "variants_per_base": args.variants_per_base,
            "reference_path": str(args.reference.relative_to(ROOT)),
            "reference_sha256": file_sha256(args.reference),
            "reference_chain_count": len(chains),
            "split_base_counts": {
                "train": args.train_bases,
                "dev": args.dev_bases,
                "test_synth": args.test_bases,
            },
            "split_example_counts": {
                name: len(examples) for name, examples in splits.items()
            },
            "noise_category_counts": {
                name: _noise_distribution(examples) for name, examples in splits.items()
            },
            "anti_leakage": "every base_id's variants are confined to exactly one split",
            "no_raw_private_address": (
                "street/landmark/name pools are synthetic and generic; only the "
                "administrative chain (province/city/district/village/postal_code) "
                "comes from the governed public reference"
            ),
            "output_sha256": {
                name: file_sha256(path) for name, path in output_paths.items()
            },
        }
        summary_path = args.output_dir / "generation-summary.json"
        temporary = summary_path.with_name(f".{summary_path.name}.part")
        temporary.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(summary_path)
    except (GeneratorError, OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(summary_path.read_text(encoding="utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
