# NeoPascal Documentation

NeoPascal is an experimental, case-insensitive programming language inspired by
Osmosian Plain English. Its bootstrap compiler reads NeoPascal source and emits
readable C89, which a host C compiler turns into an executable.

The language is deliberately small and explicit. Declarations can be spread
across source files, records are flat, and control flow is constrained so a
program remains easy to read from top to bottom.

## Start Here

- [Getting started](getting-started.md) installs the prerequisites and runs a first program.
- [Examples](examples.md) contains complete small programs.
- [Language reference](language-reference.md) lists the supported syntax.

## Guides

- [Types and exact units](type-system.md) covers primitives, records, pointers, collections, and scaled integers.
- [Control flow and routines](control-flow.md) explains procedures, `IF`, and `LOOP...REPEAT`.
- [Compiler usage](compiler-usage.md) documents command-line options and multi-file builds.
- [Architecture](architecture.md) describes the bootstrap compiler, generated C89, and runtime.

## Design Rules

1. **Case-insensitive.** `To run`, `TO RUN`, and `to run` mean the same thing.
2. **Order-independent declarations.** Types, globals, and routines may be declared in any order and across input files.
3. **Flat conditionals.** An `IF` contains a condition followed by semicolon-separated actions; an action cannot be another `IF`.
4. **One loop per routine.** Factor inner iteration into a separate procedure.
5. **No object model.** Records can extend records, but have no methods or inheritance dispatch. Derived records reduce to their base records.
6. **Exact units.** Values with declared units are integer counts of the smallest unit in their family. They never silently become floating point.

## Status

This is a bootstrap implementation, not a complete implementation of the
historical EBNF in [`../ebnf`](../ebnf). Unsupported syntax produces a
source-located compiler error rather than being guessed or ignored.
