from neko.cache import RollCache
from neko.godfat import TrackPull
from neko.models import Rarity

PULLS = [
    TrackPull(1, "A", "Bahamut", Rarity.UBER_SUPER_RARE),
    TrackPull(1, "B", "Cat", Rarity.RARE),
]


def test_load_missing_returns_none(tmp_path):
    assert RollCache(tmp_path).load(123, "ev", 30) is None


def test_round_trip_preserves_pulls(tmp_path):
    cache = RollCache(tmp_path)
    cache.save(123, "ev", 30, PULLS)
    assert cache.load(123, "ev", 30) == PULLS


def test_load_restores_rarity_enum(tmp_path):
    cache = RollCache(tmp_path)
    cache.save(123, "ev", 30, PULLS)
    assert isinstance(cache.load(123, "ev", 30)[0].rarity, Rarity)


def test_cache_key_includes_count(tmp_path):
    cache = RollCache(tmp_path)
    cache.save(123, "ev", 30, PULLS)
    assert cache.load(123, "ev", 60) is None
