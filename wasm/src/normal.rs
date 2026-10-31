// The Normal Capsules page, worked out here instead of the server: planner.services'
// build_normal_tracks and build_normal_plan over neko/normal.py's roll and
// neko/normal_plan.py's beam search, and the _normal_tracks.html / _normal_cell.html /
// _normal_plan.html markup. planner/test_normal_engine.py holds them to the Python.

use std::collections::{HashMap, HashSet};
use std::fmt::Write;

use serde::Deserialize;

use crate::engine::Request;
use crate::roll::{roll_banner, BannerRolls, TrackPull, NONE};
use crate::seek::xorshift;
use crate::tracks::esc;

const BASE: u32 = 10_000;
const BEAM: usize = 200;
const MAX_ROLLS: i64 = 500;
const CHEAP: &str = "Normal Cat Ticket";
const CURRENCIES: [&str; 3] = [CHEAP, "Lucky Ticket", "Lucky Ticket G"];
/// The page's budget field for each of CURRENCIES.
const BUDGETS: [&str; 3] = ["normal", "lucky", "luckyg"];
/// Most pulls in one plan step, so a long run on one machine reads as 10-pull steps.
const STEP_PULLS: usize = 10;
const DICE: &str = "<svg width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" aria-hidden=\"true\"><use href=\"#dice-icon\"/></svg>\n";

#[derive(Deserialize)]
pub struct NormalArgs {
    /// Per name: its catalogue unit id and form names joined by "|", for a cat item.
    pub units: Vec<Option<(u32, String)>>,
    /// Per name: what the page shows for the item - the game version's own name for it.
    /// The name table keeps the English, the item's identity (the dupe memory posts it).
    #[serde(default)]
    pub labels: Vec<String>,
    pub upgrades: Vec<u32>,
    #[serde(default)]
    pub plan: Option<PlanArgs>,
}

#[derive(Deserialize)]
pub struct PlanArgs {
    pub label: String,
    pub targets: Vec<u32>,
    /// Each currency's rolls and the banners (request indices) it feeds, dearest first.
    pub budgets: Vec<(i64, Vec<usize>)>,
    /// Banners the table shows only when the plan pulls them (a lucky machine your stash
    /// brought in).
    #[serde(default)]
    pub optional: Vec<usize>,
}

impl NormalArgs {
    fn label<'a>(&'a self, req: &'a Request, id: u32) -> &'a str {
        self.labels
            .get(id as usize)
            .map_or_else(|| req.name(id), String::as_str)
    }
}

/// How many of a normal-side currency, in the interface language ("3 Lucky Tickets").
fn currency_count(req: &Request, currency: &str, n: usize) -> String {
    let (singular, plural) = match currency {
        "Lucky Ticket" => ("%(n)s Lucky Ticket", "%(n)s Lucky Tickets"),
        "Lucky Ticket G" => ("%(n)s Lucky Ticket G", "%(n)s Lucky Ticket Gs"),
        _ => ("%(n)s Normal Cat Ticket", "%(n)s Normal Cat Tickets"),
    };
    req.trn(singular, plural, n as i64, &[("n", &n.to_string())])
}

/// One pull of a normal banner from ``seed`` holding ``last`` (normal.pull_once): the item,
/// the state after it, and the extra values a dupe's cascade used.
fn pull_once(req: &Request, banner: usize, seed: u32, last: u32) -> (u32, u32, u32) {
    let b = &req.banners[banner];
    let mut seed = xorshift(seed);
    let score = seed % BASE;
    let pool_index = b.banner.band(score);
    let pool = &b.banner.pools[pool_index];
    seed = xorshift(seed);
    let mut slots = pool.clone();
    let mut slot = seed as usize % slots.len();
    let mut name = slots[slot];
    let mut steps = 0;
    if b.banner.rerolls_band(pool_index) && name != NONE && name == last {
        let copies = pool.iter().filter(|&&c| c == name).count();
        for _ in 0..copies {
            seed = xorshift(seed);
            steps += 1;
            slots.remove(slot);
            if slots.is_empty() {
                break;
            }
            slot = seed as usize % slots.len();
            if slots[slot] != name {
                break;
            }
        }
        name = if slots.is_empty() { NONE } else { slots[slot] };
    }
    (name, seed, steps)
}

