import unittest

from sqlalchemy import select

from app.models import FriendRequest as FriendRequestModel
from app.routers import friends


class FriendRequestModelCollisionTests(unittest.TestCase):
    def test_route_keeps_friend_request_bound_to_orm_model(self) -> None:
        self.assertIs(friends.FriendRequest, FriendRequestModel)

        statement = select(friends.FriendRequest)
        self.assertIs(statement.column_descriptions[0]["entity"], FriendRequestModel)

    def test_add_request_uses_a_distinct_pydantic_model_name(self) -> None:
        self.assertIn("friend_ts_nickname", friends.FriendAddRequest.model_fields)
        self.assertIsNot(friends.FriendAddRequest, FriendRequestModel)


if __name__ == "__main__":
    unittest.main()
