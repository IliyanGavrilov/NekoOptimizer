from neko.rng import MASK, XorShift32, xorshift


def test_known_vector_from_seed_one():
    # Worked out by hand from the spec:
    #   x=1 -> (1^8192)=8193 -> (8193>>17)=0 -> 8193^(8193<<15)=0x1000A001
    assert xorshift(1) == 0x1000A001 == 268476417


def test_zero_is_a_fixed_point():
    # Every shift of 0 is 0, so the generator gets stuck on a zero seed.
    assert xorshift(0) == 0


def test_output_stays_in_32_bits():
    state = 0x9E3779B9
    for _ in range(1000):
        state = xorshift(state)
        assert 0 <= state <= MASK


def test_class_matches_bare_function():
    rng = XorShift32(12345)
    state = 12345
    for _ in range(50):
        state = xorshift(state)
        assert rng.advance() == state


def test_same_seed_is_deterministic():
    assert XorShift32(777).sequence(100) == XorShift32(777).sequence(100)


def test_different_seeds_diverge():
    assert XorShift32(1).sequence(20) != XorShift32(2).sequence(20)


def test_seed_is_masked_to_32_bits():
    # A seed above 2**32 must behave exactly like its low 32 bits.
    big = (5 << 32) | 12345
    assert XorShift32(big).sequence(10) == XorShift32(12345).sequence(10)


def test_state_tracks_last_value():
    rng = XorShift32(42)
    assert rng.state == 42
    produced = rng.advance()
    assert rng.state == produced


def test_sequence_equals_repeated_advance():
    bulk = XorShift32(99).sequence(30)
    one_at_a_time = XorShift32(99)
    assert bulk == [one_at_a_time.advance() for _ in range(30)]
