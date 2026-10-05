"""LiveWriter against a simulated text field."""

from shuper_whisper.live_writer import LiveWriter


class Field:
    """A text box: send() applies backspaces then appends, like SendInput would."""

    def __init__(self, text="", readable=True):
        self.text = text
        self.readable = readable
        self.backspaces = 0

    def send(self, text, backspaces=0):
        self.backspaces += backspaces
        if backspaces:
            self.text = self.text[:-backspaces]
        self.text += text

    def context(self):
        return self.text[-200:] if self.readable else None


class Monitor:
    healthy = True

    def __init__(self, ignore_vks=(), trigger_vk=0):
        self.user_input = False

    def start(self): pass
    def stop(self): pass
    def clear(self): self.user_input = False


class Env:
    def __init__(self, text="", readable=True):
        self.fields = {"a": Field(text, readable)}
        self.focus = "a"
        self.monitor = Monitor()
        self.modifiers_held = False
        self.writer = LiveWriter(
            send=lambda t, backspaces=0: self.fields[self.focus].send(t, backspaces),
            read_context=lambda: self.fields[self.focus].context(),
            field_id=lambda: (self.focus, None),
            monitor_factory=lambda ignore_vks=(), trigger_vk=0: self.monitor,
            replacements=lambda: [("mackinaw", "Mackinac")],
            wait_modifiers=lambda timeout=1.0: not self.modifiers_held,
        )

    @property
    def field(self):
        return self.fields[self.focus]


def test_tentative_then_stable_rewrites_only_the_tail():
    env = Env()
    w = env.writer
    w.begin()
    w.update("", "send the")
    assert env.field.text == "Send the"
    w.update("send the", "report")
    assert env.field.text == "Send the report"
    w.update("", "reports to")
    assert env.field.text == "Send the reports to"
    w.update("reports to Dana.", "", final=True)
    assert env.field.text == "Send the reports to Dana."
    w.finish()


def test_continues_existing_text():
    env = Env("We ate dinner")
    env.writer.begin()
    env.writer.update("Then we left.", "", final=True)
    assert env.field.text == "We ate dinner then we left."


def test_rules_apply_to_stable_text():
    env = Env()
    env.writer.begin()
    env.writer.update("I drove to mackinaw — it was great period", "", final=True)
    assert env.field.text == "I drove to Mackinac, it was great."


def test_new_line_split_across_updates():
    env = Env()
    env.writer.begin()
    env.writer.update("Thanks, new", "line")
    assert env.field.text == "Thanks,\n"   # "new" held back, then "new line" shown as a newline
    env.writer.update("line see you", "", final=True)
    assert env.field.text == "Thanks,\nSee you"


def test_word_fragment_in_tail_not_shown():
    env = Env()
    env.writer.begin()
    env.writer.update("", "wanted to f-")
    assert env.field.text == "Wanted to"
    env.writer.update("", "wanted to follow")
    assert env.field.text == "Wanted to follow"


def test_click_into_other_field_freezes_and_continues_there():
    env = Env()
    env.fields["b"] = Field("Other: ")
    w = env.writer
    w.begin()
    w.update("hello", "there")
    env.monitor.user_input = True
    env.focus = "b"
    w.update("there", "friend")
    assert env.fields["a"].text == "Hello there"        # untouched
    assert env.fields["b"].text == "Other: friend"      # old tail not repeated
    w.update("friend.", "", final=True)
    assert env.fields["b"].text == "Other: friend."


def test_user_typing_in_same_field_freezes_without_backspacing():
    env = Env()
    w = env.writer
    w.begin()
    w.update("", "hello there")
    env.field.text += "!!"                               # user typed
    env.monitor.user_input = True
    w.update("hello world", "", final=True)
    assert env.field.text.startswith("Hello there!!")
    assert env.field.backspaces == 0


def test_autocomplete_mismatch_freezes():
    env = Env()
    w = env.writer
    w.begin()
    w.update("", "teh")
    env.field.text = "The"                               # app autocorrected, no physical input
    w.update("the cat", "", final=True)
    assert env.field.backspaces == 0           # never fights the app's correction
    assert env.field.text.startswith("The")


def test_unreadable_field_still_works():
    env = Env(readable=False)
    w = env.writer
    w.begin()
    w.update("", "hello")
    w.update("hello world.", "", final=True)
    assert env.field.text == "Hello world."


def test_next_session_continues_unreadable_field():
    env = Env(readable=False)
    w = env.writer
    w.begin()
    w.update("first part.", "", final=True)
    w.finish()
    w.begin()
    w.update("then more.", "", final=True)
    assert env.field.text == "First part. Then more."


def test_period_word_split_across_updates():
    env = Env()
    env.writer.begin()
    env.writer.update("the trial period", "lasts")
    env.writer.update("lasts a month.", "", final=True)
    assert env.field.text == "The trial period lasts a month."


def test_spoken_period_at_end_of_utterance():
    env = Env()
    env.writer.begin()
    env.writer.update("send it today period", "")
    env.writer.update("", "", final=True)
    assert env.field.text == "Send it today."


class RichEdit(Field):
    """Reports newlines as \\r, like Win11 Notepad."""

    def context(self):
        return self.text.replace("\n", "\r")[-200:]


def test_richedit_newline_does_not_freeze():
    env = Env()
    env.fields["a"] = RichEdit()
    w = env.writer
    w.begin()
    w.update("hello, new line", "this is")
    w.update("", "this was")
    w.update("this was great.", "", final=True)
    assert env.field.text == "Hello,\nThis was great."


def test_new_line_words_mid_sentence_in_live_mode():
    env = Env()
    env.writer.begin()
    env.writer.update("We launched a new", "line of")
    env.writer.update("line of products.", "", final=True)
    assert env.field.text == "We launched a new line of products."


def test_held_modifier_defers_revision_without_losing_words():
    env = Env()
    w = env.writer
    w.begin()
    w.update("", "hello there")
    env.modifiers_held = True
    w.update("hello there", "friend")          # can't type now
    assert env.field.text == "Hello there" and env.field.backspaces == 0
    env.modifiers_held = False
    w.update("", "friend.")
    w.update("friend.", "", final=True)
    assert env.field.text == "Hello there friend."


def test_unverifiable_field_gets_committed_words_only():
    env = Env(readable=False)
    env.monitor.healthy = False
    w = env.writer
    w.begin()
    w.update("", "hello")
    assert env.field.text == ""
    w.update("hello world.", "", final=True)
    assert env.field.text == "Hello world." and env.field.backspaces == 0


def test_uia_timeout_is_not_a_focus_change():
    env = Env()
    ids = iter([("a", (1, 2)), ("a", None), ("a", (1, 2))])
    env.writer._field_id = lambda: next(ids, ("a", (1, 2)))
    w = env.writer
    w.begin()
    w.update("", "hello")
    w.update("", "hello there")
    assert env.field.text == "Hello there"
