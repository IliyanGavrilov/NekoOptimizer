// The planner's results, worked out and rendered here instead of the server:
// planner.services' subset_solutions / subset_plan (the per-subset breakdown, each row's
// summary, seed-after, landing and highlighted track) and the _solutions.html /
// _solution.html / _solution_body.html / _steps.html markup they feed.
// planner/test_plans_engine.py holds both to the Python.

use std::collections::{HashMap, HashSet};
use std::fmt::Write;

use serde::Deserialize;

use crate::engine::Request;
use crate::graph::{Graph, Outcome};
use crate::roll::{roll_banner, BannerRolls, NONE};
use crate::search::{
    astar, beam_search, combinations, obtainable, solve_subsets, Currency, Kind, Leg, Multi, Path,
    State, SubsetPlan, DRAW,
};
use crate::tracks::{esc, groups, table, Group, Marks};

const SUBSET_TARGET_LIMIT: usize = 10;
const PLAN_FILTER_ROWS: usize = 12;
const WISHLIST_BEAM_WIDTH: usize = 500;
const TRACK_ROW_CAP: usize = 100;

#[derive(Deserialize)]
pub struct PlanArgs {
    pub targets: Vec<u32>,
    pub tickets: i64,
    pub catfood: i64,
    pub platinum: i64,
    pub legend: i64,
    pub ticket_value: i64,
    #[serde(default)]
    pub detail: Option<usize>,
    #[serde(default)]
    pub subset: Vec<u32>,
    pub apply_url: String,
    pub row_url: String,
}

// ---- shared steps (plan_shared) ------------------------------------------------------

/// A move replayed on ``graph`` holding ``last``: its outcomes and the cat held after.
fn move_walk(graph: &Graph, leg: &Leg, mut last: u32) -> Option<(Vec<Outcome>, u32)> {
    let first = graph.resolve(leg.pulls.first()?.position, last)?;
    let mut outcomes = Vec::with_capacity(leg.pulls.len());
    for pull in &leg.pulls {
        let outcome = if pull.guaranteed {
            graph.guaranteed(pull.position, first.switched)
        } else {
            graph.resolve(pull.position, last)
        }?;
        outcomes.push(outcome);
        last = outcome.cat;
    }
    Some((outcomes, last))
}

/// Which other groups each of a plan's moves can be rolled on without breaking it:
/// the same multi on offer at the same price, every pull landing where the plan's did, and
/// a target pull still giving that cat. ``graphs`` are indexed like the moves' banners;
/// ``members`` lists each group's banners, its representative first.
pub(crate) fn plan_shared(
    moves: &[Leg],
    targets: &HashSet<u32>,
    graphs: &[&Graph],
    members: &[Vec<usize>],
    multis: &[Vec<Multi>],
    excluded: &HashSet<usize>,
) -> (Vec<HashSet<usize>>, Vec<HashSet<usize>>) {
    let group_of: HashMap<usize, usize> = members
        .iter()
        .enumerate()
        .flat_map(|(g, m)| m.iter().map(move |&b| (b, g)))
        .collect();
    let mut shared = vec![HashSet::new(); members.len()];
    let mut gshared = vec![HashSet::new(); members.len()];
    let mut last = NONE;
    for (i, leg) in moves.iter().enumerate() {
        let own = group_of[&leg.banner];
        let Some((own_outcomes, own_end)) = move_walk(graphs[leg.banner], leg, last) else {
            break;
        };
        for (g, banners) in members.iter().enumerate() {
            if g == own || excluded.contains(&g) {
                continue;
            }
            if leg.kind != Kind::Single {
                let guaranteed = leg.pulls.iter().any(|p| p.guaranteed);
                let offered = banners
                    .iter()
                    .flat_map(|&b| multis.get(b).into_iter().flatten());
                if !offered.into_iter().any(|m| {
                    m.rolls == leg.pulls.len() && m.cost == leg.cost && m.guaranteed == guaranteed
                }) {
                    continue;
                }
            }
            let Some((outcomes, end)) = move_walk(graphs[banners[0]], leg, last) else {
                continue;
            };
            let fits =
                leg.pulls
                    .iter()
                    .zip(&own_outcomes)
                    .zip(&outcomes)
                    .all(|((pull, own), mine)| {
                        (pull.guaranteed || mine.next == own.next)
                            && (!targets.contains(&pull.cat) || mine.cat == pull.cat)
                    });
            if !fits {
                continue;
            }
            if let Some(follow) = moves.get(i + 1) {
                if end != own_end {
                    let next = graphs[follow.banner];
                    let start = follow.pulls[0].position;
                    if next.resolve(start, own_end) != next.resolve(start, end) {
                        continue;
                    }
                }
            }
            for pull in &leg.pulls {
                if pull.guaranteed {
                    &mut gshared[g]
                } else {
                    &mut shared[g]
                }
                .insert(pull.position);
            }
        }
        last = own_end;
    }
    (shared, gshared)
}

