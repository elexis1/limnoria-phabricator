from plugin import PhabricatorPrinter

# Allows testing the querying and string construction without connecting to IRC

printer = PhabricatorPrinter(
    phabricatorURL = "code.wildfiregames.com",
    token = "your-token-here",
    storyLimit = 4,
    sleepTime = 30,
    newsPrefix = "News from 0 A.D.: ",
    ignoredUsers = ["Harbormaster", "Vulcan"],
    obscureUsernames = False,
    notifyCommit = True,
    notifyRetitle = True,
    chronokey = 6378414858781907269,
    chronokeyFile = None,
)

# some chronokeys (all n-1):
# 6377663121088159957 tests acceptance of a commit
# 6370393125263759849 tests raising of a concern of a commit
# 6375936561434323755 tests the creation of a paste
# 6370700463163291127 tests a commit without phabricator account (fallback query)
# 6376677818298665473 tests adding of reviewers
# 6377974521422163168 tests project changes

#print(printer.obscureAuthorName("foo"))
#printer.printRevisions(None, None, "rP12345")
#printer.printDifferentials(None, None, "D16")
#printer.printPastes(None, None, "P2")
printer.pollNewStories(None)
