MASK = 0xFFFFFFFF  # 32-bit wraparound, like the game's uint32


def xorshift(state: int) -> int:
    """One 32-bit xorshift step; 0 is a fixed point. O(1)."""
    x = state & MASK
    x ^= (x << 13) & MASK
    x ^= x >> 17
    x ^= (x << 15) & MASK
    return x


class XorShift32:
    """Stateful wrapper over the shared seed."""

    def __init__(self, seed: int) -> None:
        self._state = seed & MASK

    @property
    def state(self) -> int:
        """Current seed."""
        return self._state

    def advance(self) -> int:
        """Advance one step and return the new value. O(1)."""
        self._state = xorshift(self._state)
        return self._state

    def sequence(self, n: int) -> list[int]:
        """Next n values. O(n)."""
        return [self.advance() for _ in range(n)]
