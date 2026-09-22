#!/usr/bin/env python3
"""Mesor bootstrap compiler: human-readable source to C89.

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
    count: int = 1
    reference: bool = False


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
    "flag": "flag", "string": "string", "substring": "substring",
    "byte": "byte", "wyrd": "wyrd", "pointer": "pointer",
}


class Compiler:
    def __init__(self) -> None:
        self.units: dict[str, Unit] = {}
        self.records: dict[str, Record] = {}
        self.aliases: dict[str, str] = {"substring": "string"}
        self.pointers: dict[str, str | None] = {"pointer": None}
        self.collections: dict[str, str] = {}
        self.globals: dict[str, str] = {}
        self.global_values: dict[str, Value] = {}
        self.pending_globals: dict[str, tuple[str, Line]] = {}
        self.pending_typed_globals: dict[str, tuple[str, str, Line]] = {}
        self.routines: dict[str, list[Routine]] = {}
        self.lines: list[Line] = []

    def load(self, paths: list[Path]) -> None:
        for path in paths:
            try:
                raw = path.read_text(encoding="utf-8")
            except OSError as exc:
                raise CompileError(str(exc), str(path), 0) from exc
            physical: list[Line] = []
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
                    physical.append(Line(text, str(path), n))
            self.lines.extend(self._logical_lines(physical))

    @staticmethod
    def _split_periods(line: Line) -> list[Line]:
        result, start, quoted, parens, brackets = [], 0, False, 0, 0
        for index, ch in enumerate(line.text):
            if ch == '"': quoted = not quoted
            elif not quoted and ch == "(": parens += 1
            elif not quoted and ch == ")": parens = max(0, parens - 1)
            elif not quoted and ch == "[": brackets += 1
            elif not quoted and ch == "]": brackets = max(0, brackets - 1)
            elif ch == "." and not quoted and not parens and not brackets:
                if index > 0 and index + 1 < len(line.text) and line.text[index - 1].isdigit() and line.text[index + 1].isdigit():
                    continue
                text = line.text[start:index + 1].strip()
                if text: result.append(Line(text, line.source, line.number))
                start = index + 1
        tail = line.text[start:].strip()
        if tail: result.append(Line(tail, line.source, line.number))
        return result

    def _logical_lines(self, physical: list[Line]) -> list[Line]:
        """Turn wrapped declarations and inline bodies into logical clauses."""
        out: list[Line] = []
        pending: Line | None = None
        for item in physical:
            if pending is not None:
                pending.text += " " + item.text
                if self._split_periods(pending)[-1].text.endswith("."):
                    out.extend(self._split_periods(pending))
                    pending = None
                continue
            inline = re.fullmatch(r"(?i)(to\s+.+?:)\s*(.+)", item.text)
            if inline:
                out.append(Line(inline.group(1), item.source, item.number))
                out.extend(self._split_periods(Line(inline.group(2), item.source, item.number)))
                continue
            if (not self._split_periods(item)[-1].text.endswith(".")
                    and not item.text.endswith(":") and not item.text.endswith(";")):
                pending = Line(item.text, item.source, item.number)
                continue
            out.extend(self._split_periods(item))
        if pending is not None:
            raise pending.error("Unterminated declaration; expected a period")
        return out

    def _all_routines(self):
        for overloads in self.routines.values():
            yield from overloads

    def compile(self) -> str:
        self._collect_declarations()
        self._validate_types()
        return self._emit_program()

    def _collect_declarations(self) -> None:
        i = 0
        pending_aliases: list[Line] = []
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
                headers = pending_aliases + [line]
                pending_aliases = []
                for header_line in headers:
                    header_text = re.sub(r"(?i)^to\s+|[:;]\s*$", "", header_line.text)
                    routine = self._parse_routine_header(header_text, header_line, body)
                    overloads = self.routines.setdefault(routine.name, [])
                    signature = tuple(param.type_name for param in routine.params)
                    if any(tuple(param.type_name for param in other.params) == signature for other in overloads):
                        raise header_line.error(f"Routine '{routine.name}' with the same parameter types is declared twice")
                    overloads.append(routine)
                continue
            alias = re.fullmatch(r"(?i)to\s+(.+?)\s*;", text)
            if alias:
                pending_aliases.append(line)
                i += 1
                continue
            if self._parse_declaration(line):
                i += 1
                continue
            raise line.error("Expected a type, global, or routine declaration")
        if pending_aliases:
            raise pending_aliases[-1].error("Routine alias has no implementation header")
        for name, (raw, line) in self.pending_globals.items():
            lit = self._literal(raw, line)
            if lit is None:
                raise line.error(f"Invalid global constant '{raw}'")
            self.globals[name] = lit.type_name
            self.global_values[name] = lit
        for name, (type_name, raw, line) in self.pending_typed_globals.items():
            hex_match = re.fullmatch(r"\$([0-9a-fA-F]+)", raw)
            if hex_match and type_name == "wave":
                # Historical noodle WAVs were PE resources. The portable C89
                # core deliberately does not embed application sound assets.
                lit = Value("NULL", type_name)
            elif hex_match and self._resolve_type(type_name) == "string":
                digits = hex_match.group(1)
                if len(digits) % 2: digits = "0" + digits
                escaped = "".join("\\x" + digits[index:index + 2] for index in range(0, len(digits), 2))
                lit = Value('"' + escaped + '"', type_name)
            else:
                lit = self._literal(raw, line)
            if lit is None: raise line.error("A global initializer must be a constant")
            self.globals[name] = type_name
            self.global_values[name] = self._coerce(lit, type_name, line)

    @staticmethod
    def _is_declaration(text: str) -> bool:
        return bool(re.match(r"(?i)^(a|an|some|the)\s+.+\.$", text))

    def _parse_declaration(self, line: Line) -> bool:
        text = line.text
        match = re.fullmatch(r"(?i)some\s+(.+?)\s+(?:is|are)\s+some\s+(.+?)\s*\.", text)
        if match:
            name, type_name = key(match.group(1)), self._type_key("some " + match.group(2))
            if name in self.globals: raise line.error(f"Global '{name}' is declared twice")
            self.globals[name] = type_name
            return True
        # A millimeter is 1000 micrometers.
        match = re.fullmatch(r"(?i)an?\s+(.+?)\s+is\s+([0-9]+)\s+(.+?)\s*\.", text)
        if match:
            name, amount, parent = key(match.group(1)), int(match.group(2)), singular(match.group(3))
            if name in self.records or (name in self.units and not self.units[name].implicit):
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
        # An abc pointer is a pointer to an abc.
        match = re.fullmatch(r"(?i)(?:an?|some)\s+(.+?)\s+is\s+an?\s+pointer(?:\s+to\s+an?\s+(.+?))?\s*\."
                             , text)
        if match:
            name, target = key(match.group(1)), key(match.group(2)) if match.group(2) else None
            self.pointers[name] = self._type_key(target) if target else None
            return True
        # A point has a number called x and a number called y.
        match = re.fullmatch(r"(?i)(an?|some|the)\s+(.+?)\s+has\s+(.+?)\s*\.", text)
        if match:
            name = key(match.group(2))
            self._add_record(name, None, match.group(3), line)
            if key(match.group(1)) == "the": self.globals[name] = name
            return True
        # A roundy box is a box with a radius.
        match = re.fullmatch(r"(?i)(?:an?|some|the)\s+(.+?)\s+is\s+an?\s+(.+?)\s+with\s+(.+?)\s*\.", text)
        if match:
            base = key(match.group(2))
            self._add_record(key(match.group(1)), None if base in ("record", "thing record", "thing") else base, match.group(3), line)
            return True
        # A verse is a thing with a string.
        match = re.fullmatch(r"(?i)(?:an?|some|the)\s+(.+?)\s+is\s+an?\s+thing\s+with\s+(.+?)\s*\.", text)
        if match:
            self._add_record(key(match.group(1)), None, match.group(2), line)
            return True
        # An address is a number. Optional bracketed prose documents a type.
        match = re.fullmatch(r"(?i)(?:an?|some)\s+(.+?)\s+is\s+(?:an?|some)\s+(.+?)\s*(?:\[[^]]*\])?\s*\.", text)
        if match:
            name, base = key(match.group(1)), self._type_key(match.group(2))
            if name in self.aliases and self.aliases[name] == base:
                return True
            if name in self.aliases or name in self.records or name in self.pointers:
                raise line.error(f"Type '{name}' is declared twice")
            self.aliases[name] = base
            return True
        # The counter is a number. / The width is a number equal to 2.
        match = re.fullmatch(r"(?i)the\s+(.+?)\s+is\s+an?\s+(.+?)\s+equal\s+to\s+(.+?)\s*\.", text)
        if match:
            name, type_name = key(match.group(1)), self._type_key(match.group(2))
            if name in self.globals or name in self.pending_globals or name in self.pending_typed_globals:
                raise line.error(f"Global '{name}' is declared twice")
            raw = re.sub(r"\s*\[[^]]*\]\s*$", "", match.group(3)).strip()
            self.pending_typed_globals[name] = (type_name, raw, line)
            return True
        match = re.fullmatch(r"(?i)the\s+(.+?)\s+(?:is|are)\s+(an?|some)\s+(.+?)\s*\.", text)
        if match:
            name = key(match.group(1))
            type_name = self._type_key(("some " if key(match.group(2)) == "some" else "") + match.group(3))
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
        protected = re.sub(r"\[[^]]*\]", lambda m: m.group(0).replace(",", ";").replace(" and ", "; "), fields_text)
        protected = re.sub(r"\([^)]*\)", lambda m: m.group(0).replace(",", ";").replace(" and ", "; "), protected)
        normalized = re.sub(r"(?i)\s*,\s*(?:and|or)\s+|\s*,\s*|\s+(?:and|or)\s+", "|", protected)
        for raw in normalized.split("|"):
            raw = raw.strip()
            reference = bool(re.search(r"(?i)\(\s*reference\s*\)", raw))
            raw = re.sub(r"\s*\([^)]*\)|\s*\[[^]]*\]", "", raw).strip()
            match = re.fullmatch(r"(?i)(?:(an?|some|another)\s+|([0-9]+)\s+)(.+?)(?:\s+called\s+(.+))?", raw)
            if not match:
                raise line.error(f"Invalid field descriptor '{raw}'")
            count = int(match.group(2) or 1)
            type_name = self._type_key(("some " if key(match.group(1) or "") == "some" else "") + match.group(3))
            field_name = key(match.group(4) or match.group(3))
            if key(match.group(1) or "") == "another" and not match.group(4): field_name = "other " + field_name
            fields.append(Field(field_name, type_name, count, reference))
        self.records[name] = Record(name, base, fields)

    def _parse_routine_header(self, text: str, line: Line, body: list[Line]) -> Routine:
        text = key(text)
        if text == "run":
            return Routine("run", [], ["run"], body, line)
        # A routine header is also its call template. In
        # "draw a box with a color", DRAW and WITH are fixed words while the
        # two article-led portions are parameters.
        qualifier = ""
        qualifier_match = re.fullmatch(r"(.+?)\s+(\([^)]*\))", text)
        if qualifier_match:
            text, qualifier = qualifier_match.group(1), qualifier_match.group(2)
        articles = list(re.finditer(r"(?:^|\s)(a|an|some|another)\s+", text))
        if not articles:
            full_name = (text + " " + qualifier).strip()
            return Routine(full_name, [], [full_name], body, line)
        prefix = text[:articles[0].start()].strip()
        if not prefix:
            raise line.error("A routine needs a verb before its first parameter")
        params: list[Param] = []
        call_parts = [prefix]
        separators = {"and", "with", "given", "using", "returning", "to", "from", "by", "into", "in", "of", "on", "at", "before", "after", "until", "as"}
        for index, article in enumerate(articles):
            start = article.end()
            end = articles[index + 1].start() if index + 1 < len(articles) else len(text)
            descriptor = text[start:end].strip()
            separator = ""
            if index + 1 < len(articles):
                words = descriptor.split()
                separator_index = next((position for position, word in enumerate(words) if word in separators), None)
                if separator_index is None:
                    separator = ""
                else:
                    separator = " ".join(words[separator_index:])
                    descriptor = " ".join(words[:separator_index])
            else:
                trailing = re.fullmatch(r"(.+?)\s+((?:to|from|with|given|using|in|on|at|before|after)\s+the\s+.+)", descriptor)
                if trailing:
                    descriptor, separator = trailing.group(1), trailing.group(2)
                else:
                    descriptor_qualifier = re.fullmatch(r"(.+?)\s+(\([^)]*\))", descriptor)
                    if descriptor_qualifier:
                        descriptor, separator = descriptor_qualifier.group(1), descriptor_qualifier.group(2)
            match = re.fullmatch(r"(.+?)(?:\s+called\s+(.+))?", descriptor)
            if not match or not descriptor:
                raise line.error(f"Invalid routine parameter '{descriptor}'")
            described_type = key(match.group(1))
            article = key(article.group(1))
            param_name = key(match.group(2) or described_type)
            type_name = self._type_key(described_type)
            ordinal = re.fullmatch(r"(other|second|third|fourth|fifth)\s+(.+)", described_type)
            if ordinal and not match.group(2):
                type_name = self._type_key(ordinal.group(2))
            if article == "another" and not match.group(2):
                param_name = "other " + described_type
            params.append(Param(param_name, type_name))
            call_parts.append(separator)
        if qualifier:
            call_parts[-1] = (call_parts[-1] + " " + qualifier).strip()
        name = " ".join(part for part in call_parts if part)
        return Routine(name, params, call_parts, body, line)

    def _type_key(self, value: str) -> str:
        if value is None: return "pointer"
        value = key(value)
        value = re.sub(r"\s*\[[^]]*\]$", "", value).strip()
        if value.startswith("some "):
            collection = value
            if collection not in self.collections:
                self.collections[collection] = singular(value[5:])
            return collection
        value = BUILTINS.get(value, value)
        singular_value = singular(value)
        if singular_value in BUILTINS: value = BUILTINS[singular_value]
        if value not in self.units and singular_value in self.units: value = singular_value
        return value

    def _resolve_type(self, value: str, seen: set[str] | None = None) -> str:
        seen = seen or set()
        value = self._type_key(value)
        if value in seen: raise CompileError(f"Cyclic type alias involving '{value}'")
        if value in self.aliases:
            return self._resolve_type(self.aliases[value], seen | {value})
        return value

    def _validate_types(self) -> None:
        known = set(BUILTINS.values()) | set(self.units) | set(self.records) | set(self.aliases) | set(self.pointers) | set(self.collections)
        for name in self.aliases:
            resolved = self._resolve_type(name)
            if resolved not in known:
                raise CompileError(f"Type '{name}' reduces to unknown type '{resolved}'")
        for unit in self.units.values():
            if unit.parent and unit.parent not in self.units:
                raise CompileError(f"Unit '{unit.name}' refers to unknown unit '{unit.parent}'")
            self._unit_scale(unit.name, set())
        for record in self.records.values():
            if record.base and record.base not in self.records:
                raise CompileError(f"Record '{record.name}' extends unknown record '{record.base}'")
            for item in record.own_fields:
                if item.type_name not in known:
                    if item.type_name == item.name:
                        item.type_name = "number"
                    else:
                        raise CompileError(f"Record '{record.name}' uses unknown field type '{item.type_name}'")
        for type_name in self.globals.values():
            if type_name not in known:
                raise CompileError(f"Global uses unknown type '{type_name}'")
        for routine in self._all_routines():
            for param in routine.params:
                if param.type_name not in known:
                    words = param.type_name.split()
                    suffix = next((" ".join(words[index:]) for index in range(len(words))
                                   if " ".join(words[index:]) in known), None)
                    if suffix:
                        param.type_name = suffix
                    else:
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
        resolved = self._resolve_type(type_name)
        if type_name in self.pointers or resolved == "pointer": return "void *"
        if type_name in self.collections: return "np_things"
        if resolved in self.units or resolved == "number": return "np_int"
        if resolved == "byte": return "unsigned char"
        if resolved == "wyrd": return "unsigned short"
        if resolved == "real": return "double"
        if resolved == "flag": return "int"
        if resolved == "string": return "char *"
        if resolved in self.records: return ident("type " + resolved)
        raise CompileError(f"Cannot emit unknown type '{type_name}'")

    def _emit_program(self) -> str:
        out = [
            "/* Generated by Mesor. C89 source. */",
            '#include "runtime.h"', "",
        ]
        for record in self.records.values():
            c_record = ident("type " + record.name)
            out.append(f"typedef struct {c_record} {{")
            for item in self._record_fields(record.name):
                suffix = f"[{item.count}]" if item.count > 1 else ""
                out.append(f"    {self._c_type(item.type_name)} {ident(item.name)}{suffix};")
            out.append(f"}} {c_record};\n")
        for name, type_name in self.globals.items():
            initial = self.global_values.get(name)
            suffix = f" = {initial.code}" if initial is not None else ""
            out.append(f"static {self._c_type(type_name)} {ident(name)}{suffix};")
        if self.globals: out.append("")
        for routine in self._all_routines():
            if routine.name == "run": continue
            out.append(self._routine_signature(routine) + ";")
        if self.routines: out.append("")
        for routine in self._all_routines():
            if routine.name == "run": continue
            out.extend(self._emit_routine(routine))
        if "run" in self.routines:
            out.extend(self._emit_run(self.routines["run"][0]))
        return "\n".join(out) + "\n"

    def _routine_c_name(self, routine: Routine) -> str:
        overloads = self.routines.get(routine.name, [])
        if len(overloads) < 2:
            return ident(routine.name)
        signature = " ".join(param.type_name for param in routine.params) or "void"
        return ident(routine.name + " " + signature)

    def _routine_signature(self, routine: Routine) -> str:
        args = []
        for param in routine.params:
            args.append(f"{self._c_type(param.type_name)} *{ident(param.name)}")
        linkage = "" if routine.name.startswith("compatibly ") else "static "
        return f"{linkage}void {self._routine_c_name(routine)}({', '.join(args) if args else 'void'})"

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
            match = re.fullmatch(r"(?i)privatize\s+(?:(an?|some)\s+)?(.+?)(?:\s+called\s+(.+?))?\s*\.", text)
            if match:
                described = key(match.group(2))
                described = re.sub(r"^the\s+", "", described)
                existing = env.get(described)
                type_text = ("some " if key(match.group(1) or "") == "some" else "") + described
                type_name = existing[0] if existing else self._type_key(type_text)
                name = key(match.group(3) or described)
                if name in env and not existing: raise line.error(f"Local '{name}' is declared twice")
                known = set(BUILTINS.values()) | set(self.units) | set(self.records) | set(self.aliases) | set(self.pointers) | set(self.collections)
                if type_name not in known:
                    raise line.error(f"Unknown local type '{type_name}'")
                initial = existing[1] if existing else self._zero(type_name)
                c_name = ident("local " + name) if existing else ident(name)
                env[name] = (type_name, c_name)
                local_decls.append(f"    {self._c_type(type_name)} {c_name} = {initial};")
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
        resolved = self._resolve_type(type_name)
        if resolved in self.records: return "{0}"
        if resolved == "string": return 'NULL'
        if type_name in self.pointers or resolved == "pointer": return "NULL"
        if type_name in self.collections: return "{0, 0, 0}"
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
            resolved = self._resolve_type(value.type_name)
            fn = "np_write_string" if resolved == "string" else "np_write_real" if resolved == "real" else "np_write_int"
            return [indent + f"{fn}({value.code});"]
        match = re.fullmatch(r"(?i)put\s+(.+?)\s+into\s+(.+)", bare)
        if match:
            value = self._expression(match.group(1), line, env)
            target = self._variable(match.group(2), line, env)
            value = self._coerce(value, target.type_name, line)
            if self._resolve_type(target.type_name) == "string":
                return [indent + f"np_string_set(&({target.code}), {value.code});"]
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
        match = re.fullmatch(r"(?i)set\s+(.+)", bare)
        if match:
            target = self._variable(match.group(1), line, env)
            if self._resolve_type(target.type_name) != "flag": raise line.error("SET requires a flag")
            return [indent + f"{target.code} = 1;"]
        match = re.fullmatch(r"(?i)(?:clear|reset)\s+(.+)", bare)
        if match:
            target = self._variable(match.group(1), line, env)
            if self._resolve_type(target.type_name) == "flag":
                return [indent + f"{target.code} = 0;"]
            if target.type_name in self.collections:
                return [indent + f"free(({target.code}).items);", indent + f"memset(&({target.code}), 0, sizeof({target.code}));"]
        match = re.fullmatch(r"(?i)(append|prepend)\s+(.+?)\s+to\s+(.+)", bare)
        if match:
            value = self._expression(match.group(2), line, env)
            target = self._variable(match.group(3), line, env)
            if self._resolve_type(value.type_name) == "string" and self._resolve_type(target.type_name) == "string":
                fn = "np_string_append" if key(match.group(1)) == "append" else "np_string_prepend"
                return [indent + f"{fn}(&({target.code}), {value.code});"]
            if target.type_name in self.collections:
                if not value.lvalue: raise line.error("A collection stores variables, not temporary values")
                fn = "np_things_append" if key(match.group(1)) == "append" else "np_things_prepend"
                return [indent + f"{fn}(&({target.code}), (void *)&({value.code}));"]
        match = re.fullmatch(r"(?i)allocate\s+memory\s+for\s+(.+)", bare)
        if match:
            target = self._variable(match.group(1), line, env)
            if target.type_name not in self.pointers and self._resolve_type(target.type_name) != "pointer":
                raise line.error("ALLOCATE MEMORY requires a pointer")
            pointed = self.pointers.get(target.type_name)
            size = f"sizeof({self._c_type(pointed)})" if pointed else "1"
            return [indent + f"{target.code} = calloc(1, {size});"]
        match = re.fullmatch(r"(?i)(?:deallocate|unassign|destroy)\s+(.+)", bare)
        if match:
            target = self._variable(match.group(1), line, env)
            resolved = self._resolve_type(target.type_name)
            if target.type_name in self.pointers or resolved in ("pointer", "string"):
                return [indent + f"free({target.code});", indent + f"{target.code} = NULL;"]
            if target.type_name in self.collections:
                return [indent + f"free(({target.code}).items);", indent + f"memset(&({target.code}), 0, sizeof({target.code}));"]
            raise line.error("DESTROY requires a pointer or string in the C89 core")
        match = re.fullmatch(r'(?i)call\s+"([^"]+)"\s+"([^"]+)"(?:\s+with\s+(.+?))?(?:\s+returning\s+(.+))?', bare)
        if match:
            raw_args = re.split(r"(?i)\s+and\s+", match.group(3)) if match.group(3) else []
            args = [self._expression(raw, line, env) for raw in raw_args]
            if len(args) > 8: raise line.error("External CALL supports at most eight arguments")
            call = f"np_external_call(\"{match.group(1)}\", \"{match.group(2)}\", {len(args)}"
            call += "".join(f", (np_word)({arg.code})" for arg in args) + ")"
            if match.group(4):
                target = self._variable(match.group(4), line, env)
                call = f"{target.code} = ({self._c_type(target.type_name)}){call}"
            return [indent + call + ";"]
        match = re.fullmatch(r"(?i)intel\s+\$([0-9a-f]+)", bare)
        if match:
            return [indent + f'np_intel_unsupported("{match.group(1).upper()}");']
        if re.fullmatch(r"(?i)break", bare):
            if not in_loop: raise line.error("BREAK can only appear inside LOOP...REPEAT")
            return [indent + "break;"]
        if re.fullmatch(r"(?i)exit", bare):
            return [indent + ("return 0;" if main else "return;")]
        # Procedure calls follow the fixed/parameter template from the header.
        # All bootstrap procedure arguments are mutable lvalues.
        matches: list[tuple[Routine, list[str], list[Value]]] = []
        for routine in self._all_routines():
            if routine.name == "run": continue
            arguments = self._match_call(routine, bare)
            if arguments is None:
                continue
            values: list[Value] = []
            try:
                for argument in arguments:
                    values.append(self._expression(argument, line, env))
            except CompileError:
                continue
            if all(self._compatible(value.type_name, parameter.type_name)
                   for value, parameter in zip(values, routine.params)):
                matches.append((routine, arguments, values))
        if len(matches) > 1:
            names = ", ".join("/".join(p.type_name for p in r.params) for r, _, _ in matches)
            raise line.error(f"Ambiguous routine call; matching parameter types: {names}")
        if matches:
            routine, arguments, values = matches[0]
            emitted_args = []
            for argument, parameter, arg in zip(arguments, routine.params, values):
                expected = parameter.type_name
                if arg.lvalue:
                    address = f"&({arg.code})"
                else:
                    resolved = self._resolve_type(arg.type_name)
                    if resolved in ("number", "wyrd") or arg.type_name in self.units:
                        address = f"({self._c_type(expected)} *)np_scratch_int((np_int)({arg.code}))"
                    elif resolved == "byte":
                        address = f"({self._c_type(expected)} *)np_scratch_byte((unsigned char)({arg.code}))"
                    elif resolved == "string":
                        address = f"({self._c_type(expected)} *)np_scratch_string({arg.code})"
                    elif arg.type_name == "nil":
                        address = f"({self._c_type(expected)} *)np_scratch_pointer(NULL)"
                    else:
                        raise line.error(f"Argument '{argument}' cannot be materialized for mutable parameter '{parameter.name}'")
                if arg.type_name != expected and arg.type_name in self.records and expected in self.records:
                    # Derived records flatten base fields first, so the prefix is
                    # layout-compatible with its base record in emitted C.
                    address = f"({self._c_type(expected)} *){address}"
                emitted_args.append(address)
            return [indent + f"{self._routine_c_name(routine)}({', '.join(emitted_args)});"]
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
            elif index + 1 < len(routine.params):
                pattern += r"\s+"
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
            if self._resolve_type(value.type_name) == "number" and self._resolve_type(target.type_name) in ("byte", "wyrd"):
                value = self._coerce(value, target.type_name, line)
            elif self._resolve_type(value.type_name) != self._resolve_type(target.type_name):
                raise line.error(f"Cannot combine {value.type_name} with {target.type_name}")
        return f"{target.code} {op}= {value.code};"

    def _condition(self, text: str, line: Line, env: dict[str, tuple[str, str]]) -> str:
        state = re.fullmatch(r"(?i)(.+?)\s+is\s+(not\s+)?(set|clear|blank|empty|nil)", text.strip())
        if state:
            value = self._expression(state.group(1), line, env)
            negated, condition = bool(state.group(2)), key(state.group(3))
            if condition in ("blank", "empty"):
                base = f"np_string_length({value.code}) == 0"
            elif condition == "nil":
                base = f"{value.code} == NULL"
            elif condition == "set":
                base = f"{value.code} != 0"
            else:
                base = f"{value.code} == 0"
            return f"!({base})" if negated else base
        match = re.fullmatch(r"(?i)(.+?)\s+(is greater than|is less than|is at least|is at most|is not|equals|is)\s+(.+)", text.strip())
        if not match: raise line.error("Condition must use IS, IS NOT, EQUALS, or an ordered comparison")
        left, right = self._expression(match.group(1), line, env), self._expression(match.group(3), line, env)
        right = self._coerce(right, left.type_name, line)
        ops = {"is": "==", "equals": "==", "is not": "!=", "is greater than": ">", "is less than": "<", "is at least": ">=", "is at most": "<="}
        if self._resolve_type(left.type_name) == "string":
            return f"strcmp({left.code}, {right.code}) {ops[key(match.group(2))]} 0"
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
        parts = re.split(r"(?i)\s+(divided\s+by|plus|minus|times|then)\s+", text)
        if len(parts) > 1:
            value = self._expression(parts[0], line, env)
            for pos in range(1, len(parts), 2):
                value = self._binary(value, key(parts[pos]), self._expression(parts[pos + 1], line, env), line)
            return value
        literal = self._literal(text, line)
        if literal is not None: return literal
        return self._variable(text, line, env)

    def _binary(self, left: Value, operator: str, right: Value, line: Line) -> Value:
        if operator == "then":
            if self._resolve_type(left.type_name) == "string" and self._resolve_type(right.type_name) == "string":
                return Value(f"np_string_concat({left.code}, {right.code})", "string")
            raise line.error("THEN concatenates strings; convert other values explicitly")
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
        if key(text) in ("nil", "null"): return Value("NULL", "nil")
        match = re.fullmatch(r"\$([0-9a-fA-F]+)", text)
        if match: return Value("0x" + match.group(1), "number")
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
            resolved = self._resolve_type(type_name)
            if field_name in ("whereabouts", "address"):
                code, type_name = f"((void *)&({code}))", "pointer"
                continue
            if field_name == "target":
                if type_name not in self.pointers and resolved != "pointer":
                    raise line.error(f"'{root}' is not a pointer")
                target = self.pointers.get(type_name) or "byte"
                code, type_name = f"(*(({self._c_type(target)} *)({code})))", target
                continue
            if resolved == "string" and field_name == "length":
                code, type_name = f"np_string_length({code})", "number"
                continue
            if type_name in self.collections and field_name == "length":
                code, type_name = f"({code}).length", "number"
                continue
            if type_name in self.collections and field_name in ("first", "last"):
                element = self.collections[type_name]
                index = "0" if field_name == "first" else f"({code}).length - 1"
                code, type_name = f"(*(({self._c_type(element)} *)(({code}).items[{index}])))", element
                continue
            if resolved not in self.records: raise line.error(f"'{root}' is not a record")
            found = next((f for f in self._record_fields(resolved) if f.name == field_name), None)
            if found is None: raise line.error(f"Record '{type_name}' has no field '{field_name}'")
            code, type_name = f"({code}).{ident(field_name)}", found.type_name
        return Value(code, type_name, True)

    def _compatible(self, source: str, target: str) -> bool:
        if source == target: return True
        source_resolved, target_resolved = self._resolve_type(source), self._resolve_type(target)
        if source_resolved == target_resolved: return True
        if (source in self.pointers or source_resolved == "pointer") and (target in self.pointers or target_resolved == "pointer"): return True
        if source == "nil" and (target in self.pointers or target_resolved in ("pointer", "string") or target in self.collections): return True
        if source in self.units and target in self.units:
            return self._unit_scale(source, set())[0] == self._unit_scale(target, set())[0]
        current = source
        while current in self.records and self.records[current].base:
            current = self.records[current].base or ""
            if current == target: return True
        return False

    def _coerce(self, value: Value, target: str, line: Line) -> Value:
        if self._compatible(value.type_name, target):
            return Value(value.code, target, value.lvalue)
        if value.type_name in self.units and target in self.units:
            sroot, _ = self._unit_scale(value.type_name, set())
            troot, _ = self._unit_scale(target, set())
            if sroot == troot:
                # Every unit value is represented in the same root base unit.
                return Value(value.code, target, value.lvalue)
        if self._resolve_type(target) == "real" and self._resolve_type(value.type_name) == "number":
            return Value(f"((double)({value.code}))", "real")
        if self._resolve_type(value.type_name) == "number" and self._resolve_type(target) in ("byte", "wyrd"):
            return Value(f"(({self._c_type(target)})({value.code}))", target)
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
    parser = argparse.ArgumentParser(prog="mesor", description="Compile Mesor human-language programs to C89")
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
            if sys.platform.startswith("linux") and os.path.basename(cc) != "tcc": cmd.append("-ldl")
            result = subprocess.run(cmd)
            if result.returncode: return result.returncode
            if args.run:
                return subprocess.run([str(output.resolve())]).returncode
            if temporary:
                try: c_path.unlink()
                except OSError: pass
        return 0
    except CompileError as exc:
        print(f"mesor: error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"mesor: error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
