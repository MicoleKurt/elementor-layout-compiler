"""Compile a validated layout manifest into Elementor container JSON.

The language model never writes Elementor JSON. It emits a small manifest
(``layout_manifest.schema.json``); this module turns that manifest into the
``_elementor_data`` tree using the *locked* design tokens, with deterministic
ids, so output is reproducible and always passes ``validator.assert_valid``.
"""

from __future__ import annotations

import html
from typing import Any

from .ids import element_id, repeater_id
from .schema import validate_manifest
from .tokens import verify_locked
from .validator import assert_valid

# --------------------------------------------------------------------------- helpers


def _num(value: float) -> int | float:
    """Whole numbers as ints, the way Elementor saves slider sizes (``48``, not ``48.0``)."""
    rounded = round(value, 3)
    return int(rounded) if float(rounded).is_integer() else rounded


def _px(size: float) -> dict[str, Any]:
    return {"unit": "px", "size": _num(size), "sizes": []}


def _percent(size: float) -> dict[str, Any]:
    return {"unit": "%", "size": _num(size), "sizes": []}


def _dims(top: int, right: int, bottom: int, left: int, linked: bool = False) -> dict[str, Any]:
    return {"unit": "px", "top": str(top), "right": str(right), "bottom": str(bottom), "left": str(left), "isLinked": linked}


def _radius(value: int) -> dict[str, Any]:
    return _dims(value, value, value, value, True)


def _gap(value: int) -> dict[str, Any]:
    return {"column": str(value), "row": str(value), "isLinked": True, "unit": "px", "size": value}


def _luminance(hex_color: str) -> float:
    channels = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast_ratio(a: str, b: str) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def readable_on(background: str, light: str, dark: str) -> str:
    """Whichever of ``light`` or ``dark`` has the higher WCAG contrast on ``background``."""
    return light if contrast_ratio(background, light) >= contrast_ratio(background, dark) else dark


def _paragraphs(text: str) -> str:
    """Plain text to safe HTML paragraphs. Model output is escaped, never trusted as markup."""
    blocks = [b.strip() for b in text.replace("\r\n", "\n").split("\n\n") if b.strip()]
    return "".join(f"<p>{html.escape(b, quote=False)}</p>" for b in blocks) or "<p></p>"


# --------------------------------------------------------------------------- compiler


