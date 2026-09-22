Transform the ebnf into a language. The language must compile to go, or if that's not possible (strictly not possible) then to c.
It's a human language, easy to write and to reason about.

Inspired by Osmosian's Plain English...

Rules to follow:
1. Case insensitive: Upper, lower, or mixed case are identical.
2. Order independent: Declare types, routines, and globals anywhere in any file.
3. No nested IFs: Every conditional is a flat IF condition, action; action.
4. No nested LOOPs: Only one LOOP...REPEAT per routine. If you need an inner loop, factor it out into a sub-procedure.
5. No OOP (No methods/inheritance): Flat records and automatic type reduction only (A roundy box is a box with...).

The EBNF specifies fractions, but I think I will drop them and instead replace them by **first class scaled integers**:

something like:

```
A millimeter is 1000 micrometers.
A centimeter is 10 millimeters.
A dollar is 100 cents.

To run:
  Put 12.5 millimeters into a width.
  Put 2.25 dollars into a price.
  Add 0.75 dollars to the price.
```

It has to support syntax like: `A roundy box is a box with a radius.` per the EBNF

'More Original Documents' folder contains original plain english CAL-4700 compiler files

A comment on scaled integers: **No, they should NOT be freely combinable in general arithmetic (addition and subtraction).** 

If you make them freely combinable, you run into what language designers call **"The Float Contamination Problem,"** and you will instantly destroy the entire reason you added scaled integers in the first place.

However, there is a **very specific, elegant middle ground** that languages like Ada and modern physics engines use.

Here is why they should be kept separate, and the one exception where they make sense together:

---

### 1. The "Float Contamination" Problem

Why did you add scaled integers? 
To guarantee **exactness**, **zero rounding drift**, and **predictable integer execution** (e.g., $10.50\text{ dollars}$ or $12.5\text{ mm}$).

Look at what happens if the compiler silently combines them:
```text
Put 10.50 dollars into the balance.    \ Stored as integer 1050 cents
Add 0.1 to the balance.                \ 0.1 is an IEEE 754 float!
```

If the compiler promotes `balance` to a float, your exact integer becomes:
$$\mathbf{10.600000000000000532...}$$
Your exact financial or metric unit has just been **contaminated** by binary floating-point rounding error. The moment a float touches a scaled integer, all the benefits of Master Kronecker's integer math vanish.

---

### 2. The Dimensional Nonsense Problem

In a human-language compiler like NeoPascal, adding a raw, dimensionless float to a scaled unit **makes no physical sense**:

* What does `Add 2.5 to 10 millimeters` mean?
  * Did the programmer mean $2.5\text{ millimeters}$?
  * Did they mean $2.5\text{ meters}$?
  * Or are they trying to add a dimensionless abstract number to a physical length?

In English prose, that sentence is a category error. A disciplined compiler should stop the programmer right there:
```text
COMPILER ERROR: Cannot add a dimensionless number to millimeters.
Did you mean: Add 2.5 millimeters to the length?
```

---

### 3. The One Clean Exception: Scaling (Multiplication & Division)

While **adding** a float to a scaled integer is nonsense, **multiplying** or **scaling** a unit by a float is completely natural in everyday human language and physics:

$$\text{Length} + \text{Scalar} = \text{Nonsense}$$
$$\text{Length} \times \text{Scalar} = \mathbf{\text{Length}}$$

It makes total sense to say:
```text
Multiply the width by 1.5.
Scale the box's height by 0.75.
```

Here, `1.5` is not a length; it is a **dimensionless scalar multiplier**. 

#### How your compiler handles this under the hood:
1. `width` is a scaled integer (e.g. $12,500\text{ \mu m}$).
2. The compiler converts `12500` to float temporarily: $12500.0 \times 1.5 = 18750.0$.
3. It rounds the result back to the nearest whole integer: `18750` ($18.75\text{ mm}$).
4. The result remains a clean, exact scaled integer!

---

### 4. How to Handle Conversions: The Plain English Way

What if a programmer *genuinely* needs to turn a scaled integer into a float (for example, to pass it into a graphics trigonometry function like `sin` or `cos`)?

Don't do it with implicit compiler magic. Use the syntax already built into your EBNF and the manual (Page 59 & Page 111):

#### Explicit Coercion (`AS A REAL`):
```text
Put the width AS A REAL into a float.
```

#### Explicit Conversion:
```text
Convert the temperature to a real.
```

This ensures that whenever a programmer crosses the boundary between **exact integer reality** and **approximate floating-point reality**, it is an explicit, conscious choice.

---

