"""mkdocs_schema_fence: expand a ```concourse-schema fence into the docs' field reference.

Self-contained on purpose (same shape as mkdocs_metrics_fence): this file imports only the standard library
and `markdown`. PyYAML is imported lazily and only if a *.schema.yml fragment or a YAML fence body is used.
It does NOT share code with tools/build_schema.py; tests/check_loader_parity.py keeps the two loaders honest.

Usage in a page (the fragment is embedded by pymdownx.snippets, which runs first):

    ```concourse-schema
    --8<-- "steps/get.schema.yml"
    ```

or render a single def:   {"def": "getFields", "hide": ["no_get"]}   (JSON, or YAML `def: getFields`)

What is generated, matching the hand-written pages it replaces:

  * every field of an object def:   ???+ warning|info "**`name`**: [`type`](link) (required)"
                                        ### `name`          <- the heading gives the #name anchor, TOC and search hit
                                        prose...
    (required fields use `warning`, others `info`; nested fields get no heading, like the original pages)
  * every *type* def (`x-doc-type`):  ### `number` schema   <- anchor #number-schema, as config-basics.md uses
                                      prose...
  * a def that is not the page's first object def gets a  ### `label` schema  section heading
  * type links are RELATIVE .md links with anchors (../config-basics.md#identifier-schema), computed from the page
    that owns the fragment (`x-page`), so the site build validates them like any other link.

mkdocs.yml:
    - pymdownx.snippets: {base_path: [docs/assets/schema, docs], check_paths: true}
    - mkdocs_schema_fence.extension: {docs_root: docs/assets/schema}

Fragment keys read here (all `x-*`): x-page, x-type-label, x-anchor, x-since, x-docs, x-step-key,
x-doc-type, x-field-headings, x-heading-level, x-link
x-type-label / x-type-link on a FIELD override how its type is shown (passed -> [job.name] linking jobs.md#name);
on an inline object it also adds a `### label schema` sub-heading, e.g. build_log_retention_policy.
"""
import json
import os
import posixpath
import pathlib
import re
import textwrap

from markdown.extensions import Extension
from markdown.preprocessors import Preprocessor

FENCE_PATTERN = re.compile(r"```concourse-schema\n(.*?)\n```", re.DOTALL)
DEFAULT_ROOT = "docs/assets/schema"
SUFFIXES = (".schema.json", ".schema.yml", ".schema.yaml")
# (every field, required field): required fields use a different admonition type to stay visually distinct
ADMONITIONS = ("??? info", "??? warning")
HEADING_LEVEL = 3  # level of field headings and section headings unless a def sets x-heading-level


# ------------------------------------------------------------------ loading fragments
def _yaml():
    try:
        import yaml  # lazy: JSON-only setups never import it
    except ImportError as e:
        raise ImportError(
            "PyYAML is required to read *.schema.yml fragments or YAML fence bodies. "
            "Zensical/MkDocs already depend on it; otherwise `pip install pyyaml`, or use *.schema.json fragments."
        ) from e
    return yaml


def parse_text(text):
    """JSON first (stdlib); YAML as the fallback, since JSON is a subset of YAML."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return _yaml().safe_load(text)


def _load_fragment(path):
    text = path.read_text(encoding="utf-8")
    return json.loads(text) if path.name.endswith(".schema.json") else _yaml().safe_load(text)


class Index:
    """All defs across all fragments, and which docs page owns each (used to link types)."""

    def __init__(self, files):
        self.defs, self.owner, stems = {}, {}, {}
        for p in files:
            stem = str(p.with_name(p.name.split(".schema.")[0]))
            if stem in stems:
                raise ValueError(f"{p.name} and {stems[stem].name} are the same fragment in two formats; keep one")
            stems[stem] = p
            frag = _load_fragment(p)
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
    files = sorted(p for p in root.rglob("*.schema.*") if p.name.endswith(SUFFIXES))
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


def _text(value):
    """`description` may be a string or a list of lines (list form keeps JSON prose readable)."""
    return "\n".join(value) if isinstance(value, list) else (value or "")


def _kebab(name):
    name = re.sub(r"Fields$", "", name)
    return re.sub(r"(?<!^)(?=[A-Z])", "-", name).lower()


def _slug(label):
    # python-markdown's toc slug for a heading like "`env-vars` schema" -> "env-vars-schema"; underscores are kept
    return re.sub(r"[^a-z0-9_]+", "-", label.lower()).strip("-")


def _anchor(idx, name):
    """Anchor of a def on its owning page: the docs' own `<label>-schema` heading, unless x-anchor says otherwise
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


def _segments(node, idx, ctx):
    """A schema node's type as alternatives: [(label, link-or-None), ...]."""
    label = node.get("x-type-label")
    if label:  # per-field override, e.g. `passed` is "[job.name]" in the docs, not "[string]"
        if node.get("x-type-link"):  # "jobs.md#name": relative to the page being rendered, like every other link
            page, _, anchor = node["x-type-link"].partition("#")
            return [(label, _href(page, ctx) + (f"#{anchor}" if anchor else ""))]
        return [(label, f"#{_slug(label)}-schema" if "properties" in node else None)]  # named sub-schema: same page
    if "$ref" in node:
        name = node["$ref"].rsplit("/", 1)[-1]
        label = idx.defs.get(name, {}).get("x-type-label") or _kebab(name)
        return [(label, _link(idx, name, ctx))]
    if "enum" in node:
        return [(" | ".join(str(v) for v in node["enum"]), None)]
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


