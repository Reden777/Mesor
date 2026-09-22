# Language Reference

This reference describes the implemented bootstrap language. Keywords and
identifiers are case-insensitive. Backslash begins a comment outside a string.
Statements and declarations end in a period; they may wrap across physical lines
until that period.

## Declarations

```text
A NAME is a unit.
A NAME is WHOLE-NUMBER PARENT-UNIT.
An ALIAS is a TYPE.
A POINTER-TYPE is a pointer to a TYPE.
A RECORD has FIELD and FIELD.
A DERIVED-RECORD is a BASE-RECORD with FIELD.
The NAME is a TYPE.
The NAME is a TYPE equal to CONSTANT.
The NAME is CONSTANT.
Some NAMES are some TYPE.
```

Field forms include `a TYPE called NAME`, `another TYPE`, `some TYPE`, and
`COUNT TYPE called NAME`. Bracketed or parenthesized field annotations are
accepted as documentation; `(reference)` does not yet change C89 code generation.

## Routines

```text
To run:
  STATEMENT.

To VERB a TYPE called NAME with a TYPE called NAME:
  STATEMENT.

To ALIAS a TYPE;
To IMPLEMENTATION a TYPE:
  STATEMENT.
```

The article-led phrases in a header are parameters. Remaining words, including
connectors such as `with`, are fixed call-template words. Identical parameter
signatures cannot be declared twice; different signatures form overloads.

## Values and Expressions

```text
WHOLE-NUMBER              42
REAL                      1.5
SCALED-LITERAL            12.5 millimeters
STRING                    "text"
FLAG                      Yes / No / True / False
NIL                       Nil / Null
HEX                       $FF
VARIABLE                  the width
FIELD                     the shape's radius
ADDRESS                   the value's whereabouts
POINTER TARGET            the address's target
CAST                      the width as a real
```

Use `plus`, `minus`, `times`, `divided by`, and `then` between expressions.
They evaluate left-to-right. `then` concatenates strings only.

## Conditions

```text
IF LEFT is RIGHT, ACTION; ACTION.
IF LEFT is not RIGHT, ACTION.
IF LEFT is greater than RIGHT, ACTION.
IF VALUE is set, ACTION.
IF VALUE is blank, ACTION.
IF VALUE is nil, ACTION.
```

See [control flow](control-flow.md) for all comparisons and loop restrictions.

## External Calls and Callbacks

```text
Call "library-name" "entry-name".
Call "library-name" "entry-name" with VALUE and VALUE returning VARIABLE.
To compatibly NAME a TYPE called VALUE:
  STATEMENT.
```

External calls accept up to eight arguments and return a C-word-sized value
when `returning` is used. They are a low-level FFI feature; callers must match
the target library's ABI and ownership requirements.

`Intel $HEX.` is recognized for historical source compatibility, but does not
execute machine code. The C89 backend emits a runtime error if it is reached.
