from plugin import ConduitAPI, PhabricatorStringFormatting, PhabricatorReplyPrinter, PhabricatorStoryPrinter

conduitAPI = ConduitAPI("code.wildfiregames.com", "insert-api-token-here", acceptInvalidSSLCert=False)
formatting = PhabricatorStringFormatting(bolding=False, obscureUsernames=False, htmlLinks=False)

# Allows testing the querying and string construction without connecting to IRC
storyPrinter = PhabricatorStoryPrinter(
    conduitAPI=conduitAPI,
    channels=None,
    formatting=formatting,
    storyLimit=5,
    historyForwards=True,
    timestampAfter=0,
    timestampBefore=0,
    sleepTime=3,
    newsPrefix="",#"News from 0 A.D.: ",
    printDate=True,
    ignoredUsers=["Harbormaster", "Vulcan", "autobuild", "php-admin"],
    filteredUsers=[],
    notifyCommit=True,
    notifyRetitle=True,
    chronokey=None,#6377651517671901321,#6378414858781907269,
    chronokeyFile=None,
    verbose=True
)
storyPrinter.printStoriesForever(irc=None)

replyPrinter = PhabricatorReplyPrinter(
    txt=":P",
    conduitAPI=conduitAPI,
    formatting=formatting
)

print(replyPrinter.getReplies())

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
