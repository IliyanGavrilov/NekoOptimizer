// The planner engine's entry point: one JSON request in, one response out. The server
// hands the page a request (the seed, the selected banners' pools and rates, names
// interned once); the page passes it here and shows what comes back.

use std::collections::HashMap;

use serde::Deserialize;
use serde_json::{json, Value};

use crate::roll::{roll_banner, Banner, TrackPull, NONE};

#[derive(Deserialize)]
pub struct RollBanner {
    pub key: String,
    #[serde(flatten)]
    pub banner: Banner,
    #[serde(default)]
    pub guaranteed_rolls: u32,
    /// The banner's multi-roll options as (rolls, catfood, guaranteed), and the scarce
    /// ticket it runs on ("platinum"/"legend", or "" for rare tickets and catfood).
    #[serde(default)]
    pub multis: Vec<(usize, i64, bool)>,
    #[serde(default)]
    pub currency: String,
    /// A normal machine's display name.
    #[serde(default)]
    pub name: String,
}

#[derive(Deserialize)]
pub struct Request {
    pub op: String,
    pub names: Vec<String>,
    pub seed: u32,
    pub count: usize,
    #[serde(default)]
    pub last_cat: String,
    pub banners: Vec<RollBanner>,
    pub view: Option<crate::tracks::View>,
    pub plan: Option<crate::plans::PlanArgs>,
    pub normal: Option<crate::normal::NormalArgs>,
    /// The page's text in its interface language, keyed by the English: whatever it
    /// leaves out (all of it, for English) renders as written.
    #[serde(default)]
    pub text: HashMap<String, String>,
}

impl Request {
    /// A name's id in the table, NONE when it isn't one (an unknown last cat can't dupe).
    pub fn id(&self, name: &str) -> u32 {
        self.names
            .iter()
            .position(|n| n == name)
            .map_or(NONE, |i| i as u32)
    }

    /// One piece of the page's text in its interface language.
    pub fn t<'a>(&'a self, english: &'a str) -> &'a str {
        self.text.get(english).map_or(english, String::as_str)
    }

    /// A piece of text keyed apart from its English (``key``), for words that read
    /// differently in different places; ``english`` when it isn't translated.
    pub fn t_keyed<'a>(&'a self, key: &str, english: &'a str) -> &'a str {
        self.text.get(key).map_or(english, String::as_str)
    }

    /// ``t`` for a message with ``%(name)s`` slots (Django's blocktranslate form, where a
    /// literal percent is doubled), each filled with its already-escaped value.
    pub fn tr(&self, english: &str, args: &[(&str, &str)]) -> String {
        let mut out = self.t(english).replace("%%", "\u{0}");
        for (name, value) in args {
            out = out.replace(&format!("%({name})s"), value);
        }
        out.replace('\u{0}', "%")
    }

    /// ``tr`` for a counted message: English's singular for one, its plural otherwise -
    /// the request carries each form's translation under its own English.
    pub fn trn(&self, singular: &str, plural: &str, n: i64, args: &[(&str, &str)]) -> String {
        self.tr(if n == 1 { singular } else { plural }, args)
    }

    pub fn name(&self, id: u32) -> &str {
        if id == NONE {
            ""
        } else {
            &self.names[id as usize]
        }
    }
}

pub fn handle(request: &str) -> String {
    match serde_json::from_str::<Request>(request) {
        Ok(req) => match req.op.as_str() {
            "rolls" => rolls(&req).to_string(),
            "solutions" | "plan_row" => match (&req.view, &req.plan) {
                (Some(view), Some(plan)) if req.op == "solutions" => {
                    crate::plans::solutions(&req, view, plan)
                }
                (Some(view), Some(plan)) => crate::plans::plan_row(&req, view, plan),
                _ => json!({ "error": "plans need a view and a plan" }).to_string(),
            },
            "normal_tracks" => match &req.normal {
                Some(normal) => crate::normal::normal_tracks(&req, normal),
                None => json!({ "error": "normal tracks need their args" }).to_string(),
            },
            "normal_plan" => match req
                .normal
                .as_ref()
                .and_then(|n| n.plan.as_ref().map(|p| (n, p)))
            {
                Some((normal, plan)) => crate::normal::normal_plan(&req, normal, plan),
                None => json!({ "error": "a normal plan needs its args" }).to_string(),
            },
            "tracks" => match &req.view {
                Some(view) => crate::tracks::render(&req, view),
                None => json!({ "error": "tracks needs a view" }).to_string(),
            },
            other => json!({ "error": format!("unknown op {other}") }).to_string(),
        },
        Err(error) => json!({ "error": error.to_string() }).to_string(),
    }
}

/// Every selected banner's raw rolls, names spelled out: the engine's own output, for
/// holding it to the Python roller.
fn rolls(req: &Request) -> Value {
    let last = req.id(&req.last_cat);
    let pulls = |list: &[TrackPull]| -> Vec<Value> {
        list.iter()
            .map(|p| {
                json!([
                    p.position,
                    p.track,
                    req.name(p.cat),
                    p.rarity,
                    p.seed,
                    p.steps,
                    p.realized,
                    p.rarity_seed
                ])
            })
            .collect()
    };
    let out: serde_json::Map<String, Value> = req
        .banners
        .iter()
        .map(|b| {
            let r = roll_banner(req.seed, &b.banner, req.count, b.guaranteed_rolls, last);
            let value = json!({
                "pulls": pulls(&r.pulls),
                "rerolls": pulls(&r.rerolls),
                "guaranteed": pulls(&r.guaranteed),
                "guaranteed_rerolls": pulls(&r.guaranteed_rerolls),
            });
            (b.key.clone(), value)
        })
        .collect();
    Value::Object(out)
}
