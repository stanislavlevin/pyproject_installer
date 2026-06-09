from enum import IntEnum


class ExitCodes(IntEnum):
    # e.g. run: command exited with zero code
    OK = 0
    # e.g. run: command exited with non-zero code
    FAILURE = 1
    # this program usage error
    WRONG_USAGE = 2
    # internal error
    INTERNAL_ERROR = 3
    # sync --verify
    SYNC_VERIFY_ERROR = 4
    # add --candidates: no candidate matched (reported; existing source,
    # if any, left untouched)
    ADD_NO_CANDIDATE_ERROR = 5
