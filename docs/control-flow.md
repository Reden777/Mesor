# Control Flow and Routines

## Procedures

A routine header is also the template used to call the routine. Parameters are
introduced with `a`, `an`, `some`, or `another` and are mutable:

```mesor
To combine a number called source with a number called destination:
  Add the source to the destination.

To run:
  Privatize a number called left.
  Privatize a number called right.
  Put 4 into the left.
  Put 5 into the right.
  Combine the left with the right.
```

This sets `right` to `9`. Routines may be overloaded when parameter types
differ. Use a semicolon header as an alias for the next implementation:

```mesor
To announce a string;
To write a string:
  Write the string to the standard output.
```

`Exit.` returns from a procedure. In `To run:`, it returns success from the
program.

## Conditions

An `IF` is one flat statement: condition, comma, then one or more
semicolon-separated actions. Each action ends at the final period.

```mesor
If the count is at least 3, Write the count to the standard output; Break.
```

Nested `IF` actions are rejected. Supported comparisons are `is`, `equals`,
`is not`, `is greater than`, `is less than`, `is at least`, and `is at most`.
State conditions are `is set`, `is clear`, `is blank`, `is empty`, and `is nil`,
with optional `not`.

## Loops

Each routine may contain one `LOOP...REPEAT` pair:

```mesor
To run:
  Privatize a number called count.
  Loop.
  Add 1 to the count.
  If the count is at least 3, Write the count to the standard output; Break.
  Repeat.
```

`Break.` is valid only between `Loop.` and `Repeat.`. Factor inner iteration
into another routine.

## Statements

Every statement ends in a period. The implemented action statements are:

| Statement | Purpose |
| --- | --- |
| `Put VALUE into VARIABLE.` | Assignment. |
| `Add VALUE to VARIABLE.` | Addition. |
| `Subtract VALUE from VARIABLE.` | Subtraction. |
| `Scale VARIABLE by VALUE.` | Scale a unit value. |
| `Write VALUE to the standard output.` | Print a value and newline. |
| `Set VARIABLE.` / `Clear VARIABLE.` | Change a flag; `Clear` also empties a collection. |
| `Append VALUE to VARIABLE.` / `Prepend VALUE to VARIABLE.` | Change a string or collection. |
| `Allocate memory for VARIABLE.` | Allocate a pointer target. |
| `Destroy VARIABLE.` | Free a pointer, string, or collection. |
| `Call "library" "entry" ...` | Invoke a dynamic-library entry point. |
| `Intel $HEX.` | Emit an explicit portable-backend runtime trap. |

Expressions are evaluated left-to-right. `plus`, `minus`, `times`, `divided
by`, and string `then` are supported; parentheses are not part of the current
expression grammar.
