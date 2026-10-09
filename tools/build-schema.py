#!/usr/bin/env python3
"""Build the unified JSON Schema from the YAML fragments.  Standalone: shares no code with mkdocs_schema_fence/.

    python tools/build_schema.py --docs docs --out docs/assets/schema/pipeline.json     # the unified schema
    python tools/build_schema.py --docs docs --lint --check-links --strict               # CI gate

Fragments: <docs>/assets/schema/**/*.schema.yml   (override with --schema-dir).  Needs only PyYAML.

What the bundler does
  * merges every fragment's `$defs` and the single `x-root` object into one JSON Schema (draft 2020-12)
  * inlines the step modifiers/hooks (defs marked x-step-modifier) into every step branch, so each branch can
    be strict (additionalProperties: false) and editors report the real error
  * strips every `x-*` key (they only drive the docs)
  * rewrites each `description` for editors: relative page links become absolute site URLs, and MkDocs
    admonitions (`!!! note`, `??? warning "..."`) become block quotes

Keys read here: x-root (x-from-def: publish that def as the root object), x-step-branch, x-step-key, x-step-modifier, x-branch-keywords, x-page, x-docs, x-doc-type.
"""
import argparse
import copy
import json
import pathlib
import posixpath
import re
import sys
import urllib.parse

import yaml

SUFFIX = ".schema.yml"
SITE_URL = "https://concourse-ci.org/docs/"


# ------------------------------------------------------------------ loading fragments
class Index:
    def __init__(self, root):
        self.root = root
        self.frags, self.defs, self.owner = [], {}, {}
        for p in sorted(root.rglob("*" + SUFFIX)):
            frag = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            if "$schema" in frag or "$id" in frag:
                raise ValueError(
                    f"{p} looks like a bundled schema, not a fragment. Name published bundles without the "
                    "'.schema.' infix (e.g. pipeline.json) so they are not picked up as fragments."
                )
            self.frags.append((p, frag))
            for name, d in (frag.get("$defs") or {}).items():
                if name in self.defs:
                    raise ValueError(f"duplicate def {name!r} in {p} (already owned by {self.owner[name]})")
                self.defs[name] = d
                self.owner[name] = frag.get("x-page")

    def root_schema(self):
        roots = [(f["x-root"], f.get("x-page")) for _, f in self.frags if "x-root" in f]
        if len(roots) != 1:
            raise ValueError(f"expected exactly one x-root fragment, found {len(roots)}")
        return copy.deepcopy(roots[0][0]), roots[0][1]


# ------------------------------------------------------------------ editor-friendly descriptions
ADMON = re.compile(r'^(?P<i> *)(?:!!!|\?\?\?\+?) +(?P<kind>[A-Za-z]+)(?: +"(?P<title>.*)")? *$')
LINK = re.compile(r"\]\((?P<path>[^)#\s]*)(?P<frag>#[^)\s]*)?\)")


def _page_url(page, site):
    p = re.sub(r"\.md$", "", re.sub(r"(^|/)index\.md$", "", page))
    return urllib.parse.urljoin(site, p + "/" if p and not p.endswith("..") else p)


def _link(m, page, site):
    path, frag = m.group("path"), m.group("frag") or ""
    if re.match(r"^[a-z]+:", path):
        return m.group(0)
    if not path:                                     # (#anchor): same page
        return f"]({_page_url(page, site)}{frag})"
    if not path.endswith(".md"):
        return m.group(0)
    target = posixpath.normpath(posixpath.join(posixpath.dirname(page), path))
    return f"]({_page_url(target, site)}{frag})"


def _admonitions(text):
    """`!!! note` / `??? warning "title"` blocks -> block quotes (an editor shows raw admonition syntax otherwise)."""
    lines, out, i = text.split("\n"), [], 0
    while i < len(lines):
        m = ADMON.match(lines[i])
        if not m:
            out.append(lines[i]); i += 1
            continue
        ind = len(m.group("i"))
        j = i + 1
        while j < len(lines) and (not lines[j].strip() or len(lines[j]) - len(lines[j].lstrip(" ")) > ind):
            j += 1
        body = [ln[ind + 4:] if ln.strip() else "" for ln in lines[i + 1:j]]
        while body and not body[0].strip():
            body.pop(0)
        while body and not body[-1].strip():
            body.pop()
        head = m.group("title") or m.group("kind").capitalize()
        quote = ["**" + head + "**"]
        if body:
            quote += ["", *_admonitions("\n".join(body)).split("\n")]
        quoted = ["> " + q if q else ">" for q in quote]
        if out and out[-1].strip():        # a block quote needs a blank line on both sides, or neighbours merge
            out.append("")
        out.extend([m.group("i") + q for q in quoted])
        if j < len(lines) and lines[j].strip():
            out.append("")
        i = j
    return "\n".join(out)


