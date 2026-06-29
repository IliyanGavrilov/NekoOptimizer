from neko.cache import RollCache
from neko.godfat import BannerRolls, TrackPull
from neko.models import Rarity

ROLLS = BannerRolls(
    [TrackPull(1, "A", "Bahamut", Rarity.UBER_SUPER_RARE), TrackPull(1, "B", "Cat", Rarity.RARE)],
    [TrackPull(11, "A", "Kasli", Rarity.UBER_SUPER_RARE)],
    [TrackPull(7, "A", "Jurassic Cat", Rarity.RARE)],
)


def test_load_missing_returns_none(tmp_path):
    assert RollCache(tmp_path).load(123, "ev", 30) is None


def test_round_trip_preserves_rolls(tmp_path):
    cache = RollCache(tmp_path)
    cache.save(123, "ev", 30, ROLLS)
    assert cache.load(123, "ev", 30) == ROLLS


def test_round_trip_preserves_guaranteed(tmp_path):
    cache = RollCache(tmp_path)
    cache.save(123, "ev", 30, ROLLS)
    assert cache.load(123, "ev", 30).guaranteed == ROLLS.guaranteed


def test_round_trip_preserves_rerolls(tmp_path):
    cache = RollCache(tmp_path)
    cache.save(123, "ev", 30, ROLLS)
    assert cache.load(123, "ev", 30).rerolls == ROLLS.rerolls


def test_load_restores_rarity_enum(tmp_path):
    cache = RollCache(tmp_path)
    cache.save(123, "ev", 30, ROLLS)
    assert isinstance(cache.load(123, "ev", 30).pulls[0].rarity, Rarity)


def test_cache_key_includes_count(tmp_path):
    cache = RollCache(tmp_path)
    cache.save(123, "ev", 30, ROLLS)
    assert cache.load(123, "ev", 60) is None