### Summary Rules for NeoPascal

| Operation | Allowed? | Meaning / Result |
| :--- | :---: | :--- |
| `ScaledInt + ScaledInt` (same unit) | **YES** | Exact integer arithmetic ($12\text{ mm} + 5\text{ mm} = 17\text{ mm}$). |
| `ScaledInt + ScaledInt` (different unit)| **YES** | Auto-scaled ($1\text{ cm} + 2\text{ mm} = 12\text{ mm}$). |
| `ScaledInt + Float` | ❌ **ERROR** | Category error; prevents float contamination. |
| `ScaledInt * Float` (Scalar multiplier) | **YES** | Multiplies, rounds to nearest base unit. |
| `ScaledInt AS A REAL` | **YES** | Explicit cast into floating-point land. |

This gives you the best of all worlds: **Ada's strict dimensional safety**, **the speed of raw hardware**, and the **clarity of Plain English prose.**

---

Another comment:

Start with **C89**. Hands down.

When creating a new programming language, your biggest enemy in the first few weeks is **"fighting two wars at the same time"**:
1. *War 1:* Is your parser correctly understanding the Plain English grammar?
2. *War 2:* Is your backend correctly generating valid machine instructions, registers, and memory layouts?

If you start with LLVM IR or QBE, a bug in your compiler produces an opaque assembler crash, an LLVM assertion failure, or a silent segfault. You won't know if the bug was in your English parser or in your SSA code generator.

If you start with **C89**, everything becomes transparent.

---

### Why C89 is the Ultimate "First Backend"

#### 1. Human-Readable Debugging
When your compiler emits code that doesn't work, you can simply open `output.c` in a text editor:
```c
/* Generated from: To increment a number: */
void increment(int64_t *number) {
    *number += 1;
}
```
You can read it with your own eyes, spot typos in your code generator immediately, and understand exactly what your parser produced.

#### 2. The Host C Compiler Acts as Your Free Co-Pilot
When you compile the generated `output.c` with `gcc -Wall` or `clang -Wall`:
* If your type checker has a flaw, GCC/Clang will tell you:
  `error: passing argument 1 of 'increment' from incompatible pointer type`.
* The C compiler’s error messages will debug your own language semantics for you while you are still stabilizing the frontend.

#### 3. TCC Gives You the "Osmosian Speed" on Day One
If you install the **Tiny C Compiler (`tcc`)** (which is only a 300 KB download):
```bash
neopascal myprogram.pe
tcc -run output.c
```
TCC compiles and executes C code **in under 10 milliseconds**. You get the instantaneous, 2-second edit-compile-run loop that Gerry Rzeppa loved, without having to write a single line of native machine-code generation.

#### 4. The Runtime Library is Just a Simple Header File
Plain English needs basic memory primitives and console I/O. In C89, your initial `runtime.h` is trivial:
```c
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>

typedef struct {
    char *first;
    char *last;
} PE_Substring;

void pe_write_stdout(PE_Substring *str) {
    fwrite(str->first, 1, str->last - str->first + 1, stdout);
    fputc('\n', stdout);
}
```
You don't have to write low-level system calls or assembly glue; you lean on the C standard library.

---

### The Realistic Roadmap

Build it in this exact order:

```text
Phase 1 (Now)     ───► C89 Backend
                        └─ Get the grammar, types, records, and flat loops working.
                        └─ Run it with TCC for instant test feedback.

Phase 2 (Next)    ───► QBE or Go Backend
                        └─ If you want standalone native binaries without GCC: QBE.
                        └─ If you want cloud, Wasm, and garbage collection: Go.

Phase 3 (Later)   ───► LLVM IR Backend
                        └─ For extreme optimization, SIMD, and production polish.
```

Almost every legendary language that started with a small team or single creator—**C++ (Cfront), Nim, Nelua, V, and even Inform 7 (via Inter)**—started by emitting C.

It gets you from a blank screen to a working, runnable language in days rather than months.

### Your Target for "Day 1"
Don't worry about the whole manual yet. Your first goal is simply to have your compiler read this:
```text
To run:
  Write "Hello, world!" to the standard output.
```
and emit:
```c
#include "runtime.h"

int main(void) {
    pe_write_stdout_lit("Hello, world!");
    return 0;
}
```
The moment that compiles and runs, **NeoPascal is alive.**

A / An is used when passing an argument into an arbitrary instance of a type:
To draw a box: (Takes a box argument).
The (when not referring to an existing variable) is used to create named, zero-parameter actions:
To write the border: (Pure procedure name, zero arguments).
