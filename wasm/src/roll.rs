// neko/roll.py (and neko/normal.py's roll) in Rust: godfat's gacha roll - one XorShift32
// value stream read on two interleaved tracks, two values per cell, with the dupe rerolls
// and, for the rare gacha, the guaranteed columns. Cats are ids into the request's name
// table, so a dupe check is an integer compare. planner/test_engine_wasm.py holds it to
// the Python engine's exact output.

use serde::Deserialize;

use crate::seek::xorshift;

pub const NONE: u32 = u32::MAX; // an empty pool's "no cat" (godfat's id -1)
const BASE: u32 = 10_000;
// Bounce rerolls land a few positions ahead; roll this many extra rows so those landing
// cells exist.
const LANDING_BUFFER: usize = 4;

pub const RARE: u8 = 0;
pub const UBER: u8 = 2;

/// A banner's stack of rate bands: a pull's score (seed % 10000) walks the bands bottom-up,
/// the last one catching everything past the others, then its slot picks from that band's
/// pool. ``rerolls`` says which bands reroll a dupe: the rare gacha's Rare band only, the
/// normal machines' as each one has it.
#[derive(Clone, Debug, Deserialize)]
#[serde(from = "RawBanner")]
pub struct Banner {
    edges: Vec<u32>,
    pub pools: Vec<Vec<u32>>,
    rerolls: Vec<bool>,
}

/// A banner as requests spell it: each band's rate (the rare gacha leaves Legend's out -
/// it takes whatever the others don't) and pool, and the rerolling bands when they
/// aren't the rare gacha's.
#[derive(Deserialize)]
struct RawBanner {
    rates: Vec<u32>,
    pools: Vec<Vec<u32>>,
    #[serde(default)]
    reroll: Option<Vec<bool>>,
}

impl From<RawBanner> for Banner {
    fn from(raw: RawBanner) -> Self {
        let mut edges: Vec<u32> = raw
            .rates
            .iter()
            .scan(0, |total, rate| {
                *total += rate;
                Some(*total)
            })
            .collect();
        edges.truncate(raw.pools.len().saturating_sub(1));
        let rerolls = raw
            .reroll
            .unwrap_or_else(|| (0..raw.pools.len()).map(|p| p == 0).collect());
        Banner {
            edges,
            pools: raw.pools,
            rerolls,
        }
    }
}

impl Banner {
    fn rarity(&self, score: u32) -> u8 {
        self.edges
            .iter()
            .position(|&edge| score < edge)
            .unwrap_or(self.edges.len()) as u8
    }

    fn rerolls(&self, band: u8) -> bool {
        self.rerolls[usize::from(band)]
    }

    /// The band a score falls in.
    pub fn band(&self, score: u32) -> usize {
        usize::from(self.rarity(score))
    }

    pub fn rerolls_band(&self, band: usize) -> bool {
        self.rerolls[band]
    }
}

/// One pull at a 1-based position on track 0 (A) or 1 (B); see neko.models.TrackPull.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct TrackPull {
    pub position: u32,
    pub track: u8,
    pub cat: u32,
    pub rarity: u8,
    pub seed: u32,
    pub steps: u32,
    pub realized: bool,
    pub rarity_seed: u32,
}

impl TrackPull {
    /// The pull's index in the shared seed stream (graph.stream_index).
    pub fn index(&self) -> usize {
        2 * (self.position as usize - 1) + usize::from(self.track)
    }
}

#[derive(Debug, Default)]
pub struct BannerRolls {
    pub pulls: Vec<TrackPull>,
    pub guaranteed: Vec<TrackPull>,
    pub rerolls: Vec<TrackPull>,
    pub guaranteed_rerolls: Vec<TrackPull>,
    pub guaranteed_rolls: u32,
}

/// A cell of the grid or its reroll: where the play chain goes next.
#[derive(Clone, Copy)]
enum Link {
    Cell(usize, usize),
    Reroll(usize, usize),
}

struct Reroll {
    name: u32,
    slot_seed: u32,
    steps: u32,
    next: Option<Link>,
}

struct Cat {
    rarity: u8,
    reroll: bool, // its band rerolls dupes
    rarity_seed: u32,
    slot_seed: u32,
    name: u32,
    rerolled: Option<Reroll>,
    realized: bool,
    next: Option<Link>,
}

impl Cat {
    /// godfat's duped?: a named cat in a rerolling band that repeats the cat ``prev`` got.
    fn duped(&self, prev: u32) -> bool {
        self.reroll && self.name != NONE && self.name == prev
    }
}

fn pick(pool: &[u32], slot_seed: u32) -> u32 {
    if pool.is_empty() {
        NONE
    } else {
        pool[slot_seed as usize % pool.len()]
    }
}

/// godfat's reroll_cat: drop the dupe's slot from a copy of the pool and re-pick on the
/// next seed step, repeating while it stays the dupe.
fn reroll(name: u32, slot_seed: u32, pool: &[u32]) -> Reroll {
    let mut slots = pool.to_vec();
    let mut seed = slot_seed;
    let mut slot = slot_seed as usize % pool.len();
    let mut got = NONE;
    let mut steps = 0;
    let copies = pool.iter().filter(|&&c| c == name).count();
    for step in 1..=copies {
        seed = xorshift(seed);
        slots.remove(slot);
        steps = step as u32;
        if slots.is_empty() {
            break;
        }
        slot = seed as usize % slots.len();
        got = slots[slot];
        if got != name {
            break;
        }
    }
    Reroll {
        name: got,
        slot_seed: seed,
        steps,
        next: None,
    }
}

