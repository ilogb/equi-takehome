from app.pipeline.funds import decide_fund, fund_key, normalize_entity


def test_normalize():
    assert normalize_entity("Northwind Global Macro Fund, L.P.") == "northwind global macro"
    assert normalize_entity("Northwind Global Macro Fund LP") == "northwind global macro"


def test_normalize_ampersand_becomes_and():
    assert "and" in normalize_entity("Smith & Co").split()


def test_normalize_drops_the():
    assert normalize_entity("The Alpha Fund") == "alpha"


def test_normalize_collapses_whitespace():
    assert normalize_entity("  Alpha   \t Beta\n Fund  ") == "alpha beta"


def test_normalize_drops_suffix_tokens():
    assert normalize_entity("Alpha Fund Ltd") == "alpha"
    assert normalize_entity("Alpha Limited") == "alpha"
    assert normalize_entity("Alpha SICAV plc") == "alpha"
    assert normalize_entity("Alpha Inc.") == "alpha"
    assert normalize_entity("Alpha Fund L P") == "alpha"


def test_decide_fund_reuses_existing():
    assert decide_fund("alpha", {"alpha": 7, "beta": 8}) == 7


def test_decide_fund_creates_when_unknown():
    assert decide_fund("gamma", {"alpha": 7}) is None


def test_fund_key_falls_back_when_everything_is_droppable():
    keys = [fund_key(n) for n in ("The Fund", "LP", "Inc.")]
    assert all(keys)
    assert len(set(keys)) == 3


def test_fund_key_matches_normalize_when_nonempty():
    assert fund_key("Northwind Global Macro Fund, L.P.") == "northwind global macro"
