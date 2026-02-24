from datetime import datetime
from pydantic import BaseModel


class SubscriptionStatusStatsResponse(BaseModel):
    total: int
    active: int
    disabled: int
    expired: int
    limited: int
    pending: int
    available: int
    unavailable: int
    online: int
    offline: int
    total_usage: int
    last_24h_online: int
    last_24h_usage: int


class UsageSubscriptionDetail(BaseModel):
    username: str
    usage: int
    is_active: bool


class MostUsageSubscription(BaseModel):
    subscriptions: list[UsageSubscriptionDetail]
    start_date: datetime
    end_date: datetime


class UsageDetail(BaseModel):
    start_date: datetime
    end_date: datetime
    usage: int


class UsageStatsResponse(BaseModel):
    total: int
    usages: list[UsageDetail]
    start_date: datetime
    end_date: datetime


class AgentStatsDetail(BaseModel):
    category: str
    count: int


class AgentStatsResponse(BaseModel):
    agents: list[AgentStatsDetail]


class LastReachedSubscriptionDetail(BaseModel):
    username: str
    reached_at: datetime
    limited: bool
    expired: bool
