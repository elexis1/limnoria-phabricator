###
# Copyright (c) 2017, elexis
# All rights reserved.
###

import supybot.conf as conf
import supybot.registry as registry
try:
    from supybot.i18n import PluginInternationalization
    _ = PluginInternationalization('Phabricator')
except:
    # Placeholder that allows to run the plugin on a bot
    # without the i18n module
    _ = lambda x: x


# Let the user answer questions to configure the registered options
def configure(advanced):

    from supybot.questions import expect, anything, something, yn
    conf.registerPlugin('Phabricator', True)

    Phabricator.phabricatorURL.setValue(
        something("Specify the URL of the Phabricator location.", default="code.wildfiregames.com"))

    Phabricator.phabricatorToken.setValue(
        something("Specify the token to access the Phabricator conduit API.", default="code.wildfiregames.com"))

    Phabricator.storyLimit.setValue(
        something("Number of stories to pull at most per HTTP request", default=5))

    Phabricator.sleepTime.setValue(
        something("Number of seconds between consecutive HTTP request for phabricator stories", default=30))

    Phabricator.newsPrefix.setValue(
        anything("Enter string to be preceeeded with Phabricator updates"), default="News from the project:")

    Phabricator.chronokeyFile.setValue(
        something("Filename to store the most recently processed chronological key", default="chronokey.txt"))

    Phabricator.ignoredUsers.setValue(
        anything("Specify the token to access the Phabricator conduit API.", default="Harbormaster Vulcan", acceptEmpty=True))

    Phabricator.notifyRetitle.setValue(
        yn("Notify if differentials are retitled?", default=True))

    Phabricator.notifyCommit.setValue(
        yn("Notify if a developer committed a patch?", default=True))

    Phabricator.obscureUsername.setValue(
        yn("Prevent the bot from pinging irc users in updates by inserting invisible whitespace in the username?", default=True))


# Register valid options

Phabricator = conf.registerPlugin('Phabricator')

conf.registerGlobalValue(Phabricator, 'phabricatorURL',
    registry.String("", _("URL of a Phabricator instance.")))

conf.registerGlobalValue(Phabricator, 'phabricatorToken',
    registry.String("", _("Token to access Phabricators conduit API.")))

conf.registerGlobalValue(Phabricator, 'storyLimit',
    registry.PositiveInteger(5, _("Limit of phabricator updates to pull information about in one request.")))

conf.registerGlobalValue(Phabricator, 'sleepTime',
    registry.PositiveInteger(30, _("Notify IRC users about phabricator updates of all users, excluding these (for example bots)")))

conf.registerGlobalValue(Phabricator, 'newsPrefix',
    registry.String("News from the project:", _("A string to be shown in front of every Phabricator update notification")))

conf.registerGlobalValue(Phabricator, 'chronokeyFile',
    registry.String("chronokey.txt", _("Filename containing the chronological key of the most recently parsed phabricator update.")))

conf.registerGlobalValue(Phabricator, 'ignoredUsers',
    registry.SpaceSeparatedListOfStrings("", _("Notify IRC users about phabricator updates of all users, excluding these (for example bots)")))

conf.registerGlobalValue(Phabricator, 'notifyCommit',
    registry.Boolean(True, _("Whether to post a notification if a patch was committed")))

conf.registerGlobalValue(Phabricator, 'notifyRetitle',
    registry.Boolean(True, _("Whether to post a notification if a differential was renamed")))

conf.registerGlobalValue(Phabricator, 'obscureUsername',
    registry.Boolean(True, _("Inserts invisible whitespace in the username, so that the bot doesn't ping irc users if they update something")))
