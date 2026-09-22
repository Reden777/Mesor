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
            args = ["python3", str(ROOT / "mesor.py"), str(src), "--emit-c", str(cfile)]
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
            "| Mesor|\n"
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

    def test_exit_returns_from_procedure(self):
        result, generated = self.compile('''
To stop early:
 Write "inside" to the standard output.
 Exit.
 Write "unreachable" to the standard output.
To run:
 Stop early.
 Write "caller" to the standard output.
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "inside\ncaller\n")
        self.assertIn("return;", generated)
        self.assertNotIn("exit(0)", generated)

    def test_exit_returns_from_main(self):
        result, generated = self.compile('''
To run:
 Write "before" to the standard output.
 Exit.
 Write "unreachable" to the standard output.
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "before\n")
        self.assertIn("return 0;", generated)

    def test_two_parameter_procedure_template(self):
        result, generated = self.compile('''
To combine a number called source with a number called destination:
 Add the source to the destination.
To run:
 Privatize a number called left.
 Privatize a number called right.
 Put 4 into the left.
 Put 5 into the right.
 Combine the left with the right.
 Write the right to the standard output.
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "9\n")
        self.assertIn("np_combine_with(&(np_left), &(np_right));", generated)

    def test_draw_a_box_with_a_color_template(self):
        result, _ = self.compile('''
A box has a number called width.
A color has a number called shade.
To draw a box with a color:
 Put the color's shade into the box's width.
To run:
 Privatize a box called shape.
 Privatize a color called ink.
 Put 8 into the ink's shade.
 Draw the shape with the ink.
 Write the shape's width to the standard output.
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "8\n")

    def test_wrapped_records_aliases_arrays_and_overloads(self):
        result, generated = self.compile('''
An address is a number.
A packet is a record with
4 bytes called data,
An address called origin.
To bump a number:
 Add 1 to the number.
To bump a byte:
 Add 1 to the byte.
To run:
 Privatize an address called value.
 Privatize a byte called small.
 Bump the value.
 Bump the small.
 Write the value to the standard output.
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "1\n")
        self.assertIn("np_data[4]", generated)
        self.assertIn("np_bump_number", generated)
        self.assertIn("np_bump_byte", generated)

    def test_inline_routine_alias_and_privatized_parameter(self):
        result, _ = self.compile('''
To announce a string;
To write a string: Write the string to the standard output.
To consume a number called amount:
 Privatize the amount.
 Add 2 to the amount.
 Write the amount to the standard output.
To run:
 Privatize a string called words.
 Privatize a number called original.
 Put "inline" into the words.
 Put 3 into the original.
 Announce the words.
 Consume the original.
 Write the original to the standard output.
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "inline\n5\n3\n")

    def test_pointer_nil_target_and_whereabouts(self):
        result, generated = self.compile('''
A number pointer is a pointer to a number.
To run:
 Privatize a number called value.
 Privatize a number pointer called address.
 Put 7 into the value.
 Put the value's whereabouts into the address.
 Put 9 into the address's target.
 If the address is not nil, Write the value to the standard output.
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "9\n")
        self.assertIn("void *", generated)

    def test_dynamic_strings_and_collections(self):
        result, _ = self.compile('''
A name is a string.
To run:
 Privatize a name called message.
 Privatize a number called item.
 Privatize some numbers called values.
 Put "Neo" into the message.
 Append "Pascal" to the message.
 Put 4 into the item.
 Append the item to the values.
 Write the message to the standard output.
 Write the values's first to the standard output.
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "Mesor\n4\n")

    def test_library_source_does_not_require_run(self):
        result, generated = self.compile('To greet: Write "hello" to the standard output.\n', run=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("int main", generated)

    def test_intel_is_preserved_as_explicit_backend_trap(self):
        result, generated = self.compile('''
To legacy operation:
 Intel $90.
To run:
 Write "portable" to the standard output.
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "portable\n")
        self.assertIn('np_intel_unsupported("90")', generated)

    def test_literal_arguments_use_c89_scratch_storage(self):
        result, _ = self.compile('''
To show a string:
 Write the string to the standard output.
To run:
 Show "temporary".
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "temporary\n")

    def test_external_call_and_compatible_callback_codegen(self):
        result, generated = self.compile('''
To compatibly handle a number called message:
 Add 1 to the message.
To run:
 Privatize a number called result.
 Call "missing-library" "missing-entry" returning the result.
 Write the result to the standard output.
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "0\n")
        self.assertIn("np_external_call", generated)
        self.assertIn("void np_compatibly_handle", generated)


if __name__ == "__main__":
    unittest.main()
