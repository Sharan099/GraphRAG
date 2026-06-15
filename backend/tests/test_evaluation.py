from evaluation.run_evaluation import improvement_percent, keyword_recall


def test_keyword_recall_full_match():
    score = keyword_recall("Torque warning for oil filter", ["torque", "warning", "oil"])
    assert score == 1.0


def test_keyword_recall_partial_match():
    score = keyword_recall("Only torque is mentioned", ["torque", "warning"])
    assert score == 0.5


def test_keyword_recall_no_expected_keywords():
    score = keyword_recall("anything", [])
    assert score == 1.0


def test_improvement_percent_uses_remaining_headroom():
    score = improvement_percent(0.5, 0.75)
    assert score == 50.0


def test_improvement_percent_handles_perfect_baseline():
    score = improvement_percent(1.0, 1.0)
    assert score == 0.0