def render_markdown(idx, name, ctx, hide=(), admonition=ADMONITIONS, node=None):
    """Render the fields of one object def. `node` lets file mode pass the def as the fence body supplied it."""
    d = node if node is not None else idx.defs[name]
    level = d.get("x-heading-level", HEADING_LEVEL) if d.get("x-field-headings", True) else None
    return "\n".join(_object_blocks(idx, d, ctx, tuple(hide), admonition, level))


def _type_section(name, d):
    """A documented *type* (config-basics): `### `number` schema` + prose."""
    label = d.get("x-type-label") or name
    head = _heading(d.get("x-heading-level", HEADING_LEVEL), f"`{label}` schema")
    return f"{head}\n\n{_text(d.get('description')).strip()}\n"


def render_fragment(idx, frag, ctx, admonition=ADMONITIONS):
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
        out.append(render_markdown(idx, name, ctx, (), admonition, node=d))
    return "\n".join(out)


def _object_blocks(idx, node, ctx, hide, adm, heading_level):
    obj = node if "properties" in node else (_inline_object(node) or {})
    required = set(obj.get("required", []))
    if node.get("x-step-key"):  # the key that selects a step type is required in practice
        required.add(node["x-step-key"])
    return [
        _field_block(idx, prop, sub, prop in required, ctx, adm, heading_level)
        for prop, sub in (obj.get("properties") or {}).items()
        if prop not in hide
    ]


def _field_block(idx, prop, sub, required, ctx, adm, heading_level):
    """heading_level is None for nested fields: like the original pages, only the primary schema's fields get
    a heading (that heading is what creates the #anchor, the TOC entry and the search result)."""
    ref_def = idx.defs.get(sub["$ref"].rsplit("/", 1)[-1], {}) if "$ref" in sub else {}
    desc = _text(sub.get("description") or ref_def.get("description")).strip()
    since = sub.get("x-since") or ref_def.get("x-since")
    types = " | ".join(f"[`{l}`]({u})" if u else f"`{l}`" for l, u in _segments(sub, idx, ctx))
    title = f"**`{prop}`**: {types}"
    if required:
        title += " (required)"
    if since:
        title += f" *since {since}*"
    if sub.get("deprecated"):
        title += " *deprecated*"
    nested = _inline_object(sub)
    nested_blocks = _object_blocks(idx, nested, ctx, (), adm, None) if nested else []
    if nested and nested.get("x-type-label"):  # a named sub-schema, e.g. build_log_retention_policy
        level = nested.get("x-heading-level", HEADING_LEVEL + 1)
        nested_blocks.insert(0, _heading(level, f"`{nested['x-type-label']}` schema") + "\n")
    body = ([_heading(heading_level, f"`{prop}`")] if heading_level else []) + ([desc] if desc else []) + nested_blocks
    if not body:
        return title + "\n"  # nothing to put in a box: plain line, not an empty admonition
    opener = adm[1] if required else adm[0]
    inner = textwrap.indent("\n\n".join(body), "    ")
    return f'{opener} "{title.replace(chr(34), "&quot;")}"\n{inner}\n'


# ------------------------------------------------------------------ the extension
class SchemaFencePreprocessor(Preprocessor):
    def __init__(self, md, config):
        super().__init__(md)
        self.config = config

    def _adm(self):
        return (self.config["admonition"], self.config["admonition_required"])

    def run(self, lines):
        text = "\n".join(lines)

        def replace_with_admonitions(match):
            spec = parse_text(match.group(1))  # JSON body, or YAML body when PyYAML is available
            if not isinstance(spec, dict):
                hint = (" (a `--8<--` line was not expanded: enable pymdownx.snippets, and keep this extension "
                        "at a lower priority than snippets=32)" if "--8<--" in match.group(1) else "")
                raise ValueError("concourse-schema fence: body must be a mapping, either "
                                 "a def reference (def: name) or a whole schema fragment; "
                                 f"got {match.group(1)[:60]!r}{hint}")
            idx = load_index(self.config["docs_root"] or None)
            if "$defs" in spec:  # file mode: body is a whole fragment, e.g. embedded via --8<--
                ctx = Ctx(spec.get("x-page"), self.config["base_url"], self.config["link_style"])
                return render_fragment(idx, spec, ctx, self._adm())
            if spec.get("def") not in idx.defs:
                raise ValueError(f"concourse-schema fence: unknown def {spec.get('def')!r}")
            # the fence sits on the page that owns the def (tools/build_schema.py --check-links enforces it)
            ctx = Ctx(idx.owner.get(spec["def"]), self.config["base_url"], self.config["link_style"])
            return render_markdown(idx, spec["def"], ctx, spec.get("hide", ()), self._adm())

        text = FENCE_PATTERN.sub(replace_with_admonitions, text)
        return text.split("\n")


class SchemaFenceExtension(Extension):
    def __init__(self, **kwargs):
        self.config = {
            "docs_root": ["",
                          f"Directory holding *.schema.* fragments (default: $CONCOURSE_DOCS_ROOT or {DEFAULT_ROOT})"],
            "link_style": ["relative", "'relative' (../config-basics.md#x, validated by the site build) or 'absolute'"],
            "base_url": ["/docs/", "URL prefix for link_style=absolute"],
            "admonition": ["??? info", "Admonition opener for every field, same style the metrics fence uses"],
            "admonition_required": ["??? warning", "Admonition opener for required fields (visual separation)"],
        }
        super().__init__(**kwargs)

    def extendMarkdown(self, md):
        config = {k: self.getConfig(k) for k in self.config}
        # pymdownx.snippets runs at 32 and must expand `--8<--` BEFORE we read the fence body,
        # so we sit just below it (and above normalize_whitespace=30 / fenced code=25).
        md.preprocessors.register(SchemaFencePreprocessor(md, config), "schema_fence", 31)


def makeExtension(**kwargs):
    return SchemaFenceExtension(**kwargs)
