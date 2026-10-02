import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_edge_consensus", ROOT / "scripts/build_edge_consensus.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class EdgeBandResolutionTests(unittest.TestCase):
    def test_resolves_unique_named_layers_without_guessing_indexes(self):
        descriptions = [
            "Total magnetic intensity (TMI)",
            "Reduced-to-pole magnetic anomaly (RTP)",
            "Isostatic gravity anomaly",
            "Surface conductivity",
            "Depth to conductive base",
        ]
        self.assertEqual(
            MODULE.resolve_bands(descriptions),
            {
                "tmi": 0,
                "reduced_to_pole": 1,
                "isostatic_gravity": 2,
                "surface_conductivity": 3,
                "conductive_base_depth": 4,
            },
        )

    def test_organizer_reference_descriptions_select_raw_fields_not_derivatives(self):
        descriptions = [
            "Magnetic anomaly - deviation from expected Earth's magnetic field",
            "Reduced to pole magnetic data - magnetic anomaly corrected for latitude effects",
            "Total magnetic intensity horizontal gradient - rate of change in horizontal direction",
            "Isostatic gravity anomaly slope - gradient of gravity after isostatic correction",
            "Isostatic gravity anomaly - gravity after compensating for topographic mass",
            "Total magnetic intensity vertical gradient - rate of change in vertical direction",
            "Total magnetic intensity - total strength of magnetic field",
            "Conductivity surface - electrical conductivity of subsurface",
            "Depth to conductive base surface - verified official feature name",
        ]
        resolved = MODULE.resolve_bands(descriptions)
        self.assertEqual(resolved["tmi"], 6)
        self.assertEqual(resolved["reduced_to_pole"], 1)
        self.assertEqual(resolved["isostatic_gravity"], 4)
        self.assertEqual(resolved["surface_conductivity"], 7)
        self.assertEqual(resolved["conductive_base_depth"], 8)
        # Do not silently reinterpret the reference notebook's different name.
        with self.assertRaises(ValueError):
            MODULE.resolve_bands(descriptions[:-1] + ["Depth to basement surface"])

    def test_ambiguous_or_duplicate_layers_fail_closed(self):
        descriptions = [
            "TMI", "TMI alternate", "RTP", "Isostatic gravity anomaly",
            "Surface conductivity", "Depth to conductive base",
        ]
        with self.assertRaises(ValueError):
            MODULE.resolve_bands(descriptions)
        with self.assertRaises(ValueError):
            MODULE.resolve_bands(
                ["layer a", "layer b", "layer c", "layer d", "layer e"],
                {
                    "tmi": "layer a",
                    "reduced_to_pole": "layer a",
                    "isostatic_gravity": "layer c",
                    "surface_conductivity": "layer d",
                    "conductive_base_depth": "layer e",
                },
            )


if __name__ == "__main__":
    unittest.main()
