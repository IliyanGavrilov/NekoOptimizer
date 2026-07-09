from neko.rng import MASK, XorShift32, backtrack, unxorshift, xorshift


def test_known_vector():
    assert xorshift(1) == 0x1000A001


def test_unxorshift_inverts_xorshift():
    for seed in (0, 1, MASK, 12345, 1893568593, 0x9E3779B9):
        assert unxorshift(xorshift(seed)) == seed
        assert xorshift(unxorshift(seed)) == seed


def test_unxorshift_stays_in_32_bits():
    assert all(0 <= unxorshift(value) <= MASK for value in XorShift32(1).sequence(500))


def test_backtrack_steps_two_stream_values_per_roll():
    seed = 1893568593
    assert backtrack(seed) == unxorshift(unxorshift(seed))
    assert backtrack(seed, 3) == unxorshift(unxorshift(backtrack(seed, 2)))


def test_backtrack_then_advance_returns_to_the_seed():
    seed = 1893568593
    stepped = XorShift32(backtrack(seed))
    stepped.sequence(2)  # advance the two values a roll consumes
    assert stepped.state == seed


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
