#!/usr/bin/env python3
"""NeoPascal bootstrap compiler: human-readable source to C89.

This deliberately small compiler is self contained so that the language can
bootstrap its semantics before acquiring a more sophisticated parser.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path


class CompileError(Exception):
    def __init__(self, message: str, source: str = "", line: int = 0):
        self.message, self.source, self.line = message, source, line
        where = f"{source}:{line}: " if source and line else ""
        super().__init__(where + message)


def key(value: str) -> str:
    return " ".join(value.lower().strip().split())


def ident(value: str) -> str:
    out = re.sub(r"[^a-z0-9_]", "_", key(value).replace("'s", "_"))
    out = re.sub(r"_+", "_", out).strip("_")
    if not out or out[0].isdigit():
        out = "n_" + out
    return "np_" + out


def singular(word: str) -> str:
    word = key(word)
    if word.endswith("ies") and len(word) > 3:
        return word[:-3] + "y"
    if word.endswith("es") and word[:-2].endswith(("s", "x", "z", "ch", "sh")):
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


@dataclass
class Line:
    text: str
    source: str
    number: int

    def error(self, message: str) -> CompileError:
        return CompileError(message, self.source, self.number)


@dataclass
class Unit:
    name: str
    parent: str | None = None
    multiplier: int = 1
    implicit: bool = False


@dataclass
class Field:
    name: str
    type_name: str


@dataclass
class Record:
    name: str
    base: str | None
    own_fields: list[Field]


@dataclass
class Param:
    name: str
    type_name: str


@dataclass
class Routine:
    name: str
    params: list[Param]
    call_parts: list[str]
    lines: list[Line]
    header: Line


@dataclass
class Value:
    code: str
    type_name: str
    lvalue: bool = False


BUILTINS = {
    "number": "number", "integer": "number", "real": "real",
    "flag": "flag", "string": "string", "substring": "string",
    "byte": "number", "wyrd": "number", "pointer": "pointer",
}


class Compiler:
    def __init__(self) -> None:
        self.units: dict[str, Unit] = {}
        self.records: dict[str, Record] = {}
        self.globals: dict[str, str] = {}
        self.global_values: dict[str, Value] = {}
        self.pending_globals: dict[str, tuple[str, Line]] = {}
        self.routines: dict[str, Routine] = {}
        self.lines: list[Line] = []

    def load(self, paths: list[Path]) -> None:
        for path in paths:
            try:
                raw = path.read_text(encoding="utf-8")
            except OSError as exc:
                raise CompileError(str(exc), str(path), 0) from exc
            for n, original in enumerate(raw.splitlines(), 1):
                # A backslash begins a comment outside a string.
                text, quoted = "", False
                for ch in original:
                    if ch == '"':
                        quoted = not quoted
                    if ch == "\\" and not quoted:
                        break
                    text += ch
                text = text.strip()
                if text:
                    self.lines.append(Line(text, str(path), n))

    def compile(self) -> str:
        self._collect_declarations()
        self._validate_types()
        return self._emit_program()

    def _collect_declarations(self) -> None:
        i = 0
        while i < len(self.lines):
            line = self.lines[i]
            text = line.text
            header = re.fullmatch(r"(?i)to\s+(.+?)\s*:", text)
            if header:
                body: list[Line] = []
                i += 1
                while i < len(self.lines) and not re.fullmatch(r"(?i)to\s+(.+?)\s*:", self.lines[i].text):
                    # Top-level declarations may occur anywhere, including after routines.
                    if self._is_declaration(self.lines[i].text):
                        break
                    body.append(self.lines[i])
                    i += 1
                routine = self._parse_routine_header(header.group(1), line, body)
                if routine.name in self.routines:
                    raise line.error(f"Routine '{routine.name}' is declared twice")
                self.routines[routine.name] = routine
                continue
            if self._parse_declaration(line):
                i += 1
                continue
            raise line.error("Expected a type, global, or routine declaration")
        for name, (raw, line) in self.pending_globals.items():
            lit = self._literal(raw, line)
            if lit is None:
                raise line.error(f"Invalid global constant '{raw}'")
            self.globals[name] = lit.type_name
            self.global_values[name] = lit
        if "run" not in self.routines:
            raise CompileError("The program needs a 'To run:' routine")

    @staticmethod
    def _is_declaration(text: str) -> bool:
        return bool(re.match(r"(?i)^(a|an|the)\s+.+\.$", text))

    def _parse_declaration(self, line: Line) -> bool:
        text = line.text
        # A millimeter is 1000 micrometers.
        match = re.fullmatch(r"(?i)an?\s+(.+?)\s+is\s+([0-9]+)\s+(.+?)\s*\.", text)
        if match:
            name, amount, parent = key(match.group(1)), int(match.group(2)), singular(match.group(3))
            if name in self.units or name in self.records:
                raise line.error(f"Type '{name}' is declared twice")
            self.units[name] = Unit(name, parent, amount)
            if parent not in self.units:
                self.units[parent] = Unit(parent, implicit=True)
            return True
        # A cent is a unit.
        match = re.fullmatch(r"(?i)an?\s+(.+?)\s+is\s+an?\s+(?:scaled\s+)?unit\s*\.", text)
        if match:
            name = key(match.group(1))
            if name in self.records or (name in self.units and not self.units[name].implicit):
                raise line.error(f"Type '{name}' is declared twice")
            self.units[name] = Unit(name)
            return True
        # A point has a number called x and a number called y.
        match = re.fullmatch(r"(?i)an?\s+(.+?)\s+has\s+(.+?)\s*\.", text)
        if match:
            self._add_record(key(match.group(1)), None, match.group(2), line)
            return True
        # A roundy box is a box with a radius.
        match = re.fullmatch(r"(?i)an?\s+(.+?)\s+is\s+an?\s+(.+?)\s+with\s+(.+?)\s*\.", text)
        if match:
            base = key(match.group(2))
            self._add_record(key(match.group(1)), None if base in ("record", "thing record") else base, match.group(3), line)
            return True
        # The counter is a number. / The width is a number equal to 2.
        match = re.fullmatch(r"(?i)the\s+(.+?)\s+is\s+an?\s+(.+?)\s+equal\s+to\s+(.+?)\s*\.", text)
        if match:
            name, type_name = key(match.group(1)), self._type_key(match.group(2))
            if name in self.globals or name in self.pending_globals:
                raise line.error(f"Global '{name}' is declared twice")
            lit = self._literal(match.group(3), line)
            if lit is None: raise line.error("A global initializer must be a constant")
            self.globals[name] = type_name
            self.global_values[name] = self._coerce(lit, type_name, line)
            return True
        match = re.fullmatch(r"(?i)the\s+(.+?)\s+is\s+an?\s+(.+?)\s*\.", text)
        if match:
            name, type_name = key(match.group(1)), self._type_key(match.group(2))
            if name in self.globals:
                raise line.error(f"Global '{name}' is declared twice")
            self.globals[name] = type_name
            return True
        match = re.fullmatch(r"(?i)the\s+(.+?)\s+is\s+(.+?)\s*\.", text)
        if match:
            name = key(match.group(1))
            value = match.group(2)
            try:
                lit = self._literal(value, line)
            except CompileError as exc:
                if "Unknown scaled unit" not in exc.message:
                    raise
                lit = None
            if lit is None:
                if re.fullmatch(r"[+-]?[0-9]+(?:\.[0-9]+)?\s+.+", value):
                    if name in self.globals or name in self.pending_globals:
                        raise line.error(f"Global '{name}' is declared twice")
                    self.pending_globals[name] = (value, line)
                    return True
                return False
            if name in self.globals or name in self.pending_globals:
                raise line.error(f"Global '{name}' is declared twice")
            self.globals[name] = lit.type_name
            self.global_values[name] = lit
            return True
        return False

    def _add_record(self, name: str, base: str | None, fields_text: str, line: Line) -> None:
        if name in self.records or name in self.units:
            raise line.error(f"Type '{name}' is declared twice")
        fields: list[Field] = []
        normalized = re.sub(r"(?i)\s*,\s*and\s+|\s*,\s*|\s+and\s+", "|", fields_text)
        for raw in normalized.split("|"):
            raw = raw.strip()
            match = re.fullmatch(r"(?i)an?\s+(.+?)(?:\s+called\s+(.+))?", raw)
            if not match:
                raise line.error(f"Invalid field descriptor '{raw}'")
            type_name = self._type_key(match.group(1))
            field_name = key(match.group(2) or match.group(1))
            fields.append(Field(field_name, type_name))
        self.records[name] = Record(name, base, fields)

    def _parse_routine_header(self, text: str, line: Line, body: list[Line]) -> Routine:
        text = key(text)
        if text == "run":
            return Routine("run", [], ["run"], body, line)
        # A routine header is also its call template. In
        # "draw a box with a color", DRAW and WITH are fixed words while the
        # two article-led portions are parameters.
        articles = list(re.finditer(r"(?:^|\s)an?\s+", text))
        if not articles:
            return Routine(text, [], [text], body, line)
        prefix = text[:articles[0].start()].strip()
        if not prefix:
            raise line.error("A routine needs a verb before its first parameter")
        params: list[Param] = []
        call_parts = [prefix]
        separators = {"and", "with", "to", "from", "by", "into", "in", "of", "on", "before", "after"}
        for index, article in enumerate(articles):
            start = article.end()
            end = articles[index + 1].start() if index + 1 < len(articles) else len(text)
            descriptor = text[start:end].strip()
            separator = ""
            if index + 1 < len(articles):
                words = descriptor.split()
                if not words or words[-1] not in separators:
                    raise line.error("Parameters in a routine header must be separated by a phrase such as WITH or AND")
                separator = words.pop()
                descriptor = " ".join(words)
            match = re.fullmatch(r"(.+?)(?:\s+called\s+(.+))?", descriptor)
            if not match or not descriptor:
                raise line.error(f"Invalid routine parameter '{descriptor}'")
            type_name = self._type_key(match.group(1))
            param_name = key(match.group(2) or match.group(1))
            params.append(Param(param_name, type_name))
            call_parts.append(separator)
        name = " ".join(part for part in call_parts if part)
        return Routine(name, params, call_parts, body, line)

    def _type_key(self, value: str) -> str:
        value = key(value)
        value = BUILTINS.get(value, value)
        if value not in self.units and singular(value) in self.units:
            value = singular(value)
        return value

    def _validate_types(self) -> None:
        known = set(BUILTINS.values()) | set(self.units) | set(self.records)
        for unit in self.units.values():
            if unit.parent and unit.parent not in self.units:
                raise CompileError(f"Unit '{unit.name}' refers to unknown unit '{unit.parent}'")
            self._unit_scale(unit.name, set())
        for record in self.records.values():
            if record.base and record.base not in self.records:
                raise CompileError(f"Record '{record.name}' extends unknown record '{record.base}'")
            for item in record.own_fields:
                if item.type_name not in known:
                    # Plain-English shorthand: an otherwise unknown field is numeric.
                    item.type_name = "number"
        for type_name in self.globals.values():
            if type_name not in known:
                raise CompileError(f"Global uses unknown type '{type_name}'")
        for routine in self.routines.values():
            for param in routine.params:
                if param.type_name not in known:
                    raise routine.header.error(f"Parameter uses unknown type '{param.type_name}'")

    def _unit_scale(self, name: str, seen: set[str]) -> tuple[str, int]:
        if name in seen:
            raise CompileError(f"Cyclic scaled-unit definition involving '{name}'")
        unit = self.units[name]
        if unit.parent is None:
            return name, 1
        root, scale = self._unit_scale(unit.parent, seen | {name})
        return root, scale * unit.multiplier

    def _record_fields(self, name: str) -> list[Field]:
        record = self.records[name]
        inherited = self._record_fields(record.base) if record.base else []
        names = {field.name for field in inherited}
        for item in record.own_fields:
            if item.name in names:
                raise CompileError(f"Record '{name}' repeats inherited field '{item.name}'")
            names.add(item.name)
        return inherited + record.own_fields

    def _c_type(self, type_name: str) -> str:
        if type_name in self.units or type_name == "number": return "np_int"
        if type_name == "real": return "double"
        if type_name == "flag": return "int"
        if type_name == "string": return "const char *"
        if type_name == "pointer": return "void *"
        if type_name in self.records: return ident(type_name)
        raise CompileError(f"Cannot emit unknown type '{type_name}'")

    def _emit_program(self) -> str:
        out = [
            "/* Generated by NeoPascal. C89 source. */",
            '#include "runtime.h"', "",
        ]
        for record in self.records.values():
            out.append(f"typedef struct {ident(record.name)} {{")
            for item in self._record_fields(record.name):
                out.append(f"    {self._c_type(item.type_name)} {ident(item.name)};")
            out.append(f"}} {ident(record.name)};\n")
        for name, type_name in self.globals.items():
            initial = self.global_values.get(name)
            suffix = f" = {initial.code}" if initial is not None else ""
            out.append(f"static {self._c_type(type_name)} {ident(name)}{suffix};")
        if self.globals: out.append("")
        for routine in self.routines.values():
            if routine.name == "run": continue
            out.append(self._routine_signature(routine) + ";")
        if len(self.routines) > 1: out.append("")
        for routine in self.routines.values():
            if routine.name == "run": continue
            out.extend(self._emit_routine(routine))
        out.extend(self._emit_run(self.routines["run"]))
        return "\n".join(out) + "\n"

    def _routine_signature(self, routine: Routine) -> str:
        args = []
        for param in routine.params:
            args.append(f"{self._c_type(param.type_name)} *{ident(param.name)}")
        return f"static void {ident(routine.name)}({', '.join(args) if args else 'void'})"

    def _emit_routine(self, routine: Routine) -> list[str]:
        env = {p.name: (p.type_name, f"(*{ident(p.name)})") for p in routine.params}
        return self._emit_body(routine, self._routine_signature(routine), env)

    def _emit_run(self, routine: Routine) -> list[str]:
        body = self._emit_body(routine, "int main(void)", {}, main=True)
        return body

    def _emit_body(self, routine: Routine, signature: str, env: dict[str, tuple[str, str]], main: bool = False) -> list[str]:
        local_decls: list[str] = []
        code: list[str] = []
        loop_count, in_loop = 0, False
        for line in routine.lines:
            text = line.text
            match = re.fullmatch(r"(?i)privatize\s+an?\s+(.+?)(?:\s+called\s+(.+?))?\s*\.", text)
            if match:
                type_name = self._type_key(match.group(1))
                name = key(match.group(2) or match.group(1))
                if name in env: raise line.error(f"Local '{name}' is declared twice")
                if type_name not in set(BUILTINS.values()) | set(self.units) | set(self.records):
                    raise line.error(f"Unknown local type '{type_name}'")
                env[name] = (type_name, ident(name))
                local_decls.append(f"    {self._c_type(type_name)} {ident(name)} = {self._zero(type_name)};")
                continue
            if re.fullmatch(r"(?i)loop\s*\.", text):
                loop_count += 1
                if loop_count > 1: raise line.error("Only one LOOP...REPEAT is allowed per routine")
                in_loop = True
                code.append("    for (;;) {")
                continue
            if re.fullmatch(r"(?i)repeat\s*\.", text):
                if not in_loop: raise line.error("REPEAT has no matching LOOP")
                in_loop = False
                code.append("    }")
                continue
            code.extend(self._emit_statement(text, line, env, "        " if in_loop else "    ", in_loop, main))
        if in_loop: raise routine.header.error("LOOP has no matching REPEAT")
        out = [signature + " {"] + local_decls + code
        if main: out.append("    return 0;")
        out.append("}\n")
        return out

    def _zero(self, type_name: str) -> str:
        if type_name in self.records: return "{0}"
        if type_name == "string": return '""'
        if type_name == "pointer": return "NULL"
        return "0"

    def _emit_statement(self, text: str, line: Line, env: dict[str, tuple[str, str]], indent: str, in_loop: bool, main: bool) -> list[str]:
        text = text.strip()
        if not text.endswith("."):
            raise line.error("Every statement must end with a period")
        bare = text[:-1].strip()
        # IF is deliberately one physical statement containing flat actions.
        match = re.fullmatch(r"(?i)if\s+(.+?)\s*,\s*(.+)", bare)
        if match:
            actions = [a.strip() for a in match.group(2).split(";") if a.strip()]
            if not actions: raise line.error("IF needs an action after the comma")
            condition = self._condition(match.group(1), line, env)
            emitted = [indent + f"if ({condition}) {{"]
            for action in actions:
                if re.match(r"(?i)^if\s+", action): raise line.error("Nested IF statements are forbidden")
                emitted.extend(self._emit_statement(action + ".", line, env, indent + "    ", in_loop, main))
            emitted.append(indent + "}")
            return emitted
        match = re.fullmatch(r"(?i)write\s+(.+?)\s+to\s+(?:the\s+)?standard output", bare)
        if match:
            value = self._expression(match.group(1), line, env)
            fn = "np_write_string" if value.type_name == "string" else "np_write_real" if value.type_name == "real" else "np_write_int"
            return [indent + f"{fn}({value.code});"]
        match = re.fullmatch(r"(?i)put\s+(.+?)\s+into\s+(.+)", bare)
        if match:
            value = self._expression(match.group(1), line, env)
            target = self._variable(match.group(2), line, env)
            value = self._coerce(value, target.type_name, line)
            return [indent + f"{target.code} = {value.code};"]
        match = re.fullmatch(r"(?i)add\s+(.+?)\s+to\s+(.+)", bare)
        if match: return [indent + self._add_sub(match.group(1), match.group(2), "+", line, env)]
        match = re.fullmatch(r"(?i)subtract\s+(.+?)\s+from\s+(.+)", bare)
        if match: return [indent + self._add_sub(match.group(1), match.group(2), "-", line, env)]
        match = re.fullmatch(r"(?i)(?:multiply|scale)\s+(.+?)\s+by\s+(.+)", bare)
        if match:
            target = self._variable(match.group(1), line, env)
            scalar = self._expression(match.group(2), line, env)
            if target.type_name not in self.units: raise line.error("Only a scaled integer can be scaled")
            if scalar.type_name not in ("number", "real"): raise line.error("Scale factor must be dimensionless")
            if scalar.type_name == "number":
                return [indent + f"{target.code} *= {scalar.code};"]
            return [indent + f"{target.code} = np_scale({target.code}, {scalar.code});"]
        if re.fullmatch(r"(?i)break", bare):
            if not in_loop: raise line.error("BREAK can only appear inside LOOP...REPEAT")
            return [indent + "break;"]
        if re.fullmatch(r"(?i)exit", bare):
            return [indent + ("return 0;" if main else "return;")]
        # Procedure calls follow the fixed/parameter template from the header.
        # All bootstrap procedure arguments are mutable lvalues.
        for routine in self.routines.values():
            if routine.name == "run": continue
            arguments = self._match_call(routine, bare)
            if arguments is None:
                continue
            emitted_args = []
            for argument, parameter in zip(arguments, routine.params):
                arg = self._variable(argument, line, env)
                if not self._compatible(arg.type_name, parameter.type_name):
                    raise line.error(f"Routine expects {parameter.type_name}, got {arg.type_name}")
                address = f"&({arg.code})"
                expected = parameter.type_name
                if arg.type_name != expected and arg.type_name in self.records and expected in self.records:
                    # Derived records flatten base fields first, so the prefix is
                    # layout-compatible with its base record in emitted C.
                    address = f"({self._c_type(expected)} *){address}"
                emitted_args.append(address)
            return [indent + f"{ident(routine.name)}({', '.join(emitted_args)});"]
        raise line.error(f"Unsupported or unknown statement: '{bare}'")

    @staticmethod
    def _match_call(routine: Routine, text: str) -> list[str] | None:
        if not routine.params:
            return [] if key(text) == routine.call_parts[0] else None
        pattern = "^" + re.escape(routine.call_parts[0]) + r"\s+"
        for index in range(len(routine.params)):
            pattern += r"(.+?)" if index + 1 < len(routine.params) else r"(.+)"
            separator = routine.call_parts[index + 1]
            if separator:
                pattern += r"\s+" + re.escape(separator) + r"\s+"
        match = re.fullmatch(pattern, key(text), re.IGNORECASE)
        return list(match.groups()) if match else None

    def _add_sub(self, source: str, target_text: str, op: str, line: Line, env: dict[str, tuple[str, str]]) -> str:
        value = self._expression(source, line, env)
        target = self._variable(target_text, line, env)
        if target.type_name in self.units:
            if value.type_name not in self.units:
                raise line.error(f"Cannot add a dimensionless {value.type_name} to {target.type_name}")
            value = self._coerce(value, target.type_name, line)
        elif value.type_name != target.type_name:
            raise line.error(f"Cannot combine {value.type_name} with {target.type_name}")
        return f"{target.code} {op}= {value.code};"

    def _condition(self, text: str, line: Line, env: dict[str, tuple[str, str]]) -> str:
        match = re.fullmatch(r"(?i)(.+?)\s+(is greater than|is less than|is at least|is at most|is not|equals|is)\s+(.+)", text.strip())
        if not match: raise line.error("Condition must use IS, IS NOT, EQUALS, or an ordered comparison")
        left, right = self._expression(match.group(1), line, env), self._expression(match.group(3), line, env)
        right = self._coerce(right, left.type_name, line)
        ops = {"is": "==", "equals": "==", "is not": "!=", "is greater than": ">", "is less than": "<", "is at least": ">=", "is at most": "<="}
        return f"{left.code} {ops[key(match.group(2))]} {right.code}"

    def _expression(self, text: str, line: Line, env: dict[str, tuple[str, str]]) -> Value:
        text = text.strip()
        cast = re.fullmatch(r"(?i)(.+?)\s+as\s+an?\s+(real|number)", text)
        if cast:
            value = self._expression(cast.group(1), line, env)
            target = key(cast.group(2))
            if target == "real": return Value(f"((double)({value.code}))", "real")
            return Value(f"((np_int)({value.code}))", "number")
        # The grammar defines left-to-right word operators. Parentheses are not
        # part of the bootstrap expression grammar, keeping prose unambiguous.
        parts = re.split(r"(?i)\s+(divided\s+by|plus|minus|times)\s+", text)
        if len(parts) > 1:
            value = self._expression(parts[0], line, env)
            for pos in range(1, len(parts), 2):
                value = self._binary(value, key(parts[pos]), self._expression(parts[pos + 1], line, env), line)
            return value
        literal = self._literal(text, line)
        if literal is not None: return literal
        return self._variable(text, line, env)

    def _binary(self, left: Value, operator: str, right: Value, line: Line) -> Value:
        if operator in ("plus", "minus"):
            symbol = "+" if operator == "plus" else "-"
            if left.type_name in self.units:
                if right.type_name not in self.units:
                    raise line.error(f"Cannot combine scaled {left.type_name} with dimensionless {right.type_name}")
                right = self._coerce(right, left.type_name, line)
                return Value(f"({left.code} {symbol} {right.code})", left.type_name)
            if left.type_name != right.type_name or left.type_name not in ("number", "real"):
                raise line.error(f"Cannot combine {left.type_name} with {right.type_name}")
            return Value(f"({left.code} {symbol} {right.code})", left.type_name)
        if operator in ("times", "divided by"):
            symbol = "*" if operator == "times" else "/"
            if left.type_name in self.units:
                if right.type_name == "number":
                    return Value(f"({left.code} {symbol} {right.code})", left.type_name)
                if right.type_name == "real":
                    scalar = right.code if operator == "times" else f"(1.0 / ({right.code}))"
                    return Value(f"np_scale({left.code}, {scalar})", left.type_name)
                raise line.error("A scaled integer may only be scaled by a dimensionless number")
            if left.type_name in ("number", "real") and right.type_name in ("number", "real"):
                result_type = "real" if "real" in (left.type_name, right.type_name) else "number"
                return Value(f"({left.code} {symbol} {right.code})", result_type)
            raise line.error(f"Cannot multiply or divide {left.type_name} by {right.type_name}")
        raise line.error(f"Unknown operator '{operator}'")

    def _literal(self, text: str, line: Line) -> Value | None:
        text = text.strip()
        if len(text) >= 2 and text[0] == text[-1] == '"':
            escaped = text[1:-1].replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
            return Value(f'"{escaped}"', "string")
        if key(text) in ("yes", "true"): return Value("1", "flag")
        if key(text) in ("no", "false"): return Value("0", "flag")
        match = re.fullmatch(r"([+-]?[0-9]+(?:\.[0-9]+)?)(?:\s+(.+))?", text)
        if not match: return None
        try: number = Decimal(match.group(1))
        except InvalidOperation: raise line.error(f"Invalid number '{match.group(1)}'")
        unit_text = match.group(2)
        if unit_text:
            unit_name = self._type_key(unit_text)
            if unit_name not in self.units: raise line.error(f"Unknown scaled unit '{unit_text}'")
            _, scale = self._unit_scale(unit_name, set())
            stored = number * scale
            if stored != stored.to_integral_value():
                raise line.error(f"{text} is smaller than the exact base unit")
            return Value(str(int(stored)), unit_name)
        if number == number.to_integral_value(): return Value(str(int(number)), "number")
        return Value(format(number, "f"), "real")

    def _variable(self, text: str, line: Line, env: dict[str, tuple[str, str]]) -> Value:
        text = re.sub(r"(?i)^the\s+", "", text.strip())
        pieces = re.split(r"(?i)'s\s+|\s+of\s+", text)
        root = key(pieces[0])
        if root in env: type_name, code = env[root]
        elif root in self.globals: type_name, code = self.globals[root], ident(root)
        else: raise line.error(f"Unknown variable '{root}'")
        for raw_field in pieces[1:]:
            field_name = key(raw_field)
            if type_name not in self.records: raise line.error(f"'{root}' is not a record")
            found = next((f for f in self._record_fields(type_name) if f.name == field_name), None)
            if found is None: raise line.error(f"Record '{type_name}' has no field '{field_name}'")
            code, type_name = f"({code}).{ident(field_name)}", found.type_name
        return Value(code, type_name, True)

    def _compatible(self, source: str, target: str) -> bool:
        if source == target: return True
        if source in self.units and target in self.units:
            return self._unit_scale(source, set())[0] == self._unit_scale(target, set())[0]
        current = source
        while current in self.records and self.records[current].base:
            current = self.records[current].base or ""
            if current == target: return True
        return False

    def _coerce(self, value: Value, target: str, line: Line) -> Value:
        if value.type_name == target: return value
        if value.type_name in self.units and target in self.units:
            sroot, _ = self._unit_scale(value.type_name, set())
            troot, _ = self._unit_scale(target, set())
            if sroot == troot:
                # Every unit value is represented in the same root base unit.
                return Value(value.code, target, value.lvalue)
        if target == "real" and value.type_name == "number":
            return Value(f"((double)({value.code}))", "real")
        raise line.error(f"Cannot convert {value.type_name} to {target}")


def find_c_compiler(requested: str | None) -> str:
    if requested:
        path = shutil.which(requested)
        if not path: raise CompileError(f"C compiler '{requested}' was not found")
        return path
    for candidate in ("tcc", "cc", "gcc", "clang"):
        path = shutil.which(candidate)
        if path: return path
    raise CompileError("No C compiler found (tried tcc, cc, gcc, clang)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="neopascal", description="Compile NeoPascal human-language programs to C89")
    parser.add_argument("sources", nargs="+", type=Path)
    parser.add_argument("-o", "--output", type=Path, help="output executable (also invokes a C compiler)")
    parser.add_argument("--emit-c", type=Path, help="write generated C here")
    parser.add_argument("--cc", help="C compiler command (default: tcc, then cc)")
    parser.add_argument("--run", action="store_true", help="run the compiled program")
    args = parser.parse_args(argv)
    try:
        compiler = Compiler()
        compiler.load(args.sources)
        generated = compiler.compile()
        c_path = args.emit_c
        temporary = False
        if not c_path:
            c_path = args.sources[0].with_suffix(".c")
            temporary = args.output is not None
        c_path.write_text(generated, encoding="utf-8")
        if args.output or args.run:
            output = args.output or args.sources[0].with_suffix("")
            cc = find_c_compiler(args.cc)
            runtime_dir = Path(__file__).resolve().parent
            cmd = [cc, "-I", str(runtime_dir), str(c_path), "-o", str(output)]
            if os.path.basename(cc) != "tcc": cmd[1:1] = ["-std=c89", "-pedantic", "-Wall", "-Wextra"]
            result = subprocess.run(cmd)
            if result.returncode: return result.returncode
            if args.run:
                return subprocess.run([str(output.resolve())]).returncode
            if temporary:
                try: c_path.unlink()
                except OSError: pass
        return 0
    except CompileError as exc:
        print(f"neopascal: error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"neopascal: error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
