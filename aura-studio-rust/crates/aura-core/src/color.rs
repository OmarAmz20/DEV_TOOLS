//! Perceptual colour maths: sRGB, OKLab, OKLCH, WCAG contrast.

pub type Rgb = (f64, f64, f64);
pub type Oklab = (f64, f64, f64);
pub type Oklch = (f64, f64, f64);

fn to_linear(c: f64) -> f64 {
    if c <= 0.04045 {
        c / 12.92
    } else {
        ((c + 0.055) / 1.055).powf(2.4)
    }
}

fn to_srgb(c: f64) -> f64 {
    if c <= 0.003_130_8 {
        12.92 * c
    } else {
        1.055 * c.powf(1.0 / 2.4) - 0.055
    }
}

fn hex_pair(text: &str) -> Option<Rgb> {
    let text = text.trim();
    let text = text.strip_prefix('#').unwrap_or(text);
    if text.len() != 3 && text.len() != 6 {
        return None;
    }
    if !text.chars().all(|c| c.is_ascii_hexdigit()) {
        return None;
    }
    let expanded: String = if text.len() == 3 {
        text.chars().flat_map(|c| [c, c]).collect()
    } else {
        text.to_string()
    };
    let channel = |index: usize| -> f64 {
        u8::from_str_radix(&expanded[index..index + 2], 16).expect("hex digits were checked") as f64
            / 255.0
    };
    Some((channel(0), channel(2), channel(4)))
}

pub fn parse_hex(value: &str) -> Option<Rgb> {
    hex_pair(value)
}

pub fn is_hex(value: &str) -> bool {
    hex_pair(value).is_some()
}

fn channel_byte(value: f64) -> u8 {
    (value.clamp(0.0, 1.0) * 255.0).round().clamp(0.0, 255.0) as u8
}

pub fn rgb_hex(rgb: Rgb) -> String {
    format!(
        "#{:02X}{:02X}{:02X}",
        channel_byte(rgb.0),
        channel_byte(rgb.1),
        channel_byte(rgb.2)
    )
}

fn alpha_text(alpha: f64) -> String {
    let mut text = format!("{:.3}", alpha.clamp(0.0, 1.0));
    while text.ends_with('0') {
        text.pop();
    }
    if text.ends_with('.') {
        text.pop();
    }
    if text.is_empty() {
        "0".to_string()
    } else {
        text
    }
}

pub fn rgba_hex(rgb: Rgb, alpha: f64) -> String {
    let r = channel_byte(rgb.0);
    let g = channel_byte(rgb.1);
    let b = channel_byte(rgb.2);
    format!("rgba({r}, {g}, {b}, {})", alpha_text(alpha))
}

pub fn rgba_css(hexcolor: &str, alpha: f64) -> String {
    rgba_hex(parse_hex(hexcolor).unwrap_or((0.0, 0.0, 0.0)), alpha)
}

pub fn rgb_to_oklab(rgb: Rgb) -> Oklab {
    let (r, g, b) = (to_linear(rgb.0), to_linear(rgb.1), to_linear(rgb.2));
    let lr = 0.412_221_470_8 * r + 0.536_332_536_3 * g + 0.051_445_992_9 * b;
    let mg = 0.211_903_498_2 * r + 0.680_699_545_1 * g + 0.107_396_956_6 * b;
    let sb = 0.088_302_461_9 * r + 0.281_718_837_6 * g + 0.629_978_700_5 * b;
    let l_ = lr.cbrt();
    let m_ = mg.cbrt();
    let s_ = sb.cbrt();
    (
        0.210_454_255_3 * l_ + 0.793_617_785_0 * m_ - 0.004_072_046_8 * s_,
        1.977_998_495_1 * l_ - 2.428_592_205_0 * m_ + 0.450_593_709_9 * s_,
        0.025_904_037_1 * l_ + 0.782_771_766_2 * m_ - 0.808_675_766_0 * s_,
    )
}

pub fn oklab_to_rgb(lab: Oklab, clamp: bool) -> Rgb {
    let (l, a, b) = lab;
    let l_ = l + 0.396_337_777_4 * a + 0.215_803_757_3 * b;
    let m_ = l - 0.105_561_345_8 * a - 0.063_854_172_8 * b;
    let s_ = l - 0.089_484_177_5 * a - 1.291_485_548_0 * b;
    let (l, m, s) = (l_.powi(3), m_.powi(3), s_.powi(3));
    let r = 4.076_741_662_1 * l - 3.307_711_591_3 * m + 0.230_969_929_2 * s;
    let g = -1.268_438_004_6 * l + 2.609_757_401_1 * m - 0.341_319_396_5 * s;
    let bb = -0.004_196_086_3 * l - 0.703_418_614_7 * m + 1.707_614_701_0 * s;
    let out = (to_srgb(r), to_srgb(g), to_srgb(bb));
    if clamp {
        (
            out.0.clamp(0.0, 1.0),
            out.1.clamp(0.0, 1.0),
            out.2.clamp(0.0, 1.0),
        )
    } else {
        out
    }
}

pub fn oklab_to_oklch(lab: Oklab) -> Oklch {
    let (l, a, b) = lab;
    (l, a.hypot(b), b.atan2(a).to_degrees().rem_euclid(360.0))
}