def publish_text(text, page, site):
    if page:
        text = LINK.sub(lambda m: _link(m, page, site), text)
    return _admonitions(text)


# ------------------------------------------------------------------ bundling
def _walk(node, page, site, keep):
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if k.startswith("x-") and not keep:
                continue
            out[k] = publish_text(v, page, site) if k == "description" and isinstance(v, str) else _walk(v, page, site, keep)
        return out
    if isinstance(node, list):
        return [_walk(v, page, site, keep) for v in node]
    return node


def bundle(idx, keep_annotations=False, site=SITE_URL):
    mod_props, branch_kw = {}, {}
    for name, d in idx.defs.items():
        if d.get("x-step-modifier"):
            # relative links in a modifier's prose are relative to the modifier's page, not to the step it lands in
            mod_props.update(_walk(copy.deepcopy(d["properties"]), idx.owner[name], site, keep_annotations))
            branch_kw.update(copy.deepcopy(d.get("x-branch-keywords", {})))
    out_defs = {}
    for name, d in idx.defs.items():
        if d.get("x-step-modifier"):
            continue  # folded into the branches below
        d = copy.deepcopy(d)
        if d.get("x-step-branch"):
            d["properties"] = {**d.get("properties", {}), **copy.deepcopy(mod_props)}
            d["additionalProperties"] = False  # modifiers are inlined, so strictness is local to each branch
            key = d.get("x-step-key")
            if key:
                d["required"] = [key] + [r for r in d.get("required", []) if r != key]
            d.update(copy.deepcopy(branch_kw))
        out_defs[name] = _walk(d, idx.owner[name], site, keep_annotations)
    root, root_page = idx.root_schema()
    from_def = root.pop("x-from-def", None)
    if from_def:  # the root object is documented as a def (so the fence can render it); publish it as the root
        body = {k: v for k, v in copy.deepcopy(idx.defs[from_def]).items() if k != "x-type-label"}
        root.update(body)
        out_defs.pop(from_def, None)
    schema = _walk(root, idx.owner.get(from_def) or root_page, site, keep_annotations)
    schema["$defs"] = out_defs
    return schema


# ------------------------------------------------------------------ lint: fields with no prose
def inline_object(node):
    if "properties" in node and "$ref" not in node:
        return node
    if node.get("type") == "array" and isinstance(node.get("items"), dict):
        return inline_object(node["items"])
    for sub in node.get("anyOf", []):
        r = inline_object(sub)
        if r:
            return r
    if isinstance(node.get("else"), dict):
        return inline_object(node["else"])
    return None


def lint(idx):
    missing = []

    def walk(node, path):
        for prop, sub in (node.get("properties") or {}).items():
            if sub.get("x-docs") is False:
                continue
            ref_def = idx.defs.get(sub["$ref"].rsplit("/", 1)[-1], {}) if "$ref" in sub else {}
            if not (sub.get("description") or ref_def.get("description")):
                missing.append(f"{path}.{prop}")
            inner = inline_object(sub)
            if inner:
                walk(inner, f"{path}.{prop}")

    for name, d in idx.defs.items():
        if d.get("x-docs", True) and inline_object(d):
            walk(d if "properties" in d else inline_object(d), name)
        if d.get("x-docs", True) and d.get("x-doc-type") and not d.get("description"):
            missing.append(f"{name} (type definition)")
    for _, frag in idx.frags:  # the pipeline's root properties (jobs, resources, ...) live in x-root, not in a def
        for prop, sub in ((frag.get("x-root") or {}).get("properties") or {}).items():
            if not sub.get("description"):
                missing.append(f"pipeline.{prop}")
    return missing


# ------------------------------------------------------------------ check-links: fragments <-> pages
FENCE = re.compile(r"^([ \t]*)```concourse-schema[ \t]*\n(.*?)\n\1```[ \t]*$", re.DOTALL | re.MULTILINE)
EMBED = re.compile(r'^\s*--8<--\s+"([^"]+)"', re.MULTILINE)


