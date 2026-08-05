"""Self-check for the critic-calibration endpoint. Run: python test_calibration.py"""
import api_server as api

_FAKE = {"own_tweet_performance": [
    {"text": "a", "likes": 0,  "replies": 0, "reposts": 0, "critic": {"score": 5, "first_line_hook": 3, "grounding": 9}},
    {"text": "b", "likes": 5,  "replies": 0, "reposts": 0, "critic": {"score": 6, "first_line_hook": 5, "grounding": 9}},
    {"text": "c", "likes": 10, "replies": 0, "reposts": 0, "critic": {"score": 7, "first_line_hook": 7, "grounding": 9}},
    {"text": "d", "likes": 20, "replies": 0, "reposts": 0, "critic": {"score": 8, "first_line_hook": 9, "grounding": 9}},
    {"text": "e", "likes": 0,  "replies": 0, "reposts": 0, "critic": None},   # unscored -> skipped
]}


def test_calibration():
    api.read_state = lambda: _FAKE
    r = api.critic_calibration()
    assert r["sample_size"] == 4, "records without critic scores must be skipped"
    assert r["with_engagement"] == 3
    # first_line_hook rises with engagement -> strong positive correlation
    assert r["correlations"]["first_line_hook"] > 0.9
    # constant axis has zero variance, and voice_match was never scored -> None, not 0.0
    assert r["correlations"]["grounding"] is None
    assert r["correlations"]["voice_match"] is None


def test_empty_state_does_not_explode():
    api.read_state = lambda: {}
    r = api.critic_calibration()
    assert r["sample_size"] == 0
    assert all(v is None for v in r["correlations"].values())


if __name__ == "__main__":
    test_calibration()
    test_empty_state_does_not_explode()
    print("calibration checks passed")
