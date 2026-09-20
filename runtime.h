#ifndef NEOPASCAL_RUNTIME_H
#define NEOPASCAL_RUNTIME_H

/* This runtime intentionally uses only C89 library facilities. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#if defined(_WIN32)
#include <windows.h>
#elif defined(__unix__) || defined(__APPLE__)
#include <dlfcn.h>
#endif

typedef long np_int;
typedef long np_word;

static np_int *np_scratch_int(np_int value)
{
    static np_int values[16];
    static int next;
    next = (next + 1) & 15;
    values[next] = value;
    return &values[next];
}

static unsigned char *np_scratch_byte(unsigned char value)
{
    static unsigned char values[16];
    static int next;
    next = (next + 1) & 15;
    values[next] = value;
    return &values[next];
}

static char **np_scratch_string(char *value)
{
    static char *values[16];
    static int next;
    next = (next + 1) & 15;
    values[next] = value;
    return &values[next];
}

static void **np_scratch_pointer(void *value)
{
    static void *values[16];
    static int next;
    next = (next + 1) & 15;
    values[next] = value;
    return &values[next];
}

typedef struct np_things {
    void **items;
    np_int length;
    np_int capacity;
} np_things;

static void np_things_append(np_things *things, void *item)
{
    void **items;
    np_int capacity;
    if (things->length == things->capacity) {
        capacity = things->capacity == 0 ? 8 : things->capacity * 2;
        items = (void **)realloc(things->items, (size_t)capacity * sizeof(void *));
        if (items == NULL) return;
        things->items = items;
        things->capacity = capacity;
    }
    things->items[things->length++] = item;
}

static void np_things_prepend(np_things *things, void *item)
{
    np_things_append(things, item);
    if (things->length > 1) {
        memmove(things->items + 1, things->items, (size_t)(things->length - 1) * sizeof(void *));
        things->items[0] = item;
    }
}

static np_int np_string_length(const char *value)
{
    return value == NULL ? 0 : (np_int)strlen(value);
}

static char *np_string_copy(const char *value)
{
    size_t length;
    char *copy;
    if (value == NULL) value = "";
    length = strlen(value);
    copy = (char *)malloc(length + 1);
    if (copy == NULL) return NULL;
    memcpy(copy, value, length + 1);
    return copy;
}

static void np_string_set(char **target, const char *value)
{
    char *copy = np_string_copy(value);
    if (*target != NULL) free(*target);
    *target = copy;
}

static void np_string_append(char **target, const char *suffix)
{
    size_t left, right;
    char *combined;
    const char *current = *target == NULL ? "" : *target;
    if (suffix == NULL) suffix = "";
    left = strlen(current);
    right = strlen(suffix);
    combined = (char *)malloc(left + right + 1);
    if (combined == NULL) return;
    memcpy(combined, current, left);
    memcpy(combined + left, suffix, right + 1);
    if (*target != NULL) free(*target);
    *target = combined;
}

static void np_string_prepend(char **target, const char *prefix)
{
    char *result = np_string_copy(prefix);
    np_string_append(&result, *target);
    if (*target != NULL) free(*target);
    *target = result;
}

static char *np_string_concat(const char *left, const char *right)
{
    char *result = np_string_copy(left);
    np_string_append(&result, right);
    return result;
}

static np_word np_external_call(const char *library, const char *entry, int count, ...)
{
    typedef np_word (*np_external0)(void);
    typedef np_word (*np_external1)(np_word);
    typedef np_word (*np_external2)(np_word, np_word);
    typedef np_word (*np_external3)(np_word, np_word, np_word);
    typedef np_word (*np_external4)(np_word, np_word, np_word, np_word);
    typedef np_word (*np_external5)(np_word, np_word, np_word, np_word, np_word);
    typedef np_word (*np_external6)(np_word, np_word, np_word, np_word, np_word, np_word);
    typedef np_word (*np_external7)(np_word, np_word, np_word, np_word, np_word, np_word, np_word);
    typedef np_word (*np_external8)(np_word, np_word, np_word, np_word, np_word, np_word, np_word, np_word);
    union np_external_symbol {
        void *object;
        np_external0 f0; np_external1 f1; np_external2 f2;
        np_external3 f3; np_external4 f4; np_external5 f5;
        np_external6 f6; np_external7 f7; np_external8 f8;
    } symbol;
    np_word args[8];
    int index;
    va_list values;
#if defined(_WIN32)
    HMODULE module;
#elif defined(__unix__) || defined(__APPLE__)
    void *module;
#endif
    symbol.object = NULL;
#if defined(_WIN32)
    module = LoadLibraryA(library);
    if (module != NULL) symbol.object = (void *)GetProcAddress(module, entry);
#elif defined(__unix__) || defined(__APPLE__)
    module = dlopen(library, RTLD_LAZY);
    if (module != NULL) symbol.object = dlsym(module, entry);
#else
    (void)library;
    (void)entry;
#endif
    if (symbol.object == NULL) return 0;
    va_start(values, count);
    for (index = 0; index < count; ++index) args[index] = va_arg(values, np_word);
    va_end(values);
    switch (count) {
    case 0: return symbol.f0();
    case 1: return symbol.f1(args[0]);
    case 2: return symbol.f2(args[0], args[1]);
    case 3: return symbol.f3(args[0], args[1], args[2]);
    case 4: return symbol.f4(args[0], args[1], args[2], args[3]);
    case 5: return symbol.f5(args[0], args[1], args[2], args[3], args[4]);
    case 6: return symbol.f6(args[0], args[1], args[2], args[3], args[4], args[5]);
    case 7: return symbol.f7(args[0], args[1], args[2], args[3], args[4], args[5], args[6]);
    default: return symbol.f8(args[0], args[1], args[2], args[3], args[4], args[5], args[6], args[7]);
    }
}

static void np_intel_unsupported(const char *bytes)
{
    fprintf(stderr, "INTEL $%s cannot execute through the portable C89 backend.\n", bytes);
    abort();
}

static void np_write_string(const char *value)
{
    puts(value == NULL ? "" : value);
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