// ---- one solved row -------------------------------------------------------------------

/// The outcome the plan's walk took at ``pull``: resolved from the cat got before it,
/// with the recorded cat picking the reroll branch when the graph alone can't say.
fn walked_outcome(graph: &Graph, position: usize, cat: u32, before: u32) -> Option<Outcome> {
    let resolved = graph.resolve(position, before);
    [resolved, graph.reroll(position)]
        .into_iter()
        .flatten()
        .find(|o| o.cat == cat)
        .or(resolved)
}

/// The RNG state after the plan's last draw (plan_seed).
fn plan_seed(plan: &Path, graphs: &[Graph]) -> Option<u32> {
    let last = plan.pulls.last()?;
    let graph = &graphs[last.banner];
    if last.guaranteed {
        let inner = plan
            .pulls
            .iter()
            .find(|p| p.position == last.position && p.banner == last.banner && !p.guaranteed);
        let nominal = graph.resolve(last.position, NONE);
        let duped = matches!((inner, nominal), (Some(i), Some(n)) if i.cat != n.cat);
        let forced = graph
            .guaranteed(last.position, duped)
            .or_else(|| graph.guaranteed(last.position, false));
        return forced.map(|f| f.seed);
    }
    let before = if plan.pulls.len() > 1 {
        plan.pulls[plan.pulls.len() - 2].cat
    } else {
        NONE
    };
    walked_outcome(graph, last.position, last.cat, before).map(|o| o.seed)
}

/// The stream index the seed sits on after the plan (plan_landing).
fn plan_landing(plan: &Path, graphs: &[Graph]) -> Option<usize> {
    let pulls = &plan.pulls;
    let last = pulls.last()?;
    let graph = &graphs[last.banner];
    if last.guaranteed {
        if pulls.len() < 2 {
            return None;
        }
        let before = if pulls.len() > 2 {
            pulls[pulls.len() - 3].cat
        } else {
            NONE
        };
        let prev = pulls[pulls.len() - 2];
        return walked_outcome(graph, prev.position, prev.cat, before).map(|o| o.next + 1);
    }
    let before = if pulls.len() > 1 {
        pulls[pulls.len() - 2].cat
    } else {
        NONE
    };
    walked_outcome(graph, last.position, last.cat, before).map(|o| o.next)
}

fn plural(n: i64) -> &'static str {
    if n == 1 {
        ""
    } else {
        "s"
    }
}

fn cost_label(tickets: i64, catfood: i64, platinum: i64, legend: i64) -> String {
    let mut parts = Vec::new();
    if tickets != 0 {
        parts.push(format!("{tickets} ticket{}", plural(tickets)));
    }
    if platinum != 0 {
        parts.push(format!("{platinum} platinum ticket{}", plural(platinum)));
    }
    if legend != 0 {
        parts.push(format!("{legend} legend ticket{}", plural(legend)));
    }
    if catfood != 0 {
        parts.push(format!("{catfood} catfood"));
    }
    if parts.is_empty() {
        "free".to_owned()
    } else {
        parts.join(" + ")
    }
}

/// What the page renders for one result row.
struct Row {
    targets: Vec<u32>,
    found: Option<Solved>,
}

struct Solved {
    plan: Path,
    exact: bool,
    track: bool,
}

struct Ctx<'a> {
    req: &'a Request,
    view: &'a crate::tracks::View,
    args: &'a PlanArgs,
    groups: Vec<Group<'a>>,
    group_of: Vec<usize>, // per banner
    world: crate::search::World<'a>,
}

