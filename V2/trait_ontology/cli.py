"""Command-line explorer for the botanical trait ontology.

Two verbs cover all exploration; a few task verbs cover extraction.

  list      show any node (group / trait / field / value) or filter fields
  search    find anything matching a keyword (name / synonym / definition)

Examples::

    python -m trait_ontology list                              # all groups
    python -m trait_ontology list leaf_morphology              # a group: traits + fields
    python -m trait_ontology list leaf_shape_type              # a trait: its values
    python -m trait_ontology list leaf_shape_type CORDATE      # a single value
    python -m trait_ontology list fruit_diameter               # a field: its detail
    python -m trait_ontology list --structure calyx            # everything for a structure
    python -m trait_ontology list --structure calyx --sex male # filtered to male
    python -m trait_ontology list --structures                 # valid structure names

    python -m trait_ontology search calyx
    python -m trait_ontology search "heart-shaped"

    python -m trait_ontology resolve leaf_shape_type "heart-shaped"
    python -m trait_ontology resolve-any "bell-shaped"
    python -m trait_ontology stats
    python -m trait_ontology check

Add ``--json`` to any command for machine-readable output (handy for agents).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from typing import Optional

from .ontology import load_ontology


# ---------------------------------------------------------------------------
# rendering helpers
# ---------------------------------------------------------------------------
def _print(obj, as_json: bool):
    if as_json:
        print(json.dumps(obj, indent=2, default=str))
    else:
        print(obj)


def _suggest(onto, query: str, limit: int = 6) -> list:
    """Names (group / trait / field) similar to ``query``, for 'did you mean'."""
    q = query.lower()
    names = list(onto.groups) + list(onto.categorical) + list(onto.fields)
    hits = [n for n in names if q in n.lower() or n.lower() in q]
    return sorted(set(hits))[:limit]


# ---------------------------------------------------------------------------
# Generic ASCII tree renderer.
#
# A "node" is a dict: {"label": str, "children": [node, ...]}.
# Attributes (DESCRIPTION, SYNONYMS, ...) are just child nodes with no children
# of their own, so they render as labeled branches and never break the tree.
# ---------------------------------------------------------------------------
def node(label: str, children: Optional[list] = None) -> dict:
    return {"label": label, "children": children or []}


def _render_tree(nodes: list, prefix: str = "") -> None:
    """Print a list of sibling nodes under ``prefix`` with ├──/└── connectors."""
    for i, n in enumerate(nodes):
        last = i == len(nodes) - 1
        connector = "└── " if last else "├── "
        print(f"{prefix}{connector}{n['label']}")
        if n["children"]:
            extension = "    " if last else "│   "
            _render_tree(n["children"], prefix + extension)


def _value_node(v) -> dict:
    """Build a tree node for a categorical value (DESCRIPTION/SYNONYMS/PARENT
    as labeled child branches)."""
    head = v.name
    if v.label and v.label != v.name:
        head += f"  ({v.label})"
    if v.status != "active":
        head += f"  [{v.status}]"
    attrs = []
    if v.definition:
        attrs.append(node(f"DESCRIPTION: {v.definition}"))
    if v.synonyms:
        attrs.append(node(f"SYNONYMS: {', '.join(v.synonyms)}"))
    if v.parents:
        attrs.append(node(f"PARENT: {', '.join(v.parents)}"))
    return node(head, attrs)


def _field_node(f, with_tags: bool = False) -> dict:
    """Tree node for a field: DESCRIPTION (+ optional sex/position tags) as
    labeled child branches."""
    attrs = [node(f"DESCRIPTION: {f.description}")] if f.description else []
    if with_tags:
        if f.sex != "neutral":
            attrs.append(node(f"SEX: {f.sex}"))
        if f.position:
            attrs.append(node(f"POSITION: {', '.join(f.position)}"))
    return node(f"{f.name}  [{f.datatype}]", attrs)


def _trait_node(t) -> dict:
    """Tree node for a categorical trait header (DESCRIPTION branch)."""
    attrs = [node(f"DESCRIPTION: {t.description}")] if t.description else []
    return node(f"{t.name}  [categorical]", attrs)


def _trait_count(onto, gname: str) -> int:
    return len(onto.categorical_in_group(gname)) + len(onto.measurements_in_group(gname))


def _describe_one_json(onto, args) -> dict | list | None:
    """Return the JSON payload for `list <name>` (one name), so multi-name mode
    can stitch results into a dict. Mirrors the single-name JSON paths in cmd_list."""
    name = args.name
    if args.value is not None:
        t = onto.categorical.get(name)
        if t is None:
            return {"error": f"no categorical trait named {name!r}"}
        v = t.value(args.value)
        if v is None:
            return {"error": f"no value {args.value!r} in {name!r}"}
        return asdict(v)
    kind = onto.classify(name)
    if kind == "group":
        return {
            "group": name,
            "subgroups": [
                {
                    "name": s.name,
                    "description": s.description,
                    "categorical": [asdict(c) for c in onto.categorical_in_group(s.name)],
                    "fields": [asdict(m) for m in onto.measurements_in_group(s.name)],
                }
                for s in onto.subgroups(name)
            ],
            "categorical": [asdict(c) for c in onto.categorical_in_group(name)],
            "fields": [asdict(m) for m in onto.measurements_in_group(name)],
        }
    if kind == "trait":
        return [asdict(v) for v in onto.categorical[name].values]
    if kind == "field":
        return asdict(onto.fields[name])
    return {"error": f"no group, trait, or field named {name!r}"}


# ---------------------------------------------------------------------------
# list — navigate the tree, or filter fields with flags
# ---------------------------------------------------------------------------
def cmd_list(onto, args):
    # discovery: list the available structure names for --structure
    if getattr(args, "structures", False):
        rows = onto.list_structures()
        if args.json:
            _print(rows, True)
            return
        print(f"Available structures ({len(rows)}) — use with `list --structure <name>`:\n")
        for r in rows:
            print(f"  {r['structure']:<22} {r['n_fields']} field(s)")
        return

    # discovery: list the available position tags for --position
    if getattr(args, "positions", False):
        rows = onto.list_positions()
        if args.json:
            _print(rows, True)
            return
        print(f"Available positions ({len(rows)}) — use with `list --position <name>`:\n")
        for r in rows:
            print(f"  {r['position']:<22} {r['n_fields']} field(s)")
        return

    has_filter = any([args.structure, args.sex, args.position, args.group])

    # filter mode: any flag given -> cross-cutting field query
    if has_filter:
        fields = onto.fields_for(
            structure=args.structure, sex=args.sex, position=args.position,
            group=args.group,
        )

        # Categorical traits carry no structure/sex/position tags, so they're
        # matched by name/group, and only when NOT filtering by a field-only
        # dimension (--sex / --position), which can't apply to a vocabulary.
        cats: list = []
        field_only = args.sex or args.position
        if not field_only:
            if args.structure:
                cats = onto.categorical_for_structure(args.structure)
            elif args.group:
                cats = onto.categorical_in_group(args.group)

        if args.json:
            _print({"categorical": [asdict(c) for c in cats],
                    "fields": [asdict(f) for f in fields]}, True)
            return

        if not cats and not fields:
            print("(nothing matches those filters)")
            return

        roots = []
        if cats:
            roots.append(node(
                f"CATEGORICAL TRAITS ({len(cats)}) — pick from controlled vocabulary",
                [_trait_node(c) for c in cats]))
        if fields:
            by_sex: dict = {}
            for f in fields:
                by_sex.setdefault(f.sex, []).append(f)
            field_nodes = []
            for sex in ("neutral", "male", "female"):
                for f in by_sex.get(sex, []):
                    field_nodes.append(_field_node(f, with_tags=True))
            roots.append(node(f"FIELDS ({len(fields)})", field_nodes))
        _render_tree(roots)
        return

    # navigation mode
    if not args.name:
        # top level: groups as a nested tree (subgroups indented under parent)
        if args.json:
            _print(onto.list_groups(), True)
            return

        def group_node(g, depth=0) -> dict:
            children = []
            if g.description:
                children.append(node(f"DESCRIPTION: {g.description}"))
            for sg in onto.subgroups(g.name):
                children.append(group_node(sg, depth + 1))
            # subgroups (depth > 0) get a leading "+" — their traits are
            # ADDITIONAL to the parent's, not part of the parent's count.
            n = _trait_count(onto, g.name)
            count = f"+{n} trait(s)" if depth else f"{n} trait(s)"
            return node(f"{g.name}  ({count})", children)

        top = [g for g in onto.groups.values() if not g.parent]
        _render_tree([group_node(g) for g in top])
        return

    # multi-name form: `list a,b,c` -> render each in turn. One CLI call,
    # one round-trip, many names. Output: sections separated by `── name ──`
    # headers (text mode) or a dict keyed by name (JSON mode).
    names = [n.strip() for n in args.name.split(",") if n.strip()]
    if len(names) > 1:
        if args.json:
            result = {}
            for n in names:
                args.name = n
                result[n] = _describe_one_json(onto, args)
            _print(result, True)
            return
        for i, n in enumerate(names):
            if i:
                print()
            print(f"── {n} ──")
            args.name = n
            # reuse the single-name renderer by calling cmd_list recursively
            # with a single name; it writes to stdout and returns.
            cmd_list(onto, args)
        return

    name = args.name

    # value form: `list <trait> <VALUE>` -> one value's detail + narrower terms
    if args.value is not None:
        t = onto.categorical.get(name)
        if t is None:
            print(f"No categorical trait named {name!r}.", file=sys.stderr)
            sys.exit(1)
        v = t.value(args.value)
        if v is None:
            print(f"No value {args.value!r} in {name!r}.", file=sys.stderr)
            sys.exit(1)
        if args.json:
            _print(asdict(v), True)
            return
        vnode = _value_node(v)
        kids = onto.children(args.value, name)
        if kids:
            vnode["children"].append(
                node(f"NARROWER TERMS ({len(kids)})", [_value_node(k) for k in kids]))
        _render_tree([node(f"{name}.{v.name}  (value)", [vnode])])
        return

    kind = onto.classify(name)

    if kind == "group":
        subs = onto.subgroups(name)
        cats = onto.categorical_in_group(name)
        meas = onto.measurements_in_group(name)
        if args.json:
            _print({"group": name,
                    "subgroups": [
                        {
                            "name": s.name,
                            "description": s.description,
                            "categorical": [asdict(c) for c in onto.categorical_in_group(s.name)],
                            "fields": [asdict(m) for m in onto.measurements_in_group(s.name)],
                        }
                        for s in subs
                    ],
                    "categorical": [asdict(c) for c in cats],
                    "fields": [asdict(m) for m in meas]}, True)
            return
        g = onto.get_group(name)
        root_children = []
        if g and g.description:
            root_children.append(node(f"DESCRIPTION: {g.description}"))
        if g and g.parent:
            root_children.append(node(f"UNDER: {g.parent}"))
        if subs:
            sub_nodes = []
            for s in subs:
                s_cats = onto.categorical_in_group(s.name)
                s_meas = onto.measurements_in_group(s.name)
                s_children = []
                if s.description:
                    s_children.append(node(f"DESCRIPTION: {s.description}"))
                if s_cats:
                    s_children.append(node(
                        f"CATEGORICAL TRAITS ({len(s_cats)})",
                        [_trait_node(c) for c in s_cats]))
                if s_meas:
                    s_children.append(node(
                        f"FIELDS ({len(s_meas)})",
                        [_field_node(m) for m in s_meas]))
                sub_nodes.append(node(f"{s.name}  (subgroup, +{_trait_count(onto, s.name)} trait(s))", s_children))
            root_children.append(node(f"SUBGROUPS ({len(subs)})", sub_nodes))
        if cats:
            root_children.append(node(f"CATEGORICAL TRAITS ({len(cats)})",
                                      [_trait_node(c) for c in cats]))
        if meas:
            root_children.append(node(f"FIELDS ({len(meas)})",
                                      [_field_node(m) for m in meas]))
        kind_label = "subgroup" if (g and g.parent) else "group"
        _render_tree([node(f"{name}  ({kind_label})", root_children)])
        return

    if kind == "trait":
        t = onto.categorical[name]
        if args.json:
            _print([asdict(v) for v in t.values], True)
            return
        children = []
        if t.description:
            children.append(node(f"DESCRIPTION: {t.description}"))
        children.append(node(f"GROUP: {t.group}"))
        children.append(node(f"VALUES ({len(t.values)})",
                             [_value_node(v) for v in t.values]))
        _render_tree([node(f"{t.name}  (categorical trait)", children)])
        return

    if kind == "field":
        f = onto.fields[name]
        if args.json:
            _print(asdict(f), True)
            return
        attrs = []
        if f.description:
            attrs.append(node(f"DESCRIPTION: {f.description}"))
        attrs.append(node(f"GROUP: {f.group}"))
        if f.unit_hint:
            attrs.append(node(f"TYPICAL UNIT: {f.unit_hint}"))
        if f.structure:
            attrs.append(node(f"STRUCTURE: {f.structure}"))
        attrs.append(node(f"SEX: {f.sex}"))
        if f.position:
            attrs.append(node(f"POSITION: {', '.join(f.position)}"))
        _render_tree([node(f"{f.name}  ({f.datatype} field, kind={f.kind})", attrs)])
        return

    # maybe it's a bare value name living in one or more traits
    vtraits = onto.traits_with_value(name)
    if vtraits:
        print(f"{name!r} is a value, not a group/trait. Specify the trait:", file=sys.stderr)
        for tr in vtraits:
            print(f"  list {tr} {name}", file=sys.stderr)
        sys.exit(1)

    # not found
    msg = f"No group, trait, or field named {name!r}."
    sug = _suggest(onto, name)
    msg += (" Did you mean: " + ", ".join(sug) + " ?") if sug else " Try `list` or `search`."
    print(msg, file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# search — find anything matching a keyword
# ---------------------------------------------------------------------------
def _render_search_hits(hits):
    for h in hits:
        m = h.get("match", "")
        if h["type"] == "value":
            print(f"value  {h['value']:<24} in {h['trait']:<26} ({m})")
        elif h["type"] == "trait":
            print(f"trait  {h['name']:<24} group={h['group']:<22} ({m})")
        elif h["type"] == "group":
            print(f"group  {h['name']:<24} ({m})")
        else:  # field
            print(f"field  {h['name']:<24} {h.get('datatype',''):<13} ({m})")
    print(f"\n{len(hits)} match(es).")


def cmd_search(onto, args):
    queries = _split_terms(args.query)

    # Single keyword: original behavior (flat output / single JSON array).
    if len(queries) == 1:
        hits = onto.search(queries[0])
        if args.json:
            _print(hits, True)
            return
        if not hits:
            print("(no matches)")
            return
        _render_search_hits(hits)
        return

    # BATCH form: one section per keyword (text) / dict keyed by keyword (JSON).
    if args.json:
        _print({q: onto.search(q) for q in queries}, True)
        return
    for i, q in enumerate(queries):
        if i:
            print()
        print(f"── search {q!r} ──")
        hits = onto.search(q)
        if not hits:
            print("(no matches)")
            continue
        _render_search_hits(hits)


# ---------------------------------------------------------------------------
# extraction task verbs
# ---------------------------------------------------------------------------
def _split_terms(term: str) -> list[str]:
    """Split a comma-separated term string into trimmed phrases. A single
    phrase with no comma comes back as a one-element list."""
    return [t.strip() for t in term.split(",") if t.strip()]


def cmd_resolve(onto, args):
    terms = _split_terms(args.term)
    if args.json:
        if len(terms) == 1:
            v = onto.resolve_value(args.trait, terms[0])
            _print(asdict(v) if v else None, True)
            return
        out = {}
        for t in terms:
            v = onto.resolve_value(args.trait, t)
            out[t] = asdict(v) if v else None
        _print(out, True)
        return
    for t in terms:
        v = onto.resolve_value(args.trait, t)
        if v:
            print(f"{t!r} -> {v.name}  (in {args.trait})")
        else:
            print(f"{t!r} did not match any value in {args.trait!r}.")


def cmd_resolve_any(onto, args):
    terms = _split_terms(args.term)
    if args.json:
        if len(terms) == 1:
            _print(onto.resolve_anywhere(terms[0]), True)
            return
        _print({t: onto.resolve_anywhere(t) for t in terms}, True)
        return
    for t in terms:
        hits = onto.resolve_anywhere(t)
        if not hits:
            print(f"{t!r} matched no controlled value in any trait.")
            continue
        for h in hits:
            print(f"{t!r} -> {h['trait']}.{h['value']}")


# ---------------------------------------------------------------------------
# utility
# ---------------------------------------------------------------------------
def cmd_stats(onto, args):
    from collections import Counter
    cat = onto.categorical
    n_values = sum(len(t.values) for t in cat.values())
    by_datatype = Counter(f.datatype for f in onto.fields.values())
    stats = {
        "groups": len(onto.groups),
        "categorical_traits": len(cat),
        "categorical_values": n_values,
        "quantitative_fields": by_datatype.get("quantitative", 0),
        "text_fields": by_datatype.get("text", 0),
        "list_fields": by_datatype.get("list", 0),
        "total_fields": len(onto.fields),
    }
    if args.json:
        _print(stats, True)
        return
    for k, v in stats.items():
        print(f"{k:<24} {v}")


def cmd_check(onto, args):
    """Internal consistency check for the hand-edited ontology YAML."""
    problems: list = []

    for t in list(onto.categorical.values()) + list(onto.fields.values()):
        if t.group and t.group not in onto.groups:
            problems.append(f"{t.name}: group {t.group!r} does not exist")

    overlap = set(onto.categorical) & set(onto.fields)
    for name in sorted(overlap):
        problems.append(f"name {name!r} is used by both a categorical trait and a field")

    for t in onto.categorical.values():
        seen: set = set()
        for v in t.values:
            if v.name in seen:
                problems.append(f"{t.name}: duplicate value {v.name!r}")
            seen.add(v.name)
        for v in t.values:
            for p in v.parents:
                if p not in seen:
                    problems.append(f"{t.name}.{v.name}: parent {p!r} is not a value of this trait")

    for g in onto.groups.values():
        if g.parent and g.parent not in onto.groups:
            problems.append(f"group {g.name}: parent {g.parent!r} does not exist")

    if args.json:
        _print({"ok": not problems, "problems": problems}, True)
        return
    if problems:
        print(f"{len(problems)} problem(s):")
        for p in problems:
            print(f"  - {p}")
        sys.exit(1)
    print("OK — ontology is internally consistent.")


# ---------------------------------------------------------------------------
# arg parsing
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    agent_recipe = """\
Agent workflow for one trait group:
  1. `list <group>`            group's traits + fields (subgroups expanded inline)
  2. `list <trait>`            allowed values for a categorical trait
  3. `list a,b,c`              batch: get checklists for multiple traits in ONE call
  4. `resolve <trait> "<phrase>"`        map ONE phrase to a code
  5. `resolve <trait> "p1, p2, p3"`      BATCH: map several phrases in ONE call
  6. `resolve-any "<phrase>"`  same, when you don't know which trait (also batches)
  7. `search <kw>` / `search "kw1, kw2, kw3"`   keyword search (single or batched)

