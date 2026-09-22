# Getting Started

Mesor has no Python package dependencies. You need Python 3 and a C89
compiler. The compiler tries `tcc`, then `cc`, `gcc`, and `clang`; TCC is useful
for a quick edit-compile-run cycle.

## Compile a Program

From the repository root, run the included hello-world source:

```sh
./mesor examples/hello.neo --run
```

Or invoke the Python entry point directly:

```sh
python3 mesor.py examples/hello.neo --run
```

The program prints:

```text
Hello, world!
```

## Your First Source File

Create `hello.neo`:

```mesor
To run:
  Write "Hello, world!" to the standard output.
```

Compile and run it:

```sh
./mesor hello.neo --run
```

`To run:` is the optional program entry point. A source file without it is a
library of types, globals, and procedures and can still be compiled to C.

## Keep the Generated C

Mesor normally writes C next to the first input source. Use `--emit-c` to
choose and retain the generated file, and `-o` to build an executable:

```sh
./mesor hello.neo --emit-c build/hello.c -o build/hello
```

The generated file includes `runtime.h`, so compile it through Mesor or add
the repository root to your C compiler's include path yourself.

## Run the Test Suite

```sh
python3 tests/run_tests.py
```

See [compiler usage](compiler-usage.md) for C compiler selection and multi-file
programs, then [examples](examples.md) for more language patterns.
