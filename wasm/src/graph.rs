// neko/graph.py's BannerGraph: a banner's pulls indexed by shared-stream position, with
// the track switch a rare dupe makes worked out.

use crate::roll::{BannerRolls, TrackPull, NONE, RARE, UBER};

/// What pulling at one stream position gives: the cat, where the stream continues, and
/// the RNG state after it.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Outcome {
    pub cat: u32,
    pub rarity: u8,
    pub next: usize,
    pub switched: bool,
    pub seed: u32,
}

/// A run of pulls (index, outcome), where the stream continues, and the cat held after.
pub type Chain = (Vec<(usize, Outcome)>, usize, u32);

pub struct Graph<'a> {
    pulls: Vec<Option<&'a TrackPull>>,
    rerolls: Vec<Option<&'a TrackPull>>,
    guaranteed: Vec<Option<&'a TrackPull>>,
    guaranteed_rerolls: Vec<Option<&'a TrackPull>>,
}

fn by_index(list: &[TrackPull], size: usize) -> Vec<Option<&TrackPull>> {
    let mut out = vec![None; size];
    for pull in list {
        if let Some(slot) = out.get_mut(pull.index()) {
            *slot = Some(pull);
        }
    }
    out
}

impl<'a> Graph<'a> {
    pub fn new(rolls: &'a BannerRolls) -> Self {
        let size = rolls.pulls.iter().map(|p| p.index() + 1).max().unwrap_or(0);
        Graph {
            pulls: by_index(&rolls.pulls, size),
            rerolls: by_index(&rolls.rerolls, size),
            guaranteed: by_index(&rolls.guaranteed, size),
            guaranteed_rerolls: by_index(&rolls.guaranteed_rerolls, size),
        }
    }

    pub fn pull(&self, index: usize) -> Option<&'a TrackPull> {
        self.pulls.get(index).copied().flatten()
    }

    /// The highest stream index rolled, if any.
    pub fn last_index(&self) -> Option<usize> {
        self.pulls.iter().rposition(Option::is_some)
    }

    /// The pull at ``index`` when the previous pull got ``last``: a rare repeating it
    /// rerolls, moving on past the usual +2 by its extra steps.
    pub fn resolve(&self, index: usize, last: u32) -> Option<Outcome> {
        let clean = self.pull(index)?;
        if last != NONE && clean.cat == last && clean.rarity == RARE {
            return Some(match self.rerolls.get(index).copied().flatten() {
                Some(r) => Outcome {
                    cat: r.cat,
                    rarity: r.rarity,
                    next: index + 2 + r.steps.max(1) as usize,
                    switched: true,
                    seed: r.seed,
                },
                // No reroll data for this cell: keep the dupe's name, assume one step.
                None => Outcome {
                    cat: clean.cat,
                    rarity: clean.rarity,
                    next: index + 3,
                    switched: true,
                    seed: clean.seed,
                },
            });
        }
        Some(Outcome {
            cat: clean.cat,
            rarity: clean.rarity,
            next: index + 2,
            switched: false,
            seed: clean.seed,
        })
    }

    /// The straight-chain view of ``index``: what godfat's grid shows.
    pub fn outcome(&self, index: usize) -> Option<Outcome> {
        let prev = index
            .checked_sub(2)
            .and_then(|i| self.pull(i))
            .map_or(NONE, |p| p.cat);
        self.resolve(index, prev)
    }

    /// What a dupe landing at ``index`` rerolls into.
    pub fn reroll(&self, index: usize) -> Option<Outcome> {
        self.rerolls.get(index).copied().flatten().map(|r| Outcome {
            cat: r.cat,
            rarity: r.rarity,
            next: index + 2 + r.steps.max(1) as usize,
            switched: true,
            seed: r.seed,
        })
    }

    /// Whether the straight chain hits the reroll at ``index`` (godfat's R cells).
    pub fn realized(&self, index: usize) -> bool {
        self.rerolls
            .get(index)
            .copied()
            .flatten()
            .is_some_and(|r| r.realized)
    }

    /// The guaranteed column's pull at ``index`` (the duped-start column with ``duped``).
    pub fn guaranteed_pull(&self, index: usize, duped: bool) -> Option<&'a TrackPull> {
        let column = if duped {
            &self.guaranteed_rerolls
        } else {
            &self.guaranteed
        };
        column.get(index).copied().flatten()
    }

    /// The uber a guaranteed multi started at ``index`` awards.
    pub fn guaranteed(&self, index: usize, duped: bool) -> Option<Outcome> {
        self.guaranteed_pull(index, duped).map(|p| Outcome {
            cat: p.cat,
            rarity: UBER,
            next: index + 1,
            switched: false,
            seed: p.seed,
        })
    }

    pub fn has_guaranteed(&self) -> bool {
        self.guaranteed.iter().any(Option::is_some)
    }

    /// The named rare at ``index`` - the only kind of cell a repeat can dupe.
    pub fn rare_at(&self, index: usize) -> Option<u32> {
        self.pull(index)
            .filter(|p| p.rarity == RARE && p.cat != NONE)
            .map(|p| p.cat)
    }

    /// Every stream index ``cat`` can come from here: a normal roll, a maybe-reroll, or
    /// either guaranteed column (where a multi awarding it has to start).
    pub fn spots(&self, cat: u32, into: &mut Vec<usize>) {
        for column in [
            &self.pulls,
            &self.rerolls,
            &self.guaranteed,
            &self.guaranteed_rerolls,
        ] {
            for (index, pull) in column.iter().enumerate() {
                if pull.is_some_and(|p| p.cat == cat) {
                    into.push(index);
                }
            }
        }
    }

    /// The farthest one pull can move the position: +2 nominal, +2+steps on a dupe.
    pub fn max_advance(&self) -> usize {
        2 + self
            .rerolls
            .iter()
            .flatten()
            .map(|r| r.steps.max(1) as usize)
            .max()
            .unwrap_or(1)
    }

    /// ``rolls`` pulls played from ``index`` holding ``last``: the outcomes, where the
    /// stream continues and the cat held after - None when it runs off the rolled window.
    pub fn chain(&self, mut index: usize, rolls: usize, mut last: u32) -> Option<Chain> {
        let mut pulls = Vec::with_capacity(rolls);
        for _ in 0..rolls {
            let outcome = self.resolve(index, last)?;
            pulls.push((index, outcome));
            last = outcome.cat;
            index = outcome.next;
        }
        Some((pulls, index, last))
    }
}
