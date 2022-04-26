#This task will go through all pages in Category:CS1_errors:_format_without_URL and fix clear-cut cases of the improper use of format

maincat = "Category:CS1_errors:_format_without_URL"
FormatLocator = regex.compile("\| *format *= *[^|}]+(\||})")
FixCases = ["e?-?book","newspaper","magazine","letter","script","(hard|paper)(back|cover)","novel","print","dvd","blu-?ray","disc"]
def CheckPageForErrors(page):
    namespace = GetNamespace(page)
    if namespace != "Article":
        print("Skipping page not in article namespace",page)
        return
    try:
        raw = GetRawWikiText(page)
    except:
        print("Couldnt get raw of",page)
        return
    # print("Processing",page)
    lastpage = page
    try:
        CiteReferences = GetReferences(raw)
        anychanges = False
        for ref in CiteReferences: #Its a citation error, so look in citations
            refinfo = GetReferenceParameters(ref)
            if "format" in refinfo and not "url" in refinfo: #Cause of the error
                for reg in FixCases:
                    if regex.compile(reg).search(refinfo["format"].lower()):
                        #This is really shady but it works surprisingly well in testing
                        PrecisePosition = FormatLocator.search(ref).span()
                        formatPos = ref.find("format",PrecisePosition[0],PrecisePosition[1])
                        fix = SubstituteIntoString(ref,"type",formatPos,formatPos+6)
                        raw = raw.replace(ref,fix)
                        # print("Found and fixed a case. format=",refinfo["format"],"template=",refinfo["__TEMPLATE"])
                        anychanges = True
        if anychanges:
            ChangeWikiPage(page,raw,f"Changing |format= to |type= (CS1 Error: [[Category:CS1 errors: format without URL||format= without |url=]])")
        return True
    except Exception as exc:
        log(f"Failed to process {page} due to the error of {exc}")
IterateCategory(maincat,CheckPageForErrors)
