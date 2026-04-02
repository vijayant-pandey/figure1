"""
Handy date time functions
"""

import datetime
import math
from calendar import monthrange

import pytz

epoch = datetime.datetime(1970, 1, 1)
utc_epoch = epoch.replace(tzinfo=pytz.utc)


def utc_now(timezone=False):
    now = datetime.datetime.utcnow()
    if timezone:
        now = now.replace(tzinfo=datetime.timezone.utc)
    return now


def utc_from_timestamp(timestamp, timezone=False):
    t = datetime.datetime.utcfromtimestamp(timestamp)
    if timezone:
        return t.replace(tzinfo=datetime.timezone.utc)
    return t


def utc_now_timestamp(timezone=False):
    return utc_now(timezone=timezone).timestamp()


def today(timezone=False):
    """
    Gives you back today @ 00:00
    :return:
    """
    now = utc_now()
    now = datetime.datetime(year=now.year, month=now.month, day=now.day)
    if timezone:
        return now.replace(tzinfo=datetime.timezone.utc)
    return now


def yesterday():
    """
    Gives you back the previous day @ 00:00
    :return:
    """
    return today() - datetime.timedelta(days=1)


def start_week(week):
    """
    Gives you the start of the week @ 00:00 represented by 'week'
    :param week: the week you want to find the start of
    :return:
    """
    target_week = datetime.datetime(year=week.year, month=week.month, day=week.day).replace(tzinfo=week.tzinfo)
    if target_week.weekday() != 6:  # this is sunday, so we are already at the beginning of the week
        return (target_week - datetime.timedelta(days=target_week.weekday() + 1)).replace(tzinfo=week.tzinfo)
    return target_week


def following_week(week):
    """
    Gives you the start of the week @ 00:00 that follows the week represented by 'week'
    :param week: the reference week
    :return:
    """
    return week + datetime.timedelta(weeks=1)


def this_week(timezone=False):
    """
    Gives you the start of the current week (Sunday) @ 00:00
    :return:
    """
    now = today(timezone=timezone)
    return now - datetime.timedelta(days=now.weekday() + 1)


def start_day(now):
    """
    Gives you the start of the day that contains now
    :param now:
    :return:
    """
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def following_day(now):
    """
    Gives you the start of the next day that contains now
    :param now:
    :return:
    """
    return start_day(now) + datetime.timedelta(days=1)


def end_of_current_day(now):
    """
    Gives you the end of the current day
    :param now:
    :return:
    """
    return following_day(now) - datetime.timedelta(microseconds=1)


def last_week(timezone=False):
    """
    Gives you the start of the previous week (Sunday) @ 00:00
    :return:
    """
    return this_week(timezone=timezone) - datetime.timedelta(weeks=1)


def start_month(month):
    """
    Gives you the start of the month @ 00:00 represented by 'month'
    :param month: the week you want to find the start of
    :return:
    """
    return datetime.datetime(year=month.year, month=month.month, day=1).replace(tzinfo=month.tzinfo)


def following_month(month):
    """
    Gives you the start of the month @ 00:00 that follows the month represented by 'month'
    :param month: the reference month
    :return:
    """

    return month + datetime.timedelta(days=monthrange(month.year, month.month)[1])


def this_month():
    """
    Gives you the start of the current month @ 00:00
    :return:
    """
    now = today()
    return datetime.datetime(year=now.year, month=now.month, day=1)


def last_month():
    """
    Gives you the start of the previous month @ 00:00
    :return:
    """
    last_day_of_last_month = this_month() - datetime.timedelta(days=1)
    return datetime.datetime(year=last_day_of_last_month.year, month=last_day_of_last_month.month, day=1)


def start_year(year):
    """
    Gives you the start of the month @ 00:00 represented by 'month'
    :param year: the week you want to find the start of
    :return:
    """
    return datetime.datetime(year=year.year, month=1, day=1).replace(tzinfo=year.tzinfo)


def following_year(year):
    """
    Gives you the start of the year @ 00:00 that follows the year represented by 'year'
    :param year: the reference year (datetime)
    :return:
    """

    return datetime.datetime(year=year.year + 1, month=year.month, day=year.day).replace(tzinfo=year.tzinfo)


def this_year():
    """
    Gives you the start of the current year @ 00:00
    :return:
    """
    now = today()
    return datetime.datetime(year=now.year, month=1, day=1)


