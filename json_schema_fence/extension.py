"""mkdocs_schema_fence: expand a ```concourse-schema fence into the docs' field reference.

Self-contained on purpose (same shape as mkdocs_metrics_fence): imports only the standard library, `markdown`
and PyYAML (already a dependency of Zensical and MkDocs). It shares no code with tools/build_schema.py;
tests/check_loader_parity.py keeps the two loaders honest.

Page usage (the fence may be indented, e.g. inside a content tab or another admonition):

    ```concourse-schema
    def: getFields               <- the fields of one def  (optional `hide: [a, b]` or `only: [a, b]`)
    ```
    ```concourse-schema
    --8<-- "config-basics.schema.yml"     <- a whole fragment, embedded by pymdownx.snippets (runs first)
    ```

Output reproduces the hand-written pages, field by field:

    ??? info "**`passed`**: [`[job.name]`](../jobs.md#job-schema)"      <- ??? warning for required fields
        ### `passed`                  <- the field heading: #passed anchor, TOC entry, search hit
        description, verbatim

Everything that varies per field lives in the fragment, written there by tools/import_docs.py:

  field:  description | x-type (raw signature text) | x-heading (false | level) | x-open | x-doc-required
          x-required-text (false = warning colour without the words "(required)") | x-group | x-docs: false
  object schema inside a field:  x-type-label (adds a `### label schema` heading) | x-heading-level
  def:    x-page | x-type-label | x-anchor | x-link | x-docs | x-open | x-field-headings | x-heading-level
          x-doc-type (a documented *type*, rendered as `### `label` schema` + prose) | x-step-key

Links are relative .md links computed from the page that owns the fragment (`x-page`), so the site build
validates them like any hand-written link.

mkdocs.yml:
    - pymdownx.snippets: {base_path: [docs/assets/schema, docs], check_paths: true}
    - mkdocs_schema_fence.extension: {docs_root: docs/assets/schema}
"""
import os
import pathlib
import posixpath
import re
import textwrap

import yaml
from markdown.extensions import Extension
from markdown.preprocessors import Preprocessor

FENCE_PATTERN = re.compile(r"^([ \t]*)```concourse-schema[ \t]*\n(.*?)\n\1```[ \t]*$", re.DOTALL | re.MULTILINE)
DEFAULT_ROOT = "docs/assets/schema"
SUFFIX = ".schema.yml"
HEADING_LEVEL = 3  # field and section headings, unless a def sets x-heading-level
LINK = re.compile(r"\]\((?P<path>[^)#\s]*)(?P<frag>#[^)\s]*)?\)")


# ------------------------------------------------------------------ loading fragments
class Index:
    """All defs across all fragments, and which docs page owns each (used to link types)."""

    def __init__(self, files):
        self.defs, self.owner = {}, {}
        for p in files:
            frag = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            if "$schema" in frag or "$id" in frag:
                raise ValueError(
                    f"{p} looks like a bundled schema, not a fragment. Name published bundles without the "
                    "'.schema.' infix (e.g. pipeline.json) so they are not picked up as fragments."
                )
            for name, d in (frag.get("$defs") or {}).items():
                if name in self.defs:
                    raise ValueError(f"duplicate def {name!r} in {p} (already owned by {self.owner[name]})")
                self.defs[name] = d
                self.owner[name] = frag.get("x-page")


_CACHE = {}


def load_index(root=None):
    """Parsed once per build; re-parsed when any fragment changes, so live reload sees edits."""
    root = pathlib.Path(root or os.environ.get("CONCOURSE_DOCS_ROOT", DEFAULT_ROOT))
    files = sorted(p for p in root.rglob("*" + SUFFIX))
    sig = tuple((str(p), p.stat().st_mtime_ns) for p in files)
    hit = _CACHE.get(root)
    if hit and hit[0] == sig:
        return hit[1]
    idx = Index(files)
    _CACHE[root] = (sig, idx)
    return idx


