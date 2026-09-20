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
- `To run:` and procedures with mutable typed parameters;
- primitive numbers, reals, flags, strings, globals, and local `Privatize`;
- exact scaled integers and automatic conversion inside one unit family;
- explicit `AS A REAL`, while scaled-unit addition with a raw real is rejected;
- scaled multiplication with round-to-nearest base unit;
- flat records and record extension (`A roundy box is a box with ...`);
- `Put`, `Add`, `Subtract`, `Scale`/`Multiply`, `Write`, procedure calls;
- flat `IF condition, action; action.` statements;
- one `LOOP...REPEAT` per routine, with `BREAK`.

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