Node identity:
  group  = collection of traits (e.g. leaf_morphology)
  trait  = a controlled vocabulary (e.g. leaf_shape_type) — has VALUES
  field  = a non-categorical slot (e.g. fruit_diameter) — has a datatype
  value  = one entry in a trait's vocabulary (e.g. CORDATE)

Add --json to any command for machine-readable output."""
    p = argparse.ArgumentParser(prog="trait_ontology", description=__doc__,
                                epilog=agent_recipe,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ontology-dir", help="override the ontology directory")
    p.add_argument("--json", action="store_true", help="machine-readable JSON output")
    sub = p.add_subparsers(dest="command", required=True)

    # list
    list_desc = """\
Show the contents of one node, or filter fields across the ontology.

Forms:
  list                            all groups
  list <group>                    a group: subgroups (expanded inline) + traits + fields
  list <trait>                    a trait: its allowed values (with synonyms)
  list <trait> <VALUE>            one value: definition + synonyms + narrower terms
  list <field>                    a field: datatype + structure/sex/position
  list a,b,c                      batch: comma-separated names, one section per name
                                  (--json mode: dict keyed by name)
  list --structure <part>         body-part checklist (categorical + measurements)
  list --structure <part> --sex {male,female,neutral}    narrow to one sex
  list --structures               valid structure names
  list --positions                valid position names"""
    s = sub.add_parser(
        "list",
        help="show a group / trait / field / value, or filter fields (--structure ...)",
        description=list_desc,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    s.add_argument("name", nargs="?",
                   help="a group, trait, field, or (with VALUE) a trait name; omit for all groups")
    s.add_argument("value", nargs="?", help="a value name (requires the trait as `name`)")
    s.add_argument("--structure", help="filter to a structure, e.g. calyx, corolla, leaf")
    s.add_argument("--structures", action="store_true",
                   help="list the available structure names (for use with --structure)")
    s.add_argument("--sex", choices=["neutral", "male", "female"], help="filter fields by sex")
    s.add_argument("--position", help="filter fields by position, e.g. inner, outer, tube, lobe")
    s.add_argument("--positions", action="store_true",
                   help="list the available position names (for use with --position)")
    s.add_argument("--group", help="filter to a group")
    s.set_defaults(func=cmd_list)

    # search
    search_desc = """\