/// Roll ``rows`` positions into grid[seq][track] and link the play chain, rerolls and
/// bounces included (roll._build_grid).
fn build_grid(seed: u32, banner: &Banner, rows: usize, last_cat: u32) -> Vec<[Cat; 2]> {
    let mut values = Vec::with_capacity(2 * rows + 2);
    let mut state = seed;
    for _ in 0..2 * rows + 2 {
        state = xorshift(state);
        values.push(state);
    }

    let mut grid: Vec<[Cat; 2]> = (0..rows)
        .map(|seq| {
            std::array::from_fn(|track| {
                let index = 2 * seq + track;
                let (rarity_seed, slot_seed) = (values[index], values[index + 1]);
                let rarity = banner.rarity(rarity_seed % BASE);
                let pool = &banner.pools[usize::from(rarity)];
                let name = pick(pool, slot_seed);
                let rerolls = banner.rerolls(rarity);
                let rerolled = (rerolls && name != NONE).then(|| reroll(name, slot_seed, pool));
                Cat {
                    rarity,
                    reroll: rerolls,
                    rarity_seed,
                    slot_seed,
                    name,
                    rerolled,
                    realized: false,
                    next: None,
                }
            })
        })
        .collect();

    for seq in 1..rows {
        for track in 0..2 {
            let prev = grid[seq - 1][track].name;
            let realized = grid[seq][track].duped(prev);
            grid[seq][track].realized = realized;
            grid[seq - 1][track].next = Some(if realized {
                Link::Reroll(seq, track)
            } else {
                Link::Cell(seq, track)
            });
        }
    }

    if rows > 0 && last_cat != NONE && grid[0][0].duped(last_cat) {
        grid[0][0].realized = true;
    }

    // A reroll's extra step continues on the landing cell; a landing that repeats the
    // rerolled cat bounces into the landing's own reroll, which a realized chain realizes
    // too. Landings are always ahead, so one forward pass resolves every chain.
    for seq in 0..rows {
        for track in 0..2 {
            let Some(rerolled) = &grid[seq][track].rerolled else {
                continue;
            };
            let steps = rerolled.steps as usize;
            let (land_seq, land_track) =
                (seq + (track + steps) / 2 + 1, ((track + steps - 1) ^ 1) & 1);
            if land_seq >= rows {
                continue;
            }
            let name = rerolled.name;
            let realized = grid[seq][track].realized;
            let next = if grid[land_seq][land_track].duped(name) {
                grid[land_seq][land_track].realized |= realized;
                Link::Reroll(land_seq, land_track)
            } else {
                Link::Cell(land_seq, land_track)
            };
            if let Some(rerolled) = &mut grid[seq][track].rerolled {
                rerolled.next = Some(next);
            }
        }
    }
    grid
}

fn next_of(grid: &[[Cat; 2]], link: Link) -> Option<Link> {
    match link {
        Link::Cell(s, t) => grid[s][t].next,
        Link::Reroll(s, t) => grid[s][t].rerolled.as_ref().and_then(|r| r.next),
    }
}

/// Roll ``count`` positions of ``banner`` from ``seed`` (roll.roll_banner): every cell,
/// every named rare's reroll, and with ``guaranteed_rolls`` set the guaranteed-uber
/// columns keyed by a multi's first roll, for a clean start and a duped one.
pub fn roll_banner(
    seed: u32,
    banner: &Banner,
    count: usize,
    guaranteed_rolls: u32,
    last_cat: u32,
) -> BannerRolls {
    let rows = count + LANDING_BUFFER + 2 * guaranteed_rolls as usize;
    let grid = build_grid(seed, banner, rows, last_cat);
    // The rare gacha's Uber band; a normal machine has none and rolls no guaranteed column.
    let uber = banner
        .pools
        .get(usize::from(UBER))
        .map_or(&[][..], Vec::as_slice);

    let guaranteed_from = |start: Link, seq: usize, track: usize| -> Option<TrackPull> {
        let mut at = start;
        for _ in 0..guaranteed_rolls.saturating_sub(1) {
            at = next_of(&grid, at)?;
        }
        let (Link::Cell(s, t) | Link::Reroll(s, t)) = at;
        let slot_seed = grid[s][t].rarity_seed;
        Some(TrackPull {
            position: seq as u32 + 1,
            track: track as u8,
            cat: pick(uber, slot_seed),
            rarity: UBER,
            seed: slot_seed,
            steps: 0,
            realized: false,
            rarity_seed: 0,
        })
    };

    let mut out = BannerRolls {
        guaranteed_rolls,
        ..BannerRolls::default()
    };
    for (seq, row) in grid.iter().enumerate().take(count) {
        for (track, cat) in row.iter().enumerate() {
            let position = seq as u32 + 1;
            out.pulls.push(TrackPull {
                position,
                track: track as u8,
                cat: cat.name,
                rarity: cat.rarity,
                seed: cat.slot_seed,
                steps: 0,
                realized: false,
                rarity_seed: cat.rarity_seed,
            });
            if let Some(rerolled) = &cat.rerolled {
                out.rerolls.push(TrackPull {
                    position,
                    track: track as u8,
                    cat: rerolled.name,
                    rarity: cat.rarity,
                    seed: rerolled.slot_seed,
                    steps: rerolled.steps,
                    realized: cat.realized,
                    rarity_seed: 0,
                });
            }
            if guaranteed_rolls > 0 {
                out.guaranteed
                    .extend(guaranteed_from(Link::Cell(seq, track), seq, track));
                if cat.rerolled.is_some() {
                    out.guaranteed_rerolls.extend(guaranteed_from(
                        Link::Reroll(seq, track),
                        seq,
                        track,
                    ));
                }
            }
        }
    }
    out
}
