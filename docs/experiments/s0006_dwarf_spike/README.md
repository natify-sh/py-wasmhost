# S0006 spike: can pyelftools read DWARF from core wasm built by C, Zig, Rust?

Measurement only; no production reader. Files: `sample.c`, `sample.zig`, `sample.rs` (2-5 exported functions, a
self-referencing struct `node`/`Node`, an enum, a typedef (C, Zig), a callback parameter) and `dwarf_probe.py`
(extracts the wasm custom sections, builds `elftools.dwarf.dwarfinfo.DWARFInfo`, prints per CU the producer, version,
tag counts, forms, external subprograms with resolved types, struct/enum layout, tags it could not read, wall time).
Python 3.13.x, pyelftools 0.33, clang 18.1.3, rustc 1.97.0, zig 0.17.1 (from `pip install ziglang` in a venv outside the repo).

## Commands (outputs went to the scratchpad, not the repo)
```
clang --target=wasm32 -O1 -gdwarf-{4,5} -nostdlib -Wl,--no-entry -Wl,--export-all sample.c -o c_dw{4,5}.wasm
rustup target add wasm32-unknown-unknown
rustc --target wasm32-unknown-unknown --crate-type cdylib -C debuginfo=2 -C opt-level=1 -C panic=abort sample.rs -o rust_default.wasm   # DWARF 4
RUSTC_BOOTSTRAP=1 rustc ... -Zdwarf-version={4,5} sample.rs -o rust_dw{4,5}.wasm    # stable rustc rejects -Z; BOOTSTRAP is a measurement hack
zig build-lib -dynamic -target wasm32-freestanding -fno-entry -rdynamic -O ReleaseSmall sample.zig -femit-bin=zig_small.wasm
zig build-lib -dynamic -fPIC -target wasm32-freestanding -fno-entry -rdynamic -O Debug sample.zig -femit-bin=zig_debug.wasm
python3 dwarf_probe.py [-t=REGEX_FOR_TYPES_TO_PRINT] *.wasm
```
Zig note: without `-dynamic`, `build-lib` writes a static archive (`!<arch>`), not a wasm; zig emits DWARF without `-g`.

## Run / not run
Run: C DWARF4 and DWARF5; Rust DWARF4 (default) and DWARF5 (nightly flag via RUSTC_BOOTSTRAP); Zig ReleaseSmall and Debug
(both DWARF 4; zig 0.17.1 has no flag for 5 that I found, so Zig DWARF5 was NOT run). Not run: wasi-sdk/wasm32-wasip1 builds
(target installed, but the sources are `no_std` freestanding; a std/WASI module has a much larger DWARF, not measured),
C++ and emscripten, split DWARF, `.debug_types`, wasm `name`/sourcemap sections.

## Results (real output, trimmed)
```
c_dw4   CU version=4 clang 18.1.3  forms: addr data1/2/4 exprloc flag_present ref4 sec_offset strp udata      read 4.7 ms (1.7 KB file)
c_dw5   CU version=5 clang 18.1.3  forms add: addrx loclistx rnglistx strx1                                     read 1.4 ms
  add [add] (a:int, b:int) -> int                          export=True
  apply [apply] (f:cb_t=fn(int)->int*, x:int) -> int       export=True
  sum_list [sum_list] (n:const node_t*) -> u32=unsigned int
  enum color size=4 RED=0,GREEN=5,BLUE=6
  struct node size=12 value@0:int; c@4:enum:color; next@8:struct:node*
rust_dw4 / rust_default  version=4, producer 'clang LLVM (rustc version 1.97.0 ...)' lang=28   read 9.2 / 3.3 ms
rust_dw5  version=5, forms add: addrx implicit_const loclistx rnglistx strx1; sections incl. .debug_names             read 4.3 ms
  first [first] (s:structure:&[u8]) -> u8        DW_AT_external=True export=True
  len_of [len_of] (s:structure:&str) -> usize    DW_AT_external=True export=True
  sum_list [sum_list] (n:structure:Node*) -> u32
  struct &str size=8 data_ptr@0:u8*; length@4:usize
  struct &[u8] size=8 data_ptr@0:u8*; length@4:usize
  enum Color size=4 Red=0,Green=5,Blue=6      struct Node size=12 value@0:i32; c@4:enumeration:Color; next@8:structure:Node*
zig_small  version=4, producer 'zig 0.17.1' lang=12; debug_info 5192 B, 3 subprograms but 183 members (std Target types)   read 8.9-11.5 ms
zig_debug  version=4, 619 KB file, .debug_info 206 KB, 2 CUs, 6015 DW_TAG_variable                                  read 167.5 ms
  sum_list [sample.sum_list] (n:?*const sample.Node=structure:sample.Node*) -> u32  DW_AT_external=False export=True
  apply [sample.apply] (f:fn(i32)->i32*, x:i32) -> i32
  enum sample.Color size=1 red=0,green=5,blue=6   struct sample.Node size=12 value@0:i32; c@4:enumeration:sample.Color; next@8:?*sample.Node
NOT READ: none (for every file; but see (b): "not read" only counts tags absent from my KNOWN list, which I made generous)
```
(The probe prints `NOT READ` for tags outside its KNOWN set and for exceptions while resolving; the null terminator DIEs
(`tag None`) are skipped. Earlier C 300-function file, from the brief: 55 KB .debug_info, 4818 DIEs, 43 ms.)

