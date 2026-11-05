import importlib.util
import pathlib
import unittest

_spec = importlib.util.spec_from_file_location(
    "set_version", pathlib.Path(__file__).resolve().parent.parent / "packaging" / "set_version.py")
set_version = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(set_version)


class ParseTagTest(unittest.TestCase):
    def test_tag_formats(self):
        cases = {
            "Version1.2": "1.2",
            "Version1.1": "1.1",
            "v1.2.0": "1.2.0",
            "1.2.0": "1.2.0",
            "release-2.0.1": "2.0.1",
            "v1.3.0-beta1": "1.3.0~beta1",
        }
        for tag, expected in cases.items():
            with self.subTest(tag=tag):
                self.assertEqual(set_version.parse(tag), expected)

    def test_tag_without_number_fails(self):
        with self.assertRaises(SystemExit):
            set_version.parse("sin-numero")


if __name__ == "__main__":
    unittest.main()
