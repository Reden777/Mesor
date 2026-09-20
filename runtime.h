#ifndef NEOPASCAL_RUNTIME_H
#define NEOPASCAL_RUNTIME_H

/* This runtime intentionally uses only C89 library facilities. */
#include <stdio.h>
#include <stdlib.h>

typedef long np_int;

static void np_write_string(const char *value)
{
    puts(value);
}

static void np_write_int(np_int value)
{
    printf("%ld\n", value);
}

static void np_write_real(double value)
{
    printf("%.15g\n", value);
}

/* Round halves away from zero without requiring C99 round() or libm. */
static np_int np_scale(np_int value, double scalar)
{
    double result = ((double)value) * scalar;
    if (result < 0.0)
        return (np_int)(result - 0.5);
    return (np_int)(result + 0.5);
}

#endif
