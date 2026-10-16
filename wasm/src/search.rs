// neko/search.py and neko/subsets.py in Rust: the cheapest pull plan for a set of target
// cats - A* (exact), a beam search (fast, bounded) and the per-subset breakdown. Every
// tie breaks the way the Python does (heap insertion order, stable sorts, the same float
// arithmetic), so the plans are the same plans; planner/test_plans_engine.py holds it to
// that.

use std::cmp::Ordering;
use std::collections::{BinaryHeap, HashMap, HashSet};

use crate::graph::Graph;
use crate::roll::NONE;

pub const DRAW: i64 = 150; // one paid pull = 150 catfood
const INF: f64 = f64::INFINITY;
const WORDS: usize = 8; // up to 512 targets

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Multi {
    pub rolls: usize,
    pub cost: i64,
    pub guaranteed: bool,
}

/// A set of collected targets, as bits over the search's target list.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Hash)]
pub struct Found([u64; WORDS]);

impl Found {
    fn with(mut self, bit: usize) -> Self {
        self.0[bit / 64] |= 1 << (bit % 64);
        self
    }

    fn has(&self, bit: usize) -> bool {
        self.0[bit / 64] >> (bit % 64) & 1 == 1
    }

    fn covers(&self, other: &Found) -> bool {
        self.0.iter().zip(other.0).all(|(a, b)| a & b == b)
    }

