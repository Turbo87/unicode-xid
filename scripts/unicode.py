#!/usr/bin/env python
#
# Copyright 2011-2015 The Rust Project Developers. See the COPYRIGHT
# file at the top-level directory of this distribution and at
# http://rust-lang.org/COPYRIGHT.
#
# Licensed under the Apache License, Version 2.0 <LICENSE-APACHE or
# http://www.apache.org/licenses/LICENSE-2.0> or the MIT license
# <LICENSE-MIT or http://opensource.org/licenses/MIT>, at your
# option. This file may not be copied, modified, or distributed
# except according to those terms.

# This script uses the following Unicode tables:
# - DerivedCoreProperties.txt
# - ReadMe.txt
#
# Since this should not require frequent updates, we just store this
# out-of-line and check the unicode.rs file into git.

import fileinput, re, os, sys

preamble = '''// Copyright 2012-2015 The Rust Project Developers. See the COPYRIGHT
// file at the top-level directory of this distribution and at
// http://rust-lang.org/COPYRIGHT.
//
// Licensed under the Apache License, Version 2.0 <LICENSE-APACHE or
// http://www.apache.org/licenses/LICENSE-2.0> or the MIT license
// <LICENSE-MIT or http://opensource.org/licenses/MIT>, at your
// option. This file may not be copied, modified, or distributed
// except according to those terms.

// NOTE: The following code was generated by "scripts/unicode.py", do not edit directly

#![allow(missing_docs, non_upper_case_globals, non_snake_case)]
'''

def fetch(f):
    if not os.path.exists(os.path.basename(f)):
        os.system("curl -O http://www.unicode.org/Public/UNIDATA/%s"
                  % f)

    if not os.path.exists(os.path.basename(f)):
        sys.stderr.write("cannot load %s" % f)
        exit(1)

def group_cat(cat):
    cat_out = []
    letters = sorted(set(cat))
    cur_start = letters.pop(0)
    cur_end = cur_start
    for letter in letters:
        assert letter > cur_end, \
            "cur_end: %s, letter: %s" % (hex(cur_end), hex(letter))
        if letter == cur_end + 1:
            cur_end = letter
        else:
            cat_out.append((cur_start, cur_end))
            cur_start = cur_end = letter
    cat_out.append((cur_start, cur_end))
    return cat_out

def ungroup_cat(cat):
    cat_out = []
    for (lo, hi) in cat:
        while lo <= hi:
            cat_out.append(lo)
            lo += 1
    return cat_out

def format_table_content(f, content, indent):
    line = " "*indent
    first = True
    for chunk in content.split(","):
        if len(line) + len(chunk) < 98:
            if first:
                line += chunk
            else:
                line += ", " + chunk
            first = False
        else:
            f.write(line + ",\n")
            line = " "*indent + chunk
    f.write(line)

def load_properties(f, interestingprops):
    fetch(f)
    props = {}
    re1 = re.compile("^ *([0-9A-F]+) *; *(\w+)")
    re2 = re.compile("^ *([0-9A-F]+)\.\.([0-9A-F]+) *; *(\w+)")

    for line in fileinput.input(os.path.basename(f)):
        prop = None
        d_lo = 0
        d_hi = 0
        m = re1.match(line)
        if m:
            d_lo = m.group(1)
            d_hi = m.group(1)
            prop = m.group(2)
        else:
            m = re2.match(line)
            if m:
                d_lo = m.group(1)
                d_hi = m.group(2)
                prop = m.group(3)
            else:
                continue
        if interestingprops and prop not in interestingprops:
            continue
        d_lo = int(d_lo, 16)
        d_hi = int(d_hi, 16)
        if prop not in props:
            props[prop] = []
        props[prop].append((d_lo, d_hi))

    # optimize if possible
    for prop in props:
        props[prop] = group_cat(ungroup_cat(props[prop]))

    return props

def escape_char(c):
    return "'\\u{%x}'" % c

def emit_bsearch_range_table(f):
    f.write("""
fn bsearch_range_table(c: char, r: &[(char,char)]) -> bool {
    use core::cmp::Ordering::{Equal, Less, Greater};

    r.binary_search_by(|&(lo,hi)| {
        // Because ASCII ranges are at the start of the tables, a search for an
        // ASCII char will involve more `Greater` results (i.e. the `(lo,hi)`
        // table entry is greater than `c`) than `Less` results. And given that
        // ASCII chars are so common, it makes sense to favor them. Therefore,
        // the `Greater` case is tested for before the `Less` case.
        if lo > c { Greater }
        else if hi < c { Less }
        else { Equal }
    }).is_ok()
}\n
""")

def emit_table(f, name, t_data, t_type = "&[(char, char)]", is_pub=True,
        pfun=lambda x: "(%s,%s)" % (escape_char(x[0]), escape_char(x[1])), is_const=True):
    pub_string = "const"
    if not is_const:
        pub_string = "let"
    if is_pub:
        pub_string = "static"
    f.write("    %s %s: %s = &[\n" % (pub_string, name, t_type))
    data = ""
    first = True
    for dat in t_data:
        if not first:
            data += ","
        first = False
        data += pfun(dat)
    format_table_content(f, data, 8)
    f.write("\n    ];\n\n")

def emit_property_module(f, mod, tbl, emit):
    f.write("pub mod %s {\n" % mod)
    for cat in sorted(emit):
        emit_table(f, "%s_table" % cat, tbl[cat])
        f.write("    pub fn %s(c: char) -> bool {\n" % cat)
        f.write("        super::bsearch_range_table(c, %s_table)\n" % cat)
        f.write("    }\n\n")
    f.write("}\n\n")

if __name__ == "__main__":
    r = "tables.rs"
    if os.path.exists(r):
        os.remove(r)
    with open(r, "w") as rf:
        # write the file's preamble
        rf.write(preamble)

        # download and parse all the data
        fetch("ReadMe.txt")
        with open("ReadMe.txt") as readme:
            pattern = "for Version (\d+)\.(\d+)\.(\d+) of the Unicode"
            unicode_version = re.search(pattern, readme.read()).groups()
        rf.write("""
/// The version of [Unicode](http://www.unicode.org/)
/// that this version of unicode-xid is based on.
pub const UNICODE_VERSION: (u64, u64, u64) = (%s, %s, %s);
""" % unicode_version)
        emit_bsearch_range_table(rf)

        want_derived = ["XID_Start", "XID_Continue"]
        derived = load_properties("DerivedCoreProperties.txt", want_derived)
        emit_property_module(rf, "derived_property", derived, want_derived)
