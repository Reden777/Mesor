# NeoPascal

NeoPascal is a case-insensitive, human-language compiler that emits readable
C89.  This repository contains the bootstrap compiler and a deliberately small,
working language core.

```text
To run:
  Write "Hello, world!" to the standard output.
```

Compile and run it (TCC is preferred automatically):

```sh
./neopascal examples/hello.neo -o hello
./hello
./neopascal examples/hello.neo --run
./neopascal examples/ascii_box.neo --run
```

Use `--emit-c output.c` to retain the generated C, and `--cc gcc` to select a
compiler. Declarations may appear before or after one another and source files
may be passed together. Type and routine resolution happens before bodies are
checked.

## Implemented language core

- case-insensitive names and order-independent declarations;
- statement-stream parsing, including wrapped declarations, wrapped statements,
  inline routine bodies, and semicolon-linked routine aliases;
- optional `To run:` and English-template procedures with overloads and any
  number of mutable typed parameters;
- primitive numbers, reals, flags, strings, globals, and local `Privatize`;
- aliases with automatic reduction, typed pointers, `NIL`, `TARGET`,
  `WHEREABOUTS`, counted fields, and dynamic `some ...` collections;
- mutable strings with assignment, append, prepend, concatenation, and length;
- allocation/deallocation primitives, external DLL/shared-library calls, and
  C-compatible callback entry points;
- exact scaled integers and automatic conversion inside one unit family;
- explicit `AS A REAL`, while scaled-unit addition with a raw real is rejected;
- scaled multiplication with round-to-nearest base unit;
- flat records and record extension (`A roundy box is a box with ...`);
- `Put`, `Add`, `Subtract`, `Scale`/`Multiply`, `Write`, procedure calls;
- flat `IF condition, action; action.` statements;
- one `LOOP...REPEAT` per routine, with `BREAK`.
- `EXIT` as an early return to the caller (`return 0` only in `To run`).

Historical `INTEL $...` statements are retained in generated code as an
explicit runtime trap. Arbitrary 32-bit x86 instruction bytes cannot execute
portably through a C89 backend (and cannot execute on ARM hosts). They are never
silently ignored. The historical noodle's embedded WAV resources are also not
part of the portable language runtime; a `wave` hex initializer becomes empty.

Scaled values are stored as integer counts of their family's smallest declared
root unit. Thus `12.5 millimeters`, when a millimeter is 1000 micrometers, is
emitted as integer `12500`. A literal finer than the base unit is a compile-time
error. Generated code uses C89 `long`; its range is consequently platform
dependent.

The historical EBNF is broader than this bootstrap core. Unimplemented forms
produce a source-located compiler error instead of being guessed or silently
miscompiled.

Run the tests with:

```sh
python3 tests/run_tests.py
```