impl Ctx<'_> {
    fn name(&self, id: u32) -> &str {
        self.req.name(id)
    }

    fn by_name(&self, mut cats: Vec<u32>) -> Vec<u32> {
        cats.sort_by(|a, b| self.name(*a).cmp(self.name(*b)));
        cats.dedup();
        cats
    }

    fn joined(&self, cats: &[u32], with: &str) -> String {
        cats.iter()
            .map(|&c| esc(self.name(c)))
            .collect::<Vec<_>>()
            .join(with)
    }

    /// A group's banners' display titles, sorted and deduped (_titled).
    fn titles(&self, g: usize) -> Vec<&str> {
        let mut titles: Vec<&str> = self.groups[g]
            .keys
            .iter()
            .map(|&k| self.view.titles[k].as_str())
            .collect();
        titles.sort_unstable();
        titles.dedup();
        titles
    }

    fn currency(&self, g: usize) -> &'static str {
        self.groups[g]
            .keys
            .iter()
            .map(|&k| self.world.currencies[k].name())
            .find(|c| !c.is_empty())
            .unwrap_or("")
    }

    /// The plan's highlighted track (plan_highlight + plan_shared + plan_landing).
    fn track(&self, plan: &Path, targets: &HashSet<u32>) -> String {
        let mut marks: Vec<Marks> = self.groups.iter().map(|_| Marks::default()).collect();
        for pull in &plan.pulls {
            let m = &mut marks[self.group_of[pull.banner]];
            if pull.guaranteed {
                m.gpath.insert(pull.position);
                if targets.contains(&pull.cat) {
                    m.gtargets.insert(pull.position, pull.cat);
                }
            } else {
                m.path.insert(pull.position);
                if targets.contains(&pull.cat) {
                    m.targets.insert(pull.position, pull.cat);
                }
            }
        }
        for (n, leg) in plan.legs().iter().enumerate() {
            for pull in &leg.pulls {
                let m = &mut marks[self.group_of[pull.banner]];
                if pull.guaranteed {
                    &mut m.gsteps
                } else {
                    &mut m.steps
                }
                .insert(pull.position, n + 1);
            }
        }
        let members: Vec<Vec<usize>> = self.groups.iter().map(|g| g.keys.clone()).collect();
        let excluded: HashSet<usize> = (0..self.groups.len())
            .filter(|&g| {
                self.groups[g]
                    .keys
                    .iter()
                    .any(|&k| self.world.currencies[k] != Currency::None)
            })
            .collect();
        let graphs: Vec<&Graph> = self.world.graphs.iter().collect();
        let (shared, gshared) = plan_shared(
            &plan.moves,
            targets,
            &graphs,
            &members,
            &self.world.multis,
            &excluded,
        );
        for (g, m) in marks.iter_mut().enumerate() {
            m.shared = shared[g].clone();
            m.gshared = gshared[g].clone();
        }
        if let (Some(landing), Some(last)) =
            (plan_landing(plan, &self.world.graphs), plan.pulls.last())
        {
            marks[self.group_of[last.banner]].nexts.insert(landing);
        }
        let currencies: Vec<&str> = (0..self.groups.len()).map(|g| self.currency(g)).collect();
        table(
            self.req,
            self.view,
            &self.groups,
            &marks,
            TRACK_ROW_CAP,
            None,
            HashSet::new(),
            &currencies,
        )
    }

    /// _solution_body.html for a solved row.
    fn body(&self, out: &mut String, targets: &[u32], plan: &Path) {
        let wanted: HashSet<u32> = targets.iter().copied().collect();
        let label = cost_label(
            plan.tickets_used,
            plan.cost(),
            plan.platinum_used,
            plan.legend_used,
        );
        let cats: Vec<&str> = plan.pulls.iter().map(|p| self.name(p.cat)).collect();
        let _ = write!(
            out,
            "\n<div class=\"view-bar\">\n<button type=\"button\" class=\"apply-plan\" data-cats=\"{}\" data-tickets=\"{}\" data-catfood=\"{}\" data-platinum=\"{}\" data-legend=\"{}\"",
            esc(&cats.join("|")),
            plan.tickets_used,
            plan.cost(),
            plan.platinum_used,
            plan.legend_used
        );
        if let Some(seed) = plan_seed(plan, &self.world.graphs).filter(|&s| s != 0) {
            let last = plan.pulls.last().map_or("", |p| self.name(p.cat));
            let _ = write!(
                out,
                " data-seed-after=\"{seed}\" data-last-cat=\"{}\"",
                esc(last)
            );
        }
        let _ = write!(out, ">Apply this plan <span class=\"apply-cost\">{}</span></button>\n</div>\n<div class=\"plan-follow\">\n", esc(&label));
        self.steps(out, plan, &wanted, &label);
        out.push_str("<div class=\"plan-track\">");
        out.push_str(&self.track(plan, &wanted));
        out.push_str("</div>\n</div>\n");
    }

    /// _steps.html.
    fn steps(&self, out: &mut String, plan: &Path, targets: &HashSet<u32>, total: &str) {
        out.push_str("\n<div class=\"plan-steps\">\n<div class=\"steps-head\">\n<span class=\"steps-title\">Steps</span>\n<div class=\"step-nav\" role=\"group\" aria-label=\"Walk the plan step by step\">\n<button type=\"button\" class=\"step-nav-btn step-prev\" aria-label=\"Previous step\">&#8249;</button>\n<span class=\"step-count\" aria-live=\"polite\"></span>\n<button type=\"button\" class=\"step-nav-btn step-next\" aria-label=\"Next step\">&#8250;</button>\n</div>\n</div>\n<div class=\"step-list\">\n");
        for (n, leg) in plan.legs().iter().enumerate() {
            let n = n + 1;
            let rolls = leg.pulls.len() as i64;
            let funded = if leg.kind == Kind::Single {
                rolls - leg.cost / DRAW
            } else {
                0
            };
            let currency = leg.currency.name();
            let tickets = if currency.is_empty() { funded } else { 0 };
            let platinum = if leg.currency == Currency::Platinum {
                funded
            } else {
                0
            };
            let legend = if leg.currency == Currency::Legend {
                funded
            } else {
                0
            };
            let titles = self.titles(self.group_of[leg.banner]);
            out.push_str("<button type=\"button\" class=\"step-card");
            if !currency.is_empty() {
                let _ = write!(out, " capsule {currency}");
            }
            let names = titles
                .iter()
                .map(|t| esc(t))
                .collect::<Vec<_>>()
                .join(" · ");
            let _ = write!(out, "\" data-step=\"{n}\">\n<span class=\"step-card-head\">\n<span class=\"step-dot\">{n}</span>\n<span class=\"step-banner\">{names}");
            if titles.len() > 1 {
                out.push_str(" <span class=\"equiv-note\">same rolls</span>");
            }
            if !currency.is_empty() {
                let _ = write!(
                    out,
                    " <span class=\"capsule-tag {currency}\">{currency}</span>"
                );
            }
            out.push_str(
                "</span>\n</span>\n<span class=\"step-meta\">\n<span class=\"step-kind\">",
            );
            if leg.kind == Kind::Single {
                let _ = write!(out, "{rolls}&times; single pull{}", plural(rolls));
            } else {
                out.push_str(&esc(&leg.kind.label()));
            }
            out.push_str("</span>\n<span class=\"step-cost\">");
            if tickets != 0 {
                let _ = write!(
                    out,
                    "<span class=\"cost-part\">{tickets} ticket{}</span>",
                    plural(tickets)
                );
            }
            if platinum != 0 {
                let _ = write!(
                    out,
                    "<span class=\"cost-part platinum\">{platinum} platinum ticket{}</span>",
                    plural(platinum)
                );
            }
            if legend != 0 {
                let _ = write!(
                    out,
                    "<span class=\"cost-part legend\">{legend} legend ticket{}</span>",
                    plural(legend)
                );
            }
            if leg.cost != 0 {
                let _ = write!(out, "<span class=\"cost-part\">{} catfood</span>", leg.cost);
            }
            if tickets == 0 && platinum == 0 && legend == 0 && leg.cost == 0 {
                out.push_str("free");
            }
            out.push_str("</span>\n</span>\n");
            let gets: Vec<u32> = leg
                .pulls
                .iter()
                .map(|p| p.cat)
                .filter(|c| targets.contains(c))
                .collect();
            if !gets.is_empty() {
                out.push_str("<span class=\"step-gets\">gets ");
                for (i, &c) in gets.iter().enumerate() {
                    if i > 0 {
                        out.push_str(", ");
                    }
                    let _ = write!(out, "<span class=\"step-get\">{}</span>", esc(self.name(c)));
                }
                out.push_str("</span>\n");
            }
            out.push_str("</button>\n");
        }
        out.push_str("</div>\n");
        if !total.is_empty() {
            let _ = writeln!(
                out,
                "<p class=\"steps-total\">Total &middot; {}</p>",
                esc(total)
            );
        }
        out.push_str("</div>\n");
    }

    /// _solution.html.
    fn row(&self, out: &mut String, row: &Row, total: usize, open: bool) {
        let targets = self.joined(&row.targets, "|");
        let _ = write!(out, "\n<details class=\"solution\" data-cats=\"{targets}\"");
        if open && row.found.is_some() {
            out.push_str(" open");
        }
        let size = row.targets.len();
        let _ = write!(
            out,
            ">\n<summary>\n<span class=\"sol-cats\">{}</span>\n<span class=\"sol-count\" title=\"This plan gets {size} of the {total} cat{} you searched for\">{size}/{total}</span>\n",
            self.joined(&row.targets, ", "),
            plural(total as i64)
        );
        match &row.found {
            Some(solved) => {
                if !solved.exact {
                    let _ = writeln!(out, "<span class=\"sol-approx\" title=\"Best plan found, not a proven cheapest one. Past {SUBSET_TARGET_LIMIT} cats the search for the whole set is bounded - an exact one would take 2^N searches - so a cheaper plan may exist. Every smaller row here IS exact.\">best found</span>");
                }
                let plan = &solved.plan;
                let label = cost_label(
                    plan.tickets_used,
                    plan.cost(),
                    plan.platinum_used,
                    plan.legend_used,
                );
                let _ = write!(
                    out,
                    "<span class=\"sol-cost\">{}</span>\n</summary>\n<div class=\"solution-body\"",
                    esc(&label)
                );
                if solved.track {
                    out.push_str(">\n");
                    self.body(out, &row.targets, plan);
                } else {
                    let _ = write!(out, " data-subset=\"{targets}\">\n<p class=\"muted plan-loading\">Working out this plan&hellip;</p>\n");
                }
                out.push_str("</div>\n");
            }
            None => {
                out.push_str("<span class=\"sol-cost not-found\">Not found</span>\n</summary>\n")
            }
        }
        out.push_str("</details>\n");
    }

    fn start(&self) -> State {
        State {
            position: 0,
            tickets: self.args.tickets,
            draws: self.args.catfood / DRAW,
            found: Default::default(),
            last_banner: None,
            platinum: self.args.platinum,
            legend: self.args.legend,
            last_cat: self.req.id(&self.req.last_cat),
        }
    }

    /// The rows behind subset_solutions (_subset_plans), ranked, unfound ones after.
    fn rows(&self) -> Vec<Row> {
        let start = self.start();
        let items = self.by_name(self.args.targets.clone());
        let pool = obtainable(&self.world, &items);
        let pooled: HashSet<u32> = pool.iter().copied().collect();
        let names = |cats: &[u32]| {
            cats.iter()
                .map(|&c| self.name(c).to_owned())
                .collect::<Vec<_>>()
        };
        let mut found: Vec<(SubsetPlan, bool)>;
        let mut missing: Vec<Vec<u32>> = Vec::new();

        if pool.len() <= SUBSET_TARGET_LIMIT {
            found = solve_subsets(&self.world, &pool, &start, &names)
                .into_iter()
                .map(|sp| (sp, true))
                .collect();
            let keys: HashSet<Vec<u32>> = found.iter().map(|(sp, _)| sp.targets.clone()).collect();
            for size in (1..=pool.len()).rev() {
                for combo in combinations(&pool, size) {
                    if !keys.contains(&combo) {
                        missing.push(combo);
                    }
                }
            }
        } else {
            found = Vec::new();
            let mut full = beam_search(&self.world, &pool, &start, WISHLIST_BEAM_WIDTH, false);
            let mut got: Vec<u32> = pool.clone();
            if full.is_none() {
                full = beam_search(&self.world, &pool, &start, WISHLIST_BEAM_WIDTH, true);
                got = match &full {
                    Some(plan) => {
                        let cats: HashSet<u32> = plan.pulls.iter().map(|p| p.cat).collect();
                        pool.iter().copied().filter(|c| cats.contains(c)).collect()
                    }
                    None => Vec::new(),
                };
            }
            if let Some(plan) = full.filter(|_| got.len() > 1) {
                found.push((SubsetPlan { targets: got, plan }, false));
            }
            for &cat in &pool {
                if let Some(plan) = astar(&self.world, &[cat], &start, f64::INFINITY) {
                    found.push((
                        SubsetPlan {
                            targets: vec![cat],
                            plan,
                        },
                        true,
                    ));
                }
            }
            found.sort_by_key(|(sp, _)| (std::cmp::Reverse(sp.targets.len()), sp.plan.cost()));
            let keys: HashSet<Vec<u32>> = found.iter().map(|(sp, _)| sp.targets.clone()).collect();
            if !keys.contains(&pool) {
                missing.push(pool.clone());
            }
            missing.extend(
                pool.iter()
                    .filter(|&&c| !keys.contains(&vec![c]))
                    .map(|&c| vec![c]),
            );
        }
        missing.extend(
            items
                .iter()
                .filter(|c| !pooled.contains(c))
                .map(|&c| vec![c]),
        );

        let detail = self.args.detail;
        let mut rows: Vec<Row> = found
            .into_iter()
            .enumerate()
            .map(|(index, (sp, exact))| Row {
                targets: sp.targets,
                found: Some(Solved {
                    plan: sp.plan,
                    exact,
                    track: detail.is_none_or(|d| index < d),
                }),
            })
            .collect();
        rows.extend(missing.into_iter().map(|targets| Row {
            targets,
            found: None,
        }));
        rows
    }
}

