from gra.attention import (
    SimhashIndex,
    attention_share,
    cjk_count,
    copying_rate,
    hamming,
    simhash,
    split_sentences,
)


def test_cjk_count_ignores_punctuation_and_latin():
    assert cjk_count("2025年GDP增长5.2%") == 3


def test_attention_share_known_answer():
    text = "新质生产力新质生产力" + "的政策" * 8
    share = attention_share(text, ["新质生产力"], per=1000)
    assert abs(share - 2 / len(text) * 1000) < 1e-9


def test_simhash_identical_is_zero_distance():
    s = "加快发展新质生产力，推动高质量发展"
    assert hamming(simhash(s), simhash(s)) == 0


def test_simhash_near_duplicate_is_close():
    a = "加快发展新质生产力推动经济高质量发展"
    b = a + "。"
    assert hamming(simhash(a), simhash(b)) <= 8


def test_index_finds_copy_and_misses_novel_sentence():
    index = SimhashIndex()
    central = "加快发展新质生产力，推动经济高质量发展"
    index.add(simhash(central), 0)
    assert index.query(simhash("加快发展新质生产力，推动经济高质量发展")) is True
    assert index.query(simhash("加强基层医疗卫生服务体系建设")) is False


def test_copying_rate_range():
    index = SimhashIndex()
    index.add(simhash("加快发展新质生产力"), 0)
    sents = ["加快发展新质生产力", "加强基层医疗卫生服务体系建设"]
    rate = copying_rate(sents, index)
    assert 0.0 <= rate <= 1.0


def test_split_sentences_filters_short():
    assert split_sentences("好。加快发展新质生产力，推动高质量发展。") == [
        "加快发展新质生产力，推动高质量发展"
    ]
