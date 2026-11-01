//! Palette extraction: deterministic k-means in OKLab, accessible modes.

use crate::color;
use image::GenericImageView;
use serde::{Deserialize, Serialize};

pub const STYLES: [&str; 4] = ["vivid", "balanced", "muted", "mono"];
pub const STYLE_LABELS: [(&str, &str); 4] = [
    ("vivid", "Vivid"),
    ("balanced", "Balanced"),
    ("muted", "Muted"),
    ("mono", "Mono"),
];
pub const STYLE_DESCRIPTIONS: [(&str, &str); 4] = [
    ("vivid", "More chroma in the accent and backgrounds"),
    (
        "balanced",
        "Readable colour taken straight from the picture",
    ),
    ("muted", "Soft, paper-like colours with a quiet accent"),
    ("mono", "Graphite neutrals, no coloured accent"),
];
pub const SWATCH_KEYS: [&str; 6] = ["paper", "paper2", "sheet", "ink", "muted", "accent"];
pub const PALETTE_KEYS: [&str; 9] = [
    "paper",
    "paper2",
    "sheet",
    "ink",
    "muted",
    "accent",
    "accent_text",
    "on_accent",
    "ansi",
];
pub const ANSI_HUES: [f64; 6] = [28.0, 148.0, 92.0, 258.0, 330.0, 198.0];