    /// How many of ``self``'s targets ``other`` holds.
    fn shared(&self, other: &Found) -> i64 {
        self.0
            .iter()
            .zip(other.0)
            .map(|(a, b)| i64::from((a & b).count_ones()))
            .sum()
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct State {
    pub position: usize,
    pub tickets: i64,
    pub draws: i64,
    pub found: Found,
    pub last_banner: Option<usize>,
    pub platinum: i64,
    pub legend: i64,
    pub last_cat: u32,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Pull {
    pub position: usize,
    pub banner: usize,
    pub cat: u32,
    pub rarity: u8,
    pub guaranteed: bool,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Kind {
    Single,
    Multi { rolls: usize, guaranteed: bool },
}

impl Kind {
    pub fn label(&self) -> String {
        match self {
            Kind::Single => "Single pull".to_owned(),
            Kind::Multi { rolls, guaranteed } => {
                format!(
                    "{rolls}-roll{}",
                    if *guaranteed { " (guaranteed)" } else { "" }
                )
            }
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Leg {
    pub banner: usize,
    pub kind: Kind,
    pub cost: i64,
    pub pulls: Vec<Pull>,
    pub currency: Currency,
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Hash)]
pub enum Currency {
    #[default]
    None,
    Platinum,
    Legend,
}

impl Currency {
    pub fn name(&self) -> &'static str {
        match self {
            Currency::None => "",
            Currency::Platinum => "platinum",
            Currency::Legend => "legend",
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Path {
    pub pulls: Vec<Pull>,
    pub tickets_used: i64,
    pub draws_used: i64,
    pub moves: Vec<Leg>,
    pub platinum_used: i64,
    pub legend_used: i64,
}

impl Path {
    /// Catfood spent (tickets are free).
    pub fn cost(&self) -> i64 {
        self.draws_used * DRAW
    }

    /// Moves with runs of single pulls on one banner merged, for display.
    pub fn legs(&self) -> Vec<Leg> {
        let mut merged: Vec<Leg> = Vec::new();
        for leg in &self.moves {
            match merged.last_mut() {
                Some(last)
                    if last.kind == Kind::Single
                        && leg.kind == Kind::Single
                        && last.banner == leg.banner =>
                {
                    last.cost += leg.cost;
                    last.pulls.extend_from_slice(&leg.pulls);
                }
                _ => merged.push(leg.clone()),
            }
        }
        merged
    }
}

/// The banners a search runs over, and what it's looking for.
pub struct World<'a> {
    pub graphs: Vec<Graph<'a>>,
    pub multis: Vec<Vec<Multi>>,
    pub currencies: Vec<Currency>,
    pub ticket_value: i64,
}

/// One search's targets: their cat ids, each one's bit, and where each can come from.
struct Targets {
    bits: HashMap<u32, usize>,
    all: Found,
    spots: Vec<Vec<usize>>, // per bit, sorted
}

impl Targets {
    fn new(world: &World, cats: &[u32]) -> Self {
        let mut bits = HashMap::new();
        let mut all = Found::default();
        let mut spots = Vec::new();
        for &cat in cats {
            if bits.contains_key(&cat) {
                continue;
            }
            let bit = bits.len();
            bits.insert(cat, bit);
            all = all.with(bit);
            let mut at = Vec::new();
            for graph in &world.graphs {
                graph.spots(cat, &mut at);
            }
            at.sort_unstable();
            spots.push(at);
        }
        Targets { bits, all, spots }
    }

    fn mark(&self, found: Found, cat: u32) -> Found {
        self.bits.get(&cat).map_or(found, |&bit| found.with(bit))
    }

    fn remaining(&self, found: &Found) -> impl Iterator<Item = usize> + '_ {
        let found = *found;
        (0..self.spots.len()).filter(move |&bit| !found.has(bit))
    }

    fn all_ahead(&self, found: &Found, position: usize) -> bool {
        self.remaining(found)
            .all(|bit| self.spots[bit].partition_point(|&p| p < position) < self.spots[bit].len())
    }
}

/// The targets that show up anywhere in the world - the rest can never be collected.
pub fn obtainable(world: &World, cats: &[u32]) -> Vec<u32> {
    let targets = Targets::new(world, cats);
    cats.iter()
        .copied()
        .filter(|cat| !targets.spots[targets.bits[cat]].is_empty())
        .collect()
}

fn canon_last(world: &World, position: usize, last: u32) -> u32 {
    if last != NONE
        && world
            .graphs
            .iter()
            .any(|g| g.rare_at(position) == Some(last))
    {
        last
    } else {
        NONE
    }
}

fn canon(world: &World, mut state: State) -> State {
    state.last_cat = canon_last(world, state.position, state.last_cat);
    state
}

fn multi_landing(graph: &Graph, position: usize, rolls: usize, last: u32) -> Option<usize> {
    graph
        .chain(position, rolls - 1, last)
        .map(|(_, at, _)| at + 1)
}

/// Can every target still be collected from ``start``, budget aside (bar the capsules'
/// own tickets)? A BFS keeping only the biggest found-sets per (position, last, tickets).
fn collectable(world: &World, targets: &Targets, start: &State) -> bool {
    let needed: Vec<usize> = targets.remaining(&start.found).collect();
    if needed.is_empty() {
        return true;
    }
    if !targets.all_ahead(&start.found, start.position) {
        return false;
    }
    let rolls_by_banner: Vec<Vec<usize>> = world
        .multis
        .iter()
        .map(|ms| {
            let mut rolls: Vec<usize> = ms
                .iter()
                .filter(|m| m.guaranteed)
                .map(|m| m.rolls)
                .collect();
            rolls.sort_unstable();
            rolls.dedup();
            rolls
        })
        .collect();

    type Key = (usize, u32, i64, i64);
    let origin: Key = (
        start.position,
        canon_last(world, start.position, start.last_cat),
        start.platinum,
        start.legend,
    );
    let mut seen: HashMap<Key, Vec<Found>> = HashMap::from([(origin, vec![Found::default()])]);
    let mut frontier = vec![(origin, Found::default())];
    // The BFS tracks only the targets still needed, from an empty set (start.found is
    // already in hand), and is done once those are all in.
    let need = {
        let mut f = Found::default();
        for &bit in &needed {
            f = f.with(bit);
        }
        f
    };

    while !frontier.is_empty() {
        let mut upcoming = Vec::new();
        for ((pos, last, platinum, legend), found) in frontier {
            for (g, graph) in world.graphs.iter().enumerate() {
                let Some(outcome) = graph.resolve(pos, last) else {
                    continue;
                };
                let mut moves = Vec::new();
                match world.currencies[g] {
                    Currency::Platinum => {
                        if platinum > 0 {
                            moves.push((outcome.cat, outcome.next, platinum - 1, legend));
                        }
                    }
                    Currency::Legend => {
                        if legend > 0 {
                            moves.push((outcome.cat, outcome.next, platinum, legend - 1));
                        }
                    }
                    Currency::None => {
                        moves.push((outcome.cat, outcome.next, platinum, legend));
                        if let Some(forced) = graph.guaranteed(pos, outcome.switched) {
                            for &rolls in &rolls_by_banner[g] {
                                if let Some(landing) = multi_landing(graph, pos, rolls, last) {
                                    moves.push((forced.cat, landing, platinum, legend));
                                }
                            }
                        }
                    }
                }
                for (cat, next, plat, leg) in moves {
                    let got = match targets.bits.get(&cat) {
                        Some(&bit) if need.has(bit) => found.with(bit),
                        _ => found,
                    };
                    if got.covers(&need) {
                        return true;
                    }
                    let key = (next, canon_last(world, next, cat), plat, leg);
                    let kept = seen.entry(key).or_default();
                    if kept.iter().any(|other| other.covers(&got)) {
                        continue;
                    }
                    kept.retain(|other| !got.covers(other));
                    kept.push(got);
                    upcoming.push((key, got));
                }
            }
        }
        frontier = upcoming;
    }
    false
}

fn multi_floor(world: &World) -> f64 {
    world
        .multis
        .iter()
        .flatten()
        .map(|m| m.cost as f64 / m.rolls as f64)
        .fold(INF, f64::min)
}

/// A lower bound on what's left: pulls needed to reach the farthest remaining target,
/// each at the cheapest price any pull can have.
fn heuristic(
    targets: &Targets,
    state: &State,
    ticket_value: i64,
    floor: f64,
    advance: usize,
) -> f64 {
    let mut worst = 0;
    for bit in targets.remaining(&state.found) {
        let spots = &targets.spots[bit];
        let index = spots.partition_point(|&p| p < state.position);
        if index == spots.len() {
            return INF;
        }
        worst = worst.max((spots[index] - state.position) / advance + 1);
    }
    if worst == 0 {
        return 0.0;
    }
    let floor = (DRAW as f64).min(floor);
    let cheapest = (ticket_value as f64).min(floor);
    let ticketed = (worst as i64).min(state.tickets);
    ticketed as f64 * cheapest + (worst as i64 - ticketed) as f64 * floor
}

fn moves(world: &World, targets: &Targets, state: &State, g: usize) -> Vec<(State, Leg)> {
    let graph = &world.graphs[g];
    let mut out = Vec::new();
    let currency = world.currencies[g];
    if currency != Currency::None {
        let pool = if currency == Currency::Platinum {
            state.platinum
        } else {
            state.legend
        };
        if pool <= 0 {
            return out;
        }
        let Some(outcome) = graph.resolve(state.position, state.last_cat) else {
            return out;
        };
        let pull = Pull {
            position: state.position,
            banner: g,
            cat: outcome.cat,
            rarity: outcome.rarity,
            guaranteed: false,
        };
        let next = State {
            position: outcome.next,
            found: targets.mark(state.found, outcome.cat),
            last_banner: Some(g),
            platinum: state.platinum - i64::from(currency == Currency::Platinum),
            legend: state.legend - i64::from(currency == Currency::Legend),
            last_cat: outcome.cat,
            ..*state
        };
        out.push((
            next,
            Leg {
                banner: g,
                kind: Kind::Single,
                cost: 0,
                pulls: vec![pull],
                currency,
            },
        ));
        return out;
    }

    if let Some(outcome) = graph.resolve(state.position, state.last_cat) {
        let found = targets.mark(state.found, outcome.cat);
        let pull = Pull {
            position: state.position,
            banner: g,
            cat: outcome.cat,
            rarity: outcome.rarity,
            guaranteed: false,
        };
        let can_ticket = state.tickets > 0;
        let mut can_catfood = state.draws > 0;
        if can_ticket && can_catfood && world.ticket_value <= DRAW {
            can_catfood = false;
        }
        let base = State {
            position: outcome.next,
            found,
            last_banner: Some(g),
            last_cat: outcome.cat,
            ..*state
        };
        if can_ticket {
            out.push((
                State {
                    tickets: state.tickets - 1,
                    ..base
                },
                Leg {
                    banner: g,
                    kind: Kind::Single,
                    cost: 0,
                    pulls: vec![pull],
                    currency,
                },
            ));
        }
        if can_catfood {
            out.push((
                State {
                    draws: state.draws - 1,
                    ..base
                },
                Leg {
                    banner: g,
                    kind: Kind::Single,
                    cost: DRAW,
                    pulls: vec![pull],
                    currency,
                },
            ));
        }
    }

    for multi in &world.multis[g] {
        let draws = multi.cost / DRAW;
        if state.draws < draws {
            continue;
        }
        let Some(first) = graph.resolve(state.position, state.last_cat) else {
            continue;
        };
        let forced = if multi.guaranteed {
            graph.guaranteed(state.position, first.switched)
        } else {
            None
        };
        if multi.guaranteed && forced.is_none() {
            continue;
        }
        let normal = if multi.guaranteed {
            multi.rolls - 1
        } else {
            multi.rolls
        };
        let Some((walked, mut position, mut last)) =
            graph.chain(state.position, normal, state.last_cat)
        else {
            continue;
        };
        let mut found = state.found;
        let mut pulls: Vec<Pull> = walked
            .iter()
            .map(|&(at, o)| {
                found = targets.mark(found, o.cat);
                Pull {
                    position: at,
                    banner: g,
                    cat: o.cat,
                    rarity: o.rarity,
                    guaranteed: false,
                }
            })
            .collect();
        if let Some(forced) = forced {
            pulls.push(Pull {
                position: state.position,
                banner: g,
                cat: forced.cat,
                rarity: forced.rarity,
                guaranteed: true,
            });
            found = targets.mark(found, forced.cat);
            last = forced.cat;
            position += 1;
        }
        let next = State {
            position,
            draws: state.draws - draws,
            found,
            last_banner: Some(g),
            last_cat: last,
            ..*state
        };
        let kind = Kind::Multi {
            rolls: multi.rolls,
            guaranteed: multi.guaranteed,
        };
        out.push((
            next,
            Leg {
                banner: g,
                kind,
                cost: multi.cost,
                pulls,
                currency,
            },
        ));
    }
    out
}

type Cost = (i64, i64, i64); // catfood-equivalent, banner switches, catfood

fn step_cost(world: &World, state: &State, next: &State, leg: &Leg) -> Cost {
    let tickets = state.tickets - next.tickets;
    let platinum = state.platinum - next.platinum;
    let legend = state.legend - next.legend;
    let catfood = (state.draws - next.draws) * DRAW;
    let switch = i64::from(state.last_banner.is_some_and(|b| b != leg.banner));
    (
        catfood + (tickets + platinum + legend) * world.ticket_value,
        switch,
        catfood,
    )
}

fn add(a: Cost, b: Cost) -> Cost {
    (a.0 + b.0, a.1 + b.1, a.2 + b.2)
}

fn reconstruct(goal: &State, came_from: &HashMap<State, (State, Leg)>, start: &State) -> Path {
    let mut legs = Vec::new();
    let mut state = *goal;
    while let Some((previous, leg)) = came_from.get(&state) {
        legs.push(leg.clone());
        state = *previous;
    }
    legs.reverse();
    Path {
        pulls: legs.iter().flat_map(|l| l.pulls.iter().copied()).collect(),
        tickets_used: start.tickets - goal.tickets,
        draws_used: start.draws - goal.draws,
        moves: legs,
        platinum_used: start.platinum - goal.platinum,
        legend_used: start.legend - goal.legend,
    }
}

/// A heap entry, popped smallest (priority, then insertion order) first.
struct Entry {
    priority: (f64, i64, i64),
    order: u64,
    g: Cost,
    state: State,
}

impl PartialEq for Entry {
    fn eq(&self, other: &Self) -> bool {
        self.cmp(other) == Ordering::Equal
    }
}
impl Eq for Entry {}
impl PartialOrd for Entry {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}
impl Ord for Entry {
    fn cmp(&self, other: &Self) -> Ordering {
        // Reversed: BinaryHeap pops the greatest.
        other
            .priority
            .0
            .total_cmp(&self.priority.0)
            .then(other.priority.1.cmp(&self.priority.1))
            .then(other.priority.2.cmp(&self.priority.2))
            .then(other.order.cmp(&self.order))
    }
}

fn below(new_g: Cost, best: Option<&Cost>) -> bool {
    best.is_none_or(|b| new_g < *b)
}

/// The cheapest plan collecting every target, or None (search.astar).
pub fn astar(world: &World, cats: &[u32], start: &State, upper_bound: f64) -> Option<Path> {
    let targets = Targets::new(world, cats);
    if !collectable(world, &targets, start) {
        return None;
    }
    let floor = multi_floor(world);
    let advance = world
        .graphs
        .iter()
        .map(Graph::max_advance)
        .max()
        .unwrap_or(3);
    let mut g_score: HashMap<State, Cost> = HashMap::from([(*start, (0, 0, 0))]);
    let mut came_from: HashMap<State, (State, Leg)> = HashMap::new();
    let mut order = 0;
    let h0 = heuristic(&targets, start, world.ticket_value, floor, advance);
    let mut heap = BinaryHeap::from([Entry {
        priority: (h0, 0, 0),
        order,
        g: (0, 0, 0),
        state: *start,
    }]);

    while let Some(Entry { g, state, .. }) = heap.pop() {
        if g > g_score[&state] {
            continue;
        }
        if state.found.covers(&targets.all) {
            return Some(reconstruct(&state, &came_from, start));
        }
        for gi in 0..world.graphs.len() {
            for (next, leg) in moves(world, &targets, &state, gi) {
                let next = canon(world, next);
                let new_g = add(g, step_cost(world, &state, &next, &leg));
                if below(new_g, g_score.get(&next)) {
                    let h = heuristic(&targets, &next, world.ticket_value, floor, advance);
                    if h == INF || new_g.0 as f64 + h > upper_bound {
                        continue;
                    }
                    g_score.insert(next, new_g);
                    came_from.insert(next, (state, leg));
                    order += 1;
                    heap.push(Entry {
                        priority: (new_g.0 as f64 + h, new_g.1, new_g.2),
                        order,
                        g: new_g,
                        state: next,
                    });
                }
            }
        }
    }
    None
}

/// Keep the ``width`` most promising paths each step; with ``partial``, the biggest haul
/// when nothing collects them all (search.beam_search).
pub fn beam_search(
    world: &World,
    cats: &[u32],
    start: &State,
    width: usize,
    partial: bool,
) -> Option<Path> {
    let targets = Targets::new(world, cats);
    if start.found.covers(&targets.all) {
        return Some(reconstruct(start, &HashMap::new(), start));
    }
    if !partial && !targets.all_ahead(&start.found, start.position) {
        return None;
    }
    let floor = multi_floor(world);
    let advance = world
        .graphs
        .iter()
        .map(Graph::max_advance)
        .max()
        .unwrap_or(3);
    let mut best_cost: HashMap<State, Cost> = HashMap::from([(*start, (0, 0, 0))]);
    let mut came_from: HashMap<State, (State, Leg)> = HashMap::new();
    let mut best_goal: Option<(State, Cost)> = None;
    let mut best_haul: Option<(State, (i64, Cost))> = None;
    let mut frontier = vec![*start];

    while !frontier.is_empty() {
        let mut ranked: Vec<((f64, i64, i64), State)> = Vec::new();
        for state in &frontier {
            let g = best_cost[state];
            for gi in 0..world.graphs.len() {
                for (next, leg) in moves(world, &targets, state, gi) {
                    let next = canon(world, next);
                    let new_g = add(g, step_cost(world, state, &next, &leg));
                    if !below(new_g, best_cost.get(&next)) {
                        continue;
                    }
                    best_cost.insert(next, new_g);
                    came_from.insert(next, (*state, leg));

                    let hits = if partial {
                        targets.all.shared(&next.found)
                    } else {
                        0
                    };
                    if hits > 0 && best_haul.is_none_or(|(_, key)| (-hits, new_g) < key) {
                        best_haul = Some((next, (-hits, new_g)));
                    }
                    if next.found.covers(&targets.all) {
                        if best_goal.is_none_or(|(_, cost)| new_g < cost) {
                            best_goal = Some((next, new_g));
                        }
                        continue;
                    }
                    let h = heuristic(&targets, &next, world.ticket_value, floor, advance);
                    if h == INF {
                        continue;
                    }
                    ranked.push(((new_g.0 as f64 + h, new_g.1, new_g.2), next));
                }
            }
        }
        ranked.sort_by(|a, b| {
            a.0 .0
                .total_cmp(&b.0 .0)
                .then(a.0 .1.cmp(&b.0 .1))
                .then(a.0 .2.cmp(&b.0 .2))
        });
        frontier = ranked.into_iter().take(width).map(|(_, s)| s).collect();
    }

    if let Some((goal, _)) = best_goal {
        return Some(reconstruct(&goal, &came_from, start));
    }
    best_haul.map(|(state, _)| reconstruct(&state, &came_from, start))
}

/// A plan's price in catfood-equivalent (subsets._spent).
pub fn spent(plan: &Path, ticket_value: i64) -> i64 {
    plan.cost() + (plan.tickets_used + plan.platinum_used + plan.legend_used) * ticket_value
}

pub struct SubsetPlan {
    pub targets: Vec<u32>, // sorted by name
    pub plan: Path,
}

/// Every k-subset of ``items`` in itertools.combinations order.
pub fn combinations(items: &[u32], k: usize) -> Vec<Vec<u32>> {
    let n = items.len();
    let mut out = Vec::new();
    if k > n {
        return out;
    }
    let mut idx: Vec<usize> = (0..k).collect();
    loop {
        out.push(idx.iter().map(|&i| items[i]).collect());
        let Some(i) = (0..k).rev().find(|&i| idx[i] != i + n - k) else {
            return out;
        };
        idx[i] += 1;
        for j in i + 1..k {
            idx[j] = idx[j - 1] + 1;
        }
    }
}

/// The best plan for every reachable subset, biggest first then cheapest
/// (subsets.solve_subsets). ``items`` come sorted by name.
pub fn solve_subsets(
    world: &World,
    items: &[u32],
    start: &State,
    names: &dyn Fn(&[u32]) -> Vec<String>,
) -> Vec<SubsetPlan> {
    let mut plans: Vec<SubsetPlan> = Vec::new();
    let mut bounds: Vec<(HashSet<u32>, i64)> = Vec::new();
    for size in (1..=items.len()).rev() {
        for combo in combinations(items, size) {
            let wanted: HashSet<u32> = combo.iter().copied().collect();
            let bound = bounds
                .iter()
                .filter(|(key, _)| wanted.is_subset(key))
                .map(|&(_, cost)| cost as f64)
                .fold(INF, f64::min);
            if let Some(plan) = astar(world, &combo, start, bound) {
                bounds.push((wanted, spent(&plan, world.ticket_value)));
                plans.push(SubsetPlan {
                    targets: combo,
                    plan,
                });
            }
        }
    }
    plans.sort_by(|a, b| {
        (b.targets.len().cmp(&a.targets.len()))
            .then(spent(&a.plan, world.ticket_value).cmp(&spent(&b.plan, world.ticket_value)))
            .then(a.plan.cost().cmp(&b.plan.cost()))
            .then(names(&a.targets).cmp(&names(&b.targets)))
    });
    plans
}
