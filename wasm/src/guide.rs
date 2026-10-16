// Reading the in-game Cat Guide from a screenshot: where the page sits in the guide (the
// indicator thumb along the bar at the top) and, cell by cell, whether the unit is owned,
// still a gray "?", or the cell is empty past the end of its rarity. Every measure is
// relative to the image, so any phone resolution reads the same.

pub const CELLS: usize = 24; // 6 columns x 4 rows a page
const COLS: usize = 6;

/// An RGBA image, as a canvas hands it over.
pub struct Image<'a> {
    pub px: &'a [u8],
    pub w: usize,
    pub h: usize,
}

impl Image<'_> {
    fn rgb(&self, x: usize, y: usize) -> (i32, i32, i32) {
        let i = 4 * (y * self.w + x);
        (
            i32::from(self.px[i]),
            i32::from(self.px[i + 1]),
            i32::from(self.px[i + 2]),
        )
    }

    fn lum(&self, x: usize, y: usize) -> i32 {
        let (r, g, b) = self.rgb(x, y);
        (r + g + b) / 3
    }

    /// The panel's background.
    fn teal(&self, x: usize, y: usize) -> bool {
        let (r, g, b) = self.rgb(x, y);
        g - r > 40 && b - r > 50
    }
}

/// (start, end) of each run of true values.
fn runs(mask: impl IntoIterator<Item = bool>) -> Vec<(usize, usize)> {
    let mut out = Vec::new();
    let mut start = None;
    let mut i = 0;
    for on in mask {
        match (on, start) {
            (true, None) => start = Some(i),
            (false, Some(s)) => {
                out.push((s, i));
                start = None;
            }
            _ => {}
        }
        i += 1;
    }
    if let Some(s) = start {
        out.push((s, i));
    }
    out
}

/// Runs joined across a few anti-aliased pixels.
fn merged(spans: Vec<(usize, usize)>, gap: usize) -> Vec<(usize, usize)> {
    let mut out: Vec<(usize, usize)> = Vec::new();
    for (s, e) in spans {
        match out.last_mut() {
            Some(last) if s - last.1 <= gap => last.1 = e,
            _ => out.push((s, e)),
        }
    }
    out
}

/// Where the page sits in the guide, 0 on the first page and 1 on the last: the bright
/// thumb's place along the dark indicator bar that runs over the teal panel.
pub fn position(img: &Image) -> Option<f64> {
    let (w, h) = (img.w, img.h);
    let off = (h * 3 / 200).max(4); // the panel above and below the bar
    let wide = |len: usize, share: f64| len as f64 > w as f64 * share;
    let mut best: Option<(usize, f64)> = None;

    for y in off.max(8)..h / 4 {
        let row: Vec<i32> = (0..w).map(|x| img.lum(x, y)).collect();
        for (s, e) in merged(runs(row.iter().map(|&l| !(70..=190).contains(&l))), 4) {
            if !wide(e - s, 0.2) || best.is_some_and(|(len, _)| e - s <= len) {
                continue;
            }
            let bright: Vec<_> = runs(row[s..e].iter().map(|&l| l > 190))
                .into_iter()
                .filter(|&(a, b)| wide(b - a, 0.008))
                .collect();
            let [(t0, t1)] = bright[..] else { continue };
            if wide(t1 - t0, 0.06) {
                continue;
            }
            let on_panel =
                |y: usize| (s..e).filter(|&x| img.teal(x, y)).count() * 10 >= (e - s) * 6;
            if !on_panel(y - off) || !on_panel(y + off) {
                continue;
            }
            let travel = (e - s - (t1 - t0)) as f64;
            best = Some((e - s, t0 as f64 / travel));
        }
    }
    best.map(|(_, fraction)| fraction)
}

/// Where the cells are: the top-left cell's box and the step to the next column and row.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Grid {
    pub x: usize,
    pub y: usize,
    pub w: usize,
    pub h: usize,
    pub dx: usize,
    pub dy: usize,
    pub cols: usize,
    pub rows: usize,
}

/// The cell layout, from the cells' thick black frames: the image row crossing the most
/// equal-width top borders gives the columns, the left borders down the first column the
/// rows. None on a page with too few cells to tell (a rarity's last page can hold one).
pub fn grid(img: &Image) -> Option<Grid> {
    let (w, h) = (img.w, img.h);
    let cell = |len: usize| (w / 20..w * 3 / 20).contains(&len);
    let even = (w / 250).max(3);
    let mut cols: Vec<(usize, usize)> = Vec::new();

    for y in h / 6..h * 5 / 6 {
        let found: Vec<_> = runs((0..w).map(|x| img.lum(x, y) < 60))
            .into_iter()
            .filter(|&(s, e)| cell(e - s))
            .collect();
        let widths = found.iter().map(|&(s, e)| e - s);
        let spread = widths.clone().max().unwrap_or(0) - widths.min().unwrap_or(0);
        if found.len() >= 2 && spread < even && found.len() > cols.len() {
            cols = found;
        }
    }
    let &[(x, x_end), (next, _), ..] = &cols[..] else {
        return None;
    };

    let rows: Vec<_> = runs((0..h).map(|y| img.lum(x + 2, y) < 60))
        .into_iter()
        .filter(|&(s, e)| (h * 2 / 25..h * 3 / 10).contains(&(e - s)))
        .collect();
    let &(y, y_end) = rows.first()?;
    let dy = rows.get(1).map_or(0, |&(s, _)| s - y);

    Some(Grid {
        x,
        y,
        w: x_end - x,
        h: y_end - y,
        dx: next - x,
        dy,
        cols: cols.len().min(COLS),
        rows: rows.len(),
    })
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(u8)]
pub enum Mark {
    Empty = 0,
    Locked = 1,
    Owned = 2,
}

/// Every cell of a page under ``grid``, left to right, top to bottom.
pub fn marks(img: &Image, grid: &Grid) -> [Mark; CELLS] {
    std::array::from_fn(|i| {
        let x = grid.x + (i % COLS) * grid.dx;
        let y = grid.y + (i / COLS) * grid.dy;
        classify(img, x, y, grid.w, grid.h)
    })
}

/// A cell's inside, past its frame: mostly panel teal is no cell at all; flat mid-gray
/// with no white is the locked "?"; anything else is a unit's art.
fn classify(img: &Image, x: usize, y: usize, w: usize, h: usize) -> Mark {
    let inset = (w * 7 / 100).max(2);
    let (x0, y0) = (x + inset, y + inset);
    let (x1, y1) = (
        (x + w).saturating_sub(inset).min(img.w),
        (y + h).saturating_sub(inset).min(img.h),
    );
    if x0 >= x1 || y0 >= y1 {
        return Mark::Empty;
    }

    let (mut teal, mut gray, mut white) = (0, 0, 0);
    for py in y0..y1 {
        for px in x0..x1 {
            let (r, g, b) = img.rgb(px, py);
            let lum = (r + g + b) / 3;
            let chroma = r.max(g).max(b) - r.min(g).min(b);
            teal += usize::from(img.teal(px, py));
            gray += usize::from(chroma < 25 && (71..215).contains(&lum));
            white += usize::from(lum > 235);
        }
    }
    let n = (x1 - x0) * (y1 - y0);
    if teal * 10 > n * 6 {
        Mark::Empty
    } else if gray * 10 > n * 8 && white * 100 < n * 3 {
        Mark::Locked
    } else {
        Mark::Owned
    }
}
