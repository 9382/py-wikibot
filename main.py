# [!] Do NOT edit this file unless you know what you are doing (Its not exactly stable).
# [!] If you need to change the basic settings of the bot, please see the .env-example

from dotenv import dotenv_values
import urllib.parse
import re as regex
import threading
import colorama
import datetime
import requests
import random
import time
import os
#For an explenation of the config options below, please see the .env-example file
envvalues = dotenv_values()
SUBMITEDITS = envvalues["SUBMITEDITS"].lower() == "true"
INDEV = envvalues["INDEV"].lower() == "true"
EnabledTasks = envvalues["TASKS"].lower().replace("; ",";").split(";")
maxActionsPerMinute = int(envvalues["EDITSPERMIN"])
maxEdits = int(envvalues["MAXEDITS"])

isVerbose = envvalues["VERBOSE"].lower() == "true"
def verbose(origin,content):
    if isVerbose:
        print(f"[Verbose {origin}] {content}")

colorama.init()

def currentDate():
    #The current date in YYYY-MM-DD hh:mm:ss
    return str(datetime.datetime.fromtimestamp(time.time()//1))
def safeWriteToFile(filename,content,mode="w",encoding="UTF-8"):
    #Writes contents to a file, auto-creating the directory should it be missing
    if filename.find("\\") > -1:
        try:
            os.makedirs("/".join(filename.replace("\\","/").split("/")[:-1]),exist_ok=True)
        except:
            return False,f"Couldnt make directory for {filename}"
    try:
        file = open(filename,mode,encoding=encoding,newline="")
    except:
        return False,f"Failed to open {filename}"
    try:
        file.write(content)
    except Exception as exc:
        file.close()
        return False,f"Failed to write content for {filename}"
    file.close()
    return True,f"Successfully wrote to {filename}"
def log(content,*,colour=""):
    #Manages the writing to a day-based log file for debugging
    print(f"{colour}[Log {currentDate()[11:]}] {content}\033[0m")
    success,result = safeWriteToFile(f"Logs/{currentDate()[:10]}.log",f"[{currentDate()[11:]}] {content}\n","a")
    if not success:
        print(f"\033[41m\033[30m[Log {currentDate()[11:]}] Failed to write to log file: {result}\033[0m")
    return success
def lerror(content): #Black text, red background
    return log(content,colour="\033[41m\033[30m")
def lalert(content): #Red text
    return log(content,colour="\033[31m")
def lwarn(content): #Yellow text
    return log(content,colour="\033[33m")
def lsucc(content): #Green text
    return log(content,colour="\033[32m")

if SUBMITEDITS:
    log("SUBMITEDITS is set to True. Edits will actually be made")
else:
    log("SUBMITEDITS is set to False. Edits will not be requested, only simulated")
username,password = dotenv_values()["USER"],dotenv_values()["PASS"]
enwiki = "https://en.wikipedia.org/"
cookies = {}
def request(method,page,**kwargs):
    global cookies
    request = getattr(requests,method)(page,cookies=cookies,**kwargs)
    if "set-cookie" in request.headers:
        verbose("request","Attempting to note down some new cookies")
        #Handles cookies. Mostly for getting cookies from logging in
        setcookies = request.headers["set-cookie"].split(", ")
        for cookie in setcookies:
            actualCookie = cookie.split(";")[0]
            moreInfo = actualCookie.split("=")
            if moreInfo[0].find(" ") > -1:
                continue
            cookies[moreInfo[0]] = "=".join(moreInfo[1:])
            # print("Set cookie",moreInfo[0],"with value","=".join(moreInfo[1:]))
    return request
def GetTokenForType(actiontype):
    return request("get",enwiki+f"w/api.php?action=query&format=json&meta=tokens&type=*").json()["query"]["tokens"][f"{actiontype}token"]
boundary = "-----------PYB"+str(random.randint(1e9,9e9))
verbose("request",f"Using boundary {boundary}")
def CreateFormRequest(location,d):
    #This seems to be the approach that worked consistently for me, so thats what is used for all requests.
    finaltext = ""
    for arg,data in d.items():
        finaltext += f"""{boundary}\nContent-Disposition: form-data; name="{arg}"\n\n{data}\n"""
    finaltext += f"{boundary}--"
    return request("post",location,data=finaltext.encode("utf-8"),headers={"Content-Type":f"multipart/form-data; boundary={boundary[2:]}"})
def SubstituteIntoString(wholestr,substitute,start,end):
    return wholestr[:start]+substitute+wholestr[end:]

namespaces = ["User","Wikipedia","WP","File","MediaWiki","Template","Help","Category","Portal","Draft","TimedText","Module"] #Gadget( definition) is deprecated
pseudoNamespaces = {"CAT":"Category","H":"Help","MOS":"Wikipedia","WP":"Wikipedia","WT":"Wikipedia talk",
                    "Project":"Wikipedia","Project talk":"Wikipedia talk","Image":"File","Image talk":"File talk",
                    "WikiProject":"Wikipedia","T":"Template","MP":"Article","P":"Portal","MoS":"Wikipedia"} #Special cases that dont match normal sets
def GetNamespace(articlename):
    #Simply gets the namespace of an article from its name
    for namespace in namespaces:
        if articlename.startswith(namespace+":"):
            return namespace
        if articlename.startswith(namespace+" talk:"):
            return namespace+" talk"
    prefix = articlename.split(":")[0]
    if prefix in pseudoNamespaces:
        return pseudoNamespaces[prefix]
    if articlename.startswith("Talk:"):
        return "Talk"
    if articlename.startswith("Special:"):
        return "Special"
    return "Article"
namespaceIDs = {"Article":0,"Talk":1,"User":2,"User talk":3,"Wikipedia":4,"Wikipedia talk":5,"File":6,"File talk":7,
                "MediaWiki":8,"MediaWiki talk":9,"Template":10,"Template talk":11,"Help":12,"Help talk":13,
                "Category":14,"Category talk":15,"Portal":100,"Portal talk":101,"Draft":118,"Draft talk":119,
                "TimedText":710,"TimedText talk":711,"Module":828,"Module talk":829,"Special":-1,"Media":-2}
def GetNamespaceID(articlename):
    return namespaceIDs[GetNamespace(articlename)]
def StripNamespace(articlename):
    namespace = GetNamespace(articlename)
    if namespace == "Article":
        return articlename
    else:
        return articlename[len(namespace)+1:]
lastEditTime = 0
editCount = 0
def ChangeWikiPage(article,newcontent,editsummary,minorEdit):
    #Submits edits to pages automatically (since the form is a bit of a nightmare)
    #Not in the class as we need to centralise lastEditTime
    global lastEditTime
    global editCount
    if editCount >= maxEdits and maxEdits > 0:
        lwarn(f"\n\nWarning: The bot has hit its edit count limit of {maxEdits} and will not make any further edits. The edit to {article} has been prevented. Pausing script indefinitely...")
        while True:
            time.sleep(60)
    editCount += 1
    if editCount + moveCount % 5 == 0:
        print("Edit count:",editCount) #Purely statistical for the console
    if not SUBMITEDITS:
        return print(f"Not submitting changes to {article} as SUBMITEDITS is set to False")
    log(f"Making edits to {article}:\n    {editsummary}")
    EPS = 60/maxActionsPerMinute #Incase you dont wanna go too fast
    if time.time()-lastEditTime < EPS:
        print("Waiting for edit cooldown to wear off")
    while time.time()-lastEditTime < EPS:
        time.sleep(.2)
    lastEditTime = time.time()
    formData = {"wpUnicodeCheck":"ℳ𝒲♥𝓊𝓃𝒾𝒸ℴ𝒹ℯ","wpTextbox1":newcontent,"wpSummary":editsummary,"wpEditToken":GetTokenForType("csrf"),"wpUltimateParam":"1"}
    if minorEdit:
        formData["wpMinoredit"] = ""
    try:
        return CreateFormRequest(enwiki+f"/w/index.php?title={article}&action=submit",formData)
    except Exception as exc:
        lerror(f"[ChangeWikiPage] Warning: Failed to submit an edit form request for {article} -> Reason: {exc}")
        editcount -= 1 #Invalid, nullify the edit
    if editCount >= maxEdits and maxEdits > 0:
        lwarn(f"\n\nWarning: The bot has hit its edit count limit of {maxEdits} and will not make any further edits. Pausing script indefinitely...")
        while True:
            time.sleep(60)
lastMoveTime = 0 #Moves and edits have independent ratelimits
moveCount = 0
def MoveWikiPage(article,newPage,reason,leaveRedirect):
    #Exists for the same reason as the function above
    global lastMoveTime
    global moveCount
    if editCount + moveCount >= maxEdits and maxEdits > 0:
        lwarn(f"\n\nWarning: The bot has hit its action count limit of {maxEdits} and will not make any further actions. The action to {article} has been prevented. Pausing script indefinitely...")
        while True:
            time.sleep(60)
    moveCount += 1
    if moveCount % 5 == 0:
        print("Move count:",moveCount)
    log(f"Moving {article} to {newPage}{leaveRedirect==False and ' (Redirect supressed)' or ''}:\n    {reason}")
    EPS = 60/maxActionsPerMinute
    if time.time()-lastMoveTime < EPS:
        print("Waiting for move cooldown to wear off")
    while time.time()-lastMoveTime < EPS:
        time.sleep(.2)
    lastMoveTime = time.time()
    return True
def ExcludeTag(text,tag): #Returns a filtered version. Most useful for nowiki. Unused
    upperlower = "".join([f"[{x.upper()}{x.lower()}]" for x in tag])
    finalreg = f"<{upperlower}(>|[^>]*[^/]>)[\s\S]*?</{upperlower} *>"
    print(finalreg)
    return regex.sub(finalreg,"",text)

class Template: #Parses a template and returns a class object representing it
    def __init__(self,templateText):
        if type(templateText) != str or templateText[:2] != "{{" or templateText[-2:] != "}}":
            raise Exception(f"The text '{templateText}' is not a valid template")
        self.Original = templateText #DO NOT EDIT THIS
        self.Text = templateText
        templateArgs = templateText[2:-2].split("|")
        self.Template = templateArgs[0].strip()
        # print(f"Processing temmplate {self.Template}...")
        if len(self.Text) > 1500:
            verbose("Template",f"{self.Template} has a total length of {len(self.Text)}, which is larger than what is normally expected")
        args = {}
        for arg in templateArgs:
            splitarg = arg.split("=")
            key,item = splitarg[0],"=".join(splitarg[1:])
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
    def ChangeKey(self,key,newkey): #Replaces one key with another, retaining the original data
        #NOTE: THIS CURRENTLY ASSUMES YOU ARE NOT ATTEMPTING TO CHANGE AN UNKEY'D NUMERICAL INDEX.
        if type(key) == int or key.isnumeric():
            verbose("Template",f"CK was told to change {key} to {newkey} in {self.Template} despite it being a numerical index")
        if not key in self.Args:
            raise KeyError(f"{key} is not a key in the Template")
        self.Args[newkey] = self.Args[key]
        self.Args.pop(key)
        keylocation = regex.compile(f"\| *{key} *=").search(self.Text)
        keytext = keylocation.group()
        self.Text = SubstituteIntoString(self.Text,keytext.replace(key,newkey),*keylocation.span())
    def ChangeKeyData(self,key,newdata): #Changes the contents of the key
        #NOTE: THIS CURRENTLY ASSUMES YOU ARE NOT ATTEMPTING TO CHANGE AN UNKEY'D NUMERICAL INDEX.
        if type(key) == int or key.isnumeric():
            verbose("Template",f"CKD was told to change {key} to {newkey} in {self.Template} despite it being a numerical index")
        if not key in self.Args:
            raise KeyError(f"{key} is not a key in the Template")
        olddata = self.Args[key]
        self.Args[key] = newdata
        keylocation = regex.compile(f"\| *{key} *=").search(self.Text)
        target = self.Text[keylocation.start()+1:].split("|")[0]
        self.Text = SubstituteIntoString(self.Text,target.replace(olddata,newdata),keylocation.start()+1,keylocation.start()+len(target)+1)

monthconversion = {"January":1,"February":2,"March":3,"April":4,"May":5,"June":6,"July":7,"August":8,"September":9,"October":10,"November":11,"December":12}
revisionDateRegex = regex.compile('(\d+):(\d+), (\d+) (\w+) (\d+)')
def parseRevisionDate(text):
    hour,minute,day,month,year = revisionDateRegex.search(text).groups()
    return datetime.datetime(int(year),monthconversion[month],int(day),int(hour),int(minute))

#Collected data is layed out below
revisionRegex = regex.compile(
    '<li data-mw-revid="(\d+)".+?' #ID
    + 'class="mw-changeslist-date" title="[^"]+">([\w\d:, ]+)</a>.+?' #Date
    + '<span class=\'history-user\'><a [^>]+><bdi>([^<]+)</bdi>.+?' #User
    + '<span class="history-size mw-diff-bytes" data-mw-bytes="(\d+)">.+?' #Size
    + 'class="mw-plusminus-\w+ mw-diff-bytes" title="[\d,]+ [\w ]+">([+−]?[\d,]+)</(?:span|strong)>.+?' #Size change
    + '<span class="comment comment--without-parentheses">(.+?)</span>' #Revision summary
) #Note: Watch out - the negative in diff-bytes is (−) not (-)
revisionMoveRegex = regex.compile('(.+?) moved page <a [^>]+>([^<]+)</a> to <a [^>]+>([^<]+)</a>')
class Revision: #For getting the history of pages
    def __init__(self,revisionText):
        self.RawText = revisionText
        regexResults = revisionRegex.search(revisionText)
        if not regexResults:
            lerror("History search of text failed the regex check.\nData: "+str(revisionText))
            self.Failed = True
            return
        rID,rDate,rUser,rSize,rSizeChange,rSummary = regexResults.groups()
        rID = int(rID)
        rSizeChange = rSizeChange.replace(",","")
        if rSizeChange[0] == "+":
            rSizeChange = int(rSizeChange[1:])
        elif rSizeChange[0] == "−":
            rSizeChange = int(rSizeChange[1:])*-1
        else:
            rSizeChange = int(rSizeChange)
        self.ID = rID
        self.DateText = rDate
        self.Date = parseRevisionDate(rDate)
        self.User = rUser
        self.Size = rSize
        self.SizeChange = rSizeChange
        self.Summary = rSummary
        self.Failed = False
    def IsMinor(self):
        return self.RawText.find("<abbr class=\"minoredit\" title=") > -1
    def IsMove(self):
        #Returns wasMoved, From, To
        #This will ignore move revisions that created a page by placing redirect categories (the page left behind)
        if self.SizeChange == 0:
            moveData = revisionMoveRegex.search(self.Summary)
            if moveData and moveData.group(1) == self.User:
                return True,moveData.group(2),moveData.group(3)
        return False,None,None

activelyStopped = False
rawtextreg = regex.compile('<textarea [^>]+>([^<]+)</textarea>')
wholepagereg = regex.compile('<div id="mw-content-text" class="mw-body-content[ \w-]*"[^>]*?>([\s\S]+)<div id="catlinks" class="[^"]+" data-mw="interface">') #Potentially a bad move? NOTE: See if convenient API exists
wikilinkreg = regex.compile('<a href="/wiki/([^"]+?)" (class="[^"]*" )?title="[^"]+?">')
bracketbalancereg = regex.compile('{{|}}') #For templates
stripurlparams = regex.compile('([^?#&]+)([?#&].+)?')
class Article: #Creates a class representation of an article to contain functions instead of calling them from everywhere. Also makes management easier
    def __init__(self,articleName):
        articleName = urllib.parse.unquote(articleName.replace("_"," "))
        self.Article = articleName
        self.StrippedArticle = stripurlparams.search(self.Article).group(1)
        if self.Article != self.StrippedArticle:
            verbose("Article",f"Just stripped '{stripurlparams.search(self.Article).group(2)}' from {self.StrippedArticle}")
        self.Namespace = GetNamespace(articleName)
        self.OriginalContent = None #Dont change this
        self.Content = None #Avoid getting directly outside of class functions
        self.RawContent = None #Same as above
        self.Templates = None #Same as above
    def __str__(self):
        return self.StrippedArticle
    def GetRawContent(self,forceNew=False):
        if self.RawContent != None and not forceNew:
            return self.RawContent
        if GetNamespace(self.Article) == "Special":
            #Special pages wont get past the rawtext check but do exist in reality and we need them
            #Setting them to empty strings mean they pass the .exists() check
            self.RawContent = ""
            self.OriginalContent = ""
            return ""
        else:
            try:
                content = request("get",f"{enwiki}wiki/{self.StrippedArticle}?action=edit").text
                #URL should be stripped of params - they should only matter in GetContent. If we dont strip, we get rightfully caught by the global blacklist
            except Exception as exc:
                log(f"[Article] Warning: Failed a GRC request while trying to get {self.StrippedArticle} -> Reason: {exc}")
                content = "" #Default to an empty string so that rawtext fails and this gets marked as "not existing"
            rawtext = rawtextreg.search(content)
            if not rawtext:
                #Not an article, therefore flag as such and give up now.
                self.RawContent = False
                self.OriginalContent = False
                verbose("Article",f"{self.Article} failed the rawtextreg search")
                return False
            correctedtext = regex.sub("&amp;","&",regex.sub("&lt;","<",rawtext.group(1))) #&lt; and &amp; autocorrection
            self.RawContent = correctedtext
            self.OriginalContent = correctedtext
            return correctedtext
    def exists(self):
        if self.RawContent == None:
            self.GetRawContent()
        return self.RawContent != False
    def GetContent(self): #Very messy, dont use if you dont need
        if self.Content:
            return self.Content
        if not self.exists():
            return
        try:
            content = wholepagereg.search(request("get",enwiki+"wiki/"+self.Article).text).group(1)
        except Exception as exc:
            lwarn(f"[Article] Warning: Failed a GC request while trying to get {self.Article} -> Reason: {exc}")
            return "" #This should never happen thanks to the .exists() call above, but anything could happen in 2 seconds
        self.Content = content
        return content
    def edit(self,newContent,editSummary,*,minorEdit=False,bypassExclusion=False):
        if activelyStopped:
            lalert(f"Warning: Can't push edits while in panic mode (Once sorted, change User:{username}/panic to re-enable). Thread will now hang until able to resume...")
            while activelyStopped:
                time.sleep(10)
            lsucc("We are no loner panicking. Exiting pause...")
        if not self.exists():
            #Will still continue to submit the edit, even if this is the case
            log(f"Warning: Editing article that doesnt exist ({self.Article}). Continuing anyways...")
        if newContent == self.OriginalContent:
            #If you really need to null edit, add a \n. MW will ignore it, but this wont
            return lwarn(f"Warning: Attempted to make empty edit to {self.Article}. The edit has been cancelled")
        if self.HasExclusion() and not bypassExclusion:
            #Its been requested we stay away, so we will
            return lwarn(f"Warning: Refusing to edit page that has exclusion blocked ({self.Article})")
        if INDEV:
            if not (self.Namespace in ["User","User talk"] and self.Article.find(username) > -1):
                #Not in bot's user space, and indev, so get out
                return lwarn(f"Warning: Attempted to push edit to a space other than our own while in development mode ({self.Article})")
            editSummary += " [INDEV]"
        if self.OriginalContent:
            oldContent = self.OriginalContent
            currentContent = self.GetRawContent(True)
            if oldContent != currentContent:
                #Edit conflict -> Content has changed since
                return log(f"Warning: Refused to edit page that has been edited since last check ({self.Article})")
        ChangeWikiPage(self.StrippedArticle,newContent,editSummary,minorEdit)
    def GetWikiLinks(self,afterPoint=None):
        if not self.exists():
            return []
        #Does what the name suggests. Note that this is looking for GetWikiText, not GetRawWikiText. Consider changing that
        if afterPoint:
            textAfter = self.GetContent()[self.GetContent().find(afterPoint):]
            if len(textAfter) < 20:
                verbose("Article",f"'{self.Article}' used afterPoint {afterPoint} just to get a size of {len(textAfter)}. Resulting text: {textAfter}")
            result = [x[0] for x in wikilinkreg.findall(textAfter)]
            verbose("Article",f"'{self.Article}' gave {len(result)} wikilinks with afterPoint {afterPoint}")
            return result
        else:
            result = [x[0] for x in wikilinkreg.findall(self.GetContent())]
            verbose("Article",f"'{self.Article}' gave {len(result)} wikilinks")
            return result
    def GetTemplates(self):
        if self.Templates != None:
            return self.Templates
        if not self.exists():
            self.Templates = []
            return []
        templates = []
        textToScan = self.RawContent
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
        self.Templates = templates
        verbose("Article",f"Registered {len(self.Templates)} templates for {self.Article}")
        return self.Templates
    def GetHistory(self,limit=50):
        historyContent = Article(self.StrippedArticle+f"?action=history&limit={limit}").GetContent()
        revisions = []
        for line in historyContent.split("\n"):
            if line.startswith("<li data-mw-revid="):
                revision = Revision(line)
                if not revision.Failed:
                    revisions.append(revision)
        verbose("Article",f"Found {len(revisions)} revisions during history check of {self.StrippedArticle}")
        return revisions
    def GetSubpages(self):
        return Article(f"Special:PrefixIndex/{self.StrippedArticle}/").GetWikiLinks("mw-htmlform-ooui-wrapper")
    def IsRedirect(self):
        if not self.exists():
            return False
        return self.GetRawContent().startswith("#REDIRECT")
    def HasExclusion(self):
        #If the bot is excluded from editing a page, this returns True
        for template in self.GetTemplates():
            if template.Template.lower() == "nobots": #We just arent allowed here
                verbose("HasExclusion","nobots presence found")
                return True
            if template.Template.lower() == "bots": #Check |deny= and |allow=
                if "allow" in template.Args:
                    for bot in template.Args["allow"].split(","):
                        bot = bot.lower().strip()
                        if bot == username.lower() or bot == "all": #Allowed all or specific
                            verbose("HasExclusion","{{bots}} presence found but permitted")
                            return False
                    verbose("HasExclusion","{{bots}} presence found, not permitted")
                    return True #Not in the "allowed" list, therefore we dont get to be here
                if "deny" in template.Args:
                    for bot in template.Args["deny"].split(","):
                        bot = bot.lower().strip()
                        if bot == username.lower() or bot == "all": #Banned all or specific
                            verbose("HasExclusion","{{bots}} presence found, denied")
                            return True
                        if bot == "none": #Allow all
                            verbose("HasExclusion","{{bots}} presence found, not denied")
                            return False
                verbose("HasExclusion","Exclusion check has managed to not hit a return")
    def MoveTo(self,newPage,reason,leaveRedirect=True):
        #Move the page from its current location to a new one
        #Avoid supressing redirects unless necessary
        namespaceID = GetNamespaceID(newPage)
        newPage = StripNamespace(newPage) #Remove any provided namespace
        leaveRedirect = (leaveRedirect and 1) or 0
        if INDEV:
            if not (self.Namespace in ["User","User talk"] and self.Article.find(username) > -1):
                #Not in bot's user space, and indev, so get out
                print("Violations make me :(",self.Namespace,self,Article,username)
                return lwarn(f"Warning: Attempted to move a page in a space other than our own while in development mode ({self.Article})")
            reason += " [INDEV]"
        if not SUBMITEDITS:
            return lwarn(f"Not moving {self.StrippedArticle} to {newPage} as SUBMITEDITS is set to False")
        isValid = MoveWikiPage(self,newPage,reason,leaveRedirect)
        if isValid:
            result = CreateFormRequest(enwiki+"w/index.php?title=Special:MovePage&action=submit",
                {"wpNewTitleNs":namespaceID,"wpNewTitleMain":newPage,"wpReason":reason,"wpOldTitle":self.StrippedArticle,"wpEditToken":GetTokenForType("csrf"),"wpLeaveRedirect":leaveRedirect}
            )
            return result

def IterateCategory(category,torun):
    #Iterates all wikilinks of a category, even if multi-paged
    #Note: If the page scanning is successful, make sure to return True, or else this wont know
    lastpage = ""
    catpage = Article(category)
    if not catpage.exists():
        lwarn(f"Attempting to iterate '{category}' despite it not existing")
    links = catpage.GetWikiLinks('<div class="mw-category"><div class="mw-category-group">')
    for page in links:
        if torun(page):
            lastpage = page
    #If we dont get a lastpage in the first place, its either empty, or the task needs configuring. Escape either way
    if not lastpage:
        verbose("IterateCategory",f"'{category}' had no returned lastpage on its first try")
    while lastpage:
        newlastpage = ""
        catpage = Article(category+"?from="+lastpage)
        links = catpage.GetWikiLinks('<div class="mw-category"><div class="mw-category-group">')
        for page in links:
            if page != lastpage and torun(page):
                newlastpage = page
        if newlastpage:
            if ord(newlastpage[0]) < ord(lastpage[0]) or newlastpage == lastpage:
                #Determines if we have either looped, or gone back pages due to wikilinks in other sections.
                #Either way, its finished, and we should now exit
                log(f"Looped around, finished scanning {category}")
                break
            lastpage = newlastpage
        else:
            #No pages could be found in the category, its finished. Exit
            log(f"No more LPC, finished scanning {category}")
            break

log(f"Attempting to log-in as {username}")
CreateFormRequest(enwiki+f"w/api.php?action=login&format=json",{"lgname":username,"lgpassword":password,"lgtoken":GetTokenForType("login")}) #Set-Cookie handles this
if not "centralauth_User" in cookies:
    lalert(f"[!] Failed to log-in as {username}, check the password and username are correct")
    exit()
lsucc("Successfully logged in")

#Task loader
log("Attempting to load tasks...")
execList = {}
#Odd approach but it works
for file in os.listdir("Tasks"):
    if not file.endswith(".py"):
        verbose("Task Loader",f"{file} doesn't end with .py, it shouldn't be within the /Tasks")
        continue
    if not os.path.isfile("Tasks/"+file):
        verbose("Task Loader",f"{file} is a subfolder and shouldn't be within the /Tasks")
        continue
    if file[:-3].lower() in EnabledTasks: #Removes .py extension
        execList[file] = bytes("#coding: utf-8\n","utf-8")+open("Tasks/"+file,"rb").read()
    else:
        log(f"[Tasks] Skipping task {file} as it is not enabled")
for file,contents in execList.items():
    try:
        log(f"[Tasks] Running task {file}")
        taskThread = threading.Thread(target=exec,args=(contents,globals()))
        taskThread.start()
    except Exception as exc:
        lerror(f"[Tasks] Task {file} loading error -> {exc}")
lsucc("Finished loading tasks")
while True:
    time.sleep(60)
    tasks = threading.active_count()
    # log(f"Active task count: {tasks-1}")
    if tasks == 1:
        lalert("All tasks seem to have been terminated or finished")
        break
    #Note: If you get a login fail
    try:
        confirmStatus = request("get",enwiki+"w/api.php?action=query&assert=user&format=json").json()
    except Exception as exc:
        lalert(f"assert=user request failed. Reason: {exc}")
    else:
        if "error" in confirmStatus and confirmStatus["error"]["code"] == "assertuserfailed":
            activelyStopped = True
            lerror(f"The assert=user check has failed. Stopping all bot actions until script is restarted")
        else:
            panic = Article(f"User:{username}/panic")
            if panic.exists():
                if panic.GetRawContent().strip().lower() == "true":
                    activelyStopped = True
                else:
                    activelyStopped = False
            else:
                verbose("Main Thread",f"Panic page (User:{username}/panic) doesn't exist")
input("Press enter to exit...")