# ------------------------------------------------------------------ links and anchors
class Ctx:
    """Where we are rendering: the page that owns the fragment (for relative links), and the link style."""

    def __init__(self, page=None, base="/docs/", style="relative"):
        self.page, self.base, self.style = page, base, style


def _kebab(name):
    name = re.sub(r"Fields$", "", name)
    return re.sub(r"(?<!^)(?=[A-Z])", "-", name).lower()


def _slug(label):
    # python-markdown's toc slug for a heading like "`env-vars` schema" -> "env-vars-schema"; underscores are kept
    return re.sub(r"[^a-z0-9_]+", "-", label.lower()).strip("-")


def _anchor(idx, name):
    """Anchor of a def on its owning page: the docs' `<label>-schema` heading, unless x-anchor says otherwise
    ('' = link to the page without an anchor)."""
    d = idx.defs[name]
    if "x-anchor" in d:
        return d["x-anchor"] or None
    return _slug(d.get("x-type-label") or _kebab(name)) + "-schema"


def _href(page, ctx):
    if ctx.style == "relative" and ctx.page:
        if page == ctx.page:
            return ""  # same page: just the #anchor
        return posixpath.relpath(page, posixpath.dirname(ctx.page) or ".")
    p = re.sub(r"\.md$", "", re.sub(r"(^|/)index\.md$", "", page))
    return f"{ctx.base}{p}/" if p else ctx.base


def _link(idx, name, ctx):
    page = idx.owner.get(name)
    if not page or idx.defs[name].get("x-link") is False:  # x-link: false -> show the type name without a link
        return None
    anchor = _anchor(idx, name)
    return _href(page, ctx) + (f"#{anchor}" if anchor else "")


def _rel_links(text, ctx):
    """Links in x-type are stored relative to the docs root; make them relative to the page being rendered."""

    def sub(m):
        path, frag = m.group("path"), m.group("frag") or ""
        if path.endswith(".md"):  # keep the page path even for the current page: it is what the original wrote
            path = posixpath.relpath(path, posixpath.dirname(ctx.page) or ".") if ctx.page else path
        return f"]({path}{frag})"

    return LINK.sub(sub, text)


def _segments(node, idx, ctx):
    """A schema node's type as alternatives: [(label, link-or-None), ...]."""
    if "$ref" in node:
        name = node["$ref"].rsplit("/", 1)[-1]
        label = idx.defs.get(name, {}).get("x-type-label") or _kebab(name)
        return [(label, _link(idx, name, ctx))]
    if node.get("type") != "array" and "anyOf" not in node:  # a named inline sub-schema: link to its own heading
        inner = _inline_object(node)
        if inner and inner.get("x-type-label"):
            return [(inner["x-type-label"], f"#{_slug(inner['x-type-label'])}-schema")]
    if "enum" in node:
        return [(str(v), None) for v in node["enum"]]
    if "const" in node:
        return [(str(node["const"]), None)]
    if "anyOf" in node:
        segs = []
        for sub in node["anyOf"]:
            for s in _segments(sub, idx, ctx):
                if s not in segs and s[0] != "var":  # ((var)) alternatives are noise in the docs
                    segs.append(s)
        return segs
    t = node.get("type")
    if t == "array":
        inner = _segments(node.get("items", {}), idx, ctx)
        return [("[" + " | ".join(s[0] for s in inner) + "]", inner[0][1] if len(inner) == 1 else None)]
    if isinstance(t, list):
        t = next((x for x in t if x != "string"), t[0])
    return [({"integer": "number"}.get(t, t or "any"), None)]


def type_markdown(node, idx, ctx):
    """The type part of a field signature. x-type (raw text, set by the importer) wins over the derived one."""
    if node.get("x-type"):
        return _rel_links(node["x-type"], ctx)
    return " | ".join(f"[`{l}`]({u})" if u else f"`{l}`" for l, u in _segments(node, idx, ctx))


