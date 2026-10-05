from shuper_whisper.caret import place_below

WORK = (0, 0, 1920, 1040)


def test_places_under_caret():
    assert place_below((500, 300, 502, 320), WORK, (100, 32), 6) == (494, 326)


def test_flips_above_near_bottom():
    assert place_below((500, 1020, 502, 1038), WORK, (100, 32), 6) == (494, 982)


def test_clamps_to_right_edge():
    assert place_below((1900, 300, 1902, 320), WORK, (100, 32), 6) == (1820, 326)


def test_clamps_to_left_edge_on_secondary_monitor():
    assert place_below((-1918, 300, -1916, 320), (-1920, 0, 0, 1040), (100, 32), 6) == (-1920, 326)
