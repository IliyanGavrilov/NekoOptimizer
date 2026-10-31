// The Rolls table, built and rendered here instead of the server: planner.services'
// build_tracks, trace_marks and find_cats, and the _tracks.html / _track_cell.html markup
// they feed. planner/test_engine_wasm.py renders the same requests through Django and
// requires the same HTML.

use std::collections::{HashMap, HashSet};
use std::fmt::Write;

use serde::Deserialize;

use crate::engine::Request;
use crate::graph::{Graph, Outcome};
use crate::plans::plan_shared;
use crate::roll::{roll_banner, BannerRolls, NONE, UBER};
use crate::search::{Currency, Kind, Leg, Pull};

const RARITIES: [&str; 4] = ["Rare", "Super Rare", "Uber Super Rare", "Legend Rare"];
const SHORT_RARITY: [&str; 4] = ["Rare", "Super", "Uber", "Legend"];

#[derive(Deserialize, Clone)]
pub struct Badge {
    pub tier: String,
    pub up: Option<String>,
    pub up_note: String,
    /// The ranked unit, so a click on the badge can open its spot in the tier list.
    #[serde(default)]
    pub uid: Option<u32>,
}

#[derive(Deserialize)]
pub struct Trace {
    pub tag: String,
    pub idx: usize,
    #[serde(default)]
    pub guaranteed: bool,
    #[serde(default)]
    pub reroll: bool,
}

/// What the Rolls table shows beyond the rolls: the player's marks and the page's
/// options, every cat an id into the request's name table.
#[derive(Deserialize)]
pub struct View {
    pub owned: Vec<u32>,
    pub wanted: Vec<u32>,
    /// Per name: its catalogue unit id and tier badge, when it has them.
    pub uids: Vec<Option<u32>>,
    pub tiers: Vec<Option<Badge>>,
    /// Per banner, aligned with the request's banners.
    pub titles: Vec<String>,
    pub debuts: Vec<Vec<u32>>,
    // The browse view's own: rows shown, the Targets panel, the trace, future padding.
    #[serde(default)]
    pub rows: usize,
    #[serde(default)]
    pub future: Option<Vec<u32>>,
    #[serde(default)]
    pub targets: Vec<(u32, String)>,
    #[serde(default)]
    pub wishlist: Vec<(u32, String)>,
    #[serde(default)]
    pub pool: Option<Vec<u32>>,
    #[serde(default)]
    pub pks: Vec<(u32, u64)>,
    #[serde(default)]
    pub include_guaranteed: bool,
    #[serde(default)]
    pub horizon: usize,
    #[serde(default)]
    pub selected_titles: String,
    #[serde(default)]
    pub trace: Option<Trace>,
}

// ---- building ----------------------------------------------------------------------

/// Selected banners with the same rolls merged, tagged 1, 2, 3... (_banner_groups).
pub(crate) struct Group<'a> {
    pub(crate) tag: String,
    pub(crate) keys: Vec<usize>, // the merged banners, by request index, in name order
    pub(crate) graph: Graph<'a>,
    debuts: HashSet<u32>,
    guaranteed_rolls: u32, // the longest guaranteed multi among the merged banners
}

/// Where a trace or a plan lights one group (TrackMarks, for one representative).
#[derive(Default)]
pub(crate) struct Marks {
    pub(crate) path: HashSet<usize>,
    pub(crate) targets: HashMap<usize, u32>,
    pub(crate) gpath: HashSet<usize>,
    pub(crate) gtargets: HashMap<usize, u32>,
    pub(crate) shared: HashSet<usize>,
    pub(crate) gshared: HashSet<usize>,
    pub(crate) nexts: HashSet<usize>,
    galt_targets: HashSet<usize>,
    pub(crate) steps: HashMap<usize, usize>,
    pub(crate) gsteps: HashMap<usize, usize>,
}

fn same_rolls(a: &BannerRolls, b: &BannerRolls) -> bool {
    a.pulls == b.pulls && a.guaranteed == b.guaranteed
}

pub(crate) fn groups<'a>(req: &Request, rolls: &'a [BannerRolls], view: &View) -> Vec<Group<'a>> {
    let mut groups: Vec<Group> = Vec::new();
    let mut seen: HashSet<usize> = HashSet::new();
    for (i, r) in rolls.iter().enumerate() {
        let mut keys: Vec<usize> = (0..rolls.len())
            .filter(|&j| same_rolls(r, &rolls[j]))
            .collect();
        keys.sort_by(|&a, &b| req.banners[a].key.cmp(&req.banners[b].key));
        if !seen.insert(keys[0]) {
            continue;
        }
        let debuts = keys
            .iter()
            .flat_map(|&k| view.debuts[k].iter().copied())
            .collect();
        let guaranteed_rolls = keys
            .iter()
            .map(|&k| req.banners[k].guaranteed_rolls)
            .max()
            .unwrap_or(0);
        let tag = (groups.len() + 1).to_string();
        groups.push(Group {
            tag,
            keys,
            graph: Graph::new(&rolls[i]),
            debuts,
            guaranteed_rolls,
        });
    }
    groups
}

