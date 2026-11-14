from gra.parse import decode, html_to_text

GBK_PAGE = (
    '<html><head><meta charset="gb2312"></head><body>'
    "<nav>导航栏不要</nav>"
    "<div id='zoom'><p>加快发展新质生产力，推动经济高质量发展。</p>"
    "<p>2025年全省地区生产总值增长5.2%。</p></div>"
    "<footer>版权所有</footer></body></html>"
).encode("gb18030")


def test_decode_handles_gbk():
    assert "新质生产力" in decode(GBK_PAGE)


def test_html_to_text_drops_chrome():
    text = html_to_text(GBK_PAGE)
    assert "新质生产力" in text
    assert "导航栏" not in text
    assert "版权所有" not in text
