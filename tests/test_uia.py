from shuper_whisper import uia

PAGE = "Search￼\nReply to Claude\n"   # text of the page around the field
FIELD = "hello there"


class FakeMod:
    TextPatternRangeEndpoint_Start = 0
    TextPatternRangeEndpoint_End = 1
    TextUnit_Character = 0
    IUIAutomationTextPattern = object()


class Range:
    """A text range over PAGE + FIELD that, like Chromium's, can be moved
    out of the field into the rest of the page."""

    def __init__(self, start, end):
        self.ends = [start, end]

    def Clone(self):
        return Range(*self.ends)

    def MoveEndpointByRange(self, endpoint, other, other_endpoint):
        self.ends[endpoint] = other.ends[other_endpoint]

    def MoveEndpointByUnit(self, endpoint, _unit, count):
        self.ends[endpoint] = max(0, self.ends[endpoint] + count)

    def CompareEndpoints(self, endpoint, other, other_endpoint):
        a, b = self.ends[endpoint], other.ends[other_endpoint]
        return (a > b) - (a < b)

    def GetText(self, _max):
        return (PAGE + FIELD)[self.ends[0]:self.ends[1]]


class Selection:
    Length = 1

    def __init__(self, caret):
        self.caret = caret

    def GetElement(self, _i):
        return Range(self.caret, self.caret)


class Pattern:
    def __init__(self, caret):
        self.DocumentRange = Range(len(PAGE), len(PAGE + FIELD))
        self.caret = caret

    def QueryInterface(self, _iface):
        return self

    def GetSelection(self):
        return Selection(self.caret)


class Element:
    def __init__(self, caret):
        self.pattern = Pattern(caret)

    def GetCurrentPattern(self, _id):
        return self.pattern


def test_context_stops_at_the_start_of_the_field(monkeypatch):
    monkeypatch.setattr(uia, "_client", lambda: (None, FakeMod))
    assert uia._text_before_caret_of(Element(len(PAGE))) == ""          # empty so far
    assert uia._text_before_caret_of(Element(len(PAGE) + 5)) == "hello"


def test_invisible_characters_and_no_break_spaces_are_tidied(monkeypatch):
    monkeypatch.setattr(uia, "_run", lambda fn, timeout: "￼\nhello​\xa0")
    assert uia.text_before_caret() == "\nhello "