/// The cells a trace click lights, per group (trace_marks).
fn trace_marks(groups: &[Group], trace: &Trace, last_cat: u32) -> Vec<Marks> {
    let mut marks: Vec<Marks> = groups.iter().map(|_| Marks::default()).collect();
    let Some(picked) = groups.iter().position(|g| g.tag == trace.tag) else {
        return marks;
    };
    let graph = &groups[picked].graph;
    let index = trace.idx;
    let Some(clean) = graph.pull(index) else {
        return marks;
    };

    let gpull = if trace.guaranteed {
        graph.guaranteed_pull(index, trace.reroll)
    } else {
        None
    };
    if trace.guaranteed && gpull.is_none_or(|p| p.cat == NONE) {
        return marks;
    }
    let branch = if trace.reroll {
        graph.reroll(index)
    } else {
        None
    };
    if trace.reroll && !trace.guaranteed && branch.is_none_or(|b| b.cat == NONE) {
        return marks;
    }

    let mut walk: Vec<(usize, Outcome)> = Vec::new();
    let (mut last, mut at) = (last_cat, 0);
    while at <= index {
        let Some(outcome) = graph.resolve(at, last) else {
            break;
        };
        walk.push((at, outcome));
        if at == index {
            break;
        }
        (last, at) = (outcome.cat, outcome.next);
    }
    let reached = walk.last().is_some_and(|&(i, _)| i == index);
    let duped_arrival = reached && walk.last().is_some_and(|(_, o)| o.switched);
    let walked: HashSet<usize> = if reached && duped_arrival == trace.reroll {
        walk.iter().map(|&(i, _)| i).collect()
    } else {
        HashSet::new()
    };
    let mine = &mut marks[picked];

    if let Some(gpull) = gpull {
        mine.gtargets.insert(index, gpull.cat);
        if trace.reroll {
            mine.galt_targets.insert(index);
        }
        let size = groups[picked].guaranteed_rolls;
        let mut steps = walked;
        let first = if trace.reroll {
            branch
        } else {
            graph.resolve(index, NONE)
        };
        if size >= 2 {
            if let Some(first) = first {
                steps.insert(index);
                let (mut last, mut at) = (first.cat, first.next);
                let mut finished = true;
                for _ in 0..size - 2 {
                    let Some(outcome) = graph.resolve(at, last) else {
                        finished = false;
                        break;
                    };
                    steps.insert(at);
                    (last, at) = (outcome.cat, outcome.next);
                }
                if finished {
                    mine.nexts.insert(at + 1);
                }
            }
        }
        if !steps.is_empty() {
            mine.path = steps;
            mine.gpath.insert(index);
        }
        return marks;
    }

    if let Some(branch) = branch {
        mine.path = walked;
        mine.targets.insert(index, branch.cat);
        mine.nexts.insert(branch.next);
        return marks;
    }

    if !reached || duped_arrival {
        mine.targets.insert(index, clean.cat);
        mine.nexts.insert(index + 2);
        return marks;
    }

    let (_, end) = *walk.last().expect("reached");
    mine.path = walk.iter().map(|&(i, _)| i).collect();
    mine.targets.insert(index, end.cat);
    mine.nexts.insert(end.next);

    // The walk as a plan of single pulls: which other banner each one could be rolled on
    // without changing the path.
    let moves: Vec<Leg> = walk
        .iter()
        .map(|&(step, o)| Leg {
            banner: picked,
            kind: Kind::Single,
            cost: 0,
            pulls: vec![Pull {
                position: step,
                banner: picked,
                cat: o.cat,
                rarity: o.rarity,
                guaranteed: false,
            }],
            currency: Currency::None,
        })
        .collect();
    let graphs: Vec<&Graph> = groups.iter().map(|g| &g.graph).collect();
    let members: Vec<Vec<usize>> = (0..groups.len()).map(|g| vec![g]).collect();
    let target = HashSet::from([end.cat]);
    let (shared, _) = plan_shared(&moves, &target, &graphs, &members, &[], &HashSet::new());
    for (m, steps) in marks.iter_mut().zip(shared) {
        m.shared = steps;
    }
    marks
}

// ---- the Targets panel (find_cats) ---------------------------------------------------

pub(crate) struct Found {
    name: u32,
    rarity: String,
    index: Option<usize>,
    guaranteed: bool,
    pos: String,
    unreachable: bool,
}

fn pos_label(index: usize, guaranteed: bool) -> String {
    format!(
        "{}{}{}",
        index / 2 + 1,
        if index & 1 == 1 { 'B' } else { 'A' },
        if guaranteed { "G" } else { "" }
    )
}

fn find_cats(rolls: &[BannerRolls], view: &View) -> Vec<Found> {
    let targets: HashMap<u32, &str> = view.targets.iter().map(|(n, r)| (*n, r.as_str())).collect();
    let pool: Option<HashSet<u32>> = view.pool.as_ref().map(|p| p.iter().copied().collect());
    let mut wanted: HashMap<u32, String> = view
        .wishlist
        .iter()
        .filter(|(n, _)| targets.contains_key(n) || pool.as_ref().is_none_or(|p| p.contains(n)))
        .map(|(n, r)| (*n, r.clone()))
        .collect();
    for (n, r) in &view.targets {
        wanted.insert(*n, r.clone());
    }
    if wanted.is_empty() {
        return Vec::new();
    }

    let mut best: HashMap<u32, (usize, bool, u8)> = HashMap::new();
    let mut offer = |cat: u32, rarity: u8, index: usize, guaranteed: bool| {
        if wanted.contains_key(&cat) && best.get(&cat).is_none_or(|b| index < b.0) {
            best.insert(cat, (index, guaranteed, rarity));
        }
    };
    for r in rolls {
        for p in &r.pulls {
            offer(p.cat, p.rarity, p.index(), false);
        }
        if view.include_guaranteed {
            for p in r.guaranteed.iter().filter(|p| p.cat != NONE) {
                offer(p.cat, p.rarity, p.index(), true);
            }
        }
    }

    let found: Vec<Found> = best
        .iter()
        .map(|(&name, &(index, guaranteed, rarity))| Found {
            name,
            rarity: RARITIES[usize::from(rarity)].to_owned(),
            index: Some(index),
            guaranteed,
            pos: pos_label(index, guaranteed),
            unreachable: false,
        })
        .collect();
    found
}