class LayoutCompiler:
    """One instance compiles one page against one set of locked tokens."""

    def __init__(self, locked_tokens: dict[str, Any], page_slug: str):
        self.tokens = verify_locked(locked_tokens)
        self.slug = page_slug
        self.colors = self.tokens["colors"]
        self.type = self.tokens["typography"]
        self.space = self.tokens["spacing"]
        self.radii = self.tokens["radii"]
        self.buttons = self.tokens["buttons"]

    # -- element constructors ------------------------------------------------
    def _node(self, path: str, el_type: str, settings: dict[str, Any] | list, elements: list[dict[str, Any]],
              *, inner: bool, widget: str | None = None) -> dict[str, Any]:
        node: dict[str, Any] = {"id": element_id(self.slug, path), "elType": el_type}
        if widget:
            node["widgetType"] = widget
        node.update({"isInner": inner, "settings": settings, "elements": elements})
        return node

    def _container(self, path: str, children: list[dict[str, Any]], *, inner: bool, **settings: Any) -> dict[str, Any]:
        return self._node(path, "container", settings, children, inner=inner)

    def _widget(self, path: str, widget: str, settings: dict[str, Any]) -> dict[str, Any]:
        return self._node(path, "widget", settings, [], inner=False, widget=widget)

    def _font(self, role: str, size: int, color: str) -> dict[str, Any]:
        family = self.type["heading_font"] if role == "heading" else self.type["body_font"]
        weight = self.type["heading_weight"] if role == "heading" else self.type["body_weight"]
        return {
            "typography_typography": "custom",
            "typography_font_family": family,
            "typography_font_size": _px(size),
            "typography_font_weight": str(weight),
            "typography_line_height": {"unit": "em", "size": self.type["line_height"], "sizes": []},
        }

    # -- widgets ---------------------------------------------------------------
    def heading(self, path: str, text: str, level: int, color: str, align: str = "left") -> dict[str, Any]:
        size = self.type["scale"][f"h{level}"]
        return self._widget(path, "heading", {
            "title": html.escape(text, quote=False), "header_size": f"h{level}", "align": align,
            "title_color": color, **self._font("heading", size, color),
        })

    def paragraph(self, path: str, text: str, color: str, align: str = "left") -> dict[str, Any]:
        return self._widget(path, "text-editor", {
            "editor": _paragraphs(text), "align": align, "text_color": color,
            **self._font("body", self.type["scale"]["body"], color),
        })

    def button(self, path: str, label: str, url: str, background: str, text_color: str, align: str = "left") -> dict[str, Any]:
        solid = self.buttons["style"] == "solid"
        settings: dict[str, Any] = {
            "text": label.upper() if self.buttons["uppercase"] else label,
            "link": {"url": url, "is_external": "", "nofollow": "", "custom_attributes": ""},
            "align": align,
            "button_text_color": text_color if solid else background,
            "background_color": background if solid else "",
            "border_border": "solid" if not solid else "",
            "border_color": background,
            "border_radius": _radius(self.radii["button"]),
            "text_padding": _dims(14, 28, 14, 28),
            **self._font("heading", self.type["scale"]["body"], text_color),
        }
        return self._widget(path, "button", {k: v for k, v in settings.items() if v != ""})

    def image(self, path: str, url: str, alt: str) -> dict[str, Any]:
        return self._widget(path, "image", {
            "image": {"url": url, "id": "", "alt": alt, "source": "external"},
            "image_size": "full",
            "image_border_radius": _radius(self.radii["image"]),
        })

    # -- section scaffolding -----------------------------------------------------
    def _section(self, index: int, background: str, children: list[dict[str, Any]], *, direction: str = "column",
                 align: str = "stretch") -> dict[str, Any]:
        """Full-width outer container that holds a boxed inner container."""
        pad_y, gutter = self.space["section_padding_y"], self.space["gutter"]
        inner = self._container(
            f"{index}.0", children, inner=True,
            content_width="boxed", boxed_width=_px(self.space["container_max_width"]),
            flex_direction=direction, flex_gap=_gap(self.space["gap"]), flex_align_items=align,
        )
        return self._container(
            f"{index}", [inner], inner=False,
            content_width="full", flex_direction="column",
            padding=_dims(pad_y, gutter, pad_y, gutter),
            background_background="classic", background_color=background,
        )

    def _card(self, path: str, children: list[dict[str, Any]], width: float) -> dict[str, Any]:
        return self._container(
            path, children, inner=True,
            content_width="full", width=_percent(width), flex_direction="column", flex_gap=_gap(max(8, self.space["gap"] // 2)),
            padding=_dims(24, 24, 24, 24, True),
            background_background="classic", background_color=self.colors["surface"],
            border_radius=_radius(self.radii["container"]),
        )

    def _on(self, background: str) -> str:
        return readable_on(background, self.colors["background"], self.colors["text"])

    # -- section builders ------------------------------------------------------------
    def hero(self, i: int, s: dict[str, Any]) -> dict[str, Any]:
        bg = self.colors["surface"]
        ink, muted = self._on(bg), self.colors["text_muted"]
        kids = [self.heading(f"{i}.0.0", s["heading"], 1, ink)]
        if s.get("subheading"):
            kids.append(self.paragraph(f"{i}.0.1", s["subheading"], muted))
        kids.append(self.button(f"{i}.0.2", s["cta"]["label"], s["cta"]["url"], self.colors["primary"], self._on(self.colors["primary"])))
        if s.get("image"):
            kids.append(self.image(f"{i}.0.3", s["image"]["url"], s["image"]["alt"]))
        return self._section(i, bg, kids)

    def feature_grid(self, i: int, s: dict[str, Any]) -> dict[str, Any]:
        bg, ink = self.colors["background"], self._on(self.colors["background"])
        cols = s["columns"]
        width = 100 / cols - (self.space["gap"] / 12)
        cards = [
            self._card(f"{i}.0.1.{n}", [
                self.heading(f"{i}.0.1.{n}.0", item["title"], 3, self._on(self.colors["surface"])),
                self.paragraph(f"{i}.0.1.{n}.1", item["text"], self.colors["text_muted"]),
            ], width)
            for n, item in enumerate(s["items"])
        ]
        grid = self._container(f"{i}.0.1", cards, inner=True, content_width="full", flex_direction="row",
                               flex_wrap="wrap", flex_gap=_gap(self.space["gap"]))
        return self._section(i, bg, [self.heading(f"{i}.0.0", s["heading"], 2, ink), grid])

    def text_image(self, i: int, s: dict[str, Any]) -> dict[str, Any]:
        bg, ink = self.colors["background"], self._on(self.colors["background"])
        text_col = self._container(f"{i}.0.0", [
            self.heading(f"{i}.0.0.0", s["heading"], 2, ink),
            self.paragraph(f"{i}.0.0.1", s["body"], self.colors["text_muted"]),
        ], inner=True, content_width="full", width=_percent(50), flex_direction="column", flex_gap=_gap(self.space["gap"]))
        image_col = self._container(f"{i}.0.1", [self.image(f"{i}.0.1.0", s["image"]["url"], s["image"]["alt"])],
                                    inner=True, content_width="full", width=_percent(50), flex_direction="column")
        direction = "row-reverse" if s.get("image_side") == "left" else "row"
        return self._section(i, bg, [text_col, image_col], direction=direction, align="center")

    def cta_band(self, i: int, s: dict[str, Any]) -> dict[str, Any]:
        bg = self.colors["primary"]
        ink = self._on(bg)
        kids = [
            self.heading(f"{i}.0.0", s["heading"], 2, ink, "center"),
            self.button(f"{i}.0.1", s["cta"]["label"], s["cta"]["url"], self.colors["background"], self._on(self.colors["background"]), "center"),
        ]
        return self._section(i, bg, kids, align="center")

    def testimonials(self, i: int, s: dict[str, Any]) -> dict[str, Any]:
        bg, ink = self.colors["background"], self._on(self.colors["background"])
        items = s["items"]
        width = 100 / min(len(items), 3) - (self.space["gap"] / 12)
        cards = [
            self._card(f"{i}.0.{1 if s.get('heading') else 0}.{n}", [
                self.paragraph(f"{i}.0.{1 if s.get('heading') else 0}.{n}.0", f"“{it['quote']}”", self._on(self.colors["surface"])),
                self.heading(f"{i}.0.{1 if s.get('heading') else 0}.{n}.1", it["author"], 4, self.colors["text_muted"]),
            ], width)
            for n, it in enumerate(items)
        ]
        grid_idx = 1 if s.get("heading") else 0
        grid = self._container(f"{i}.0.{grid_idx}", cards, inner=True, content_width="full", flex_direction="row",
                               flex_wrap="wrap", flex_gap=_gap(self.space["gap"]))
        kids = ([self.heading(f"{i}.0.0", s["heading"], 2, ink)] if s.get("heading") else []) + [grid]
        return self._section(i, bg, kids)

    def faq(self, i: int, s: dict[str, Any]) -> dict[str, Any]:
        bg, ink = self.colors["background"], self._on(self.colors["background"])
        tabs = [
            {"_id": repeater_id(self.slug, f"{i}.0.1.{n}"), "tab_title": html.escape(it["q"], quote=False), "tab_content": _paragraphs(it["a"])}
            for n, it in enumerate(s["items"])
        ]
        accordion = self._widget(f"{i}.0.1", "accordion", {
            "tabs": tabs, "title_color": ink, "tab_active_color": self.colors["primary"], "content_color": self.colors["text_muted"],
            **{k: v for k, v in self._font("heading", self.type["scale"]["h4"], ink).items() if k.startswith("title_")},
        })
        return self._section(i, bg, [self.heading(f"{i}.0.0", s["heading"], 2, ink), accordion])

    # -- entry point ---------------------------------------------------------------------
    def compile(self, manifest: dict[str, Any]) -> list[dict[str, Any]]:
        validate_manifest(manifest)
        if manifest["page"]["slug"] != self.slug:
            raise ValueError(f"manifest slug {manifest['page']['slug']!r} does not match compiler slug {self.slug!r}")
        builders = {"hero": self.hero, "feature_grid": self.feature_grid, "text_image": self.text_image,
                    "cta_band": self.cta_band, "testimonials": self.testimonials, "faq": self.faq}
        tree = [builders[section["type"]](index, section) for index, section in enumerate(manifest["sections"])]
        assert_valid(tree)
        return tree


def compile_manifest(manifest: dict[str, Any], locked_tokens: dict[str, Any]) -> list[dict[str, Any]]:
    """Convenience wrapper: compile ``manifest`` against ``locked_tokens``."""
    return LayoutCompiler(locked_tokens, manifest["page"]["slug"]).compile(manifest)