def check_links(idx, docs, schema_dir):
    """Returns (errors, warnings). Errors: wrong-page embed, missing path/def/field. Warnings: missing page, orphan."""
    by_file = {p.resolve(): f for p, f in idx.frags}
    errors, warnings, rendered = [], [], set()
    for page in sorted(docs.rglob("*.md")):
        rel = page.relative_to(docs).as_posix()
        for m in FENCE.finditer(page.read_text(encoding="utf-8")):
            indent, body = m.group(1), m.group(2)
            body = "\n".join(ln[len(indent):] if ln.startswith(indent) else ln.lstrip() for ln in body.split("\n"))
            paths = EMBED.findall(body)
            if paths:
                for rp in paths:
                    hit = next((b / rp for b in (schema_dir, docs) if (b / rp).is_file()), None)
                    if not hit:
                        errors.append(f"{rel}: embeds {rp!r} which does not exist")
                        continue
                    frag = by_file.get(hit.resolve())
                    rendered.add(hit.resolve())
                    if frag is None:
                        errors.append(f"{rel}: {rp!r} is not under {schema_dir}")
                    elif frag.get("x-page") != rel:
                        errors.append(f"{rel}: embeds {rp!r} but that fragment says x-page: {frag.get('x-page')!r}")
            else:
                spec = yaml.safe_load(body) or {}
                name = spec.get("def") if isinstance(spec, dict) else None
                if name not in idx.defs:
                    errors.append(f"{rel}: fence references unknown def {name!r}")
                    continue
                if idx.owner[name] != rel:
                    errors.append(f"{rel}: renders def {name!r} which belongs to page {idx.owner[name]!r}")
                d = idx.defs[name]
                props = ((d if "properties" in d else inline_object(d)) or {}).get("properties", {})
                for key in ("only", "hide"):
                    for field in spec.get(key) or []:
                        if field not in props:
                            errors.append(f"{rel}: fence {key} lists {field!r}, which is not a field of {name}")
                rendered.update(p.resolve() for p, f in idx.frags if name in (f.get("$defs") or {}))
    for path, frag in idx.frags:
        page, label = frag.get("x-page"), path.relative_to(schema_dir)
        if page and not (docs / page).is_file():
            warnings.append(f"{label}: x-page {page!r} does not exist")
        documentable = any(d.get("x-docs", True) and (d.get("x-doc-type") or inline_object(d)) for d in (frag.get("$defs") or {}).values())
        if documentable and path.resolve() not in rendered:
            warnings.append(f"{label}: has fields but no page renders it (orphan)")
    return errors, warnings


# ------------------------------------------------------------------ CLI
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--docs", default="docs", help="docs directory (pages live here)")
    ap.add_argument("--schema-dir", help="fragment directory (default: <docs>/assets/schema)")
    ap.add_argument("--out", help="write the unified schema here (name it pipeline.json, never *.schema.yml)")
    ap.add_argument("--site-url", default=SITE_URL, help="base URL used to make links in descriptions absolute")
    ap.add_argument("--keep-annotations", action="store_true", help="keep x-* keys and raw descriptions (debugging)")
    ap.add_argument("--lint", action="store_true", help="report fields that have no prose")
    ap.add_argument("--check-links", action="store_true", help="check fragments and pages reference each other correctly")
    ap.add_argument("--strict", action="store_true", help="warnings from --lint/--check-links fail the run")
    a = ap.parse_args(argv)

    docs = pathlib.Path(a.docs)
    schema_dir = pathlib.Path(a.schema_dir) if a.schema_dir else docs / "assets" / "schema"
    idx = Index(schema_dir)
    status = 0
    if a.out:
        out = pathlib.Path(a.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        bundled = bundle(idx, a.keep_annotations, a.site_url)
        out.write_text(json.dumps(bundled, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {out}  ({len(idx.frags)} fragments -> {len(bundled['$defs'])} defs)")
    if a.lint:
        missing = lint(idx)
        print(f"{len(missing)} fields without prose")
        for m in missing[:15]:
            print("  -", m)
        if len(missing) > 15:
            print(f"  ... and {len(missing) - 15} more")
        status |= 1 if (a.strict and missing) else 0
    if a.check_links:
        errors, warnings = check_links(idx, docs, schema_dir)
        for e in errors:
            print("ERROR", e)
        for w in warnings[:6]:
            print("WARN ", w)
        if len(warnings) > 6:
            print(f"WARN  ... and {len(warnings) - 6} more")
        print(f"{len(idx.frags)} fragments, {len(errors)} error(s), {len(warnings)} warning(s)")
        status |= 1 if (errors or (a.strict and warnings)) else 0
    return status


if __name__ == "__main__":
    sys.exit(main())
