import os
import re
import time


def normalize_name_pep427(name):
    return re.sub(r"[-_.]+", "_", name).lower()


def source_date_time(mtime):
    """Honor reproducible builds"""
    return int(os.environ.get("SOURCE_DATE_EPOCH", mtime))


def source_date_time_zinfo(mtime):
    """Honor reproducible builds"""
    return time.gmtime(source_date_time(mtime))[0:6]
