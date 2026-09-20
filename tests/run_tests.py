#!/usr/bin/env python3
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CompilerTests(unittest.TestCase):
    def compile(self, source, run=True):
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "test.neo"
            exe = Path(directory) / "test"
            cfile = Path(directory) / "test.c"
            src.write_text(source)
            args = ["python3", str(ROOT / "neopascal.py"), str(src), "--emit-c", str(cfile)]
            if run: args += ["-o", str(exe), "--run"]
            return subprocess.run(args, text=True, capture_output=True), cfile.read_text() if cfile.exists() else ""

    def test_hello(self):
        result, generated = self.compile('To run:\n Write "Hello, world!" to the standard output.\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "Hello, world!\n")
        self.assertIn("int main(void)", generated)

    def test_ascii_box(self):
        source = (ROOT / "examples" / "ascii_box.neo").read_text()
        result, _ = self.compile(source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, (
            "+----------+\n"
            "|          |\n"
            "| NeoPascal|\n"
            "|          |\n"
            "+----------+\n"
        ))

    def test_scaled_units_are_exact(self):
        result, _ = self.compile('''
A micrometer is a unit.
A millimeter is 1000 micrometers.
A centimeter is 10 millimeters.
To run:
 Privatize a millimeter called width.
 Put 12.5 millimeters into the width.
 Add 2 millimeters to the width.
 Scale the width by 1.5.
 Write the width to the standard output.
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "21750\n")

    def test_float_contamination_is_rejected(self):
        result, _ = self.compile('''
A cent is a unit.
A dollar is 100 cents.
To run:
 Privatize a dollar called balance.
 Add 0.1 to the balance.
''', run=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("dimensionless real", result.stderr)

    def test_flat_if_and_loop(self):
        result, _ = self.compile('''
To run:
 Privatize a number called count.
 Loop.
 Add 1 to the count.
 If the count is at least 3, Write the count to the standard output; Break.
 Repeat.
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "3\n")

    def test_record_extension_is_flat(self):
        result, generated = self.compile('''
A box has a number called width and a number called height.
A roundy box is a box with a number called radius.
To run:
 Privatize a roundy box called shape.
 Put 4 into the shape's width.
 Put 2 into the shape's radius.
 Write the shape's width to the standard output.
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "4\n")
        self.assertIn("np_width", generated)
        self.assertIn("np_radius", generated)

    def test_declarations_are_order_independent(self):
        result, _ = self.compile('''
A millimeter is 1000 micrometers.
A micrometer is a unit.
The starting amount is 2 millimeters.
To run:
 Write the starting amount to the standard output.
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "2000\n")

    def test_global_can_precede_its_unit_and_expressions_scale(self):
        result, _ = self.compile('''
The starting amount is 2 millimeters.
A millimeter is 1000 micrometers.
To run:
 Privatize a millimeter called result.
 Put the starting amount plus 0.5 millimeters into the result.
 Put the result times 2 into the result.
 Write the result to the standard output.
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "5000\n")

    def test_procedure_parameter(self):
        result, _ = self.compile('''
To increment a number called value:
 Add 1 to the value.
To run:
 Privatize a number called count.
 Increment the count.
 Write the count to the standard output.
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "1\n")

    def test_derived_record_reduces_to_base_parameter(self):
        result, _ = self.compile('''
A box has a number called width.
A roundy box is a box with a radius.
To widen a box called item:
 Put 7 into the item's width.
To run:
 Privatize a roundy box called shape.
 Widen the shape.
 Write the shape's width to the standard output.
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "7\n")


if __name__ == "__main__":
    unittest.main()
