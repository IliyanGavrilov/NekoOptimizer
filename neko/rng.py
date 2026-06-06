"""Battle Cats' shared XOR-shift PRNG.

Every banner is driven by one 32-bit seed. Each pull advances the seed, so once
the seed is known the entire future pull sequence is fully determined. This
module is just the number generator; turning the raw stream into rarities,
units, and track switches is the graph builder's job.
"""

MASK = 0xFFFFFFFF  # 32-bit wraparound, like the game's uint32


def xorshift(state: int) -> int:
    """Advance one step of the 32-bit xorshift. Pure, O(1).

    state -> next state, both in [0, 2**32). Note that 0 is a fixed point.
    """
    x = state & MASK
    x ^= (x << 13) & MASK
    x ^= x >> 17
    x ^= (x << 15) & MASK
    return x


class XorShift32:
    """Stateful view of the shared seed: each advance() yields the next number."""

    def __init__(self, seed: int) -> None:
        self._state = seed & MASK

    @property
    def state(self) -> int:
        """The current seed (last value produced, or the initial seed)."""
        return self._state

    def advance(self) -> int:
        """Advance the seed one step and return the new value. O(1)."""
        self._state = xorshift(self._state)
        return self._state

    def sequence(self, n: int) -> list[int]:
        """The next n values, advancing the seed n times. O(n)."""
        return [self.advance() for _ in range(n)]
