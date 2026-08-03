from app.domain.fund_identity import fund_display_identity, fund_display_sort_key


def test_recognize_share_class_from_name_and_code() -> None:
    assert fund_display_identity("吉余示例基金B类", "T001").group_name == "吉余示例基金"
    assert fund_display_identity("吉余示例基金B类", "T001").share_class == "B类"
    assert fund_display_identity("吉余示例基金", "T001(A级)").share_class == "A类"
    assert fund_display_identity("吉余示例基金A", "T001A").share_class == "A类"


def test_sort_share_classes_next_to_base_fund() -> None:
    products = [
        ("吉余示例基金C类", "T001C"),
        ("吉余另一基金", "T002"),
        ("吉余示例基金", "T001"),
        ("吉余示例基金A类", "T001A"),
        ("吉余示例基金B类", "T001B"),
    ]

    ordered = sorted(products, key=lambda item: fund_display_sort_key(*item))

    assert ordered[-4:] == [
        ("吉余示例基金", "T001"),
        ("吉余示例基金A类", "T001A"),
        ("吉余示例基金B类", "T001B"),
        ("吉余示例基金C类", "T001C"),
    ]
