#!/usr/bin/env python3
"""Resolve named competition bands and build the H1 cross-family edge feature."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

TOKENS = {
    "tmi": ("total magnetic intensity", "tmi"),
    "reduced_to_pole": ("reduced to pole", "reduced-to-pole", "rtp"),
    "isostatic_gravity": ("isostatic gravity anomaly", "isostatic gravity"),
    "surface_conductivity": ("surface conductivity", "conductivity surface"),
    "conductive_base_depth": ("depth to conductive base", "conductive base surface"),
}
EXCLUDED_TERMS = {
    # Prefer the scalar potential fields: slopes/derivatives are separate bands
    # and otherwise make a broad-name match ambiguous or silently change H1.
    "tmi": ("gradient", "slope", "source depth"),
    "isostatic_gravity": ("gradient", "slope"),
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def resolve_bands(descriptions: list[str], explicit: dict[str, str] | None = None) -> dict[str, int]:
    resolved: dict[str, int] = {}
    for key, choices in TOKENS.items():
        if explicit and key in explicit:
            matches = [i for i, name in enumerate(descriptions) if name.strip() == explicit[key].strip()]
            if len(matches) != 1:
                raise ValueError(f"Explicit layer name {explicit[key]!r} for {key} matched {len(matches)} bands")
            resolved[key] = matches[0]
            continue
        matches = []
        for i, name in enumerate(descriptions):
            lowered = name.casefold()
            if any(term in lowered for term in EXCLUDED_TERMS.get(key, ())):
                continue
            if any(re.search(r"(?<![a-z0-9])" + re.escape(token.casefold()) + r"(?![a-z0-9])", lowered) for token in choices):
                matches.append(i)
        # The long phrase can appear in multiple metadata strings (for example
        # in an alias). Failing closed is safer than guessing a band index.
        if len(matches) != 1:
            raise ValueError(f"Could not uniquely resolve {key} from band descriptions; matches={matches}, descriptions={descriptions}")
        resolved[key] = matches[0]
    if len(set(resolved.values())) != len(resolved):
        raise ValueError(f"Layer resolver mapped multiple logical channels to the same band: {resolved}")
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("data/processed/manifest.json"))
    parser.add_argument("--features", type=Path, default=Path("data/processed/features.npy"))
    parser.add_argument("--footprint", type=Path, default=Path("data/processed/footprint.npy"))
    parser.add_argument("--band-map", type=Path, default=None, help="optional JSON mapping logical channel names to exact band descriptions")
    parser.add_argument("--output", type=Path, default=Path("data/processed/features-h1.npy"))
    parser.add_argument("--sigma", type=float, nargs="+", default=[1.0, 2.0, 4.0])
    args = parser.parse_args()
    try:
        import numpy as np
        from gems.geology import multiscale_geophysical_edge_consensus

        if args.output.exists():
            raise FileExistsError(f"Refusing to overwrite existing feature stack: {args.output}")
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        descriptions = manifest.get("feature_descriptions")
        if not isinstance(descriptions, list) or not descriptions:
            raise ValueError("Manifest has no feature_descriptions; do not infer channel indexes")
        explicit = None if args.band_map is None else json.loads(args.band_map.read_text(encoding="utf-8"))
        band_map = resolve_bands([str(item) for item in descriptions], explicit)
        x = np.load(args.features, mmap_mode="r")
        footprint = np.asarray(np.load(args.footprint, mmap_mode="r"), dtype=bool)
        if x.ndim != 3 or x.shape[0] != len(descriptions) or x.shape[1:] != footprint.shape:
            raise ValueError("Prepared features, band descriptions, and footprint do not align")
        layers = {key: x[index] for key, index in band_map.items()}
        edge = np.asarray(
            multiscale_geophysical_edge_consensus(layers, footprint, scales_pixels=args.sigma),
            dtype=np.float32,
        )
        if not np.isfinite(edge[footprint]).all():
            raise ValueError("Edge consensus produced non-finite values inside the footprint")
        edge[~footprint] = 0.0
        args.output.parent.mkdir(parents=True, exist_ok=True)
        combined = np.lib.format.open_memmap(
            args.output, mode="w+", dtype=np.float32,
            shape=(x.shape[0] + 1, x.shape[1], x.shape[2]),
        )
        block = 256
        for row in range(0, x.shape[1], block):
            ys = slice(row, min(row + block, x.shape[1]))
            combined[:-1, ys, :] = x[:, ys, :]
            combined[-1, ys, :] = edge[ys, :]
        combined.flush()
        sidecar = {
            "candidate_id": "H1-edge-consensus",
            "input_features_sha256": sha256(args.features),
            "output_features_sha256": sha256(args.output),
            "manifest_sha256": sha256(args.manifest),
            "band_names": {key: descriptions[index] for key, index in band_map.items()},
            "band_indexes_zero_based": band_map,
            "scales_pixels": args.sigma,
            "transform": "multiscale cross-family edge-normal concordance; feature value in [0,1], not a fault probability",
            "status": "constructed; blocked validation not yet run",
            "warning": "Feature metadata mapping must be inspected; this transform has not been verified on official competition rasters in this checkout.",
        }
        args.output.with_suffix(".json").write_text(json.dumps(sidecar, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(sidecar, indent=2))
        return 0
    except Exception as exc:
        print(f"build_edge_consensus: ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