// ---- rendering ---------------------------------------------------------------------

/// Django's autoescape.
pub(crate) fn esc(text: &str) -> String {
    let mut out = String::with_capacity(text.len());
    for c in text.chars() {
        match c {
            '&' => out.push_str("&amp;"),
            '<' => out.push_str("&lt;"),
            '>' => out.push_str("&gt;"),
            '"' => out.push_str("&quot;"),
            '\'' => out.push_str("&#x27;"),
            _ => out.push(c),
        }
    }
    out
}

/// Python's json.dumps of a list of strings: ", " between items, non-ASCII as \u escapes.
fn json_list(items: &[&str]) -> String {
    let mut out = String::from("[");
    for (i, item) in items.iter().enumerate() {
        if i > 0 {
            out.push_str(", ");
        }
        out.push('"');
        for unit in item.encode_utf16() {
            match unit {
                0x22 => out.push_str("\\\""),
                0x5C => out.push_str("\\\\"),
                0x0A => out.push_str("\\n"),
                0x0D => out.push_str("\\r"),
                0x09 => out.push_str("\\t"),
                0x08 => out.push_str("\\b"),
                0x0C => out.push_str("\\f"),
                0x20..=0x7E => out.push(char::from(unit as u8)),
                _ => {
                    let _ = write!(out, "\\u{unit:04x}");
                }
            }
        }
        out.push('"');
    }
    out.push(']');
    out
}

fn is_future_uber(name: &str) -> bool {
    let Some(rest) = name.strip_prefix("Future Uber ") else {
        return false;
    };
    let (number, banner) = match rest.split_once(" @ ") {
        Some((n, b)) => (n, Some(b)),
        None => (rest, None),
    };
    !number.is_empty()
        && number.bytes().all(|b| b.is_ascii_digit())
        && banner.is_none_or(|b| !b.is_empty())
}

fn future_label(name: &str) -> &str {
    name.split_once(" @ ").map_or(name, |(label, _)| label)
}

const DICE: &str = "<svg width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" aria-hidden=\"true\"><use href=\"#dice-icon\"/></svg>\n";
const FUTURE_TITLE: &str = "An uber not released yet - a stand-in for whatever joins the pool next";

/// A future uber's label, "Future Uber 3", in the interface language.
fn future_text(req: &Request, name: &str) -> String {
    let label = future_label(name);
    let n = label.strip_prefix("Future Uber ").unwrap_or(label);
    req.tr("Future Uber %(n)s", &[("n", &esc(n))])
}

struct Ctx<'a> {
    req: &'a Request,
    view: &'a View,
    owned: HashSet<u32>,
    wanted: HashSet<u32>,
    target_names: HashSet<u32>,
    multi: usize,
}

struct Alt {
    cat: u32,
    to: String,
    left: bool,
    seed: u32,
    target: bool,
    guaranteed: bool,
}

struct Entry<'a> {
    tag: &'a str,
    idx: usize,
    cat: u32,
    rarity: u8,
    switch: bool,
    alt: Option<Alt>,
    on_path: bool,
    step: Option<usize>,
    target: bool,
    lit: bool,
    shared: bool,
    next: bool,
    seed: u32,
    new: bool,
    owned: bool,
    wanted: bool,
    debut: bool,
    future: bool,
}

impl Ctx<'_> {
    fn name(&self, id: u32) -> &str {
        self.req.name(id)
    }

    fn uid(&self, id: u32) -> Option<u32> {
        self.view.uids.get(id as usize).copied().flatten()
    }

    fn tier(&self, id: u32) -> Option<&Badge> {
        self.view.tiers.get(id as usize).and_then(Option::as_ref)
    }

    /// _collection_marks: (new, owned, wanted, debut, future).
    fn marks(&self, cat: u32, rarity: u8, debuts: &HashSet<u32>) -> (bool, bool, bool, bool, bool) {
        if is_future_uber(self.name(cat)) {
            return (true, false, false, true, true);
        }
        (
            rarity >= UBER && !self.owned.contains(&cat),
            self.owned.contains(&cat),
            self.wanted.contains(&cat),
            debuts.contains(&cat),
            false,
        )
    }
}

fn entries<'a>(ctx: &Ctx, groups: &'a [Group], marks: &[Marks], index: usize) -> Vec<Entry<'a>> {
    let mut cells = Vec::new();
    for (g, group) in groups.iter().enumerate() {
        let Some(tp) = group.graph.pull(index) else {
            continue;
        };
        let graph = &group.graph;
        let m = &marks[g];
        let outcome = graph.outcome(index);
        let switched = outcome.is_some_and(|o| o.switched);
        let on_path = m.path.contains(&index);
        let branch = if switched {
            outcome
        } else if graph.realized(index) {
            graph.reroll(index).filter(|r| r.cat != NONE)
        } else {
            None
        };
        let obtained = m.targets.get(&index).copied();
        let alt = branch.map(|b| Alt {
            cat: b.cat,
            to: pos_label(b.next, false),
            left: b.next % 2 == 0,
            seed: b.seed,
            target: obtained == Some(b.cat) || ctx.target_names.contains(&b.cat),
            guaranteed: false,
        });
        let target = obtained == Some(tp.cat) || ctx.target_names.contains(&tp.cat);
        let (new, owned, wanted, debut, future) = ctx.marks(tp.cat, tp.rarity, &group.debuts);
        let lit = target || alt.as_ref().is_some_and(|a| a.target);
        cells.push(Entry {
            tag: &group.tag,
            idx: index,
            cat: tp.cat,
            rarity: tp.rarity,
            switch: switched,
            alt,
            on_path,
            step: m.steps.get(&index).copied(),
            target,
            lit,
            shared: !on_path && m.shared.contains(&index),
            next: m.nexts.contains(&index),
            seed: tp.seed,
            new,
            owned,
            wanted,
            debut,
            future,
        });
    }
    cells
}

