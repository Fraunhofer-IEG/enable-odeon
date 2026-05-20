from typing import List


def lists_equal(l1: List, l2: List) -> bool:
    """
    Test whether two lists are equal in terms of elements ignoring order
    """
    return len(l1) == len(l2) and all(x in l2 for x in l1) and all(x in l1 for x in l2)