Substring match across names, synonyms, and definitions of groups, traits,
fields, and values.

Use search as a fall-back: prefer `resolve` when you already know the trait.

  search calyx                          → all calyx-related fields / traits / values
  search "heart-shaped"                 → CORDATE  (synonym match in leaf_shape_type)
  search "floret, ray color, pappus"    → BATCH: one section per keyword in ONE call
                                          (--json mode: dict keyed by keyword)"""
    s = sub.add_parser(
        "search",
        help="find anything matching a keyword (name / synonym / definition)",
        description=search_desc,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    s.add_argument("query", help="substring to look up (quote if it has spaces); "
                                  "for batch, pass comma-separated keywords as one quoted string")
    s.set_defaults(func=cmd_search)

    # resolve
    resolve_desc = """\
Map a book phrase to the controlled code within ONE trait. Use when you know
which trait the phrase belongs to (the usual case during extraction).

  resolve leaf_shape_type "heart-shaped"           → CORDATE
  resolve corolla_type    "bell-shaped"            → CAMPANULATE

Batch form — comma-separated phrases for the same trait in ONE call:

  resolve leaf_shape_type "ovate, lanceolate, cordate"
  # → three mappings printed, one per phrase

If nothing matches, try `resolve-any` or `search` to find the right trait."""
    s = sub.add_parser(
        "resolve",
        help="map a raw term to a controlled value within one trait",
        description=resolve_desc,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    s.add_argument("trait", help="the trait name (e.g. leaf_shape_type)")
    s.add_argument("term", help="book phrase to map (quote if it has spaces); "
                                 "for batch, pass comma-separated phrases as one quoted string")
    s.set_defaults(func=cmd_resolve)

    resolve_any_desc = """\
Map a phrase to a code across ALL traits — useful when you don't yet know
which trait it belongs to.

  resolve-any "bell-shaped"          → corolla_type.CAMPANULATE
  resolve-any "ovate"                → multiple matches; narrow with `resolve`

Batch form — comma-separated phrases in ONE call:

  resolve-any "bell-shaped, heart-shaped, prostrate"
  # → returns matches grouped by phrase"""
    s = sub.add_parser(
        "resolve-any",
        help="map a raw term to a controlled value across all traits",
        description=resolve_any_desc,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    s.add_argument("term", help="book phrase to map (quote if it has spaces); "
                                 "for batch, pass comma-separated phrases as one quoted string")
    s.set_defaults(func=cmd_resolve_any)

    # utility
    s = sub.add_parser("stats", help="ontology summary counts")
    s.set_defaults(func=cmd_stats)

    s = sub.add_parser("check", help="validate the ontology YAML for internal consistency")
    s.set_defaults(func=cmd_check)

    return p


def main(argv: Optional[list] = None):
    args = build_parser().parse_args(argv)
    onto = load_ontology(args.ontology_dir)
    args.func(onto, args)


if __name__ == "__main__":
    main()