fn guaranteed_entries<'a>(
    ctx: &Ctx,
    groups: &'a [Group],
    marks: &[Marks],
    index: usize,
) -> Vec<Entry<'a>> {
    let mut cells = Vec::new();
    for (g, group) in groups.iter().enumerate() {
        let graph = &group.graph;
        let Some(tp) = graph.guaranteed_pull(index, false) else {
            continue;
        };
        if tp.cat == NONE {
            continue;
        }
        let m = &marks[g];
        let on_path = m.gpath.contains(&index);
        let gobtained = m.gtargets.get(&index).copied();
        let picked_alt = m.galt_targets.contains(&index);
        let target =
            (gobtained == Some(tp.cat) && !picked_alt) || ctx.target_names.contains(&tp.cat);
        let (new, owned, wanted, debut, future) = ctx.marks(tp.cat, tp.rarity, &group.debuts);
        let mut alt = None;
        let outcome = graph.outcome(index);
        if outcome.is_some_and(|o| o.switched) || graph.realized(index) {
            if let Some(dupe) = graph.guaranteed_pull(index, true).filter(|d| d.cat != NONE) {
                alt = Some(Alt {
                    cat: dupe.cat,
                    to: String::new(),
                    left: false,
                    seed: dupe.seed,
                    target: (gobtained == Some(dupe.cat)
                        && (picked_alt || gobtained != Some(tp.cat)))
                        || ctx.target_names.contains(&dupe.cat),
                    guaranteed: true,
                });
            }
        }
        let lit = target || alt.as_ref().is_some_and(|a| a.target);
        cells.push(Entry {
            tag: &group.tag,
            idx: index,
            cat: tp.cat,
            rarity: tp.rarity,
            switch: false,
            alt,
            on_path,
            step: m.gsteps.get(&index).copied(),
            target,
            lit,
            shared: !on_path && m.gshared.contains(&index),
            next: false,
            seed: tp.seed,
            new,
            owned,
            wanted,
            debut,
            future,
        });
    }
    cells
}

fn badge(out: &mut String, req: &Request, badge: Option<&Badge>) {
    let Some(b) = badge else { return };
    let band: String = b.tier.chars().take(1).collect();
    let _ = write!(
        out,
        "<span class=\"tier-badge\" data-band=\"{}\"",
        esc(&band)
    );
    if let Some(uid) = b.uid {
        let _ = write!(
            out,
            " data-uid=\"{uid}\" title=\"{}\"",
            req.t("See it in the tier list")
        );
    }
    let _ = write!(out, ">{}", esc(&b.tier));
    if let Some(up) = b.up.as_deref().filter(|u| !u.is_empty()) {
        let _ = write!(
            out,
            "<span class=\"tier-up\" title=\"{}\">&#9650;{}</span>",
            esc(&b.up_note),
            esc(up)
        );
    }
    out.push_str("</span>");
}