fn context<'a>(
    req: &'a Request,
    view: &'a crate::tracks::View,
    args: &'a PlanArgs,
    rolls: &'a [BannerRolls],
) -> Ctx<'a> {
    let groups = groups(req, rolls, view);
    let mut group_of = vec![0; rolls.len()];
    for (g, group) in groups.iter().enumerate() {
        for &k in &group.keys {
            group_of[k] = g;
        }
    }
    let world = crate::search::World {
        graphs: rolls.iter().map(Graph::new).collect(),
        multis: req
            .banners
            .iter()
            .map(|b| {
                b.multis
                    .iter()
                    .map(|&(rolls, cost, guaranteed)| Multi {
                        rolls,
                        cost,
                        guaranteed,
                    })
                    .collect()
            })
            .collect(),
        currencies: req
            .banners
            .iter()
            .map(|b| match b.currency.as_str() {
                "platinum" => Currency::Platinum,
                "legend" => Currency::Legend,
                _ => Currency::None,
            })
            .collect(),
        ticket_value: args.ticket_value,
    };
    Ctx {
        req,
        view,
        args,
        groups,
        group_of,
        world,
    }
}

fn roll_all(req: &Request) -> Vec<BannerRolls> {
    let last = req.id(&req.last_cat);
    req.banners
        .iter()
        .map(|b| roll_banner(req.seed, &b.banner, req.count, b.guaranteed_rolls, last))
        .collect()
}

