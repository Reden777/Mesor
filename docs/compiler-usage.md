# Compiler Usage

```text
neopascal SOURCE [SOURCE ...] [-o EXECUTABLE] [--emit-c FILE] [--cc COMMAND] [--run]
```

`neopascal` is the shell wrapper around `neopascal.py`. Each input is UTF-8
source. All inputs form one program: the compiler collects declarations before
it validates types and emits routine bodies.

## Options

| Option | Meaning |
| --- | --- |
| `SOURCE [SOURCE ...]` | One or more NeoPascal files. |
| `-o FILE`, `--output FILE` | Compile generated C into `FILE`. |
| `--emit-c FILE` | Write generated C89 to `FILE`. |
| `--cc COMMAND` | Use this C compiler instead of automatic selection. |
| `--run` | Build and run the program. |

Without `--emit-c`, generated C is written beside the first source file. When
`-o` is used without `--emit-c`, that temporary C file is removed after a
successful C compilation.

## Examples

```sh
./neopascal examples/scaled.neo --run
./neopascal program.neo --cc gcc --emit-c program.c -o program
./neopascal units.neo library.neo app.neo -o app
```

On Linux, non-TCC builds link `libdl` automatically for external library calls.
On Windows and macOS, the runtime uses the platform's dynamic-library API.

## Diagnostics

Compiler errors have this form:

```text
neopascal: error: path/to/file.neo:12: explanation
```

The C compiler may also diagnose generated code. Keeping C with `--emit-c` is
the fastest way to inspect the backend result.
