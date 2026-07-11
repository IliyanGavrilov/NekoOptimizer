# The seed finders' in-process jobs: a search sieves the whole 2^32 seed space
# (~10s of numpy), so it runs on a daemon thread and the page polls for progress.
# One global registry, like the one global collection - a dev-server restart just
# forgets unfinished jobs and the page offers to search again. The rare and normal
# finders share the registry: a job is just a runner plus its polled state.

import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from neko.models import Banner, Rarity
from neko.normal import NormalBanner
from neko.seek import ProgressFn, SeekResult, seek_normal, seek_seed

_KEEP = 8  # jobs kept for late polls; older ones are pruned as new ones start

_jobs: dict[str, SeekJob] = {}
_lock = threading.Lock()

Runner = Callable[[ProgressFn], SeekResult]


@dataclass
class SeekJob:
    """One running or finished search. The worker thread writes ``progress``/``run``
    as it goes and ``result``/``error`` once; polls read whatever is there (single
    attribute writes, so no lock needed beyond the registry's)."""

    key: str
    last_cat: str  # the last observed pull's name: the found seed's dupe memory
    progress: float = 0.0
    run: int = 0
    result: SeekResult | None = None
    error: str = ""
    created: float = field(default_factory=time.monotonic)

    def snapshot(self) -> dict:
        """The polling payload: progress while running, the matches once done."""
        done = self.result is not None or bool(self.error)
        data = {
            "done": done,
            "progress": self.progress,
            "run": self.run,
            "error": self.error,
            "last_cat": self.last_cat,
        }
        if self.result is not None:
            data["truncated"] = self.result.truncated
            data["matches"] = [
                {"seed_before": m.seed_before, "seed_after": m.seed_after, "run": m.run}
                for m in self.result.matches
            ]

        return data


def start(banner: Banner, observed: list[tuple[Rarity, int]], last_cat: str) -> str:
    """Kick off a rare-gacha search."""
    return _start(lambda progress: seek_seed(banner, observed, progress=progress), last_cat)


def start_normal(banner: NormalBanner, observed: list[tuple[int, int]], last_item: str) -> str:
    """Kick off a normal-gacha search (the normal seed is its own, but the job
    life-cycle is identical)."""
    return _start(lambda progress: seek_normal(banner, observed, progress=progress), last_item)


def get(key: str) -> SeekJob | None:
    with _lock:
        return _jobs.get(key)


def _start(runner: Runner, last_cat: str) -> str:
    job = SeekJob(uuid.uuid4().hex[:12], last_cat)
    with _lock:
        _prune()
        _jobs[job.key] = job

    threading.Thread(target=_work, args=(job, runner), daemon=True).start()

    return job.key


def _work(job: SeekJob, runner: Runner) -> None:
    def note(run: int, fraction: float) -> None:
        job.run, job.progress = run, fraction

    try:
        job.result = runner(note)
    except Exception as error:  # noqa: BLE001 - a dead thread would spin the poll forever
        job.error = str(error)


def _prune() -> None:
    for job in sorted(_jobs.values(), key=lambda j: j.created)[:-_KEEP]:
        del _jobs[job.key]
