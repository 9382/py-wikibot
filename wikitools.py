#coding: utf-8
# [!] Do NOT edit this file unless you know what you are doing, as these are core functions.

__all__ = [
        "log", "lerror", "lalert", "lwarn", "lsucc",
        "Article", "BatchProcessArticles", "Template", "Revision", "IterateCategory", "WikiConfig",
        "APIException", "GetSelf", "AttemptLogin", "CheckIfStopped", "HaltIfStopped", "SetStopped",
        "requestapi", "CreateAPIFormRequest"
]

## Notes:
# All uses of datetime.datetime.fromisoformat will strip the last character since py3.8's datetime can't handle the ending Z
# could be fixed by just upgrading python version but I am very lazy

from dotenv import dotenv_values
import urllib.parse
import re as regex
import threading
import traceback
import colorama
import datetime
import requests
import random
import json
import time
import sys
import os
colorama.init()

#For an explanation of the config options below, please see the .env-example file
envvalues = dotenv_values()
SUBMITEDITS = envvalues["SUBMITEDITS"].lower() == "true"
INDEV = envvalues["INDEV"].lower() == "true"
maxActionsPerMinute = int(envvalues["EDITSPERMIN"])
maxEdits = int(envvalues["MAXEDITS"])

activelyStopped = False
APS = 60/maxActionsPerMinute
lastActionTime = 0
actionCount = 0