def last_year():
    """
    Gives you the start of the previous year @ 00:00
    :return:
    """
    beginning_of_this_year = this_year()
    return datetime.datetime(year=beginning_of_this_year.year - 1, month=1, day=1)


def long_format(value):
    return value.strftime('%Y-%m-%d %H:%M:%S.%f')


def this_minute():
    """
    Gives you the start of the current minute
    :return:
    """
    return datetime.datetime.utcnow().replace(second=0, microsecond=0)


def start_minute(minute):
    """
    Gives you the start of the current minute
    :param minute:
    :return:
    """
    return minute.replace(second=0, microsecond=0)


def following_minute(minute):
    """
    Gives you the start of the following minute
    :param minute: the current minute
    :return:
    """
    return start_minute(minute) + datetime.timedelta(seconds=60)


def last_5min():
    """
    Gives you the start of the previous 5 minute period
    :return:
    """
    period_secs = 60 * 5
    this_period_start = compute_period_start(datetime.datetime.utcnow(), period_secs)

    return this_period_start - datetime.timedelta(seconds=period_secs)


def following_5min(period):
    """
    Gives you the start of the 5 minute period that follows the 5 minute period represented by 'period'
    :param period: the reference period (datetime)
    :return:
    """

    return period + datetime.timedelta(seconds=60 * 5)


def start_5min(now):
    """
    Gives you the start of the 5 minute period that contains period
    :param now: a datetime
    :return:
    """
    return compute_period_start(now, 60 * 5)


def last_15min():
    """
    Gives you the start of the previous 15 minute period
    :return:
    """
    period_secs = 60 * 15
    this_period_start = compute_period_start(datetime.datetime.utcnow(), period_secs)

    return this_period_start - datetime.timedelta(seconds=period_secs)


def following_15min(period):
    """
    Gives you the start of the 15 minute period that follows the 15 minute period represented by 'period'
    :param period: the reference period (datetime)
    :return:
    """

    return period + datetime.timedelta(seconds=60 * 15)


def start_15min(now):
    """
    Gives you the start of the 5 minute period that contains period
    :param now: a datetime
    :return:
    """
    return compute_period_start(now, 60 * 15)


def last_hour():
    """
    Gives you the start of the previous 1 hour period
    :return:
    """
    period_secs = 60 * 60
    this_period_start = compute_period_start(datetime.datetime.utcnow(), period_secs)

    return this_period_start - datetime.timedelta(seconds=period_secs)


def following_hour(period):
    """
    Gives you the start of the 1 hour period that follows the 1 hour period represented by 'period'
    :param period: the reference period (datetime)
    :return:
    """

    return period + datetime.timedelta(seconds=60 * 60)


def start_hour(now):
    """
    Gives you the start of the 5 minute period that contains period
    :param now: a datetime
    :return:
    """
    return compute_period_start(now, 60 * 60)


def last_4hour():
    """
    Gives you the start of the previous 4 hour period
    :return:
    """
    period_secs = 60 * 60 * 4
    this_period_start = compute_period_start(datetime.datetime.utcnow(), period_secs)

    return this_period_start - datetime.timedelta(seconds=period_secs)


def following_4hour(period):
    """
    Gives you the start of the 4 hour period that follows the 4 hour period represented by 'period'
    :param period: the reference period (datetime)
    :return:
    """

    return period + datetime.timedelta(seconds=60 * 60 * 4)


def start_4hour(now):
    """
    Gives you the start of the 5 minute period that contains period
    :param now: a datetime
    :return:
    """
    return compute_period_start(now, 60 * 60 * 4)


def compute_period_start(now, duration_secs, timezone=True):
    """
    Computes the start time of a bar based on a reference timestamp.

    ** IMPORTANT ** The default implementation of this method only works for timescales of 1 day or less. Subclasses
    that represent durations of longer than one day should override this method with their own implementation that
    correctly computes the start of the bar.

    :param now: the reference datetime.datetime off which to base the start of a bar
    :param duration_secs: the duration that this bar represents
    :param timezone: true if the result should be timezone aware (default is False)
    :return: a datetime that represents the start time for a bar given a reference datetime and duration
    """
    current_second = (now.hour * 60 + now.minute) * 60 + now.second
    secs_to_start = math.floor(current_second / duration_secs) * duration_secs
    period_start = datetime.datetime(year=now.year, month=now.month, day=now.day)
    if timezone:
        period_start = period_start.replace(tzinfo=datetime.timezone.utc)
    period_start = period_start + datetime.timedelta(seconds=secs_to_start)
    return period_start