pub fn oklch_to_oklab(lch: Oklch) -> Oklab {
    let (l, c, h) = lch;
    let rad = h.to_radians();
    (l, c * rad.cos(), c * rad.sin())
}

pub fn rgb_to_oklch(rgb: Rgb) -> Oklch {
    oklab_to_oklch(rgb_to_oklab(rgb))
}

pub fn hex_to_oklch(hexcolor: &str) -> Option<Oklch> {
    parse_hex(hexcolor).map(rgb_to_oklch)
}

fn in_gamut(lab: Oklab) -> bool {
    let rgb = oklab_to_rgb(lab, false);
    rgb.0 >= -1e-5
        && rgb.0 <= 1.0 + 1e-5
        && rgb.1 >= -1e-5
        && rgb.1 <= 1.0 + 1e-5
        && rgb.2 >= -1e-5
        && rgb.2 <= 1.0 + 1e-5
}

fn fit_chroma(l: f64, c: f64, h: f64) -> f64 {
    let l = l.clamp(0.0, 1.0);
    if c <= 0.0 || in_gamut(oklch_to_oklab((l, c, h))) {
        return c.max(0.0);
    }
    let (mut lo, mut hi) = (0.0, c);
    for _ in 0..18 {
        let mid = (lo + hi) / 2.0;
        if in_gamut(oklch_to_oklab((l, mid, h))) {
            lo = mid;
        } else {
            hi = mid;
        }
    }
    lo
}

pub fn oklch_rgb(lch: Oklch) -> Rgb {
    let l = lch.0.clamp(0.0, 1.0);
    let c = fit_chroma(l, lch.1, lch.2).max(0.0);
    oklab_to_rgb(oklch_to_oklab((l, c, lch.2)), true)
}

pub fn oklch_hex(l: f64, c: f64, h: f64) -> String {
    rgb_hex(oklch_rgb((l, c, h)))
}

pub fn hex_to_lch(hexcolor: &str) -> Oklch {
    oklab_to_oklch(rgb_to_oklab(parse_hex(hexcolor).unwrap_or((0.0, 0.0, 0.0))))
}

pub fn luminance(hexcolor: &str) -> f64 {
    let (r, g, b) = parse_hex(hexcolor).unwrap_or((0.0, 0.0, 0.0));
    let r = to_linear(r.clamp(0.0, 1.0));
    let g = to_linear(g.clamp(0.0, 1.0));
    let b = to_linear(b.clamp(0.0, 1.0));
    0.2126 * r + 0.7152 * g + 0.0722 * b
}

pub fn contrast(one: &str, two: &str) -> f64 {
    let a = luminance(one);
    let b = luminance(two);
    let (high, low) = if a >= b { (a, b) } else { (b, a) };
    (high + 0.05) / (low + 0.05)
}

pub fn best_on(background: &str, candidates: &[String]) -> String {
    let fallback = ["#101014".to_string(), "#FFFFFF".to_string()];
    let choices = if candidates.is_empty() {
        &fallback[..]
    } else {
        candidates
    };
    choices
        .iter()
        .max_by(|a, b| {
            contrast(a, background)
                .partial_cmp(&contrast(b, background))
                .unwrap_or(std::cmp::Ordering::Equal)
        })
        .cloned()
        .unwrap_or_else(|| "#FFFFFF".to_string())
}

pub fn contrast_label(value: f64) -> &'static str {
    if value >= 7.0 {
        "AAA"
    } else if value >= 4.5 {
        "AA"
    } else if value >= 3.0 {
        "AA large"
    } else {
        "low"
    }
}

pub fn adjust_for_contrast(
    l: f64,
    c: f64,
    h: f64,
    against: &str,
    target: f64,
    prefer: Option<&str>,
) -> (String, f64) {
    let directions: [f64; 2] = match prefer {
        Some("lighter") => [1.0, -1.0],
        _ => [-1.0, 1.0],
    };
    for direction in directions {
        let mut value = l;
        for _ in 0..160 {
            let candidate = oklch_hex(value, c, h);
            if contrast(&candidate, against) >= target {
                return (candidate, value);
            }
            value += direction * 0.004;
            if value < 0.0 || value > 1.0 {
                break;
            }
        }
    }
    let dark = oklch_hex(0.08, c * 0.6, h);
    let light = oklch_hex(0.97, c * 0.4, h);
    if contrast(&dark, against) >= contrast(&light, against) {
        (dark, l)
    } else {
        (light, l)
    }
}

pub fn tint(lightness: f64, chroma: f64, hue: f64) -> String {
    oklch_hex(lightness, chroma, hue)
}

pub fn hue_distance(one: f64, two: f64) -> f64 {
    let d = (one - two).abs() % 360.0;
    d.min(360.0 - d)
}

pub fn circular_mean(hues: &[f64], weights: Option<&[f64]>) -> f64 {
    let mut x = 0.0;
    let mut y = 0.0;
    for (index, hue) in hues.iter().enumerate() {
        let weight = weights
            .and_then(|values| values.get(index).copied())
            .unwrap_or(1.0);
        let rad = hue.to_radians();
        x += rad.cos() * weight;
        y += rad.sin() * weight;
    }
    if x == 0.0 && y == 0.0 {
        0.0
    } else {
        y.atan2(x).to_degrees().rem_euclid(360.0)
    }
}
