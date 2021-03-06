###
# Copyright (c) 2014, spline
# Copyright (c) 2020, oddluck <oddluck@riseup.net>
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#   * Redistributions of source code must retain the above copyright notice,
#     this list of conditions, and the following disclaimer.
#   * Redistributions in binary form must reproduce the above copyright notice,
#     this list of conditions, and the following disclaimer in the
#     documentation and/or other materials provided with the distribution.
#   * Neither the name of the author of this software nor the name of
#     contributors to this software may be used to endorse or promote products
#     derived from this software without specific prior written consent.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
###

# my libs
import json
import requests
from requests_oauthlib import OAuth1
import os

# libraries for time_created_at
import time
from datetime import datetime

# for unescape
import re
import html.entities

# supybot libs
import supybot.utils as utils
from supybot.commands import *
import supybot.plugins as plugins
import supybot.ircutils as ircutils
import supybot.callbacks as callbacks
import supybot.conf as conf
import supybot.world as world
import supybot.log as log


class OAuthApi:
    """OAuth class to work with Twitter v1.1 API."""

    def __init__(self, consumer_key, consumer_secret, token, token_secret):
        self.auth = OAuth1(consumer_key, consumer_secret, token, token_secret)

    def ApiCall(self, call, parameters={}):
        """Calls the twitter API with 'call' and returns the twitter object (JSON)."""
        extra_params = {}
        if parameters:
            extra_params.update(parameters)
        try:
            r = requests.get(
                "https://api.twitter.com/1.1/" + call + ".json",
                params=extra_params,
                auth=self.auth,
                timeout=10,
            )
            r.raise_for_status()
        except (
            requests.exceptions.RequestException,
            requests.exceptions.HTTPError,
        ) as e:
            log.info(
                "Tweety: error connecting to Twitter API (Retrying...): {0}".format(e)
            )
            try:
                r = requests.get(
                    "https://api.twitter.com/1.1/" + call + ".json",
                    params=extra_params,
                    auth=self.auth,
                    timeout=10,
                )
                r.raise_for_status()
            except (
                requests.exceptions.RequestException,
                requests.exceptions.HTTPError,
            ) as e:
                log.info(
                    "Tweety: error connecting to Twitter API on retry: {0}".format(e)
                )
            else:
                return r.content
        else:
            return r.content


