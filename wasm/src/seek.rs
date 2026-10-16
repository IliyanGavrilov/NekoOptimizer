// neko/seek.py's seed sieve, one candidate at a time instead of numpy lanes, so the 2^32
// sweep runs on the visitor's machine rather than the server. The Python module stays
// the reference; the tests below replay its results.

const BASE: u32 = 10_000; // rarity scores and rates are parts-per-10000
const SPACE: u64 = 1 << 32;
const PROGRESS_EVERY: u64 = 1 << 20; // candidates between progress reports

pub fn xorshift(mut x: u32) -> u32 {
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 15;
    x
}

fn undo_shift_xor(y: u32, shift: u32, left: bool) -> u32 {
    let mut x = y;
    for _ in (0..32).step_by(shift as usize) {
        x = y ^ if left { x << shift } else { x >> shift };
    }
    x
}

pub fn unxorshift(x: u32) -> u32 {
    let x = undo_shift_xor(x, 15, true);
    let x = undo_shift_xor(x, 17, false);
    undo_shift_xor(x, 13, true)
}

/// What to search for: the observed pulls as (pool, slot) pairs, the pools' cumulative
/// rate bands and sizes, and which pools reroll a dupe (bit per pool).
pub struct Spec {
    pub cats: Vec<(usize, u32)>,
    pub bands: Vec<u32>,
    pub sizes: Vec<u32>,
    pub rerollable: u32,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Match {
    pub seed_before: u32,
    pub seed_after: u32,
    pub run: u32,
}

impl Spec {
    fn rerolls(&self, pool: usize) -> bool {
        self.rerollable >> pool & 1 == 1 && self.sizes[pool] > 1
    }

    fn in_band(&self, pool: usize, score: u32) -> bool {
        self.bands[pool] <= score && score < self.bands[pool + 1]
    }

    /// The slot a pull lands on from ``state`` (its slot value), repicking a dupe of
    /// the previous pull in a rerolling pool; returns (slot, state after the pull).
    fn slot(&self, j: usize, mut state: u32) -> (u32, u32) {
        let (pool, _) = self.cats[j];
        let size = self.sizes[pool];
        let mut slot = state % size;
        if j > 0 && self.rerolls(pool) {
            let (prev_pool, prev_slot) = self.cats[j - 1];
            if prev_pool == pool && slot == prev_slot {
                state = xorshift(state);
                let repick = state % (size - 1);
                slot = repick + u32::from(repick >= prev_slot);
            }
        }
        (slot, state)
    }

    /// Whether pulls 1.. also match, from the state holding pull 0's slot value.
    fn sieve(&self, mut state: u32) -> bool {
        for j in 1..self.cats.len() {
            let (pool, want) = self.cats[j];
            state = xorshift(state);
            if !self.in_band(pool, state % BASE) {
                return false;
            }
            let (slot, next) = self.slot(j, xorshift(state));
            if slot != want {
                return false;
            }
            state = next;
        }
        true
    }

    /// Replay every pull from ``begin`` with full checks; the state after the last one.
    /// A run 1/2 start can't check its first pull, so it just consumes its three values.
    fn verify(&self, begin: u32, run: u32) -> Option<u32> {
        let mut seed = begin;
        for (j, &(pool, want)) in self.cats.iter().enumerate() {
            if run != 0 && j == 0 {
                seed = xorshift(xorshift(xorshift(seed)));
                continue;
            }
            seed = xorshift(seed);
            if !self.in_band(pool, seed % BASE) {
                return None;
            }
            let (slot, next) = self.slot(j, xorshift(seed));
            if slot != want {
                return None;
            }
            seed = next;
        }
        Some(seed)
    }
}

/// One run-type reading of the first pull: which candidate family it sweeps and how far
/// back a candidate sits from the window's opening state.
struct Pass {
    run: u32,
    m: u32,
    b: u32,
    by_rarity: bool,
    lo: u32,
    hi: u32,
    back: u32,
}

impl Pass {
    /// None when this reading can't apply: a repick (runs 1/2) needs a rerolling first
    /// pool, and slot 0 can't land at-or-above the shadow slot nor the last slot below it.
    fn new(spec: &Spec, run: u32) -> Option<Pass> {
        let (pool, slot) = spec.cats[0];
        let size = spec.sizes[pool];
        let (lo, hi) = (spec.bands[pool], spec.bands[pool + 1]);
        let (m, b, by_rarity) = if run == 0 {
            // Sieve whichever candidate family is smaller: stream values in the first
            // pull's band, or on its slot residue.
            let by_rarity = (SPACE / u64::from(BASE)) as f64 * f64::from(hi - lo)
                < (SPACE / u64::from(size)) as f64 * 1.5;
            (size, slot, by_rarity)
        } else if !spec.rerolls(pool) || (run == 1 && slot == size - 1) || (run == 2 && slot == 0) {
            return None;
        } else {
            (size - 1, slot - u32::from(run == 2), false)
        };
        let back = if by_rarity { 1 } else { 2 + u32::from(run > 0) };
        Some(Pass {
            run,
            m,
            b,
            by_rarity,
            lo,
            hi,
            back,
        })
    }

