"""Read DWARF from the custom sections of a core wasm module with pyelftools.

Usage: python3 dwarf_probe.py a.wasm [...]
"""

import re
import sys
import time
from collections import Counter
from io import BytesIO

from elftools.dwarf.dwarfinfo import DebugSectionDescriptor, DwarfConfig, DWARFInfo

NAMES = (
    ".debug_info .debug_aranges .debug_abbrev .debug_str .debug_loc .debug_ranges .debug_line "
    ".debug_addr .debug_str_offsets .debug_line_str .debug_loclists .debug_rnglists"
).split()
# tags this probe knows how to turn into a type string; anything else is reported
KNOWN = {
    "DW_TAG_base_type",
    "DW_TAG_pointer_type",
    "DW_TAG_typedef",
    "DW_TAG_const_type",
    "DW_TAG_volatile_type",
    "DW_TAG_structure_type",
    "DW_TAG_union_type",
    "DW_TAG_enumeration_type",
    "DW_TAG_enumerator",
    "DW_TAG_member",
    "DW_TAG_subprogram",
    "DW_TAG_formal_parameter",
    "DW_TAG_subroutine_type",
    "DW_TAG_compile_unit",
    "DW_TAG_array_type",
    "DW_TAG_subrange_type",
    "DW_TAG_variable",
    "DW_TAG_lexical_block",
    "DW_TAG_inlined_subroutine",
    "DW_TAG_namespace",
    "DW_TAG_reference_type",
    "DW_TAG_unspecified_type",
    "DW_TAG_variant_part",
    "DW_TAG_variant",
    "DW_TAG_template_type_param",
    "DW_TAG_GNU_call_site",
    "DW_TAG_call_site",
    "DW_TAG_call_site_parameter",
}


def leb(b, p):
    r = s = 0
    while True:
        x = b[p]
        p += 1
        r |= (x & 0x7F) << s
        s += 7
        if not x & 0x80:
            return r, p


def custom_sections(wasm):
    p, out = 8, {}
    while p < len(wasm):
        sid = wasm[p]
        size, p = leb(wasm, p + 1)
        if sid == 0:
            n, q = leb(wasm, p)
            out[wasm[q : q + n].decode()] = wasm[q + n : p + size]
        p += size
    return out


def wasm_exports(wasm):
    p = 8
    while p < len(wasm):
        sid = wasm[p]
        size, p = leb(wasm, p + 1)
        if sid == 7:
            n, q = leb(wasm, p)
            names = []
            for _ in range(n):
                ln, q = leb(wasm, q)
                names.append(wasm[q : q + ln].decode())
                q += ln + 1
                _, q = leb(wasm, q)
            return names
        p += size
    return []


def attr(die, name, default=None):
    a = die.attributes.get(name)
    if a is None:
        return default
    v = a.value
    return v.decode() if isinstance(v, bytes) else v


def tname(cu, die, depth=0):
    if die is None:
        return "void"
    if depth > 6:
        return "..."
    t, nm = die.tag, attr(die, "DW_AT_name")
    if "DW_AT_type" in die.attributes:
        inner = tname(cu, die.get_DIE_from_attribute("DW_AT_type"), depth + 1)
    else:
        inner = "void"
    if t == "DW_TAG_base_type":
        return nm
    if t == "DW_TAG_pointer_type":
        return inner + "*"
    if t == "DW_TAG_const_type":
        return "const " + inner
    if t == "DW_TAG_typedef":
        return f"{nm}={inner}" if depth == 0 else nm
    if t in ("DW_TAG_structure_type", "DW_TAG_union_type", "DW_TAG_enumeration_type"):
        return f"{t[7:].replace('_type', '')}:{nm}"
    if t == "DW_TAG_subroutine_type":
        ps = [
            tname(cu, c.get_DIE_from_attribute("DW_AT_type")) if "DW_AT_type" in c.attributes else "void"
            for c in die.iter_children()
            if c.tag == "DW_TAG_formal_parameter"
        ]
        return f"fn({', '.join(ps)})->{inner}"
    return f"<{t}>"


