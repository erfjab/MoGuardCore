from datetime import datetime, timedelta
import math


class FormatUtils:
    @staticmethod
    def byte_convert(byte: int) -> str:
        """Convert bytes to a human-readable format."""
        if byte == 0:
            return "0B"
        sign = ""
        if byte < 0:
            sign = "-"
            byte = abs(byte)

        byte = float(byte)
        size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
        i = int(math.floor(math.log(byte, 1024)))
        p = math.pow(1024, i)
        s = "%.2f" % (byte / p)
        return f"{sign}{s} {size_name[i]}"

    @staticmethod
    def time_convert(expire: int) -> str:
        if expire == 0:
            return "Unlimited"
        if expire < 0:
            expire = abs(expire)
        elif expire > 0:
            expire = expire - int(datetime.utcnow().timestamp())
        days, remainder = divmod(expire, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        time_parts = []
        if days > 0:
            time_parts.append(f"{days} d")
        if hours > 0:
            time_parts.append(f"{hours} h")
        if minutes > 0:
            time_parts.append(f"{minutes} min")
        if seconds > 0:
            time_parts.append(f"{seconds} sec")
        return ", ".join(time_parts[:2])

    @staticmethod
    def day_convert(expire: int) -> int:
        if expire < 0:
            return abs(expire) // 86400
        elif expire > 0:
            return int((expire - int(datetime.utcnow().timestamp())) / 86400)

    @staticmethod
    def date_convert(expire: int) -> str:
        current_ts = int(datetime.utcnow().timestamp())
        MAX_SECONDS = 315360000  # 10 years in seconds

        if expire < 0:
            expire = abs(expire)
        elif expire > 0:
            expire = expire - current_ts

        if expire > MAX_SECONDS:
            expire = MAX_SECONDS

        try:
            target_date = datetime.utcnow() + timedelta(seconds=expire)
        except OverflowError:
            target_date = datetime.utcnow() + timedelta(seconds=MAX_SECONDS)

        return target_date.strftime("%Y-%m-%d %H:%M:%S UTC")