/// The solutions accordion (find_plan's _solutions.html).
pub fn solutions(req: &Request, view: &crate::tracks::View, args: &PlanArgs) -> String {
    let rolls = roll_all(req);
    let ctx = context(req, view, args, &rolls);
    let rows = ctx.rows();
    if rows.is_empty() {
        return "\n<p class=\"muted\">No reachable plan with given resources.</p>\n".to_owned();
    }
    let total = ctx.by_name(args.targets.clone()).len();
    let mut out = String::new();
    if rows.len() > PLAN_FILTER_ROWS {
        out.push_str("\n<div class=\"plan-filter\" id=\"planFilter\">\n<span class=\"plan-filter-label\">Only plans with</span>\n<span class=\"plan-filter-cats\">\n");
        for cat in ctx.by_name(args.targets.clone()) {
            let name = esc(ctx.name(cat));
            let _ = write!(out, "<button type=\"button\" class=\"filter-cat\" aria-pressed=\"false\" data-cat=\"{name}\">{name}</button>");
        }
        let _ = write!(out, "\n</span>\n<button type=\"button\" class=\"plan-filter-clear\" hidden>Clear</button>\n<span class=\"plan-filter-count\" aria-live=\"polite\">{} plans</span>\n</div>\n", rows.len());
    }
    let _ = write!(
        out,
        "\n<div id=\"planResults\" data-apply-url=\"{}\" data-row-url=\"{}\">\n",
        esc(&args.apply_url),
        esc(&args.row_url)
    );
    for (i, row) in rows.iter().enumerate() {
        ctx.row(&mut out, row, total, i == 0);
    }
    out.push_str("\n</div>\n");
    out
}

/// One opened row's body (plan_row's _solution_body.html), or "" when the subset has
/// no plan within the budget.
pub fn plan_row(req: &Request, view: &crate::tracks::View, args: &PlanArgs) -> String {
    let rolls = roll_all(req);
    let ctx = context(req, view, args, &rolls);
    let subset = ctx.by_name(args.subset.clone());
    match astar(&ctx.world, &subset, &ctx.start(), f64::INFINITY) {
        Some(plan) => {
            let mut out = String::new();
            ctx.body(&mut out, &subset, &plan);
            out
        }
        None => String::new(),
    }
}
