# Examples

The matching source files live in [`../examples`](../examples).

## Hello World

```neopascal
To run:
  Write "Hello, world!" to the standard output.
```

Run it with `./neopascal examples/hello.neo --run`.

## Exact Dimensions and Money

```neopascal
A micrometer is a unit.
A millimeter is 1000 micrometers.
A cent is a unit.
A dollar is 100 cents.

To run:
  Privatize a millimeter called width.
  Privatize a dollar called price.
  Put 12.5 millimeters into the width.
  Put 2.25 dollars into the price.
  Add 0.75 dollars to the price.
  Scale the width by 1.5.
  Write the width to the standard output.
  Write the price to the standard output.
```

This writes `18750` and `300`: root-unit counts, not formatted values.
`examples/scaled.neo` contains this program.

## An ASCII Box

```neopascal
To write border:
  Write "+----------+" to the standard output.

To run:
  Write border.
  Write "|          |" to the standard output.
  Write "| NeoPascal|" to the standard output.
  Write "|          |" to the standard output.
  Write border.
```

`examples/ascii_box.neo` is useful as a small routine-call example.

## Order-Independent Files

`app.neo` may refer to a unit declared in another input file, even if `app.neo`
appears first:

```neopascal
The starting amount is 2 millimeters.
To run:
  Write the starting amount to the standard output.
```

```neopascal
A millimeter is 1000 micrometers.
A micrometer is a unit.
```

Compile both files together:

```sh
./neopascal app.neo units.neo --run
```