/// _track_cell.html.
fn cell(
    out: &mut String,
    ctx: &Ctx,
    cells: &[Entry],
    cell_class: &str,
    details: Option<(u32, u32)>,
) {
    out.push_str("\n<td class=\"cell");
    if !cell_class.is_empty() {
        let _ = write!(out, " {cell_class}");
    }
    out.push_str("\">");
    for e in cells {
        let name = esc(ctx.name(e.cat));
        out.push_str("<div class=\"entry");
        for (on, class) in [
            (e.on_path, " on-path"),
            (e.lit, " target"),
            (e.new, " new"),
            (e.owned, " owned"),
            (e.wanted, " wanted"),
            (e.shared, " shared"),
            (e.next, " next"),
        ] {
            if on {
                out.push_str(class);
            }
        }
        let _ = write!(out, "\" data-tag=\"{}\" data-idx=\"{}\"", e.tag, e.idx);
        if let Some(step) = e.step.filter(|&s| s != 0) {
            let _ = write!(out, " data-step=\"{step}\"");
        }
        let req = ctx.req;
        if e.shared {
            let _ = write!(out, " title=\"{}\"", req.t("This step of the plan can be rolled on this banner instead - you'd get this cat, and the rest of the plan still works"));
        } else if e.next {
            let _ = write!(out, " title=\"{}\"", req.t("You land here next: the first cat another roll on this banner would give after the highlighted draws"));
        }
        out.push_str("><span class=\"entry-name\">");
        if let Some(step) = e.step.filter(|&s| s != 0) {
            let _ = write!(
                out,
                "<span class=\"step-dot\" aria-hidden=\"true\">{step}</span> "
            );
        }
        if ctx.multi > 1 {
            let _ = write!(out, "<span class=\"tag\">{}</span> ", e.tag);
        }
        let target = if e.target { " target" } else { "" };
        if e.future {
            let _ = write!(
                out,
                "<span class=\"catlink future{target}\" title=\"{}\">{}</span>",
                req.t(FUTURE_TITLE),
                future_text(req, ctx.name(e.cat))
            );
        } else {
            let _ = write!(
                out,
                "<button type=\"button\" class=\"catlink icon-host{target}\" data-name=\"{name}\""
            );
            if let Some(uid) = ctx.uid(e.cat).filter(|&u| u != 0) {
                let _ = write!(out, " data-uid=\"{uid}\"");
            }
            let _ = write!(out, "><span class=\"catname\">{name}</span></button>");
        }
        if e.debut {
            let _ = write!(
                out,
                " <span class=\"debut\" title=\"{}\">{}</span>",
                req.t("Debuts with this banner &mdash; this is its first event anywhere"),
                req.t("new")
            );
        }
        let rarity = RARITIES[usize::from(e.rarity)];
        let _ = write!(
            out,
            "</span><span class=\"entry-rarity\"><span class=\"rarity\" data-rarity=\"{rarity}\" title=\"{}\">{}</span></span><span class=\"entry-tier\">",
            req.t(rarity),
            {
                let short = SHORT_RARITY[usize::from(e.rarity)];
                req.t_keyed(&format!("short rarity:{short}"), short)
            }
        );
        badge(out, ctx.req, ctx.tier(e.cat));
        out.push_str("</span><span class=\"entry-dice\">");
        if e.seed != 0 {
            let title = req.t(if cell_class.is_empty() {
                "Rolled this? Jump the seed to just after this clean pull (a dupe's branch has its own dice)"
            } else {
                "Rolled this guaranteed multi? Jump the seed to just after its final draw"
            });
            let _ = write!(
                out,
                "<button type=\"button\" class=\"reseed inline\" data-seed=\"{}\" data-cat=\"{name}\" title=\"{title}\" aria-label=\"{}\">{DICE}</button>",
                e.seed,
                req.tr("Jump the seed to just after %(name)s", &[("name", &name)])
            );
        }
        out.push_str("</span>");
        if let Some(alt) = &e.alt {
            let alt_name = esc(ctx.name(alt.cat));
            let why = if alt.guaranteed {
                "If this guaranteed multi's first roll comes up as a dupe, it rerolls and the multi ends on a different cell - you get this uber instead"
            } else if e.switch {
                "Following the track dupes here: the previous pull obtains this same cat, so this cell rerolls into the branch value and jumps tracks"
            } else {
                "Only when the arriving pull already holds this cell's cat (a bounce path, or your remembered last pull): it rerolls into the branch value and jumps tracks"
            };
            let _ = write!(out, "<span class=\"arrow\" title=\"{}\">", req.t(why));
            out.push_str(if alt.left { "&#8626;" } else { "&#8627;" });
            let _ = write!(out, " {} ", req.t("if dupe:"));
            let alt_target = if alt.target { " target" } else { "" };
            if alt.guaranteed && is_future_uber(ctx.name(alt.cat)) {
                let _ = write!(
                    out,
                    "<span class=\"catlink future{alt_target}\" title=\"{}\">{}</span>",
                    req.t(FUTURE_TITLE),
                    future_text(req, ctx.name(alt.cat))
                );
            } else {
                let _ = write!(out, "<button type=\"button\" class=\"catlink{alt_target}\" data-name=\"{alt_name}\">{alt_name}</button>");
            }
            if !alt.guaranteed {
                out.push_str(&req.tr(", jumps to %(to)s", &[("to", &alt.to.to_string())]));
            }
            if alt.seed != 0 {
                let title = if alt.guaranteed {
                    req.t("Rolled this guaranteed multi (its first roll duped)? Jump the seed to just after its final draw").to_owned()
                } else {
                    req.tr(
                        "Got %(name)s here? Jump the seed to just after that reroll",
                        &[("name", &alt_name)],
                    )
                };
                let _ = write!(
                    out,
                    " <button type=\"button\" class=\"reseed inline\" data-seed=\"{}\" data-cat=\"{alt_name}\" title=\"{title}\" aria-label=\"{}\">{DICE}</button>",
                    alt.seed,
                    req.tr("Jump the seed to just after %(name)s", &[("name", &alt_name)])
                );
            }
            out.push_str("</span>");
        }
        out.push_str("</div>");
    }
    if let Some((rarity_seed, slot_seed)) = details {
        let seeds = ctx.req.tr(
            "rarity %(rarity)s &middot; slot %(slot)s",
            &[
                ("rarity", &rarity_seed.to_string()),
                ("slot", &slot_seed.to_string()),
            ],
        );
        let _ = write!(out, "<span class=\"cell-seeds\">{seeds}</span>");
    }
    out.push_str("</td>\n");
}