def _inline_object(node):
    """The object schema (with `properties`) inside a node: directly, under items/anyOf, or in an if/else."""
    if "properties" in node and "$ref" not in node:
        return node
    if node.get("type") == "array" and isinstance(node.get("items"), dict):
        return _inline_object(node["items"])
    for sub in node.get("anyOf", []):
        r = _inline_object(sub)
        if r:
            return r
    if isinstance(node.get("else"), dict):
        return _inline_object(node["else"])
    return None


# ------------------------------------------------------------------ rendering (Markdown out)
def _heading(level, text):
    return f"{'#' * level} {text}"


def render_markdown(idx, name, ctx, hide=(), node=None, only=None):
    """Render the fields of one object def (`only`: just these fields, in the schema's order). `node` lets file
    mode pass the def as the fence body supplied it."""
    d = node if node is not None else idx.defs[name]
    level = None if d.get("x-field-headings") is False else d.get("x-heading-level", HEADING_LEVEL)
    return "\n".join(_object_blocks(idx, d, ctx, tuple(hide), level, bool(d.get("x-open")), 0, only))


def _type_section(name, d):
    """A documented *type* (config-basics): `### `number` schema` + prose."""
    label = d.get("x-type-label") or name
    head = _heading(d.get("x-heading-level", HEADING_LEVEL), f"`{label}` schema")
    return f"{head}\n\n{(d.get('description') or '').strip()}\n"


def render_fragment(idx, frag, ctx):
    """File mode: the fence body is a whole fragment. Renders, in file order, every type def (x-doc-type) and every
    def that has fields, skipping `x-docs: false`. The first object def is the page's main schema (its heading is
    written by hand on the page); every other object def gets a `### `label` schema` section heading."""
    todo = [(n, d) for n, d in (frag.get("$defs") or {}).items()
            if d.get("x-docs", True) and (d.get("x-doc-type") or _inline_object(d))]
    out, seen_object = [], False
    for name, d in todo:
        if d.get("x-doc-type"):
            out.append(_type_section(name, d))
            continue
        if seen_object:
            label = d.get("x-type-label") or name
            out.append(_heading(d.get("x-heading-level", HEADING_LEVEL), f"`{label}` schema") + "\n")
        seen_object = True
        out.append(render_markdown(idx, name, ctx, (), node=d))
    return "\n".join(out)


def _object_blocks(idx, node, ctx, hide, level, open_, depth, only=None):
    obj = node if "properties" in node else (_inline_object(node) or {})
    required = set(obj.get("required", []))
    if node.get("x-step-key"):  # the key that selects a step type is required in practice
        required.add(node["x-step-key"])
    out, prev_group = [], None
    for prop, sub in (obj.get("properties") or {}).items():
        if prop in hide or sub.get("x-docs") is False or (only is not None and prop not in only):
            continue
        group = sub.get("x-group") if depth == 0 else None
        if group and group != prev_group:  # e.g. `### Job Hooks` above the five hooks
            out.append(_heading(group.get("level", HEADING_LEVEL), group["text"]) + "\n")
        prev_group = group
        out.append(_field_block(idx, prop, sub, prop in required, ctx, level, open_, depth))
    return out


