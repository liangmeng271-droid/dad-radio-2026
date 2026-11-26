import json
from hashlib import sha256
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZIP_STORED, ZipFile, ZipInfo


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills" / "monthly-personal-reimbursement" / "scripts" / "pack_verified.py"
)


def fictional_pdf(label):
    stream = f"BT /F1 12 Tf 20 40 Td ({label}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 240 80] "
         b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, content in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(b"%d 0 obj\n%s\nendobj\n" % (number, content))
    xref = len(pdf)
    pdf.extend(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for offset in offsets:
        pdf.extend(b"%010d 00000 n \n" % offset)
    pdf.extend(
        b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
        % (len(objects) + 1, xref)
    )
    return bytes(pdf)


class PackVerifiedTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        self.sources = root / "sources"
        self.output = root / "output"
        self.manifest_file = root / "manifest.json"
        self.sources.mkdir()
        self.output.mkdir()
        self.archive_names = ["模拟甲组.zip", "模拟乙组.zip"]

        self.documents = {
            "goods.pdf": fictional_pdf("Sample goods 14.25"),
            "shipping.pdf": fictional_pdf("Sample shipping 2.75"),
            "toll.pdf": fictional_pdf("Sample toll 18.00"),
            "trans.pdf": fictional_pdf("Sample trip linked to TEST-TOLL"),
        }
        for name in ("goods.pdf", "shipping.pdf", "toll.pdf"):
            (self.sources / name).write_bytes(self.documents[name])
        with ZipFile(self.sources / "trip-source.zip", "w") as trips:
            trips.writestr("trans.pdf", self.documents["trans.pdf"])
            trips.writestr("apply.pdf", fictional_pdf("Sample duplicate index"))

        self.manifest = {
            "groups": [
                {
                    "name": "模拟甲组",
                    "total": "17.00",
                    "invoices": [
                        {
                            "id": "TEST-GOODS", "amount": "14.25", "path": "goods.pdf",
                            "sha256": sha256(self.documents["goods.pdf"]).hexdigest(),
                        },
                        {"id": "TEST-SHIP", "amount": "2.75", "path": "shipping.pdf"},
                    ],
                    "trips": [],
                },
                {
                    "name": "模拟乙组",
                    "total": "18.00",
                    "invoices": [
                        {"id": "TEST-TOLL", "amount": "18.00", "path": "toll.pdf"},
                    ],
                    "trips": [
                        {
                            "invoice_ids": ["TEST-TOLL"],
                            "path": "trip-source.zip",
                            "member": "trans.pdf",
                            "name": "route.pdf",
                        },
                    ],
                },
            ]
        }

    def run_pack(self):
        self.manifest_file.write_text(
            json.dumps(self.manifest, ensure_ascii=False), encoding="utf-8"
        )
        return subprocess.run(
            [
                sys.executable, "-B", "-X", "utf8", str(SCRIPT),
                str(self.manifest_file), "--source-root", str(self.sources),
                "--output-dir", str(self.output),
            ],
            capture_output=True,
            encoding="utf-8",
            timeout=20,
        )

    def assert_rejected(self, message):
        result = self.run_pack()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(message, result.stderr)

    def test_groups_reconcile_and_preserve_the_selected_originals(self):
        result = self.run_pack()
        self.assertEqual(result.returncode, 0, result.stderr)
        summaries = json.loads(result.stdout)
        self.assertEqual(
            [(item["name"], item["total"], item["pdf_count"]) for item in summaries],
            [(self.archive_names[0], "17.00", 2), (self.archive_names[1], "18.00", 2)],
        )
        expected = (
            {"发票/goods.pdf": "goods.pdf", "发票/shipping.pdf": "shipping.pdf"},
            {"发票/toll.pdf": "toll.pdf", "高速费行程单/route.pdf": "trans.pdf"},
        )
        for summary, documents in zip(summaries, expected):
            path = self.output / summary["name"]
            self.assertEqual(sha256(path.read_bytes()).hexdigest(), summary["sha256"])
            with ZipFile(path) as archive:
                self.assertIsNone(archive.testzip())
                self.assertCountEqual(archive.namelist(), documents)
                for member, original in documents.items():
                    self.assertEqual(archive.read(member), self.documents[original])

    def test_rejects_missing_or_incorrect_group_total(self):
        group = self.manifest["groups"][1]
        del group["total"]
        self.assert_rejected("'total'")
        self.assertEqual(list(self.output.iterdir()), [])
        group["total"] = "18.01"
        self.assert_rejected("Invoice amounts do not reconcile")
        self.assertEqual(list(self.output.iterdir()), [])

    def test_rejects_trip_linked_to_another_group(self):
        self.manifest["groups"][1]["trips"][0]["invoice_ids"] = ["TEST-GOODS"]
        self.assert_rejected("Trip PDF references an unlisted invoice")
        self.assertEqual(list(self.output.iterdir()), [])

    def test_rejects_duplicate_invoice_across_groups(self):
        self.manifest["groups"][1]["invoices"][0]["id"] = "TEST-GOODS"
        self.assert_rejected("Repeated invoice ID")
        self.assertEqual(list(self.output.iterdir()), [])

    def test_identical_rerun_keeps_existing_archives(self):
        first = self.run_pack()
        self.assertEqual(first.returncode, 0, first.stderr)
        existing = {path.name: path.read_bytes() for path in self.output.iterdir()}

        second = self.run_pack()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(json.loads(first.stdout), json.loads(second.stdout))
        self.assertEqual(
            {path.name: path.read_bytes() for path in self.output.iterdir()}, existing
        )

    def test_same_contents_with_different_zip_metadata_are_preserved(self):
        path = self.output / self.archive_names[0]
        with ZipFile(path, "x") as archive:
            archive.comment = b"Archived by another ZIP writer"
            for name in ("shipping.pdf", "goods.pdf"):
                info = ZipInfo(f"发票/{name}", date_time=(2024, 1, 2, 3, 4, 6))
                archive.writestr(info, self.documents[name], compress_type=ZIP_STORED)
        original = path.read_bytes()

        result = self.run_pack()
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout)[0]
        self.assertEqual(summary["name"], path.name)
        self.assertEqual(summary["sha256"], sha256(original).hexdigest())
        self.assertEqual(path.read_bytes(), original)

    def test_valid_archive_with_different_content_is_preserved(self):
        path = self.output / self.archive_names[0]
        with ZipFile(path, "x") as archive:
            archive.writestr("发票/goods.pdf", fictional_pdf("Different sample goods"))
            archive.writestr("发票/shipping.pdf", self.documents["shipping.pdf"])
        original = path.read_bytes()

        self.assert_rejected("Existing ZIP differs")
        self.assertEqual(path.read_bytes(), original)
        self.assertFalse((self.output / self.archive_names[1]).exists())

    def test_different_existing_archive_is_preserved(self):
        conflict = self.output / self.archive_names[1]
        original = b"Existing artifact"
        conflict.write_bytes(original)
        self.assert_rejected("Existing ZIP differs")
        self.assertEqual(conflict.read_bytes(), original)
        self.assertFalse((self.output / self.archive_names[0]).exists())


if __name__ == "__main__":
    unittest.main()
