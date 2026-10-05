import json
from pathlib import Path
import tempfile
import unittest

from scripts.catalog.import_winisd_drivers import import_directory, parse_number


SAMPLE = """[Driver]
Brand=Example Audio
Model=Test 10
Manufacturer=
ProvidedBy=Unit Test
Comment=Decimal comma test
DateAdded=20260101
DateModified=20260101
Qts=0,36
Znom=4
Fs=28,5
Pe=250
SPL=84,2
Re=3,2
Le=0,0008
fLe=1000
KLe=0
BL=12,5
Xmax=0,012
Cms=0,00065
Qms=4,2
Qes=0,394
Rms=3,1
Mms=0,048
Sd=0,033
Vas=0,098
Dia=0
Vd=0,0004
no=0,0014
Dd=0,2
EBP=72
numVC=1
Hc=0
Hg=0
SPLmax=110
SPLmaxLF=100
USPL=88
alfaVC=0
Rt=0
Ct=0
gamma=80
Rme=30
Mpow=5
Mcost=0
c=343
roo=1,2
"""


class WinISDImportTests(unittest.TestCase):
    def test_decimal_comma_parsing(self):
        self.assertEqual(parse_number("0,36"), 0.36)
        self.assertEqual(parse_number("0.0008"), 0.0008)

    def test_preserves_identical_duplicate_records_with_unique_ids(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"
            source.mkdir()
            (source / "first.wdr").write_text(SAMPLE, encoding="utf-8")
            (source / "second.wdr").write_text(SAMPLE, encoding="utf-8")
            output = Path(temporary) / "catalog.json"

            catalog = import_directory(source, output)
            saved = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(catalog["record_count"], 2)
        self.assertEqual(catalog["duplicate_identity_group_count"], 1)
        self.assertEqual(catalog["duplicate_content_group_count"], 1)
        self.assertEqual(len({row["record_id"] for row in saved["drivers"]}), 2)
        self.assertTrue(all(row["duplicate_identity"] for row in saved["drivers"]))
        self.assertTrue(all(row["model_ready"] for row in saved["drivers"]))
        self.assertEqual(saved["drivers"][0]["parameters"]["fs_hz"], 28.5)
        self.assertEqual(saved["drivers"][0]["parameters"]["le_h"], 0.0008)


if __name__ == "__main__":
    unittest.main()
