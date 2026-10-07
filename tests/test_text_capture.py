from types import SimpleNamespace

from text_capture import _capture_from_automation


class FakeRange:
    def __init__(self, text):
        self.text = text

    def GetText(self, _maximum):
        return self.text


class FakeSelection:
    def __init__(self, *parts):
        self.parts = [FakeRange(part) for part in parts]
        self.Length = len(self.parts)

    def GetElement(self, index):
        return self.parts[index]


class FakePattern:
    def __init__(self, selection=(), document=""):
        self.selection = FakeSelection(*selection)
        self.DocumentRange = FakeRange(document)

    def GetSelection(self):
        return self.selection


class FakeUnknown:
    def __init__(self, pattern):
        self.pattern = pattern

    def QueryInterface(self, _interface):
        return self.pattern


class FakeElement:
    def __init__(self, pattern=None, parent=None):
        self.pattern = pattern
        self.parent = parent

    def GetCurrentPattern(self, _pattern_id):
        if self.pattern is None:
            raise RuntimeError("TextPattern unavailable")
        return FakeUnknown(self.pattern)


class FakeWalker:
    @staticmethod
    def GetParentElement(element):
        return element.parent


class FakeAutomation:
    ControlViewWalker = FakeWalker()

    def __init__(self, focused):
        self.focused = focused

    def GetFocusedElement(self):
        return self.focused


UIA = SimpleNamespace(UIA_TextPatternId=10014, IUIAutomationTextPattern=object())


def test_selection_is_found_on_parent_document_control():
    parent = FakeElement(FakePattern(selection=("Highlighted browser text",), document="Whole page"))
    focused_leaf = FakeElement(parent=parent)

    result = _capture_from_automation(FakeAutomation(focused_leaf), UIA, True, 1000)

    assert result == ("Highlighted browser text", "selection")


def test_outer_document_is_used_when_nothing_is_selected():
    parent = FakeElement(FakePattern(document="Complete active document"))
    focused = FakeElement(FakePattern(document="Focused field"), parent=parent)

    result = _capture_from_automation(FakeAutomation(focused), UIA, True, 1000)

    assert result == ("Complete active document", "document")