    /// The candidate index space: 10000-blocks of the band, or values on the residue.
    fn total(&self) -> u64 {
        if self.by_rarity {
            SPACE.div_ceil(u64::from(BASE))
        } else {
            (SPACE - 1 - u64::from(self.b)) / u64::from(self.m) + 1
        }
    }

    /// The match a candidate stream value yields, if its window plays out.
    fn check(&self, spec: &Spec, value: u32) -> Option<Match> {
        if value == 0 {
            return None; // the xorshift fixed point, never a live stream value
        }
        let state = if self.by_rarity {
            let state = xorshift(value);
            if state % self.m != self.b {
                return None;
            }
            state
        } else {
            value
        };
        if !spec.sieve(state) {
            return None;
        }
        let mut begin = value;
        for _ in 0..self.back {
            begin = unxorshift(begin);
        }
        let end = spec.verify(begin, self.run)?;
        Some(Match {
            seed_before: begin,
            seed_after: end,
            run: self.run,
        })
    }
}

/// How many candidates pass ``run`` sweeps - the index space ``scan`` slices - or 0 when
/// that reading of the first pull can't apply.
pub fn candidates(spec: &Spec, run: u32) -> u64 {
    Pass::new(spec, run).map_or(0, |pass| pass.total())
}

/// The matches among candidates ``from..to`` of pass ``run``, in seed-space order,
/// stopping at ``cap``. Slices scanned apart and concatenated in order give exactly what
/// one sweep would, which is what lets the page split a pass across workers.
pub fn scan(
    spec: &Spec,
    run: u32,
    from: u64,
    to: u64,
    cap: usize,
    progress: &mut impl FnMut(u32, f64),
) -> Vec<Match> {
    let mut found = Vec::new();
    let Some(pass) = Pass::new(spec, run) else {
        return found;
    };
    let to = to.min(pass.total());
    let span = to.saturating_sub(from).max(1) as f64;
    let every = if pass.by_rarity {
        (PROGRESS_EVERY / u64::from((pass.hi - pass.lo).max(1))).max(1)
    } else {
        PROGRESS_EVERY
    };

    for index in from..to {
        if pass.by_rarity {
            let block = index * u64::from(BASE);
            for offset in pass.lo..pass.hi {
                let value = block + u64::from(offset);
                if value >= SPACE {
                    break;
                }
                found.extend(pass.check(spec, value as u32));
                if found.len() >= cap {
                    return found;
                }
            }
        } else {
            found.extend(pass.check(spec, (index * u64::from(pass.m) + u64::from(pass.b)) as u32));
            if found.len() >= cap {
                return found;
            }
        }
        if (index - from).is_multiple_of(every) {
            progress(run, (index - from) as f64 / span);
        }
    }
    progress(run, 1.0);
    found
}

/// Every seed whose play reproduces ``spec.cats``: the clean reading first, then - only
/// when that finds nothing - the two dupe-repick readings of the first pull. The bool is
/// ``truncated``: past ``limit`` matches the window can't pin the seed down.
pub fn seek(spec: &Spec, limit: usize, progress: &mut impl FnMut(u32, f64)) -> (Vec<Match>, bool) {
    let mut found = scan(spec, 0, 0, candidates(spec, 0), limit + 1, progress);
    let mut truncated = found.len() > limit;
    if found.is_empty() {
        for run in [1, 2] {
            let cap = (limit + 1).saturating_sub(found.len()).max(1);
            found.extend(scan(spec, run, 0, candidates(spec, run), cap, progress));
            truncated |= found.len() > limit;
        }
    }
    (found, truncated)
}

// Expected results come from neko/seek.py on the same inputs (see neko/tests/test_seek.py).
#[cfg(test)]
mod tests {
    use super::*;

    fn spec(cats: &[(usize, u32)], bands: &[u32], sizes: &[u32], rerollable: u32) -> Spec {
        Spec {
            cats: cats.to_vec(),
            bands: bands.to_vec(),
            sizes: sizes.to_vec(),
            rerollable,
        }
    }

    fn m(seed_before: u32, seed_after: u32, run: u32) -> Match {
        Match {
            seed_before,
            seed_after,
            run,
        }
    }

    #[test]
    fn slices_scanned_apart_concatenate_to_one_sweep() {
        let spec = spec(
            &[(0, 7)],
            &[0, 10000, 10000, 10000, 10000],
            &[3000, 0, 0, 0],
            1,
        );
        let total = candidates(&spec, 0);
        let whole = scan(&spec, 0, 0, total, usize::MAX, &mut |_, _| {});
        let step = total.div_ceil(7);
        let sliced: Vec<Match> = (0..total)
            .step_by(step as usize)
            .flat_map(|from| scan(&spec, 0, from, from + step, usize::MAX, &mut |_, _| {}))
            .collect();
        assert_eq!(sliced, whole);
    }

    #[test]
    fn unxorshift_inverts_xorshift() {
        for x in [1, 7, 1893568593, u32::MAX] {
            assert_eq!(unxorshift(xorshift(x)), x);
        }
    }

