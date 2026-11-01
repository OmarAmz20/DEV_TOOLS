//! PyO3 bindings for Aura Studio's Rust core.

use ::aura_core::{color as colours, palette as engine};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyAny, PyDict, PyList, PyModule};
use std::collections::BTreeMap;

const ANSI_NAMES: [&str; 6] = ["red", "green", "yellow", "blue", "magenta", "cyan"];

#[pyfunction]
fn parse_hex(value: &str) -> Option<(f64, f64, f64)> {
    colours::parse_hex(value)
}

#[pyfunction]
fn is_hex(value: &str) -> bool {
    colours::is_hex(value)
}

#[pyfunction]
fn rgb_hex(rgb: (f64, f64, f64)) -> String {
    colours::rgb_hex(rgb)
}

#[pyfunction]
fn rgba_hex(rgb: (f64, f64, f64), alpha: f64) -> String {
    colours::rgba_hex(rgb, alpha)
}

#[pyfunction]
fn rgba_css(hexcolor: &str, alpha: f64) -> String {
    colours::rgba_css(hexcolor, alpha)
}

#[pyfunction]
fn rgb_to_oklab(rgb: (f64, f64, f64)) -> (f64, f64, f64) {
    colours::rgb_to_oklab(rgb)
}

#[pyfunction]
#[pyo3(signature = (lab, clamp=true))]
fn oklab_to_rgb(lab: (f64, f64, f64), clamp: bool) -> (f64, f64, f64) {
    colours::oklab_to_rgb(lab, clamp)
}

#[pyfunction]
fn oklab_to_oklch(lab: (f64, f64, f64)) -> (f64, f64, f64) {
    colours::oklab_to_oklch(lab)
}

#[pyfunction]
fn oklch_to_oklab(lch: (f64, f64, f64)) -> (f64, f64, f64) {
    colours::oklch_to_oklab(lch)
}

#[pyfunction]
fn rgb_to_oklch(rgb: (f64, f64, f64)) -> (f64, f64, f64) {
    colours::rgb_to_oklch(rgb)
}

#[pyfunction]
fn hex_to_oklch(hexcolor: &str) -> Option<(f64, f64, f64)> {
    colours::hex_to_oklch(hexcolor)
}

#[pyfunction]
fn oklch_rgb(l: f64, c: f64, h: f64) -> (f64, f64, f64) {
    colours::oklch_rgb((l, c, h))
}

#[pyfunction]
fn oklch_hex(l: f64, c: f64, h: f64) -> String {
    colours::oklch_hex(l, c, h)
}

#[pyfunction]
fn hex_to_lch(hexcolor: &str) -> (f64, f64, f64) {
    colours::hex_to_lch(hexcolor)
}

#[pyfunction]
fn luminance(hexcolor: &str) -> f64 {
    colours::luminance(hexcolor)
}

#[pyfunction]
fn contrast(one: &str, two: &str) -> f64 {
    colours::contrast(one, two)
}

#[pyfunction]
fn best_on(background: &str, candidates: Vec<String>) -> String {
    colours::best_on(background, &candidates)
}

#[pyfunction]
fn contrast_label(value: f64) -> &'static str {
    colours::contrast_label(value)
}

#[pyfunction]
#[pyo3(signature = (l, c, h, against, target, prefer=None))]
fn adjust_for_contrast(
    l: f64,
    c: f64,
    h: f64,
    against: &str,
    target: f64,
    prefer: Option<String>,
) -> (String, f64) {
    colours::adjust_for_contrast(l, c, h, against, target, prefer.as_deref())
}

#[pyfunction]
fn tint(lightness: f64, chroma: f64, hue: f64) -> String {
    colours::tint(lightness, chroma, hue)
}

#[pyfunction]
fn hue_distance(one: f64, two: f64) -> f64 {
    colours::hue_distance(one, two)
}

#[pyfunction]
#[pyo3(signature = (hues, weights=None))]
fn circular_mean(hues: Vec<f64>, weights: Option<Vec<f64>>) -> f64 {
    colours::circular_mean(&hues, weights.as_deref())
}