class Tweety(callbacks.Plugin):
    """Public Twitter class for working with the API."""

    threaded = True

    def __init__(self, irc):
        self.__parent = super(Tweety, self)
        self.__parent.__init__(irc)
        self.twitterApi = False
        if not self.twitterApi:
            self._checkAuthorization()
        self.data_file = conf.supybot.directories.data.dirize("tweety.json")
        if os.path.exists(self.data_file):
            with open(self.data_file) as f:
                self.since_id = json.load(f)
        else:
            log.debug("Tweety: Creating new since_id DB")
            self.since_id = {}
        world.flushers.append(self._flush_db)

    def _flush_db(self):
        with open(self.data_file, "w") as f:
            json.dump(self.since_id, f)

    def die(self):
        world.flushers.remove(self._flush_db)
        self._flush_db()
        super().die()

    def _shortenUrl(self, url):
        """Shortens a long URL into a short one."""
        try:
            data = requests.get(
                "http://tinyurl.com/api-create.php?url={0}".format(url), timeout=5
            )
        except (
            requests.exceptions.RequestException,
            requests.exceptions.HTTPError,
        ) as e:
            log.error("Tweety: ERROR retrieving tiny url: {0}".format(e))
            return
        else:
            return data.content.decode()

    def _checkAuthorization(self):
        """ Check if we have our keys and can auth."""
        if not self.twitterApi:  # if not set, try and auth.
            failTest = False  # first check that we have all 4 keys.
            for checkKey in (
                "consumerKey",
                "consumerSecret",
                "accessKey",
                "accessSecret",
            ):
                try:  # try to see if each key is set.
                    testKey = self.registryValue(checkKey)
                except:  # a key is not set, break and error.
                    log.error(
                        "Tweety: ERROR checking keys. We're missing the config value "
                        "for: {0}. Please set this and try again.".format(checkKey)
                    )
                    failTest = True
                    break
            # if any missing, throw an error and keep twitterApi=False
            if failTest:
                log.error(
                    "Tweety: ERROR getting keys. You must set all 4 keys in config "
                    "variables and reload plugin."
                )
                return False
            # We have all 4 keys. Check validity by calling verify_credentials in the API.
            self.log.info("Got all 4 keys. Now trying to auth up with Twitter.")
            twitterApi = OAuthApi(
                self.registryValue("consumerKey"),
                self.registryValue("consumerSecret"),
                self.registryValue("accessKey"),
                self.registryValue("accessSecret"),
            )
            data = twitterApi.ApiCall("account/verify_credentials")
            # check the response. if we can load json, it means we're authenticated.
            try:  # if we pass, response is validated. set self.twitterApi w/object.
                json.loads(data)
                self.log.info(
                    "I have successfully authorized and logged in to Twitter using "
                    "your credentials."
                )
                self.twitterApi = OAuthApi(
                    self.registryValue("consumerKey"),
                    self.registryValue("consumerSecret"),
                    self.registryValue("accessKey"),
                    self.registryValue("accessSecret"),
                )
            except:  # response failed. Return what we got back.
                log.error("Tweety: ERROR. I could not log in using your credentials.")
                return False
        else:  # if we're already validated, pass.
            pass

    ########################
    # COLOR AND FORMATTING #
    ########################

    def _red(self, string):
        """Returns a red string."""
        return ircutils.mircColor(string, "red")

    def _blue(self, string):
        """Returns a blue string."""
        return ircutils.mircColor(string, "blue")

    def _bold(self, string):
        """Returns a bold string."""
        return ircutils.bold(string)

    def _ul(self, string):
        """Returns an underline string."""
        return ircutils.underline(string)

    def _bu(self, string):
        """Returns a bold/underline string."""
        return ircutils.bold(ircutils.underline(string))

    ######################
    # INTERNAL FUNCTIONS #
    ######################

    def _unescape(self, text):
        """Created by Fredrik Lundh (http://effbot.org/zone/re-sub.htm#unescape-html)"""
        # quick dump \n and \r, usually coming from bots that autopost html.
        text = text.replace("\n", " ").replace("\r", " ")
        # now the actual unescape.
        def fixup(m):
            text = m.group(0)
            if text[:2] == "&#":
                # character reference
                try:
                    if text[:3] == "&#x":
                        return chr(int(text[3:-1], 16))
                    else:
                        return chr(int(text[2:-1]))
                except (ValueError, OverflowError):
                    pass
            else:
                # named entity
                try:
                    text = chr(html.entities.name2codepoint[text[1:-1]])
                except KeyError:
                    pass
            return text  # leave as is

        return re.sub(r"&#?\w+;", fixup, text)

    def _time_created_at(self, s):
        """
        Return relative time delta between now and s (dt string).
        """
        try:  # timeline's created_at Tue May 08 10:58:49 +0000 2012
            ddate = time.strptime(s, "%a %b %d %H:%M:%S +0000 %Y")[:-2]
        except ValueError:
            try:  # search's created_at Thu, 06 Oct 2011 19:41:12 +0000
                ddate = time.strptime(s, "%a, %d %b %Y %H:%M:%S +0000")[:-2]
            except ValueError:
                return s
        # do the math
        d = datetime.utcnow() - datetime(*ddate, tzinfo=None)
        # now parse and return.
        if d.days:
            rel_time = "{:1d}d ago".format(abs(d.days))
        elif d.seconds > 3600:
            rel_time = "{:.1f}h ago".format(round((abs(d.seconds) / 3600), 1))
        elif 60 <= d.seconds < 3600:
            rel_time = "{:.1f}m ago".format(round((abs(d.seconds) / 60), 1))
        else:
            rel_time = "%ss ago" % (abs(d.seconds))
        return rel_time

    def _outputTweet(
        self, irc, msg, nick, name, verified, text, time, tweetid, retweetid
    ):
        """
        Constructs string to output for Tweet. Used for tsearch and twitter.
        """
        url = url2 = None
        # build output string.
        if self.registryValue("outputColorTweets", msg.args[0]):
            ret = "@{0}".format(self._ul(self._blue(nick)))
        else:  # bold otherwise.
            ret = "@{0}".format(self._bu(nick))
        if verified:
            string = self._bold(ircutils.mircColor("✓", "white", "blue"))
            ret += "{}".format(string)
        # show real name in tweet output?
        if not self.registryValue("hideRealName", msg.args[0]):
            ret += " ({0})".format(name)
        # short url the link to the tweet?
        if self.registryValue("addShortUrl", msg.args[0]):
            url = self._shortenUrl(
                "https://twitter.com/{0}/status/{1}".format(nick, tweetid)
            )
            if url:
                text += " {0}".format(url)
            if retweetid and retweetid != tweetid:
                url2 = self._shortenUrl(
                    "https://twitter.com/{0}/status/{1}".format(nick, retweetid)
                )
            if url2:
                text += " {0}".format(url2)
        # add in the end with the text + tape.
        if self.registryValue("colorTweetURLs", msg.args[0]):  # color urls.
            text = re.sub(
                r"(http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F]"
                r"[0-9a-fA-F]))+)",
                self._red(r"\1"),
                text,
            )
            ret += ": {0} ({1})".format(text, self._bold(time))
        else:  # only bold time. no text color.
            ret += ": {0} ({1})".format(text, self._bold(time))
        # now return.
        return ret

    def _woeid_lookup(self, lookup):
        """<location>
        Use Yahoo's API to look-up a WOEID.
        """
        data = self.twitterApi.ApiCall("trends/available")
        if not data:
            log.error("Tweety: ERROR retrieving data from Trends API")
            return
        try:
            data = json.loads(data)
        except:
            data = None
            log.error("Tweety: ERROR retrieving data from Trends API")
        if not data:
            log.info("Tweety: No location results for {0}".format(lookup))
            return
        return next(
            (item["woeid"] for item in data if lookup.lower() in item["name"].lower()),
            None,
        )

    ####################
    # PUBLIC FUNCTIONS #
    ####################

    def woeidlookup(self, irc, msg, args, lookup):
        """<location>
        Search Yahoo's WOEID DB for a location. Useful for the trends variable.
        Ex: London or Boston
        """
        woeid = self._woeid_lookup(lookup)
        if woeid:
            irc.reply("WOEID: {0} for '{1}'".format(self._bold(woeid), lookup))
        else:
            irc.reply(
                "ERROR: Something broke trying to find a WOEID for '{0}'".format(lookup)
            )

    woeidlookup = wrap(woeidlookup, ["text"])

    def ratelimits(self, irc, msg, args):
        """
        Display current rate limits for your twitter API account.
        """
        # before we do anything, make sure we have a twitterApi object.
        if not self.twitterApi:
            irc.reply(
                "ERROR: Twitter is not authorized. Please check logs before running "
                "this command."
            )
            return
        # make API call.
        data = self.twitterApi.ApiCall(
            "application/rate_limit_status",
            parameters={"resources": "trends,search,statuses,users"},
        )
        try:
            data = json.loads(data)
        except:
            irc.reply("ERROR: Failed to lookup ratelimit data: {0}".format(data))
            return
        # parse data;
        data = data.get("resources")
        if not data:  # simple check if we have part of the json dict.
            irc.reply(
                "ERROR: Failed to fetch application rate limit status. Something could "
                "be wrong with Twitter."
            )
            log.error("Tweety: ERROR fetching rate limit data: {0}".format(data))
            return
        # dict of resources and how to parse. key=name, values are for the json dict.
        resources = {
            "trends": ["trends", "/trends/place"],
            "tsearch": ["search", "/search/tweets"],
            "twitter --id": ["statuses", "/statuses/show/:id"],
            "twitter --info": ["users", "/users/show/:id"],
            "twitter timeline": ["statuses", "/statuses/user_timeline"],
        }
        # now iterate through dict above.
        for resource in resources:
            rdict = resources[resource]  # get value.
            endpoint = data.get(rdict[0]).get(rdict[1])  # value[0], value[1]
            minutes = "%sm%ss" % divmod(
                int(endpoint["reset"]) - int(time.time()), 60
            )  # math.
            output = "Reset in: {0}  Remaining: {1}".format(
                minutes, endpoint["remaining"]
            )
            irc.reply("{0} :: {1}".format(self._bold(resource), output))

    ratelimits = wrap(ratelimits)

    def trends(self, irc, msg, args, getopts, optwoeid):
        """[--exclude] [location]
        Returns the top Twitter trends for a specific location. Use optional argument
        location for trends. Defaults to worldwide and can be set via config variable.
        Use --exclude to not include #hashtags in trends data.
        Ex: Boston or --exclude London
        """
        # enforce +voice or above to use command?
        if self.registryValue("requireVoiceOrAbove", msg.args[0]):  # should we check?
            if ircutils.isChannel(msg.args[0]):  # are we in a channel?
                if not irc.state.channels[msg.args[0]].isVoicePlus(
                    msg.nick
                ):  # are they + or @?
                    irc.error(
                        "ERROR: You have to be at least voiced to use the trends "
                        "command in {0}.".format(msg.args[0])
                    )
                    return
        # before we do anything, make sure we have a twitterApi object.
        if not self.twitterApi:
            irc.reply(
                "ERROR: Twitter is not authorized. Please check logs before running "
                "this command."
            )
            return
        # default arguments.
        args = {
            "id": self.registryValue("woeid", msg.args[0]),
            "exclude": self.registryValue("hideHashtagsTrends", msg.args[0]),
        }
        # handle input.
        if getopts:
            for (key, value) in getopts:
                if key == "exclude":  # remove hashtags from trends.
                    args["exclude"] = "hashtags"
        # work with woeid. 1 is world, the default. can be set via input or via config.
        if optwoeid:  # if we have an input location, lookup the woeid.
            if optwoeid.lower().startswith(
                "world"
            ):  # looking for worldwide or some variation. (bypass)
                args["id"] = 1  # "World Wide" is worldwide (odd bug) = 1.
            elif optwoeid.strip().isdigit():
                args["id"] = optwoeid.strip()
            else:  # looking for something else.
                woeid = self._woeid_lookup(optwoeid)  # yahoo search for woeid.
                if (
                    woeid
                ):  # if we get a returned value, set it. otherwise default value.
                    args["id"] = woeid
                else:  # location not found.
                    irc.reply(
                        "ERROR: I could not lookup location: {0}. Try a different "
                        "location.".format(optwoeid)
                    )
                    return
        # now build our API call
        data = self.twitterApi.ApiCall("trends/place", parameters=args)
        try:
            data = json.loads(data)
        except:
            irc.reply("ERROR: failed to lookup trends on Twitter: {0}".format(data))
            return
        # now, before processing, check for errors:
        if "errors" in data:
            if data["errors"][0]["code"] == 34:  # 34 means location not found.
                irc.reply("ERROR: I do not have any trends for: {0}".format(optwoeid))
                return
            else:  # just return the message.
                errmsg = data["errors"][0]
                irc.reply(
                    "ERROR: Could not load trends. ({0} {1})".format(
                        errmsg["code"], errmsg["message"]
                    )
                )
                return
        # if no error here, we found trends. prepare string and output.
        location = data[0]["locations"][0]["name"]
        ttrends = " | ".join([trend["name"] for trend in data[0]["trends"]])
        irc.reply(
            "Top Twitter Trends in {0} :: {1}".format(self._bold(location), ttrends)
        )

    trends = wrap(trends, [getopts({"exclude": ""}), optional("text")])

    def tsearch(self, irc, msg, args, optlist, optterm):
        """[--num number] [--searchtype mixed|recent|popular] [--lang xx] [--nort] [--new] <term>
        Searches Twitter for the <term> and returns the most recent results.
        --num is number of results.
        --searchtype being recent, popular or mixed. Popular is the default.
        --new returns new messages since last search for <term> in channel.
        Ex: --num 3 breaking news
        """
        # enforce +voice or above to use command?
        if self.registryValue("requireVoiceOrAbove", msg.args[0]):  # should we check?
            if ircutils.isChannel(msg.args[0]):  # are we in a channel?
                if not irc.state.channels[msg.args[0]].isVoicePlus(
                    msg.nick
                ):  # are they + or @?
                    irc.error(
                        "ERROR: You have to be at least voiced to use the tsearch "
                        "command in {0}.".format(msg.args[0])
                    )
                    return
        # before we do anything, make sure we have a twitterApi object.
        if not self.twitterApi:
            irc.reply(
                "ERROR: Twitter is not authorized. Please check logs before running "
                "this command."
            )
            return
        self.since_id.setdefault(msg.channel, {})
        self.since_id[msg.channel].setdefault("{0}".format(optterm), None)
        new = False
        # default arguments.
        tsearchArgs = {
            "include_entities": "false",
            "tweet_mode": "extended",
            "count": self.registryValue("defaultSearchResults", msg.args[0]),
            "lang": "en",
            "q": utils.web.urlquote(optterm),
        }
        # check input.
        if optlist:
            for (key, value) in optlist:
                if key == "num":  # --num
                    maxresults = self.registryValue("maxSearchResults", msg.args[0])
                    if not (
                        1 <= value <= maxresults
                    ):  # make sure it's between what we should output.
                        irc.reply(
                            "ERROR: '{0}' is not a valid number of tweets. Range is "
                            "between 1 and {1}.".format(value, maxresults)
                        )
                        return
                    else:  # change number to output.
                        tsearchArgs["count"] = value
                if key == "searchtype":  # getopts limits us here.
                    tsearchArgs[
                        "result_type"
                    ] = value  # limited by getopts to valid values.
                if key == "lang":  # lang . Uses ISO-639 codes like 'en'
                    tsearchArgs["lang"] = value
                if key == "new" and self.since_id[msg.channel]["{0}".format(optterm)]:
                    new = True
                    tsearchArgs["since_id"] = self.since_id[msg.channel][
                        "{0}".format(optterm)
                    ]
                if key == "nort":
                    tsearchArgs["q"] += " -filter:retweets"
        # now build our API call.
        data = self.twitterApi.ApiCall("search/tweets", parameters=tsearchArgs)
        if not data:
            if not new:
                irc.reply(
                    "ERROR: Something went wrong trying to search Twitter. ({0})"
                    .format(data)
                )
            log.error("Tweety: ERROR trying to search Twitter: {0}".format(data))
            return
        try:
            data = json.loads(data)
        except:
            if not new:
                irc.reply(
                    "ERROR: Something went wrong trying to search Twitter. ({0})"
                    .format(data)
                )
            log.error("Tweety: ERROR trying to search Twitter: {0}".format(data))
            return
        # check the return data.
        results = data.get("statuses")  # data returned as a dict.
        if not results or len(results) == 0:  # found nothing or length 0.
            if not new:
                irc.reply(
                    "ERROR: No Twitter Search results found for '{0}'".format(optterm)
                )
            log.info(
                "Tweety: No Twitter Search results found for '{0}': {1}".format(
                    optterm, data
                )
            )
            return
        else:  # we found something.
            self.since_id[msg.channel]["{0}".format(optterm)] = results[0].get("id")
            for result in results[0 : int(tsearchArgs["count"])]:  # iterate over each.
                nick = self._unescape(result["user"].get("screen_name"))
                name = self._unescape(result["user"].get("name"))
                verified = result["user"].get("verified")
                text = self._unescape(result.get("full_text")) or self._unescape(
                    result.get("text")
                )
                date = self._time_created_at(result.get("created_at"))
                tweetid = result.get("id_str")
                # build output string and output.
                output = self._outputTweet(
                    irc, msg, nick, name, verified, text, date, tweetid, None
                )
                irc.reply(output)

    tsearch = wrap(
        tsearch,
        [
            getopts(
                {
                    "num": "int",
                    "searchtype": ("literal", ("popular", "mixed", "recent")),
                    "lang": "somethingWithoutSpaces",
                    "new": "",
                    "nort": "",
                }
            ),
            "text",
        ],
    )

    def twitter(self, irc, msg, args, optlist, optnick):
        """[--noreply] [--nort] [--num <##>] [--info] [--new] [--id <id#>] <nick>
        Returns last tweet or --num tweets. Shows all tweets, including RT and reply.
        To not display replies or RT's, use --noreply or --nort.
        Return new tweets since you last checked in channel with --new.
        Return specific tweet with --id <id#>.
        Return information on user with --info.
        Ex: --info CNN | --id 337197009729622016 | --num 3 CNN
        """
        self.since_id.setdefault(msg.channel, {})
        self.since_id[msg.channel].setdefault("{0}".format(optnick), None)
        # enforce +voice or above to use command?
        if self.registryValue("requireVoiceOrAbove", msg.args[0]):  # should we check?
            if ircutils.isChannel(msg.args[0]):  # are we in a channel?
                if not irc.state.channels[msg.args[0]].isVoicePlus(
                    msg.nick
                ):  # are they + or @?
                    irc.error(
                        "ERROR: You have to be at least voiced to use the twitter "
                        "command in {0}.".format(msg.args[0])
                    )
                    return
        # before we do anything, make sure we have a twitterApi object.
        if not self.twitterApi:
            irc.reply(
                "ERROR: Twitter is not authorized. Please check logs before running "
                "this command."
            )
            return
        # now begin
        optnick = optnick.replace("@", "")  # strip @ from input if given.
        # default options.
        args = {
            "id": False,
            "nort": False,
            "noreply": False,
            "url": False,
            "new": False,
            "num": self.registryValue("defaultResults", msg.args[0]),
            "info": False,
        }
        # handle input optlist.
        if optlist:
            for (key, value) in optlist:
                if key == "id":
                    args["id"] = True
                if key == "url":
                    args["url"] = True
                if key == "nort":
                    args["nort"] = True
                if key == "noreply":
                    args["noreply"] = True
                if key == "new":
                    args["new"] = True
                if key == "num":
                    maxresults = self.registryValue("maxResults", msg.args[0])
                    if not (
                        1 <= value <= maxresults
                    ):  # make sure it's between what we should output.
                        irc.reply(
                            "ERROR: '{0}' is not a valid number of tweets. Range is "
                            "between 1 and {1}.".format(value, maxresults)
                        )
                        return
                    else:  # number is valid so return this.
                        args["num"] = value
                if key == "info":
                    args["info"] = True
        # handle the four different rest api endpoint urls + twitterArgs dict for options.
        if args["id"]:  # -id #.
            apiUrl = "statuses/show"
            twitterArgs = {
                "id": optnick,
                "include_entities": "false",
                "tweet_mode": "extended",
            }
        elif args["info"]:  # --info.
            apiUrl = "users/show"
            twitterArgs = {"screen_name": optnick, "include_entities": "false"}
        elif args["new"]:  # --new.
            apiUrl = "statuses/user_timeline"
            if self.since_id[msg.channel]["{0}".format(optnick)]:
                twitterArgs = {
                    "screen_name": optnick,
                    "since_id": self.since_id[msg.channel]["{0}".format(optnick)],
                    "count": args["num"],
                    "tweet_mode": "extended",
                }
                if args["nort"]:  # show retweets?
                    twitterArgs["include_rts"] = "false"
                else:  # default is to show retweets.
                    twitterArgs["include_rts"] = "true"
                if args["noreply"]:  # show replies?
                    twitterArgs["exclude_replies"] = "true"
                else:  # default is to NOT exclude replies.
                    twitterArgs["exclude_replies"] = "false"
            else:
                twitterArgs = {
                    "screen_name": optnick,
                    "count": args["num"],
                    "tweet_mode": "extended",
                }
                if args["nort"]:  # show retweets?
                    twitterArgs["include_rts"] = "false"
                else:  # default is to show retweets.
                    twitterArgs["include_rts"] = "true"
                if args["noreply"]:  # show replies?
                    twitterArgs["exclude_replies"] = "true"
                else:  # default is to NOT exclude replies.
                    twitterArgs["exclude_replies"] = "false"
        else:  # if not an --id --info, or --new we're printing from their timeline.
            apiUrl = "statuses/user_timeline"
            twitterArgs = {
                "screen_name": optnick,
                "count": args["num"],
                "tweet_mode": "extended",
            }
            if args["nort"]:  # show retweets?
                twitterArgs["include_rts"] = "false"
            else:  # default is to show retweets.
                twitterArgs["include_rts"] = "true"
            if args["noreply"]:  # show replies?
                twitterArgs["exclude_replies"] = "true"
            else:  # default is to NOT exclude replies.
                twitterArgs["exclude_replies"] = "false"
        # call the Twitter API with our data.
        data = self.twitterApi.ApiCall(apiUrl, parameters=twitterArgs)
        if not data:
            if not args["new"]:
                irc.reply(
                    "ERROR: Failed to lookup Twitter for '{0}' ({1})".format(
                        optnick, data
                    )
                )
            log.error: "Tweety: ERROR looking up Twitter for '{0}': {1}".format(
                optnick, data
            )
            return
        try:
            data = json.loads(data)
        except:
            if not args["new"]:
                irc.reply(
                    "ERROR: Failed to lookup Twitter for '{0}' ({1})".format(
                        optnick, data
                    )
                )
            log.error: "Tweety: ERROR looking up Twitter for '{0}': {1}".format(
                optnick, data
            )
            return
        # before anything, check for errors. errmsg is conditional.
        if "errors" in data:
            if data["errors"][0]["code"] == 34:  # not found.
                if args["id"]:  # --id #. # is not found.
                    errmsg = "ERROR: Tweet ID '{0}' not found.".format(optnick)
                else:  # --info <user> or twitter <user> not found.
                    errmsg = "ERROR: Twitter user '{0}' not found.".format(optnick)
                irc.reply(errmsg)  # print the error and exit.
                return
            else:  # errmsg is not 34. just return it.
                errmsg = data["errors"][0]
                if not args["new"]:
                    irc.reply(
                        "ERROR: {0} {1}".format(errmsg["code"], errmsg["message"])
                    )
                log.error(
                    "Tweety: ERROR: {0}: {1}".format(errmsg["code"], errmsg["message"])
                )
                return
        # no errors, so we process data conditionally.
        if args["id"]:  # If --id was given for a single tweet.
            text = self._unescape(data.get("full_text")) or self._unescape(
                data.get("text")
            )
            nick = self._unescape(data["user"].get("screen_name"))
            name = self._unescape(data["user"].get("name"))
            verified = data["user"].get("verified")
            relativeTime = self._time_created_at(data.get("created_at"))
            tweetid = data.get("id")
            if data.get("retweeted_status"):
                retweetid = data["retweeted_status"].get("id")
            else:
                retweetid = None
            # prepare string to output and send to irc.
            output = self._outputTweet(
                irc, msg, nick, name, verified, text, relativeTime, tweetid, retweetid
            )
            irc.reply(output)
            return
        elif args["info"]:  # --info to return info on a Twitter user.
            location = data.get("location")
            followers = data.get("followers_count")
            friends = data.get("friends_count")
            description = self._unescape(data.get("description"))
            screen_name = self._unescape(data.get("screen_name"))
            created_at = data.get("created_at")
            statuses_count = data.get("statuses_count")
            protected = data.get("protected")
            name = self._unescape(data.get("name"))
            url = data.get("url")
            # build output string conditionally. build string conditionally.
            ret = self._bu("@{0}".format(screen_name))
            ret += " ({0})".format(name)
            if protected:  # is the account protected/locked?
                ret += " [{0}]:".format(self._bu("LOCKED"))
            else:  # open.
                ret += ":"
            if url:  # do they have a url?
                ret += " {0}".format(self._ul(url))
            if description:  # a description?
                ret += " {0}".format(self._unescape(description))
            ret += " [{0} friends,".format(self._bold(friends))
            ret += " {0} tweets,".format(self._bold(statuses_count))
            ret += " {0} followers,".format(self._bold(followers))
            ret += " signup: {0}".format(self._bold(self._time_created_at(created_at)))
            if location:  # do we have location?
                ret += " Location: {0}]".format(self._bold(location))
            else:  # nope.
                ret += "]"
            # finally, output.
            irc.reply(ret)
            return
        else:  # this will display tweets/a user's timeline. can be n+1 tweets.
            if len(data) == 0:  # no tweets found.
                if not args["new"]:
                    irc.reply("ERROR: '{0}' has not tweeted yet.".format(optnick))
                log.info("Tweety: '{0}' has not tweeted yet.".format(optnick))
                return
            self.since_id[msg.channel]["{0}".format(optnick)] = data[0].get("id")
            for tweet in data:  # n+1 tweets found. iterate through each tweet.
                text = self._unescape(tweet.get("full_text")) or self._unescape(
                    tweet.get("text")
                )
                nick = self._unescape(tweet["user"].get("screen_name"))
                name = self._unescape(tweet["user"].get("name"))
                verified = tweet["user"].get("verified")
                tweetid = tweet.get("id")
                if tweet.get("retweeted_status"):
                    retweetid = tweet["retweeted_status"].get("id")
                else:
                    retweetid = None
                relativeTime = self._time_created_at(tweet.get("created_at"))
                # prepare string to output and send to irc.
                output = self._outputTweet(
                    irc,
                    msg,
                    nick,
                    name,
                    verified,
                    text,
                    relativeTime,
                    tweetid,
                    retweetid,
                )
                irc.reply(output)

    twitter = wrap(
        twitter,
        [
            getopts(
                {
                    "noreply": "",
                    "nort": "",
                    "info": "",
                    "id": "",
                    "url": "",
                    "new": "",
                    "num": "int",
                }
            ),
            "somethingWithoutSpaces",
        ],
    )


Class = Tweety


# vim:set shiftwidth=4 softtabstop=4 expandtab textwidth=279:
