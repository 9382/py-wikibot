# [!] Do NOT edit this file unless you know what you are doing (Its not exactly stable).
# [!] If you need to change the basic settings of the bot, please see the .env-example

from dotenv import dotenv_values
from datetime import datetime
import re as regex
import threading
import requests
import random
import time
import os
#For an explenation of the config options below, please see the .env-example file
envvalues = dotenv_values()
SUBMITEDITS = envvalues["SUBMITEDITS"].lower() == "true"
INDEV = envvalues["INDEV"].lower() == "true"
EnabledTasks = envvalues["TASKS"].lower().replace("; ",";").split(";")
maxEditsPerMinute = int(envvalues["EDITSPERMIN"])
maxEdits = int(envvalues["MAXEDITS"])

isVerbose = envvalues["VERBOSE"].lower() == "true"
def verbose(origin,content):
    if isVerbose:
        print(f"[Verbose {origin}] {content}")

def currentDate():
    #The current date in YYYY-MM-DD hh:mm:ss
    return str(datetime.fromtimestamp(time.time()//1))
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
def log(content):
    #Manages the writing to a daily log file for debugging
    print(f"[Log {currentDate()[11:]}]",content)
    success,result = safeWriteToFile(f"Logs/{currentDate()[:10]}.log",f"[{currentDate()[11:]}] {content}\n","a")
    if not success:
        print(f"[Log {currentDate()[11:]}] Failed to write to log file: {result}")
    return success
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
                    "Project":"Wikipedia","Project_talk":"Wikipedia talk","Image":"File","Image_talk":"File talk",
                    "WikiProject":"Wikipedia","T":"Template","MP":"Article","P":"Portal","MoS":"Wikipedia"} #Special cases that dont match normal sets
def GetNamespace(articlename):
    #Simply gets the namespace of an article from its name
    for namespace in namespaces:
        if articlename.startswith(namespace+":"):
            return namespace
        if articlename.startswith(namespace+"_talk:"):
            return namespace+" talk"
    prefix = articlename.split(":")[0]
    if prefix in pseudoNamespaces:
        return pseudoNamespaces[prefix]
    if articlename.startswith("Talk:"):
        return "Talk"
    if articlename.startswith("Special:"):
        return "Special"
    return "Article"
lastEditTime = 0
editCount = 0
def ChangeWikiPage(article,newcontent,editsummary,minorEdit):
    #Submits edits to pages automatically (since the form is a bit of a nightmare)
    #Not in the class as we need to centralise lastEditTime
    global lastEditTime
    global editCount
    if editCount >= maxEdits and maxEdits > 0:
        log(f"\n\n\nWarning: The bot has hit its edit count limit of {maxEdits} and will not make any further edits. The edit to {article} has been prevented. Pausing script indefinitely...")
        while True:
            time.sleep(60)
    editCount += 1
    if editCount % 5 == 0:
        print("Edit count:",editCount) #Purely statistical for the console
    if not SUBMITEDITS:
        return print(f"Not submitting changes to {article} as SUBMITEDITS is set to False")
    log(f"Making edits to {article}:\n    {editsummary}")
    EPS = 60/maxEditsPerMinute #Incase you dont wanna go too fast
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
        log(f"[ChangeWikiPage] Warning: Failed to submit an edit form request for {article} -> Reason: {exc}")
        editcount -= 1 #Invalid, nullify the edit
    if editCount >= maxEdits and maxEdits > 0:
        log(f"\n\n\nWarning: The bot has hit its edit count limit of {maxEdits} and will not make any further edits. Pausing script indefinitely...")
        while True:
            time.sleep(60)
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
        if len(self.Text) > 1000:
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

# class Revision: #For getting the history of pages. Currently unimplemented
#     def __init__(self,revisionid)

activelyStopped = False
rawtextreg = regex.compile('<textarea [^>]+>([^<]+)</textarea>')
wholepagereg = regex.compile('<div id="mw-content-text" class="mw-body-content mw-content-ltr" [^>]+?>([\s\S]+)<div id="catlinks" class="[^"]+" data-mw="interface">') #Potentially a bad move? NOTE: See if convenient API exists
wikilinkreg = regex.compile('<a href="/wiki/([^"]+?)" (class="[^"]*" )?title="[^"]+?">')
templatesreg = regex.compile('({{([^{}]+({{[^}]+}})?)+}})')
stripurlparams = regex.compile('([^?#&]+)([?#&].+)?')
class Article: #Creates a class representation of an article to contain functions instead of calling them from everywhere. Also makes management easier
    def __init__(self,articleName):
        self.Article = articleName
        self.StrippedArticle = stripurlparams.search(self.Article).group(1)
        if self.Article != self.StrippedArticle:
            verbose("Article",f"Just stripped '{stripurlparams.search(self.Article).group(2)}' from {self.StrippedArticle}")
        self.Namespace = GetNamespace(articleName)
        self._raw = None #Dont change this
        self.Content = None #Avoid getting directly outside of class functions
        self.RawContent = None #Same as above
        self.Templates = None #Same as above
    def GetRawContent(self,forceNew=False):
        if self.RawContent != None and not forceNew:
            return self.RawContent
        try:
            content = request("get",f"{enwiki}wiki/{self.StrippedArticle}?action=edit").text
            #URL should be stripped of params - they should only matter in GetContent. If we dont strip, we get caught by the global blacklist
        except Exception as exc:
            log(f"[Article] Warning: Failed a GRC request while trying to get {self.StrippedArticle} -> Reason: {exc}")
            content = "" #Default to an empty string so that rawtext fails and this gets marked as "not existing"
        rawtext = rawtextreg.search(content)
        if not rawtext:
            #Not an article, therefore flag as such and give up now.
            self.RawContent = False
            self._raw = False
            verbose("Article",f"{self.Article} failed the rawtextreg search")
            return False
        correctedtext = regex.sub("&amp;","&",regex.sub("&lt;","<",rawtext.group(1))) #&lt; and &amp; autocorrection
        self.RawContent = correctedtext
        self._raw = correctedtext
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
            log(f"[Article] Warning: Failed a GC request while trying to get {self.Article} -> Reason: {exc}")
            return "" #This should never happen thanks to the .exists() call above, but anything could happen in 2 seconds
        self.Content = content
        return content
    def edit(self,newContent,editSummary,*,minorEdit=False,bypassExclusion=False):
        if activelyStopped:
            log(f"Warning: Can't push edits while in panic mode (Once sorted, change User:{username}/panic to re-enable). Thread will now hang until able to resume...")
            while activelyStopped:
                time.sleep(10)
            log("We are no loner panicking. Exiting pause...")
        if newContent == self._raw:
            #If you really need to null edit, add a \n. MW will ignore it, but this wont
            return log(f"Warning: Attempted to make empty edit to {self.Article}. The edit has been cancelled")
        if not self.exists():
            #Will still continue to submit the edit, even if this is the case
            log(f"Warning: Editing article that doesnt exist ({self.Article}). Continuing anyways...")
        if self.HasExclusion() and not bypassExclusion:
            #Its been requested we stay away, so we will
            return log(f"Warning: Refusing to edit page that has exclusion blocked ({self.Article})")
        if INDEV and not self.Namespace in ["User","User talk"]:
            return log(f"Warning: Attempted to push edit to non-user space while in development mode ({self.Article}, {self.Namespace})")
        if self.RawContent:
            oldContent = self.RawContent
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
        self.Templates = [Template(x[0]) for x in templatesreg.findall(self.RawContent)]
        verbose("Article",f"Registered {len(self.Templates)} templates for {self.Article}")
        return self.Templates
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
                            verbose("HasExclusion","bots presence found but permitted")
                            return False
                    verbose("HasExclusion","bots presence found, not permitted")
                    return True #Not in the "allowed" list, therefore we dont get to be here
                if "deny" in template.Args:
                    for bot in template.Args["deny"].split(","):
                        bot = bot.lower().strip()
                        if bot == username.lower() or bot == "all": #Banned all or specific
                            verbose("HasExclusion","bots presence found, denied")
                            return True
                        if bot == "none": #Allow all
                            verbose("HasExclusion","bots presence found, not denied")
                            return False
                verbose("HasExclusion","Exclusion check has managed to not hit a return")

def IterateCategory(category,torun):
    #Iterates all wikilinks of a category, even if multi-paged
    #Note: If the page scanning is successful, make sure to return True, or else this wont know
    lastpage = ""
    catpage = Article(category)
    if not catpage.exists():
        log(f"Attempting to iterate {category} despite it not existing")
    links = catpage.GetWikiLinks('ion">learn more</a>).')
    for page in links:
        if torun(page):
            lastpage = page
    #If we dont get a lastpage in the first place, its either empty, or the task needs configuring. Escape either way
    if not lastpage:
        verbose("IterateCategory",f"'{category}' had no returned lastpage on its first try")
    while lastpage:
        newlastpage = ""
        catpage = Article(category+"?from="+lastpage)
        links = catpage.GetWikiLinks('ion">learn more</a>).')
        for page in links:
            if torun(page):
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
    log(f"[!] Failed to log-in as {username}, check the password and username are correct")
    exit()
log("Successfully logged in")

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
        log(f"[Tasks] Task {file} loading error -> {exc}")
log("Finished loading tasks")
while True:
    time.sleep(60)
    tasks = threading.active_count()
    # log(f"Active task count: {tasks-1}")
    if tasks == 1:
        log("All tasks seem to have been terminated or finished")
        break
    panic = Article(f"User:{username}/panic")
    if panic.exists():
        if panic.GetRawContent().strip().lower() == "true":
            activelyStopped = True
        else:
            activelyStopped = False
    else:
        verbose("Main Thread",f"Panic page (User:{username}/panic) doesn't exist")
input("Press enter to exit...")
