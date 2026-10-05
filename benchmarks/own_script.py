"""What you read aloud for record.py: about 750 words, roughly four minutes at
a quick pace. Everyday dictation (messages, notes, reviews), with "[pause]"
where to stop for a second or so mid-sentence, as if thinking, to test that
those don't become sentence breaks.

The text is also the answer key, so read it as written, but naturally.
"""

OWN_SCRIPT = [
    ("own-01-email",
     "Hi Sarah, thanks for getting back to me so quickly. I looked over the proposal last night and I "
     "think it's in good shape, but I'd like to move the launch to the second week of November so we "
     "have time to test everything properly."),
    ("own-02-deploy",
     "Heads up, I'm deploying the new build to staging in about ten minutes. If anything looks off "
     "after that, ping me here and I'll roll it back right away."),
    ("own-03-thinking",
     "I think the problem is [pause] that the settings window loads before the model does, [pause] so "
     "the first time you open it the list of microphones is empty."),
    ("own-04-notes",
     "Notes from today's meeting. We agreed to ship the installer first. Jared will handle the GPU "
     "setup screen, and the rest of us will focus on bug fixes until Friday."),
    ("own-05-questions",
     "Can you check whether the backup ran last night? Also, do we still need the old database, or can "
     "we delete it this week?"),
    ("own-06-tech",
     "The app is written in Python and uses faster-whisper for transcription. The settings page is "
     "built with React and Tailwind, and it talks to the back end through pywebview."),
    ("own-07-ramble",
     "So yesterday I spent most of the afternoon trying to figure out why the microphone kept cutting "
     "out, and it turned out that Windows had switched the default device after an update, so every "
     "app was listening to the webcam instead of the actual mic, which explains why everything sounded "
     "so muffled on the call this morning."),
    ("own-08-pause",
     "So I was going to say [pause] that we could probably skip the review this time, [pause] since "
     "nothing in the core logic changed."),
    ("own-09-room",
     "The meeting is at half past three on Tuesday, and we're expecting about forty people, so let's "
     "book the bigger room downstairs."),
    ("own-10-text",
     "Hey, running about ten minutes late. Traffic is terrible on the highway. Order me whatever "
     "you're having and I'll be there soon."),
    ("own-11-review",
     "This looks good overall. One small thing, the retry loop doesn't have a limit, so if the server "
     "is down it will keep trying forever. Can we cap it at three attempts?"),
    ("own-12-breaks",
     "The tests are passing now. [pause] I still want to clean up the error messages before we merge. "
     "[pause] Let's look at it together tomorrow morning."),
    ("own-13-names",
     "Tell Marcus and Priya that the demo moved to Thursday afternoon, and send the slides to Elena "
     "before lunch."),
    ("own-14-casual",
     "Honestly, I'm not sure that's the right call. Let me think about it over the weekend and I'll get "
     "back to you on Monday."),
    ("own-15-steps",
     "First, unplug the router and wait thirty seconds. Then plug it back in, wait for the lights to "
     "stop blinking, and try connecting again."),
    ("own-16-weird",
     "The weird thing is [pause] it only happens on my desktop, [pause] never on the laptop."),
    ("own-17-dictation",
     "I'm testing ShuperWhisper with my own voice through Voicemeeter. If this works well, I'll finally "
     "stop typing long messages by hand."),
    ("own-18-plan",
     "Okay, so here's the plan. We grab coffee, we sit down for an hour, we go through every open "
     "ticket, and anything that isn't a real bug gets closed."),
    ("own-19-client",
     "Do you know if [pause] the client ever replied about the contract? I sent it over on Monday and "
     "haven't heard anything since."),
    ("own-20-ramble",
     "What I really want is for the whole thing to feel invisible, like you just start talking and the "
     "words show up where you're typing, and if it gets something wrong you fix it and move on without "
     "having to think about which mode you're in or what button to press."),
    ("own-21-update",
     "Quick update on the migration. The data is copied over, the old tables are still there as a "
     "backup, and I'll remove them once we've run in production for a full week without problems."),
    ("own-22-feedback",
     "I really like the new design. The only thing I'd change is the font size on the second page, "
     "because it's hard to read on a laptop screen."),
    ("own-23-pause",
     "We could try [pause] moving the whole thing to the new server [pause] and see if the timeouts go "
     "away."),
    ("own-24-errands",
     "Reminder for tomorrow: pick up the dry cleaning, call the dentist about rescheduling, and buy a "
     "birthday card for Mom before the store closes."),
    ("own-25-schedule",
     "What time works best for you next week? I'm free Tuesday after two and most of Wednesday, but "
     "Thursday is packed."),
    ("own-26-story",
     "The funny part is that after all that debugging, the fix was a single line. Somebody had changed "
     "the sample rate in the config file months ago, and nobody noticed because the old microphone "
     "happened to support both."),
    ("own-27-signoff",
     "Thanks again for all your help this week. Have a great weekend, and I'll see you on Monday."),
]


def expected(text: str) -> str:
    """The answer key: the script without its [pause] marks."""
    return " ".join(text.replace("[pause]", " ").split())
