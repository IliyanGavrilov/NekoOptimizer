// The site's browser-side number crunching, compiled to planner/static/planner/neko.wasm:
// the seed finder's sieve (seek) and the Cat Guide screenshot reader (guide).
// After a change: cargo build --release --target wasm32-unknown-unknown, then copy
// target/wasm32-unknown-unknown/release/nekowasm.wasm to planner/static/planner/neko.wasm.

pub mod guide;
pub mod seek;

#[cfg(target_arch = "wasm32")]
mod exports {
    use crate::guide::{self, Grid, Image, CELLS};
    use crate::seek::{candidates, scan, Spec};
    use std::cell::UnsafeCell;

    const MAX_MATCHES: usize = 64;

    struct Buffer<T>(UnsafeCell<T>);
    // A wasm32 instance runs on one thread; each worker gets its own instance.
    unsafe impl<T> Sync for Buffer<T> {}

    static SEEK_INPUT: Buffer<[u32; 1024]> = Buffer(UnsafeCell::new([0; 1024]));
    static SEEK_OUTPUT: Buffer<[u32; 3 * MAX_MATCHES]> =
        Buffer(UnsafeCell::new([0; 3 * MAX_MATCHES]));
    static GUIDE_PAGE: Buffer<[f64; 9]> = Buffer(UnsafeCell::new([0.0; 9]));
    static GUIDE_MARKS: Buffer<[u8; CELLS]> = Buffer(UnsafeCell::new([0; CELLS]));

    #[link(wasm_import_module = "env")]
    extern "C" {
        fn progress(run: u32, fraction: f64);
    }

    // ---- seek: a worker writes the spec into ``seek_input`` as [pools, sizes..,
    // bands.. (pools + 1), rerollable mask, pulls, (pool, slot)..], asks
    // ``seek_pass_size`` for a pass's size, ``seek_search``es its slice and reads
    // (seed_before, seed_after, run) triples from ``seek_output``. Counts cross as f64:
    // at most 2^32, exact.

    fn spec() -> Spec {
        let words = unsafe { &*SEEK_INPUT.0.get() };
        let pools = words[0] as usize;
        let n = words[3 + 2 * pools] as usize;
        let pairs = &words[4 + 2 * pools..4 + 2 * pools + 2 * n];
        Spec {
            cats: pairs.chunks(2).map(|p| (p[0] as usize, p[1])).collect(),
            bands: words[1 + pools..2 + 2 * pools].to_vec(),
            sizes: words[1..1 + pools].to_vec(),
            rerollable: words[2 + 2 * pools],
        }
    }

    #[no_mangle]
    pub extern "C" fn seek_input() -> *mut u32 {
        SEEK_INPUT.0.get().cast()
    }

    #[no_mangle]
    pub extern "C" fn seek_output() -> *const u32 {
        SEEK_OUTPUT.0.get().cast()
    }

    #[no_mangle]
    pub extern "C" fn seek_pass_size(run: u32) -> f64 {
        candidates(&spec(), run) as f64
    }

    /// Scan candidates ``from..to`` of pass ``run``; the match count written to output.
    #[no_mangle]
    pub extern "C" fn seek_search(run: u32, from: f64, to: f64, cap: u32) -> u32 {
        let cap = (cap as usize).clamp(1, MAX_MATCHES);
        let found = scan(
            &spec(),
            run,
            from as u64,
            to as u64,
            cap,
            &mut |run, f| unsafe { progress(run, f) },
        );
        let out = unsafe { &mut *SEEK_OUTPUT.0.get() };
        for (i, m) in found.iter().enumerate() {
            out[3 * i..3 * i + 3].copy_from_slice(&[m.seed_before, m.seed_after, m.run]);
        }
        found.len() as u32
    }

    // ---- guide: the page copies a screenshot's RGBA pixels into ``alloc``ed memory,
    // ``guide_measure``s every shot, then ``guide_read``s each under the best grid found.

    #[no_mangle]
    pub extern "C" fn alloc(len: usize) -> *mut u8 {
        let mut bytes = Vec::<u8>::with_capacity(len);
        let ptr = bytes.as_mut_ptr();
        std::mem::forget(bytes);
        ptr
    }

    /// # Safety
    /// ``ptr`` and ``len`` must come from one ``alloc`` call, freed once.
    #[no_mangle]
    pub unsafe extern "C" fn dealloc(ptr: *mut u8, len: usize) {
        drop(Vec::from_raw_parts(ptr, 0, len));
    }

    fn image<'a>(ptr: *const u8, w: usize, h: usize) -> Image<'a> {
        Image {
            px: unsafe { std::slice::from_raw_parts(ptr, 4 * w * h) },
            w,
            h,
        }
    }

    /// Measure a shot into ``guide_page`` as [position, x, y, w, h, dx, dy, cols, rows];
    /// bit 0 of the result says the position was found, bit 1 the grid.
    #[no_mangle]
    pub extern "C" fn guide_measure(ptr: *const u8, w: usize, h: usize) -> u32 {
        let img = image(ptr, w, h);
        let out = unsafe { &mut *GUIDE_PAGE.0.get() };
        let position = guide::position(&img);
        let grid = guide::grid(&img);
        out[0] = position.unwrap_or(0.0);
        if let Some(g) = grid {
            let fields = [g.x, g.y, g.w, g.h, g.dx, g.dy, g.cols, g.rows];
            for (slot, value) in out[1..].iter_mut().zip(fields) {
                *slot = value as f64;
            }
        }
        u32::from(position.is_some()) | u32::from(grid.is_some()) << 1
    }

    #[no_mangle]
    pub extern "C" fn guide_page() -> *const f64 {
        GUIDE_PAGE.0.get().cast()
    }

    /// The shot's 24 cell marks (0 empty, 1 locked, 2 owned) under the given grid.
    #[no_mangle]
    #[allow(clippy::too_many_arguments)]
    pub extern "C" fn guide_read(
        ptr: *const u8,
        w: usize,
        h: usize,
        x: usize,
        y: usize,
        cw: usize,
        ch: usize,
        dx: usize,
        dy: usize,
    ) -> *const u8 {
        let grid = Grid {
            x,
            y,
            w: cw,
            h: ch,
            dx,
            dy,
            cols: 6,
            rows: 4,
        };
        let out = unsafe { &mut *GUIDE_MARKS.0.get() };
        for (slot, mark) in out.iter_mut().zip(guide::marks(&image(ptr, w, h), &grid)) {
            *slot = mark as u8;
        }
        out.as_ptr()
    }
}
