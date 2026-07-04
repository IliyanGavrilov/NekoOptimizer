from neko.rng import MASK, XorShift32, xorshift


def test_known_vector():
    assert xorshift(1) == 0x1000A001


def test_zero_is_fixed_point():
    assert xorshift(0) == 0


def test_output_stays_in_32_bits():
    assert all(0 <= value <= MASK for value in XorShift32(0x9E3779B9).sequence(1000))


def test_class_matches_repeated_function():
    expected, state = [], 12345
    for _ in range(50):
        state = xorshift(state)
        expected.append(state)
    assert XorShift32(12345).sequence(50) == expected


def test_initial_state_is_masked_seed():
    assert XorShift32((5 << 32) | 12345).state == 12345


def test_state_follows_last_advance():
    rng = XorShift32(42)
    assert rng.advance() == rng.state