fn found_panel(out: &mut String, ctx: &Ctx, items: &[(Found, bool)], hits: usize) {
    let req = ctx.req;
    let _ = write!(
        out,
        "\n<div class=\"found-cats\">\n<span class=\"found-label\" title=\"{}\">{}</span>\n<span class=\"found-count\" title=\"{}\">{}</span>\n<ul class=\"found-list\">\n",
        req.t("Every cat you're searching for - the targets you picked, your wishlist (when that search is on), and any future ubers you've toggled - with its next spot in these rolls. Click a position to jump to its cell."),
        req.t("Targets"),
        req.tr("%(hits)s of them turn up in these rolls", &[("hits", &hits.to_string())]),
        items.len()
    );
    let pks: HashMap<u32, u64> = ctx.view.pks.iter().copied().collect();
    for (f, found) in items {
        let raw = ctx.name(f.name);
        let name = esc(raw);
        let owned = ctx.owned.contains(&f.name);
        let wanted = ctx.wanted.contains(&f.name);
        out.push_str("<li class=\"found-item");
        if f.unreachable {
            out.push_str(" is-unreachable");
        } else if !found {
            out.push_str(" is-out");
        }
        if owned {
            out.push_str(" owned");
        }
        if wanted {
            out.push_str(" wanted");
        }
        out.push_str("\">\n");
        if !f.rarity.is_empty() {
            let _ = writeln!(
                out,
                "<span class=\"rarity\" data-rarity=\"{}\">{}</span>",
                esc(&f.rarity),
                esc(req.t(&f.rarity))
            );
        }
        let future = is_future_uber(raw);
        if future {
            let _ = write!(
                out,
                "<span class=\"found-cat future\" title=\"{}\"><span class=\"catname\">{}</span></span>",
                req.t("An uber not released yet - a stand-in for whatever joins this banner's pool next"),
                future_text(req, raw)
            );
            if let Some((_, banner)) = raw.split_once(" @ ") {
                let shown = ctx
                    .req
                    .banners
                    .iter()
                    .position(|b| b.key == banner)
                    .map_or(banner, |i| ctx.view.titles[i].as_str());
                let shown = esc(shown);
                let _ = write!(
                    out,
                    " <span class=\"found-banner\" title=\"{shown}\">{shown}</span>"
                );
            }
            out.push('\n');
        } else {
            let _ = writeln!(out, "<button type=\"button\" class=\"catlink found-cat\" data-name=\"{name}\"><span class=\"catname\">{name}</span></button>");
        }
        if *found {
            let index = f.index.unwrap_or(0);
            let _ = write!(
                out,
                "<button type=\"button\" class=\"find-pos\" data-idx=\"{index}\""
            );
            if f.guaranteed {
                out.push_str(" data-guaranteed=\"1\"");
            }
            let _ = writeln!(
                out,
                " title=\"{}\">{}</button>",
                req.tr("Jump to %(pos)s in the track", &[("pos", &f.pos)]),
                f.pos
            );
        } else if f.unreachable {
            let _ = writeln!(
                out,
                "<span class=\"find-warn\" role=\"img\" aria-label=\"{}\" title=\"{}\">&#9888;</span>",
                req.t("Won't drop on the selected banners"),
                req.tr(
                    "Won't drop on the selected banners: %(banners)s. Add a banner that carries it, or remove it.",
                    &[("banners", &esc(&ctx.view.selected_titles))]
                )
            );
        } else {
            let _ = writeln!(
                out,
                "<span class=\"find-out\" title=\"{}\">{}</span>",
                req.tr(
                    "Doesn't turn up in the first %(rolls)s rolls",
                    &[("rolls", &f.pos.replace('+', ""))]
                ),
                f.pos
            );
        }
        let remove = req.t("Remove target");
        if let Some(pk) = pks.get(&f.name) {
            let title = req.tr("Remove %(name)s from your targets", &[("name", &name)]);
            let _ = write!(out, "<button type=\"button\" class=\"found-remove\" data-pk=\"{pk}\" title=\"{title}\" aria-label=\"{remove}\">&times;</button>");
        } else if future {
            let title = req.t("Stop searching for this future uber");
            let _ = write!(out, "<button type=\"button\" class=\"found-remove\" data-future-name=\"{name}\" title=\"{title}\" aria-label=\"{remove}\">&times;</button>");
        }
        out.push_str("\n</li>\n");
    }
    out.push_str("</ul>\n</div>\n");
}

/// The track guide's opening and its always-there entries (_tracks.html).
fn legend(req: &Request) -> String {
    let t = |s| req.t(s);
    format!(
        "<details class=\"track-guide\">\n<summary>{}</summary>\n<ul class=\"symbol-legend\">\n<li><span class=\"sym\">A / B</span> {}</li>\n<li><span class=\"sym dice-sym\">{DICE}</span> {}</li>\n<li><span class=\"arrow sample\">&#8627; {}</span> {}</li>\n<li><span class=\"entry on-path sample\">{}</span> {}</li>\n<li><span class=\"entry next sample\">{}</span> {}</li>\n<li><span class=\"entry new sample\"><span class=\"catlink\">{}</span></span> {}</li>\n<li><span class=\"entry owned sample\"><span class=\"catlink\"></span></span> {} <span class=\"sep\">&middot;</span> <span class=\"entry wanted sample\"><span class=\"catlink\"><span class=\"catname\">{}</span></span></span> {}</li>\n<li><span class=\"entry target sample\"><span class=\"catlink target\"><span class=\"catname\">{}</span></span></span> {}</li>\n<li><span class=\"debut\">{}</span> {}</li>\n",
        t("Legend"),
        t("alternate timelines; a dupe rerolls and switches track"),
        t("&ldquo;I rolled this cell&rdquo; &mdash; jumps the seed to just after it"),
        t("if dupe"),
        t("the reroll branch (its own dice &amp; landing)"),
        t("path"),
        t("click a cell's name-free space: the rolls up to it light like a plan"),
        t("striped"),
        t("you land here next &mdash; the first cat one more roll would give after the lit draws"),
        t("green name"),
        t("Uber/Legend not in your collection"),
        t("owned"),
        t("cat"),
        t("wishlisted"),
        t("cat"),
        t("a target you picked &mdash; gold here, and its next spot shows in <em>Targets</em> above"),
        t("new"),
        t("Uber debuting with this banner (its first event anywhere)"),
    )
}