def probe(path):
    wasm = open(path, "rb").read()
    t0 = time.perf_counter()
    secs = custom_sections(wasm)

    def sec(n):
        d = secs.get(n)
        return None if d is None else DebugSectionDescriptor(BytesIO(d), n, 0, len(d), 0)

    cfg = DwarfConfig(little_endian=True, default_address_size=4, machine_arch="wasm32")
    s = {n: sec(n) for n in NAMES}
    if s[".debug_info"] is None:
        print(f"== {path}: no .debug_info (sections: {sorted(secs)})")
        return
    info = DWARFInfo(
        cfg,
        s[".debug_info"],
        s[".debug_aranges"],
        s[".debug_abbrev"],
        None,
        None,
        s[".debug_str"],
        s[".debug_loc"],
        s[".debug_ranges"],
        s[".debug_line"],
        None,
        None,
        s[".debug_addr"],
        s[".debug_str_offsets"],
        s[".debug_line_str"],
        s[".debug_loclists"],
        s[".debug_rnglists"],
        None,
        None,
        None,
    )
    exports = set(wasm_exports(wasm))
    print(
        f"== {path}: {len(wasm)} bytes, debug sections "
        f"{{{', '.join(f'{k}:{len(v)}' for k, v in secs.items() if k.startswith('.debug'))}}}"
    )
    tags, forms, unread, funcs, structs = Counter(), Counter(), Counter(), [], []
    for cu in info.iter_CUs():
        top = cu.get_top_DIE()
        print(f"CU version={cu['version']} producer={attr(top, 'DW_AT_producer')!r} lang={attr(top, 'DW_AT_language')}")
        for die in cu.iter_DIEs():
            if die.is_null():  # sibling-list terminator, not a tag
                continue
            tags[die.tag] += 1
            if die.tag not in KNOWN:
                unread[die.tag] += 1
            for a in die.attributes.values():
                forms[a.form] += 1
            try:
                ext = "DW_AT_external" in die.attributes
                if (
                    die.tag == "DW_TAG_subprogram"
                    and "DW_AT_low_pc" in die.attributes
                    and (ext or attr(die, "DW_AT_name") in exports)
                ):
                    ps = [
                        f"{attr(c, 'DW_AT_name')}:{tname(cu, c.get_DIE_from_attribute('DW_AT_type'))}"
                        for c in die.iter_children()
                        if c.tag == "DW_TAG_formal_parameter"
                    ]
                    rt = (
                        tname(cu, die.get_DIE_from_attribute("DW_AT_type"))
                        if "DW_AT_type" in die.attributes
                        else "void"
                    )
                    nm = attr(die, "DW_AT_linkage_name") or attr(die, "DW_AT_name")
                    funcs.append((attr(die, "DW_AT_name"), nm, ps, rt, ext))
                if die.tag in ("DW_TAG_structure_type", "DW_TAG_enumeration_type") and attr(die, "DW_AT_name"):
                    if die.tag == "DW_TAG_enumeration_type":
                        structs.append(
                            f"enum {attr(die, 'DW_AT_name')} size={attr(die, 'DW_AT_byte_size')} "
                            + ",".join(
                                f"{attr(c, 'DW_AT_name')}={attr(c, 'DW_AT_const_value')}"
                                for c in die.iter_children()
                                if c.tag == "DW_TAG_enumerator"
                            )
                        )
                    else:
                        ms = [
                            f"{attr(c, 'DW_AT_name')}@{attr(c, 'DW_AT_data_member_location')}:"
                            f"{tname(cu, c.get_DIE_from_attribute('DW_AT_type'))}"
                            for c in die.iter_children()
                            if c.tag == "DW_TAG_member"
                        ]
                        structs.append(
                            f"struct {attr(die, 'DW_AT_name')} size={attr(die, 'DW_AT_byte_size')} " + "; ".join(ms)
                        )
            except Exception as e:  # report, never hide
                unread[f"error:{type(e).__name__}:{e}"] += 1
    dt = time.perf_counter() - t0
    print("tags:", dict(tags))
    print("forms:", sorted(forms))
    print("external subprograms (name, linkage/name, params, ret, is-wasm-export):")
    for n, ln, ps, rt, ext in funcs:
        print(f"  {n} [{ln}] ({', '.join(ps)}) -> {rt}  DW_AT_external={ext} export={n in exports}")
    print("types:")
    for x in structs:
        if re.search(TYPES, x):
            print("  " + x[:300])
    print("exports:", sorted(exports))
    print("NOT READ:", dict(unread) or "none")
    print(f"read time {dt * 1000:.1f} ms")


TYPES = ".*"
for p in sys.argv[1:]:
    if p.startswith("-t="):  # only print types whose line matches this regex
        TYPES = p[3:]
        continue
    probe(p)
