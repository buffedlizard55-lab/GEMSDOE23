#!/usr/bin/env python3
"""Read-only stdlib audit for classic, single-band float32 TIFFs using TIFF LZW.

This is deliberately a narrow independent audit tool, not a replacement for
GDAL/rasterio. It inspects GeoTIFF tags and decompresses every strip to verify
finite-value bounds. Exact competition-template matching is performed by
`src/gems/submission.py` and still requires the official sample raster.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
from collections import Counter
from pathlib import Path
from typing import Any

TYPE_INFO = {
    1: ("B", 1), 2: ("c", 1), 3: ("H", 2), 4: ("I", 4), 5: ("II", 8),
    6: ("b", 1), 7: ("B", 1), 8: ("h", 2), 9: ("i", 4), 10: ("ii", 8),
    11: ("f", 4), 12: ("d", 8),
}


def read_ifd(data: bytes) -> tuple[str, dict[int, Any]]:
    if data[:2] == b"II":
        endian = "<"
    elif data[:2] == b"MM":
        endian = ">"
    else:
        raise ValueError("Invalid TIFF byte-order marker")
    if struct.unpack_from(endian + "H", data, 2)[0] != 42:
        raise ValueError("Only classic TIFF (magic 42), not BigTIFF, is supported")
    ifd_offset = struct.unpack_from(endian + "I", data, 4)[0]
    entry_count = struct.unpack_from(endian + "H", data, ifd_offset)[0]
    tags: dict[int, Any] = {}
    for i in range(entry_count):
        entry_offset = ifd_offset + 2 + 12 * i
        tag, field_type, count = struct.unpack_from(endian + "HHI", data, entry_offset)
        if field_type not in TYPE_INFO:
            raise ValueError(f"Unsupported TIFF field type {field_type} for tag {tag}")
        fmt, type_size = TYPE_INFO[field_type]
        length = count * type_size
        value_field_offset = entry_offset + 8
        value_offset = (
            struct.unpack_from(endian + "I", data, value_field_offset)[0]
            if length > 4 else value_field_offset
        )
        raw = data[value_offset:value_offset + length]
        if len(raw) != length:
            raise ValueError(f"Truncated TIFF field for tag {tag}")
        if field_type == 2:
            value = raw.rstrip(b"\0").decode("ascii", errors="replace")
        elif field_type in (5, 10):
            value = [struct.unpack_from(endian + fmt, raw, j) for j in range(0, length, 8)]
        else:
            value = list(struct.unpack(endian + str(count) + fmt, raw)) if count else []
        tags[tag] = value
    return endian, tags


def lzw_decode(compressed: bytes) -> bytes:
    bit_position = 0
    output = bytearray()
    clear_code, end_code = 256, 257
    table = {i: bytes((i,)) for i in range(256)}
    next_code, code_width, previous = 258, 9, None

    def get_code() -> int | None:
        nonlocal bit_position
        if bit_position + code_width > len(compressed) * 8:
            return None
        value = 0
        for _ in range(code_width):
            value = (value << 1) | ((compressed[bit_position >> 3] >> (7 - (bit_position & 7))) & 1)
            bit_position += 1
        return value

    while True:
        code = get_code()
        if code is None:
            break
        if code == clear_code:
            table = {i: bytes((i,)) for i in range(256)}
            next_code, code_width, previous = 258, 9, None
            continue
        if code == end_code:
            break
        if code in table:
            item = table[code]
        elif code == next_code and previous is not None:
            item = previous + previous[:1]
        else:
            raise ValueError(f"Invalid TIFF LZW code {code}; next={next_code}, width={code_width}")
        output.extend(item)
        if previous is not None and next_code < 4096:
            table[next_code] = previous + item[:1]
            next_code += 1
            # TIFF uses EarlyChange=1 when increasing code width.
            if code_width < 12 and next_code == (1 << code_width) - 1:
                code_width += 1
        previous = item
    return bytes(output)


def audit(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    endian, tags = read_ifd(data)

    def scalar(tag: int, default: Any = None) -> Any:
        values = tags.get(tag)
        return default if values is None else (values[0] if isinstance(values, list) and len(values) == 1 else values)

    width, height = int(scalar(256)), int(scalar(257))
    bits = int(scalar(258))
    compression = int(scalar(259))
    samples = int(scalar(277, 1))
    rows_per_strip = int(scalar(278, height))
    predictor = int(scalar(317, 1))
    sample_format = int(scalar(339, 1))
    if samples != 1 or bits != 32 or sample_format != 3:
        raise ValueError(f"Expected one float32 sample per pixel; samples={samples}, bits={bits}, sample_format={sample_format}")
    if compression != 5 or predictor != 1:
        raise ValueError(f"This independent decoder supports LZW with predictor=1 only; compression={compression}, predictor={predictor}")

    strip_offsets = tags.get(273)
    strip_byte_counts = tags.get(279)
    if not isinstance(strip_offsets, list) or not isinstance(strip_byte_counts, list):
        raise ValueError("Expected strip offset and byte-count arrays")
    if len(strip_offsets) != len(strip_byte_counts):
        raise ValueError("Strip offset and byte-count arrays differ in length")
    expected_strips = math.ceil(height / rows_per_strip)
    if len(strip_offsets) != expected_strips:
        raise ValueError(f"Strip count {len(strip_offsets)} does not match expected {expected_strips}")

    finite_count = nan_count = positive_inf_count = negative_inf_count = 0
    minimum, maximum = math.inf, -math.inf
    value_counts: Counter[float] = Counter()
    pixel_count = 0
    for strip_index, (offset, byte_count) in enumerate(zip(strip_offsets, strip_byte_counts)):
        decoded = lzw_decode(data[int(offset):int(offset) + int(byte_count)])
        strip_rows = min(rows_per_strip, height - strip_index * rows_per_strip)
        expected_size = width * strip_rows * 4
        if len(decoded) != expected_size:
            raise ValueError(f"Strip {strip_index} decoded to {len(decoded)} bytes; expected {expected_size}")
        for (value,) in struct.iter_unpack(endian + "f", decoded):
            pixel_count += 1
            if math.isnan(value):
                nan_count += 1
            elif math.isinf(value):
                if value > 0:
                    positive_inf_count += 1
                else:
                    negative_inf_count += 1
            else:
                finite_count += 1
                minimum, maximum = min(minimum, value), max(maximum, value)
                value_counts[value] += 1

    geokeys = tags.get(34735, [])
    epsg = None
    if len(geokeys) >= 4:
        nkeys = geokeys[3]
        for i in range(nkeys):
            key_id, location, count, value_offset = geokeys[4 + 4 * i:8 + 4 * i]
            if key_id == 3072 and location == 0 and count == 1:
                epsg = int(value_offset)
    scale = tags.get(33550)
    tiepoint = tags.get(33922)
    nodata = tags.get(42113)
    nodata_value = nodata if isinstance(nodata, str) else None
    all_in_range = finite_count > 0 and minimum >= 0.0 and maximum <= 1.0
    return {
        "path": str(path),
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "classic_tiff": True,
        "byte_order": "little" if endian == "<" else "big",
        "width": width,
        "height": height,
        "samples_per_pixel": samples,
        "bits_per_sample": bits,
        "sample_format": "IEEE float" if sample_format == 3 else sample_format,
        "compression": "LZW" if compression == 5 else compression,
        "predictor": predictor,
        "epsg": epsg,
        "pixel_scale": scale,
        "tiepoint": tiepoint,
        "gdal_nodata": nodata_value,
        "decoded_pixels": pixel_count,
        "finite_pixels": finite_count,
        "nan_pixels": nan_count,
        "positive_infinity_pixels": positive_inf_count,
        "negative_infinity_pixels": negative_inf_count,
        "finite_min": minimum if finite_count else None,
        "finite_max": maximum if finite_count else None,
        "finite_value_counts": (
            {str(value): count for value, count in sorted(value_counts.items())}
            if len(value_counts) <= 32
            else {
                **{str(value): count for value, count in value_counts.most_common(16)},
                "_total_unique_finite_values": len(value_counts),
            }
        ),
        "finite_values_in_0_1": all_in_range,
        "template_match": "NOT CHECKED; official sample_submission.tif is required",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tif", type=Path)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()
    try:
        report = audit(args.tif)
        text = json.dumps(report, indent=2)
        print(text)
        if args.json:
            args.json.parent.mkdir(parents=True, exist_ok=True)
            args.json.write_text(text + "\n", encoding="utf-8")
        return 0 if report["finite_values_in_0_1"] and not (report["positive_infinity_pixels"] or report["negative_infinity_pixels"]) else 3
    except Exception as exc:
        print(f"audit_reference_tif: ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
