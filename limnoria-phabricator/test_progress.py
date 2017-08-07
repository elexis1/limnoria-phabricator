import datetime
from plugin import ConduitAPI, PhabricatorStringFormatting, PhabricatorStoryPrinter

# Prints a generic HTML progress report for Wildfire Games development without connecting to IRC

useHTML = True

newlineSeparator = "<br/>\n" if useHTML else "\n"

def printParagraph(txt):
    if not useHTML:
        print(txt)
    print("<p>" + txt + "</p>")

def printSpoiler(txt):
    if not useHTML:
        print(txt)
        return

    print(
        '<div class="ipsSpoiler" data-ipsspoiler="">' +
        '<div class="ipsSpoiler_header"><span>Spoiler</span></div>' +
        '<div class="ipsSpoiler_contents">' + txt + '</div>' +
        '</div>')

def printAuthorStories(previousAuthor, authorName, currentAuthorStories, handledObjIDs):

    if previousAuthor != authorName:
        if previousAuthor is not None:
            printParagraph(previousAuthor + ":")
            printSpoiler(newlineSeparator.join(currentAuthorStories))

        previousAuthor = authorName
        handledObjIDs = []
        currentAuthorStories = []

    return previousAuthor, handledObjIDs, currentAuthorStories


def progressReport(authorNames, start, end):

    storyPrinter = PhabricatorStoryPrinter(
        conduitAPI = ConduitAPI("code.wildfiregames.com", "insert-api-token-here", acceptInvalidSSLCert=False, httpTimeout=60),
        channels=None,
        formatting = PhabricatorStringFormatting(bolding=False, obscureUsernames=False, htmlLinks=useHTML),
        storyLimit=200,
        historyForwards=False,
        timestampAfter=start.timestamp(),
        timestampBefore=end.timestamp(),
        sleepTime=5,
        newsPrefix="",
        printDate=True,
        ignoredUsers=["Harbormaster", "Vulcan", "autobuild", "php-admin"],
        filteredUsers=authorNames,
        notifyCommit=True,
        notifyRetitle=False,
        chronokey=None,
        chronokeyFile=None,
        verbose=False
    )

    # TODO: via https://code.wildfiregames.com/api/project.query
    teamMembers = [
        "Itms",
        "trompetin17",
        "enrique",
        "Yves",
        "elexis",
        "Gallaecio",
        "LordGood",
        "Pureon",
        "fcxSanya",
        "FeXoR",
        "fabio",
        "scythetwirler",
        "Imarok",
        "niektb",
        "mimo",
        "leper",
        "fatherbushido",
        "wraitii",
        "sanderd17",
        "s0600204",
        "bb"
    ]

    objTypes = ["Differential Revision", "Diffusion Commit"]

    actionOrder = [
        "committed",
        "abandoned",
        "closed",
        "created",
        "updated the diff for",
        "planned changes to",
        "accepted",
        "requested changes to",
        "raised a concern with",
        "added a comment to",
        "added inline comments to",
        "abandoned",
    ]

    actionOrder = ({key: i for i, key in enumerate(actionOrder)})

    # Pull all stories in the given interval and
    # only keep those of the given object types and actions
    allStories = []
    while True:
        stories = storyPrinter.pullSomeStories()

        if stories is True:
            break

        for story in stories:
            string, authorName, objID, objType, action = story

            if objType in objTypes and action in actionOrder:
                allStories.append((authorName, objID, action, string))

    printParagraph("Generic Progress Report for Wildfire Games in the time between " + start.strftime("%c") + " and " + end.strftime("%c"))

    # Sort stories by team member status, author, then by significance of action
    allStories = sorted(allStories, key=lambda story: (story[0] not in teamMembers, story[0].lower(), actionOrder[story[2]]))

    # Grab team member stories first, then non-team member stories
    currentAuthorStories = []
    previousAuthor = None
    handledObjIDs = []
    printedNonTeamMembers = False
    for story in allStories:

        authorName, objID, action, string = story

        previousAuthor, handledObjIDs, currentAuthorStories = \
            printAuthorStories(previousAuthor, authorName, currentAuthorStories, handledObjIDs);

        if not printedNonTeamMembers and authorName not in teamMembers:
            print("Progress by non-team members:")
            printedNonTeamMembers = True

        # Only show the most important action for each object
        if objID in handledObjIDs:
            continue

        currentAuthorStories.append(string + newlineSeparator)
        handledObjIDs.append(objID)

    printAuthorStories(authorName, "", currentAuthorStories, []);

meetDates = [
    datetime.datetime(2016, 12, 18, 1, 49),
    datetime.datetime(2017, 1, 15, 9, 23), #1
    datetime.datetime(2017, 1, 23, 2, 52), #2
    datetime.datetime(2017, 1, 30, 10, 26), #3
    datetime.datetime(2017, 2, 12, 20, 24), #4
    datetime.datetime(2017, 2, 20, 6, 56), #5
    datetime.datetime(2017, 2, 27, 15, 17), #6
    datetime.datetime(2017, 3, 6, 5, 17), #7
    datetime.datetime(2017, 3, 13, 5, 29), #8
    datetime.datetime(2017, 3, 20, 4, 30), #9
    datetime.datetime(2017, 3, 27, 5, 00), #10
    datetime.datetime(2017, 4, 3, 5, 00), #11
    datetime.datetime(2017, 4, 9, 18, 00), #12
    datetime.datetime(2017, 4, 17, 6, 00), #13
    datetime.datetime(2017, 4, 24, 6, 00), #14
    datetime.datetime(2017, 5, 1, 8, 00), #15
    datetime.datetime(2017, 5, 7, 22, 00), #16
    datetime.datetime(2017, 5, 15, 6, 00), #17
    datetime.datetime(2017, 5, 22, 6, 00), #18
]

targetMeeting = len(meetDates) - 1;

start = meetDates[targetMeeting - 1]
end = meetDates[targetMeeting]
progressReport(None, start, end)
#progressReport("some dev", datetime.datetime(2016, 10, 1, 1, 1), datetime.datetime.now())
