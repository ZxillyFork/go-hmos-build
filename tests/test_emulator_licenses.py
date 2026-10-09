# Copyright 2026 The Go Authors. All rights reserved.
# Use of this source code is governed by a BSD-style
# license that can be found in the LICENSE file.

"""Synthetic regression cases for the fail-closed agreement comparison gate."""

import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock


PATH = Path(__file__).resolve().parents[1] / "scripts/emulator/licenses.py"
SPEC = importlib.util.spec_from_file_location("emulator_licenses", PATH)
licenses = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(licenses)


def agreement(title, body):
    return title + "\n\n" + body


DOCUMENTS = (
    agreement(licenses.SOFTWARE_TITLE, "Synthetic general-device terms."),
    agreement(licenses.SOFTWARE_TITLE, "Synthetic general-device terms."),
    agreement(licenses.SOFTWARE_TITLE, "Synthetic wearable terms."),
    agreement(licenses.SDK_TITLE, "Synthetic SDK terms."),
)
EXPECTED = tuple(
    (document.splitlines()[0], hashlib.sha256(document.encode()).hexdigest())
    for document in DOCUMENTS
)


def rendered(documents=DOCUMENTS):
    output = "1/3:\n" + licenses.SEPARATOR + "\n"
    for index, document in enumerate(documents):
        output += document + "\n"
        if index < 2:
            output += f"\n{index + 2}/3:\n"
        output += licenses.SEPARATOR + "\n"
    return output


class LicenseComparisonTest(unittest.TestCase):
    def test_complete_exact_collection(self):
        licenses._compare(rendered(), EXPECTED)

    def test_normalizes_crlf_and_trailing_whitespace(self):
        text = "\r\n".join(line + " \t" for line in rendered().split("\n"))
        licenses._compare(text, EXPECTED)

    def test_duplicate_is_required(self):
        with self.assertRaisesRegex(ValueError, "expected 4, found 3"):
            licenses._compare(rendered(DOCUMENTS[1:]), EXPECTED)

    def test_extra_known_agreement_rejected(self):
        with self.assertRaisesRegex(ValueError, "expected 4, found 5"):
            licenses._compare(rendered(DOCUMENTS + (DOCUMENTS[0],)), EXPECTED)

    def test_modified_body_rejected(self):
        with self.assertRaisesRegex(ValueError, "differs"):
            licenses._compare(rendered().replace("Synthetic SDK terms.", "New SDK terms."), EXPECTED)

    def test_order_change_rejected(self):
        with self.assertRaisesRegex(ValueError, "differs"):
            licenses._compare(rendered(tuple(reversed(DOCUMENTS))), EXPECTED)

    def test_unknown_text_is_never_discarded(self):
        for extra in ("New Agreement\nNew obligations", "New liability clause", "Do you accept?", "All licenses have been automatically accepted."):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                licenses._compare(rendered() + extra, EXPECTED)

    def test_unknown_title_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unrecognized"):
            licenses._compare(rendered().replace(licenses.SDK_TITLE, "New SDK Agreement"), EXPECTED)

    def test_decline_truncation_rejected(self):
        with self.assertRaises(ValueError):
            licenses._compare(rendered(DOCUMENTS[:1]), EXPECTED)

    def test_missing_final_separator_rejected(self):
        with self.assertRaisesRegex(ValueError, "incomplete outer frame"):
            licenses._compare(rendered().rsplit(licenses.SEPARATOR, 1)[0], EXPECTED)

    def test_control_characters_rejected(self):
        with self.assertRaisesRegex(ValueError, "control characters"):
            licenses._compare(rendered() + "\x1b[0m", EXPECTED)

    def test_empty_or_unframed_output_rejected(self):
        for text in ("", DOCUMENTS[0], "already accepted"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                licenses._compare(text, EXPECTED)

    def test_oversized_output_rejected(self):
        with self.assertRaisesRegex(ValueError, "inspection limit"):
            licenses._parse("x" * (licenses._MAX_OUTPUT_BYTES + 1))

    def test_production_baseline_does_not_accept_synthetic_terms(self):
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(ValueError):
            licenses.verify(Path(directory), rendered())

    def test_missing_directory_rejected(self):
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(ValueError, "missing"):
            licenses.verify(Path(directory) / "missing", rendered())

    def test_local_known_files_cannot_substitute_for_incomplete_view(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "license.txt").write_text(rendered())
            with mock.patch.object(licenses, "EXPECTED_AGREEMENTS", EXPECTED):
                with self.assertRaises(ValueError):
                    licenses.verify(root, rendered(DOCUMENTS[:1]))

    def test_verify_contract_has_no_side_effects(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = rendered()
            path = root / "license.txt"
            path.write_text(original)
            with mock.patch.object(licenses, "EXPECTED_AGREEMENTS", EXPECTED):
                self.assertIsNone(licenses.verify(root, original))
            self.assertEqual(path.read_text(), original)
            self.assertEqual(list(root.iterdir()), [path])


if __name__ == "__main__":
    unittest.main()