pub type Point = (f64, f64, f64);

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ModePalette {
    pub paper: String,
    pub paper2: String,
    pub sheet: String,
    pub ink: String,
    pub muted: String,
    pub accent: String,
    pub accent_text: String,
    pub on_accent: String,
    pub ansi: Vec<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct PaletteMeta {
    pub cast_hue: f64,
    pub cast_chroma: f64,
    pub coloured_share: f64,
    pub accent_hue: f64,
    pub accent_chroma: f64,
    pub mono: bool,
    pub style: String,
    pub custom_accent: bool,
    pub clusters: usize,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Palette {
    pub light: ModePalette,
    pub dark: ModePalette,
    pub meta: PaletteMeta,
}

#[derive(Clone, Copy, Debug)]
struct Cluster {
    lab: Point,
    weight: f64,
}

pub fn valid_mode(mode: &ModePalette) -> bool {
    [
        &mode.paper,
        &mode.paper2,
        &mode.sheet,
        &mode.ink,
        &mode.muted,
        &mode.accent,
        &mode.accent_text,
        &mode.on_accent,
    ]
    .iter()
    .all(|value| color::is_hex(value))
        && mode.ansi.len() == 16
        && mode.ansi.iter().all(|value| color::is_hex(value))
}

pub fn valid_palette(palette: &Palette) -> bool {
    valid_mode(&palette.light) && valid_mode(&palette.dark)
}

pub fn contrast_pair(mode: &ModePalette) -> (f64, f64) {
    (
        color::contrast(&mode.ink, &mode.paper),
        color::contrast(&mode.accent_text, &mode.paper),
    )
}

struct Rng {
    state: u64,
}

impl Rng {
    fn new(seed: u64) -> Self {
        Self {
            state: seed.wrapping_add(0x9E37_79B9_7F4A_7C15),
        }
    }

    fn next_f64(&mut self) -> f64 {
        self.state = self
            .state
            .wrapping_mul(6_364_136_223_846_793_005)
            .wrapping_add(1_442_695_040_888_963_407);
        ((self.state >> 11) as f64) / ((1u64 << 53) as f64)
    }

    fn index(&mut self, length: usize) -> usize {
        if length == 0 {
            0
        } else {
            ((self.next_f64() * length as f64) as usize).min(length - 1)
        }
    }
}

fn distance(one: Point, two: Point) -> f64 {
    (one.0 - two.0).powi(2) + (one.1 - two.1).powi(2) + (one.2 - two.2).powi(2)
}

fn kmeans(points: &[Point], k: usize, iterations: usize) -> Vec<Cluster> {
    if points.is_empty() {
        return Vec::new();
    }
    let step = ((points.len() as f64 / 3200.0).ceil() as usize).max(1);
    let pts: Vec<Point> = points.iter().copied().step_by(step).collect();
    let k = k.min(pts.len()).max(1);
    let mut rng = Rng::new(7);
    let mut centres = vec![pts[rng.index(pts.len())]];
    while centres.len() < k {
        let distances: Vec<f64> = pts
            .iter()
            .map(|point| {
                centres
                    .iter()
                    .map(|centre| distance(*point, *centre))
                    .fold(f64::INFINITY, f64::min)
            })
            .collect();
        let total: f64 = distances.iter().sum();
        if total <= 1e-12 {
            break;
        }
        let mut target = rng.next_f64() * total;
        let mut added = false;
        for (point, value) in pts.iter().zip(distances.iter()) {
            target -= value;
            if target <= 0.0 {
                centres.push(*point);
                added = true;
                break;
            }
        }
        if !added {
            centres.push(*pts.last().expect("points is not empty"));
        }
    }

    let mut groups: Vec<Vec<Point>> = vec![Vec::new(); centres.len()];
    for _ in 0..iterations {
        for group in groups.iter_mut() {
            group.clear();
        }
        for point in &pts {
            let mut best = 0;
            let mut best_distance = distance(*point, centres[0]);
            for (index, centre) in centres.iter().enumerate().skip(1) {
                let value = distance(*point, *centre);
                if value < best_distance {
                    best = index;
                    best_distance = value;
                }
            }
            groups[best].push(*point);
        }
        let mut moved = false;
        for (index, group) in groups.iter().enumerate() {
            if group.is_empty() {
                continue;
            }
            let centre = (
                group.iter().map(|point| point.0).sum::<f64>() / group.len() as f64,
                group.iter().map(|point| point.1).sum::<f64>() / group.len() as f64,
                group.iter().map(|point| point.2).sum::<f64>() / group.len() as f64,
            );
            if distance(centre, centres[index]) > 1e-10 {
                moved = true;
            }
            centres[index] = centre;
        }
        if !moved {
            break;
        }
    }

    let total = pts.len() as f64;
    let mut clusters: Vec<Cluster> = groups
        .iter()
        .zip(centres.iter())
        .filter(|(group, _)| !group.is_empty())
        .map(|(group, centre)| Cluster {
            lab: *centre,
            weight: group.len() as f64 / total,
        })
        .collect();
    clusters.sort_by(|a, b| {
        b.weight
            .partial_cmp(&a.weight)
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    clusters
}

fn cluster_hue(cluster: &Cluster) -> (f64, f64) {
    let (_l, a, b) = cluster.lab;
    (a.hypot(b), b.atan2(a).to_degrees().rem_euclid(360.0))
}

fn pick_accent(clusters: &[Cluster], cast_hue: f64) -> Option<(f64, f64)> {
    let mut best = None;
    let mut best_score = 0.0;
    for cluster in clusters {
        let (l, _a, _b) = cluster.lab;
        let (chroma, hue) = cluster_hue(cluster);
        if chroma < 0.024 || l <= 0.18 || l >= 0.94 {
            continue;
        }
        let distinctness = 0.58 + 0.42 * color::hue_distance(hue, cast_hue).min(120.0) / 120.0;
        let score = cluster.weight.powf(0.32) * (chroma / 0.20).min(1.0) * distinctness;
        if score > best_score {
            best = Some((hue, chroma));
            best_score = score;
        }
    }
    best
}

fn style_accent(hue: f64, mut chroma: f64, style: &str) -> (f64, f64) {
    if style == "mono" {
        return (hue, 0.0);
    }
    if style == "vivid" {
        chroma *= 1.18;
    } else if style == "muted" {
        chroma *= 0.68;
    }
    if chroma < 0.024 {
        return (hue, 0.0);
    }
    (hue, chroma.clamp(0.078, 0.205))
}

fn tint_strength(cast_chroma: f64, style: &str) -> f64 {
    let factor = match style {
        "vivid" => 0.58,
        "balanced" => 0.38,
        "muted" => 0.20,
        _ => 0.0,
    };
    (cast_chroma * factor).clamp(0.0, 0.048)
}

fn ansi(
    light: bool,
    paper: &str,
    tint_hue: f64,
    tint_chroma: f64,
    accent_chroma: f64,
) -> Vec<String> {
    let chroma = (accent_chroma * 0.62).clamp(0.085, 0.16);
    let (base_l, bright_l, prefer) = if light {
        (0.455, 0.60, "darker")
    } else {
        (0.685, 0.795, "lighter")
    };
    let base: Vec<String> = ANSI_HUES
        .iter()
        .map(|hue| color::adjust_for_contrast(base_l, chroma, *hue, paper, 3.1, Some(prefer)).0)
        .collect();
    let bright_target = if light { 3.8 } else { 4.0 };
    let bright: Vec<String> = ANSI_HUES
        .iter()
        .map(|hue| {
            color::adjust_for_contrast(bright_l, chroma, *hue, paper, bright_target, Some(prefer)).0
        })
        .collect();
    let (black, white, bright_black, bright_white) = if light {
        (
            color::tint(0.22, tint_chroma * 0.7, tint_hue),
            color::tint(0.46, tint_chroma * 0.6, tint_hue),
            color::tint(0.36, tint_chroma * 0.6, tint_hue),
            color::tint(0.20, tint_chroma * 0.7, tint_hue),
        )
    } else {
        (
            color::tint(0.235, tint_chroma * 0.75, tint_hue),
            color::tint(0.86, tint_chroma * 0.5, tint_hue),
            color::tint(0.62, tint_chroma * 0.5, tint_hue),
            color::tint(0.955, tint_chroma * 0.3, tint_hue),
        )
    };
    let mut result = Vec::with_capacity(16);
    result.push(black);
    result.extend(base[..6].iter().cloned());
    result.push(white);
    result.push(bright_black);
    result.extend(bright[..6].iter().cloned());
    result.push(bright_white);
    result
}

fn mode(
    light: bool,
    tint_hue: f64,
    tint_chroma: f64,
    accent_hue: f64,
    accent_chroma: f64,
) -> ModePalette {
    let (paper, paper2, sheet, ink, muted, accent, accent_text) = if light {
        let paper = color::tint(0.966, tint_chroma * 0.48, tint_hue);
        let paper2 = color::tint(0.925, tint_chroma * 0.72, tint_hue);
        let sheet = color::tint(0.991, tint_chroma * 0.22, tint_hue);
        let ink = color::tint(0.225, tint_chroma * 0.62, tint_hue);
        let muted = color::tint(0.465, tint_chroma * 0.55, tint_hue);
        if accent_chroma == 0.0 {
            (
                paper,
                paper2,
                sheet,
                ink,
                muted,
                color::tint(0.335, 0.0, tint_hue),
                color::tint(0.245, 0.0, tint_hue),
            )
        } else {
            let accent = color::adjust_for_contrast(
                0.585,
                accent_chroma,
                accent_hue,
                &paper,
                3.2,
                Some("darker"),
            )
            .0;
            let accent_text = color::adjust_for_contrast(
                0.46,
                accent_chroma,
                accent_hue,
                &paper,
                4.6,
                Some("darker"),
            )
            .0;
            (paper, paper2, sheet, ink, muted, accent, accent_text)
        }
    } else {
        let paper = color::tint(0.158, tint_chroma * 0.78, tint_hue);
        let paper2 = color::tint(0.128, tint_chroma * 0.95, tint_hue);
        let sheet = color::tint(0.210, tint_chroma * 0.82, tint_hue);
        let ink = color::tint(0.930, tint_chroma * 0.42, tint_hue);
        let muted = color::tint(0.680, tint_chroma * 0.50, tint_hue);
        if accent_chroma == 0.0 {
            (
                paper,
                paper2,
                sheet,
                ink,
                muted,
                color::tint(0.805, 0.0, tint_hue),
                color::tint(0.885, 0.0, tint_hue),
            )
        } else {
            let accent = color::adjust_for_contrast(
                0.735,
                accent_chroma,
                accent_hue,
                &paper,
                4.6,
                Some("lighter"),
            )
            .0;
            let accent_text = color::adjust_for_contrast(
                0.815,
                accent_chroma,
                accent_hue,
                &paper,
                7.0,
                Some("lighter"),
            )
            .0;
            (paper, paper2, sheet, ink, muted, accent, accent_text)
        }
    };
    let on_accent = color::best_on(&accent, &["#101014".to_string(), "#FFFFFF".to_string()]);
    ModePalette {
        paper: paper.clone(),
        paper2,
        sheet,
        ink,
        muted,
        accent,
        accent_text,
        on_accent,
        ansi: ansi(light, &paper, tint_hue, tint_chroma, accent_chroma),
    }
}

pub fn build(
    samples: &[Point],
    style: &str,
    accent_override: Option<&str>,
) -> Result<Palette, String> {
    let style = if STYLES.contains(&style) {
        style
    } else {
        "balanced"
    };
    if samples.is_empty() {
        return Err("the picture has no readable pixels".to_string());
    }
    let clusters = kmeans(samples, 10, 14);
    let (cast_hue, cast_chroma, coloured_share) = cast(samples);
    let mono_image = coloured_share < 0.035 || cast_chroma < 0.018;

    let tint_chroma = if mono_image {
        0.0
    } else {
        tint_strength(cast_chroma, style)
    };

    let mut custom = accent_override.is_some();
    let (mut accent_hue, mut accent_chroma) = (cast_hue, 0.0);
    if let Some(override_value) = accent_override {
        if let Some((_l, chroma, hue)) = color::hex_to_oklch(override_value) {
            accent_hue = hue;
            accent_chroma = chroma;
        } else {
            custom = false;
        }
    }
    if !custom {
        accent_hue = cast_hue;
        accent_chroma = 0.0;
        if !mono_image {
            if let Some((hue, chroma)) = pick_accent(&clusters, cast_hue) {
                accent_hue = hue;
                accent_chroma = chroma;
            } else {
                accent_hue = cast_hue;
                accent_chroma = cast_chroma;
            }
        }
        (accent_hue, accent_chroma) = style_accent(accent_hue, accent_chroma, style);
    } else {
        let accent_style = if style == "mono" { "balanced" } else { style };
        (accent_hue, accent_chroma) = style_accent(accent_hue, accent_chroma, accent_style);
    }

    let light = mode(true, cast_hue, tint_chroma, accent_hue, accent_chroma);
    let dark = mode(false, cast_hue, tint_chroma, accent_hue, accent_chroma);
    let meta = PaletteMeta {
        cast_hue: round(cast_hue, 1),
        cast_chroma: round(cast_chroma, 4),
        coloured_share: round(coloured_share, 3),
        accent_hue: round(accent_hue, 1),
        accent_chroma: round(accent_chroma, 4),
        mono: mono_image || style == "mono",
        style: style.to_string(),
        custom_accent: custom,
        clusters: clusters.len(),
    };
    Ok(Palette { light, dark, meta })
}

pub fn from_image(
    path: &str,
    style: &str,
    accent_override: Option<&str>,
) -> Result<Palette, String> {
    let image = image::open(path).map_err(|error| format!("could not read a picture: {error}"))?;
    let thumbnail = image.thumbnail(72, 72);
    let (width, height) = thumbnail.dimensions();
    if width == 0 || height == 0 {
        return Err("the picture has no readable pixels".to_string());
    }
    let rgba = thumbnail.to_rgba8();
    let mut samples = Vec::with_capacity((width * height) as usize);
    for pixel in rgba.pixels() {
        let [r, g, b, a] = pixel.0;
        if a < 128 {
            continue;
        }
        samples.push(color::rgb_to_oklab((
            r as f64 / 255.0,
            g as f64 / 255.0,
            b as f64 / 255.0,
        )));
    }
    if samples.is_empty() {
        return Err("the picture has no readable pixels".to_string());
    }
    build(&samples, style, accent_override)
}

fn cast(samples: &[Point]) -> (f64, f64, f64) {
    let mut hues = Vec::new();
    let mut weights = Vec::new();
    let mut chromas = Vec::new();
    for (l, a, b) in samples {
        let chroma = a.hypot(*b);
        if chroma > 0.018 && *l > 0.05 && *l < 0.95 {
            hues.push(b.atan2(*a).to_degrees().rem_euclid(360.0));
            weights.push(chroma);
            chromas.push(chroma);
        }
    }
    if hues.is_empty() {
        return (0.0, 0.0, 0.0);
    }
    let mut hist = [0.0; 36];
    for (hue, weight) in hues.iter().zip(weights.iter()) {
        hist[(*hue / 10.0) as usize % 36] += *weight;
    }
    let mut smooth = [0.0; 36];
    for index in 0..36 {
        smooth[index] = hist[index] + 0.5 * (hist[(index + 35) % 36] + hist[(index + 1) % 36]);
    }
    let mut peak_bin = 0;
    for index in 1..36 {
        if smooth[index] > smooth[peak_bin] {
            peak_bin = index;
        }
    }
    let peak = peak_bin as f64 * 10.0 + 5.0;
    let mut picked_hues = Vec::new();
    let mut picked_weights = Vec::new();
    for (hue, weight) in hues.iter().zip(weights.iter()) {
        if color::hue_distance(*hue, peak) <= 24.0 {
            picked_hues.push(*hue);
            picked_weights.push(*weight);
        }
    }
    let cast_hue = if picked_hues.is_empty() {
        color::circular_mean(&hues, Some(&weights))
    } else {
        color::circular_mean(&picked_hues, Some(&picked_weights))
    };
    let cast_chroma = if picked_weights.is_empty() {
        chromas.iter().sum::<f64>() / chromas.len() as f64
    } else {
        picked_weights.iter().sum::<f64>() / picked_weights.len() as f64
    };
    let share = hues.len() as f64 / samples.len() as f64;
    (cast_hue, cast_chroma, share)
}

fn round(value: f64, places: i32) -> f64 {
    let factor = 10f64.powi(places);
    (value * factor).round() / factor
}
