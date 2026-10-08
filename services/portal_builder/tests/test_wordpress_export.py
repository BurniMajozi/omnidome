from types import SimpleNamespace

import pytest

from services.portal_builder.wordpress_export import ExportError, export_page


def page(blocks, **kwargs):
    return SimpleNamespace(title="Fibre & more", slug="fibre", description="Fast", content={"blocks": blocks},
                           seo_meta=kwargs.get("seo_meta"), custom_css=None)


def test_export_escapes_markup_and_is_deterministic():
    p = page([{"type": "hero", "heading": '<script>bad</script> Fibre & friends',
               "cta_label": "Enquire", "cta_url": "https://isp.example/contact"},
              {"type": "pricing", "items": [{"title": "100 Mbps", "price": "R599", "body": "Unlimited"}]}])
    result = export_page(p)
    assert "<script>" not in result["content"]
    assert "Fibre &amp; friends" in result["content"]
    assert "wp:button" in result["content"] and "R599" in result["content"]
    assert result["exported_hash"] == export_page(p)["exported_hash"]
    p.title = "Changed"
    assert result["exported_hash"] != export_page(p)["exported_hash"]


@pytest.mark.parametrize("block", [{"type": "form"}, {"type": "cta", "cta_label": "Enquire", "cta_url": "#enquiry"},
                                  {"type": "hero", "image": "/preview.png"},
                                  {"type": "cta", "cta_label": "Bad", "cta_url": "javascript:alert(1)"}])
def test_unsupported_or_broken_content_blocks_export(block):
    with pytest.raises(ExportError):
        export_page(page([block]))