## Answers
(a) Yes for everything run: pyelftools 0.33 parses C (DWARF 4+5), Rust (4+5) and Zig (4) with a hand-built `DWARFInfo`
(custom sections extracted by us; `DwarfConfig(default_address_size=4, machine_arch='wasm32')`; no exceptions, DIE references
resolved with `die.get_DIE_from_attribute`). DWARF5 forms strx1/addrx/loclistx/rnglistx/implicit_const worked. Zig DWARF5 untested.
(b) Tags seen: compile_unit, subprogram, formal_parameter, base_type, pointer_type, const_type (C), typedef (C, Zig; Rust has
none: `type U32 = u32` leaves no DIE), structure_type, union_type (Zig), member, enumeration_type, enumerator, subroutine_type,
array_type, subrange_type, variable. A generator must refuse or skip: namespace, variant_part, variant, template_type_param,
inlined_subroutine, lexical_block (Rust); Zig/Rust optionals and unions (`?*T` is a struct with payload/some members in Zig); array_type
members (Zig `Target.Cpu.Feature.Set`, Rust vtable). Forms seen: addr, addrx, block1, data1/2/4, exprloc, flag_present, implicit_const,
loclistx, ref4, rnglistx, sdata, sec_offset, strp, strx1, udata; no ref_addr/ref_sig8/strx2+ appeared (not proven absent in larger modules).
Also sections `.debug_names` (Rust DWARF5) and `.debug_pubnames/.debug_pubtypes` (Zig) are present and unused.
(c) Rust `&str` and `&[u8]` are a `DW_TAG_structure_type` named `&str` / `&[u8]`, size 8, members `data_ptr` (offset 0, pointer to u8)
and `length` (offset 4, usize); the parameter `s` has that struct type (a fat pointer; a wasm export takes it as two i32 or per
ABI, not as one value; `extern "C"` with a slice is not FFI-safe). Zig slices `[]const u8` are a struct with `ptr`@0 / `len`@4.
(d) C and Rust: `DW_AT_name` and `DW_AT_linkage_name` equal the export name and `DW_AT_external` is present. Zig: no
`DW_AT_external`; `DW_AT_linkage_name` is module-qualified (`sample.add`), `DW_AT_name` (`add`) matches the export. So match by
`DW_AT_name` against the export section, not by the external flag, for Zig. Non-exported externals would be missed for Zig.
(e) CPython 3.13: 1.4-4.7 ms for 0.3-1.7 KB .debug_info (C, Rust), 9-12 ms for 5 KB (Zig ReleaseSmall, has the std Target
types), 43 ms for 55 KB (brief), 167 ms for 206 KB (Zig Debug). Roughly 0.8 ms per KB of .debug_info; not measured on Pythonista/3.10.