/// The browse view's Rolls table (the tracks view, rendered): rolls every selected
/// banner ``count`` rows deep for the Targets panel, shows ``view.rows`` of them.
pub fn render(req: &Request, view: &View) -> String {
    let last = req.id(&req.last_cat);
    let rolls: Vec<BannerRolls> = req
        .banners
        .iter()
        .map(|b| roll_banner(req.seed, &b.banner, req.count, b.guaranteed_rolls, last))
        .collect();
    let groups = groups(req, &rolls, view);
    let marks = match &view.trace {
        Some(trace) => trace_marks(&groups, trace, last),
        None => groups.iter().map(|_| Marks::default()).collect(),
    };

    let mut found = find_cats(&rolls, view);
    let wanted_rarity: HashMap<u32, &String> = view
        .wishlist
        .iter()
        .chain(&view.targets)
        .map(|(n, r)| (*n, r))
        .collect();
    let listed: HashSet<u32> = found.iter().map(|f| f.name).collect();
    let pool: Option<HashSet<u32>> = view.pool.as_ref().map(|p| p.iter().copied().collect());
    let targets: HashSet<u32> = view.targets.iter().map(|(n, _)| *n).collect();
    let mut missing: Vec<u32> = wanted_rarity
        .keys()
        .copied()
        .filter(|n| !listed.contains(n))
        .filter(|n| targets.contains(n) || pool.as_ref().is_none_or(|p| p.contains(n)))
        .collect();
    missing.sort_by(|a, b| req.name(*a).cmp(req.name(*b)));
    found.sort_by(|a, b| {
        (a.index, a.guaranteed, req.name(a.name)).cmp(&(b.index, b.guaranteed, req.name(b.name)))
    });
    let hits = found.len();
    let mut items: Vec<(Found, bool)> = found.into_iter().map(|f| (f, true)).collect();
    for name in missing {
        let unreachable =
            pool.as_ref().is_some_and(|p| !p.contains(&name)) && !is_future_uber(req.name(name));
        let rarity = view
            .targets
            .iter()
            .find(|(n, _)| *n == name)
            .or_else(|| view.wishlist.iter().find(|(n, _)| *n == name))
            .map(|(_, r)| r.clone())
            .unwrap_or_default();
        let pos = if unreachable {
            String::new()
        } else {
            format!("{}+", view.horizon)
        };
        items.push((
            Found {
                name,
                rarity,
                index: None,
                guaranteed: false,
                pos,
                unreachable,
            },
            false,
        ));
    }

    let target_names = items.iter().map(|(f, _)| f.name).collect();
    let currencies = vec![""; groups.len()];
    table(
        req,
        view,
        &groups,
        &marks,
        view.rows,
        Some((&items, hits)),
        target_names,
        &currencies,
    )
}