/// The 1-based cell a reroll's extra ``steps`` land the chain on (normal.landing).
fn landing(position: usize, track: usize, steps: usize) -> (usize, usize) {
    (
        position + (track + steps) / 2 + 1,
        ((track + steps - 1) ^ 1) & 1,
    )
}

#[derive(Clone)]
struct Step {
    machine: usize,
    item: u32,
    position: usize,
    track: usize,
    dupe: bool,
    target: bool,
}

#[derive(Clone)]
struct Node {
    seed: u32,
    position: usize,
    track: usize,
    last: u32,
    budgets: Vec<i64>,
    hits: i64,
    forced: i64,
    steps: Vec<Step>,
}

impl Node {
    /// More hits first, then the fewest forced track changes (the longest runs on one
    /// machine), then the most left of each budget in turn (the page sends at most
    /// three), then the fewest rolls.
    fn rank(&self) -> (i64, i64, [i64; 3], usize) {
        let mut kept = [0; 3];
        for (slot, count) in kept.iter_mut().zip(&self.budgets) {
            *slot = -count;
        }
        (-self.hits, self.forced, kept, self.steps.len())
    }
}

/// The pull sequence from ``seed`` collecting the most targets (normal_plan.plan_normal):
/// a beam over the shared stream, one machine per pull, keeping the dearest budgets.
fn plan(req: &Request, seed: u32, last: u32, args: &PlanArgs) -> Node {
    let targets: HashSet<u32> = args.targets.iter().copied().collect();
    let groups: Vec<(i64, &Vec<usize>)> = args
        .budgets
        .iter()
        .filter(|(count, keys)| *count > 0 && !keys.is_empty())
        .map(|(count, keys)| ((*count).min(MAX_ROLLS), keys))
        .collect();
    let start = Node {
        seed,
        position: 1,
        track: 0,
        last,
        budgets: groups.iter().map(|(count, _)| *count).collect(),
        hits: 0,
        forced: 0,
        steps: Vec::new(),
    };
    if groups.is_empty() || targets.is_empty() {
        return start;
    }
    let choices: Vec<(usize, usize)> = groups
        .iter()
        .enumerate()
        .flat_map(|(i, (_, keys))| keys.iter().map(move |&k| (i, k)))
        .collect();
    let depth = start.budgets.iter().sum::<i64>().min(MAX_ROLLS);
    let mut best = start.clone();
    let mut nodes = vec![start];

    for _ in 0..depth {
        // Python's dict: a better child for a seen state takes that state's first slot.
        let mut order: Vec<Node> = Vec::new();
        let mut at: HashMap<(u32, u32, Vec<i64>, usize), usize> = HashMap::new();
        for node in &nodes {
            for &(index, key) in &choices {
                if node.budgets[index] == 0 {
                    continue;
                }
                let (item, after, extra) = pull_once(req, key, node.seed, node.last);
                let dupe = extra > 0;
                let hit = targets.contains(&item);
                // A dupe only this machine deals, where the one before it would roll on.
                let previous = node.steps.last().map_or(key, |s| s.machine);
                let forced = dupe
                    && previous != key
                    && pull_once(req, previous, node.seed, node.last).2 == 0;
                let step = Step {
                    machine: key,
                    item,
                    position: node.position,
                    track: node.track,
                    dupe,
                    target: hit,
                };
                let (position, track) = if dupe {
                    landing(node.position, node.track, extra as usize)
                } else {
                    (node.position + 1, node.track)
                };
                let mut budgets = node.budgets.clone();
                budgets[index] -= 1;
                let mut steps = node.steps.clone();
                steps.push(step);
                let child = Node {
                    seed: after,
                    position,
                    track,
                    last: item,
                    budgets,
                    hits: node.hits + i64::from(hit),
                    forced: node.forced + i64::from(forced),
                    steps,
                };
                if hit && child.rank() < best.rank() {
                    best = child.clone();
                }
                // The machine you're on joins the state: it decides which dupes are forced.
                let state = (child.seed, child.last, child.budgets.clone(), key);
                match at.get(&state) {
                    Some(&i) => {
                        if child.rank() < order[i].rank() {
                            order[i] = child;
                        }
                    }
                    None => {
                        at.insert(state, order.len());
                        order.push(child);
                    }
                }
            }
        }
        order.sort_by_key(Node::rank);
        order.truncate(BEAM);
        nodes = order;
        if nodes.is_empty() {
            break;
        }
    }
    best
}

