import unittest

from odeon.model import Branch
from odeon.metadata import CallTracker, track


class TestCallTracker(unittest.TestCase):

    def test_simple_track_decorator(self):

        b = Branch(year=2030)

        @track()
        def x(branch: Branch, a, b):
            return y(branch=branch, c=2, d=False)

        @track()
        def y(branch: Branch, c, d):
            b.history.log("this is a log message")
            b.history.log("and this is another one")
            return "hello world"

        print(x(b, 1, b="uiae"))

        b.history.print()

    def test_track_decorator(self):

        b = Branch(year=2030)
        b.history = CallTracker()

        @track(package_names=["pandas", "odeon"])
        def x(branch: Branch, a, b):
            return y(branch=branch, c=2, d=False)

        @track(package_names=["scipy"], git_modules=[Branch])
        def y(branch: Branch, c, d):
            b.history.log("this is a log message")
            b.history.log("and this is another one")
            return "hello world"

        print(x(b, 1, b="uiae"))

        b.history.print()


if __name__ == "__main__":
    TestCallTracker().test_simple_track_decorator()
    TestCallTracker().test_track_decorator()
