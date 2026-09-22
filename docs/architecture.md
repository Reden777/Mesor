# Architecture

## Compilation Pipeline

1. `neopascal.py` reads each UTF-8 source file, strips backslash comments, and joins wrapped declarations and statements.
2. It collects declarations for units, aliases, pointers, records, globals, and routines without requiring source order.
3. It validates type aliases, record bases, scaled-unit families, routine signatures, and global constants.
4. It type-checks and emits routine bodies as readable C89.
5. When requested, a host C compiler builds the emitted C with `runtime.h`.

The frontend is intentionally self-contained Python. It uses `Decimal` while
reading numeric unit literals so a source decimal becomes an exact root-unit
integer before C code is generated.

## Generated C and Runtime

Generated C includes [`../runtime.h`](../runtime.h). The runtime supplies
printing, mutable strings, collections, integer scaling, allocation helpers,
and platform-specific dynamic library lookup. It uses C89 library facilities.

The C89 backend is intentionally transparent: retain output with `--emit-c`
and inspect it when diagnosing a compiler or runtime issue.

## Current Boundaries

- The historical [`../ebnf`](../ebnf) is source material, not a promise that every listed form is implemented.
- There are procedures, not functions with source-level return values.
- Record fields can be declared as fixed-size arrays, but indexed access is not yet implemented.
- Unit values are stored and printed as root-unit counts; display formatting in a chosen unit is not yet available.
- The backend cannot execute embedded `INTEL` bytes portably and preserves them as an explicit runtime trap.
- Collections hold addresses of variables, so temporary values cannot be appended.

The original Plain English materials in `More Original Documents` are retained
for historical reference and are separate from the supported bootstrap surface.