def currentDate(): #The current date in YYYY-MM-DD hh:mm:ss
    return str(datetime.datetime.fromtimestamp(time.time()//1))
_logSession = f"{currentDate()[:10]}.{int(time.time()//1)}"
if not os.path.exists("Logs/"):
    os.makedirs("Logs")
_logFile = open(f"Logs/{_logSession}.log", "w", encoding="utf-8", newline="")
_logLocked = False
_logCount = [0, 0, 0, 0, 0] #log, error, alert, warn, success
_logCountOrder = ["Log", "Error", "Alert", "Warning", "Success"]
_print = print
def print(*args, **kwargs):
    sys.stdout.write('\x1b[2K\r') #clear the last line via magic
    _print(*args, **kwargs)
    _print(f"\033[47m\033[30mLOG DATA | Normal: {_logCount[0]} | Errors: {_logCount[1]} | Alerts: {_logCount[2]} | Warnings: {_logCount[3]} | Successes: {_logCount[4]}", end="\033[0m")
def log(content, *, colour="", LogType="Log"):
    #Manages the writing to a log file for debugging
    global _logLocked #Prevent thread collisions (guarantee clean printing)
    while _logLocked:
        time.sleep(0)
    _logLocked = True
    _logCount[_logCountOrder.index(LogType)] += 1
    prefixText = f"{LogType} {currentDate()} - {threading.current_thread().name}"
    print(f"{colour}[{prefixText}] {content}\033[0m")
    try:
        _logFile.write(f"[{prefixText}] {content}\n")
    except Exception as exc:
        _logCount[1] += 1 #+1 to Error
        print(f"\033[41m\033[30m[{prefixText}] Failed to write to log file: {exc}\033[0m")
    else:
        _logFile.flush()
    _logLocked = False
def lerror(content): #Black text, red background
    log(content, colour="\033[41m\033[30m", LogType="Error")
def lalert(content): #Red text
    log(content, colour="\033[31m", LogType="Alert")
def lwarn(content): #Yellow text
    log(content, colour="\033[33m", LogType="Warning")
def lsucc(content): #Green text
    log(content, colour="\033[32m", LogType="Success")


if SUBMITEDITS:
    log("SUBMITEDITS is set to True. Edits will actually be made")
else:
    EditLog = open("EditLog.txt", "w", encoding="utf-8")
    log("SUBMITEDITS is set to False. Edits will not be requested, only simulated and logged")


class APIException(Exception):
    def __init__(self, message, code):
        self.message = message
        self.code = code
    def __str__(self):
        return f"{self.code}: {self.message}"


username, userid = None, None
enwiki = "https://en.wikipedia.org/"
requestSession = requests.Session()
requestSession.headers.update({"User-Agent": "python-wikibot/2.1.0"}) #version number is mostly random

#Central request handler, used for automatically sorting cookies
MaxRequestTries = 3
def request(method, page, **kwargs):
    request = None
    for i in range(1, MaxRequestTries+1):
        startTime = time.perf_counter()
        try:
            request = getattr(requestSession, method)(page, **kwargs)
        except (requests.ConnectionError, requests.Timeout) as exc:
            lalert(f"Failed to send a request due to timeout on try {i}{i<MaxRequestTries and '; gonna sleep for a bit and then try again' or ''}")
            if i == MaxRequestTries:
                raise exc
            time.sleep(5)
        else:
            timeTaken = time.perf_counter() - startTime
            break
    if timeTaken > 2.5:
        lwarn(f"[request] Just took {timeTaken}s to complete a single request - are we running alright?")
    return request


#Similar to request, but also adds some api-specific checks and simplicity
def requestapi(method, apimethod, DoAssert=True, **kwargs):
    apirequest = request(method, enwiki+"w/api.php?"+apimethod+f"&format=json{DoAssert and '&assert=user' or ''}", **kwargs)
    data = apirequest.json()
    if "error" in data: #Request failed
        code,info = data["error"]["code"], data["error"]["info"]
        lerror(f"[requestapi] API Request failed to complete for query '{apimethod}' | {code} - {info}")
        raise APIException(info, code)
    if "warnings" in data: #Request worked, though theres some issues
        for warntype,text in data["warnings"].items():
            lwarn(f"[requestapi] API Request {warntype} warning for query '{apimethod}' - {text['*']}")
    # print("Haha look at me its raw data man for",method,apimethod,data)
    return data
def GetTokenForType(actiontype):
    return requestapi("get", "action=query&meta=tokens&type=*", DoAssert=False)["query"]["tokens"][f"{actiontype}token"]


boundary = "-----------PYB"+str(random.randint(1e9, 9e9)) #Any obscure string works
log(f"[request] Using boundary {boundary}")
def CreateAPIFormRequest(location, data, DoAssert=True):
    #For post-based api requests. Helps avoid the possiblity of url encoding issues
    finaltext = ""
    for key, value in data.items():
        finaltext += f"""{boundary}\nContent-Disposition: form-data; name="{key}"\n\n{value}\n"""
    finaltext += f"{boundary}--"
    return requestapi("post", location, DoAssert=DoAssert, data=finaltext.encode("utf-8"), headers={"Content-Type":f"multipart/form-data; boundary={boundary[2:]}"})

def CheckIfStopped():
    return activelyStopped
def HaltIfStopped():
    if activelyStopped:
        lalert("The thread has been paused from continuing while panic mode is active. Pausing thread...")
        while activelyStopped:
            time.sleep(5)
        lsucc("Panic mode is no longer active. Exiting pause...")
        return True
    return False
def SetStopped(state):
    global activelyStopped
    if state != activelyStopped:
        log(f"Setting panic state to {state}")
    activelyStopped = state


namespaces = ["User", "Wikipedia", "File", "MediaWiki", "Template", "Help", "Category", "Portal", "Draft", "TimedText", "Module"] #Gadget( definition) is deprecated
pseudoNamespaces = {"WP":"Wikipedia", "WT":"Wikipedia talk", "Project":"Wikipedia", "Project talk":"Wikipedia talk",
                    "Image":"File", "Image talk":"File talk", "Mediawiki":"MediaWiki", "Mediawiki talk":"MediaWiki talk"} #Special cases that dont match normal sets
namespaceIDs = {"Article":0, "Talk":1, "User":2, "User talk":3, "Wikipedia":4, "Wikipedia talk":5, "File":6, "File talk":7,
                "MediaWiki":8, "MediaWiki talk":9, "Template":10, "Template talk":11, "Help":12, "Help talk":13,
                "Category":14, "Category talk":15, "Portal":100, "Portal talk":101, "Draft":118, "Draft talk":119,
                "TimedText":710, "TimedText talk":711, "Module":828, "Module talk":829, "Special":-1, "Media":-2}
def GetNamespace(identifier):
    #Simply gets the namespace of an article from its name
    if type(identifier) == str:
        for namespace in namespaces:
            if identifier.startswith(namespace+":"):
                return namespace
            if identifier.startswith(namespace+" talk:"):
                return namespace+" talk"
        prefix = identifier.split(":")[0]
        if prefix in pseudoNamespaces:
            return pseudoNamespaces[prefix]
        if identifier.startswith("Talk:"):
            return "Talk"
        if identifier.startswith("Special:"):
            return "Special"
        return "Article"
    elif type(identifier) == int:
        for namespace, nsid in namespaceIDs.items():
            if nsid == identifier:
                return namespace
def GetNamespaceID(articlename):
    return namespaceIDs[GetNamespace(articlename)]
def StripNamespace(articlename):
    namespace = GetNamespace(articlename)
    if namespace == "Article":
        return articlename
    else:
        return articlename[len(namespace)+1:]


def SubstituteIntoString(wholestr, substitute, start, end):
    return wholestr[:start]+substitute+wholestr[end:]
class Template: #Parses a template and returns a class object representing it
    def __init__(self, templateText):
        if type(templateText) != str or templateText[:2] != "{{" or templateText[-2:] != "}}":
            raise Exception(f"The text '{templateText}' is not a valid template")
        self.Original = templateText
        self.Text = templateText
        templateArgs = templateText[2:-2].split("|")
        self.Template = templateArgs[0].strip()
        args = {}
        for arg in templateArgs:
            splitarg = arg.split("=")
            key, item = splitarg[0], "=".join(splitarg[1:])
            if not item: #No key
                lowestKeyPossible = 1
                while True:
                    if lowestKeyPossible in args:
                        lowestKeyPossible += 1
                    else:
                        args[lowestKeyPossible] = arg.strip()
                        break
            else: #Key specified
                args[key.strip()] = item.strip()
        self.Args = args

    #The functions below are designed to respect the original template's format (E.g. its spacing)
    #Simply use the below functions, and then ask for self.Text for the new representation to use
    #TODO: Re-code the below, because its bloody stupid and has problems (we use regex?? why not just store whitespace seperately???)
    def ChangeKey(self, key, newkey): #Replaces one key with another, retaining the original data
        #NOTE: THIS CURRENTLY ASSUMES YOU ARE NOT ATTEMPTING TO CHANGE AN UNKEY'D NUMERICAL INDEXs
        if type(key) == int or key.isnumeric():
            lwarn(f"[Template] CK was told to change {key} to {newkey} in {self.Template} despite it being a numerical index")
        if not key in self.Args:
            raise KeyError(f"{key} is not a key in the Template")
        self.Args[newkey] = self.Args[key]
        self.Args.pop(key)
        keylocation = regex.compile(f"\| *{key} *=").search(self.Text)
        keytext = keylocation.group()
        self.Text = SubstituteIntoString(self.Text, keytext.replace(key, newkey), *keylocation.span())

    def ChangeKeyData(self, key, newdata): #Changes the contents of the key
        #NOTE: THIS CURRENTLY ASSUMES YOU ARE NOT ATTEMPTING TO CHANGE AN UNKEY'D NUMERICAL INDEX
        if type(key) == int or key.isnumeric():
            lwarn(f"[Template] CKD was told to change {key} to {newkey} in {self.Template} despite it being a numerical index")
        if not key in self.Args:
            raise KeyError(f"{key} is not a key in the Template")
        olddata = self.Args[key]
        self.Args[key] = newdata
        keylocation = regex.compile(f"\| *{key} *=").search(self.Text)
        target = self.Text[keylocation.start()+1:].split("|")[0]
        self.Text = SubstituteIntoString(self.Text, target.replace(olddata, newdata), keylocation.start()+1, keylocation.start()+len(target)+1)

revisionMoveRegex = regex.compile('^(.+?) moved page \[\[([^\]]+)\]\] to \[\[([^\]]+)\]\]')
class Revision: #For getting the history of pages
    def __init__(self, data, diff=None):
        self.ID = data["revid"]
        self.ParentID = data["parentid"]
        self.User = ("userhidden" in data and "< User hidden >") or data["user"]
        self.Timestamp = data["timestamp"][:-1] #Strip the ending Z for datetime
        self.Date = datetime.datetime.fromisoformat(self.Timestamp)
        self.Age = (datetime.datetime.utcnow() - self.Date).total_seconds()
        self.Comment = ("commenthidden" in data and "< Comment hidden >") or data["comment"]
        self.Size = data["size"]
        if type(diff) == int:
            self.SizeChange = diff
        else:
            self.SizeChange = self.Size
        self.IsMinor = "minor" in data
        self.IsIP = "anon" in data
        self.IsSuppressed = "suppressed" in data

    def IsMove(self):
        #Returns wasMoved, From, To
        #Based off of the edit summary and the change in size of the page
        #Can technically be fooled, but it's so unlikely, and shouldn't be a major consequence regardless (hopefully)
        moveData = revisionMoveRegex.search(self.Comment)
        if moveData and moveData.group(1) == self.User:
            if self.SizeChange == 0 or self.SizeChange == 61+len(moveData.group(3).encode("utf-8")):
                return True, moveData.group(2), moveData.group(3)
        return False, None, None


def CheckActionCount():
    global lastActionTime
    global actionCount
    if actionCount >= maxEdits and maxEdits > 0:
        lsucc(f"\n\nThe bot has hit its action count limit of {maxEdits} and will not make any further edits. Pausing script indefinitely...")
        while True:
            time.sleep(60)
    actionCount += 1
    if actionCount % 10 == 0:
        log(f"Action count: {actionCount}")
    if time.time()-lastActionTime < APS: #Slow it down
        print("Waiting for action cooldown to wear off")
        while time.time()-lastActionTime < APS:
            time.sleep(.2)
    lastActionTime = time.time()


def SimplifyQueryData(queryData):
    out = {"normalized": {}, "redirects": {}}
    if "normalized" in queryData:
        for occurance in queryData["normalized"]:
            out["normalized"][occurance["from"]] = occurance["to"]
    if "redirects" in queryData:
        for occurance in queryData["redirects"]:
            out["redirects"][occurance["from"]] = occurance["to"]
    return out

bracketbalancereg = regex.compile('{{|}}') #For template processing
_ArticleSearchString = "action=query&prop=info&indexpageids=&intestactions=edit|move"
class Article: #Creates a class representation of an article to contain functions instead of calling them from everywhere. Also makes management easier
    def __init__(self, identifier=None, *, FollowRedirects=False, pageInfo=None, queryData=None):
        #cringe code that keeps getting messier
        if pageInfo and not queryData:
            lwarn(f"Attempted to declare an article from raw data with no redirect data")
            queryData = {"normalized": {}, "redirects": {}}
        if not pageInfo:
            if type(identifier) == str:
                identifier = urllib.parse.quote(identifier.replace("_", " "))
                searchType = "titles"
            elif type(identifier) == int:
                searchType = "pageids"
            elif type(identifier) == dict:
                if "pageid" in identifier:
                    identifier = identifier["pageid"]
                    searchType = "pageids"
                elif "title" in identifier:
                    identifier = identifier["title"]
                    searchType = "titles"
            else:
                raise Exception(f"Invalid identifier input '{identifier}'")
            rawData = requestapi("get", f"{_ArticleSearchString}&{searchType}={identifier}{FollowRedirects and '&redirects=' or ''}")
            queryData = SimplifyQueryData(rawData["query"])
            pageInfo = rawData["query"]["pages"][rawData["query"]["pageids"][0]] #Loooovely oneliner, ay?

        if "invalid" in pageInfo:
            raise APIException(pageInfo["invalidreason"],"invalidpage")
        self._rawdata = pageInfo
        self.NamespaceID = pageInfo["ns"]
        self.Namespace = GetNamespace(self.NamespaceID)
        self.Exists = "missing" not in pageInfo
        self.Title = pageInfo["title"]
        self.URLTitle = urllib.parse.quote(self.Title)
        if self.NamespaceID != 0:
            self.StrippedTitle = self.Title[len(self.Namespace)+1:]
        else:
            self.StrippedTitle = self.Title
        self.StrippedURLTitle = urllib.parse.quote(self.StrippedTitle)
        self.ContentModel = pageInfo["contentmodel"]
        self.IsRedirect = "redirect" in pageInfo
        self.WasRedirected = FollowRedirects and self.Title in queryData["redirects"].values()
        self.CanEdit = "edit" in pageInfo["actions"]
        self.CanMove = "move" in pageInfo["actions"]
        if self.Exists:
            self.PageID = pageInfo["pageid"]
            self.CurrentRevision = pageInfo["lastrevid"]
        else:
            self.PageID = None
            self.CurrentRevision = None
        #Storage variables
        self._Content = None
        self._Templates = None
    def __str__(self):
        return self.Title

    def GetContent(self):
        if not self.Exists:
            return
        if self._Content != None:
            return self._Content
        if self.NamespaceID < 0:
            #Special pages do exist, but their content is, for our purposes, not relevant here.
            #For simplicity we just assign empty strings
            lwarn(f"[Article] Attempted to access content of special page {self}")
            self._Content = ""
            return ""
        data = requestapi("get", f"action=query&prop=revisions&indexpageids=&pageids={self.PageID}&rvslots=*&rvprop=timestamp|user|comment|content")
        data = data["query"]["pages"][data["query"]["pageids"][0]]
        self._Content = data["revisions"][0]["slots"]["main"]["*"] #Idk man
        return self._Content

    def CanEditWithConditions(self, *, allowPageCreation=True, bypassExclusion=False):
        if not self.Exists and not allowPageCreation:
            return False, "Will only edit the page if it already exists"
        if not bypassExclusion and self.HasExclusion():
            return False, "The page has relevant bot exclusion"
        return self.CanEdit, "The API told us we can't edit the page"
    def Edit(self, newContent, editSummary, *, minorEdit=False, allowPageCreation=True, bypassExclusion=False, markAsBot=True):
        #Edit a page's content, replacing it with newContent
        if HaltIfStopped():
            return
        success, result = self.CanEditWithConditions(allowPageCreation=allowPageCreation, bypassExclusion=bypassExclusion)
        if not success:
            lwarn(f"[Article] Refusing to edit page ({self}): {result}")
            return
        if INDEV:
            if not (self.Namespace in ["User", "User talk"] and self.Title.find(username) > -1):
                #Not in bot's user space, and indev, so get out
                lwarn(f"[Article] Attempted to push edit to a space other than our own while in development mode ({self})")
                return False
            editSummary += ") (INDEV"
        CheckActionCount()
        if not SUBMITEDITS:
            # open(urllib.parse.quote(self.Title).replace("/", "slash")+".txt", "w").write(newContent)
            EditLog.write(f"Tried to edit {self} with the summary {editSummary}\n")
            EditLog.flush()
            return lwarn(f"[Article] Not submitting edit to {self} with summary '{editSummary}' as SUBMITEDITS is set to False")
        #All of our customary checks are done, now we actually start trying to edit the page
        log(f"Making edits to {self}:\n    {editSummary}")
        formData = {"pageid":self.PageID, "text":newContent, "summary":editSummary, "token":GetTokenForType("csrf"), "baserevid":self.CurrentRevision}
        if minorEdit:
            formData["minor"] = ""
        if markAsBot:
            formData["bot"] = ""
        if not allowPageCreation:
            formData["nocreate"] = ""
        try:
            return CreateAPIFormRequest("action=edit", formData)
        except Exception as exc:
            lerror(f"[Article edit] Warning: Failed to submit an edit request for {self} - {traceback.format_exc()}")

    def CanMoveTo(self, newPage, *, bypassExclusion=False, checkTarget=True):
        if not bypassExclusion and self.HasExclusion():
            return False, "The page has relevant bot exclusion"
        if checkTarget:
            newPageObj = Article(newPage)
            if newPageObj.Exists:
                quickHistory = newPageObj.GetHistory(2)
                if len(quickHistory) == 2 or not quickHistory[0].IsMove():
                    return False, "There exists a target page which likely can not be overwritten"
            if not newPageObj.CanEdit:
                return False, "The API told us the target page is no good (probably title blacklist)"
        return self.CanMove, "The API told us we can't move the page"
    def MoveTo(self, newPage, reason, *, leaveRedirect=True, bypassExclusion=False, checkTarget=True):
        #Move the page from its current location to a new one
        #Avoid supressing redirects unless necessary
        if HaltIfStopped():
            return
        success, result = self.CanMoveTo(newPage, bypassExclusion=bypassExclusion, checkTarget=checkTarget)
        if not success:
            lwarn(f"[Article] Refusing to move page ({self}) to its target ({newPage}): {result}")
            return
        if INDEV:
            if not (self.Namespace in ["User", "User talk"] and self.Title.find(username) > -1):
                #Not in bot's user space, and indev, so get out
                return lwarn(f"[Article] Attempted to move a page in a space other than our own while in development mode ({self})")
            reason += ") (INDEV"
        CheckActionCount()
        if not SUBMITEDITS:
            EditLog.write(f"Tried to move {self} to {newPage} with the summary {reason}\n")
            EditLog.flush()
            return lwarn(f"[Article] Not moving {self} to {newPage} with summary '{reason}' as SUBMITEDITS is set to False")
        #All our customary checks are done, begin the process of actually moving
        log(f"Moving {self} to {newPage}{leaveRedirect==False and ' (Redirect supressed)' or ''}:\n    {reason}")
        formData = {"fromid":self.PageID, "to":newPage, "reason":reason, "token":GetTokenForType("csrf")}
        if not leaveRedirect:
            formData["noredirect"] = ""
        try:
            return CreateAPIFormRequest("action=move", formData)
        except Exception as exc:
            lerror(f"[Article move] Warning: Failed to submit a move request for {self} - {traceback.format_exc()}")

    def GetWikiLinks(self, limit=200):
        if not self.Exists:
            return []
        data = requestapi("get", f"action=query&prop=links&indexpageids=&pllimit={limit}&pageids={self.PageID}")
        data = data["query"]["pages"][data["query"]["pageids"][0]]
        return data["links"]

    def GetSubpages(self):
        return requestapi("get", f"action=query&list=allpages&aplimit=100&apnamespace={self.NamespaceID}&apprefix={self.StrippedURLTitle}/")["query"]["allpages"]

    def GetTemplates(self):
        if self._Templates != None:
            return self._Templates
        if not self.Exists:
            return []
        templates = []
        textToScan = self.GetContent()
        while True:
            nextTemplate = textToScan.find("{{")
            if nextTemplate == -1:
                break #Found all templates, exit
            textToScan = textToScan[nextTemplate:]
            balance = 1
            furthestScan = 0
            while True:
                nextBracket = bracketbalancereg.search(textToScan[furthestScan+2:])
                if nextBracket:
                    bracketType = nextBracket.group()
                    balance += (bracketType == "{{" and 1) or -1
                    furthestScan += nextBracket.end()
                    if balance == 0:
                        templates.append(Template(textToScan[:furthestScan+2]))
                        textToScan = textToScan[2:] #Move past brackets
                        break
                else:
                    textToScan = textToScan[2:] #Skip past unbalanced bracket set
                    break #Unfinished template, ignore it
        self._Templates = templates
        return self._Templates

    def GetLinkedPage(self):
        #Article gets Talk, Talk gets Article, you get the idea
        ID = self.NamespaceID
        if ID < 0: #Special pages have no talk
            return Article(self.Title)
        elif ID == 1: #Special case for converting from Talk: to article space
            return Article(StripNamespace(self.Title))
        elif ID % 2 == 0:
            return Article(GetNamespace(ID+1) + ":" + StripNamespace(self.Title))
        else:
            return Article(GetNamespace(ID-1) + ":" + StripNamespace(self.Title))

    def GetHistory(self, limit=50, getContent=False):
        properties = "ids|timestamp|user|comment|flags|size"
        if getContent:
            properties += "|content"
        data = requestapi("get", f"action=query&prop=revisions&indexpageids=&pageids={self.PageID}&rvslots=*&rvlimit={limit}&rvprop={properties}")
        data = data["query"]["pages"][data["query"]["pageids"][0]]
        revisions = []
        for i in range(len(data["revisions"])):
            revision = data["revisions"][i]
            if i != len(data["revisions"])-1:
                child = data["revisions"][i+1]
                revisions.append(Revision(revision, revision["size"] - child["size"]))
            else:
                revisions.append(Revision(revision))
        return revisions

    def HasExclusion(self):
        #If the bot is excluded from editing a page, this returns True
        if not self.Exists:
            return False
        if not username:
            return True #Shouldn't reach this, but just in case
        for template in self.GetTemplates():
            if template.Template.lower() == "nobots": #We just arent allowed here
                log("[Article] nobots presence found")
                return True
            if template.Template.lower() == "bots": #Check |deny= and |allow=
                if "allow" in template.Args:
                    for bot in template.Args["allow"].split(","):
                        bot = bot.lower().strip()
                        if bot == username.lower() or bot == "all": #Allowed all or specific
                            log("[Article] {{bots}} presence found but permitted")
                            return False
                    log("[Article] {{bots}} presence found, not permitted")
                    return True #Not in the "allowed" list, therefore we dont get to be here
                if "deny" in template.Args:
                    for bot in template.Args["deny"].split(","):
                        bot = bot.lower().strip()
                        if bot == username.lower() or bot == "all": #Banned all or specific
                            log("[Article] {{bots}} presence found, denied")
                            return True
                        if bot == "none": #Allow all
                            log("[Article] {{bots}} presence found, not denied")
                            return False
                log("[Article] Exclusion check has managed to not hit a return, which is very odd")


def BatchProcessArticles(articleSet, *, FollowRedirects=False):
    # The order returned will be based on Page IDs
    pageIDs = []
    titles = []
    for identifier in articleSet:
        if type(identifier) == str:
            titles.append(identifier.replace("_", " "))#urllib.parse.quote(identifier.replace("_", " ")))
        elif type(identifier) == int:
            pageIDs.append(identifier)
        elif type(identifier) == dict:
            if "pageid" in identifier:
                pageIDs.append(identifier["pageid"])
            elif "title" in identifier:
                titles.append(identifier["title"].replace("_", " "))
        else:
            lalert(f"[BatchProcessArticles] Ignoring impossible Article identifier: {identifier}")
    if len(pageIDs) > 0 and len(titles) > 0:
        lwarn(f"[BatchProcessArticles] Received both types of input identifiers - expect abnormal ordering")
    output = []
    # The 200 at a time limit is arbitrary, I just felt like 200 sounded reasonable
    while len(pageIDs) > 0:
        rawData = requestapi("post", f"{_ArticleSearchString}{FollowRedirects and '&redirects=' or ''}", data={"pageids": "|".join(pageIDs[0:200])})["query"]
        queryData = SimplifyQueryData(rawData)
        pageIDs = pageIDs[200:]
        for pageid in rawData["pageids"]:
            output.append(Article(pageInfo=rawData["pages"][pageid], queryData=queryData))
        if len(pageIDs) > 0:
            log(f"[BatchProcessArticles] Working on pageids... {len(pageIDs)} left")
    while len(titles) > 0:
        rawData = requestapi("post", f"{_ArticleSearchString}{FollowRedirects and '&redirects=' or ''}", data={"titles": "|".join(titles[0:200])})["query"]
        queryData = SimplifyQueryData(rawData)
        titles = titles[200:]
        for pageid in rawData["pageids"]:
            output.append(Article(pageInfo=rawData["pages"][pageid], queryData=queryData))
        if len(titles) > 0:
            log(f"[BatchProcessArticles] Working on titles... {len(titles)} left")
    return output


def IterateCategory(category, torun):
    #Iterates all wikilinks of a category, even if multi-paged
    if HaltIfStopped():
        return
    catpage = Article(category)
    if not catpage.Exists:
        return lalert(f"[IterateCategory] Attempted to iterate '{category}' despite it not existing")
    data = requestapi("get", f"action=query&list=categorymembers&cmtype=page&cmlimit=100&cmpageid={catpage.PageID}")
    for page in data["query"]["categorymembers"]:
        torun(Article(page["pageid"]))
    cmcontinue = "continue" in data and data["continue"]["cmcontinue"]
    while cmcontinue:
        if HaltIfStopped():
            return
        data = requestapi("get", f"action=query&list=categorymembers&cmtype=page&cmlimit=100&cmpageid={catpage.PageID}&cmcontinue={cmcontinue}")
        for page in data["query"]["categorymembers"]:
            torun(Article(page["pageid"]))
        cmcontinue = "continue" in data and data["continue"]["cmcontinue"]


class WikiConfig: #Handles the fetching of configs from on-wiki locations
    def __init__(self, page, defaultConfig, *, immediatelyUpdate=True):
        self.Page = page
        self.Config = defaultConfig
        if immediatelyUpdate:
            self.update()

    def update(self):
        Page = Article(self.Page, FollowRedirects=True)
        if not Page.Exists:
            return lalert(f"[WikiConfig] Page {self.Page} doesn't exist")
        else:
            if Page.ContentModel != "json":
                lwarn(f"[WikiConfig] Page {self.Page} has a non-json content model {Page.ContentModel}")
            try:
                NewConfig = json.loads(Page.GetContent())
            except Exception as exc:
                return lerror(f"[WikiConfig] Trouble parsing {self.Page}: {exc}")
            else:
                for key,data in NewConfig.items():
                    value = data["Value"]
                    if self.Config[key] != value:
                        log(f"[WikiConfig] '{key}' in config {self.Page} was changed to '{value}'")
                        self.Config[key] = value

    def get(self, key):
        if key in self.Config:
            return self.Config[key]
        return None


def GetSelf():
    return username, userid

def AttemptLogin(name, password):
    global username, userid
    log(f"Attempting to log-in as {name}")
    loginAttempt = CreateAPIFormRequest("action=login", {"lgname":name, "lgpassword":password, "lgtoken":GetTokenForType("login")}, DoAssert=False)["login"]
    if loginAttempt["result"] != "Success":
        lerror(f"Failed to log-in as {name}. check the password and username are correct")
        return False, None
    else:
        username = loginAttempt["lgusername"]
        userid = loginAttempt["lguserid"]
        lsucc(f"Successfully logged in as {username} (ID {userid})")
        return True, username


log("WikiTools has loaded")


if __name__ == "__main__":
    #Interactive mode for quick testing
    #If intending to use anything request based, AttemptLogin will need doing first due to assert calls
    log("Currently in the WikiTools CLI mode. Make sure to log-in (AttemptLogin) to work around assert=user calls")
    while True:
        code = input("Input code >>> ")
        try:
            exec(code,globals(),locals())
        except BaseException as exc:
            lerror("Failed to handle custom code input: " + str(exc))
        else:
            lsucc("Successfully executed code input")