    #[test]
    fn recovers_the_golden_seed() {
        let spec = spec(
            &[
                (0, 10),
                (0, 13),
                (0, 21),
                (0, 15),
                (0, 7),
                (0, 3),
                (0, 21),
                (0, 8),
            ],
            &[0, 7000, 9500, 10000, 10000],
            &[25, 18, 13, 0],
            1,
        );
        assert_eq!(
            seek(&spec, 20, &mut |_, _| {}),
            (vec![m(1893568593, 364859633, 0)], false)
        );
    }

    #[test]
    fn matches_a_window_with_a_repick_inside() {
        let spec = spec(
            &[(0, 2950), (0, 462), (0, 180), (0, 99), (0, 1884), (0, 364)],
            &[0, 10000, 10000, 10000, 10000],
            &[3000, 0, 0, 0],
            1,
        );
        assert_eq!(
            seek(&spec, 20, &mut |_, _| {}),
            (vec![m(3417762340, 2070524959, 0)], false)
        );
    }

    #[test]
    fn reads_a_first_pull_that_was_a_repick() {
        let spec = spec(
            &[(0, 364), (0, 1811), (0, 1200), (0, 50), (0, 1035)],
            &[0, 10000, 10000, 10000, 10000],
            &[3000, 0, 0, 0],
            1,
        );
        assert_eq!(
            seek(&spec, 20, &mut |_, _| {}),
            (vec![m(890350884, 3491143035, 1)], false)
        );
    }

    #[test]
    fn takes_the_rarity_method_for_a_narrow_band() {
        let spec = spec(
            &[(3, 68), (0, 63), (0, 68), (0, 237), (0, 119), (0, 265)],
            &[0, 6000, 8000, 9970, 10000],
            &[300, 200, 100, 100],
            1,
        );
        assert_eq!(
            seek(&spec, 20, &mut |_, _| {}),
            (vec![m(1114347809, 3527966665, 0)], false)
        );
    }

    #[test]
    fn truncates_an_underdetermined_window() {
        let spec = spec(
            &[(0, 7)],
            &[0, 10000, 10000, 10000, 10000],
            &[3000, 0, 0, 0],
            1,
        );
        assert_eq!(
            seek(&spec, 5, &mut |_, _| {}),
            (
                vec![
                    m(2738928134, 7, 0),
                    m(3249696638, 3007, 0),
                    m(1654993143, 6007, 0),
                    m(2511619432, 9007, 0),
                    m(613126117, 12007, 0),
                    m(1972290258, 15007, 0)
                ],
                true
            )
        );
    }

    #[test]
    fn finds_nothing_for_an_impossible_window() {
        let spec = spec(
            &[(0, 5), (0, 5)],
            &[0, 10000, 10000, 10000, 10000],
            &[3000, 0, 0, 0],
            1,
        );
        assert_eq!(seek(&spec, 20, &mut |_, _| {}), (vec![], false));
    }

    #[test]
    fn recovers_a_catseye_normal_seed() {
        let spec = spec(
            &[
                (1, 0),
                (1, 2),
                (1, 0),
                (1, 1),
                (1, 0),
                (1, 1),
                (1, 0),
                (0, 0),
                (1, 3),
                (1, 2),
            ],
            &[0, 500, 7400, 9400, 9900, 10000],
            &[1, 4, 2, 1, 1],
            2,
        );
        assert_eq!(
            seek(&spec, 20, &mut |_, _| {}),
            (
                vec![
                    m(3844582352, 1888247550, 0),
                    m(2350978938, 593305070, 0),
                    m(2510024623, 1413609740, 0),
                    m(3855806566, 498856870, 0),
                    m(1847614281, 1435470454, 0),
                    m(93837455, 3934816462, 0),
                    m(1174241811, 94240298, 0),
                    m(459729019, 3129808058, 0),
                    m(2418936605, 986247382, 0),
                    m(923467773, 2471488690, 0),
                    m(45955394, 1352474242, 0),
                    m(419859339, 3867753950, 0),
                    m(3712976640, 2048930534, 0),
                    m(2579524378, 2617919950, 0),
                    m(3513388030, 2500212366, 0),
                    m(2681850090, 2632695490, 0),
                    m(1823770763, 1064600798, 0),
                    m(1004867762, 2283692346, 0),
                    m(413264648, 2537670236, 0),
                    m(2437223184, 3262448266, 0),
                    m(686739351, 243282890, 0)
                ],
                true
            )
        );
    }

    #[test]
    fn recovers_a_wide_normal_seed() {
        let spec = spec(
            &[
                (0, 1660),
                (0, 488),
                (0, 2471),
                (0, 1865),
                (0, 182),
                (0, 228),
                (0, 2278),
                (0, 1450),
            ],
            &[0, 10000],
            &[3000],
            1,
        );
        assert_eq!(
            seek(&spec, 20, &mut |_, _| {}),
            (vec![m(1893568593, 1074130450, 0)], false)
        );
    }
}
