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


class LocalResourceTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / "agreement").mkdir()
        self.resources = []
        for relative, documents in (
            ("agreement/HarmonyOS_Software_Service_Agreement.txt", DOCUMENTS[:3]),
            ("agreement/HarmonyOS_SDK_Agreement.txt", DOCUMENTS[3:]),
        ):
            data = ("\n" + licenses.SEPARATOR + "\n").join(documents).encode()
            (self.root / relative).write_bytes(data)
            self.resources.append((relative, len(data), hashlib.sha256(data).hexdigest()))
        for name, value in (("EXPECTED_RESOURCES", tuple(self.resources)),
                            ("EXPECTED_AGREEMENTS", EXPECTED)):
            patch = mock.patch.object(licenses, name, value)
            patch.start()
            self.addCleanup(patch.stop)

    def test_exact_abort_banner_and_complete_files_pass(self):
        licenses.verify(self.root, licenses.ABORTED_VIEW)

    def test_changed_count_or_banner_rejected(self):
        for banner in (licenses.ABORTED_VIEW.replace("2 license", "3 license"),
                       licenses.ABORTED_VIEW + "New terms apply.\n", ""):
            with self.subTest(banner=banner), self.assertRaises(ValueError):
                licenses.verify(self.root, banner)

    def test_missing_file_rejected(self):
        (self.root / self.resources[0][0]).unlink()
        with self.assertRaisesRegex(ValueError, "inventory differs"):
            licenses.verify(self.root, licenses.ABORTED_VIEW)

    def test_extra_file_with_arbitrary_name_rejected(self):
        (self.root / "agreement/extra.txt").write_text("New obligations")
        with self.assertRaisesRegex(ValueError, "inventory differs"):
            licenses.verify(self.root, licenses.ABORTED_VIEW)

    def test_extra_resource_outside_directory_rejected(self):
        (self.root / "new-license.txt").write_text("New obligations")
        with self.assertRaisesRegex(ValueError, "inventory differs"):
            licenses.verify(self.root, licenses.ABORTED_VIEW)

    def test_file_symlink_rejected(self):
        path = self.root / self.resources[0][0]
        path.rename(self.root / "target.txt")
        path.symlink_to(self.root / "target.txt")
        with self.assertRaisesRegex(ValueError, "not a regular file"):
            licenses.verify(self.root, licenses.ABORTED_VIEW)

    def test_directory_symlink_rejected(self):
        path = self.root / "agreement"
        path.rename(self.root / "target")
        path.symlink_to(self.root / "target", target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "directory is missing or a symlink"):
            licenses.verify(self.root, licenses.ABORTED_VIEW)

    def test_same_size_changed_content_rejected(self):
        path = self.root / self.resources[0][0]
        path.write_bytes(path.read_bytes().replace(b"Synthetic", b"DIFFERENT"))
        with self.assertRaisesRegex(ValueError, "SHA-256 differs"):
            licenses.verify(self.root, licenses.ABORTED_VIEW)

    def test_changed_size_rejected(self):
        path = self.root / self.resources[0][0]
        path.write_bytes(path.read_bytes() + b"new clause")
        with self.assertRaisesRegex(ValueError, "size differs"):
            licenses.verify(self.root, licenses.ABORTED_VIEW)

    def test_raw_file_hash_is_not_enough_without_text_match(self):
        with mock.patch.object(licenses, "EXPECTED_AGREEMENTS", EXPECTED[:3]):
            with self.assertRaisesRegex(ValueError, "expected 3, found 4"):
                licenses.verify(self.root, licenses.ABORTED_VIEW)

    def test_unknown_preamble_is_not_discarded(self):
        with self.assertRaisesRegex(ValueError, "preamble"):
            licenses._frame_resource_text(["New terms\n" + DOCUMENTS[0]])

    def test_resource_wrapper_conversion_matches_reference_format(self):
        pieces = ["1/3:\n" + licenses.SEPARATOR + "\n" + DOCUMENTS[0] + "\n2/3:\n",
                  licenses.SEPARATOR + "\n" + DOCUMENTS[1] + "\n3/3:\n",
                  licenses.SEPARATOR + "\n" + DOCUMENTS[2], DOCUMENTS[3]]
        licenses._compare(licenses._frame_resource_text(pieces), EXPECTED)


if __name__ == "__main__":
    unittest.main()
