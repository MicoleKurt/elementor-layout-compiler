# Elementor keys used, and where they come from

Verify against your Elementor version before production: in the editor, save a container with
the settings you want as a template, export the JSON, and diff its keys against the tables below.
The tests in `tests/test_compiler.py` pin these names, so a correction is a small change.

## Structural keys (documented)

Source: Elementor developer documentation, *Data Structure* (General Elements, Container Element,
Widget Element, Page Content).

| Key | Meaning |
|---|---|
| `id` | Unique element id, shown in the docs as 8 hex characters |
| `elType` | `container` or `widget` (legacy: `section`, `column`) |
| `widgetType` | Present on widgets only (`heading`, `image`, `button`, ...) |
| `isInner` | Whether the element is an inner element |
| `settings` | Control values; an empty array when there are none |
| `elements` | Nested elements |

The wrapper used in exported files is `{ "title", "type", "version", "page_settings", "content" }`;
`content` is the same element tree that WordPress stores in the `_elementor_data` post meta.

## Container settings (export conventions)

`content_width` (`boxed`/`full`), `boxed_width`, `flex_direction`, `flex_wrap`, `flex_gap`,
`flex_align_items`, `width`, `padding`, `background_background`, `background_color`, `border_radius`.
Dimension values use `{unit, top, right, bottom, left, isLinked}`; sizes use `{unit, size, sizes}`.

## Widget settings (export conventions)

| Widget | Keys used |
|---|---|
| `heading` | `title`, `header_size`, `align`, `title_color`, `typography_*` |
| `text-editor` | `editor`, `align`, `text_color`, `typography_*` |
| `button` | `text`, `link {url, is_external, nofollow, custom_attributes}`, `align`, `button_text_color`, `background_color`, `border_border`, `border_color`, `border_radius`, `text_padding`, `typography_*` |
| `image` | `image {url, id, alt, source}`, `image_size`, `image_border_radius` |
| `accordion` | `tabs` repeater of `{_id, tab_title, tab_content}`, `title_color`, `tab_active_color`, `content_color` |

## Post meta written by the companion plugin

`_elementor_data` (JSON, slashed), `_elementor_edit_mode = builder`, `_elementor_template_type = wp-page`,
`_wp_page_template`. See `wp-staging-bridge`.