/// A plan's lit cells: (position, track) -> banner -> (dupe, target, step).
type Marks = HashMap<(usize, usize), HashMap<usize, (bool, bool, usize)>>;

struct Column {
    tag: usize,
    banner: usize,
    rolls: BannerRolls,
}

impl Column {
    fn pull(&self, position: usize, track: usize) -> &TrackPull {
        &self.rolls.pulls[2 * (position - 1) + track]
    }

    fn reroll(&self, position: usize, track: usize) -> Option<&TrackPull> {
        self.rolls.rerolls.iter().find(|r| {
            r.position as usize == position && usize::from(r.track) == track && r.realized
        })
    }
}

const TRACKS: [&str; 2] = ["A", "B"];

/// The merged A/B table over the chosen banners (build_normal_tracks + _normal_tracks.html).
fn tracks(
    req: &Request,
    args: &NormalArgs,
    banners: &[usize],
    rows: usize,
    marks: &Marks,
) -> String {
    let last = req.id(&req.last_cat);
    let columns: Vec<Column> = banners
        .iter()
        .enumerate()
        .map(|(i, &b)| Column {
            tag: i + 1,
            banner: b,
            rolls: roll_banner(req.seed, &req.banners[b].banner, rows, 0, last),
        })
        .collect();
    if columns.is_empty() || rows == 0 {
        return format!(
            "\n<p class=\"muted\">{}</p>\n",
            req.t("Pick at least one capsule machine to roll.")
        );
    }
    let upgrades: HashSet<u32> = args.upgrades.iter().copied().collect();
    let dark = req.id("Dark Catseye");
    let unit = |id: u32| args.units.get(id as usize).and_then(Option::as_ref);

    let t = |s| req.t(s);
    let mut out = format!(
        "\n<details class=\"track-guide\">\n<summary>{}</summary>\n<ul class=\"symbol-legend\">\n<li><span class=\"sym\">A / B</span> {}</li>\n<li><span class=\"sym dice-sym\">{DICE}</span> {}</li>\n<li><span class=\"arrow sample\">&#8627; {}</span> {}</li>\n<li><span class=\"item sample\" data-pool=\"2\">{}</span> <span class=\"sep\">&middot;</span> <span class=\"item sample\" data-pool=\"3\">{}</span> <span class=\"sep\">&middot;</span> <span class=\"item sample\" data-pool=\"4\">{}</span> {}</li>\n<li><span class=\"item upgrade sample\">{}</span> {}</li>\n<li><span class=\"item dark-catseye sample\">{}</span> {}</li>\n<li><span class=\"entry on-path sample\">{}</span> {} <span class=\"sep\">&middot;</span> <span class=\"entry target sample\"><span class=\"item got\">{}</span></span> {}</li>\n</ul>\n</details>\n",
        t("Legend"),
        t("alternate timelines; a dupe rerolls and switches track"),
        t("&ldquo;I rolled this cell&rdquo; &mdash; jumps the seed to just after it"),
        t("if dupe"),
        t("the reroll branch (its own dice &amp; landing)"),
        t("gold"),
        t("red"),
        t("aqua"),
        t("the machine's rarer rate bands, scarcest last"),
        t("blue"),
        t("an upgrade (Special Skill), not a cat"),
        t("Dark Catseye"),
        t("the 1% Catseye-event jackpot"),
        t("path"),
        t("a planned pull"),
        t("target"),
        t("what it collects"),
    );
    // The banner legend is the thead's first row, so the two stick as one block.
    out.push_str("<table class=\"track normal-track\">\n<thead>\n");
    if columns.len() > 1 {
        out.push_str("<tr class=\"legend-row\"><th colspan=\"3\"><ul class=\"track-legend\">\n");
        for c in &columns {
            let _ = writeln!(
                out,
                "<li><span class=\"tag\">{}</span> {}</li>",
                c.tag,
                esc(&req.banners[c.banner].name)
            );
        }
        out.push_str("</ul></th></tr>\n");
    }
    let _ = write!(
        out,
        "<tr>\n<th class=\"pos\">#</th>\n<th>{}</th>\n<th>{}</th>\n</tr></thead>\n<tbody>\n",
        req.t("Track A"),
        req.t("Track B")
    );
    let none = HashMap::new();
    for position in 1..=rows {
        let _ = write!(
            out,
            "<tr>\n<th scope=\"row\" class=\"pos\">{position}</th>\n"
        );
        for track in 0..TRACKS.len() {
            let cell_marks = marks.get(&(position, track)).unwrap_or(&none);
            out.push_str("\n<td class=\"cell\">");
            for c in &columns {
                let pull = c.pull(position, track);
                let mark = cell_marks.get(&c.banner);
                let target = mark.is_some_and(|&(dupe, target, _)| !dupe && target);
                let alt = c.reroll(position, track);
                let alt_target =
                    alt.is_some() && mark.is_some_and(|&(dupe, target, _)| dupe && target);
                out.push_str("<div class=\"entry");
                if mark.is_some() {
                    out.push_str(" on-path");
                }
                if target {
                    out.push_str(" target");
                }
                if alt_target {
                    out.push_str(" target");
                }
                out.push('"');
                let step = mark.map(|&(_, _, step)| step).filter(|&s| s != 0);
                if let Some(step) = step {
                    let _ = write!(out, " data-step=\"{step}\"");
                }
                out.push_str("><span class=\"entry-name\">");
                if let Some(step) = step {
                    let _ = write!(
                        out,
                        "<span class=\"step-dot\" aria-hidden=\"true\">{step}</span> "
                    );
                }
                if columns.len() > 1 {
                    let _ = write!(out, "<span class=\"tag\">{}</span> ", c.tag);
                }
                let item = esc(args.label(req, pull.cat));
                let pool = pull.rarity;
                match unit(pull.cat) {
                    Some((uid, forms)) => {
                        let _ = write!(
                            out,
                            "<button type=\"button\" class=\"catlink item icon-host{}\" data-name=\"{item}\" data-uid=\"{uid}\" data-forms=\"{}\" data-pool=\"{pool}\"><span class=\"catname\">{item}</span></button>",
                            if target { " target" } else { "" },
                            esc(forms)
                        );
                    }
                    None => {
                        out.push_str("<span class=\"item");
                        if upgrades.contains(&pull.cat) {
                            out.push_str(" upgrade");
                        }
                        if pull.cat == dark && dark != NONE {
                            out.push_str(" dark-catseye");
                        }
                        if target {
                            out.push_str(" got");
                        }
                        let _ = write!(out, "\" data-pool=\"{pool}\">{item}</span>");
                    }
                }
                out.push_str("</span><span class=\"entry-dice\">");
                if pull.seed != 0 {
                    let _ = write!(
                        out,
                        "<button type=\"button\" class=\"reseed inline\" data-seed=\"{}\" data-item=\"{}\" title=\"{}\" aria-label=\"{}\">{DICE}</button>",
                        pull.seed,
                        esc(req.name(pull.cat)),
                        req.t("Rolled this? Jump the seed to just after this clean pull (a dupe's branch has its own dice)"),
                        req.tr("Jump the seed to just after %(name)s", &[("name", &item)])
                    );
                }
                out.push_str("</span>");
                if let Some(alt) = alt {
                    let (to_pos, to_track) = landing(position, track, alt.steps as usize);
                    let alt_item = esc(args.label(req, alt.cat));
                    let _ = write!(
                        out,
                        "<span class=\"arrow\" title=\"{}\">&#8627; {} ",
                        req.t("Following the track dupes here: the previous pull obtains this same item, so this cell rerolls into the branch value and jumps tracks"),
                        req.t("if dupe:")
                    );
                    if unit(alt.cat).is_some() {
                        let _ = write!(
                            out,
                            "<button type=\"button\" class=\"catlink item{}\" data-name=\"{alt_item}\">{alt_item}</button>",
                            if alt_target { " target" } else { "" }
                        );
                    } else {
                        out.push_str("<span class=\"item");
                        if alt.cat == dark && dark != NONE {
                            out.push_str(" dark-catseye");
                        }
                        if alt_target {
                            out.push_str(" got");
                        }
                        let _ = write!(out, "\" data-pool=\"{pool}\">{alt_item}</span>");
                    }
                    let to = format!("{to_pos}{}", TRACKS[to_track]);
                    let _ = write!(
                        out,
                        "{} <button type=\"button\" class=\"reseed inline\" data-seed=\"{}\" data-item=\"{}\" title=\"{}\" aria-label=\"{}\">{DICE}</button></span>",
                        req.tr(", jumps to %(to)s", &[("to", &to)]),
                        alt.seed,
                        esc(req.name(alt.cat)),
                        req.tr("Got %(name)s here? Jump the seed to just after that reroll", &[("name", &alt_item)]),
                        req.tr("Jump the seed to just after %(name)s", &[("name", &alt_item)])
                    );
                }
                out.push_str("</div>");
            }
            out.push_str("</td>\n");
        }
        out.push_str("</tr>\n");
    }
    out.push_str("</tbody>\n</table>\n");
    out
}

