# Types and Exact Units

## Primitive Types

| Mesor type | C89 representation | Notes |
| --- | --- | --- |
| `number`, `integer`, `wyrd` | `long` | Whole-number values. |
| `byte` | `unsigned char` | A small unsigned whole number. |
| `real` | `double` | Approximate floating-point value. |
| `flag` | integer flag | Use `Yes`/`No`, `Set`, and `Clear`. |
| `string`, `substring` | `char *` | Heap-managed mutable string. |
| `pointer` | `void *` | Untyped address. |

`Number` and `integer` are synonyms. Generated `long` range depends on the
host C implementation.

## Aliases, Globals, and Locals

```mesor
An address is a number.
The default address is 42.

To run:
  Privatize an address called current address.
  Put the default address into the current address.
```

Declare a typed global with `equal to` when its type should be explicit:

```mesor
The limit is a number equal to 100.
```

`Privatize` creates a routine-local variable. Parameters are mutable by
default; `Privatize the parameter` creates a local copy.

## Scaled Integers

Declare a root unit, then larger units in the same family:

```mesor
A micrometer is a unit.
A millimeter is 1000 micrometers.
A centimeter is 10 millimeters.

A cent is a unit.
A dollar is 100 cents.
```

Every value in a family is stored as an exact integer count of its root unit.
For example, `12.5 millimeters` is stored as `12500` micrometers. A literal
smaller than its declared root unit is rejected at compile time.

Addition and subtraction accept values from the same unit family, including
different named units. They do not accept a dimensionless number or real:

```mesor
Put 1 centimeter plus 2 millimeters into the width.
Add 0.1 to the balance. \ Error: no implicit real conversion.
```

Multiply or divide a scaled value by a dimensionless `number`; multiply or
divide it by a `real` to scale it with round-to-nearest-root-unit behavior.
`Scale` and `Multiply` mutate a scaled variable directly:

```mesor
Scale the width by 1.5.
Multiply the price by 2.
```

Use an explicit cast when crossing into approximate arithmetic:

```mesor
Put the width as a real into the display value.
```

The current bootstrap cast converts the stored root-unit count; it does not
format the value in a larger display unit.

## Records

Records are flat collections of fields:

```mesor
A box has a number called width and a number called height.
A roundy box is a box with a number called radius.
```

`Roundy box` contains `width`, `height`, and `radius`; the base fields come
first. This permits automatic reduction when a procedure expects a `box`.
Access fields with possessive English: `the shape's radius`.

Fixed-size fields use a numeric descriptor, for example `A packet is a record
with 4 bytes called data.` The current statement grammar does not yet provide
indexed array access.

## Pointers, Collections, and Strings

```mesor
A number pointer is a pointer to a number.
Put the value's whereabouts into the address.
Put 9 into the address's target.

Privatize some numbers called values.
Append the item to the values.
Write the values's first to the standard output.
```

`Nil` (or `null`) can be assigned to pointers. `Allocate memory for the
address.` zero-allocates its target type; `Deallocate`, `Unassign`, and
`Destroy` free pointers and set them to `Nil`.

`some TYPE` creates a growable collection of addresses to variables. Collections
expose `first`, `last`, and `length`; temporary expressions cannot be appended.
`Clear` frees their storage.

Strings are mutable. Use `Put`, `Append`, `Prepend`, and `Then`:

```mesor
Put "Neo" into the message.
Append "Pascal" to the message.
Put "Hello, " then the message into the greeting.
Write the message's length to the standard output.
```

`Destroy the message.` frees a string and assigns `Nil`.
