import pytest
from pydantic import ValidationError

from app.schemas import PostCreate


def test_post_create_accepts_valid_payload():
    post = PostCreate(
        category="39",
        title="좋은 제목",
        content="본문입니다",
        password="1234",
    )

    assert post.category == "39"
    assert post.title == "좋은 제목"


def test_post_create_rejects_invalid_category_and_short_password():
    with pytest.raises(ValidationError):
        PostCreate(
            category="99",
            title="제목",
            content="본문",
            password="12",
        )