/// The Normal Capsules table for the posted machines (normal_tracks).
pub fn normal_tracks(req: &Request, args: &NormalArgs) -> String {
    let banners: Vec<usize> = (0..req.banners.len()).collect();
    tracks(req, args, &banners, req.count, &HashMap::new())
}

/// The path planner's result (build_normal_plan + _normal_plan.html). ``req.banners``
/// are the live machines in the page's column order.
pub fn normal_plan(req: &Request, args: &NormalArgs, plan_args: &PlanArgs) -> String {
    let last = req.id(&req.last_cat);
    let best = plan(req, req.seed, last, plan_args);
    let found = !best.steps.is_empty();
    let seed_after = if found { best.seed } else { req.seed };
    let last_item = if found { best.last } else { last };

    // Legs (runs of up to STEP_PULLS pulls on one machine) and the track marks,
    // numbered together.
    struct Leg {
        n: usize,
        machine: usize,
        pulls: Vec<Step>,
    }
    let mut legs: Vec<Leg> = Vec::new();
    let mut marks: Marks = HashMap::new();
    for step in &best.steps {
        let n = match legs.last() {
            Some(leg) if leg.machine == step.machine && leg.pulls.len() < STEP_PULLS => leg.n,
            _ => {
                legs.push(Leg {
                    n: legs.len() + 1,
                    machine: step.machine,
                    pulls: Vec::new(),
                });
                legs.len()
            }
        };
        marks
            .entry((step.position, step.track))
            .or_default()
            .insert(step.machine, (step.dupe, step.target, n));
        if let Some(leg) = legs.last_mut() {
            leg.pulls.push(step.clone());
        }
    }
    let rows = best.steps.iter().map(|s| s.position).max().unwrap_or(0);
    let banners: Vec<usize> = (0..req.banners.len())
        .filter(|b| !plan_args.optional.contains(b) || best.steps.iter().any(|s| s.machine == *b))
        .collect();
    let track = tracks(req, args, &banners, req.count.max(rows + 2), &marks);
    let dark = req.id("Dark Catseye");

    let mut out = String::from("\n<div class=\"normal-plan\">\n");
    if best.hits > 0 {
        let mut spent: Vec<(&str, &str, usize)> = Vec::new();
        for (currency, budget) in CURRENCIES.into_iter().zip(BUDGETS) {
            let n = best
                .steps
                .iter()
                .filter(|s| req.banners[s.machine].currency == currency)
                .count();
            if n > 0 {
                spent.push((currency, budget, n));
            }
        }
        let _ = write!(
            out,
            "<p class=\"plan-haul\">\n<strong>{}</strong> {}\n{}\n",
            best.hits,
            esc(&plan_args.label),
            req.t("for")
        );
        for (i, (name, _, n)) in spent.iter().enumerate() {
            if i > 0 {
                out.push_str(" + ");
            }
            out.push_str(&esc(&currency_count(req, name, *n)));
        }
        let _ = write!(
            out,
            ".\n<button type=\"button\" class=\"seek-use plan-apply\" data-seed=\"{seed_after}\" data-item=\"{}\"",
            esc(req.name(last_item))
        );
        for (_, budget, n) in &spent {
            let _ = write!(out, " data-{budget}=\"{n}\"");
        }
        let _ = write!(
            out,
            " title=\"{}\">{}</button>\n</p>\n",
            req.t("You rolled this plan: the seed jumps to just after its final pull and its tickets come off your stash"),
            req.t("Apply this plan")
        );
        let _ = write!(
            out,
            "<div class=\"plan-follow\">\n<div class=\"plan-steps\">\n<div class=\"steps-head\">\n<span class=\"steps-title\">{}</span>\n<div class=\"step-nav\" role=\"group\" aria-label=\"{}\">\n<button type=\"button\" class=\"step-nav-btn step-prev\" aria-label=\"{}\">&#8249;</button>\n<span class=\"step-count\" aria-live=\"polite\"></span>\n<button type=\"button\" class=\"step-nav-btn step-next\" aria-label=\"{}\">&#8250;</button>\n</div>\n</div>\n<div class=\"step-list\">\n",
            req.t("Steps"),
            req.t("Walk the plan step by step"),
            req.t("Previous step"),
            req.t("Next step")
        );
        for leg in &legs {
            let b = &req.banners[leg.machine];
            let count = leg.pulls.len();
            let kind = req.trn(
                "%(n)s&times; pull",
                "%(n)s&times; pulls",
                count as i64,
                &[("n", &count.to_string())],
            );
            let _ = write!(
                out,
                "<button type=\"button\" class=\"step-card\" data-step=\"{0}\">\n<span class=\"step-card-head\">\n<span class=\"step-dot\">{0}</span>\n<span class=\"step-banner\">{1}</span>\n</span>\n<span class=\"step-meta\">\n<span class=\"step-kind\">{kind}</span>\n<span class=\"step-cost\">{2}</span>\n</span>\n",
                leg.n,
                esc(&b.name),
                esc(&currency_count(req, &b.currency, count))
            );
            let gets: Vec<&Step> = leg.pulls.iter().filter(|p| p.target).collect();
            if !gets.is_empty() {
                let _ = write!(out, "<span class=\"step-gets\">{} ", req.t("gets"));
                for (i, p) in gets.iter().enumerate() {
                    if i > 0 {
                        out.push_str(", ");
                    }
                    let class = if p.item == dark && dark != NONE {
                        " dark-catseye"
                    } else {
                        ""
                    };
                    let _ = write!(
                        out,
                        "<span class=\"step-get{class}\">{}</span>",
                        esc(args.label(req, p.item))
                    );
                }
                out.push_str("</span>\n");
            }
            out.push_str("</button>\n");
        }
        let _ = write!(
            out,
            "</div>\n</div>\n<div class=\"plan-track\">{track}</div>\n</div>\n"
        );
    } else {
        let _ = write!(
            out,
            "<p class=\"seek-none\">{}</p>\n{track}",
            req.tr(
                "No %(target)s reachable with those rolls. Give a machine more budget, or try again after your next real pulls move the seed.",
                &[("target", &esc(&plan_args.label))]
            )
        );
    }
    out.push_str("</div>\n");
    out
}
