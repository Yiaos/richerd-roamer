from roamerd.capabilities.hearing.wake_phrases import strip_wake_phrase


def test_strip_wake_phrase_removes_prefix_variants() -> None:
    phrases = ["小乐小乐", "小乐"]

    assert strip_wake_phrase("小乐小乐回充电", phrases) == "回充电"
    assert strip_wake_phrase("小乐，回充电", phrases) == "回充电"
    assert strip_wake_phrase("  小乐小乐   现在几点  ", phrases) == "现在几点"


def test_strip_wake_phrase_only_strips_leading_phrase() -> None:
    phrases = ["小乐小乐"]

    assert strip_wake_phrase("请小乐小乐回充电", phrases) == "请小乐小乐回充电"
    assert strip_wake_phrase("回充电小乐小乐", phrases) == "回充电小乐小乐"
