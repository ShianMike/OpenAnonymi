from app.comparison.service import align_sources


def test_alignment_preserves_exact_unicode_line_endings_and_change_sections():
    before = "😀 Café 東京\r\nOld line\nShared\nRemoved\nEnd\n"
    after = "😀 Café 東京\r\nNew line\nShared\nEnd\nAdded\n"
    blocks, coarse = align_sources(before, after)
    assert not coarse
    assert "".join(block.left_text for block in blocks) == before
    assert "".join(block.right_text for block in blocks) == after
    assert [block.kind for block in blocks if block.change] == ["replace", "delete", "insert"]
    same, _ = align_sources(before, before)
    assert len(same) == 1 and same[0].change is None


def test_large_comparison_is_bounded_and_explicitly_coarse_without_losing_text():
    before = "start\n" + "a\n" * 40_000 + "end\n"
    after = "start\n" + "b\n" * 40_000 + "end\n"
    blocks, coarse = align_sources(before, after)
    assert coarse and len(blocks) == 3
    assert "".join(block.left_text for block in blocks) == before
    assert "".join(block.right_text for block in blocks) == after
    assert sum(block.change is not None for block in blocks) == 1