/// The Rolls table markup (_tracks.html) for built groups and marks: the browse view's
/// (with its Targets ``panel``) or a plan's (lit by its marks, its capsule banners tagged
/// with their ``currencies``, one per group).
#[allow(clippy::too_many_arguments)]
pub(crate) fn table(
    req: &Request,
    view: &View,
    groups: &[Group],
    marks: &[Marks],
    rows: usize,
    panel: Option<(&[(Found, bool)], usize)>,
    target_names: HashSet<u32>,
    currencies: &[&str],
) -> String {
    let ctx = Ctx {
        req,
        view,
        owned: view.owned.iter().copied().collect(),
        wanted: view.wanted.iter().copied().collect(),
        target_names,
        multi: groups.len(),
    };

    let avail = groups
        .iter()
        .filter_map(|g| g.graph.last_index())
        .max()
        .map_or(0, |i| i / 2 + 1);
    let needed = marks
        .iter()
        .flat_map(|m| m.path.iter().chain(&m.gpath).chain(&m.nexts))
        .map(|i| i / 2 + 1)
        .max()
        .unwrap_or(0);
    let max_pos = avail.min(rows.max(needed));
    if max_pos == 0 {
        return format!(
            "\n  <p class=\"muted\">{}</p>\n",
            req.t("No rolls for this seed and banner selection.")
        );
    }

    let has_guaranteed = groups.iter().any(|g| g.graph.has_guaranteed());
    let padded = view
        .future
        .as_ref()
        .is_some_and(|f| f.iter().any(|&c| c > 0));
    let has_currency = currencies.iter().any(|c| !c.is_empty());
    let mut out = String::from("\n");
    if let Some((items, hits)) = panel.filter(|(items, _)| !items.is_empty()) {
        found_panel(&mut out, &ctx, items, hits);
    }
    out.push_str(&legend(req));
    if padded {
        let _ = writeln!(
            out,
            "<li><span class=\"entry new sample\"><span class=\"catlink future\">{}</span></span> {}</li>",
            req.tr("Future Uber %(n)s", &[("n", "1")]),
            req.t("an expected-but-unreleased Uber padding the pool")
        );
    }
    if has_guaranteed {
        let _ = writeln!(
            out,
            "<li><span class=\"sym\">{}</span> {}</li>",
            req.t("Guaranteed"),
            req.t("the Uber a guaranteed multi awards if started on that cell")
        );
    }
    if marks
        .iter()
        .any(|m| !m.shared.is_empty() || !m.gshared.is_empty())
    {
        let _ = writeln!(
            out,
            "<li><span class=\"entry shared sample\">{}</span> {}</li>",
            req.t("dashed"),
            req.t("another banner this plan step can roll on instead")
        );
    }
    if has_currency {
        let _ = writeln!(
            out,
            "<li><span class=\"capsule-tag platinum\">{}</span> / <span class=\"capsule-tag legend\">{}</span> {}</li>",
            req.t("platinum"),
            req.t("legend"),
            req.t("a capsule banner &mdash; its pulls spend that scarce ticket, not rare tickets or catfood")
        );
    }
    out.push_str("</ul>\n<div class=\"rarity-legend\">\n");
    for rarity in RARITIES {
        let _ = writeln!(
            out,
            "<span class=\"rarity\" data-rarity=\"{rarity}\">{}</span>",
            req.t(rarity)
        );
    }
    out.push_str("</div>\n</details>\n");

    let show_future = view.future.is_some();
    if groups.len() > 1 || show_future || has_currency {
        out.push_str("<ul class=\"track-legend\">\n");
        for (g, group) in groups.iter().enumerate() {
            let mut titles: Vec<&str> = group
                .keys
                .iter()
                .map(|&k| view.titles[k].as_str())
                .collect();
            titles.sort_unstable();
            titles.dedup();
            let names = titles
                .iter()
                .map(|t| esc(t))
                .collect::<Vec<_>>()
                .join(" · ");
            let _ = write!(out, "<li><span class=\"tag\">{}</span> {names}", group.tag);
            if !currencies[g].is_empty() {
                let currency = currencies[g];
                let _ = write!(
                    out,
                    " <span class=\"capsule-tag {currency}\">{}</span>",
                    req.t(currency)
                );
            }
            if let Some(future) = &view.future {
                let count = group.keys.iter().map(|&k| future[k]).max().unwrap_or(0);
                let keys: Vec<&str> = group
                    .keys
                    .iter()
                    .map(|&k| req.banners[k].key.as_str())
                    .collect();
                let _ = write!(
                    out,
                    " <label class=\"future-ctl\" title=\"{}\">{} <input type=\"number\" class=\"future-ubers\" value=\"{count}\" min=\"0\" max=\"99\" data-names=\"{}\"></label>",
                    req.t("Pad this banner's uber pool with expected-but-unreleased ubers (godfat's Count of future ubers) - its uber cells land as if those units were already in the pool; drag the box up/down to adjust"),
                    req.t("Add future ubers"),
                    esc(&json_list(&keys))
                );
                if count > 0 {
                    let rep = req.banners[group.keys[0]].key.as_str();
                    let _ = write!(
                        out,
                        " <span class=\"future-targets\" title=\"{}\">",
                        req.t("Toggle a future uber to search for it - it joins your Targets above and glows on this banner's cells")
                    );
                    for n in 1..=count {
                        let label = req.tr("Future Uber %(n)s", &[("n", &n.to_string())]);
                        let _ = write!(
                            out,
                            "<button type=\"button\" class=\"future-target\" aria-pressed=\"false\" data-future-name=\"{}\" title=\"{}\">{label}</button>",
                            esc(&format!("Future Uber {n} @ {rep}")),
                            req.tr("Search for %(label)s on %(banners)s", &[("label", &label), ("banners", &names)])
                        );
                    }
                    out.push_str("</span>");
                }
            }
            out.push_str("</li>\n");
        }
        out.push_str("</ul>\n");
    }

    let guaranteed = format!(
        "<th class=\"guaranteed-col\">{}</th>\n",
        req.t("Guaranteed")
    );
    let _ = write!(
        out,
        "<table class=\"track\">\n<thead><tr>\n<th class=\"pos\">#</th>\n<th>{}</th>\n",
        req.t("Track A")
    );
    if has_guaranteed {
        out.push_str(&guaranteed);
    }
    let _ = writeln!(out, "<th>{}</th>", req.t("Track B"));
    if has_guaranteed {
        out.push_str(&guaranteed);
    }
    out.push_str("</tr></thead>\n<tbody>\n");
    let details = |index: usize| {
        groups
            .iter()
            .find_map(|g| g.graph.pull(index))
            .map(|p| (p.rarity_seed, p.seed))
    };
    for pos in 1..=max_pos {
        let (a, b) = (2 * (pos - 1), 2 * (pos - 1) + 1);
        let _ = write!(out, "<tr>\n<th scope=\"row\" class=\"pos\">{pos}</th>\n");
        cell(
            &mut out,
            &ctx,
            &entries(&ctx, groups, marks, a),
            "",
            details(a),
        );
        if has_guaranteed {
            cell(
                &mut out,
                &ctx,
                &guaranteed_entries(&ctx, groups, marks, a),
                "guaranteed-col",
                None,
            );
        }
        cell(
            &mut out,
            &ctx,
            &entries(&ctx, groups, marks, b),
            "",
            details(b),
        );
        if has_guaranteed {
            cell(
                &mut out,
                &ctx,
                &guaranteed_entries(&ctx, groups, marks, b),
                "guaranteed-col",
                None,
            );
        }
        out.push_str("</tr>\n");
    }
    out.push_str("</tbody>\n</table>\n");
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn json_list_escapes_like_python() {
        assert_eq!(
            json_list(&["a", "Caf\u{e9} \"x\""]),
            "[\"a\", \"Caf\\u00e9 \\\"x\\\"\"]"
        );
    }

    #[test]
    fn future_uber_names_match_the_python_pattern() {
        assert!(is_future_uber("Future Uber 3 @ Some Fest"));
        assert!(is_future_uber("Future Uber 12"));
        assert!(!is_future_uber("Future Uber x"));
        assert!(!is_future_uber("Future Uber 1 @ "));
    }
}