fn required_string(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<String> {
    dict.get_item(key)?
        .ok_or_else(|| PyValueError::new_err(format!("missing palette key: {key}")))?
        .extract::<String>()
}

fn mode_from_py(value: &Bound<'_, PyAny>) -> PyResult<engine::ModePalette> {
    let dict = value.downcast::<PyDict>()?;
    let ansi = dict
        .get_item("ansi")?
        .ok_or_else(|| PyValueError::new_err("missing palette key: ansi"))?
        .extract::<Vec<String>>()?;
    Ok(engine::ModePalette {
        paper: required_string(dict, "paper")?,
        paper2: required_string(dict, "paper2")?,
        sheet: required_string(dict, "sheet")?,
        ink: required_string(dict, "ink")?,
        muted: required_string(dict, "muted")?,
        accent: required_string(dict, "accent")?,
        accent_text: required_string(dict, "accent_text")?,
        on_accent: required_string(dict, "on_accent")?,
        ansi,
    })
}

fn modes_from_py(value: &Bound<'_, PyAny>) -> PyResult<(engine::ModePalette, engine::ModePalette)> {
    let dict = value.downcast::<PyDict>()?;
    let light = dict
        .get_item("light")?
        .ok_or_else(|| PyValueError::new_err("palette has no light mode"))?;
    let dark = dict
        .get_item("dark")?
        .ok_or_else(|| PyValueError::new_err("palette has no dark mode"))?;
    Ok((mode_from_py(&light)?, mode_from_py(&dark)?))
}

fn mode_to_py(py: Python<'_>, mode: &engine::ModePalette) -> PyResult<Py<PyAny>> {
    let dict = PyDict::new(py);
    dict.set_item("paper", &mode.paper)?;
    dict.set_item("paper2", &mode.paper2)?;
    dict.set_item("sheet", &mode.sheet)?;
    dict.set_item("ink", &mode.ink)?;
    dict.set_item("muted", &mode.muted)?;
    dict.set_item("accent", &mode.accent)?;
    dict.set_item("accent_text", &mode.accent_text)?;
    dict.set_item("on_accent", &mode.on_accent)?;
    dict.set_item("ansi", PyList::new(py, &mode.ansi)?)?;
    Ok(dict.into_any().unbind())
}

fn palette_to_py(py: Python<'_>, palette: &engine::Palette) -> PyResult<Py<PyAny>> {
    let dict = PyDict::new(py);
    dict.set_item("light", mode_to_py(py, &palette.light)?)?;
    dict.set_item("dark", mode_to_py(py, &palette.dark)?)?;
    let meta = PyDict::new(py);
    meta.set_item("cast_hue", palette.meta.cast_hue)?;
    meta.set_item("cast_chroma", palette.meta.cast_chroma)?;
    meta.set_item("coloured_share", palette.meta.coloured_share)?;
    meta.set_item("accent_hue", palette.meta.accent_hue)?;
    meta.set_item("accent_chroma", palette.meta.accent_chroma)?;
    meta.set_item("mono", palette.meta.mono)?;
    meta.set_item("style", &palette.meta.style)?;
    meta.set_item("custom_accent", palette.meta.custom_accent)?;
    meta.set_item("clusters", palette.meta.clusters)?;
    dict.set_item("meta", meta)?;
    Ok(dict.into_any().unbind())
}

fn contrast_to_py(
    py: Python<'_>,
    light: &engine::ModePalette,
    dark: &engine::ModePalette,
) -> PyResult<Py<PyAny>> {
    let report = PyDict::new(py);
    for (name, mode) in [("light", light), ("dark", dark)] {
        let (body, accent) = engine::contrast_pair(mode);
        let entry = PyDict::new(py);
        entry.set_item("body", body)?;
        entry.set_item("accent", accent)?;
        report.set_item(name, entry)?;
    }
    Ok(report.into_any().unbind())
}

#[pyfunction]
#[pyo3(signature = (path, style="balanced", accent=None))]
fn palette_from_image(
    py: Python<'_>,
    path: &str,
    style: &str,
    accent: Option<&str>,
) -> PyResult<Py<PyAny>> {
    let palette = engine::from_image(path, style, accent).map_err(PyValueError::new_err)?;
    palette_to_py(py, &palette)
}

#[pyfunction]
#[pyo3(signature = (samples, style="balanced", accent=None))]
fn palette_from_samples(
    py: Python<'_>,
    samples: Vec<(f64, f64, f64)>,
    style: &str,
    accent: Option<&str>,
) -> PyResult<Py<PyAny>> {
    let palette = engine::build(&samples, style, accent).map_err(PyValueError::new_err)?;
    palette_to_py(py, &palette)
}

#[pyfunction]
fn valid_mode(value: &Bound<'_, PyAny>) -> bool {
    mode_from_py(value)
        .map(|mode| engine::valid_mode(&mode))
        .unwrap_or(false)
}

#[pyfunction]
fn valid_palette(value: &Bound<'_, PyAny>) -> bool {
    modes_from_py(value)
        .map(|(light, dark)| engine::valid_mode(&light) && engine::valid_mode(&dark))
        .unwrap_or(false)
}

#[pyfunction]
fn contrast_report(py: Python<'_>, value: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    let (light, dark) = modes_from_py(value)?;
    contrast_to_py(py, &light, &dark)
}

#[pyfunction]
fn terminal_colours(py: Python<'_>, value: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    let mode = mode_from_py(value)?;
    let dict = PyDict::new(py);
    dict.set_item("background", &mode.paper)?;
    dict.set_item("foreground", &mode.ink)?;
    dict.set_item("cursor", &mode.accent)?;
    dict.set_item("cursor_text", &mode.on_accent)?;
    dict.set_item("selection_background", &mode.accent)?;
    dict.set_item("selection_foreground", &mode.on_accent)?;
    dict.set_item("palette", PyList::new(py, &mode.ansi)?)?;
    Ok(dict.into_any().unbind())
}

#[pyfunction]
fn kitty_theme(value: &Bound<'_, PyAny>) -> PyResult<String> {
    let mode = mode_from_py(value)?;
    let mut lines = vec![
        "# Generated by Aura Studio. Changes are overwritten.".to_string(),
        format!("background {}", mode.paper),
        format!("foreground {}", mode.ink),
        format!("cursor {}", mode.accent),
        format!("cursor_text_color {}", mode.on_accent),
        format!("selection_background {}", mode.accent),
        format!("selection_foreground {}", mode.on_accent),
    ];
    for (index, colour) in mode.ansi.iter().enumerate() {
        lines.push(format!("color{index} {colour}"));
    }
    Ok(lines.join("\n") + "\n")
}

const GLASS_CSS: &str = r#"
/* see-through windows: the wallpaper shows through, text stays solid */
window.background:not(.popup):not(tooltip):not(.solid-csd):not(.desktopwindow) {
  background-color: alpha(@window_bg_color, 0.72);
}
headerbar, .titlebar:not(headerbar) { background-color: alpha(@headerbar_bg_color, 0.48); }
headerbar:backdrop, .titlebar:not(headerbar):backdrop { background-color: alpha(@headerbar_backdrop_color, 0.42); }
.view, textview text, iconview, treeview.view, list, listview, columnview, .content-view,
.boxed-list, scrolledwindow > viewport > list, entry, spinbutton {
  background-color: alpha(@view_bg_color, 0.48);
}
.sidebar, placessidebar, stacksidebar, .navigation-sidebar, .sidebar-pane {
  background-color: alpha(@sidebar_bg_color, 0.42);
}
list row, listview row, .card, frame > border { background-color: transparent; }
popover > contents, popover.background > contents, menu, .menu, .context-menu, tooltip,
tooltip.background, messagedialog, dialog.background, window.dialog {
  background-color: @popover_bg_color;
}
"#;

fn gtk_css_for_mode(mode: &engine::ModePalette, dark: bool, glass: bool) -> String {
    if !engine::valid_mode(mode) {
        return String::new();
    }
    let mut colours: BTreeMap<&str, String> = BTreeMap::new();
    colours.insert("accent_color", mode.accent_text.clone());
    colours.insert("accent_bg_color", mode.accent.clone());
    colours.insert("accent_fg_color", mode.on_accent.clone());
    colours.insert(
        "destructive_color",
        if dark {
            mode.ansi[9].clone()
        } else {
            mode.ansi[1].clone()
        },
    );
    colours.insert("destructive_bg_color", mode.ansi[1].clone());
    colours.insert("destructive_fg_color", "#FFFFFF".to_string());
    colours.insert("success_color", mode.ansi[2].clone());
    colours.insert("warning_color", mode.ansi[3].clone());
    colours.insert("error_color", mode.ansi[1].clone());
    colours.insert("window_bg_color", mode.paper.clone());
    colours.insert("window_fg_color", mode.ink.clone());
    colours.insert("view_bg_color", mode.sheet.clone());
    colours.insert("view_fg_color", mode.ink.clone());
    colours.insert("headerbar_bg_color", mode.paper2.clone());
    colours.insert("headerbar_fg_color", mode.ink.clone());
    colours.insert("headerbar_border_color", mode.ink.clone());
    colours.insert("headerbar_backdrop_color", mode.paper.clone());
    colours.insert(
        "headerbar_shade_color",
        if dark {
            "rgba(0, 0, 0, 0.5)".to_string()
        } else {
            colours::rgba_css(&mode.ink, 0.12)
        },
    );
    colours.insert("card_bg_color", mode.sheet.clone());
    colours.insert("card_fg_color", mode.ink.clone());
    colours.insert(
        "card_shade_color",
        if dark {
            "rgba(0, 0, 0, 0.4)".to_string()
        } else {
            colours::rgba_css(&mode.ink, 0.10)
        },
    );
    colours.insert(
        "dialog_bg_color",
        if dark {
            mode.sheet.clone()
        } else {
            mode.paper.clone()
        },
    );
    colours.insert("dialog_fg_color", mode.ink.clone());
    colours.insert("popover_bg_color", mode.sheet.clone());
    colours.insert("popover_fg_color", mode.ink.clone());
    colours.insert("sidebar_bg_color", mode.paper2.clone());
    colours.insert("sidebar_fg_color", mode.ink.clone());
    colours.insert(
        "shade_color",
        if dark {
            "rgba(0, 0, 0, 0.35)".to_string()
        } else {
            colours::rgba_css(&mode.ink, 0.08)
        },
    );
    colours.insert(
        "scrollbar_outline_color",
        if dark {
            "rgba(0, 0, 0, 0.5)".to_string()
        } else {
            "rgba(255, 255, 255, 0.5)".to_string()
        },
    );
    colours.insert("theme_bg_color", mode.paper.clone());
    colours.insert("theme_fg_color", mode.ink.clone());
    colours.insert("theme_base_color", mode.sheet.clone());
    colours.insert("theme_text_color", mode.ink.clone());
    colours.insert("theme_selected_bg_color", mode.accent.clone());
    colours.insert("theme_selected_fg_color", mode.on_accent.clone());
    colours.insert("aura_paper", mode.paper.clone());
    colours.insert("aura_paper2", mode.paper2.clone());
    colours.insert("aura_sheet", mode.sheet.clone());
    colours.insert("aura_ink", mode.ink.clone());
    colours.insert("aura_muted", mode.muted.clone());
    colours.insert("aura_accent", mode.accent.clone());
    colours.insert("aura_accent_text", mode.accent_text.clone());
    colours.insert("aura_on_accent", mode.on_accent.clone());
    colours.insert(
        "aura_shadow",
        if dark {
            "#000000".to_string()
        } else {
            mode.ink.clone()
        },
    );

    let mut text =
        "/* Aura Studio — generated from your wallpaper; changes are overwritten */\n".to_string();
    for (name, value) in &colours {
        text.push_str(&format!("@define-color {name} {value};\n"));
    }
    text.push_str("\nwindow.desktopwindow { background-color: transparent; }\n");
    if glass {
        text.push_str(GLASS_CSS);
    }
    text
}

#[pyfunction]
#[pyo3(signature = (value, dark, glass=false))]
fn gtk_css(value: &Bound<'_, PyAny>, dark: bool, glass: bool) -> PyResult<String> {
    let mode = mode_from_py(value)?;
    if !engine::valid_mode(&mode) {
        return Err(PyValueError::new_err("invalid palette colours"));
    }
    Ok(gtk_css_for_mode(&mode, dark, glass))
}

#[pyfunction]
fn css_for_export(value: &Bound<'_, PyAny>, dark: bool) -> PyResult<String> {
    let (light, dark_mode) = modes_from_py(value)?;
    let mode = if dark { &dark_mode } else { &light };
    if !engine::valid_mode(mode) {
        return Err(PyValueError::new_err("invalid palette colours"));
    }
    Ok(gtk_css_for_mode(mode, dark, false))
}

#[pyfunction]
fn palette_json(py: Python<'_>, value: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    let (light, dark) = modes_from_py(value)?;
    let source = value.downcast::<PyDict>()?;
    let out = PyDict::new(py);
    out.set_item("generator", "Aura Studio")?;
    let meta = match source.get_item("meta")? {
        Some(value) => value.unbind(),
        None => PyDict::new(py).into_any().unbind(),
    };
    out.set_item("meta", meta)?;
    out.set_item("light", mode_to_py(py, &light)?)?;
    out.set_item("dark", mode_to_py(py, &dark)?)?;

    let report = PyDict::new(py);
    for (name, mode) in [("light", &light), ("dark", &dark)] {
        let (body, accent) = engine::contrast_pair(mode);
        let entry = PyDict::new(py);
        entry.set_item("body", (body * 100.0).round() / 100.0)?;
        entry.set_item("accent", (accent * 100.0).round() / 100.0)?;
        report.set_item(name, entry)?;
    }
    out.set_item("contrast", report)?;
    Ok(out.into_any().unbind())
}

#[pyfunction]
fn style_labels() -> Vec<(String, String)> {
    engine::STYLE_LABELS
        .iter()
        .map(|(key, label)| (key.to_string(), label.to_string()))
        .collect()
}

#[pyfunction]
fn style_descriptions() -> Vec<(String, String)> {
    engine::STYLE_DESCRIPTIONS
        .iter()
        .map(|(key, description)| (key.to_string(), description.to_string()))
        .collect()
}

#[pyfunction]
fn ansi_names() -> Vec<String> {
    ANSI_NAMES.iter().map(|name| name.to_string()).collect()
}

#[pymodule]
fn aura_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", "0.1.0")?;
    m.add("STYLES", engine::STYLES.to_vec())?;
    m.add("PALETTE_KEYS", engine::PALETTE_KEYS.to_vec())?;
    m.add("SWATCH_KEYS", engine::SWATCH_KEYS.to_vec())?;
    m.add("ANSI_HUES", engine::ANSI_HUES.to_vec())?;
    m.add_function(wrap_pyfunction!(parse_hex, m)?)?;
    m.add_function(wrap_pyfunction!(is_hex, m)?)?;
    m.add_function(wrap_pyfunction!(rgb_hex, m)?)?;
    m.add_function(wrap_pyfunction!(rgba_hex, m)?)?;
    m.add_function(wrap_pyfunction!(rgba_css, m)?)?;
    m.add_function(wrap_pyfunction!(rgb_to_oklab, m)?)?;
    m.add_function(wrap_pyfunction!(oklab_to_rgb, m)?)?;
    m.add_function(wrap_pyfunction!(oklab_to_oklch, m)?)?;
    m.add_function(wrap_pyfunction!(oklch_to_oklab, m)?)?;
    m.add_function(wrap_pyfunction!(rgb_to_oklch, m)?)?;
    m.add_function(wrap_pyfunction!(hex_to_oklch, m)?)?;
    m.add_function(wrap_pyfunction!(oklch_rgb, m)?)?;
    m.add_function(wrap_pyfunction!(oklch_hex, m)?)?;
    m.add_function(wrap_pyfunction!(hex_to_lch, m)?)?;
    m.add_function(wrap_pyfunction!(luminance, m)?)?;
    m.add_function(wrap_pyfunction!(contrast, m)?)?;
    m.add_function(wrap_pyfunction!(best_on, m)?)?;
    m.add_function(wrap_pyfunction!(contrast_label, m)?)?;
    m.add_function(wrap_pyfunction!(adjust_for_contrast, m)?)?;
    m.add_function(wrap_pyfunction!(tint, m)?)?;
    m.add_function(wrap_pyfunction!(hue_distance, m)?)?;
    m.add_function(wrap_pyfunction!(circular_mean, m)?)?;
    m.add_function(wrap_pyfunction!(palette_from_image, m)?)?;
    m.add_function(wrap_pyfunction!(palette_from_samples, m)?)?;
    m.add_function(wrap_pyfunction!(valid_mode, m)?)?;
    m.add_function(wrap_pyfunction!(valid_palette, m)?)?;
    m.add_function(wrap_pyfunction!(contrast_report, m)?)?;
    m.add_function(wrap_pyfunction!(terminal_colours, m)?)?;
    m.add_function(wrap_pyfunction!(kitty_theme, m)?)?;
    m.add_function(wrap_pyfunction!(gtk_css, m)?)?;
    m.add_function(wrap_pyfunction!(css_for_export, m)?)?;
    m.add_function(wrap_pyfunction!(palette_json, m)?)?;
    m.add_function(wrap_pyfunction!(style_labels, m)?)?;
    m.add_function(wrap_pyfunction!(style_descriptions, m)?)?;
    m.add_function(wrap_pyfunction!(ansi_names, m)?)?;
    Ok(())
}