def _field_block(idx, prop, sub, schema_required, ctx, level, open_, depth):
    """Only the primary schema's fields (depth 0) get a heading: it creates the #anchor, the TOC entry and the
    search hit. Nested fields, like in the hand-written pages, do not."""
    ref_def = idx.defs.get(sub["$ref"].rsplit("/", 1)[-1], {}) if "$ref" in sub else {}
    desc = (sub.get("description") or ref_def.get("description") or "").strip("\n")
    warn = sub.get("x-doc-required", schema_required)  # warning colour
    words = warn and sub.get("x-required-text", True)  # the literal "(required)"
    title = f"**`{prop}`**: {type_markdown(sub, idx, ctx)}" + (" (required)" if words else "")
    if sub.get("deprecated"):
        title += " *deprecated*"
    hl = sub.get("x-heading", level) if depth == 0 else None
    hl = None if hl is False else hl
    nested = _inline_object(sub)
    body = []
    if hl:
        body.append(_heading(hl, f"`{prop}`"))
    if desc:
        body.append(desc)
    if nested:
        if nested.get("x-type-label"):  # a named sub-schema, e.g. build_log_retention_policy
            sub_level = nested.get("x-heading-level", (hl + 1) if hl else HEADING_LEVEL)
            body.append(_heading(sub_level, f"`{nested['x-type-label']}` schema") + "\n")
        body += _object_blocks(idx, nested, ctx, (), None, sub.get("x-open", open_), depth + 1)
    if not body:
        return title + "\n"  # nothing to put in a box: plain line, not an empty admonition
    opener = f"{'???+' if sub.get('x-open', open_) else '???'} {'warning' if warn else 'info'}"
    inner = textwrap.indent("\n\n".join(body), "    ")
    return f'{opener} "{title.replace(chr(34), "&quot;")}"\n\n{inner}\n'


# ------------------------------------------------------------------ the extension
class SchemaFencePreprocessor(Preprocessor):
    def __init__(self, md, config):
        super().__init__(md)
        self.config = config

    def run(self, lines):
        text = "\n".join(lines)

        def replace_fence(match):
            indent, body = match.group(1), match.group(2)
            body = "\n".join(ln[len(indent):] if ln.startswith(indent) else ln.lstrip() for ln in body.split("\n"))
            spec = yaml.safe_load(body)
            if not isinstance(spec, dict):
                hint = (" (a `--8<--` line was not expanded: enable pymdownx.snippets, and keep this extension "
                        "at a lower priority than snippets=32)" if "--8<--" in body else "")
                raise ValueError("concourse-schema fence: body must be a mapping, either "
                                 "a def reference (def: name) or a whole schema fragment; "
                                 f"got {body[:60]!r}{hint}")
            idx = load_index(self.config["docs_root"] or None)
            if "$defs" in spec:  # file mode: body is a whole fragment, e.g. embedded via --8<--
                ctx = Ctx(spec.get("x-page"), self.config["base_url"], self.config["link_style"])
                out = render_fragment(idx, spec, ctx)
            else:
                if spec.get("def") not in idx.defs:
                    raise ValueError(f"concourse-schema fence: unknown def {spec.get('def')!r}")
                # the fence sits on the page that owns the def (tools/build_schema.py --check-links enforces it)
                ctx = Ctx(idx.owner.get(spec["def"]), self.config["base_url"], self.config["link_style"])
                out = render_markdown(idx, spec["def"], ctx, spec.get("hide", ()), only=spec.get("only"))
            return textwrap.indent(out.rstrip("\n"), indent) if indent else out.rstrip("\n")

        return FENCE_PATTERN.sub(replace_fence, text).split("\n")


class SchemaFenceExtension(Extension):
    def __init__(self, **kwargs):
        self.config = {
            "docs_root": ["",
                          f"Directory holding *.schema.yml fragments (default: $CONCOURSE_DOCS_ROOT or {DEFAULT_ROOT})"],
            "link_style": ["relative", "'relative' (../config-basics.md#x, validated by the site build) or 'absolute'"],
            "base_url": ["/docs/", "URL prefix for link_style=absolute"],
        }
        super().__init__(**kwargs)

    def extendMarkdown(self, md):
        config = {k: self.getConfig(k) for k in self.config}
        # pymdownx.snippets runs at 32 and must expand `--8<--` BEFORE we read the fence body,
        # so we sit just below it (and above normalize_whitespace=30 / fenced code=25).
        md.preprocessors.register(SchemaFencePreprocessor(md, config), "schema_fence", 31)


def makeExtension(**kwargs):
    return SchemaFenceExtension(**kwargs)
