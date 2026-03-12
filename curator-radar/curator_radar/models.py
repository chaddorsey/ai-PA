from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, Float, Boolean, DateTime, JSON, Text
from datetime import datetime


class Base(DeclarativeBase):
    pass


class StarredRepo(Base):
    __tablename__ = "starred_repos"

    repo_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    owner: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    language: Mapped[str | None] = mapped_column(String(50), nullable=True)
    topics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    stargazers_count: Mapped[int] = mapped_column(Integer, default=0)
    stargazers_count_at_fetch: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stargazers_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pushed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    starred_at_by_chad: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RepoStargazer(Base):
    __tablename__ = "repo_stargazers"

    repo_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_login: Mapped[str] = mapped_column(String(100), primary_key=True, index=True)
    starred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Curator(Base):
    __tablename__ = "curators"

    user_login: Mapped[str] = mapped_column(String(100), primary_key=True)
    platform: Mapped[str] = mapped_column(String(20), primary_key=True, default="github")
    overlap_count: Mapped[int] = mapped_column(Integer, default=0)
    overlap_score: Mapped[float] = mapped_column(Float, default=0.0)
    earlyness_mean: Mapped[float] = mapped_column(Float, default=0.0)
    last_scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False)


class CuratorEvent(Base):
    __tablename__ = "curator_events"

    event_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    user_login: Mapped[str] = mapped_column(String(100), index=True)
    repo_full_name: Mapped[str] = mapped_column(String(255))
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    processed: Mapped[bool] = mapped_column(Boolean, default=False)


class BackfillCheckpoint(Base):
    __tablename__ = "backfill_checkpoints"

    job_name: Mapped[str] = mapped_column(String(100), primary_key=True)
    checkpoint: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class BookmarkedTweet(Base):
    __tablename__ = "bookmarked_tweets"

    tweet_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    author_handle: Mapped[str] = mapped_column(String(100))
    author_name: Mapped[str] = mapped_column(String(200), default="")
    text: Mapped[str] = mapped_column(Text, default="")
    tweet_url: Mapped[str] = mapped_column(String(300))
    bookmarked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    likers_fetched: Mapped[bool] = mapped_column(Boolean, default=False)


class TweetLiker(Base):
    __tablename__ = "tweet_likers"

    tweet_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    user_handle: Mapped[str] = mapped_column(String(100), primary_key=True, index=True)
    user_name: Mapped[str] = mapped_column(String(200), default="")
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TwitterList(Base):
    __tablename__ = "twitter_lists"

    list_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    list_name: Mapped[str] = mapped_column(String(100))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TwitterListMember(Base):
    __tablename__ = "twitter_list_members"

    list_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    user_handle: Mapped[str] = mapped_column(String(100), primary_key=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
