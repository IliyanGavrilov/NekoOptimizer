MASK = 0xFFFFFFFF  # 32-bit wraparound, like the game's uint32


def xorshift(state: int) -> int:
    """One 32-bit xorshift step; 0 is a fixed point. O(1)."""
    x = state & MASK
    x ^= (x << 13) & MASK
    x ^= x >> 17
    x ^= (x << 15) & MASK
    return x


def _undo_shift_xor(y: int, shift: int, left: bool) -> int:
    """Invert one ``x ^= x << shift`` (or ``>>``) step. Each pass fixes another
    ``shift`` bits, so ceil(32 / shift) passes recover x fully."""
    x = y
    for _ in range(0, 32, shift):
        x = y ^ (((x << shift) & MASK) if left else (x >> shift))
    return x & MASK


def unxorshift(state: int) -> int:
    """The inverse of ``xorshift``: undo each XOR-shift in reverse order. Stepping the
    seed backward (godfat's Backtrack) rolls the stream in reverse. O(1)."""
    x = _undo_shift_xor(state & MASK, 15, left=True)
    x = _undo_shift_xor(x, 17, left=False)
    return _undo_shift_xor(x, 13, left=True)


def backtrack(seed: int, rolls: int = 1) -> int:
    """The seed ``rolls`` pulls earlier in the stream. A pull advances the same track by
    two stream values, so stepping the RNG back twice per roll makes the pull just before
    the current first cell the new first cell (godfat's Backtrack)."""
    for _ in range(2 * rolls):
        seed = unxorshift(seed)
    return seed


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
